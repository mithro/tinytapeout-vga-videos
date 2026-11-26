# SPDX-License-Identifier: Apache-2.0
"""Helpers for running a tb.cpp model in the simulation tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
