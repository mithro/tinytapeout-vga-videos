"""The owner report's projections to all projects (plan Task 22). Run from the repository root:

    uv run docs/reports/2026-11-pilot/report_projection.py > tmp/report-projection.md

Inputs, all committed:
- `data/results/*/*/result.json`: the reference run's `timings`, `timing.clocks_simulated` and
  `timing.distinct_frames` (the projects "with frames" are those with `distinct_frames`);
- `docs/reports/2026-11-pilot/raw/*.json`: the pilot's records (Task 20);
- `docs/reports/2026-11-pilot/logs/derive-now.jsonl`: derive at this commit (`derive_now.py`);
- `STUDY_MB` below: the trace-format study's "Total bytes, MB" table, vgacap 00037fa.

Every projection is linear in one pilot quantity and says which. The pilot was chosen for busy
designs, so projections from its bytes per clock or per distinct frame likely overstate.
"""
import json
from pathlib import Path

HERE = Path("docs/reports/2026-11-pilot")
IDS = HERE.joinpath("ids.txt").read_text().split()

# https://github.com/mithro/vgacap/blob/00037fa417057afe7b3df19d4bb2eeb3ffcc1d2f/docs/superpowers/2026-11-27-trace-format-study.md
# "File size and background CPU", "Total bytes, MB (projected to the whole trace where sampled)".
STUDY_FORMATS = ("vgch2 (zstd 1)", "planar (zstd 1)", "sigrok-like (deflate 6)", "FST (LZ4)", "FST (zlib)",
                 "FST with clk (LZ4)", "VCD (zstd 1)", "LXT2")
STUDY_MB = {
    "nyancat": (416.43, 53.76, 249.48, 211.69, 160.84, 121.50, 3330.34, 6103.70),
    "rle_vga": (18.39, 0.62, 43.89, 39.50, 22.49, 50.88, 824.85, 13283.69),
    "dvd_screensaver": (1.31, 1.36, 51.74, 2.87, 3.11, 55.66, 26.81, 37.73),
    "colorbars": (0.56, 0.67, 162.61, 2.05, 3.69, 54.67, 221.17, 304.67),
    "mandelbrot": (14.72, 8.13, 230.39, 10.44, 16.10, 94.61, 106.79, 128.29),
    "atari2600": (596.59, 9.02, 590.82, 317.52, 214.97, 101.09, 5451.29, 7341.87),
    "vgadonut": (167.33, 35.13, 205.82, 78.69, 55.01, 91.26, 853.19, 2269.49),
    "cfib_demo": (20.59, 2.45, 192.13, 22.14, 14.11, 40.60, 178.81, 324.15),
    "nyan": (51.78, 0.51, 167.79, 47.58, 39.46, 26.84, 171.28, 191.75),
    "metaballs": (1.33, 0.72, 90.56, 1.03, 1.00, 36.62, 19.54, 36.35),
    "tomkeddie_a": (0.11, 0.16, 60.14, 0.67, 1.14, 53.09, 49.86, 61.76),
}
# The same study, "A full-pin export to FST: vgch2's file against planar's, median of the reps":
# process CPU s of the export from vgch2's file, and of vgacap-export itself on it.
EXPORT_CPU_S = {
    "tt08/tt_um_a1k0n_nyancat": (447.9, 541.0),
    "ttihp25a/tt_um_MichaelBell_rle_vga": (516.2, 468.9),
    "ttihp25a/tt_um_rejunity_atari2600": (757.5, 791.3),
}
JOBS = 24
OLD_STAGES = ("fetch", "build", "simulate", "encode")
NEW_STAGES = ("fetch", "build", "simulate", "derive", "encode", "publish")


def results() -> dict[str, dict]:
    out = {}
    for p in sorted(Path("data/results").glob("*/*/result.json")):
        r = json.loads(p.read_text())
        out[r["id"]] = r
    return out


def raw(pid: str) -> dict:
    return json.loads(HERE.joinpath("raw", pid.replace("/", "__") + ".json").read_text())


def mean(xs):
    return sum(xs) / len(xs)


