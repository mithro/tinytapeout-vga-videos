# SPDX-License-Identifier: Apache-2.0
"""`tt-vga frames hash` writes the same bytes as vgacap-sample's own hash files."""

from __future__ import annotations

import pytest

from tests.sim.tbv1 import simulate
from ttvga.cli import main

pytestmark = pytest.mark.sim


@pytest.fixture(autouse=True)
def dev_env(dev, monkeypatch):
    monkeypatch.setenv("TTVGA_DEV_TOOLS", str(dev.root))


@pytest.fixture(scope="module")
def sampled(models, dev, tmp_path_factory):
    out = tmp_path_factory.mktemp("bars640")
    simulate(models("bars640"), dev, out, "bars640")
    res = tmp_path_factory.mktemp("sampled")
    assert main(["sample", str(out / "trace.vgch.zst"), "--out", str(res), "--sampler", "centre-v1", "--sampler", "tb-v1"]) == 0
    return res


# vgacap-sample writes sha256-rgb6 for both samplers and the FNV file for tb-v1 only.
@pytest.mark.parametrize("sampler,method", [("centre-v1", "sha256-rgb6"), ("tb-v1", "sha256-rgb6"),
                                            ("tb-v1", "fnv1a64-tb2026-rgb888")])
def test_hash_matches_vgacap_sample(sampled, sampler, method, tmp_path):
    theirs = sampled / sampler / f"frame_hashes.{method}.txt"
    assert theirs.is_file()
    mine = tmp_path / "mine.txt"
    assert main(["frames", "hash", str(sampled / sampler / "frames.txt"), "--method", method, "--out", str(mine)]) == 0
    assert mine.read_bytes() == theirs.read_bytes()
