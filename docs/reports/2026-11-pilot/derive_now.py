"""derive's CPU at this commit on one pilot project's published trace (plan Task 22).

    TTVGA_DEV_TOOLS=... uv run docs/reports/2026-11-pilot/derive_now.py FRAMES_ROOT OUT ID SAMPLERS

FRAMES_ROOT is host.toml's frames_root, read only: only `<FRAMES_ROOT>/<id>/<stem>_trace.vgch.zst` is
opened. OUT is a scratch directory; the derive writes into `OUT/<stem>-<SAMPLERS>/`, which must not
exist. SAMPLERS is `centre` (centre-v1 alone, the default after the re-run) or `both` (as Task 23 runs).

It calls `derive.derive`, the job's own derive step, with the dev tools' vgacap-sample and tracetool
and no centre-window override (none of the 11 has one), and prints one JSON line: the id, the samplers,
derive's `cpu_seconds` (its own CPU plus its children's), its wall time, and the PNGs it wrote and
hard-linked. Each call is its own process, so the children's CPU is this project's alone.
"""
import json
import sys
import time
from pathlib import Path

from ttvga import devtools
from ttvga.harness import derive, vgacap_path

frames_root, out_root, pid, which = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
if which not in ("centre", "both"):
    sys.exit(f"SAMPLERS must be centre or both, not {which!r}")
dev = devtools.paths()
vgacap_path.add_src(dev.vgacap_src)
stem = pid.replace("/", "_")
trace = frames_root / pid / f"{stem}_trace.vgch.zst"
out = out_root / f"{stem}-{which}"
out.mkdir(parents=True)
tools = derive.Tools(vgacap_sample=dev.vgacap_sample, tracetool=dev.tracetool)
t0 = time.monotonic()
res = derive.derive(trace, out, stem, tb_v1=which == "both", centre_window=None, store_level=None,
                    tools=tools, log=out / "derive.log", tb_hashes=None)
wall = time.monotonic() - t0
print(json.dumps({
    "id": pid, "samplers": which, "cpu_seconds": round(res.cpu_seconds, 2), "wall_seconds": round(wall, 2),
    "pngs_written": res.pngs_written, "pngs_linked": res.pngs_linked, "error": res.error,
    "distinct": {s: v.get("distinct_frames") for s, v in res.samplers.items()},
}))