def gb(x: float) -> str:
    return f"{x / 1e9:,.2f}"


def main() -> None:
    res = results()
    framed = {i: r for i, r in res.items() if (r.get("timing") or {}).get("distinct_frames") is not None}
    clocks_all = sum(int(r["timing"]["clocks_simulated"]) for r in framed.values())
    distinct_all = sum(int(r["timing"]["distinct_frames"]) for r in framed.values())
    clocks_pilot = sum(int(res[i]["timing"]["clocks_simulated"]) for i in IDS)
    distinct_pilot = sum(int(res[i]["timing"]["distinct_frames"]) for i in IDS)
    print(f"projects with frames: {len(framed)}; their clocks: {clocks_all:,}; distinct frames: {distinct_all:,}")
    print(f"pilot: clocks {clocks_pilot:,}; distinct frames {distinct_pilot:,}; "
          f"clocks share {clocks_pilot / clocks_all:.4f}\n")

    # 1. Trace size per format.
    print("## Trace size per format\n")
    print("| format | pilot total (MB) | over vgch2 | 408 projects, projected (GB) |")
    print("| --- | ---: | ---: | ---: |")
    vg = sum(v[0] for v in STUDY_MB.values())
    for k, name in enumerate(STUDY_FORMATS):
        tot = sum(v[k] for v in STUDY_MB.values())
        print(f"| {name} | {tot:,.2f} | {tot / vg:.3f} | {tot * 1e6 / clocks_pilot * clocks_all / 1e9:,.1f} |")
    print()

    # 1b. Exporting every trace to FST from VGCH v2, scaled by clocks from the study's 3 busy traces.
    print("## A full-pin export to FST, projected\n")
    ex_clocks = sum(int(res[i]["timing"]["clocks_simulated"]) for i in EXPORT_CPU_S)
    print("| exporter | 3 busy traces (CPU s) | their clocks | 408 projects, projected (CPU h) |")
    print("| --- | ---: | ---: | ---: |")
    for k, name in enumerate(("the study's export from VGCH v2", "vgacap-export on VGCH v2")):
        s = sum(v[k] for v in EXPORT_CPU_S.values())
        print(f"| {name} | {s:,.1f} | {ex_clocks:,} | {s / ex_clocks * clocks_all / 3600:,.1f} |")
    print()

    # 2. Stores and PNGs, and what tb-v1 adds after sharing.
    dn = [json.loads(line) for line in HERE.joinpath("logs/derive-now.jsonl").read_text().splitlines()]
    written = {(d["id"], d["samplers"]): d["pngs_written"] for d in dn}
    sums = {"c_store": 0, "t_store": 0, "c_png": 0, "t_png_added": 0, "c_files": 0, "t_files_added": 0}
    print("## Stores and PNGs, pilot\n")
    print("| project | distinct frames | centre-v1 store (bytes) | tb-v1 store (bytes) | centre-v1 PNGs (bytes) "
          "| centre-v1 PNG files | PNGs written, both samplers | tb-v1 PNG files added | tb-v1 PNG bytes added |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for i in IDS:
        s = raw(i)["sizes"]["samplers"]
        c, t = s["centre-v1"], s["tb-v1"]
        added = written[(i, "both")] - written[(i, "centre")]
        t_bytes = t["png_bytes"] * added // t["png_files"]
        sums["c_store"] += c["store"]
        sums["t_store"] += t["store"]
        sums["c_png"] += c["png_bytes"]
        sums["c_files"] += c["png_files"]
        sums["t_png_added"] += t_bytes
        sums["t_files_added"] += added
        print(f"| {i} | {res[i]['timing']['distinct_frames']:,} | {c['store']:,} | {t['store']:,} | "
              f"{c['png_bytes']:,} | {c['png_files']:,} | {written[(i, 'both')]:,} | {added:,} | {t_bytes:,} |")
    print()
    print("## Stores and PNGs, projected by distinct frames\n")
    print("| quantity | pilot | per distinct frame | 408 projects, projected |")
    print("| --- | ---: | ---: | ---: |")
    for key, label, unit in (("c_store", "centre-v1 store (GB)", "bytes"), ("t_store", "tb-v1 store (GB)", "bytes"),
                             ("c_png", "centre-v1 PNGs (GB)", "bytes"), ("t_png_added", "tb-v1 PNG bytes added (GB)", "bytes"),
                             ("c_files", "centre-v1 PNG files", "files"), ("t_files_added", "tb-v1 PNG files added", "files")):
        per = sums[key] / distinct_pilot
        proj = per * distinct_all
        shown = f"{proj:,.0f}" if unit == "files" else gb(proj)
        pilot = f"{sums[key]:,}"
        print(f"| {label} | {pilot} | {per:,.3f} | {shown} |")
    print()

    # 3. Run time per job, and the re-run.
    print("## Run time per job\n")
    print("| project | reference run (s) | pilot job (s) | pilot derive (s) | derive now, both (s) | ratio |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    old_p = new_p = new_now = 0.0
    wall_now = {d["id"]: d["wall_seconds"] for d in dn if d["samplers"] == "both"}
    for i in IDS:
        old = sum(res[i]["timings"].get(k) or 0 for k in OLD_STAGES)
        t = raw(i)["result"]["timings"]
        new = sum(t.get(k) or 0 for k in NEW_STAGES)
        now = new - (t.get("derive") or 0) + wall_now[i]
        old_p, new_p, new_now = old_p + old, new_p + new, new_now + now
        print(f"| {i} | {old:,.1f} | {new:,.1f} | {t.get('derive') or 0:,.1f} | {wall_now[i]:,.1f} | {new / old:.2f} |")
    f_pilot, f_now = new_p / old_p, new_now / old_p
    print(f"| all 11 | {old_p:,.1f} | {new_p:,.1f} | - | - | {f_pilot:.2f} |\n")
    old_all = [sum(r["timings"].get(k) or 0 for k in OLD_STAGES) for r in res.values() if r.get("timings")]
    longest = max(old_all)
    print("| quantity | value |")
    print("| --- | ---: |")
    print(f"| results with timings | {len(old_all)} |")
    print(f"| their reference-run job time (h) | {sum(old_all) / 3600:,.1f} |")
    print(f"| longest reference-run job (s) | {longest:,.1f} |")
    print(f"| pilot factor, as run | {f_pilot:.3f} |")
    print(f"| pilot factor, derive at this commit | {f_now:.3f} |")
    for label, f in (("as run", f_pilot), ("derive at this commit", f_now)):
        total = sum(old_all) * f
        print(f"| projected job time, {label} (h) | {total / 3600:,.1f} |")
        print(f"| projected wall at {JOBS} jobs, {label} (h) | {max(total / JOBS, longest * f) / 3600:,.1f} |")
    print()

    # 4. Post-simulation CPU, then and now.
    print("## Post-simulation CPU, then and now\n")
    print("| project | CPU without (s) | compressor (s) | budget (s) | pilot derive (s) | post, pilot (%) "
          "| derive now, both (s) | post now, both (%) | derive now, centre-v1 (s) | post now, centre-v1 (%) |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    cpu = {(d["id"], d["samplers"]): d["cpu_seconds"] for d in dn}
    for i in IDS:
        r = raw(i)
        runs = [x for x in r["runs"] if x.get("time")]
        c_no = mean([x["time"]["cpu_s"] for x in runs if not x["traced"]])
        c_tr = mean([x["time"]["cpu_s"] for x in runs if x["traced"]])
        comp = c_tr - c_no
        d0 = r["result"]["derive_cpu_seconds"]
        b, c = cpu[(i, "both")], cpu[(i, "centre")]
        print(f"| {i} | {c_no:,.1f} | {comp:.1f} | {0.05 * c_no:.1f} | {d0:.1f} | {(comp + d0) / c_no * 100:.1f} | "
              f"{b:.1f} | {(comp + b) / c_no * 100:.1f} | {c:.1f} | {(comp + c) / c_no * 100:.1f} |")
    print()


main()
