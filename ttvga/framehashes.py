# SPDX-License-Identifier: Apache-2.0
"""Export each run's per-frame hashes as `data/results/<shuttle>/<macro>/frame_hashes.txt`.

The testbench hashes every captured frame (FNV-1a 64, see `fnv1a()` in
harness/tb.cpp) and puts the list in result.json. That list is most of the
file's size, so `tt-vga collect` takes it out of the committed result.json
and writes it here instead, one hash per line, frame 0 first. Other tools,
such as an FPGA harness checking its output against the simulation, can then
compare frame for frame without the clips, which are lossy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FILE_NAME = "frame_hashes.txt"
_SYNC = re.compile(r"tb: sync at clock (\d+)")


def capture_clock(result: dict) -> int | None:
    """The clock after which capture began, from the testbench's own log line.

    Probe runs are quiet and print no sync line, so the last match is the real run.
    """
    found = _SYNC.findall(result.get("sim_log_tail") or "")
    return int(found[-1]) if found else None


def render(result: dict) -> str:
    """The text of frame_hashes.txt for one result that still carries its hashes."""
    t = result["timing"]
    hashes = t["frame_hashes"]
    after = capture_clock(result)
    lines = [
        "# Per-frame hashes from the simulation, frame 0 first, one per line.",
        "# Hash: FNV-1a 64 over the frame as RGB888, row-major, active area only, at native",
        "# resolution, each 2-bit channel stored as value * 85, pixels sampled mid-period.",
        "# Stimulus: ena=1, rst_n=0 for 10 clocks, then 1. Clock 0 is the first reset clock.",
        "# Frame 0 starts at the first end of a vsync pulse after capture_after_clock.",
        f"id: {result['id']}",
        f"mode: {t.get('mode')}",
        f"width: {t.get('width')}",
        f"height: {t.get('height')}",
        f"clock_hz: {t.get('clock_hz')}",
        f"clocks_per_pixel: {t.get('clocks_per_pixel')}",
        f"capture_after_clock: {after if after is not None else 'unknown'}",
        f"frames: {len(hashes)}",
        "",
    ]
    return "\n".join(lines) + "".join(h + "\n" for h in hashes)


def export(result_path: Path) -> str:
    """Write the hash file beside one result.json and strip the list from it.

    Returns "written", "removed" (a stale file for a run that now has no
    frames), or "kept" (already exported earlier, nothing to do).
    """
    result = json.loads(result_path.read_text())
    timing = result.get("timing") or {}
    out = result_path.parent / FILE_NAME
    if "frame_hashes" in timing:
        out.write_text(render(result))
        timing["frame_hashes_count"] = len(timing.pop("frame_hashes"))
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        return "written"
    if "frame_hashes_count" not in timing and out.exists():
        out.unlink()
        return "removed"
    return "kept"
