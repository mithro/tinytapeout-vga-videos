# SPDX-License-Identifier: Apache-2.0
"""pngio: 8-bit indexed PNGs of rgb6 frames, written deterministically."""

from __future__ import annotations

import random
import struct
import zlib

import pytest

from ttvga.harness import pngio


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    out, i = [], 8
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        out.append((kind, data[i + 8:i + 8 + n]))
        i += 12 + n
    return out


@pytest.mark.parametrize("w,h", [(640, 480), (1, 1), (1280, 1024)])
def test_png_round_trip_is_byte_identical(tmp_path, w, h):
    rgb6 = random.Random(w * h).randbytes(w * h)
    rgb6 = bytes(b & 63 for b in rgb6)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    pngio.write_rgb6(a, w, h, rgb6)
    assert pngio.read_rgb6(a) == (w, h, rgb6)
    pngio.write_rgb6(b, w, h, pngio.read_rgb6(a)[2])
    assert a.read_bytes() == b.read_bytes()
    pngio.write_rgb6(b, w, h, rgb6)
    assert a.read_bytes() == b.read_bytes()


def test_png_palette_index_is_rgb6(tmp_path):
    assert len(pngio.PALETTE) == 192
    for i in range(64):
        assert pngio.PALETTE[3 * i:3 * i + 3] == bytes([((i >> 4) & 3) * 85, ((i >> 2) & 3) * 85, (i & 3) * 85])
    p = tmp_path / "x.png"
    pngio.write_rgb6(p, 64, 1, bytes(range(64)))
    chunks = png_chunks(p.read_bytes())
    assert [k for k, _ in chunks] == [b"IHDR", b"PLTE", b"IDAT", b"IEND"]
    ihdr = dict(zip(("w", "h", "depth", "colour", "comp", "filter", "interlace"), struct.unpack(">IIBBBBB", chunks[0][1])))
    assert ihdr == {"w": 64, "h": 1, "depth": 8, "colour": 3, "comp": 0, "filter": 0, "interlace": 0}
    assert chunks[1][1] == pngio.PALETTE
    # Filter type 0 on every row, and the pixel bytes are the palette indices.
    assert zlib.decompress(chunks[2][1]) == b"\x00" + bytes(range(64))
    assert chunks[2][1] == zlib.compress(b"\x00" + bytes(range(64)), 1)


def test_write_refuses_bad_input(tmp_path):
    with pytest.raises(ValueError):
        pngio.write_rgb6(tmp_path / "x.png", 2, 2, bytes(3))
    with pytest.raises(ValueError):
        pngio.write_rgb6(tmp_path / "x.png", 1, 1, bytes([64]))


def test_read_refuses_other_pngs(tmp_path):
    good = tmp_path / "good.png"
    pngio.write_rgb6(good, 4, 2, bytes(range(8)))
    data = good.read_bytes()

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    def png(ihdr=struct.pack(">IIBBBBB", 4, 2, 8, 3, 0, 0, 0), plte=pngio.PALETTE, rows=b"\x00" + bytes(4) + b"\x00" + bytes(4)):
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"PLTE", plte) + chunk(b"IDAT", zlib.compress(rows, 1)) + chunk(b"IEND", b"")

    assert pngio.read_rgb6(_write(tmp_path, "ok.png", png()))[:2] == (4, 2)
    bad = {
        "not a png": b"hello",
        "truncated": data[:-5],
        "trailing": data + b"x",
        "rgb colour type": png(ihdr=struct.pack(">IIBBBBB", 4, 2, 8, 2, 0, 0, 0)),
        "interlaced": png(ihdr=struct.pack(">IIBBBBB", 4, 2, 8, 3, 0, 0, 1)),
        "4-bit": png(ihdr=struct.pack(">IIBBBBB", 4, 2, 4, 3, 0, 0, 0)),
        "other palette": png(plte=bytes(192)),
        "short palette": png(plte=pngio.PALETTE[:30]),
        "filter 1": png(rows=b"\x01" + bytes(4) + b"\x00" + bytes(4)),
        "index 64": png(rows=b"\x00" + bytes([64, 0, 0, 0]) + b"\x00" + bytes(4)),
        "short data": png(rows=b"\x00" + bytes(4)),
        "bad crc": data[:-1] + bytes([data[-1] ^ 1]),
    }
    for name, content in bad.items():
        with pytest.raises(ValueError):
            pngio.read_rgb6(_write(tmp_path, "bad.png", content))
        # (the message names the file)
    with pytest.raises(ValueError, match="bad.png"):
        pngio.read_rgb6(_write(tmp_path, "bad.png", b"hello"))


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content)
    return p


@pytest.mark.parametrize("bad", [64, 255])
def test_write_rgb6_refuses_a_byte_above_63(tmp_path, bad):
    px = bytearray(16 * 16)
    px[200] = bad
    with pytest.raises(ValueError, match="not an rgb6 value"):
        pngio.write_rgb6(tmp_path / "x.png", 16, 16, bytes(px))
    assert not (tmp_path / "x.png").exists()
