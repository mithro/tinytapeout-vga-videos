#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that what is published is actually playable. Runs on the host.

Usage: verify.py --videos ~/public_html --root ~/ttvga [--decode 40]

Every check here exists because something got past the ones before it:

- a project can be missing a file, or hold one of zero bytes, when a run was
  stopped while it was being written;
- a clip can exist at a plausible size and still be truncated, so a sample is
  decoded from end to end rather than probed;
- a WebM can decode perfectly in every software player and still not play
  in Chrome on a machine with a hardware VP9 decoder, if it is full range.
  That one is checked on every file, because it is invisible otherwise;
- and a run's record can say it captured sound while the published clip is
  silent, because the encode that made the sound wrote somewhere else. The
  record is what the index believes, so the two have to be compared. The
  rate is checked with it: left to itself ffmpeg followed the 192 kHz capture
  into 96 kHz AAC, which is unusual enough that some decoders refuse it, and
  the clip plays perfectly everywhere it was tested.

Exits non-zero if anything fails, so it can gate a publish.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from encode import AUDIO_OUT_RATE, GIF_SECONDS, LENGTHS, clip_names, preview_names, stem_for  # noqa: E402


def probe(ffprobe: str, path: Path, entries: str, stream: str = "v:0") -> str:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", stream,
                          "-show_entries", entries, "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return out.stdout.strip()


def claims_audio(root: Path, name: str) -> bool:
    """Whether this project's own record says the run captured its sound."""
    result = root / "work" / name / "result.json"
    if not result.exists():
        return False
    try:
        timing = (json.loads(result.read_text()).get("timing") or {})
    except (json.JSONDecodeError, OSError):
        return False
    return bool(timing.get("audio_driven")) and bool(timing.get("audio_samples"))


def decodes(ffmpeg: str, path: Path) -> tuple[bool, str]:
    """Decode every frame and throw it away: catches truncation a probe misses."""
    p = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True)
    return p.returncode == 0, p.stderr.strip()[:160]


def projects(videos: Path) -> list[tuple[str, str, Path]]:
    out = []
    for d in sorted(videos.glob("*/*")):
        if d.is_dir():
            out.append((f"{d.parent.name}/{d.name}", stem_for(d.parent.name, d.name), d))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, default=Path.home() / "public_html")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--decode", type=int, default=40, help="how many projects to decode in full (0 to skip)")
    ap.add_argument("--jobs", type=int, default=16)
    args = ap.parse_args()

    bin_dir = args.root / "tools" / "ffmpeg" / "bin"
    ffmpeg, ffprobe = str(bin_dir / "ffmpeg"), str(bin_dir / "ffprobe")
    found = projects(args.videos)
    print(f"verifying {len(found)} projects in {args.videos}")
    failures: list[str] = []

    # 1. every file present and not empty
    incomplete = 0
    for name, stem, d in found:
        want = clip_names(stem) + preview_names(stem)
        missing = [w for w in want if not (d / w).exists()]
        empty = [w for w in want if (d / w).exists() and (d / w).stat().st_size == 0]
        if missing or empty:
            incomplete += 1
            failures.append(f"{name}: missing {missing}, empty {empty}")
    print(f"  complete: {len(found) - incomplete} of {len(found)}")

    # 2. colour range on every WebM: the fault that only a hardware decoder sees
    webms = sorted(args.videos.glob("*/*/*.webm"))
    ranges: Counter = Counter()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for path, out in zip(webms, pool.map(
                lambda p: probe(ffprobe, p, "stream=color_range,color_space"), webms)):
            ranges[out] += 1
            if not out.startswith("tv"):
                failures.append(f"{path.parent.parent.name}/{path.parent.name}/{path.name}: "
                                f"colour range {out or 'unknown'}, must be limited (tv)")
    print(f"  WebM colour range: {dict(ranges)}")

    # 3. previews are the length they should be
    odd = 0
    gifs = sorted(args.videos.glob("*/*/*_preview.gif"))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for path, out in zip(gifs, pool.map(lambda p: probe(ffprobe, p, "format=duration"), gifs)):
            try:
                d = float(out)
            except ValueError:
                d = 0.0
            if not 0.5 <= d <= GIF_SECONDS + 0.5:
                odd += 1
                failures.append(f"{path.parent.parent.name}/{path.parent.name}: preview is {d:.2f}s")
    print(f"  previews the right length: {len(gifs) - odd} of {len(gifs)}")

    # 4. a sample decoded end to end, with the cuts the length they claim
    if args.decode:
        sample = random.Random(0).sample(found, min(args.decode, len(found)))

        def check(item):
            name, stem, d = item
            bad = []
            for secs in LENGTHS:
                for ext in ("mp4", "webm"):
                    f = d / f"{stem}_{secs}s.{ext}"
                    if not f.exists():
                        continue
                    ok, err = decodes(ffmpeg, f)
                    if not ok:
                        bad.append(f"{f.name} does not decode: {err}")
                        continue
                    try:
                        dur = float(probe(ffprobe, f, "format=duration"))
                    except ValueError:
                        bad.append(f"{f.name} has no duration")
                        continue
                    if secs != LENGTHS[0] and abs(dur - secs) > 0.5:
                        bad.append(f"{f.name} is {dur:.2f}s, expected {secs}s")
            return name, bad

        broken = 0
        with ThreadPoolExecutor(max_workers=max(args.jobs // 2, 1)) as pool:
            for name, bad in pool.map(check, sample):
                if bad:
                    broken += 1
                    failures.extend(f"{name}: {b}" for b in bad)
        print(f"  decoded in full: {len(sample) - broken} of {len(sample)} sampled")

    # 5. a clip whose record claims sound has to have some
    claimed = [(name, stem, d) for name, stem, d in found if claims_audio(args.root, name)]
    if claimed:
        silent = 0
        for name, stem, d in claimed:
            bad = []
            for f in (d / f"{stem}_{LENGTHS[0]}s.mp4", d / f"{stem}_{LENGTHS[0]}s.webm"):
                if not f.exists():
                    continue
                rate = probe(ffprobe, f, "stream=sample_rate", stream="a:0")
                if not rate:
                    bad.append(f"{f.name} has no audio track")
                elif rate != AUDIO_OUT_RATE:
                    bad.append(f"{f.name} is {rate} Hz, expected {AUDIO_OUT_RATE}")
            if bad:
                silent += 1
                failures.append(f"{name}: run captured audio but {'; '.join(bad)}")
        print(f"  clips with the sound their record claims: {len(claimed) - silent} of {len(claimed)}")

    if failures:
        print(f"\n{len(failures)} problems:")
        for f in failures[:30]:
            print(f"  {f}")
        if len(failures) > 30:
            print(f"  ... and {len(failures) - 30} more")
    print(f"\nVERIFIED: {'yes' if not failures else 'NO'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
