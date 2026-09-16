# SPDX-License-Identifier: Apache-2.0
"""Derive an input script for a project from the names it gives its pins.

A design that shows nothing, or shows one unchanging picture, is often just
waiting to be driven: a game wants its buttons, a UART receiver wants an idle
line, a stepper wants a clock edge. Project authors write what each pin does
in `info.yaml`, and those names are in `data/targets.json`, so the script can
be derived rather than written by hand for every project.

What is produced is an ordinary override (see `ttvga/overrides.py`), written
to `overrides/<shuttle>/<macro>.yaml` with a comment saying where it came
from, so it can be read, corrected and committed like a hand-written one.

Only three things are inferred, all from pin names:

- Gamepad Pmod pins (latch/clock/data) mean the design reads a controller, so
  the Pmod protocol is emulated and buttons are pressed in a pattern.
- A UART receive pin is held high, because an idle line is high and holding it
  low looks like an endless break condition.
- Pins named after buttons or steps are pulsed or held in turn.

Anything else is left alone.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from ttvga import OVERRIDES_DIR, ROOT
from ttvga.analyze import analyze_all
from ttvga.targets import load_targets

# Pin names, lower-cased, that mean "press me". Each entry is a regular
# expression matched against the whole pin name, and a priority: directions and
# actions make better video than menu buttons.
BUTTONS = [
    (r".*\b(up|north)\b.*", "up"),
    (r".*\b(down|south)\b.*", "down"),
    (r".*\b(left|west)\b.*", "left"),
    (r".*\b(right|east)\b.*", "right"),
    (r".*\b(a|b|x|y|fire|shoot|jump|flap|action|button|btn|hit|kick|serve)\b.*", "action"),
    (r".*\b(start|begin|go|play|enable|en|run)\b.*", "start"),
    (r".*\b(select|menu|mode|next|prev|previous|cycle|switch)\b.*", "select"),
    (r".*\b(step|advance|tick|inc|increment|randomi[sz]e|add)\b.*", "step"),
]
GAMEPAD_PINS = {"latch": r"(gamepad|snes|nes|pad).*latch|latch.*(gamepad|snes|nes|pad)",
                "clock": r"(gamepad|snes|nes|pad).*(clk|clock)|(clk|clock).*(gamepad|snes|nes|pad)",
                "data": r"(gamepad|snes|nes|pad).*data|data.*(gamepad|snes|nes|pad)"}
# The Gamepad Pmod is wired to fixed pins, so a project that uses one does not
# have to name them for us to drive it. From the playground's own example:
#     .pmod_data(ui_in[6]), .pmod_clk(ui_in[5]), .pmod_latch(ui_in[4])
# which agrees with its InputController packing the pins as
#     (data << 6) | (clock << 5) | (latch << 4)
GAMEPAD_STANDARD = {"latch": 4, "clock": 5, "data": 6}
GAMEPAD_ANY = r"\b(gamepad|snes|nes)\b"
UART_RX = r"\b(uart[_ ]?rx|rx|rxd|serial[_ ]?in|rx[_ ]?in)\b"
# Names that must not be driven. Either the pin stops the picture, or it is
# part of an interface (a video input, a serial bus, a memory) where a lone
# toggle means nothing: those need a model, not a button press.
AVOID = (r"\b(pause|hold|halt|stop|reset|rst|freeze|blank|off|disable|power"
         r"|vga|rgb|hsync|vsync|sync|pixel|colou?r|video"
         r"|spi|qspi|psram|flash|sram|miso|mosi|sck|sclk|scl|sda|cs|csb|cs_n|ss"
         r"|serial|uart|tx|txd|i2c|latency|addr|address|config|cfg|register|reg"
         r"|audio|pwm|pdm|clk|clock|latch)\b")

# The order button classes are exercised in: something that starts the design
# first, then the ones that usually change the picture most.
ORDER = ["start", "action", "right", "down", "left", "up", "select", "step"]
FIRST = 3.0         # seconds before the first press
EVERY = 3.5         # seconds between presses
HOLD = 0.4          # seconds a direction is held
TAP = 0.05          # seconds any other button press lasts


def pin_index(pin: str) -> int | None:
    m = re.fullmatch(r"ui\[(\d)\]", pin)
    return int(m.group(1)) if m else None


def classify(pinout: dict[str, str]) -> tuple[dict[str, int], dict[str, list[int]], list[int]]:
    """Return (gamepad pins, button classes to bit numbers, UART receive bits) for ui_in."""
    gamepad: dict[str, int] = {}
    buttons: dict[str, list[int]] = {}
    uart: list[int] = []
    for pin, raw in sorted(pinout.items()):
        bit = pin_index(pin)
        if bit is None or not raw:
            continue
        # Underscores separate words here: SPI_START is a SPI pin, not a start button.
        name = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
        is_gamepad = False
        for role, pattern in GAMEPAD_PINS.items():
            if re.search(pattern, name):
                gamepad[role] = bit
                is_gamepad = True
        if is_gamepad:
            continue
        if re.search(UART_RX, name):
            uart.append(bit)
            continue
        if re.search(AVOID, name):
            continue
        for pattern, cls in BUTTONS:
            if re.fullmatch(pattern, name):
                buttons.setdefault(cls, []).append(bit)
                break
    return gamepad, buttons, uart


GAMEPAD_NAMES = {"up": "up", "down": "down", "left": "left", "right": "right",
                 "action": "a", "start": "start", "select": "select", "step": "b"}


def schedule(count: int, seconds: float) -> list[float]:
    """Times for `count` presses, repeating through the clip."""
    slots = max(1, int((seconds - FIRST) / EVERY))
    return [FIRST + i * EVERY for i in range(min(count, slots))]


def wants_gamepad(target: dict) -> str | None:
    """Why this project looks wired to a Gamepad Pmod, or None.

    Projects name these pins inconsistently: some spell out `gamepad_latch`,
    some label all three simply `gamepad`, and some declare the Pmod and leave
    the pin names blank. The wiring is fixed whichever way they write it, so
    any of those is enough to go on.
    """
    if any("gamepad" in str(p).lower() for p in (target.get("pmods") or [])):
        return "the project declares a Gamepad Pmod"
    pinout = target.get("pinout") or {}
    named = [b for b in GAMEPAD_STANDARD.values()
             if re.search(GAMEPAD_ANY,
                          re.sub(r"[^a-z0-9]+", " ", str(pinout.get(f"ui[{b}]", "")).lower()))]
    if len(named) == len(GAMEPAD_STANDARD):
        return "ui[4], ui[5] and ui[6] are all named for a gamepad"
    return None


def derive(target: dict, seconds: float = 60.0) -> tuple[dict, str] | None:
    """Return (override dict, explanation) for a project, or None if nothing to drive."""
    gamepad, buttons, uart = classify(target["pinout"])
    standard = None
    if len(gamepad) != 3:
        standard = wants_gamepad(target)
        if standard:
            # The pins did not name their roles, but the Pmod's wiring is fixed.
            gamepad = dict(GAMEPAD_STANDARD)
    if len(gamepad) == 3:
        # One button at a time, directions twice as they show movement best.
        order = ["start", "a", "right", "down", "left", "up", "a", "right", "up", "select", "b", "left", "down"]
        events = [{"at": f"{at}s", "hold": [name], "for": f"{HOLD}s"}
                  for at, name in zip(schedule(len(order), seconds), order)]
        found = f"assumed from the standard wiring because {standard}" if standard else "found"
        why = (f"Gamepad Pmod pins {found} (latch ui[{gamepad['latch']}], "
               f"clock ui[{gamepad['clock']}], data ui[{gamepad['data']}]); the protocol is "
               f"emulated and one button is held at a time.")
        return {"gamepad": events}, why

    if not buttons and not uart:
        return None

    base = 0
    for bit in uart:
        base |= 1 << bit
    # One pin at a time, so a press that stops the design can be told apart
    # from one that starts it. Each named pin gets a turn, directions first
    # among the repeats because they usually move something.
    pins: list[tuple[str, int]] = []
    for cls in ORDER:
        for bit in sorted(buttons.get(cls, [])):
            pins.append((cls, bit))
    repeats = [(cls, bit) for cls, bit in pins if cls in ("right", "down", "left", "up", "action")]
    pins = pins + repeats
    events = [{"at": 0, "ui_in": base}]
    used: list[str] = []
    for at, (cls, bit) in zip(schedule(len(pins), seconds), pins):
        length = HOLD if cls in ("up", "down", "left", "right") else TAP
        events.append({"at": f"{at}s", "ui_in": base | (1 << bit)})
        events.append({"at": f"{at + length}s", "ui_in": base})
        used.append(f"{cls} ui[{bit}]")
    if len(events) <= 1:
        if not uart:
            return None
        why = f"ui[{uart[0]}] is a UART receive pin, held high so the line reads as idle."
        return {"inputs": events}, why
    why = ""
    if uart:
        why += f"UART receive on ui{uart} held high. "
    why += "One pin at a time, from the pin names: " + ", ".join(dict.fromkeys(used)) + "."
    return {"inputs": events}, why


def to_yaml(override: dict, why: str) -> str:
    lines = ["# Derived from the project's own pin names by `tt-vga stimulus`.",
             "# " + why, "# Correct it by hand if the design wants something else.", ""]
    for key, events in override.items():
        lines.append(f"{key}:")
        for e in events:
            first = True
            for k, v in e.items():
                value = v if not isinstance(v, list) else "[" + ", ".join(str(x) for x in v) + "]"
                lines.append(f"  {'- ' if first else '  '}{k}: {value}")
                first = False
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    verdicts = {v for v in args.verdicts.split(",") if v}
    results = {r["id"]: r for r in analyze_all()} if verdicts else {}
    written, skipped, nothing = 0, 0, 0
    for target in load_targets():
        if target["skip"]:
            continue
        if verdicts and results.get(target["id"], {}).get("verdict") not in verdicts:
            continue
        path = OVERRIDES_DIR / target["shuttle"] / f"{target['macro']}.yaml"
        if path.exists() and not args.force:
            skipped += 1
            continue
        derived = derive(target, args.seconds)
        if derived is None:
            nothing += 1
            continue
        override, why = derived
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(to_yaml(override, why))
        else:
            print(f"--- {target['id']}\n{to_yaml(override, why)}")
        written += 1
    verb = "wrote" if args.write else "would write"
    print(f"{verb} {written} stimulus overrides; {skipped} already had one; {nothing} had no drivable pins")
    if args.write and written:
        print(f"review them with: git diff --stat {OVERRIDES_DIR.relative_to(ROOT)}")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("stimulus", help="derive input scripts from the projects' own pin names")
    p.add_argument("--verdicts", default="static,blank,no-sync",
                   help="only projects with these verdicts (empty for all)")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--write", action="store_true", help="write the override files")
    p.add_argument("--force", action="store_true", help="overwrite existing overrides")
    p.set_defaults(func=run)
