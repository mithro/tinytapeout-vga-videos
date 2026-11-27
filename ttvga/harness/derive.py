# SPDX-License-Identifier: Apache-2.0
"""The derive step: a tb.cpp trace to frames, hashes, PNGs and pages, in a scratch directory.

Standard library only. It runs vgacap's `vgacap-sample` once over the trace (centre-v1
always, tb-v1 on request; Ruling W), turns the records of its `--png-fd` pipe into PNGs as
they arrive, writes each sampler's page, hashes `uo_out` with `tracetool uohash`, and with
tb-v1 compares tb-v1's FNV hashes with tb.cpp's own `tb_frame_hashes.txt`.

vgacap-sample is used only through its command line and its documented outputs (the files
of `docs/frames-format.md` and the `--png-fd` records), so moving the vgacap pin does not
change this module. frames.txt is read with vgacap's own `framesfile`: the caller puts the
pinned vgacap Python on sys.path first (`vgacap_path.add` or `add_src`).

The trace's SHA-256 is returned for result.json and written only to the uncommitted sidecar
`tb-v1/TRACE_SHA256` (C4); it is in no frames.txt or hash file. Nothing is ever deleted
here: a re-run without tb-v1 leaves any tb-v1 files where they are (Ruling Z), and a
directory this run would write must not exist yet.

    derive(trace, out, stem, tb_v1=..., centre_window=..., store_level=..., tools=..., log=...,
           tb_hashes=...) -> DeriveResult
"""

from __future__ import annotations

import hashlib
import os
import resource
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import xxhash

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pages  # noqa: E402
import pngio  # noqa: E402

CENTRE = "centre-v1"
TB_V1 = "tb-v1"
FNV = "frame_hashes.fnv1a64-tb2026-rgb888.txt"
TRACE_SHA_FILE = "TRACE_SHA256"
_READ = 1 << 20
_HEADER_MAX = 256
# The largest frame side frames-format.md allows (16 to 4096 pixels or lines).
MAX_SIDE = 4096


class DeriveError(RuntimeError):
    """The derive step could not run (a slice, an unreadable trace, a broken PNG pipe)."""


@dataclass(frozen=True)
class Tools:
    vgacap_sample: Path
    tracetool: Path


@dataclass(frozen=True)
class DeriveResult:
    samplers: dict[str, dict]
    trace_sha: str
    uo_out_xxh3_128: str
    uo_out_xxh3_128_clocks: tuple[int, int]
    tb_v1_check: str            # match | mismatch | not-run | off
    error: str | None
    cpu_seconds: float
    pngs_written: int
    pngs_linked: int
    info: dict[str, str]        # `tracetool info` of the trace (blocks, clocks, open.*, close.*)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_READ):
            h.update(chunk)
    return h.hexdigest()


