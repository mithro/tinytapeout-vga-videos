#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one project through fetch, build, simulate, derive, encode and publish. Runs on the host.

Usage: job.py --targets targets.json --id <shuttle>/<macro> --root ~/ttvga [options]

Layout under --root:
    tools/oss-cad-suite/bin/verilator, tools/ffmpeg/bin/ffmpeg
    tools/vgacap-src, tools/vgacap-build (the pinned vgacap and tracetool, see vgacap_path.py)
    harness/tb.cpp (this directory), harness/HARNESS_VERSION
    host.toml (frames_root, staging_dir: see hostconf.py)
    overrides/<shuttle>/<macro>.json (+ .inputs/.gamepad/.diff), compiled by ttvga/overrides.py
    work/<shuttle>/<macro>/{repo/, build/, out/, scratch/, frames/, kept/,
                            build.log, sim.log, derive.log, publish.log, timing.json, result.json}
    ~/public_html/<shuttle>/<macro>/<shuttle>_<macro>_{60,30,10}s.{mp4,webm} + _poster/_contact/_preview
      (published at https://<host>/~<user>/, see docs/publishing.md)
    <frames_root>/<shuttle>/<macro>/: the trace and each sampler's frames (publish.py)

The model writes its trace into `scratch/`; derive samples it into
`scratch/<sampler>/`; publish copies scratch to staging and swaps it into the
frames subtree. Each job makes scratch fresh and removes it at the end on every
path (the `testpatterns` pseudo-shuttle, never published, moves it to `kept/`).
`frames/` holds what `collect` brings into git: each sampler's frames.txt and
the tb-v1 FNV file, never TRACE_SHA256 (C4). It changes only when a run publishes.

tb-v1, the legacy sampler, runs only with --tb-v1. Without it a published
`tb-v1/` is carried into the new copy unchanged: no run deletes tb-v1 files
except one with --drop-tb-v1 (Ruling Z). result.json's `tb_v1` says whether
they were made from this run's trace (`current`), from another (`stale`), or
do not exist (`none`).

A failed job (fetch, build, a simulation that left no trace, any derive
error, a publish refusal) publishes nothing: the published copy and `frames/`
stay as they were. A run with no picture, a model killed with a trace left,
and an encode failure still publish the trace and the frames.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import derive  # noqa: E402
import hostconf  # noqa: E402
import publish  # noqa: E402
import vgacap_path  # noqa: E402
from encode import published_files, render_previews, run, stem_for, transcode  # noqa: E402

DEFAULT_CLOCK_HZ = 25_175_000
STAGES = ("fetch", "build", "simulate", "derive", "encode", "publish")
# The calibration designs' pseudo-shuttle: derived, never encoded or published.
TESTPATTERNS = "testpatterns"
NO_PICTURE = ("no-sync", "bad-timing")
# What `collect` takes from each sampler (never tb-v1/TRACE_SHA256: C4).
WORK_FRAMES = {derive.CENTRE: ("frames.txt",), derive.TB_V1: ("frames.txt", derive.FNV)}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_override(path: Path) -> dict:
    """Read the compiled per-project override (`<macro>.json`, made by `ttvga/overrides.py`).

    Keys: clock_hz, seconds, calib_seconds, ui_in, uio_in, verilator_flags,
    sources, top_module, skip, and file names (next to the JSON) for inputs,
    gamepad and patch.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def override_meta(overrides: Path, shuttle: str, macro: str) -> str:
    """The trace's `override` META value: the compiled override and its hash, or `none`."""
    path = overrides / shuttle / f"{macro}.json"
    if not path.exists():
        return "none"
    return f"{shuttle}/{macro}.json sha256:{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}"


def fetch(target: dict, repo_dir: Path, log: Path, patch: Path | None = None) -> str | None:
    """Clone the project repo at its recorded commit and apply an optional patch."""
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    steps = [
        ["git", "init", "-q"],
        ["git", "remote", "add", "origin", target["repo"]],
        ["git", "fetch", "-q", "--depth", "1", "origin", target["commit"]],
        ["git", "checkout", "-q", "FETCH_HEAD"],
    ]
    for cmd in steps:
        if run(cmd, log, cwd=repo_dir, timeout=600, env=env) != 0:
            return f"{cmd[1]} failed"
    # Submodules are rare but do occur (shared libraries of Verilog modules).
    # Their URLs are usually SSH, which hangs without a key, and an `insteadOf`
    # rewrite is not enough, so edit .gitmodules itself before fetching.
    if (repo_dir / ".gitmodules").exists():
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
        listing = subprocess.run(["git", "config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.url"],
                                 cwd=repo_dir, capture_output=True, text=True, env=env)
        for line in listing.stdout.splitlines():
            key, _, url = line.partition(" ")
            https = re.sub(r"^(git@github\.com:|ssh://git@github\.com/)", "https://github.com/", url.strip())
            if https != url.strip():
                run(["git", "config", "-f", ".gitmodules", key, https], log, cwd=repo_dir, env=env)
        run(["git", "submodule", "sync", "-q", "--recursive"], log, cwd=repo_dir, timeout=120, env=env)
        run(["git", "submodule", "update", "-q", "--init", "--depth", "1", "--recursive"], log, cwd=repo_dir,
            timeout=300, env=env)
    if patch is not None:
        if run(["git", "apply", "--whitespace=nowarn", str(patch)], log, cwd=repo_dir, timeout=60, env=env) != 0:
            return "patch did not apply"
    return None


CELLS = Path(__file__).resolve().parent / "cells"
TB_CPP = Path(__file__).resolve().parent / "tb.cpp"


def verilator_base(verilator: str, top: str, build_dir: Path, src: Path) -> list[str]:
    """The Verilator command `build` runs, before the project's own flags, tb.cpp and the sources."""
    return [
        verilator, "--cc", "--exe", "--build", "-j", "1",
        "--prefix", "Vtop", "--top-module", top, "-Mdir", str(build_dir),
        "-O3", "--x-assign", "fast", "--x-initial", "fast",
        "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-MULTIDRIVEN", "-Wno-UNOPTFLAT",
        "-CFLAGS", "-std=c++17", "-MAKEFLAGS", "OPT_FAST=-O2",
        "-I" + str(src), "-y", str(src), "--relative-includes",
        # Behavioural models for PDK cells instantiated by name (latches, clock
        # gates, buffers). A `-v` library file only contributes modules that are
        # actually referenced.
        "-v", str(CELLS / "sky130_polyfill.v"),
    ]


def vgacap_link_flags(vgacap_src: Path, vgacap_build: Path) -> list[str]:
    """Verilator flags that compile tb.cpp against vgacap's trace writer and link it.

    Raises FileNotFoundError naming the first library that is missing.
    """
    libs = [
        vgacap_build / "libvgacap_trace.a",
        vgacap_build / "libvgacap_stream.a",
        vgacap_build / "third_party" / "libvgacap_zstd.a",
    ]
    for lib in libs:
        if not lib.is_file():
            raise FileNotFoundError(f"vgacap library missing: {lib}")
    return ["-CFLAGS", f"-I{vgacap_src / 'include'}",
            "-LDFLAGS", " ".join(str(lib) for lib in libs) + " -pthread"]


def src_dir(target: dict, repo_dir: Path) -> Path:
    """Where the project's sources are, and where its model runs ($readmem paths are relative to it)."""
    return repo_dir / target.get("src_dir", "src")


def build(target: dict, ov: dict, repo_dir: Path, build_dir: Path, log: Path, tools: dict,
          vgacap_src: Path, vgacap_build: Path, test_hooks: bool = False) -> str | None:
    """Verilate the sources with tb.cpp, linked with vgacap's trace writer. Returns an error string or None.

    `test_hooks` (job.py --test-hooks, for the tests only) compiles in tb.cpp's TTVGA_TEST_HOOKS code.
    """
    try:
        link = vgacap_link_flags(vgacap_src, vgacap_build)
    except FileNotFoundError as e:
        return str(e)
    if test_hooks:
        link += ["-CFLAGS", "-DTTVGA_TEST_HOOKS"]
    src = src_dir(target, repo_dir)
    sources = list(ov.get("sources") or target["source_files"])
    # IHP re-hardens of sky130 projects list a polyfill the project repo never
    # had (the shuttle added it); the same file also stands in for sky130
    # standard cells instantiated directly in RTL.
    for i, s in enumerate(sources):
        if Path(s).name == "sky130_polyfill.v" and not (src / s).exists():
            sources[i] = str(CELLS / "sky130_polyfill.v")
    missing = [s for s in sources if not (src / s).exists() and not Path(s).is_absolute()]
    if missing:
        return "missing sources: " + ", ".join(missing)
    top = ov.get("top_module") or target["top_module"]
    # Re-hardened projects are sometimes renamed on the shuttle (tt_um_x_tt08)
    # while the repo at the recorded commit still declares the original name.
    declared = set()
    for s in sources:
        p = Path(s) if Path(s).is_absolute() else src / s
        if p.suffix in (".v", ".sv") and p.exists():
            declared.update(re.findall(r"^\s*module\s+(tt_um_\w+)", p.read_text(errors="replace"), re.M))
    if top not in declared and len(declared) == 1:
        with log.open("a") as f:
            f.write(f"top module {top} not declared; using {next(iter(declared))}\n")
        top = next(iter(declared))
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    base = verilator_base(tools["verilator"], top, build_dir, src) + link
    flags = list(ov.get("verilator_flags") or [])
    files = [s if Path(s).is_absolute() else str(src / s) for s in sources if not s.endswith((".vh", ".svh", ".h"))]
    tb = str(TB_CPP)
    rc = run(base + flags + [tb] + files, log, cwd=src, timeout=1800)
    text = log.read_text()
    if rc != 0 and "--timing" not in flags and ("NEEDTIMINGOPT" in text or "--timing" in text):
        flags.append("--timing")
        shutil.rmtree(build_dir)
        build_dir.mkdir()
        rc = run(base + flags + [tb] + files, log, cwd=src, timeout=1800)
    if rc == 124:
        return "verilator timed out"
    if rc != 0 or not (build_dir / "Vtop").exists():
        return "verilator failed"
    return None


# How a project names the pins of the QSPI Pmod, in the order they are tried.
# The first pattern that matches a pin claims it.
QSPI_NAMES = [
    ("sck", r"\b(sck|sclk|spi[_ ]?clk|qspi[_ ]?sck|psram[_ ]?sck|flash[_ ]?clk|clk)\b"),
    ("sd0", r"\b(sd0|io0|dq0|d0|si|mosi|sio0)\b"),
    ("sd1", r"\b(sd1|io1|dq1|d1|so|miso|sio1)\b"),
    ("sd2", r"\b(sd2|io2|dq2|d2|wp|sio2)\b"),
    ("sd3", r"\b(sd3|io3|dq3|d3|hold|sio3)\b"),
    ("cs0", r"\b(cs|cs0|csb|cs_n|csn|ncs|flash[_ ]?cs|spi[_ ]?cs)\b"),
    ("cs1", r"\b(cs1|ram[_ ]?a|psram[_ ]?cs|ram[_ ]?cs1?)\b"),
    ("cs2", r"\b(cs2|ram[_ ]?b|psram[_ ]?b|ram[_ ]?cs2)\b"),
]


def detect_qspi(pinout: dict) -> str | None:
    """Return a `--qspi` pin map when the bidirectional pins look like the QSPI Pmod."""
    found: dict[str, int] = {}
    for pin, raw in sorted(pinout.items()):
        m = re.fullmatch(r"uio\[(\d)\]", pin)
        if not m or not raw:
            continue
        bit = int(m.group(1))
        # "SD0 / SCK" means the project can be wired either way: take the first.
        # Underscores are separators here, not part of a word: QSPI_SD0 is SD0.
        name = re.sub(r"[^a-z0-9]+", " ", raw.split("/")[0].strip().lower())
        for role, pattern in QSPI_NAMES:
            if role in found:
                continue
            if re.search(pattern, name):
                found[role] = bit
                break
    if not {"sck", "sd0", "sd1"} <= set(found) or not ({"cs0", "cs1", "cs2"} & set(found)):
        return None
    return ",".join(f"{k}={v}" for k, v in sorted(found.items()))


def timing_status(out: Path) -> str | None:
    try:
        return json.loads((out / "timing.json").read_text()).get("status")
    except (OSError, json.JSONDecodeError):
        return None


def model_cmd(target: dict, ov: dict, build_dir: Path, out: Path, tools: dict, args: argparse.Namespace,
              seconds: float, ui_in: int | None = None, trace: Path | None = None) -> list[str]:
    """The model's command line. With `trace`, the model records it there, with `args.trace_meta`."""
    clock_hz = int(ov.get("clock_hz") or target.get("clock_hz") or 0) or DEFAULT_CLOCK_HZ
    cmd = [str(build_dir / "Vtop"), "--clock-hz", str(clock_hz), "--seconds", str(seconds),
           "--calib-seconds", str(ov.get("calib_seconds") or args.calib_seconds),
           "--out", str(out), "--ffmpeg", tools["ffmpeg"]]
    if ui_in is None:
        ui_in = ov.get("ui_in")
    if ui_in is not None:
        cmd += ["--ui-in", str(ui_in)]
    if ov.get("uio_in") is not None:
        cmd += ["--uio-in", str(ov["uio_in"])]
    for key in ("inputs", "gamepad"):
        if ov.get(key):
            cmd += [f"--{key}", str((args.overrides / target["shuttle"] / ov[key]).resolve())]
    qspi = ov.get("qspi")
    if qspi is None and not args.no_qspi:
        qspi = detect_qspi(target["pinout"])
    if qspi and qspi != "off":
        cmd += ["--qspi", qspi]
        if ov.get("flash"):
            cmd += ["--flash", str((args.overrides / target["shuttle"] / ov["flash"]).resolve())]
    if trace is not None:
        cmd += ["--trace", str(trace)]
        for kv in args.trace_meta:
            cmd += ["--meta", kv]
    return cmd


def _sim_problem(out: Path, rc: int, trace: Path, after: str = "") -> str | None:
    """What is wrong with a finished model run: no timing.json, or no trace. None when nothing is."""
    timing = out / "timing.json"
    if not timing.exists():
        state = "without"
    else:
        try:
            json.loads(timing.read_text())
            state = None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # Empty (killed while capturing) or cut short (killed mid-write): no timing either way.
            state = "with an empty" if timing.stat().st_size == 0 else "with a truncated"
    if state is not None:
        # Killed outright at the wall-clock limit (SIGTERM ignored, then SIGKILL after
        # the grace): timing.json is still empty, or missing if it died calibrating.
        if rc == 124:
            return "wall-clock limit"
        return f"model exited {rc} {state} timing.json{after}"
    if not trace.is_file():
        return f"model exited {rc} without a trace{after}"
    return None


def simulate(target: dict, ov: dict, repo_dir: Path, build_dir: Path, work: Path, log: Path, tools: dict,
             args: argparse.Namespace, result: dict, *, trace: Path) -> str | None:
    """Run the Verilated model. Writes `trace`, timing.json and capture.avi. Returns an error string or None.

    The caller still derives and publishes a `trace` an erring model left behind.
    """
    seconds = float(ov.get("seconds") or args.seconds)
    out = work / "out"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    # $readmem paths in Tiny Tapeout projects are usually relative to src/.
    cwd = src_dir(target, repo_dir)
    rc = run(model_cmd(target, ov, build_dir, out, tools, args, seconds, trace=trace), log, cwd=cwd,
             timeout=args.timeout, grace=args.grace)
    if (problem := _sim_problem(out, rc, trace)):
        return problem

    # No raster with the default inputs and nothing specified by hand: many
    # designs want a mode-select or start bit. Probe each single input bit
    # with a calibration-only run, which records no trace, and keep the first
    # one that syncs.
    if (timing_status(out) in NO_PICTURE and not args.no_probe
            and not any(ov.get(k) is not None for k in ("ui_in", "inputs", "gamepad"))):
        probe = work / "probe"
        found = None
        for ui_in in [1 << i for i in range(8)] + [0xff]:
            if probe.exists():
                shutil.rmtree(probe)
            probe.mkdir()
            run(model_cmd(target, ov, build_dir, probe, tools, args, 0.05, ui_in) + ["--quiet"], log, cwd=cwd,
                timeout=300, grace=10)
            status = timing_status(probe)
            with log.open("a") as f:
                f.write(f"probe ui_in=0x{ui_in:02x}: {status}\n")
            if status not in (*NO_PICTURE, None):
                found = ui_in
                break
        shutil.rmtree(probe, ignore_errors=True)
        if found is not None:
            result["auto_ui_in"] = found
            # Only the re-run's trace is kept: the first run's has the input that did not sync.
            trace.unlink()
            shutil.rmtree(out)
            out.mkdir()
            rc = run(model_cmd(target, ov, build_dir, out, tools, args, seconds, found, trace=trace), log, cwd=cwd,
                     timeout=args.timeout, grace=args.grace)
            return _sim_problem(out, rc, trace, " (after probe)")
    return None


def _derive_child(w: int, call) -> None:
    """In the forked child: run `call`, write its result (or error) to `w` as JSON, and exit."""
    try:
        os.setpgid(0, 0)
        # The parent's SIGTERM handler is not ours: the parent kills this group itself.
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            payload = {"result": dataclasses.asdict(call())}
        except derive.DeriveError as e:
            payload = {"error": str(e)}
        except BaseException:   # anything else is a bug: report it whole
            payload = {"error": "derive crashed: " + traceback.format_exc()}
        view = memoryview(json.dumps(payload).encode())
        while view:
            view = view[os.write(w, view):]
    finally:
        os._exit(0)


def run_derive(trace: Path, scratch: Path, stem: str, *, tb_v1: bool, tb_hashes: Path | None, tools: dict,
               log: Path, timeout: float) -> tuple[derive.DeriveResult | None, str | None]:
    """derive.derive() in a forked child, in its own process group, killed after `timeout` seconds.

    derive has no timeouts of its own (vgacap-sample, tracetool), so this is
    where the job's wall-clock limit covers it. Returns (the result or None, the error or None).
    """
    dtools = derive.Tools(vgacap_sample=Path(tools["vgacap_sample"]), tracetool=Path(tools["tracetool"]))

    def call() -> derive.DeriveResult:
        return derive.derive(trace, scratch, stem, tb_v1=tb_v1, centre_window=None, store_level=None,
                             tools=dtools, log=log, tb_hashes=tb_hashes)

    sys.stdout.flush()
    sys.stderr.flush()
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        _derive_child(w, call)
    os.close(w)
    try:
        os.setpgid(pid, pid)   # the child does it too: whichever runs first
    except OSError:
        pass
    chunks: list[bytes] = []
    deadline, timed_out = time.monotonic() + timeout, False
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True
                break
            if select.select([r], [], [], left)[0]:
                chunk = os.read(r, 1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
    finally:
        os.close(r)
        # Always: whatever the child left in its group (a vgacap-sample or tracetool
        # still running after a timeout, an exception or SIGTERM here) goes with it.
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _, status = os.waitpid(pid, 0)
    if timed_out:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"derive: wall-clock limit ({timeout:g} s): killed\n")
        return None, "derive wall-clock limit"
    try:
        payload = json.loads(b"".join(chunks))
    except json.JSONDecodeError:
        how = f"signal {os.WTERMSIG(status)}" if os.WIFSIGNALED(status) else f"exit {os.waitstatus_to_exitcode(status)}"
        return None, f"derive died ({how}) without a result"
    if "error" in payload:
        return None, payload["error"]
    fields = payload["result"]
    fields["uo_out_sha256_clocks"] = tuple(fields["uo_out_sha256_clocks"])
    res = derive.DeriveResult(**fields)
    return res, res.error


def tb_v1_rule(*, tb_v1: bool, drop: bool, published: Path | None, work_frames: Path,
               trace_sha: str | None) -> tuple[list[str], dict]:
    """What to carry over from the published copy, and result.json's `tb_v1` (Global Constraints, Ruling Z).

    `published` is the project's published directory (None when there is none to
    look at), `work_frames` its `work/.../frames/`.
    """
    if drop:
        return [], {"state": "none", "trace_sha": None, "dropped": True}
    if tb_v1:
        return [], {"state": "current", "trace_sha": trace_sha, "dropped": False}
    if published is not None and (published / derive.TB_V1).is_dir():
        sha_file = published / derive.TB_V1 / derive.TRACE_SHA_FILE
        recorded = (sha_file.read_text().strip() if sha_file.is_file() else "") or None
        state = "current" if recorded is not None and recorded == trace_sha else "stale"
        return [derive.TB_V1], {"state": state, "trace_sha": recorded, "dropped": False}
    if (work_frames / derive.TB_V1).exists():
        # The converted files (Task 17), made before traces existed.
        return [], {"state": "stale", "trace_sha": None, "dropped": False}
    return [], {"state": "none", "trace_sha": None, "dropped": False}


def _replace_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)


