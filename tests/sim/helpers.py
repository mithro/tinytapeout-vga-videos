# SPDX-License-Identifier: Apache-2.0
"""Helpers for running a tb.cpp model in the simulation tests."""

from __future__ import annotations

import json
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

HARNESS = "test-harness-2026-11-26"


def meta_args(design: str) -> list[str]:
    return ["--meta", f"project=test/{design}", "--meta", "override=none",
            "--meta", "simulator=verilator", "--meta", f"harness={HARNESS}"]


def base_args(dev, out: Path) -> list[str]:
    return ["--seconds", "0.2", "--calib-seconds", "0.1", "--no-audio", "--quiet",
            "--ffmpeg", str(dev.ffmpeg_sink), "--out", str(out)]


def run(model: Path, dev, out: Path, *extra: str, trace: bool = True, design: str = "bars640",
        env: dict | None = None) -> subprocess.CompletedProcess:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(model)] + base_args(dev, out)
    if trace:
        cmd += ["--trace", str(out / "trace.vgch.zst")] + meta_args(design)
    cmd += list(extra)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)


def timing(out: Path) -> dict:
    return json.loads((out / "timing.json").read_text())


def tracetool(dev, *args, check=True) -> subprocess.CompletedProcess:
    dev.require("tracetool")
    p = subprocess.run([str(dev.tracetool), *map(str, args)], capture_output=True, text=True, timeout=600)
    if check:
        assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    return p


def kv(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        k, v = line.split(": ", 1)
        assert k not in out, f"duplicate key {k}"
        out[k] = v
    return out


def info(dev, path) -> dict[str, str]:
    return kv(tracetool(dev, "info", path).stdout)


# A model killed mid-run, shared by every test (in any module) that needs a truncated trace.
_killed: dict[str, Path] = {}


def killed_trace(models, dev, tmp_path_factory) -> Path:
    if "path" in _killed:
        return _killed["path"]
    out = tmp_path_factory.mktemp("killed")
    out.mkdir(exist_ok=True)
    trace = out / "trace.vgch.zst"
    log = (out / "poll.log").open("w")
    cmd = [str(models("noisy"))] + base_args(dev, out) + ["--trace", str(trace)] + meta_args("noisy")
    cmd += ["--seconds", "30"]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    start = time.monotonic()
    try:
        while True:
            time.sleep(1)
            assert p.poll() is None, "the model exited before it was killed"
            elapsed = time.monotonic() - start
            if elapsed > 120:
                pytest.fail("the trace has fewer than 2 blocks after 120 s")
            copy = out / "copy.vgch.zst"
            if not trace.exists():
                print(f"{elapsed:5.1f}s: no trace file yet", file=log, flush=True)
                continue
            shutil.copyfile(trace, copy)
            q = tracetool(dev, "info", copy, check=False)
            blocks = kv(q.stdout).get("blocks", "?") if q.returncode == 0 else f"info exit {q.returncode}: {q.stderr.strip()}"
            print(f"{elapsed:5.1f}s: copy {copy.stat().st_size} bytes, blocks {blocks}", file=log, flush=True)
            if q.returncode == 0 and int(blocks) >= 2:
                break
    finally:
        p.send_signal(signal.SIGKILL)
        p.wait()
        log.close()
    _killed["path"] = trace
    return trace
