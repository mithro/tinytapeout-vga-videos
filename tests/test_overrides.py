# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from ttvga.overrides import compile_gamepad, compile_inputs, compile_one, to_clocks


def test_to_clocks_units():
    assert to_clocks(1000, 25_000_000) == 1000
    assert to_clocks("2s", 25_000_000) == 50_000_000
    assert to_clocks("250ms", 25_000_000) == 6_250_000
    assert to_clocks("4us", 25_000_000) == 100
    with pytest.raises(ValueError):
        to_clocks("soon", 25_000_000)


def test_compile_inputs_carries_state_forward():
    text = compile_inputs([{"at": 0, "ui_in": 0x80}, {"at": "1s", "uio_in": 3}], 1000)
    assert text.splitlines()[1:] == ["0 0x80 0x00", "1000 0x80 0x03"]


def test_compile_gamepad_press_hold_release():
    text = compile_gamepad([
        {"at": "1s", "press": ["start"]},               # bit 3 for 100 ms
        {"at": "2s", "hold": ["right", "a"], "for": "1s"},
        {"at": "2.5s", "release": "all"},
    ], 1000)
    rows = [line.split() for line in text.splitlines()[1:]]
    assert rows == [["1000", "0x008"], ["1100", "0x000"], ["2000", "0x180"], ["2500", "0x000"], ["3000", "0x000"]]


def test_compile_one_writes_json_and_scripts(tmp_path):
    y = tmp_path / "ov" / "tt09" / "tt_um_x.yaml"
    y.parent.mkdir(parents=True)
    (y.parent / "fix.diff").write_text("--- a\n+++ b\n")
    y.write_text(
        "clock_hz: 1000\nverilator_flags: ['--timing']\npatch: fix.diff\n"
        "inputs:\n  - at: 1s\n    ui_in: 1\ngamepad:\n  - at: 2s\n    press: [b]\n"
    )
    out = tmp_path / "compiled" / "tt09"
    compiled = compile_one(y, {"clock_hz": 50}, out)
    assert compiled == {"clock_hz": 1000, "verilator_flags": ["--timing"], "inputs": "tt_um_x.inputs",
                        "gamepad": "tt_um_x.gamepad", "patch": "tt_um_x.diff"}
    assert json.loads((out / "tt_um_x.json").read_text()) == compiled
    assert (out / "tt_um_x.inputs").read_text().splitlines()[1] == "1000 0x01 0x00"   # override clock wins
    assert (out / "tt_um_x.gamepad").read_text().splitlines()[1] == "2000 0x001"
    assert (out / "tt_um_x.diff").exists()
