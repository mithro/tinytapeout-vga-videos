# SPDX-License-Identifier: Apache-2.0
"""`tt-vga frames`: turn a sampler's frame store into PNGs and back, hash it, diff two frames, compare two runs.

A sampler directory holds `frames.txt` and its STORE, a zstd file of the distinct frames' rgb6 bytes
(one byte per pixel, R<<4 | G<<2 | B) back to back. vgacap's own reader, writers and hash functions
do the format work; this module only moves frames between STORE and PNG.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import xxhash
from compression import zstd

from ttvga import devtools
from ttvga.harness import pngio, vgacap_path

METHODS = ("xxh3-128-rgb6", "fnv1a64-tb2026-rgb888")
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
    """The uncompressed store of `ff`, checked against its length and XXH3-128."""
    path = directory / ff.store
    try:
        data = zstd.decompress(path.read_bytes())
    except (OSError, zstd.ZstdError) as e:
        raise FramesError(f"{path}: {e}") from None
    n = ff.width * ff.height
    if len(data) != ff.store_length or len(data) != len(ff.distinct) * n:
        raise FramesError(f"{path}: {len(data)} bytes, frames.txt says store_length {ff.store_length}")
    if xxhash.xxh3_128_hexdigest(data) != ff.store_xxh3_128:
        raise FramesError(f"{path}: XXH3-128 differs from store_xxh3_128 in frames.txt")
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
    distinct = _distinct_frames(ff, _read_store(ff, txt.parent))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for k, rgb6 in enumerate(distinct):
        pngio.write_rgb6(out / f"{k:06d}.png", ff.width, ff.height, rgb6)
    print(f"{len(distinct)} PNGs of {ff.width}x{ff.height} in {out}")
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
        try:
            w, h, rgb6 = pngio.read_rgb6(p)
        except ValueError as e:
            return _fail(str(e))
        if (w, h) != (ff.width, ff.height):
            return _fail(f"{p} is {w}x{h}, frames.txt has {ff.width}x{ff.height}")
        parts.append(rgb6)
    store = b"".join(parts)
    Path(args.out).write_bytes(zstd.compress(store))
    digest = xxhash.xxh3_128_hexdigest(store)
    print(f"{len(parts)} frames, {len(store)} bytes, xxh3-128 {digest} "
          f"({'matches' if digest == ff.store_xxh3_128 else 'differs from'} frames.txt)")
    return 0


def hash_frames(args: argparse.Namespace) -> int:
    framesfile, hashes = _vgacap()
    txt = Path(args.frames_txt)
    ff = _read_frames_txt(txt)
    distinct = _distinct_frames(ff, _read_store(ff, txt.parent))
    if args.method == "xxh3-128-rgb6":
        per = [hashes.xxh3_128_rgb6(f) for f in distinct]
    else:
        per = [f"{hashes.fnv1a64_tb2026_rgb888(f):016x}" for f in distinct]
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
    _diff_report(wa, ha, a, b, Path(args.out))
    return 0


def _diff_report(wa: int, ha: int, a: bytes, b: bytes, out: Path | None) -> None:
    """Print the `frames diff` lines for two frames of one shape; with `out`, write a.png, b.png, mask.png."""
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
    if out is None:
        return
    out.mkdir(parents=True, exist_ok=True)
    pngio.write_rgb6(out / "a.png", wa, ha, a)
    pngio.write_rgb6(out / "b.png", wa, ha, b)
    mask = bytearray(len(a))
    for i in idx:
        mask[i] = 63
    pngio.write_rgb6(out / "mask.png", wa, ha, bytes(mask))


# ---- compare ---------------------------------------------------------------

MAX_OFFSET = 120
MIN_PAIRS = 10
_DELTA_LINES = 5


class CompareError(FramesError):
    """Two runs that cannot be compared (hash methods differ); exit 2."""


@dataclass
class Comparison:
    """`frames compare` of runs A and B. Counts are of each run's frames (gaps included) and gaps.

    `offset` d means b[j + d] shows a[j] for every frame j >= first_mismatch with data in both.
    `start_clock_deltas` (two frames.txt only) counts b's start clock minus a's over the pairs:
    offset 0 before first_mismatch, `offset` (or 0 when there is none) from it on.
    """
    first_mismatch: int | None
    offset: int | None
    start_clock_deltas: dict[int, int] | None
    frames_a: int
    frames_b: int
    gaps_a: int
    gaps_b: int


@dataclass
class _Run:
    path: Path
    method: str                # xxh3-128-rgb6 for a frames.txt (its distinct hashes are XXH3-128 of rgb6)
    keys: list[str | None]     # frame k's hash, None for a gap
    ff: object | None          # the FramesFile, for a frames.txt


def _load_run(path: Path) -> _Run:
    framesfile, _ = _vgacap()
    try:
        with open(path, encoding="utf-8", newline="") as f:
            first = f.readline()
        if first.startswith("hash_method: "):
            hf = framesfile.read_hash_file(path)
            return _Run(path, hf.method, list(hf.hashes), None)
        ff = framesfile.read_frames_txt(path)
    except (OSError, ValueError) as e:
        raise FramesError(f"{path}: {e}") from None
    keys = [None if f.distinct < 0 else ff.distinct[f.distinct] for f in ff.frames]
    return _Run(path, "xxh3-128-rgb6", keys, ff)


def _offsets():
    yield 0
    for n in range(1, MAX_OFFSET + 1):
        yield -n
        yield n


def _fits(a: list, b: list, k: int, d: int) -> bool:
    pairs = 0
    for j in range(max(k, -d), min(len(a), len(b) - d)):
        x, y = a[j], b[j + d]
        if x is None or y is None:
            continue
        if x != y:
            return False
        pairs += 1
    return pairs >= MIN_PAIRS


def _pair_offset(j: int, k: int | None, offset: int | None) -> int:
    return offset if k is not None and j >= k and offset is not None else 0


def compare(a: Path, b: Path) -> Comparison:
    """Compare two runs, each a frames.txt or a hash file. Raises CompareError if they cannot be compared."""
    ra, rb = _load_run(Path(a)), _load_run(Path(b))
    kinds = {r.path: ("frames.txt" if r.ff is not None else f"a {r.method} hash file") for r in (ra, rb)}
    if ra.method != rb.method:
        raise CompareError(f"{ra.path} is {kinds[ra.path]} and {rb.path} is {kinds[rb.path]}; "
                           f"only runs of one hash method compare (a frames.txt compares as xxh3-128-rgb6)")
    ka, kb = ra.keys, rb.keys
    k = next((j for j in range(min(len(ka), len(kb)))
              if ka[j] is not None and kb[j] is not None and ka[j] != kb[j]), None)
    if k is None:
        offset = 0 if _fits(ka, kb, 0, 0) else None
    else:
        offset = next((d for d in _offsets() if _fits(ka, kb, k, d)), None)
    deltas = None
    if ra.ff is not None and rb.ff is not None:
        deltas = Counter()
        fa, fb = ra.ff.frames, rb.ff.frames
        for j in range(len(fa)):
            jb = j + _pair_offset(j, k, offset)
            if 0 <= jb < len(fb) and fa[j].distinct >= 0 and fb[jb].distinct >= 0:
                deltas[fb[jb].start_clock - fa[j].start_clock] += 1
        deltas = dict(deltas)
    return Comparison(k, offset, deltas, len(ka), len(kb), ka.count(None), kb.count(None))


def _store_frame(run: _Run, j: int) -> tuple[int, int, bytes] | None:
    """Frame j of a frames.txt run from its store, or None when the store is not beside it."""
    if run.ff is None or not (run.path.parent / run.ff.store).is_file():
        return None
    return load_frame(f"{run.path.parent / run.ff.store}@{j}")


def _trace_of(run: _Run) -> Path | None:
    """The project's trace beside a published `<sampler>/frames.txt`, or None when it is not there."""
    if run.ff is None:
        return None
    suffix = f"_{run.ff.sampler}_frames.rgb6.zst"
    if not run.ff.store.endswith(suffix):
        return None
    trace = run.path.parent.parent / f"{run.ff.store[:-len(suffix)]}_trace.vgch.zst"
    return trace if trace.is_file() else None


