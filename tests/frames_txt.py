# SPDX-License-Identifier: Apache-2.0
"""frames.txt files for tests that need vgacap's reader to accept (or refuse) them."""

from __future__ import annotations

from pathlib import Path


def write_frames_txt(framesfile, path: Path, pid: str, sampler: str, store: str, distinct: int):
    """A frames.txt in the current format, through vgacap's own writer. Returns the FramesFile."""
    ff = framesfile.FramesFile(
        id=pid, status="ok", sampler=sampler, sampler_status="ok", width=8, height=6, mode="test",
        clock_hz=25000000, clocks_per_pixel=1.0, capture_after_clock=0, store=store,
        store_length=distinct * 48, store_xxh3_128="0" * 31 + "1", distinct=[f"{n:032x}" for n in range(distinct)],
        frames=[framesfile.Frame(n, 100 * n, 0) for n in range(distinct)],
        centre=framesfile.Centre((0, 0), (0, 0), 0, (0, 0), 0, 0) if sampler == "centre-v1" else None)
    framesfile.write_frames_txt(path, ff)
    return ff


def to_pre_xxh3(text: str) -> str:
    """The same frames.txt as the SHA-256 format wrote it: `store_sha256` and 64-digit digests."""
    out = []
    for line in text.splitlines():
        if line.startswith("store_xxh3_128: "):
            line = "store_sha256: " + line.split(": ")[1] * 2
        elif len(line) == 32 and set(line) <= set("0123456789abcdef"):
            line = line * 2
        out.append(line)
    return "\n".join(out) + "\n"
