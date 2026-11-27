"""Project the upload's file count and listing time to all committed projects (Task 20 fix round 1).

    uv run scripts/pilot_measure.py --upload-listing /var/lib/data-upload/rsync.log --last 80 > tmp/listing.md
    uv run docs/reports/2026-11-pilot/upload_projection.py tmp/listing.md

Per project: 9 entries with centre-v1 alone, 17 with both samplers (counted in the pilot's frames
tree), plus one PNG per distinct frame per sampler; plus one directory per shuttle and the root.
Listing time: the pilot's mean before plus files times the per-file cost (from 39,588 added files).
"""
import json
import re
import statistics
import sys
from pathlib import Path

results = sorted(Path("data/results").glob("*/*/result.json"))
distinct, published = [], 0
for p in results:
    t = json.loads(p.read_text()).get("timing") or {}
    if t.get("status"):            # simulated: published (a no-picture run publishes frames: 0)
        published += 1
    if t.get("distinct_frames") is not None:
        distinct.append(int(t["distinct_frames"]))
shuttles = {p.parts[2] for p in results}
log = Path(sys.argv[1]).read_text()
rows = re.findall(r"\| (2026-11-27T\d\d:\d\d:\d\d) \| ([\d,]+) \| (\d+) \|", log)
before = [int(d) for t, n, d in rows if n.replace(",", "") in ("62991", "62993")]
after = [int(d) for t, n, d in rows if n.replace(",", "") == "102579"]
added = 102579 - 62991
mb, ma = statistics.mean(before), statistics.mean(after)
print(f"results {len(results)}, published {published}, with frames {len(distinct)}, shuttles {len(shuttles)}, distinct sum {sum(distinct):,}, "
      f"mean {statistics.mean(distinct):,.0f}, median {statistics.median(distinct):,.0f}")
print(f"before: {len(before)} runs, mean {mb:.2f} s; after: {len(after)} runs, mean {ma:.2f} s")
for label, delta in (("central", ma - mb), ("low", ma - mb - 1.0), ("high", ma - mb + 1.0)):
    per = delta / added
    for name, fixed, k in (("both samplers", 17, 2), ("centre-v1 only", 9, 1)):
        files = published * fixed + k * sum(distinct) + len(shuttles) + 1
        print(f"{label}: per file {per * 1e3:.3f} ms; {name}: files {files:,}, listing {mb + files * per:.0f} s")
