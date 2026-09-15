# SPDX-License-Identifier: Apache-2.0
"""Per-project overrides: YAML in `overrides/<shuttle>/<macro>.yaml`, compiled to what the host needs.

The YAML is written by people (or by the diagnosis agent) in convenient
units; `compile_all` turns it into plain JSON plus clock-based script files
under `data/overrides-compiled/`, which `tt-vga sync` copies to the host.
The host side (`harness/job.py`) then needs no YAML parser and no unit
conversion.

Keys:

    clock_hz: 50000000          # replaces the project's declared clock
    seconds: 60                 # length to simulate
    calib_seconds: 2            # how long to wait for stable sync
    ui_in: 0b00000001           # constant inputs (ints, any base as YAML allows)
    uio_in: 0
    verilator_flags: ["--timing"]
    sources: [a.v, b.v]         # replaces info.yaml source_files
    top_module: tt_um_x
    patch: fix.diff             # unified diff applied to the clone, relative to the YAML
    skip: "reason"              # do not simulate
    inputs:                     # timed changes of ui_in / uio_in
      - at: 0s                  # seconds ("3s"), milliseconds ("250ms") or clocks (int)
        ui_in: 0x80
      - at: 1000
        ui_in: 0
    gamepad:                    # Gamepad Pmod buttons, by name or bit index
      - at: 5s
        press: [start]          # held for `for` (default 100ms)
      - at: 8s
        hold: [right]
        for: 2s
      - at: 12s
        release: all
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml

from ttvga import DATA_DIR, OVERRIDES_DIR
from ttvga.targets import load_targets

COMPILED_DIR = DATA_DIR / "overrides-compiled"
DEFAULT_CLOCK_HZ = 25_175_000
# Bit index of each button in the 12-bit Gamepad Pmod report (playground InputController.ts).
GAMEPAD_BUTTONS = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
                   "a": 8, "x": 9, "l": 10, "r": 11}
PLAIN_KEYS = ("clock_hz", "seconds", "calib_seconds", "ui_in", "uio_in", "verilator_flags", "sources",
              "top_module", "skip")


def to_clocks(value: int | float | str, clock_hz: int) -> int:
    """'3s', '250ms', '4us' or a bare number of clocks."""
    if isinstance(value, (int, float)):
        return int(value)
    m = re.fullmatch(r"\s*([0-9.]+)\s*(s|ms|us|clk|clocks)?\s*", str(value))
    if not m:
        raise ValueError(f"bad time {value!r}")
    n, unit = float(m.group(1)), m.group(2) or "clocks"
    scale = {"s": clock_hz, "ms": clock_hz / 1000, "us": clock_hz / 1_000_000, "clk": 1, "clocks": 1}[unit]
    return int(round(n * scale))


def buttons_mask(names) -> int:
    if names in ("all", None):
        return 0xfff if names == "all" else 0
    mask = 0
    for n in names:
        mask |= 1 << (n if isinstance(n, int) else GAMEPAD_BUTTONS[str(n).lower()])
    return mask


def compile_inputs(events: list[dict], clock_hz: int) -> str:
    lines = ["# clock ui_in uio_in"]
    ui, uio = 0, 0
    for e in events:
        ui = int(e.get("ui_in", ui))
        uio = int(e.get("uio_in", uio))
        lines.append(f"{to_clocks(e['at'], clock_hz)} 0x{ui:02x} 0x{uio:02x}")
    return "\n".join(lines) + "\n"


def compile_gamepad(events: list[dict], clock_hz: int) -> str:
    """Expand press/hold/release events into (clock, buttons) state changes."""
    changes: list[tuple[int, int, int]] = []   # (clock, set_mask, clear_mask)
    for e in events:
        at = to_clocks(e["at"], clock_hz)
        if "press" in e or "hold" in e:
            mask = buttons_mask(e.get("press", e.get("hold")))
            length = to_clocks(e.get("for", "100ms"), clock_hz)
            changes.append((at, mask, 0))
            changes.append((at + length, 0, mask))
        if "release" in e:
            changes.append((at, 0, buttons_mask(e["release"])))
    changes.sort()
    state, lines = 0, ["# clock buttons"]
    for clock, set_mask, clear_mask in changes:
        state = (state | set_mask) & ~clear_mask
        lines.append(f"{clock} 0x{state:03x}")
    return "\n".join(lines) + "\n"


def compile_one(yaml_path: Path, target: dict | None, out_dir: Path) -> dict:
    ov = yaml.safe_load(yaml_path.read_text()) or {}
    clock_hz = int(ov.get("clock_hz") or (target or {}).get("clock_hz") or 0) or DEFAULT_CLOCK_HZ
    macro = yaml_path.stem
    compiled = {k: ov[k] for k in PLAIN_KEYS if k in ov}
    out_dir.mkdir(parents=True, exist_ok=True)
    if ov.get("inputs"):
        (out_dir / f"{macro}.inputs").write_text(compile_inputs(ov["inputs"], clock_hz))
        compiled["inputs"] = f"{macro}.inputs"
    if ov.get("gamepad"):
        (out_dir / f"{macro}.gamepad").write_text(compile_gamepad(ov["gamepad"], clock_hz))
        compiled["gamepad"] = f"{macro}.gamepad"
    if ov.get("patch"):
        shutil.copy(yaml_path.parent / ov["patch"], out_dir / f"{macro}.diff")
        compiled["patch"] = f"{macro}.diff"
    (out_dir / f"{macro}.json").write_text(json.dumps(compiled, indent=2) + "\n")
    return compiled


def compile_all(overrides_dir: Path = OVERRIDES_DIR, out_dir: Path = COMPILED_DIR) -> int:
    """Compile every override; returns how many. The output directory is rebuilt from scratch."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    targets = {t["id"]: t for t in load_targets()} if (DATA_DIR / "targets.json").exists() else {}
    n = 0
    for yaml_path in sorted(overrides_dir.glob("*/*.yaml")):
        shuttle = yaml_path.parent.name
        compile_one(yaml_path, targets.get(f"{shuttle}/{yaml_path.stem}"), out_dir / shuttle)
        n += 1
    return n
