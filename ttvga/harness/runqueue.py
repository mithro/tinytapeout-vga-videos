#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run job.py for many projects in parallel, each in its own systemd user scope. Runs on the host, inside tmux.

Usage: runqueue.py --targets targets.json --root ~/ttvga --jobs 24 [--only tt08,ttsky26a/tt_um_x]
                   [--redo | --redo-unless-harness VERSION] [--rederive] [--tb-v1 | --drop-tb-v1]

Which projects run:
- by default, those without work/<shuttle>/<macro>/result.json, so the queue can be killed and
  restarted at any time; `--redo` runs every selected project;
- `--rederive` takes only projects whose result.json has a `trace`, and runs `job.py --rederive`;
- `--redo-unless-harness VERSION` runs a project unless its result.json has a `trace`,
  `harness == VERSION` and, with `--tb-v1`, `tb_v1_check == "match"` (a re-derive cannot match,
  having no tb.cpp hashes: there `tb_v1.state == "current"` instead). A crashed re-run restarts
  where it stopped.

Each job runs as `systemd-run --user --scope ... -p MemoryMax -p CPUQuota -p TasksMax -p
RuntimeMaxSec -- python job.py ...`. The scope limits resources only, not file access (the user
account does that). A preflight checks that the user manager can make scopes; if it cannot, the
queue stops there: there is no unconfined fallback. The user needs linger
(`loginctl enable-linger`) for the scopes to outlive the login session that started tmux.

Before each job the queue waits while the root volume has less than host.toml's
`min_free_root_gb` free. Progress goes to <root>/queue.log and <root>/queue-state.json.

`--test-hooks` is refused (exit 2): only job.py's own tests build tb.cpp's test hooks.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hostconf  # noqa: E402

# job.py --grace, passed explicitly so the scope's runtime limit and the job agree.
GRACE = 120.0
FREE_SPACE_POLL = 60
SCOPE_MEMORY = "6G"
SCOPE_CPU = "200%"
SCOPE_TASKS = 64
# The bounded stages of one job besides simulate and derive (Task 9's worst case), in seconds:
# 9 probes of 300 + 10 s, fetch, build (with its --timing retry), encode, tool versions,
# and an allowance for publish, whose rsync, cp -al and flock have no limit of their own.
PROBES, FETCH, BUILD, ENCODE, TOOL_VERSIONS, PUBLISH = 9 * 310, 2880, 2 * 1800, 16000, 2 * 30, 3600
_UNIT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_.-")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def selected(target: dict, only: list[str]) -> bool:
    return not only or target["shuttle"] in only or target["id"] in only


def runtime_max_sec(timeout: float, grace: float) -> int:
    """The scope's RuntimeMaxSec: the worst job, rounded up to whole hours.

    Simulation T + 9 probes + the re-run T + G, derive's own T, then the other stages
    (see the constants). At T = 10800, G = 120 the worst job is 61,450 s, so 18 h.
    """
    worst = 3 * timeout + grace + PROBES + FETCH + BUILD + ENCODE + TOOL_VERSIONS + PUBLISH
    return int(math.ceil(worst / 3600) * 3600)


def scope_unit(shuttle: str, macro: str) -> str:
    """`ttvga-job-<shuttle>-<macro>`, with anything a unit name cannot hold escaped as \\xNN."""
    def esc(s: str) -> str:
        return "".join(c if c in _UNIT_CHARS else "".join(f"\\x{b:02x}" for b in c.encode()) for c in s)
    return f"ttvga-job-{esc(shuttle)}-{esc(macro)}"


def job_command(t: dict, args: argparse.Namespace) -> list[str]:
    """The job's command: job.py under the queue's own interpreter, inside a systemd user scope."""
    scope = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--unit", scope_unit(t["shuttle"], t["macro"]),
             "-p", f"MemoryMax={args.scope_memory}", "-p", f"CPUQuota={args.scope_cpu}",
             "-p", f"TasksMax={SCOPE_TASKS}", "-p", f"RuntimeMaxSec={runtime_max_sec(args.timeout, GRACE)}"]
    job = [sys.executable, str(HERE / "job.py"), "--targets", str(args.targets), "--id", t["id"],
           "--root", str(args.root), "--seconds", str(args.seconds), "--timeout", str(args.timeout),
           "--grace", str(GRACE)]
    for flag in ("rederive", "tb_v1", "drop_tb_v1"):
        if getattr(args, flag):
            job.append("--" + flag.replace("_", "-"))
    return scope + ["--"] + job


def preflight() -> str | None:
    """None when the user manager makes scopes; otherwise what went wrong."""
    cmd = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "true"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"systemd-run --user --scope true failed: {e}"
    if p.returncode != 0:
        out = (p.stderr or p.stdout).strip() or "no output"
        return f"systemd-run --user --scope true failed (exit {p.returncode}): {out}"
    return None


