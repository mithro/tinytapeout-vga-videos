#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run job.py for many projects in parallel. Runs on the host, usually inside tmux.

Usage: queue.py --targets targets.json --root ~/ttvga --jobs 40 [--only tt08,ttsky26a/tt_um_x] [--redo]

Projects that already have work/<shuttle>/<macro>/result.json are skipped
unless --redo is given, so the queue can be killed and restarted at any time.
Progress goes to <root>/queue.log and <root>/queue-state.json.
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def selected(target: dict, only: list[str]) -> bool:
    return not only or target["shuttle"] in only or target["id"] in only


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", type=Path, default=HERE / "targets.json")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only", default="", help="comma separated shuttles or <shuttle>/<macro> ids")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many jobs (0 = all)")
    ap.add_argument("--redo", action="store_true", help="rerun projects that already have a result")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    only = [s for s in args.only.split(",") if s]
    targets = [t for t in json.loads(args.targets.read_text())["targets"] if selected(t, only)]
    pending = []
    for t in targets:
        done = args.root / "work" / t["shuttle"] / t["macro"] / "result.json"
        if args.redo or not done.exists():
            pending.append(t)
    if args.limit:
        pending = pending[: args.limit]

    log = (args.root / "queue.log").open("a")
    state_path = args.root / "queue-state.json"
    lock = threading.Lock()
    state = {"started": now(), "jobs": args.jobs, "selected": len(targets), "pending": len(pending),
             "running": [], "done": 0, "failed": 0, "finished": None, "pid": None}
    import os
    state["pid"] = os.getpid()

    def write_state() -> None:
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        tmp.rename(state_path)

    def say(msg: str) -> None:
        with lock:
            log.write(f"{now()} {msg}\n")
            log.flush()

    stop = threading.Event()

    def on_signal(signum, frame):
        say(f"signal {signum}: finishing running jobs, starting no more")
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    def run_one(t: dict) -> tuple[str, int]:
        with lock:
            state["running"].append(t["id"])
            write_state()
        cmd = [sys.executable, str(HERE / "job.py"), "--targets", str(args.targets), "--id", t["id"],
               "--root", str(args.root), "--seconds", str(args.seconds), "--timeout", str(args.timeout)]
        t0 = time.monotonic()
        p = subprocess.run(cmd, capture_output=True, text=True)
        with lock:
            state["running"].remove(t["id"])
            state["done"] += 1
            if p.returncode != 0:
                state["failed"] += 1
            write_state()
        say(f"{t['id']}: {(p.stdout or p.stderr).strip().splitlines()[-1] if (p.stdout or p.stderr).strip() else 'no output'}"
            f" ({time.monotonic() - t0:.0f}s)")
        return t["id"], p.returncode

    say(f"queue start: {len(pending)} pending of {len(targets)} selected, {args.jobs} jobs")
    write_state()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = []
        for t in pending:
            if stop.is_set():
                break
            futures.append(pool.submit(run_one, t))
            # Submit gradually so a stop request does not leave hundreds queued.
            while len([f for f in futures if not f.done()]) >= args.jobs and not stop.is_set():
                time.sleep(1)
        for f in as_completed(futures):
            f.result()
    state["finished"] = now()
    write_state()
    say(f"queue finished: {state['done']} done, {state['failed']} with errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
