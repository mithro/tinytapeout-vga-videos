# SPDX-License-Identifier: Apache-2.0
"""`tt-vga frames`: turn a sampler's frame store into PNGs and back, hash it, and diff two frames.

A sampler directory holds `frames.txt` and its STORE, a zstd file of the distinct frames' rgb6 bytes
(one byte per pixel, R<<4 | G<<2 | B) back to back. vgacap's own reader, writers and hash functions
do the format work; this module only moves frames between STORE and PNG.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

from compression import zstd

from ttvga import devtools
from ttvga.harness import pngio, vgacap_path

METHODS = ("sha256-rgb6", "fnv1a64-tb2026-rgb888")
_SPEC = re.compile(r"(.+)([:@])([0-9]+)\Z")
_PAIRS = 10


class FramesError(Exception):
    """A frames command cannot do what was asked; the message is for the user."""


def _vgacap():
    vgacap_path.add_src(devtools.paths().vgacap_src)
    from vgacap import framesfile, hashes

    return framesfile, hashes


def _read_frames_txt(path: Path):
    framesfile, _ = _vgacap()
    try:
        return framesfile.read_frames_txt(path)
    except (OSError, ValueError) as e:
        raise FramesError(f"{path}: {e}") from None


def _read_store(ff, directory: Path) -> bytes:
    """The uncompressed store of `ff`, checked against its length and SHA-256."""
    path = directory / ff.store
    try:
        data = zstd.decompress(path.read_bytes())
    except (OSError, zstd.ZstdError) as e:
        raise FramesError(f"{path}: {e}") from None
    n = ff.width * ff.height
    if len(data) != ff.store_length or len(data) != len(ff.distinct) * n:
        raise FramesError(f"{path}: {len(data)} bytes, frames.txt says store_length {ff.store_length}")
    if hashlib.sha256(data).hexdigest() != ff.store_sha256:
        raise FramesError(f"{path}: SHA-256 differs from store_sha256 in frames.txt")
    return data


def _distinct_frames(ff, store: bytes) -> list[bytes]:
    n = ff.width * ff.height
    return [store[k * n:(k + 1) * n] for k in range(len(ff.distinct))]


def load_frame(spec: str) -> tuple[int, int, bytes]:
    """(width, height, rgb6) of `STORE:N` (distinct frame N), `STORE@F` (captured frame F) or a PNG.

    STORE is the store file named in the `frames.txt` beside it. Raises ValueError if the frame is
    not there (a captured frame that is a gap, an index out of range, an unreadable file).
    """
    m = _SPEC.fullmatch(spec)
    if not spec.endswith(".png") and m:
        path, kind, number = Path(m[1]), m[2], int(m[3])
        try:
            ff = _read_frames_txt(path.parent / "frames.txt")
            if path.name != ff.store:
                raise FramesError(f"{path}: frames.txt beside it names the store {ff.store}")
            distinct = _distinct_frames(ff, _read_store(ff, path.parent))
        except FramesError as e:
            raise ValueError(str(e)) from None
        if kind == ":":
            if number >= len(distinct):
                raise ValueError(f"{spec}: distinct frame {number} out of range (the store has {len(distinct)})")
            return ff.width, ff.height, distinct[number]
        if number >= len(ff.frames):
            raise ValueError(f"{spec}: frame {number} out of range (frames.txt has {len(ff.frames)})")
        d = ff.frames[number].distinct
        if d < 0:
            raise ValueError(f"{spec}: frame {number} is a gap, it has no pixels")
        return ff.width, ff.height, distinct[d]
    return pngio.read_rgb6(spec)


def _fail(message: str) -> int:
    print(f"tt-vga: {message}", file=sys.stderr)
    return 1


def to_png(args: argparse.Namespace) -> int:
    txt = Path(args.frames_txt)
    ff = _read_frames_txt(txt)
    frames = _distinct_frames(ff, _read_store(ff, txt.parent))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for k, rgb6 in enumerate(frames):
        pngio.write_rgb6(out / f"{k:06d}.png", ff.width, ff.height, rgb6)
    print(f"{len(frames)} PNGs of {ff.width}x{ff.height} in {out}")
    return 0


def from_png(args: argparse.Namespace) -> int:
    ff = _read_frames_txt(Path(args.frames))
    files = sorted(Path(args.dir).glob("*.png"))
    want = [f"{k:06d}.png" for k in range(len(ff.distinct))]
    if [p.name for p in files] != want:
        return _fail(f"{args.dir} must hold exactly {len(want)} PNGs named {want[0] if want else ''} ... "
                     f"({len(files)} found)")
    parts = []
    for p in files:
        w, h, rgb6 = pngio.read_rgb6(p)
        if (w, h) != (ff.width, ff.height):
            return _fail(f"{p} is {w}x{h}, frames.txt has {ff.width}x{ff.height}")
        parts.append(rgb6)
    store = b"".join(parts)
    Path(args.out).write_bytes(zstd.compress(store))
    sha = hashlib.sha256(store).hexdigest()
    print(f"{len(parts)} frames, {len(store)} bytes, sha256 {sha} "
          f"({'matches' if sha == ff.store_sha256 else 'differs from'} frames.txt)")
    return 0


def hash_frames(args: argparse.Namespace) -> int:
    framesfile, hashes = _vgacap()
    txt = Path(args.frames_txt)
    ff = _read_frames_txt(txt)
    frames = _distinct_frames(ff, _read_store(ff, txt.parent))
    if args.method == "sha256-rgb6":
        per = [hashes.sha256_rgb6(f) for f in frames]
    else:
        per = [f"{hashes.fnv1a64_tb2026_rgb888(f):016x}" for f in frames]
    framesfile.write_hash_file(args.out, framesfile.HashFile.from_frames(ff, args.method, per))
    return 0


def _channels(v: int) -> str:
    return f"{(v >> 4) & 3},{(v >> 2) & 3},{v & 3}"


def diff(args: argparse.Namespace) -> int:
    try:
        wa, ha, a = load_frame(args.a)
        wb, hb, b = load_frame(args.b)
    except ValueError as e:
        return _fail(str(e))
    if (wa, ha) != (wb, hb):
        return _fail(f"A is {wa}x{ha} and B is {wb}x{hb}; only frames of one shape can be compared")
    idx = [i for i in range(len(a)) if a[i] != b[i]]
    per = [sum(1 for i in idx if (a[i] ^ b[i]) >> s & 3) for s in (4, 2, 0)]
    print(f"differing_pixels: {len(idx)}")
    if idx:
        xs, ys = [i % wa for i in idx], [i // wa for i in idx]
        print(f"bbox: {min(xs)} {min(ys)} {max(xs) + 1} {max(ys) + 1}")
    else:
        print("bbox: none")
    print(f"per_channel: r {per[0]} g {per[1]} b {per[2]}")
    pairs = Counter((a[i], b[i]) for i in idx)
    for (va, vb), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:_PAIRS]:
        print(f"{_channels(va)} -> {_channels(vb)}: {n}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pngio.write_rgb6(out / "a.png", wa, ha, a)
    pngio.write_rgb6(out / "b.png", wa, ha, b)
    mask = bytearray(len(a))
    for i in idx:
        mask[i] = 63
    pngio.write_rgb6(out / "mask.png", wa, ha, bytes(mask))
    return 0


def _run(func):
    def wrapper(args: argparse.Namespace) -> int:
        try:
            return func(args)
        except FramesError as e:
            return _fail(str(e))
    return wrapper


def add_parser(sub: argparse._SubParsersAction) -> None:
    f = sub.add_parser("frames", help="frame stores: to PNG, from PNG, hash, diff")
    fs = f.add_subparsers(dest="frames_command", required=True)

    p = fs.add_parser("to-png", help="write each distinct frame of a frames.txt's store as NNNNNN.png",
                      description="Write one 8-bit indexed PNG per distinct frame, named like the harness's png/ directory.")
    p.add_argument("frames_txt", metavar="FRAMES_TXT")
    p.add_argument("--out", required=True, metavar="DIR")
    p.set_defaults(func=_run(to_png))

    p = fs.add_parser("from-png", help="pack a directory of NNNNNN.png into a zstd store",
                      description="Pack DIR's PNGs (one per distinct frame of FRAMES_TXT) into a zstd-compressed store.")
    p.add_argument("dir", metavar="DIR")
    p.add_argument("--frames", required=True, metavar="FRAMES_TXT")
    p.add_argument("--out", required=True, metavar="STORE")
    p.set_defaults(func=_run(from_png))

    p = fs.add_parser("hash", help="write a frame_hashes file for a frames.txt (same bytes as vgacap-sample)",
                      description="Hash each distinct frame and write the hash file vgacap-sample would. "
                                  "Warning: fnv1a64-tb2026-rgb888 is computed in Python and takes about "
                                  "0.15 s per 640x480 frame; sha256-rgb6 is fast.")
    p.add_argument("frames_txt", metavar="FRAMES_TXT")
    p.add_argument("--method", required=True, choices=METHODS, metavar="ID", help=" or ".join(METHODS))
    p.add_argument("--out", required=True, metavar="FILE")
    p.set_defaults(func=_run(hash_frames))

    p = fs.add_parser("diff", help="compare two frames and write a.png, b.png and mask.png",
                      description="A and B are each STORE:N (distinct frame N), STORE@F (captured frame F; "
                                  "frames.txt must sit beside STORE) or a PNG. Exit 1 if the shapes differ.")
    p.add_argument("a", metavar="A")
    p.add_argument("b", metavar="B")
    p.add_argument("--out", required=True, metavar="DIR")
    p.set_defaults(func=_run(diff))
