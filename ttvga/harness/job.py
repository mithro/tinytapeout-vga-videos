#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one project through fetch, build, simulate and encode. Runs on the host.

Usage: job.py --targets targets.json --id <shuttle>/<macro> --root ~/ttvga [options]

Layout under --root:
    tools/oss-cad-suite/bin/verilator, tools/ffmpeg/bin/ffmpeg
    harness/tb.cpp (this directory)
    overrides/<shuttle>/<macro>.json (+ .inputs/.gamepad/.diff), compiled by ttvga/overrides.py
    work/<shuttle>/<macro>/{repo/, build/, build.log, sim.log, timing.json, result.json}
    videos/<shuttle>/<macro>/{60s.avi, 30s.avi, 10s.avi, poster.png, contact.png}

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CLOCK_HZ = 25_175_000
STAGES = ("fetch", "build", "simulate", "encode")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], log: Path, cwd: Path | None = None, timeout: float | None = None,
        env: dict[str, str] | None = None) -> int:
    """Run a command, appending its output to `log`. Returns the exit code (124 on timeout)."""
    with log.open("a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n")
        f.flush()
        try:
            p = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            f.write(f"\n[timeout after {timeout}s]\n")
            return 124
        f.write(f"[exit {p.returncode}]\n")
        return p.returncode


