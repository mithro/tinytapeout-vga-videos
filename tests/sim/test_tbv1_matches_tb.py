# SPDX-License-Identifier: Apache-2.0
"""vgacap's tb-v1 sampler, run on a tb.cpp trace, gives exactly tb.cpp's own frame hashes and timing.

A difference is a bug in vgacap's tb-v1 port: the run is kept in
tmp/tbv1-mismatch/<design>/ for the vgacap session. tb.cpp is never changed to match.
"""

from __future__ import annotations

import pytest

from tests.sim import tbv1
from tests.sim.build import DESIGNS

pytestmark = pytest.mark.sim

ALL_DESIGNS = sorted(p.stem for p in DESIGNS.glob("*.v"))


@pytest.mark.parametrize("design", ALL_DESIGNS)
def test_tbv1_matches_tb(design, models, dev, tmp_path):
    out = tmp_path / design
    tbv1.simulate(models(design), dev, out, design)
    tbv1_dir = tbv1.sample(dev, out / "trace.vgch.zst", out / "sampled", design)
    diffs = tbv1.differences(dev, out, tbv1_dir)
    if diffs:
        kept = tbv1.keep_mismatch(design, out, diffs)
        pytest.fail(f"tb-v1 differs from tb.cpp on {design} (kept in {kept}):\n" + "\n".join(diffs))


def test_differences_sees_a_changed_hash(models, dev, tmp_path):
    """The comparison itself catches a one-frame difference, a missing frame and a changed field."""
    out = tmp_path / "bars640"
    tbv1.simulate(models("bars640"), dev, out, "bars640")
    tbv1_dir = tbv1.sample(dev, out / "trace.vgch.zst", out / "sampled", "bars640")
    assert tbv1.differences(dev, out, tbv1_dir) == []
    hashes = out / "tb_frame_hashes.txt"
    lines = hashes.read_text().splitlines()
    hashes.write_text("\n".join(["0" * 16] + lines[1:-1]) + "\n")
    diffs = tbv1.differences(dev, out, tbv1_dir)
    assert diffs == [f"frame 0: tb-v1 {lines[0]}, tb.cpp {'0' * 16}",
                     f"frame {len(lines) - 1}: tb-v1 {lines[-1]}, tb.cpp (none)"]
    timing = out / "timing.json"
    timing.write_text(timing.read_text().replace('"width": 640', '"width": 641'))
    assert "width: tb-v1 640, timing.json 641" in tbv1.differences(dev, out, tbv1_dir)
