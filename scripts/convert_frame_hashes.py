# SPDX-License-Identifier: Apache-2.0
"""Move each committed frame_hashes.txt to vgacap's tb-v1 FNV file (plan Task 17).

    uv run scripts/convert_frame_hashes.py [--seed-host HOST] >> tmp/t17.log 2>&1
    uv run scripts/convert_frame_hashes.py --dry-run [--seed-host HOST] >> tmp/t17.log 2>&1

For every `data/results/<s>/<m>/frame_hashes.txt` (the run before traces
existed), it writes
`data/results/<s>/<m>/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`
with vgacap's `write_hash_file`, removes the old file, and in `result.json`
drops `timing.frame_hashes_count` and adds
`"tb_v1": {"state": "stale", "trace_sha": null, "dropped": false}`.

Every project is converted and checked before anything is written; one
failure writes nothing. The checks: the hash lines are byte-identical to the
old file's, their number is `timing.frame_hashes_count`, `capture_after_clock`
is a number, `clocks_per_pixel` rounded to 4 decimals is timing's, the mode is
in tb.cpp's table, and the written file reads back with `read_hash_file`.

`--seed-host HOST` then rsyncs each converted file, as the host's dedicated
user, to `~/ttvga/work/<s>/<m>/frames/tb-v1/`, so the host's copy matches git.

`--dry-run` copies `data/results/` to a scratch tree under `tmp/`, converts
there, and prints the rsync commands `--seed-host` would run without running them.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ttvga import RESULTS_DIR, devtools, remote  # noqa: E402
from ttvga.harness import vgacap_path  # noqa: E402

vgacap_path.add_src(devtools.paths().vgacap_src)
from vgacap.framesfile import HashFile, format_hash_file, read_hash_file, write_hash_file  # noqa: E402
from vgacap.tbv1 import TB_MODES, cround  # noqa: E402

OLD_NAME = "frame_hashes.txt"
METHOD = "fnv1a64-tb2026-rgb888"
SAMPLER = "tb-v1"
NEW_REL = Path("frames") / SAMPLER / f"frame_hashes.{METHOD}.txt"
OFFSET_BASIS = "0x14650fb0739d0383"
TB_V1_STALE = {"state": "stale", "trace_sha": None, "dropped": False}
# The old header's keys, in order, after the seven comment lines.
OLD_KEYS = ("id", "hash_offset_basis", "mode", "width", "height", "clock_hz", "clocks_per_pixel",
            "capture_after_clock", "frames")
_UINT = re.compile(r"(0|[1-9][0-9]*)\Z")


class ConvertError(ValueError):
    """An old file cannot be converted exactly; the message names the file and the check."""


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def _parse_old(old: Path) -> tuple[dict[str, str], str]:
    """The old header's values, and the hash lines' text (everything after `frames: N`)."""
    text = old.read_text()
    lines = text.split("\n")
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        i += 1
    header: dict[str, str] = {}
    for key in OLD_KEYS:
        line = lines[i] if i < len(lines) else ""
        if not line.startswith(key + ": "):
            raise ConvertError(f"{old}: line {i + 1}: expected '{key}: ', got {line!r}")
        header[key] = line[len(key) + 2:]
        i += 1
    return header, "\n".join(lines[i:])


def _uint(old: Path, header: dict[str, str], key: str) -> int:
    v = header[key]
    if not _UINT.match(v):
        raise ConvertError(f"{old}: {key} is not a number: {v!r}")
    return int(v)


def tb_cpp_clocks_per_pixel(line_clocks: int, mode_name: str) -> float:
    """tb.cpp's clocks per pixel: line_clocks / the mode's line_px, rounded when within 0.01 (tb.cpp:641, 669)."""
    mode = next((m for m in TB_MODES if m[0] == mode_name), None)
    if mode is None:
        raise ConvertError(f"mode {mode_name!r} is not in tb.cpp's table")
    cpp = float(line_clocks) / mode[1]
    if abs(cpp - cround(cpp)) < 0.01:
        cpp = cround(cpp)
    return cpp


def convert(old: Path, result: dict) -> HashFile:
    """The tb-v1 FNV file for the old frame_hashes.txt at `old`, given the project's result.json."""
    header, hash_text = _parse_old(old)
    timing = result["timing"]
    if header["hash_offset_basis"] != OFFSET_BASIS:
        raise ConvertError(f"{old}: hash_offset_basis {header['hash_offset_basis']}, expected {OFFSET_BASIS}")
    if header["id"] != result["id"]:
        raise ConvertError(f"{old}: id {header['id']!r}, result.json has {result['id']!r}")
    capture = _uint(old, header, "capture_after_clock")
    try:
        cpp = tb_cpp_clocks_per_pixel(timing["line_clocks"], header["mode"])
    except ConvertError as e:
        raise ConvertError(f"{old}: {e}") from None
    if round(cpp, 4) != timing["clocks_per_pixel"]:
        raise ConvertError(f"{old}: clocks_per_pixel {cpp!r} rounds to {round(cpp, 4)!r}, "
                           f"timing.clocks_per_pixel is {timing['clocks_per_pixel']!r}")
    hashes = hash_text.split("\n")
    if hashes[-1] != "":
        raise ConvertError(f"{old}: the last line has no newline")
    hashes = hashes[:-1]
    count = timing.get("frame_hashes_count")
    if len(hashes) != count:
        raise ConvertError(f"{old}: {len(hashes)} hash lines, timing.frame_hashes_count is {count!r}")
    if len(hashes) != _uint(old, header, "frames"):
        raise ConvertError(f"{old}: {len(hashes)} hash lines, its header says frames: {header['frames']}")
    hf = HashFile(METHOD, header["id"], timing["status"], SAMPLER, "ok", header["mode"],
                  _uint(old, header, "width"), _uint(old, header, "height"), _uint(old, header, "clock_hz"),
                  cpp, capture, [None if h == "-" else h for h in hashes])
    new_text = format_hash_file(hf)
    tail = f"\nframes: {len(hashes)}\n"
    if not new_text.endswith(tail + hash_text) or new_text.count(tail) != 1:
        raise ConvertError(f"{old}: the converted hash lines are not byte-identical to the old file's")
    return hf


