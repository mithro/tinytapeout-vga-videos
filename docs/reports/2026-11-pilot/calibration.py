"""Task 21 Step 4: centre-v1 on the calibration designs against tt-vga-testpatterns' reference render.

    uv run tt-vga frames to-png <work>/<macro>/kept/centre-v1/frames.txt --out <dir>/<macro>/png
    uv run --project <tt-vga-testpatterns checkout> docs/reports/2026-11-pilot/calibration.py <dir>

<dir>/<macro>/ holds the job's centre-v1 frames.txt and the PNGs `tt-vga frames to-png` wrote from its
store (one per distinct frame). Run under tt-vga-testpatterns' own environment so that its
`tools/render.py` is the reference. ui_in comes from this repository's overrides/testpatterns/.

Each distinct frame must equal the render pixel for pixel. For counter and prbs, whose picture
changes every frame, the 8-bit frame counter is decoded from the frame itself (as tools/check.py
does) and the render is made for that value; and the counter must go up by 1 (mod 256) from each
captured frame to the next. Prints a Markdown table; exits 1 on any difference.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from tools import check, render

OVERRIDES = Path(__file__).resolve().parents[3] / "overrides" / "testpatterns"
# macro -> (render(ui_in, counter), expected mode, counter row or None)
DESIGNS = {
    "tt_um_vgacal_bars": (lambda u, c: render.bars(), "640x480@60", None),
    "tt_um_vgacal_grid": (lambda u, c: render.grid(), "640x480@60", None),
    "tt_um_vgacal_counter": (lambda u, c: render.counter(c), "640x480@60", 30),
    "tt_um_vgacal_prbs": (lambda u, c: render.prbs(c), "640x480@60", 4),
    "tt_um_vgacal_modes_m0": (lambda u, c: render.modes(ui_in=u), "640x480@60", None),
    "tt_um_vgacal_modes_m1": (lambda u, c: render.modes(ui_in=u), "800x600@60", None),
    "tt_um_vgacal_modes_m2": (lambda u, c: render.modes(ui_in=u), "720x400@70", None),
    "tt_um_vgacal_modes_m0_hneg": (lambda u, c: render.modes(ui_in=u), "640x480@60", None),
    "tt_um_vgacal_modes_m0_vneg": (lambda u, c: render.modes(ui_in=u), "640x480@60", None),
    "tt_um_vgacal_modes_m0_hvneg": (lambda u, c: render.modes(ui_in=u), "640x480@60", None),
}


def read_frames_txt(path: Path) -> tuple[dict, list[int]]:
    """The header keys, and each captured frame's distinct index (-1 for a gap), from the runs."""
    head, per_frame, section = {}, [], None
    for line in path.read_text().splitlines():
        if line in ("distinct:", "runs:"):
            section = line
            continue
        if section == "runs:":
            f = line.split()
            d = int(f[2]) if len(f) == 5 else -1
            per_frame += [d] * int(f[1])
        elif section is None:
            k, _, v = line.partition(": ")
            head[k] = v
    return head, per_frame


def ui_in(macro: str) -> int:
    for line in (OVERRIDES / f"{macro}.yaml").read_text().splitlines():
        if line.startswith("ui_in:"):
            return int(line.split(":")[1])
    return 0


def main() -> int:
    root, bad = Path(sys.argv[1]), 0
    print("| design | ui_in | mode | expected mode | size | frames | gaps | distinct | distinct equal to render "
          "| counter steps by 1 | result |")
    print("| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
    for macro, (fn, want_mode, row) in DESIGNS.items():
        head, per_frame = read_frames_txt(root / macro / "frames.txt")
        u = ui_in(macro)
        pngs = sorted((root / macro / "png").glob("*.png"))
        equal, counters, notes = 0, [], []
        for p in pngs:
            got = check.rgb_to_img6(np.asarray(Image.open(p).convert("RGB")))
            c = check.decode_frame_counter(got, row) if row is not None else 0
            counters.append(c)
            want = fn(u, c)
            if got.shape == want.shape and np.array_equal(got, want):
                equal += 1
            else:
                n = int((got != want).sum()) if got.shape == want.shape else "shape"
                notes.append(f"{p.name}: {n}")
        steps = "-"
        if row is not None:
            seq = [counters[d] for d in per_frame if d >= 0]
            ok = all(b == (a + 1) & 0xFF for a, b in zip(seq, seq[1:])) and -1 not in per_frame
            steps = "yes" if ok else "**no**"
        gaps = per_frame.count(-1)
        good = (equal == len(pngs) == int(head["distinct_frames"]) and head["mode"] == want_mode
                and steps != "**no**" and head["status"] == "ok")
        bad += not good
        print(f"| {macro} | {u} | {head['mode']} | {want_mode} | {head['width']}x{head['height']} | "
              f"{len(per_frame):,} | {gaps} | {len(pngs)} | {equal} | {steps} | "
              f"{'pixel-exact' if good else '**differs**'} |")
        for n in notes[:5]:
            print(f"<!-- {macro} {n} -->")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