def read_override(path: Path) -> dict:
    """Read the compiled per-project override (`<macro>.json`, made by `ttvga/overrides.py`).

    Keys: clock_hz, seconds, calib_seconds, ui_in, uio_in, verilator_flags,
    sources, top_module, skip, and file names (next to the JSON) for inputs,
    gamepad and patch.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text())


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
    if (repo_dir / ".gitmodules").exists():
        run(["git", "submodule", "update", "-q", "--init", "--depth", "1", "--recursive"], log, cwd=repo_dir,
            timeout=600, env=env)
    if patch is not None:
        if run(["git", "apply", "--whitespace=nowarn", str(patch)], log, cwd=repo_dir, timeout=60, env=env) != 0:
            return "patch did not apply"
    return None


def build(target: dict, ov: dict, repo_dir: Path, build_dir: Path, log: Path, tools: dict) -> str | None:
    """Verilate the sources with tb.cpp. Returns an error string or None."""
    src = repo_dir / "src"
    sources = ov.get("sources") or target["source_files"]
    missing = [s for s in sources if not (src / s).exists()]
    if missing:
        return "missing sources: " + ", ".join(missing)
    top = ov.get("top_module") or target["top_module"]
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    base = [
        tools["verilator"], "--cc", "--exe", "--build", "-j", "1",
        "--prefix", "Vtop", "--top-module", top, "-Mdir", str(build_dir),
        "-O3", "--x-assign", "fast", "--x-initial", "fast",
        "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-MULTIDRIVEN", "-Wno-UNOPTFLAT",
        "-CFLAGS", "-std=c++17", "-MAKEFLAGS", "OPT_FAST=-O2",
        "-I" + str(src), "-y", str(src), "--relative-includes",
    ]
    flags = list(ov.get("verilator_flags") or [])
    files = [str(src / s) for s in sources if not s.endswith((".vh", ".svh", ".h"))]
    tb = str(Path(__file__).resolve().parent / "tb.cpp")
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


def simulate(target: dict, ov: dict, repo_dir: Path, build_dir: Path, work: Path, log: Path, tools: dict,
             args: argparse.Namespace) -> str | None:
    """Run the Verilated model. Writes timing.json and 60s.avi. Returns an error string or None."""
    clock_hz = int(ov.get("clock_hz") or target.get("clock_hz") or 0) or DEFAULT_CLOCK_HZ
    seconds = float(ov.get("seconds") or args.seconds)
    out = work / "out"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    cmd = [str(build_dir / "Vtop"), "--clock-hz", str(clock_hz), "--seconds", str(seconds),
           "--calib-seconds", str(ov.get("calib_seconds") or args.calib_seconds),
           "--out", str(out), "--ffmpeg", tools["ffmpeg"]]
    if ov.get("ui_in") is not None:
        cmd += ["--ui-in", str(ov["ui_in"])]
    if ov.get("uio_in") is not None:
        cmd += ["--uio-in", str(ov["uio_in"])]
    for key in ("inputs", "gamepad"):
        if ov.get(key):
            cmd += [f"--{key}", str((args.overrides / target["shuttle"] / ov[key]).resolve())]
    # $readmem paths in Tiny Tapeout projects are usually relative to src/.
    rc = run(cmd, log, cwd=repo_dir / "src", timeout=args.timeout)
    if rc == 124:
        return "wall-clock limit"
    if not (out / "timing.json").exists():
        return f"model exited {rc} without timing.json"
    if (out / "timing.json").stat().st_size == 0:
        return f"model exited {rc} with an empty timing.json"
    return None


def encode(work: Path, videos: Path, log: Path, tools: dict) -> str | None:
    """Cut 30 s and 10 s clips, a poster and a contact sheet from 60s.avi."""
    src = work / "out" / "60s.avi"
    if not src.exists() or src.stat().st_size == 0:
        return "no 60s.avi"
    timing = json.loads((work / "out" / "timing.json").read_text())
    frames, fps = timing.get("frames", 0), timing.get("fps", 60.0)
    duration = frames / fps if fps else 0.0
    poster_at = min(5.0, duration / 2)                 # content has usually settled by 5 s
    step = max(1, frames // 16)                        # 16 frames spread over the clip
    if videos.exists():
        shutil.rmtree(videos)
    videos.mkdir(parents=True)
    shutil.move(str(src), videos / "60s.avi")
    ff = tools["ffmpeg"]
    for secs in (30, 10):
        if run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(videos / "60s.avi"), "-t", str(secs),
                "-c", "copy", str(videos / f"{secs}s.avi")], log, timeout=600) != 0:
            return f"ffmpeg cut {secs}s failed"
    run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{poster_at:.3f}", "-i", str(videos / "60s.avi"),
         "-frames:v", "1", str(videos / "poster.png")], log, timeout=600)
    run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(videos / "60s.avi"),
         "-vf", f"select='not(mod(n\\,{step}))',scale=iw/2:-1,tile=4x4", "-frames:v", "1",
         str(videos / "contact.png")], log, timeout=600)
    if not (videos / "poster.png").exists():
        return "poster failed"
    return None


def tool_versions(tools: dict) -> dict:
    out = {}
    for name, exe in tools.items():
        try:
            p = subprocess.run([exe, "--version" if name == "verilator" else "-version"], capture_output=True,
                               text=True, timeout=30)
            out[name] = (p.stdout or p.stderr).splitlines()[0].strip()
        except (OSError, subprocess.TimeoutExpired, IndexError):
            out[name] = "unknown"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--id", required=True, help="<shuttle>/<macro>")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--overrides", type=Path, default=None, help="default <root>/overrides")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--calib-seconds", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=1800.0, help="wall-clock limit for the simulation")
    ap.add_argument("--keep-build", action="store_true")
    args = ap.parse_args()
    args.overrides = args.overrides or args.root / "overrides"

    targets = json.loads(args.targets.read_text())["targets"]
    target = next((t for t in targets if t["id"] == args.id), None)
    if target is None:
        print(f"job: no target {args.id}", file=sys.stderr)
        return 2
    shuttle, macro = target["shuttle"], target["macro"]
    work = args.root / "work" / shuttle / macro
    videos = args.root / "videos" / shuttle / macro
    tools = {
        "verilator": str(args.root / "tools" / "oss-cad-suite" / "bin" / "verilator"),
        "ffmpeg": str(args.root / "tools" / "ffmpeg" / "bin" / "ffmpeg"),
    }
    ov = read_override(args.overrides / shuttle / f"{macro}.json")
    patch = (args.overrides / shuttle / ov["patch"]) if ov.get("patch") else None

    work.mkdir(parents=True, exist_ok=True)
    for old in ("build.log", "sim.log", "result.json"):
        (work / old).unlink(missing_ok=True)
    result = {
        "id": target["id"], "shuttle": shuttle, "macro": macro, "started": now(),
        "host": os.uname().nodename, "override": ov or None, "stage": None, "error": None,
        "timings": {}, "tools": tool_versions(tools),
    }
    error = ov.get("skip") or target.get("skip")
    if error:
        result["stage"] = "skipped"
    repo_dir, build_dir = work / "repo", work / "build"
    if not error:
        for stage in STAGES:
            t0 = time.monotonic()
            result["stage"] = stage
            if stage == "fetch":
                error = fetch(target, repo_dir, work / "build.log", patch)
            elif stage == "build":
                error = build(target, ov, repo_dir, build_dir, work / "build.log", tools)
            elif stage == "simulate":
                error = simulate(target, ov, repo_dir, build_dir, work, work / "sim.log", tools, args)
            elif stage == "encode":
                error = encode(work, videos, work / "sim.log", tools)
            result["timings"][stage] = round(time.monotonic() - t0, 1)
            if error:
                break
            if stage == "simulate":
                # No raster found: there is nothing to encode. Partial or unstable
                # rasters are still encoded because the clip helps diagnosis.
                try:
                    status = json.loads((work / "out" / "timing.json").read_text()).get("status")
                except (OSError, json.JSONDecodeError):
                    status = None
                if status in ("no-sync", "bad-timing"):
                    break
    timing_path = work / "out" / "timing.json"
    if timing_path.exists():
        shutil.copy(timing_path, work / "timing.json")
        try:
            result["timing"] = json.loads(timing_path.read_text())
        except json.JSONDecodeError:
            # The model was killed while writing (wall-clock limit): keep what we know.
            result["timing"] = {"status": "sim-timeout", "partial": True}
    if videos.exists():
        result["videos"] = {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
                            for p in sorted(videos.iterdir())}
    for name in ("build.log", "sim.log"):
        p = work / name
        if p.exists():
            result[name.replace(".log", "_log_tail")] = p.read_text()[-4000:]
    result["error"] = error
    result["finished"] = now()
    if not args.keep_build and build_dir.exists():
        shutil.rmtree(build_dir)
    if (work / "out").exists():
        shutil.rmtree(work / "out")
    tmp = work / "result.json.tmp"
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    tmp.rename(work / "result.json")
    print(f"job: {target['id']}: stage={result['stage']} error={error!r} "
          f"status={result.get('timing', {}).get('status')}")
    return 0 if not error else 1


if __name__ == "__main__":
    sys.exit(main())