def _dump(result: dict) -> str:
    return json.dumps(result, indent=2) + "\n"


def plan(results: Path) -> list[tuple[Path, HashFile, dict, str]]:
    """(old path, new HashFile, new result.json dict, new result.json text) for every project, all checked."""
    out, errors = [], []
    for old in sorted(results.glob(f"*/*/{OLD_NAME}")):
        rpath = old.parent / "result.json"
        try:
            text = rpath.read_text()
            res = json.loads(text)
            if _dump(res) != text:
                raise ConvertError(f"{rpath}: rewriting it would change more than the two keys")
            hf = convert(old, res)
            if "tb_v1" in res:
                raise ConvertError(f"{rpath}: already has tb_v1")
            if (old.parent / NEW_REL).exists():
                raise ConvertError(f"{old.parent / NEW_REL}: already exists")
            del res["timing"]["frame_hashes_count"]
            res["tb_v1"] = dict(TB_V1_STALE)
            out.append((old, hf, res, _dump(res)))
        except (ConvertError, OSError, KeyError, ValueError) as e:
            errors.append(f"{old}: {type(e).__name__}: {e}")
    for e in errors:
        log(f"FAILED {e}")
    if errors:
        raise SystemExit(f"convert_frame_hashes: {len(errors)} project(s) failed the checks; nothing was written")
    return out


def write(results: Path, todo: list) -> list[Path]:
    """Write the new files and result.json, remove the old files; returns the new files."""
    written = []
    for old, hf, _, rtext in todo:
        new = old.parent / NEW_REL
        new.parent.mkdir(parents=True, exist_ok=True)
        write_hash_file(new, hf)
        if read_hash_file(new) != hf:
            raise SystemExit(f"convert_frame_hashes: {new} does not read back as written")
        (old.parent / "result.json").write_text(rtext)
        old.unlink()
        written.append(new)
        log(f"converted {new.relative_to(results)} ({len(hf.hashes)} frames)")
    return written


def seed_commands(host: remote.Host, results: Path, files: list[Path]) -> list[list[str]]:
    """One rsync per converted file to the host's `~/ttvga/work/<s>/<m>/frames/tb-v1/`."""
    cmds = []
    for f in files:
        rel = f.parent.relative_to(results).as_posix()
        dest = f"{remote.REMOTE_ROOT}/work/{rel}/"
        cmds.append(["rsync", "-a", "--checksum", "--mkpath", "--chmod=D755,F644",
                     "-e", " ".join(shlex.quote(c) for c in host.ssh_cmd()), str(f), f"{host.ssh}:{dest}"])
    return cmds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", type=Path, default=RESULTS_DIR, help="the results tree (default data/results)")
    ap.add_argument("--seed-host", metavar="HOST", help="also rsync each converted file to HOST's work/ (as its ttvga user)")
    ap.add_argument("--dry-run", action="store_true",
                    help="convert a copy under tmp/, and print the --seed-host rsync commands without running them")
    args = ap.parse_args(argv)
    host = remote.resolve_host(args.seed_host) if args.seed_host else None

    results = args.results.resolve()
    if args.dry_run:
        scratch = ROOT / "tmp" / "t17-dry-run" / time.strftime("%Y-%m-%dT%H%M%S")
        shutil.copytree(results, scratch / "results")
        log(f"dry run: copied {results} to {scratch / 'results'}")
        results = scratch / "results"

    todo = plan(results)
    files = write(results, todo)
    log(f"converted {len(files)}")

    if host is not None:
        cmds = seed_commands(host, results, files)
        for cmd in cmds:
            line = shlex.join(cmd)
            if args.dry_run:
                log(f"would run: {line}")
                continue
            log(f"$ {line}")
            subprocess.run(cmd, check=True)
        log(f"{'would seed' if args.dry_run else 'seeded'} {len(cmds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
