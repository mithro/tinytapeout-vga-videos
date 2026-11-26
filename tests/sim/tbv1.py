# SPDX-License-Identifier: Apache-2.0
"""Run a test design with a trace, sample the trace with vgacap's tb-v1, and
compare tb-v1's results with tb.cpp's own: the comparison test and
`scripts/export_tbv1_vectors.py` both use it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from ttvga.devtools import DevTools
from tests.sim.helpers import run

FNV = "frame_hashes.fnv1a64-tb2026-rgb888.txt"
REPO_ROOT = Path(__file__).resolve().parents[2]
MISMATCH_DIR = REPO_ROOT / "tmp" / "tbv1-mismatch"

# --clock-hz for the designs that are not run at tb.cpp's default 25,175,000 Hz.
CLOCK_HZ = {"bars_cpp2": "50350000", "frac": "48000000"}
# tb.cpp's exit code for each design's expected timing.json status.
EXIT = {"ok": 0, "no-sync": 3, "unstable-sync": 3}
# timing.json has clocks_per_pixel to 4 decimals (%.4f), so tb-v1's full value is
# at most half a unit of the 4th decimal away, inclusive: frac's 1.90625 is written
# 1.9062, 5e-5 off. The 1e-12 keeps that bound inclusive against the doubles' rounding.
CPP_TOLERANCE = 5e-5
CPP_ROUNDING = 1e-12
# Each design's expected timing.json status and fewest captured frames: a design
# that silently stops producing a picture must fail, not compare two empty lists.
EXPECT = {
    "bars640": ("ok", 2),
    "bars_cpp2": ("ok", 2),
    "frac": ("ok", 2),
    "glitch": ("unstable-sync", 2),
    "negedge": ("ok", 2),
    "noisy": ("ok", 2),
    "nosync": ("no-sync", 0),
    "playground": ("ok", 2),
    "uio_echo": ("no-sync", 0),
}


def vgacap_pin() -> str:
    """The vgacap commit `ttvga/tools.toml` pins."""
    return tomllib.loads((REPO_ROOT / "ttvga" / "tools.toml").read_text())["vgacap"]["commit"]


def check_pin(dev: DevTools) -> str:
    """Refuse dev-tools whose vgacap build is not the pinned commit; return the pin."""
    pin = vgacap_pin()
    built = (dev.vgacap_build / "PINNED").read_text().strip()
    if built != pin:
        raise RuntimeError(f"dev-tools vgacap is {built}, the pin is {pin}: run tt-vga dev-tools")
    return pin


def expectation_problems(design: str, tj: dict) -> list[str]:
    """How timing.json misses the design's expected status and frame count (EXPECT)."""
    status, min_frames = EXPECT[design]
    frames = tj.get("frames", 0)
    problems = []
    if tj["status"] != status:
        problems.append(f"{design}: status {tj['status']}, expected {status}")
    if min_frames == 0 and frames != 0:
        problems.append(f"{design}: {frames} frames, expected 0")
    elif frames < min_frames:
        problems.append(f"{design}: {frames} frames, expected at least {min_frames}")
    return problems


def framesfile(dev: DevTools):
    path = str(dev.vgacap_src / "python")
    if path not in sys.path:
        sys.path.insert(0, path)
    from vgacap import framesfile

    return framesfile


def simulate(model: Path, dev: DevTools, out: Path, design: str, *extra: str) -> dict:
    """Run `design` with a trace into `out`; return its timing.json. Raises on an unexpected exit."""
    clock = ["--clock-hz", CLOCK_HZ[design]] if design in CLOCK_HZ else []
    p = run(model, dev, out, *clock, *extra, design=design)
    (out / "tb.stderr").write_text(p.stderr)
    tj = json.loads((out / "timing.json").read_text())
    if p.returncode != EXIT.get(tj["status"]):
        raise RuntimeError(f"{design}: tb exit {p.returncode} with status {tj['status']}: {p.stderr}")
    return tj


def sample(dev: DevTools, trace: Path, out: Path, name: str) -> Path:
    """`vgacap-sample TRACE --out OUT --name NAME --sampler tb-v1`; return OUT/tb-v1."""
    dev.require("vgacap_sample")
    check_pin(dev)
    cmd = [str(dev.vgacap_sample), str(trace), "--out", str(out), "--name", name, "--sampler", "tb-v1"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    (out.parent / f"{out.name}.log").write_text("$ " + " ".join(cmd) + f"\nexit {p.returncode}\n" + p.stdout + p.stderr)
    if p.returncode != 0:
        raise RuntimeError(f"vgacap-sample exit {p.returncode}: {p.stderr}")
    return out / "tb-v1"


def differences(dev: DevTools, run_dir: Path, tbv1_dir: Path) -> list[str]:
    """Every way tb-v1's FNV file differs from tb.cpp's timing.json and tb_frame_hashes.txt."""
    hf = framesfile(dev).read_hash_file(tbv1_dir / FNV)
    tj = json.loads((run_dir / "timing.json").read_text())
    tb = (run_dir / "tb_frame_hashes.txt").read_text().splitlines()
    diffs = []
    got = [h if h is not None else "-" for h in hf.hashes]
    for k in range(max(len(got), len(tb))):
        a = got[k] if k < len(got) else "(none)"
        b = tb[k] if k < len(tb) else "(none)"
        if a != b:
            diffs.append(f"frame {k}: tb-v1 {a}, tb.cpp {b}")
    expect = {"status": tj["status"], "frames": tj.get("frames", 0)}
    for key in ("mode", "width", "height", "capture_after_clock"):
        if key in tj:
            expect[key] = tj[key]
    have = {"status": hf.status, "frames": len(hf.hashes), "mode": hf.mode, "width": hf.width,
            "height": hf.height, "capture_after_clock": hf.capture_after_clock}
    for key, want in expect.items():
        if have[key] != want:
            diffs.append(f"{key}: tb-v1 {have[key]!r}, timing.json {want!r}")
    if "clocks_per_pixel" in tj and abs(hf.clocks_per_pixel - tj["clocks_per_pixel"]) > CPP_TOLERANCE + CPP_ROUNDING:
        diffs.append(f"clocks_per_pixel: tb-v1 {hf.clocks_per_pixel!r}, timing.json {tj['clocks_per_pixel']!r}")
    return diffs


def keep_mismatch(design: str, run_dir: Path, diffs: list[str]) -> Path:
    """Copy the run (trace, tb.cpp output, tb-v1 output) to tmp/tbv1-mismatch/<design>/ with the differences."""
    dest = MISMATCH_DIR / design
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run_dir, dest)
    (dest / "DIFFERENCES.txt").write_text("\n".join(diffs) + "\n")
    return dest
