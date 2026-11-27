"""Task 21 Steps 1-3: tb-v1's FNV against git, distinct counts, tb-v1 against centre-v1.

    TTVGA_DEV_TOOLS=... uv run docs/reports/2026-11-pilot/correctness.py FRAMES_ROOT > tmp/correctness.md

FRAMES_ROOT is host.toml's frames_root (the published frames subtree). Run from the repository root.
Per project it writes, under docs/reports/2026-11-pilot/frames/<shuttle>__<macro>/:
- compare.txt: `tt-vga frames compare` of tb-v1 (A) and centre-v1 (B);
- diff.txt, a.png, b.png, mask.png: `tt-vga frames diff` of the first differing pair, when there is one.
It prints the Markdown tables to stdout. Step 1 exits 1 on any FNV difference.
"""
import subprocess
import sys
from pathlib import Path

from ttvga import devtools
from ttvga.harness import vgacap_path

vgacap_path.add_src(devtools.paths().vgacap_src)
from vgacap import framesfile  # noqa: E402

FNV = "frame_hashes.fnv1a64-tb2026-rgb888.txt"
HERE = Path("docs/reports/2026-11-pilot")
IDS = HERE.joinpath("ids.txt").read_text().split()
CHECKED = {"tt08/tt_um_nyan": 1, "ttihp25a/tt_um_MichaelBell_rle_vga": 1, "tt08/tt_um_MichaelBell_mandelbrot": 4}


def tt_vga(*args: str) -> str:
    p = subprocess.run(["tt-vga", *args], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"tt-vga {' '.join(args)}: exit {p.returncode}\n{p.stderr}")
    return p.stdout


def fields(text: str) -> dict[str, str]:
    return {k: v for k, _, v in (ln.partition(": ") for ln in text.splitlines()) if v}


def main() -> int:
    root = Path(sys.argv[1])
    print("## Step 1\n")
    print("| project | frames | hash lines equal | file bytes equal |")
    print("| --- | ---: | --- | --- |")
    bad = 0
    for id_ in IDS:
        git, pub = Path("data/results") / id_ / "frames/tb-v1" / FNV, root / id_ / "tb-v1" / FNV
        hg, hp = framesfile.read_hash_file(git), framesfile.read_hash_file(pub)
        same = hg.hashes == hp.hashes
        bad += not same
        print(f"| {id_} | {len(hp.hashes):,} | {'yes' if same else '**no**'} | "
              f"{'yes' if git.read_bytes() == pub.read_bytes() else 'no'} |")

    print("\n## Step 2\n")
    print("| project | tb-v1 distinct XXH3-128 | centre-v1 distinct XXH3-128 | distinct FNV | XXH3-128 minus FNV |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for id_ in IDS:
        tb = framesfile.read_frames_txt(root / id_ / "tb-v1/frames.txt")
        ce = framesfile.read_frames_txt(root / id_ / "centre-v1/frames.txt")
        fnv = {h for h in framesfile.read_hash_file(root / id_ / "tb-v1" / FNV).hashes if h is not None}
        print(f"| {id_} | {len(tb.distinct):,} | {len(ce.distinct):,} | {len(fnv):,} | {len(tb.distinct) - len(fnv)} |")
    total = 0
    files = sorted(Path("data/results").glob(f"*/*/frames/tb-v1/{FNV}"))
    for p in files:
        total += len({h for h in framesfile.read_hash_file(p).hashes if h is not None})
    print(f"\nCommitted FNV files: {len(files)}, distinct FNV values summed per project: {total:,}")

    print("\n## Step 3\n")
    print("| project | centre-v1 cpp | tb-v1 cpp | first mismatch | offset | start clock delta | differing pixels | diff |")
    print("| --- | ---: | ---: | --- | --- | --- | ---: | --- |")
    agree, checks = [], []
    for id_ in IDS:
        out = HERE / "frames" / id_.replace("/", "__")
        out.mkdir(parents=True, exist_ok=True)
        a, b = root / id_ / "tb-v1/frames.txt", root / id_ / "centre-v1/frames.txt"
        text = tt_vga("frames", "compare", str(a), str(b))
        (out / "compare.txt").write_text(text)
        c = fields(text)
        tb, ce = framesfile.read_frames_txt(a), framesfile.read_frames_txt(b)
        delta = text.split("start_clock_delta: ")[1].split()[0] if "start_clock_delta" in text else "-"
        px, link = "-", "-"
        k = c["first_mismatch"]
        if k != "none":
            d = tt_vga("frames", "diff", f"{a.parent / tb.store}@{k}", f"{b.parent / ce.store}@{k}",
                       "--out", str(out))
            (out / "diff.txt").write_text(d)
            px = f"{int(fields(d)['differing_pixels']):,}"
            link = f"[{k}](frames/{out.name}/)"
        elif ce.clocks_per_pixel == 1:
            agree.append(id_)
        print(f"| {id_} | {ce.clocks_per_pixel:g} | {tb.clocks_per_pixel:g} | {k} | {c['offset']} | {delta} | {px} | {link} |")
        if id_ in CHECKED:
            m = ce.centre
            checks.append((id_, CHECKED[id_], ce.clocks_per_pixel, m.colour_changes_off_grid, m.outside,
                           m.suggested_offset, m.porches))

    print("\n| project | cpp wanted | cpp | `colour_changes_off_grid` | `outside` | `suggested_offset` | `porches` | all as wanted |")
    print("| --- | ---: | ---: | ---: | ---: | --- | --- | --- |")
    for id_, want, cpp, off, outside, sug, por in checks:
        ok = cpp == want and off == 0 and outside == 0
        offs = "-" if off is None else f"{off:,}"
        print(f"| {id_} | {want} | {cpp:g} | {offs} | {outside:,} | {sug[0]} {sug[1]} | {por[0]} {por[1]} | "
              f"{'yes' if ok else '**no**'} |")
    print("\ncpp = 1 (centre-v1) projects where the samplers agree frame for frame:\n")
    for id_ in agree:
        print(f"- {id_}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
