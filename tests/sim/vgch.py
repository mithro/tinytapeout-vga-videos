# SPDX-License-Identifier: Apache-2.0
"""Read a tb.cpp trace for the tests: decompress it and decode it with vgacap's own Python reader."""

from __future__ import annotations

import sys
from compression import zstd
from dataclasses import dataclass
from pathlib import Path

from ttvga.devtools import DevTools


def _stream(dev: DevTools):
    path = str(dev.vgacap_src / "python")
    if path not in sys.path:
        sys.path.insert(0, path)
    from vgacap import stream

    return stream


@dataclass
class Trace:
    header: object          # vgacap.stream.Header
    runs: list[tuple[int, int, int]]   # (first sample, value with its clock bit, run length)
    metas: list[dict[str, str]]        # every META chunk, in order
    samples: int

    def meta(self, kind: str) -> dict[str, str]:
        found = [m for m in self.metas if m.get("meta") == kind]
        assert len(found) == 1, f"{len(found)} META({kind}) chunks"
        return found[0]

    def value(self, n: int) -> int:
        """Sample n, with its clock bit."""
        for first, v, r in self.runs:
            if first <= n < first + r:
                clk = self.header.clock_first ^ (n & 1)
                return (v & ~(1 << self.header.clock_bit)) | (clk << self.header.clock_bit)
        raise IndexError(n)


def _parse_meta(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.rstrip("\n").split("\n"))


def read(path: Path, dev: DevTools) -> Trace:
    stream = _stream(dev)
    data = zstd.decompress(Path(path).read_bytes())
    header, items = stream.read_stream(data)
    # vgacap.stream.parse_header at the pin (d8df216) reuses the name `clock`
    # for "has a clock bit", so a v2 header's clock_hz comes back as a bool.
    # Take clock_hz from the VGCH payload itself (u32 at offset 4,
    # docs/trace-format.md) until vgacap fixes it.
    tag, payload = next(stream.read_chunks(data))
    assert tag == "VGCH"
    header.clock_hz = int.from_bytes(payload[4:8], "little")
    runs, metas, n = [], [], 0
    for item in items:
        if item[0] == "run":
            runs.append((n, item[1], item[2]))
            n += item[2]
        elif item[0] == "meta":
            metas.append(_parse_meta(item[1]))
        elif item[0] == "block":
            assert item[1] == n
    return Trace(header=header, runs=runs, metas=metas, samples=n)