def linger_note() -> str | None:
    """A warning when this user has no linger: its user manager, and every scope, ends with the last login."""
    user = os.environ.get("USER") or str(os.getuid())
    try:
        p = subprocess.run(["loginctl", "show-user", user, "-p", "Linger", "--value"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"warning: cannot ask loginctl about linger: {e}"
    if p.returncode != 0 or p.stdout.strip() != "yes":
        said = (p.stdout.strip() or p.stderr.strip() or f"exit {p.returncode}")
        return (f"warning: linger is not on for {user} ({said}): the job scopes end when the last login "
                f"session does")
    return None


def wait_for_free_space(root: Path, need_gb: float, say, *, stop: threading.Event | None = None,
                        sleep=time.sleep) -> bool:
    """Wait while `root`'s volume has less than `need_gb` GB free, saying so once a minute.

    Returns False when `stop` was set while waiting.
    """
    while (free := shutil.disk_usage(root).free) < need_gb * 1e9:
        if stop is not None and stop.is_set():
            return False
        say(f"waiting for free space: {free / 1e9:.1f} GB free, need {need_gb:g}")
        sleep(FREE_SPACE_POLL)
    return not (stop is not None and stop.is_set())


def _result(root: Path, t: dict) -> dict | None:
    path = root / "work" / t["shuttle"] / t["macro"] / "result.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}   # unreadable: treated as not done


def is_done(result: dict | None, version: str, *, tb_v1: bool, rederive: bool) -> bool:
    """`--redo-unless-harness`: this result already comes from harness `version` (and tb-v1, if asked)."""
    if not result or not result.get("trace") or result.get("harness") != version:
        return False
    if not tb_v1:
        return True
    if rederive:
        return (result.get("tb_v1") or {}).get("state") == "current" and result.get("tb_v1_check") == "not-run"
    return result.get("tb_v1_check") == "match"


def select_pending(targets: list[dict], args: argparse.Namespace) -> list[dict]:
    pending = []
    for t in targets:
        result = _result(args.root, t)
        if args.rederive and not (result and result.get("trace")):
            continue
        if args.redo_unless_harness is not None:
            if is_done(result, args.redo_unless_harness, tb_v1=args.tb_v1, rederive=args.rederive):
                continue
        elif not (args.redo or args.rederive) and result is not None:
            continue
        pending.append(t)
    return pending


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", type=Path, default=HERE / "targets.json")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only", default="", help="comma separated shuttles or <shuttle>/<macro> ids")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many jobs (0 = all)")
    redo = ap.add_mutually_exclusive_group()
    redo.add_argument("--redo", action="store_true", help="rerun projects that already have a result")
    redo.add_argument("--redo-unless-harness", metavar="VERSION",
                      help="rerun unless result.json has a trace from this HARNESS_VERSION (and, with --tb-v1, a match)")
    ap.add_argument("--rederive", action="store_true", help="job.py --rederive the projects whose result.json has a trace")
    tb = ap.add_mutually_exclusive_group()
    tb.add_argument("--tb-v1", action="store_true", help="pass --tb-v1 to each job")
    tb.add_argument("--drop-tb-v1", action="store_true", help="pass --drop-tb-v1 to each job")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--scope-memory", default=SCOPE_MEMORY, help=f"each job's MemoryMax (default {SCOPE_MEMORY})")
    ap.add_argument("--scope-cpu", default=SCOPE_CPU, help=f"each job's CPUQuota (default {SCOPE_CPU}%)")  # %% for argparse
    ap.add_argument("--test-hooks", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.test_hooks:
        ap.error("--test-hooks is for job.py's own tests: the queue never builds tb.cpp's test hooks")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    only = [s for s in args.only.split(",") if s]
    targets = [t for t in json.loads(args.targets.read_text())["targets"] if selected(t, only)]

    log = (args.root / "queue.log").open("a")
    lock = threading.Lock()

    def say(msg: str) -> None:
        with lock:
            log.write(f"{now()} {msg}\n")
            log.flush()

    def refuse(msg: str) -> int:
        say(f"queue refused: {msg}")
        print(f"runqueue: {msg}", file=sys.stderr)
        return 1

    try:
        conf = hostconf.load(args.root)
    except (hostconf.ConfigError, OSError) as e:
        return refuse(f"host.toml: {e}")
    if (error := preflight()):
        return refuse(error)
    if (note := linger_note()):
        say(note)

    pending = select_pending(targets, args)
    if args.limit:
        pending = pending[: args.limit]

    state_path = args.root / "queue-state.json"
    state = {"started": now(), "jobs": args.jobs, "selected": len(targets), "pending": len(pending),
             "running": [], "done": 0, "failed": 0, "finished": None, "pid": os.getpid()}

    def write_state() -> None:
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        tmp.rename(state_path)

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
        t0 = time.monotonic()
        p = subprocess.run(job_command(t, args), capture_output=True, text=True)
        with lock:
            state["running"].remove(t["id"])
            state["done"] += 1
            if p.returncode != 0:
                state["failed"] += 1
            write_state()
        text = (p.stdout or p.stderr).strip()
        say(f"{t['id']}: {text.splitlines()[-1] if text else 'no output'} (exit {p.returncode}, "
            f"{time.monotonic() - t0:.0f}s)")
        return t["id"], p.returncode

    say(f"queue start: {len(pending)} pending of {len(targets)} selected, {args.jobs} jobs"
        + (", rederive" if args.rederive else "") + (", tb-v1" if args.tb_v1 else "")
        + (", drop tb-v1" if args.drop_tb_v1 else ""))
    write_state()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = []
        for t in pending:
            if stop.is_set():
                break
            if not wait_for_free_space(args.root, conf.min_free_root_gb, say, stop=stop):
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
