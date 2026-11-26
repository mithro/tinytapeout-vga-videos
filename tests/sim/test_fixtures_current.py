# SPDX-License-Identifier: Apache-2.0
"""tests/fixtures/frames/*/frames.txt are what vgacap-sample makes now, from a fresh simulation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.sim import framesfix

pytestmark = pytest.mark.sim

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "frames"


@pytest.mark.parametrize("name", sorted(framesfix.CASES))
def test_frames_fixture_is_current(name, models, dev, tmp_path):
    design, _ = framesfix.CASES[name]
    txt = framesfix.centre_frames_txt(dev, models(design), design, tmp_path)
    assert txt.read_bytes() == (FIXTURES / name / "frames.txt").read_bytes(), (
        "regenerate with: uv run tests/fixtures/frames/make_fixture.py")
