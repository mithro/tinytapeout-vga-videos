# SPDX-License-Identifier: Apache-2.0
"""Write the fpga-library.json fixture and its five bins (spec section 1).

Run: uv run tests/fixtures/fpga-library/make_fixture.py

Each bin is 4096 bytes: ff 00 00 ff 7e aa 99 7e, zeros, with byte 8 set to the
entry's row number, so the five hashes differ. The ids are written out here, not
derived, so the fixture checks `library_id` rather than depending on it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREAMBLE = bytes.fromhex("ff0000ff7eaa997e")
ZERO_COMMIT = "0123456789abcdef0123456789abcdef01234567"

# (id, shuttle, macro, title, author, build_status, fmax_hz, ui_in, ui_in_mask, verdict, media)
ROWS = [
    ("ttsky25b_lukasdragoste_vga_patterns", "ttsky25b", "tt_um_lukasdragoste_vga_patterns",
     "VGA Patterns", "Lukas Dragoste", "ok", 31420000, 1, 1, "barely-moving", True),
    ("ttsky25a_vga_example", "ttsky25a", "tt_um_vga_example",
     "VGA Example", "Uri Shaked", "ok", 31420000, None, 0, "ok", True),
    ("ttihp26a_vga_example", "ttihp26a", "tt_um_vga_example",
     "VGA Example", "Uri Shaked", "ok", 29850000, None, 0, "ok", False),
    ("ttihp25a_yuri_panchul_sea_battl_09a2562b", "ttihp25a", "tt_um_yuri_panchul_sea_battle_vga_game",
     "Sea Battle VGA Game", "Yuri Panchul", "ok", 27300000, None, 0, "ok", True),
    ("tt05_flappy_vga_cutout1", "tt05", "tt_um_flappy_vga_cutout1",
     "Flappy VGA", "Tiny Tapeout Contributor", "timing-fail", 17080000, None, 0, "ok", True),
]


def entry(row: int, spec: tuple) -> dict:
    id_, shuttle, macro, title, author, status, fmax, ui_in, mask, verdict, media = spec
    data = bytearray(4096)
    data[: len(PREAMBLE)] = PREAMBLE
    data[8] = row
    sha = hashlib.sha256(data).hexdigest()
    bin_path = f"{shuttle}/{macro}/{id_}-{sha[:12]}.bin"
    (HERE / bin_path).parent.mkdir(parents=True, exist_ok=True)
    (HERE / bin_path).write_bytes(bytes(data))
    base = f"{shuttle}/{macro}/{shuttle}_{macro}"
    return {
        "id": id_,
        "shuttle": shuttle,
        "macro": macro,
        "title": title,
        "author": author,
        "description": "",
        "docs_url": f"https://tinytapeout.com/chips/{shuttle}/{macro}",
        "repo_url": "https://github.com/TinyTapeout/vga-playground-template",
        "commit": ZERO_COMMIT,
        "clock_hz": 25175000,
        "pinout": {
            "ui_in": [""] * 8,
            "uo_out": ["R1", "G1", "B1", "VSync", "R0", "G0", "B0", "HSync"],
            "uio": [""] * 8,
        },
        "ui_in": ui_in,
        "ui_in_mask": mask,
        "bin": bin_path,
        "bin_bytes": len(data),
        "bin_sha256": sha,
        "build_status": status,
        "fmax_hz": fmax,
        "validation": "none",
        "verdict": verdict,
        "qspi": "none",
        "poster": f"{base}_poster.png" if media else None,
        "preview_gif": f"{base}_preview.gif" if media else None,
        "video_10s_webm": f"{base}_10s.webm" if media else None,
    }


def main() -> None:
    doc = {
        "schema": 1,
        "generated": "2026-11-26T03:00:00Z",
        "tthfv_commit": ZERO_COMMIT,
        "videos_repo_commit": "89abcdef0123456789abcdef0123456789abcdef",
        "designs": [entry(i, spec) for i, spec in enumerate(ROWS)],
    }
    text = json.dumps(doc, indent=2, allow_nan=False) + "\n"
    (HERE / "fpga-library.json").write_text(text)


if __name__ == "__main__":
    main()
