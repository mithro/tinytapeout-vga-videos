"""The `window` flags (docs/consumers.md, "Sampler windows") of the 11 pilot projects' published frames.

    TTVGA_DEV_TOOLS=... uv run docs/reports/2026-11-pilot/window_flags.py FRAMES_ROOT > tmp/window-flags.md

FRAMES_ROOT is host.toml's frames_root (the published frames subtree), read only. Run from the repository
root. It reads `<FRAMES_ROOT>/<id>/<sampler>/frames.txt` for both samplers, computes the flags with
`derive.windows` (the code that writes them into result.json) and prints a Markdown table.
"""
import sys
from pathlib import Path

from ttvga import devtools
from ttvga.harness import derive, vgacap_path

vgacap_path.add_src(devtools.paths().vgacap_src)
from vgacap import framesfile  # noqa: E402

HERE = Path("docs/reports/2026-11-pilot")
IDS = HERE.joinpath("ids.txt").read_text().split()


def main() -> int:
    root = Path(sys.argv[1])
    print("| project | mode | centre-v1 cpp | tb-v1 cpp | frame_clocks | mode_frame_clocks | `outside` "
          "| `suggested_offset` | centre-v1 exact | tb-v1 exact |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |")
    for pid in IDS:
        read = {s: framesfile.read_frames_txt(root / pid / s / "frames.txt") for s in (derive.CENTRE, derive.TB_V1)}
        w = derive.windows(read)
        c, t = w[derive.CENTRE], w[derive.TB_V1]
        if read[derive.CENTRE].mode != read[derive.TB_V1].mode or c["frame_clocks"] != t["frame_clocks"] \
                or c["mode_frame_clocks"] != t["mode_frame_clocks"]:
            sys.exit(f"{pid}: the samplers disagree on mode or timing: {w}")
        x, y = c["suggested_offset"]
        print(f"| {pid} | {read[derive.CENTRE].mode} | {read[derive.CENTRE].clocks_per_pixel:g} "
              f"| {read[derive.TB_V1].clocks_per_pixel:g} | {c['frame_clocks']:,} | {c['mode_frame_clocks']:,} "
              f"| {c['outside']:,} | ({x}, {y}) | {'yes' if c['exact'] else '**no**'} "
              f"| {'yes' if t['exact'] else '**no**'} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
