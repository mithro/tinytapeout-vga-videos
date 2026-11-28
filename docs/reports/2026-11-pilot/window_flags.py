"""The `window` flags (docs/consumers.md, "Sampler windows") of the 11 pilot projects' published frames.

    TTVGA_DEV_TOOLS=... uv run docs/reports/2026-11-pilot/window_flags.py FRAMES_ROOT > tmp/window-flags.md

FRAMES_ROOT is host.toml's frames_root (the published frames subtree), read only. Run from the repository
root. It reads `<FRAMES_ROOT>/<id>/<sampler>/frames.txt` for both samplers, computes the flags with
`derive.windows` (the code that writes them into result.json) and prints a Markdown table.

Every row is checked: the two samplers must have the same mode and `frame_clocks`. All disagreements are
listed on stderr after the table, and the script then exits 1.
"""
import sys
from pathlib import Path

from ttvga import devtools
from ttvga.harness import derive, vgacap_path

vgacap_path.add_src(devtools.paths().vgacap_src)
from vgacap import framesfile  # noqa: E402

HERE = Path("docs/reports/2026-11-pilot")
IDS = HERE.joinpath("ids.txt").read_text().split()


def num(v: int | None) -> str:
    return "-" if v is None else f"{v:,}"


def yes(v: bool) -> str:
    return "yes" if v else "**no**"


def main() -> int:
    root = Path(sys.argv[1])
    problems: list[str] = []
    print("| project | mode | centre-v1 cpp | tb-v1 cpp | frame_clocks | centre-v1 mode_frame_clocks | `outside` "
          "| `suggested_offset` | tb-v1 line_clocks | tb-v1 lines | mode_line_clocks | mode_lines "
          "| centre-v1 exact | tb-v1 exact |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |")
    for pid in IDS:
        read = {s: framesfile.read_frames_txt(root / pid / s / "frames.txt") for s in (derive.CENTRE, derive.TB_V1)}
        w = derive.windows(read)
        c, t = w[derive.CENTRE], w[derive.TB_V1]
        if read[derive.CENTRE].mode != read[derive.TB_V1].mode:
            problems.append(f"{pid}: mode {read[derive.CENTRE].mode} in centre-v1, {read[derive.TB_V1].mode} in tb-v1")
        if c["frame_clocks"] != t["frame_clocks"]:
            problems.append(f"{pid}: frame_clocks {c['frame_clocks']} in centre-v1, {t['frame_clocks']} in tb-v1")
        x, y = c["suggested_offset"]
        print(f"| {pid} | {read[derive.CENTRE].mode} | {read[derive.CENTRE].clocks_per_pixel:g} "
              f"| {read[derive.TB_V1].clocks_per_pixel:g} | {num(c['frame_clocks'])} | {num(c['mode_frame_clocks'])} "
              f"| {num(c['outside'])} | ({x}, {y}) | {num(t['line_clocks'])} | {num(t['lines'])} "
              f"| {num(t['mode_line_clocks'])} | {num(t['mode_lines'])} | {yes(c['exact'])} | {yes(t['exact'])} |")
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