def update_work_frames(scratch: Path, frames: Path, *, tb_v1: bool, drop: bool) -> None:
    """Bring this run's frames.txt, and with tb-v1 its FNV file, into `frames/` for collect.

    Only the WORK_FRAMES files are replaced. Anything else under `frames/tb-v1/`
    stays, unless `drop` removes the directory.
    """
    for sampler, names in WORK_FRAMES.items():
        if sampler == derive.TB_V1 and not tb_v1:
            continue
        for name in names:
            _replace_file(scratch / sampler / name, frames / sampler / name)
    if drop and (frames / derive.TB_V1).exists():
        shutil.rmtree(frames / derive.TB_V1)


def encode(work: Path, videos: Path, log: Path, tools: dict, stem: str) -> str | None:
    """Publish the capture as browser-playable clips, then render the previews."""
    src = work / "out" / "capture.avi"
    try:
        timing = json.loads((work / "out" / "timing.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return f"timing.json cannot be read: {e}"
    # When its ffmpeg fails, tb.cpp goes on without video and still exits 0.
    if timing.get("ffmpeg_status"):
        return f"the capture's ffmpeg failed (ffmpeg_status {timing['ffmpeg_status']})"
    if not src.exists() or src.stat().st_size == 0:
        return "no capture.avi"
    frames, fps = timing.get("frames", 0), timing.get("fps", 60.0)
    if videos.exists():
        shutil.rmtree(videos)
    videos.mkdir(parents=True)
    error = transcode(src, videos, stem, log, tools["ffmpeg"])
    if error:
        return error
    return render_previews(videos, stem, log, tools["ffmpeg"], frames, fps)


def tool_versions(tools: dict) -> dict:
    out = {}
    for name in ("verilator", "ffmpeg"):
        try:
            p = subprocess.run([tools[name], "--version" if name == "verilator" else "-version"],
                               capture_output=True, text=True, timeout=30)
            out[name] = (p.stdout or p.stderr).splitlines()[0].strip()
        except (OSError, subprocess.TimeoutExpired, IndexError):
            out[name] = "unknown"
    return out


# tb.cpp's one start-up stderr line when the model's ports are not contiguous and
# it records by the slow path (Task 3a). The coordinator names "tb: trace fallback";
# t03a-trace-speed at 3cf378c prints the second. Keep only the one that lands.
TRACE_FALLBACK = ("tb: trace fallback", "tb: the model's 8 port bytes are not contiguous")


def trace_fast_path(sim_log: Path) -> bool:
    """False when tb.cpp said, anywhere in `sim_log`, that it fell back to the slow trace path."""
    with open(sim_log, encoding="utf-8", errors="replace") as f:
        return not any(line.startswith(TRACE_FALLBACK) for line in f)


def _tail(path: Path) -> str | None:
    return path.read_text(errors="replace")[-4000:] if path.exists() else None


def _job() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--id", required=True, help="<shuttle>/<macro>")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--videos", type=Path, default=Path.home() / "public_html",
                    help="where the clips are published (default ~/public_html)")
    ap.add_argument("--overrides", type=Path, default=None, help="default <root>/overrides")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--calib-seconds", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=1800.0,
                    help="wall-clock limit for the simulation, and the same again for derive")
    ap.add_argument("--grace", type=float, default=120.0,
                    help="seconds from SIGTERM to SIGKILL when the simulation reaches its limit (default 120)")
    ap.add_argument("--keep-build", action="store_true")
    ap.add_argument("--no-probe", action="store_true", help="do not try single input bits when there is no sync")
    ap.add_argument("--no-qspi", action="store_true", help="do not model a QSPI flash/PSRAM on the bidir pins")
    tb = ap.add_mutually_exclusive_group()
    tb.add_argument("--tb-v1", action="store_true", help="also run the legacy tb-v1 sampler and check it against tb.cpp")
    tb.add_argument("--drop-tb-v1", action="store_true",
                    help="retire tb-v1: publish without it and remove work/.../frames/tb-v1/")
    ap.add_argument("--test-hooks", action="store_true",
                    help="tests only: compile in tb.cpp's TTVGA_TEST_HOOKS; result.json records it")
    args = ap.parse_args()
    args.overrides = args.overrides or args.root / "overrides"
    # Everything the published tree gets is 0644/0755, whatever the caller's umask.
    os.umask(0o022)
    vgacap_path.add(args.root)

    targets = json.loads(args.targets.read_text())["targets"]
    target = next((t for t in targets if t["id"] == args.id), None)
    if target is None:
        print(f"job: no target {args.id}", file=sys.stderr)
        return 2
    version_file = args.root / "harness" / "HARNESS_VERSION"
    if not version_file.is_file():
        print(f"job: {version_file} is missing (written by tt-vga's push_harness)", file=sys.stderr)
        return 2
    harness = version_file.read_text().strip()
    shuttle, macro = target["shuttle"], target["macro"]
    stem = stem_for(shuttle, macro)
    testpatterns = shuttle == TESTPATTERNS
    work = args.root / "work" / shuttle / macro
    videos = args.videos / shuttle / macro
    tools = {
        "verilator": str(args.root / "tools" / "oss-cad-suite" / "bin" / "verilator"),
        "ffmpeg": str(args.root / "tools" / "ffmpeg" / "bin" / "ffmpeg"),
        **{name: str(path) for name, path in vgacap_path.tools(args.root).items()},
        # The pinned vgacap clone and build (`tt-vga bootstrap`, see vgacap_path.py).
        "vgacap_src": str(args.root / "tools" / "vgacap-src"),
        "vgacap_build": str(args.root / "tools" / "vgacap-build"),
    }
    ov = read_override(args.overrides / shuttle / f"{macro}.json")
    patch = (args.overrides / shuttle / ov["patch"]) if ov.get("patch") else None

    work.mkdir(parents=True, exist_ok=True)
    # One job per project at a time: two runs sharing a work directory delete
    # each other's output and both end up with nothing.
    lock = (work / ".lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"job: {target['id']}: already running elsewhere, skipped", file=sys.stderr)
        return 0
    for old in ("build.log", "sim.log", "derive.log", "publish.log", "result.json"):
        (work / old).unlink(missing_ok=True)
    result = {
        "id": target["id"], "shuttle": shuttle, "macro": macro, "started": now(),
        "host": os.uname().nodename, "harness": harness, "test_hooks": args.test_hooks,
        "override": ov or None, "stage": None, "error": None,
        "timings": {}, "tools": tool_versions(tools), "auto_ui_in": None,
        "qspi": ov.get("qspi") if ov.get("qspi") is not None else detect_qspi(target["pinout"]),
        "trace": None, "samplers": None, "tb_v1": None, "tb_v1_check": None, "derive_cpu_seconds": None,
        "published": False,
    }
    args.trace_meta = [f"project={target['id']}", f"override={override_meta(args.overrides, shuttle, macro)}",
                       f"simulator={result['tools']['verilator']}", f"harness={harness}"]

    errors: list[str] = []   # in order: the first is what went wrong first
    conf = None
    if ov.get("skip") or target.get("skip"):
        errors.append(ov.get("skip") or target.get("skip"))
        result["stage"] = "skipped"
    elif not testpatterns:
        # Checked before hours of simulation, and again by publish.install.
        try:
            conf = hostconf.load(args.root)
        except (hostconf.ConfigError, OSError) as e:
            # hostconf wraps a missing or malformed file; any other OSError (permissions, os.stat) lands here too.
            errors.append(f"host.toml: {e}" if isinstance(e, OSError) else str(e))
            result["stage"] = "setup"
    published_dir = conf.frames_root / shuttle / macro if conf else None

    repo_dir, build_dir, out = work / "repo", work / "build", work / "out"
    scratch = work / "scratch"
    trace = scratch / f"{stem}_trace.vgch.zst"
    dres: derive.DeriveResult | None = None
    terminated = False
    try:
        if scratch.exists():
            shutil.rmtree(scratch)
        scratch.mkdir()
        sim_error = None
        for stage in STAGES if not errors else ():
            if stage == "encode" and (testpatterns or sim_error or timing_status(out) in NO_PICTURE):
                # No raster, or a killed model: nothing to encode. Partial or unstable
                # rasters are still encoded because the clip helps diagnosis.
                continue
            if stage == "publish" and testpatterns:
                continue
            t0 = time.monotonic()
            result["stage"] = stage
            fatal = None
            try:
                if stage == "fetch":
                    fatal = fetch(target, repo_dir, work / "build.log", patch)
                elif stage == "build":
                    fatal = build(target, ov, repo_dir, build_dir, work / "build.log", tools,
                                  Path(tools["vgacap_src"]), Path(tools["vgacap_build"]), test_hooks=args.test_hooks)
                elif stage == "simulate":
                    sim_error = simulate(target, ov, repo_dir, build_dir, work, work / "sim.log", tools, args,
                                         result, trace=trace)
                    if sim_error and trace.is_file():
                        errors.append(sim_error)   # still derived and published, then reported
                    else:
                        fatal = sim_error
                elif stage == "derive":
                    # A killed model never wrote tb.cpp's own hash list, so there is nothing to check against.
                    hashes = out / "tb_frame_hashes.txt" if args.tb_v1 and not sim_error else None
                    dres, fatal = run_derive(trace, scratch, stem, tb_v1=args.tb_v1, tb_hashes=hashes, tools=tools,
                                             log=work / "derive.log", timeout=args.timeout)
                    if dres is not None:
                        result["derive_cpu_seconds"] = round(dres.cpu_seconds, 3)
                    if fatal is None and testpatterns:
                        _, result["tb_v1"] = tb_v1_rule(tb_v1=args.tb_v1, drop=args.drop_tb_v1, published=None,
                                                        work_frames=work / "frames", trace_sha=dres.trace_sha)
                        update_work_frames(scratch, work / "frames", tb_v1=args.tb_v1, drop=args.drop_tb_v1)
                elif stage == "encode":
                    if (err := encode(work, videos, work / "sim.log", tools, stem)):
                        errors.append(err)   # recorded; the trace and frames are still published
                elif stage == "publish":
                    carry, tb_state = tb_v1_rule(tb_v1=args.tb_v1, drop=args.drop_tb_v1, published=published_dir,
                                                 work_frames=work / "frames", trace_sha=dres.trace_sha)
                    try:
                        publish.install(scratch, conf, shuttle, macro, work / "publish.log", carry=carry)
                    except (publish.PublishError, OSError) as e:
                        fatal = f"publish: {e}"
                    else:
                        result["published"] = True
                        result["tb_v1"] = tb_state
                        try:
                            update_work_frames(scratch, work / "frames", tb_v1=args.tb_v1, drop=args.drop_tb_v1)
                        except OSError as e:
                            errors.append(f"published, but work/frames was not updated: {e}")
            except Exception as e:   # a bug or an unexpected failure: recorded, and nothing (more) published
                fatal = f"stage crashed: {stage}: {type(e).__name__}: {e}"
                result["traceback"] = traceback.format_exc()
            result["timings"][stage] = round(time.monotonic() - t0, 1)
            if fatal:
                errors.append(fatal)
                break

        try:
            if dres is not None:
                result["trace"] = {
                    "file": trace.name, "sha256": dres.trace_sha, "bytes": trace.stat().st_size,
                    "blocks": int(dres.info["blocks"]), "clocks": int(dres.info["clocks"]),
                    "uo_out_sha256": dres.uo_out_sha256, "uo_out_sha256_clocks": list(dres.uo_out_sha256_clocks),
                    "fast_path": trace_fast_path(work / "sim.log"),
                }
                result["samplers"] = dres.samplers
            result["tb_v1_check"] = dres.tb_v1_check if dres is not None else ("not-run" if args.tb_v1 else "off")
            if result["tb_v1"] is None:
                # Nothing was published: say what the files already there are.
                _, result["tb_v1"] = tb_v1_rule(tb_v1=False, drop=False, published=published_dir,
                                                work_frames=work / "frames",
                                                trace_sha=dres.trace_sha if dres is not None else None)
        except Exception as e:
            errors.append(f"stage crashed: result: {type(e).__name__}: {e}")
            result["traceback"] = traceback.format_exc()
    except Terminated:
        # SIGTERM (a queue stop, the scope): the finally below and run_derive's clean up; result.json says so.
        errors.append(f"terminated by SIGTERM during {result['stage']}")
        terminated = True
    finally:
        if testpatterns and trace.is_file():
            # Never published: the trace and frames stay in the work directory.
            if (work / "kept").exists():
                shutil.rmtree(work / "kept")
            scratch.rename(work / "kept")
        elif scratch.exists():
            shutil.rmtree(scratch)

    timing_path = out / "timing.json"
    if timing_path.exists():
        shutil.copy(timing_path, work / "timing.json")
        try:
            result["timing"] = json.loads(timing_path.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError):
            # The model was killed before writing it (wall-clock limit): keep what we know.
            result["timing"] = {"status": "sim-timeout", "partial": True}
    result["videos"] = published_files(videos)
    for name in ("build.log", "sim.log", "derive.log", "publish.log"):
        result[name.replace(".log", "_log_tail")] = _tail(work / name)
    error = "; ".join(errors) or None
    result["error"] = error
    result["finished"] = now()
    if not args.keep_build and build_dir.exists():
        shutil.rmtree(build_dir)
    if out.exists():
        shutil.rmtree(out)
    tmp = work / "result.json.tmp"
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    tmp.rename(work / "result.json")
    print(f"job: {target['id']}: stage={result['stage']} error={error!r} "
          f"status={result.get('timing', {}).get('status')} published={result['published']}")
    if terminated:
        return 128 + signal.SIGTERM
    return 0 if not error else 1


class Terminated(SystemExit):
    """Raised by the SIGTERM handler, so every `finally` runs (scratch, the derive child's group)."""


def _on_sigterm(signum, frame) -> None:
    raise Terminated(128 + signum)


def main() -> int:
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return _job()
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
