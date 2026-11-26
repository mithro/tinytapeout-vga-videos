# SPDX-License-Identifier: Apache-2.0
"""vgacap's tb-v1 sampler, run on a tb.cpp trace, gives exactly tb.cpp's own frame hashes and timing.

A difference is a bug in vgacap's tb-v1 port: the run is kept in
tmp/tbv1-mismatch/<design>/ for the vgacap session. tb.cpp is never changed to match.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from tests.sim import tbv1
from tests.sim.build import DESIGNS

pytestmark = pytest.mark.sim

ALL_DESIGNS = sorted(p.stem for p in DESIGNS.glob("*.v"))


@pytest.mark.parametrize("design", ALL_DESIGNS)
def test_tbv1_matches_tb(design, models, dev, tmp_path):
    out = tmp_path / design
    tj = tbv1.simulate(models(design), dev, out, design)
    assert tbv1.expectation_problems(design, tj) == []
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
    hashes.write_text("\n".join(lines) + "\n")
    timing = out / "timing.json"
    original = timing.read_text()
    timing.write_text(original.replace('"width": 640', '"width": 641'))
    assert tbv1.differences(dev, out, tbv1_dir) == ["width: tb-v1 640, timing.json 641"]

    # clocks_per_pixel: tb-v1 has 1; exactly 5e-5 away is within, 5e-5 + 1e-9 is not.
    tj = json.loads(original)
    assert tj["clocks_per_pixel"] == 1.0
    for cpp, want in ((1 + 5e-5, []), (1 - 5e-5, []),
                      (1 + 5e-5 + 1e-9, [f"clocks_per_pixel: tb-v1 1.0, timing.json {1 + 5e-5 + 1e-9!r}"])):
        timing.write_text(json.dumps(dict(tj, clocks_per_pixel=cpp)))
        assert tbv1.differences(dev, out, tbv1_dir) == want, cpp


def test_expectations_cover_every_design():
    assert sorted(tbv1.EXPECT) == ALL_DESIGNS
    assert tbv1.expectation_problems("nosync", {"status": "no-sync"}) == []
    assert tbv1.expectation_problems("nosync", {"status": "no-sync", "frames": 1}) == ["nosync: 1 frames, expected 0"]
    assert tbv1.expectation_problems("bars640", {"status": "ok", "frames": 1}) == [
        "bars640: 1 frames, expected at least 2"]
    assert tbv1.expectation_problems("glitch", {"status": "ok", "frames": 12}) == [
        "glitch: status ok, expected unstable-sync"]


def test_sample_refuses_unpinned_vgacap(dev, tmp_path):
    fake = tmp_path / "vgacap-build"
    fake.mkdir()
    (fake / "PINNED").write_text("0" * 40 + "\n")
    with pytest.raises(RuntimeError, match="the pin is"):
        tbv1.sample(dataclasses.replace(dev, vgacap_build=fake), tmp_path / "t.vgch", tmp_path / "s", "x")
