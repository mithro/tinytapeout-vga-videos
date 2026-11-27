# SPDX-License-Identifier: Apache-2.0
"""PNGs of rgb6 frames: 8-bit indexed, one fixed 64-entry palette (standard library only).

The pixel byte is the rgb6 value `rr gg bb` (two bits each), so the file's pixels are
the frame's own bytes. Encoding is deterministic: one IDAT, filter type 0 on every row,
zlib at a fixed level, no ancillary chunks. The same frame always gives the same bytes.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PALETTE: bytes = bytes(c for i in range(64) for c in (((i >> 4) & 3) * 85, ((i >> 2) & 3) * 85, (i & 3) * 85))
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_RGB6 = bytes(range(64))


def _is_rgb6(data: bytes | bytearray) -> bool:
    """Every byte is 0..63. `translate` runs in C; `max()` walks Python ints (5 ms a 640x480 frame)."""
    return not data.translate(None, _RGB6)


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def write_rgb6(path: str | Path, width: int, height: int, rgb6: bytes, level: int = 1) -> None:
    """Write `rgb6` (width * height bytes, each 0..63) as an indexed PNG."""
    if width < 1 or height < 1:
        raise ValueError(f"bad size {width}x{height}")
    if len(rgb6) != width * height:
        raise ValueError(f"{len(rgb6)} bytes for {width}x{height}")
    if not _is_rgb6(rgb6):
        raise ValueError("a byte is not an rgb6 value (0..63)")
    rows = b"".join(b"\x00" + rgb6[y * width:(y + 1) * width] for y in range(height))
    data = (_SIGNATURE
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
            + _chunk(b"PLTE", PALETTE)
            + _chunk(b"IDAT", zlib.compress(rows, level))
            + _chunk(b"IEND", b""))
    Path(path).write_bytes(data)


def read_rgb6(path: str | Path) -> tuple[int, int, bytes]:
    """Read a PNG written by `write_rgb6`: (width, height, rgb6). Anything else is a ValueError."""
    try:
        return _read(Path(path).read_bytes())
    except (ValueError, struct.error, zlib.error) as e:
        raise ValueError(f"{path}: not an rgb6 PNG: {e}") from None


def _read(data: bytes) -> tuple[int, int, bytes]:
    if data[:8] != _SIGNATURE:
        raise ValueError("bad signature")
    chunks, i = [], 8
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        crc = data[i + 8 + n:i + 12 + n]
        if len(body) != n or len(crc) != 4 or struct.unpack(">I", crc)[0] != zlib.crc32(kind + body):
            raise ValueError(f"bad {kind!r} chunk")
        chunks.append((kind, body))
        i += 12 + n
    if [k for k, _ in chunks] != [b"IHDR", b"PLTE", b"IDAT", b"IEND"] or chunks[3][1]:
        raise ValueError("chunks are not IHDR, PLTE, IDAT, IEND")
    if len(chunks[0][1]) != 13:
        raise ValueError("bad IHDR")
    width, height, depth, colour, comp, filt, interlace = struct.unpack(">IIBBBBB", chunks[0][1])
    if (depth, colour, comp, filt, interlace) != (8, 3, 0, 0, 0) or width < 1 or height < 1:
        raise ValueError("not 8-bit indexed, non-interlaced")
    if chunks[1][1] != PALETTE:
        raise ValueError("the palette is not the rgb6 palette")
    raw = zlib.decompress(chunks[2][1])
    if len(raw) != height * (width + 1):
        raise ValueError("wrong amount of pixel data")
    out = bytearray()
    for y in range(height):
        row = raw[y * (width + 1):(y + 1) * (width + 1)]
        if row[0] != 0:
            raise ValueError(f"row {y}: filter {row[0]}, expected 0")
        out += row[1:]
    if not _is_rgb6(out):
        raise ValueError("a pixel is not an rgb6 value")
    return width, height, bytes(out)
