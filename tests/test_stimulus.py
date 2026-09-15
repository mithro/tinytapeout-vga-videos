# SPDX-License-Identifier: Apache-2.0
import yaml

from ttvga.stimulus import classify, derive, to_yaml


def pinout(**names):
    """pinout(ui0='left', ui4='gamepad_latch') -> {'ui[0]': 'left', ...}"""
    return {f"ui[{k[2:]}]": v for k, v in names.items()}


def test_gamepad_pins_recognised():
    gamepad, buttons, uart = classify(pinout(ui4="gamepad_latch", ui5="gamepad_clk", ui6="gamepad_data"))
    assert gamepad == {"latch": 4, "clock": 5, "data": 6}
    assert not buttons and not uart
    gamepad, _, _ = classify(pinout(ui4="SNES_PMOD_Latch", ui5="SNES_PMOD_Clk", ui6="SNES_PMOD_Data"))
    assert gamepad == {"latch": 4, "clock": 5, "data": 6}


def test_buttons_and_uart_and_avoided_names():
    _, buttons, uart = classify(pinout(
        ui0="Scroll speed bit 0", ui2="Pause scrolling", ui3="UART RX", ui4="FLAP", ui5="START"))
    assert buttons == {"action": [4], "start": [5]}
    assert uart == [3]
    # A pin that would stop the picture is never driven.
    _, buttons, _ = classify(pinout(ui6="External Hold", ui7="External Step (on rising edge)"))
    assert buttons == {"step": [7]}


def test_derive_gamepad_holds_buttons():
    override, why = derive({"pinout": pinout(ui4="gamepad_latch", ui5="gamepad_clk", ui6="gamepad_data")})
    assert "gamepad" in override and "inputs" not in override
    assert override["gamepad"][0] == {"at": "3.0s", "hold": ["start"], "for": "0.4s"}
    assert [e["hold"][0] for e in override["gamepad"]][:4] == ["start", "a", "right", "down"]
    assert "Gamepad Pmod pins found" in why


def test_derive_buttons_keeps_uart_high_throughout():
    override, why = derive({"pinout": pinout(ui3="UART RX", ui0="left", ui1="right")})
    events = override["inputs"]
    assert events[0] == {"at": 0, "ui_in": 0b1000}
    assert all(e["ui_in"] & 0b1000 for e in events)          # the UART line never drops
    assert any(e["ui_in"] == 0b1010 for e in events)         # right is pressed at some point
    assert "UART receive" in why


def test_only_one_pin_is_driven_at_a_time():
    override, _ = derive({"pinout": pinout(ui0="jump", ui1="fire", ui2="start")})
    pressed = [e["ui_in"] for e in override["inputs"] if e["ui_in"]]
    assert pressed and all(bin(v).count("1") == 1 for v in pressed)


def test_derive_returns_none_without_drivable_pins():
    assert derive({"pinout": pinout(ui0="", ui1="SPI latency[0]")}) is None


def test_to_yaml_round_trips():
    override, why = derive({"pinout": pinout(ui0="up", ui1="down")})
    parsed = yaml.safe_load(to_yaml(override, why))
    assert parsed["inputs"][0] == {"at": 0, "ui_in": 0}
    assert {"at", "ui_in"} <= set(parsed["inputs"][1])
    gamepad, _ = derive({"pinout": pinout(ui4="pad latch", ui5="pad clock", ui6="pad data")})
    parsed = yaml.safe_load(to_yaml(gamepad, "why"))
    assert parsed["gamepad"][0]["hold"] == ["start"]
