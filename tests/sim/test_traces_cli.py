# SPDX-License-Identifier: Apache-2.0
"""`tt-vga trace` and `tt-vga sample` over a tb.cpp trace."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.sim.helpers import info
from tests.sim.tbv1 import simulate
from ttvga.cli import main

pytestmark = pytest.mark.sim


@pytest.fixture(scope="module")
def bars(models, dev, tmp_path_factory):
    out = tmp_path_factory.mktemp("bars640")
    simulate(models("bars640"), dev, out, "bars640")
    return out / "trace.vgch.zst"


@pytest.fixture(autouse=True)
def dev_env(dev, monkeypatch):
    monkeypatch.setenv("TTVGA_DEV_TOOLS", str(dev.root))


def changes(dev, path: Path) -> dict[str, list[tuple[int, str]]]:
    """The value changes of a waveform per signal name, as (time, value); id codes and bit padding are normalised."""
    if path.suffix == ".fst":
        text = subprocess.run([str(dev.fst2vcd), "-f", str(path)], capture_output=True, text=True, check=True).stdout
    else:
        text = path.read_text()
    names: dict[str, str] = {}
    out: dict[str, list[tuple[int, str]]] = {}
    now = 0
    body = False
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "$var" and not body:
            name = "".join(words[4:-1])
            names[words[3]] = name
            out[name] = []
        elif words[0] == "$enddefinitions":
            body = True
        elif not body or words[0].startswith("$"):
            continue
        elif line.startswith("#"):
            now = int(line[1:])
        elif words[0][0] in "bB" and len(words) == 2:
            bits = words[0][1:].lstrip("0") or "0"
            out[names[words[1]]].append((now, bits))
        elif words[0][0] in "01xXzZ" and len(words[0]) > 1:
            out[names[words[0][1:]]].append((now, words[0][0].lstrip("0") or "0"))
    return out


def test_export_fst_equals_vcd(dev, bars, tmp_path, capfd):
    dev.require("fst2vcd")
    fst, vcd = tmp_path / "t.fst", tmp_path / "t.vcd"
    assert main(["trace", "export", str(bars), "--format", "fst", "--out", str(fst), "--from", "0", "--to", "2000"]) == 0
    assert main(["trace", "export", str(bars), "--format", "vcd", "--out", str(vcd), "--from", "0", "--to", "2000"]) == 0
    a, b = changes(dev, fst), changes(dev, vcd)
    assert sum(len(v) for v in a.values()) > 10
    assert a == b
    assert main(["trace", "info", str(bars)]) == 0
    assert "close.status: ok" in capfd.readouterr().out


def test_sample_writes_both_on_request(bars, tmp_path):
    out = tmp_path / "out"
    assert main(["sample", str(bars), "--out", str(out), "--sampler", "centre-v1", "--sampler", "tb-v1"]) == 0
    for s in ("centre-v1", "tb-v1"):
        assert (out / s / "frames.txt").is_file()
        assert (out / s / "index.html").is_file()
        assert (out / s / f"test_bars640_{s}_frames.rgb6.zst").is_file()
    # The default is centre-v1 alone, and --name replaces the META project prefix.
    out2 = tmp_path / "out2"
    assert main(["sample", str(bars), "--out", str(out2), "--name", "mine"]) == 0
    assert (out2 / "centre-v1" / "mine_centre-v1_frames.rgb6.zst").is_file()
    assert not (out2 / "tb-v1").exists()
    assert main(["sample", str(bars), "--out", str(tmp_path / "o3"), "--sampler", "nope"]) == 1


def test_slice_then_export(dev, bars, tmp_path):
    sl = tmp_path / "slice.vgch.zst"
    assert main(["trace", "slice", str(bars), "--from", "1000", "--to", "3000", "--out", str(sl)]) == 0
    i = info(dev, sl)
    assert i["open.slice_from_clock"] == "1000" and i["clocks"] == "2000"
    vcd = tmp_path / "s.vcd"
    assert main(["trace", "export", str(sl), "--format", "vcd", "--out", str(vcd)]) == 0
    assert vcd.stat().st_size > 0
    # A slice is not derived.
    assert main(["sample", str(sl), "--out", str(tmp_path / "o")]) == 1
