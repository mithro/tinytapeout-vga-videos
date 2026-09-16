#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild the published clips and previews from what is already there. Runs on the host.

Usage: rerender.py --videos ~/public_html --root ~/ttvga [--jobs 16] [--only tt08,ttsky26a/tt_um_x]

Changing how a poster, contact sheet or animation looks does not need the
simulation again: the long clip is already there. This walks the published
directory and re-renders from it, which takes seconds per project instead of
minutes.

It also migrates a project that still holds the old motion JPEG AVIs, by
transcoding them into the MP4 and WebM a browser can play. The AVIs are left
in place unless `--drop-legacy` is given: they are the only copy of the
simulation's output, and re-making one costs minutes of machine time.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from encode import LENGTHS, render_previews, stem_for, transcode  # noqa: E402

# What the published directory held before the clips became browser-playable.
LEGACY = ("60s.avi", "30s.avi", "10s.avi", "poster.png", "contact.png", "preview.gif")
LEGACY_CAPTURE = "60s.avi"


def clip_shape(ffmpeg: str, clip: Path, work: Path) -> tuple[int, float]:
    """Frames and frame rate for a clip, from the simulation's own record if it is there."""
    timing = work / "timing.json"
    if timing.exists():
        try:
            t = json.loads(timing.read_text())
            if t.get("frames") and t.get("fps"):
                return int(t["frames"]), float(t["fps"])
        except (json.JSONDecodeError, ValueError):
            pass
    probe = Path(ffmpeg).with_name("ffprobe")
    out = subprocess.run([str(probe), "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate:format=duration",
                          "-of", "default=nw=1:nk=1", str(clip)], capture_output=True, text=True)
    lines = out.stdout.split()
    fps, duration = 60.0, 60.0
    for line in lines:
        if "/" in line:
            num, _, den = line.partition("/")
            fps = float(num) / float(den or 1)
        else:
            duration = float(line)
    return int(duration * fps), fps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, default=Path.home() / "public_html")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only", default="", help="comma separated shuttles or <shuttle>/<macro> ids")
    ap.add_argument("--drop-legacy", action="store_true",
                    help="delete the superseded AVIs and unprefixed previews once the clips are written")
    ap.add_argument("--previews-only", action="store_true",
                    help="re-render the previews but do not transcode anything")
    args = ap.parse_args()

    ffmpeg = str(args.root / "tools" / "ffmpeg" / "bin" / "ffmpeg")
    only = [s for s in args.only.split(",") if s]
    # Match on the directory, not on one file name: a project part way through
    # the move to browser-playable clips has some of each.
    dirs = sorted(p for p in args.videos.glob("*/*") if p.is_dir())
    jobs = []
    for videos in dirs:
        macro, shuttle = videos.name, videos.parent.name
        if only and shuttle not in only and f"{shuttle}/{macro}" not in only:
            continue
        stem = stem_for(shuttle, macro)
        if not (videos / f"{stem}_{LENGTHS[0]}s.mp4").exists() and not (videos / LEGACY_CAPTURE).exists():
            continue
        jobs.append((f"{shuttle}/{macro}", stem, videos, args.root / "work" / shuttle / macro))

    print(f"rerender: {len(jobs)} of {len(dirs)} projects, {args.jobs} at a time", flush=True)
    done = failed = migrated = 0

    def one(item):
        name, stem, videos, work = item
        log = work / "rerender.log" if work.exists() else videos / "rerender.log"
        mp4 = videos / f"{stem}_{LENGTHS[0]}s.mp4"
        moved = False
        if not mp4.exists():
            if args.previews_only:
                return name, f"no {mp4.name}", False
            error = transcode(videos / LEGACY_CAPTURE, videos, stem, log, ffmpeg)
            if error:
                return name, error, False
            moved = True
        frames, fps = clip_shape(ffmpeg, mp4, work)
        error = render_previews(videos, stem, log, ffmpeg, frames, fps)
        if error:
            return name, error, moved
        if args.drop_legacy:
            for old in LEGACY:
                (videos / old).unlink(missing_ok=True)
        return name, None, moved

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(one, j) for j in jobs]):
            name, error, moved = future.result()
            done += 1
            migrated += moved
            if error:
                failed += 1
                print(f"rerender: {name}: {error}", flush=True)
            elif done % 25 == 0:
                print(f"rerender: {done} of {len(jobs)} ({migrated} transcoded)", flush=True)
    print(f"rerender: finished, {done} done, {migrated} transcoded, {failed} failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
