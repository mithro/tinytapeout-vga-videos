# SPDX-License-Identifier: Apache-2.0
"""Turn a job's result.json into a verdict.

Verdicts, in the order they are checked:

| verdict                | meaning                                                     |
| ---------------------- | ----------------------------------------------------------- |
| skipped                | not attempted (analog, Wokwi, ...)                          |
| fetch-failed           | repo or commit not reachable                                |
| build-failed           | Verilator could not build the sources                       |
| partial                | wall-clock limit hit, but a clip of at least 1 s exists      |
| sim-timeout            | wall-clock limit hit before a usable clip                   |
| no-sync                | no periodic hsync/vsync seen during calibration             |
| bad-timing             | sync seen but not a plausible raster                        |
| unstable-sync          | line or frame period varied by more than 1%                 |
| encode-failed          | ffmpeg problem                                              |
| blank                  | nearly every frame is one flat colour                       |
| static                 | a picture, but it never changes: fine, or needs stimulus    |
| ok                     | stable raster with changing content                         |

`static` and `ok` are both successes; `static` is "successful but may need
more work" (a static image by design, or a design waiting for input).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ttvga import RESULTS_DIR

SUCCESS = {"ok", "static", "partial"}


def verdict(result: dict) -> tuple[str, str]:
    """Return (verdict, one-line reason) for a result.json record."""
    stage, error, timing = result.get("stage"), result.get("error"), result.get("timing") or {}
    if stage == "skipped":
        return "skipped", error or "skipped"
    if stage == "fetch" and error:
        return "fetch-failed", error
    if stage == "build" and error:
        return "build-failed", error
    if stage == "simulate" and error:
        if error == "wall-clock limit":
            return "sim-timeout", error
        if not timing:
            return "sim-crashed", error
    status = timing.get("status")
    if status == "sim-timeout" and timing.get("frames", 0) >= 60 and result.get("videos"):
        # Killed at the wall-clock limit but a usable clip was written.
        return "partial", (f"{timing['frames']} of {timing.get('target_frames', '?')} frames in "
                           f"{timing.get('wall_seconds', 0):.0f} s wall ({timing.get('mode')}, "
                           f"{timing.get('clocks_per_wall_second', 0) / 1e6:.2f} Mclk/s)")
    if status in ("no-sync", "bad-timing", "unstable-sync", "sim-timeout"):
        detail = (f"line {timing.get('line_clocks') or timing.get('hsync_period_clocks')} clocks, "
                  f"{timing.get('lines', '?')} lines, hsync transitions {timing.get('hsync_transitions', '?')}")
        return status, detail
    if stage == "encode" and error:
        return "encode-failed", error
    if error:
        return "error", error
    frames = timing.get("frames", 0)
    if frames == 0:
        return "no-sync", "no frames captured"
    uniform = timing.get("uniform_frames", 0)
    distinct = timing.get("distinct_frames", 0)
    mode = timing.get("mode", "unknown")
    if uniform >= frames * 0.95:
        colour = "black" if timing.get("black_frames", 0) >= uniform else "one colour"
        return "blank", f"{uniform}/{frames} frames are {colour} ({mode})"
    # Two distinct frames can already be an animation (Nyan cat alternates two
    # frames), so only a single unchanging frame counts as static.
    if distinct <= 1:
        return "static", f"{distinct} distinct frame(s) in {frames} ({mode}, {timing.get('width')}x{timing.get('height')})"
    return "ok", (f"{distinct} distinct frames of {frames} ({mode}, {timing.get('width')}x{timing.get('height')}, "
                  f"{timing.get('fps', 0):.1f} fps)")


def analyze_all(results_dir: Path = RESULTS_DIR) -> list[dict]:
    """Attach `verdict` and `reason` to every result.json under data/results and return them."""
    rows = []
    for path in sorted(results_dir.glob("*/*/result.json")):
        result = json.loads(path.read_text())
        v, reason = verdict(result)
        if result.get("verdict") != v or result.get("reason") != reason:
            result["verdict"], result["reason"] = v, reason
            path.write_text(json.dumps(result, indent=2) + "\n")
        rows.append(result)
    return rows


def run(args: argparse.Namespace) -> int:
    rows = analyze_all()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for v, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{n:5d}  {v}")
    if args.verbose:
        for r in rows:
            print(f"{r['id']:60s} {r['verdict']:14s} {r['reason']}")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("analyze", help="assign verdicts to collected results")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=run)
