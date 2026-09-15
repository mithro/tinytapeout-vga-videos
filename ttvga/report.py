# SPDX-License-Identifier: Apache-2.0
"""Write docs/status.md and data/status.json from the collected, analysed results."""

from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime, timezone

from ttvga import DATA_DIR, ROOT
from ttvga.analyze import SUCCESS, analyze_all
from ttvga.targets import load_targets

STATUS_MD = ROOT / "docs" / "status.md"
STATUS_JSON = DATA_DIR / "status.json"
VERDICT_ORDER = ["ok", "static", "barely-moving", "partial", "blank", "no-sync", "bad-timing", "unstable-sync",
                 "sim-timeout",
                 "sim-crashed", "build-failed", "fetch-failed", "encode-failed", "error", "skipped"]


def run(args: argparse.Namespace) -> int:
    targets = load_targets()
    results = {r["id"]: r for r in analyze_all()}
    shuttles = list(dict.fromkeys(t["shuttle"] for t in targets))
    per_shuttle: dict[str, collections.Counter] = {s: collections.Counter() for s in shuttles}
    total = collections.Counter()
    for t in targets:
        r = results.get(t["id"])
        v = r["verdict"] if r else "pending"
        per_shuttle[t["shuttle"]][v] += 1
        total[v] += 1
    done = sum(n for v, n in total.items() if v != "pending")
    succeeded = sum(n for v, n in total.items() if v in SUCCESS)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    video_bytes = sum(v.get("bytes", 0) for r in results.values() for v in (r.get("videos") or {}).values())
    lines = [
        "# Status", "",
        f"Generated {generated} by `tt-vga report`. Do not edit by hand.", "",
        f"- Targets: {len(targets)}",
        f"- Attempted: {done}",
        f"- Videos produced: {succeeded}",
        f"- Pending: {total['pending']}",
        f"- Video, poster and contact sheet size on the simulation host: {video_bytes / 1e9:.0f} GB", "",
        "## Verdicts", "",
        "| Verdict | Count |", "| --- | ---: |",
    ]
    for v in VERDICT_ORDER + ["pending"]:
        if total[v]:
            lines.append(f"| {v} | {total[v]} |")
    cols = [v for v in VERDICT_ORDER + ["pending"] if total[v]]
    lines += ["", "## Per shuttle", "", "| Shuttle | Targets | " + " | ".join(cols) + " |",
              "| --- | ---: | " + " | ".join("---:" for _ in cols) + " |"]
    for s in shuttles:
        c = per_shuttle[s]
        lines.append(f"| {s} | {sum(c.values())} | " + " | ".join(str(c[v] or "") for v in cols) + " |")
    failures = [r for r in results.values() if r["verdict"] not in SUCCESS and r["verdict"] != "skipped"]
    if failures:
        lines += ["", "## Not yet producing a video", "", "| Project | Verdict | Reason |", "| --- | --- | --- |"]
        for r in sorted(failures, key=lambda r: (VERDICT_ORDER.index(r["verdict"]) if r["verdict"] in VERDICT_ORDER else 99, r["id"])):
            reason = r["reason"].replace("|", "/")
            lines.append(f"| {r['id']} | {r['verdict']} | {reason} |")
    STATUS_MD.write_text("\n".join(lines) + "\n")
    STATUS_JSON.write_text(json.dumps({
        "generated": generated, "targets": len(targets), "attempted": done, "succeeded": succeeded,
        "verdicts": dict(total),
        "projects": {r["id"]: {"verdict": r["verdict"], "reason": r["reason"],
                               "videos": sorted((r.get("videos") or {}).keys())} for r in results.values()},
    }, indent=2, sort_keys=True) + "\n")
    print(f"{done} attempted, {succeeded} with videos, {total['pending']} pending -> {STATUS_MD.relative_to(ROOT)}")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("report", help="write docs/status.md and data/status.json")
    p.set_defaults(func=run)
