"""Side-by-side trace bench: per-pair overheads and medians, as measurements.md tables.

Usage: uv run docs/reports/2026-11-pilot/bench_summary.py PROJECT=LOG ... (logs in bench/)  (a LOG line: [id] round=N LABEL rc=0 wall=W cpu=C ...)
Pairs, run at the same moment: (notraceA, traceA), (notraceB, traceB), (notrace, L1).
"""
import re
import statistics
import sys

PAIRS = (("notraceA", "traceA"), ("notraceB", "traceB"), ("notrace", "L1"))
rows = []
for spec in sys.argv[1:]:
    name, _, path = spec.partition("=")
    walls: dict[tuple[int, str], float] = {}
    for line in open(path):
        m = re.search(r"(?:(\S+) )?round=(\d+) (\S+) rc=0 wall=([\d.]+)", line)
        if m and (m.group(1) is None or m.group(1).endswith(name)):
            walls[(int(m.group(2)), m.group(3))] = float(m.group(4))
    pairs = []
    for r in sorted({k[0] for k in walls}):
        for a, b in PAIRS:
            if (r, a) in walls and (r, b) in walls:
                pairs.append((r, a[-1] if a != "notrace" else "-", walls[(r, a)], walls[(r, b)]))
    rows.append((name, pairs))

print("| project | round | pair | without (s) | with (s) | overhead (%) |")
print("| --- | ---: | --- | ---: | ---: | ---: |")
for name, pairs in rows:
    for r, p, a, b in pairs:
        print(f"| {name} | {r} | {p} | {a:.1f} | {b:.1f} | {(b / a - 1) * 100:+.1f} |")
print()
print("| project | pairs | median overhead (%) | lowest (%) | highest (%) | pairs span 5% | verdict |")
print("| --- | ---: | ---: | ---: | ---: | --- | --- |")
for name, pairs in rows:
    ov = [(b / a - 1) * 100 for _, _, a, b in pairs]
    med = statistics.median(ov)
    verdict = "over" if med > 5 else "within"
    spans = "yes" if min(ov) <= 5 < max(ov) else "no"
    print(f"| {name} | {len(ov)} | {med:+.1f} | {min(ov):+.1f} | {max(ov):+.1f} | {spans} | {verdict} |")
