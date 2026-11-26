# SPDX-License-Identifier: Apache-2.0
"""Make a centre-v1 frames.txt for a test design: simulate with a trace, then `vgacap-sample` it.

Used by `tests/fixtures/frames/make_fixture.py` (writes the committed fixtures) and
`tests/sim/test_fixtures_current.py` (regenerates them and compares).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.sim import tbv1
from ttvga.devtools import DevTools

#: Fixture name -> (design, --seconds).
CASES = {"bars640": ("bars640", "0.2"), "glitch": ("glitch", "0.2")}


def centre_frames_txt(dev: DevTools, model: Path, design: str, out: Path) -> Path:
    """Simulate `design` into `out`, sample its trace with centre-v1; return the frames.txt path."""
    dev.require("vgacap_sample")
    tbv1.check_pin(dev)
    tbv1.simulate(model, dev, out, design)
    cmd = [str(dev.vgacap_sample), str(out / "trace.vgch.zst"), "--out", str(out / "sampled"), "--name", design]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    (out / "sample.log").write_text("$ " + " ".join(cmd) + f"\nexit {p.returncode}\n" + p.stdout + p.stderr)
    if p.returncode != 0:
        raise RuntimeError(f"vgacap-sample exit {p.returncode}: {p.stderr}")
    return out / "sampled" / "centre-v1" / "frames.txt"
