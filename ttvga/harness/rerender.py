#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild the previews from clips that already exist. Runs on the host.

Usage: rerender.py --videos ~/public_html --root ~/ttvga [--jobs 16] [--only tt08,ttsky26a/tt_um_x]

Changing how a poster, contact sheet or animation looks does not need the
simulation again: the 60 second clip is already there. This walks the
published directory and re-renders the previews from it, which takes
seconds per project instead of minutes.
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

from job import render_previews  # noqa: E402


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
    args = ap.parse_args()

    ffmpeg = str(args.root / "tools" / "ffmpeg" / "bin" / "ffmpeg")
    only = [s for s in args.only.split(",") if s]
    clips = sorted(args.videos.glob("*/*/60s.avi"))
    jobs = []
    for clip in clips:
        macro, shuttle = clip.parent.name, clip.parent.parent.name
        if only and shuttle not in only and f"{shuttle}/{macro}" not in only:
            continue
        jobs.append((f"{shuttle}/{macro}", clip.parent, args.root / "work" / shuttle / macro))

    print(f"rerender: {len(jobs)} of {len(clips)} clips, {args.jobs} at a time", flush=True)
    done = failed = 0

    def one(item):
        name, videos, work = item
        frames, fps = clip_shape(ffmpeg, videos / "60s.avi", work)
        log = work / "rerender.log" if work.exists() else videos / "rerender.log"
        error = render_previews(videos, log, {"ffmpeg": ffmpeg}, frames, fps)
        return name, error

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(one, j) for j in jobs]):
            name, error = future.result()
            done += 1
            if error:
                failed += 1
                print(f"rerender: {name}: {error}", flush=True)
            elif done % 25 == 0:
                print(f"rerender: {done} of {len(jobs)}", flush=True)
    print(f"rerender: finished, {done} done, {failed} failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