def _kv(text: str, what: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition(": ")
        if not sep or k in out:
            raise DeriveError(f"{what}: unexpected output line {line!r}")
        out[k] = v
    return out


def _log_run(log, cmd: list[str], rc: int, stdout: str, stderr: str) -> None:
    log.write("$ " + " ".join(cmd) + f"\nexit {rc}\n")
    if stdout:
        log.write("--- stdout\n" + stdout + ("" if stdout.endswith("\n") else "\n"))
    if stderr:
        log.write("--- stderr\n" + stderr + ("" if stderr.endswith("\n") else "\n"))
    log.flush()


def _tracetool(tools: Tools, log, *args: str) -> dict[str, str]:
    cmd = [str(tools.tracetool), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    _log_run(log, cmd, p.returncode, p.stdout, p.stderr)
    if p.returncode != 0:
        last = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else f"exit {p.returncode}"
        raise DeriveError(f"tracetool {args[0]} failed (exit {p.returncode}): {last}")
    return _kv(p.stdout, f"tracetool {args[0]}")


class _PngSink:
    """Reads vgacap-sample's `--png-fd` records on a thread and writes `<out>/<sampler>/png/NNNNNN.png`.

    A record is `"<sampler> <distinct> <width> <height>\\n"` and width * height rgb6 bytes.
    A frame whose (width, height, XXH3-128) was already written is hard-linked to that PNG.
    Any malformed record stops the reader (closing the pipe, so vgacap-sample fails too).
    """

    def __init__(self, fd: int, out: Path, samplers: list[str]):
        self.file = os.fdopen(fd, "rb", buffering=_READ)
        self.out = out
        self.next = {s: 0 for s in samplers}
        self.seen: dict[tuple[int, int, bytes], Path] = {}
        self.sizes: dict[str, set[tuple[int, int]]] = {s: set() for s in samplers}
        self.written = 0
        self.linked = 0
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._loop, name="png-sink", daemon=True)
        self.thread.start()

    def _record(self, header: bytes) -> None:
        if not header.endswith(b"\n"):
            raise DeriveError(f"bad record header {header[:80]!r}")
        parts = header.decode("ascii").split(" ")
        if len(parts) != 4:
            raise DeriveError(f"bad record header {header!r}")
        sampler = parts[0]
        distinct, width, height = (int(x) for x in parts[1:])
        if sampler not in self.next:
            raise DeriveError(f"record for sampler {sampler!r}, which was not asked for")
        if distinct != self.next[sampler]:
            raise DeriveError(f"{sampler}: record for distinct frame {distinct}, expected {self.next[sampler]}")
        if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
            raise DeriveError(f"{sampler}: bad frame size {width}x{height}")
        rgb6 = self.file.read(width * height)
        if len(rgb6) != width * height:
            raise DeriveError(f"{sampler}: distinct frame {distinct} cut short "
                              f"({len(rgb6)} of {width * height} bytes)")
        self.next[sampler] += 1
        self.sizes[sampler].add((width, height))
        dest = self.out / sampler / "png" / f"{distinct:06d}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        key = (width, height, xxhash.xxh3_128_digest(rgb6))
        same = self.seen.get(key)
        if same is not None:
            os.link(same, dest)
            self.linked += 1
        else:
            pngio.write_rgb6(dest, width, height, rgb6)
            self.seen[key] = dest
            self.written += 1

    def _loop(self) -> None:
        try:
            while header := self.file.readline(_HEADER_MAX):
                self._record(header)
        except BaseException as e:   # reported by join(); the pipe is closed below
            self.error = e
        finally:
            self.file.close()

    def join(self, cause: str | None) -> None:
        """Wait for the reader; raise its error, with vgacap-sample's own `cause` when it failed too."""
        self.thread.join()
        if self.error is not None:
            why = f" (vgacap-sample: {cause})" if cause else ""
            raise DeriveError(f"PNG pipe from vgacap-sample: {self.error}{why}") from self.error


def _summary(ff) -> dict:
    return {"sampler_status": ff.sampler_status, "frames": len(ff.frames), "distinct_frames": len(ff.distinct),
            "mode": ff.mode, "width": ff.width, "height": ff.height, "clocks_per_pixel": ff.clocks_per_pixel}


def _compare_tb_v1(framesfile, tb_dir: Path, tb_hashes: Path) -> int | None:
    """The first frame where tb-v1's FNV hashes and tb.cpp's differ, or None when they agree."""
    ours = ["-" if h is None else h for h in framesfile.read_hash_file(tb_dir / FNV).hashes]
    theirs = tb_hashes.read_text().splitlines()
    for k, (a, b) in enumerate(zip(ours, theirs)):
        if a != b:
            return k
    return None if len(ours) == len(theirs) else min(len(ours), len(theirs))


def derive(trace: Path, out: Path, stem: str, *, tb_v1: bool, centre_window: tuple[int, int] | None,
           store_level: int | None, tools: Tools, log: Path, tb_hashes: Path | None) -> DeriveResult:
    """Sample `trace` into `out/<sampler>/` (see the module docstring).

    Raises DeriveError when the step cannot run: the trace is a slice, tracetool cannot
    read it, an output directory already exists, or the PNG pipe breaks. A sampler or
    tb-v1 failure is not raised: it is the result's `error`, and the files are left in `out`.
    """
    trace, out = Path(trace), Path(out)
    cpu0 = time.process_time()
    kids0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    samplers = [CENTRE] + ([TB_V1] if tb_v1 else [])
    with open(log, "a", encoding="utf-8") as lf:
        lf.write(f"derive {trace} -> {out} (stem {stem}, samplers {' '.join(samplers)})\n")
        info = _tracetool(tools, lf, "info", str(trace))
        if "open.slice_from_clock" in info:
            raise DeriveError(f"{trace} is a slice (clocks {info['open.slice_from_clock']} to "
                              f"{info.get('open.slice_to_clock', '?')}); only a whole trace is derived")
        for s in samplers:
            if (out / s).exists():
                raise DeriveError(f"{out / s} already exists; derive writes into a fresh directory")
        trace_sha = sha256_file(trace)
        from vgacap import framesfile

        cmd = [str(tools.vgacap_sample), str(trace), "--out", str(out), "--name", stem]
        for s in samplers:
            cmd += ["--sampler", s]
        if centre_window is not None:
            cmd += ["--centre-window", f"{centre_window[0]},{centre_window[1]}"]
        if store_level is not None:
            cmd += ["--store-level", str(store_level)]
        r, w = os.pipe()
        cmd += ["--png-fd", str(w)]
        sink = _PngSink(r, out, samplers)
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, pass_fds=(w,))
        except OSError as e:
            raise DeriveError(f"cannot run {tools.vgacap_sample}: {e}") from e
        finally:
            os.close(w)
        stdout, stderr = p.communicate()
        _log_run(lf, cmd, p.returncode, stdout, stderr)
        if p.returncode < 0:
            last = f"killed by signal {-p.returncode}"
        elif stderr.strip():
            last = stderr.strip().splitlines()[-1]
        else:
            last = f"vgacap-sample exit {p.returncode}"
        sink.join(last if p.returncode != 0 else None)

        errors: list[str] = []
        summaries: dict[str, dict] = {}
        read: dict[str, object] = {}
        if p.returncode in (0, 1):
            try:
                read = {s: framesfile.read_frames_txt(out / s / "frames.txt") for s in samplers}
            except (OSError, ValueError) as e:
                if p.returncode == 0:
                    raise DeriveError(f"vgacap-sample exited 0 but its frames.txt cannot be read: {e}") from e
                read = {}
        bad_window = CENTRE in read and read[CENTRE].sampler_status == "bad-window"
        if p.returncode == 0 and not bad_window:
            pass
        elif p.returncode == 1 and bad_window:
            dx, dy = centre_window or (0, 0)
            errors.append(f"centre_window {dx},{dy} does not fit: {last}")
        else:
            errors.append(last)
            read = {}

        for s, ff in read.items():
            if sink.next[s] != len(ff.distinct):
                raise DeriveError(f"{s}: vgacap-sample piped {sink.next[s]} distinct frames, "
                                  f"frames.txt has {len(ff.distinct)}")
            if sink.sizes[s] - {(ff.width, ff.height)}:
                got = ", ".join(f"{a}x{b}" for a, b in sorted(sink.sizes[s]))
                raise DeriveError(f"{s}: vgacap-sample piped frames of {got}, frames.txt has {ff.width}x{ff.height}")
            (out / s / "png").mkdir(parents=True, exist_ok=True)
            pages.write_sampler_page(out / s, ff, stem, s)
            summaries[s] = _summary(ff)

        uo = _tracetool(tools, lf, "uohash", str(trace))
        try:
            lo, hi = (int(x) for x in uo["uo_out_xxh3_128_clocks"].split())
            uo_digest = uo["uo_out_xxh3_128"]
        except (KeyError, ValueError) as e:
            raise DeriveError(f"tracetool uohash: unexpected output {uo}") from e

        if tb_v1 and tb_hashes is not None and not Path(tb_hashes).is_file():
            lf.write(f"tb-v1 check not run: tb.cpp's hashes {tb_hashes} do not exist\n")
        if not tb_v1:
            check = "off"
        elif TB_V1 not in read or tb_hashes is None or not Path(tb_hashes).is_file():
            check = "not-run"
        else:
            k = _compare_tb_v1(framesfile, out / TB_V1, Path(tb_hashes))
            check = "match" if k is None else "mismatch"
            if k is not None:
                errors.append(f"tb-v1 differs from tb.cpp at frame {k}")
        if TB_V1 in read:
            (out / TB_V1 / TRACE_SHA_FILE).write_text(trace_sha + "\n")

        kids1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (time.process_time() - cpu0 + kids1.ru_utime - kids0.ru_utime + kids1.ru_stime - kids0.ru_stime)
        error = "; ".join(errors) or None
        lf.write(f"derive done: error {error}, tb_v1_check {check}, pngs {sink.written} written, "
                 f"{sink.linked} linked, cpu {cpu:.2f} s\n")
    return DeriveResult(samplers=summaries, trace_sha=trace_sha, uo_out_xxh3_128=uo_digest,
                        uo_out_xxh3_128_clocks=(lo, hi), tb_v1_check=check, error=error, cpu_seconds=cpu,
                        pngs_written=sink.written, pngs_linked=sink.linked, info=info)