def compare_cmd(args: argparse.Namespace) -> int:
    try:
        c = compare(Path(args.run_a), Path(args.run_b))
    except CompareError as e:
        print(f"tt-vga: {e}", file=sys.stderr)
        return 2
    none = lambda v: "none" if v is None else str(v)  # noqa: E731
    print(f"frames_a: {c.frames_a}")
    print(f"frames_b: {c.frames_b}")
    print(f"gaps_a: {c.gaps_a}")
    print(f"gaps_b: {c.gaps_b}")
    print(f"first_mismatch: {none(c.first_mismatch)}")
    print(f"offset: {none(c.offset)}")
    if c.start_clock_deltas is not None:
        for delta, n in sorted(c.start_clock_deltas.items(), key=lambda kv: (-kv[1], kv[0]))[:_DELTA_LINES]:
            print(f"start_clock_delta: {delta} x{n}")
    k = c.first_mismatch
    if k is None:
        return 0
    ra, rb = _load_run(Path(args.run_a)), _load_run(Path(args.run_b))
    try:
        fa, fb = _store_frame(ra, k), _store_frame(rb, k)
    except ValueError as e:
        raise FramesError(str(e)) from None
    if fa is not None and fb is not None:
        if fa[:2] != fb[:2]:
            print(f"diff: none, frame {k} is {fa[0]}x{fa[1]} in A and {fb[0]}x{fb[1]} in B")
        else:
            _diff_report(fa[0], fa[1], fa[2], fb[2], Path(args.out) if args.out else None)
    for name, run in (("a", ra), ("b", rb)):
        if _trace_of(run) is not None:
            c0 = run.ff.frames[k].start_clock
            print(f"trace_range_{name}: --from {c0} --to {c0 + run.ff.frame_clocks}")
    return 0


def _run(func):
    """`func` with a FramesError or an OSError (a file that cannot be read or written) as exit 1 and a message."""
    def wrapper(args: argparse.Namespace) -> int:
        try:
            return func(args)
        except FramesError as e:
            return _fail(str(e))
        except OSError as e:
            return _fail(f"{e.filename}: {e.strerror}" if e.filename else str(e))
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
                                  "0.15 s per 640x480 frame; xxh3-128-rgb6 is fast.")
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

    p = fs.add_parser("compare", help="first mismatch, frame offset and start-clock deltas of two runs",
                      description="RUN_A and RUN_B are each a frames.txt or a frame_hashes file. Two hash files "
                                  "must share a method; a frames.txt compares only with frames.txt or a "
                                  "xxh3-128-rgb6 file (otherwise exit 2). A gap is no data, never a mismatch. "
                                  "offset d: b[j + d] shows a[j] for every frame j from the first mismatch on "
                                  f"with data in both, |d| <= {MAX_OFFSET}, over at least {MIN_PAIRS} pairs. "
                                  "With both stores beside their frames.txt, the first mismatching pair is "
                                  "diffed; with the traces present, their clock ranges are printed.")
    p.add_argument("run_a", metavar="RUN_A")
    p.add_argument("run_b", metavar="RUN_B")
    p.add_argument("--out", metavar="DIR", help="write the first mismatching pair's a.png, b.png and mask.png here")
    p.set_defaults(func=_run(compare_cmd))
