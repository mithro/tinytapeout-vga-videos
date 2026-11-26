#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""List each project's result.json for `tt-vga collect`. Runs on the host.

Usage: list_results.py WORK   (WORK is ~/ttvga/work)

For every WORK/<shuttle>/<macro>/result.json, one JSON line on stdout:

    {"id": "<shuttle>/<macro>", "harness": bool, "dropped": bool}

`harness` is whether the parsed object has a `harness` key (only results
written by the raw-traces job.py do), and `dropped` is its `tb_v1.dropped`.
The file is parsed, never searched as text: a log tail inside it can hold the
word "harness". A file that does not parse gives `{"id", "error"}` instead,
and the error is also written to stderr.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def entry(path: Path, rid: str) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return {"id": rid, "error": f"{path}: {e}"}
    if not isinstance(result, dict):
        return {"id": rid, "error": f"{path}: not a JSON object"}
    tb_v1 = result.get("tb_v1")
    return {"id": rid, "harness": "harness" in result,
            "dropped": isinstance(tb_v1, dict) and tb_v1.get("dropped") is True}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: list_results.py WORK", file=sys.stderr)
        return 2
    work = Path(argv[1])
    for path in sorted(work.glob("*/*/result.json")):
        e = entry(path, f"{path.parent.parent.name}/{path.parent.name}")
        if "error" in e:
            print(f"list_results: error: {e['error']}", file=sys.stderr)
        print(json.dumps(e), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
