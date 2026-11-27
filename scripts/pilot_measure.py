#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The pilot (plan Task 20, rollout step 2): measure the budget on a few projects.

    uv run scripts/pilot_measure.py --host big --ids FILE --out docs/reports/2026-11-pilot/raw \\
        --jobs 11 --timeout 10800 [--no-wait | --pull-only] >> tmp/t20.log 2>&1
    uv run scripts/pilot_measure.py --report docs/reports/2026-11-pilot/raw
    uv run scripts/pilot_measure.py --upload-listing /var/lib/data-upload/rsync.log [--last 5]

The local mode copies this file and a plan (the ids, each with its previous run's stage
times from `data/results/<id>/result.json`) to `~/ttvga/work/pilot/` on the host and starts
it there in the tmux session `ttvga-pilot`, under the pinned Python, logging to
`~/ttvga/work/pilot.log`. Then it waits for `raw/DONE` and pulls `raw/*.json` into `--out`.
Run it again to re-attach: it never starts a second pilot while the session exists or a
finished one is there.

On the host (`--on-host`) every project runs at once (up to `--jobs`), each in its own
systemd user scope with the queue's limits (runqueue.py: MemoryMax, CPUQuota, TasksMax,
OOMPolicy=continue). Inside it (`--on-host-project`), each under `/usr/bin/time -v`:
1. `job.py --tb-v1 --keep-build --timeout T`, which publishes to the frames subtree;
2. the kept `Vtop`, with the job's cwd and arguments (from sim.log), 4 times: without
   `--trace`, with, without, with; `--out` (so ffmpeg's capture.avi) in a scratch directory;
3. `vgacap-sample` alone on the published trace (copied to the root volume), with its
   default sampler and with both, with VGACAP_SAMPLE_DEBUG=1;
4. the published store, PNG and trace sizes (`du -b`: hard links counted once).
While a scope exists the coordinator polls it every 5 s: `du -sb` of the project's work and
pilot directories, and the scope's MemoryCurrent, MemoryPeak and TasksCurrent (`--collect`
removes the scope at its end, so they are read while it runs). It writes a progress line with
the remaining runs and the ETA to pilot.log once a minute.

The host part is standard library only, like the harness.
"""

from __future__ import annotations

import argparse
import atexit
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION = "ttvga-pilot"
SAMPLERS = ("centre-v1", "tb-v1")
POLL_S = 5
PROGRESS_S = 60
GRACE = 120
# Re-run order: interleaved so a drift in host load falls on both sides.
RERUNS = (False, True, False, True)
RUNS_PER_PROJECT = 1 + len(RERUNS)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Parsing (tested)
# ---------------------------------------------------------------------------

def _clock(text: str) -> float:
    secs = 0.0
    for part in text.strip().split(":"):
        secs = secs * 60 + float(part)
    return round(secs, 3)


def parse_time_v(text: str) -> dict:
    """GNU time -v's report: wall, user, sys and their sum (seconds), max RSS (kB), exit status, signal."""
    fields: dict[str, str] = {}
    sig = None
    for line in text.splitlines():
        if (m := re.match(r"Command terminated by signal (\d+)", line.strip())):
            sig = int(m.group(1))
            continue
        key, sep, value = line.strip().rpartition(": ")
        if sep:
            fields[key] = value
    try:
        user = float(fields["User time (seconds)"])
        sys_ = float(fields["System time (seconds)"])
        return {"wall_s": _clock(fields["Elapsed (wall clock) time (h:mm:ss or m:ss)"]), "user_s": user,
                "sys_s": sys_, "cpu_s": round(user + sys_, 2),
                "max_rss_kb": int(fields["Maximum resident set size (kbytes)"]),
                "exit_status": int(fields["Exit status"]), "signal": sig}
    except KeyError as e:
        raise ValueError(f"time -v report without {e}") from e


def model_argv(sim_log: str) -> list[str]:
    """The model's command line in a job's sim.log: the last `$ .../Vtop` line that is not a probe."""
    found = None
    for line in sim_log.splitlines():
        if not line.startswith("$ "):
            continue
        argv = line[2:].split(" ")
        if argv[0].endswith("/Vtop") and "--quiet" not in argv:
            found = argv
    if found is None:
        raise ValueError("no model command line in sim.log")
    return found


def rerun_argv(argv: list[str], out: str, trace: str | None) -> list[str]:
    """`argv` with `--out` replaced, and `--trace` (with the job's `--meta`s) only when `trace` is given."""
    base, metas = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "--trace"):
            i += 2
            continue
        if a == "--meta":
            # sim.log joins the command with spaces, and META values have spaces
            # ("simulator=Verilator 5.053 ..."): a value runs to the next option.
            j = i + 1
            while j < len(argv) and (j == i + 1 or not argv[j].startswith("--")):
                j += 1
            metas += ["--meta", " ".join(argv[i + 1:j])]
            i = j
            continue
        base.append(a)
        i += 1
    base += ["--out", out]
    if trace is not None:
        base += ["--trace", trace] + metas
    return base


_RSYNC = re.compile(r"^(\d{4})/(\d\d)/(\d\d) (\d\d:\d\d:\d\d) \[(\d+)\] (.*)$")


def parse_rsync_log(text: str) -> list[dict]:
    """The upload's complete runs: pid, start (host local time), end, duration_s, files (`Number of files`)."""
    open_runs: dict[int, dict] = {}
    runs = []
    for line in text.splitlines():
        m = _RSYNC.match(line)
        if not m:
            continue
        y, mo, d, hms, pid, msg = m.groups()
        when = datetime.fromisoformat(f"{y}-{mo}-{d}T{hms}")
        pid = int(pid)
        if msg.startswith("building file list"):
            open_runs[pid] = {"pid": pid, "start": when.isoformat(), "_t0": when, "files": None}
        elif pid in open_runs and (fm := re.match(r"Number of files: ([\d,]+)", msg)):
            open_runs[pid]["files"] = int(fm.group(1).replace(",", ""))
        elif pid in open_runs and msg.startswith("total size is"):
            r = open_runs.pop(pid)
            r["end"] = when.isoformat()
            r["duration_s"] = (when - r.pop("_t0")).total_seconds()
            runs.append(r)
    return runs


def redact(text: str, paths: dict[str, str]) -> str:
    """`text` with each host path (host.toml's directories, the home) replaced by its placeholder.

    The repository never names a host path (Global Constraints); the longest path goes first.
    """
    for path in sorted(paths, key=len, reverse=True):
        text = text.replace(path, paths[path])
    return text


def min_free_root_gb(peak_bytes: float) -> int:
    """Step 2's rule: 24 jobs times the peak, times 2, in GB (1e9), rounded up to 10."""
    return int(math.ceil(round(24 * peak_bytes / 1e9 * 2, 6) / 10) * 10)


def eta(plan: dict[str, list[float]], state: dict[str, dict]) -> tuple[int, float]:
    """(runs left, seconds left): the projects run in parallel, so the slowest one sets the end.

    `plan[id]` is the expected seconds of each run; `state[id]` its `done` runs and the
    seconds `elapsed_in_phase` of the one running.
    """
    runs, longest = 0, 0.0
    for pid, expected in plan.items():
        st = state.get(pid, {"done": 0, "elapsed_in_phase": 0.0})
        done = min(st["done"], len(expected))
        runs += len(expected) - done
        left = sum(expected[done:])
        if done < len(expected):
            left -= min(st["elapsed_in_phase"], expected[done])
        longest = max(longest, left)
    return runs, longest


# ---------------------------------------------------------------------------
# The budget tables (tested)
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _split(raw: dict, key: str) -> tuple[list[float], list[float]]:
    runs = [r for r in raw["runs"] if r.get("time")]
    return ([r["time"][key] for r in runs if not r["traced"]], [r["time"][key] for r in runs if r["traced"]])


def recording_row(raw: dict) -> dict:
    no, tr = _split(raw, "wall_s")
    w_no, w_tr = _mean(no), _mean(tr)
    clocks = raw["result"]["trace"]["clocks"]
    pct = (w_tr - w_no) / w_no * 100
    return {"walls_without": no, "walls_with": tr, "wall_without": w_no, "wall_with": w_tr,
            "overhead_pct": pct, "ns_per_clock": (w_tr - w_no) / clocks * 1e9, "clocks": clocks, "ok": pct <= 5}


def postsim_row(raw: dict) -> dict:
    no, tr = _split(raw, "cpu_s")
    c_no, c_tr = _mean(no), _mean(tr)
    comp = c_tr - c_no
    derive = raw["result"]["derive_cpu_seconds"]
    post = comp + derive
    pct = post / c_no * 100
    return {"cpu_without": c_no, "cpu_with": c_tr, "compressor_cpu_s": comp, "derive_cpu_s": derive,
            "post_cpu_s": post, "post_pct": pct, "budget_s": 0.05 * c_no, "ok": pct <= 5}


def _mib(x: float | None) -> str:
    """Bytes as MiB (2**20): time -v's max RSS is in KiB, MemoryPeak in bytes."""
    return "-" if x is None else f"{x / 2**20:,.0f}"


def _kb(x: float | None) -> str:
    return "-" if x is None else f"{x / 1e3:,.0f}"


def _gb(x: float | None) -> str:
    return "-" if x is None else f"{x / 1e9:.2f}"


def _n(x: int | None) -> str:
    return "-" if x is None else f"{x:,}"


def _sec(x: float) -> str:
    return f"{x:.1f}"


def _yes(ok: bool) -> str:
    return "yes" if ok else "**no**"


def memory_row(raw: dict) -> dict:
    rss = [r["time"]["max_rss_kb"] * 1024 for r in raw["runs"] if r.get("time")]
    samples = {s["variant"]: s["time"]["max_rss_kb"] * 1024 for s in raw.get("samples", []) if s.get("time")}
    scope = raw.get("scope") or {}
    return {"job_rss": raw["job"]["time"]["max_rss_kb"] * 1024 if raw["job"].get("time") else None,
            "model_rss": max(rss) if rss else None, "sample_default_rss": samples.get("default"),
            "sample_both_rss": samples.get("both"), "scope_peak": scope.get("memory_peak"),
            "tasks_peak": scope.get("tasks_peak")}


def root_row(raw: dict) -> dict:
    poll = raw.get("poll") or {}
    job = poll.get("job") or {}
    others = [p.get("pilot_bytes_peak") or 0 for k, p in poll.items() if k != "job"]
    return {"job_peak": job.get("work_bytes_peak"), "scratch_peak": job.get("scratch_bytes_peak"),
            "rerun_peak": max(others) if others else None}


def report(raw_dir: Path) -> str:
    """measurements.md's tables, one per target, one row per project."""
    raws = [json.loads(p.read_text()) for p in sorted(Path(raw_dir).glob("*.json"))]
    raws = [r for r in raws if r.get("runs") and r.get("result") and r["result"].get("trace")]
    out = []
    out.append("## Recording\n")
    out.append("Target: `(wall with trace - wall without) / wall without` at most 5%. Mean of 2 runs each.\n")
    out.append("| project | wall without (s) | wall with (s) | overhead (%) | ns per clock | clocks | within 5% |")
    out.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in raws:
        x = recording_row(r)
        out.append(f"| {r['id']} | {_sec(x['wall_without'])} | {_sec(x['wall_with'])} | {x['overhead_pct']:.2f} | "
                   f"{x['ns_per_clock']:.1f} | {x['clocks']:,} | {_yes(x['ok'])} |")
    out.append("\n## Post-simulation CPU\n")
    out.append("Target: (compressor CPU + `derive_cpu_seconds`) / simulation CPU without the trace, at most 5%.\n")
    out.append("| project | CPU without (s) | CPU with (s) | compressor (s) | derive (s) | post (s) | budget (s) | "
               "post (%) | within 5% |")
    out.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in raws:
        x = postsim_row(r)
        out.append(f"| {r['id']} | {_sec(x['cpu_without'])} | {_sec(x['cpu_with'])} | {x['compressor_cpu_s']:.1f} | "
                   f"{x['derive_cpu_s']:.1f} | {x['post_cpu_s']:.1f} | {x['budget_s']:.1f} | {x['post_pct']:.2f} | "
                   f"{_yes(x['ok'])} |")
    out.append("\n## Memory per job\n")
    out.append("Max RSS from `time -v` (the largest single process), and the scope's MemoryPeak (all its processes "
               "and page cache), in MiB. `time -v` reports KiB.\n")
    out.append("| project | job max RSS | model max RSS | sample default max RSS | sample both max RSS | "
               "scope MemoryPeak | scope peak tasks |")
    out.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in raws:
        x = memory_row(r)
        out.append(f"| {r['id']} | {_mib(x['job_rss'])} | {_mib(x['model_rss'])} | {_mib(x['sample_default_rss'])} | "
                   f"{_mib(x['sample_both_rss'])} | {_mib(x['scope_peak'])} | {x['tasks_peak'] if x['tasks_peak'] is not None else '-'} |")
    out.append("\n## Root-volume peak per job\n")
    out.append("Peak `du -sb` of the project's work directory while job.py ran, polled every 5 s, in GB.\n")
    out.append("| project | work directory peak | scratch peak | pilot re-run directory peak |")
    out.append("| --- | ---: | ---: | ---: |")
    peaks = []
    for r in raws:
        x = root_row(r)
        if x["job_peak"] is not None:
            peaks.append(x["job_peak"])
        out.append(f"| {r['id']} | {_gb(x['job_peak'])} | {_gb(x['scratch_peak'])} | {_gb(x['rerun_peak'])} |")
    if peaks:
        peak = max(peaks)
        out.append(f"\nLargest peak {peak / 1e9:.2f} GB: 24 x {peak / 1e9:.2f} x 2 = {48 * peak / 1e9:.1f} GB, "
                   f"rounded up to 10: `min_free_root_gb = {min_free_root_gb(peak)}`.")
    done = Path(raw_dir) / "DONE"
    if done.is_file() and (m := re.search(r"root_free_min_bytes (\d+)", done.read_text())):
        out.append(f"\nRoot volume free, lowest seen by the 5 s polls during the pilot: {int(m.group(1)) / 1e9:,.0f} GB.")
    out.append("\n## Sizes\n")
    out.append("The published directory (`du -b`, hard links once), in kB (1,000 bytes).\n")
    out.append("| project | trace | centre-v1 store | tb-v1 store | centre-v1 PNGs | tb-v1 PNGs | centre-v1 PNG files | "
               "tb-v1 PNG files | whole directory |")
    out.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in raws:
        s = r.get("sizes") or {}
        sm = s.get("samplers") or {}

        def g(name, key, sm=sm):
            return (sm.get(name) or {}).get(key)
        out.append(f"| {r['id']} | {_kb(s.get('trace'))} | {_kb(g('centre-v1', 'store'))} | {_kb(g('tb-v1', 'store'))} | "
                   f"{_kb(g('centre-v1', 'png_bytes'))} | {_kb(g('tb-v1', 'png_bytes'))} | "
                   f"{_n(g('centre-v1', 'png_files'))} | {_n(g('tb-v1', 'png_files'))} | {_kb(s.get('total'))} |")
    out.append("\n## vgacap-sample alone\n")
    out.append("On the published trace, VGACAP_SAMPLE_DEBUG=1; and the job's derive from result.json.\n")
    out.append("| project | default wall (s) | default CPU (s) | both wall (s) | both CPU (s) | both debug | "
               "job derive wall (s) | job derive CPU (s) | frames | distinct frames |")
    out.append("| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |")
    for r in raws:
        sv = {s["variant"]: s for s in r.get("samples", []) if s.get("time")}
        d, b = sv.get("default"), sv.get("both")
        c = (r["result"].get("samplers") or {}).get("centre-v1") or {}
        out.append(f"| {r['id']} | {_sec(d['time']['wall_s']) if d else '-'} | {_sec(d['time']['cpu_s']) if d else '-'} | "
                   f"{_sec(b['time']['wall_s']) if b else '-'} | {_sec(b['time']['cpu_s']) if b else '-'} | "
                   f"{(b or {}).get('debug') or '-'} | {r['result']['timings'].get('derive', '-')} | "
                   f"{r['result']['derive_cpu_seconds']:.1f} | {_n(c.get('frames'))} | {_n(c.get('distinct_frames'))} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# On the host: one project, inside its scope
# ---------------------------------------------------------------------------

def _du(path: Path) -> int | None:
    if not path.exists():
        return None
    p = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True)
    try:
        return int(p.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def _timed(cmd: list[str], tfile: Path, log: Path, *, cwd: Path | None = None, env: dict | None = None) -> dict:
    """Run `cmd` under /usr/bin/time -v, appending its output to `log`. Returns rc and the parsed report."""
    with log.open("a") as f:
        f.write(f"\n{now()} $ {' '.join(cmd)}\n")
        f.flush()
        rc = subprocess.run(["/usr/bin/time", "-v", "-o", str(tfile)] + cmd, cwd=cwd, env=env, stdout=f,
                            stderr=subprocess.STDOUT).returncode
        f.write(f"{now()} [exit {rc}]\n")
    rec = {"rc": rc, "cmd": cmd}
    try:
        rec["time"] = parse_time_v(tfile.read_text())
    except (OSError, ValueError) as e:
        rec["time"] = None
        rec["time_error"] = str(e)
    return rec


def _phase(pdir: Path, index: int, name: str, say) -> None:
    tmp = pdir / "phase.tmp"
    tmp.write_text(json.dumps({"index": index, "name": name, "t0": time.time()}))
    tmp.rename(pdir / "phase")
    say(f"phase {index} {name}")


def on_host_project(args: argparse.Namespace) -> int:
    root = args.root
    targets = json.loads((root / "harness" / "targets.json").read_text())["targets"]
    target = next(t for t in targets if t["id"] == args.id)
    s, m = target["shuttle"], target["macro"]
    stem = f"{s}_{m}"
    work = root / "work" / s / m
    pdir = root / "work" / "pilot" / s / m
    pdir.mkdir(parents=True, exist_ok=True)
    log = pdir / "project.log"

    def say(msg: str) -> None:
        print(f"{now()} {args.id}: {msg}", flush=True)

    conf = tomllib.loads((root / "host.toml").read_text())
    published = Path(conf["frames_root"]) / s / m
    rec: dict = {"id": args.id, "started": now(), "host_load_start": os.getloadavg(), "nproc": os.cpu_count(),
                 "runs": [], "samples": [], "errors": []}
    try:
        _phase(pdir, 0, "job", say)
        job = [sys.executable, str(root / "harness" / "job.py"), "--targets", str(root / "harness" / "targets.json"),
               "--id", args.id, "--root", str(root), "--seconds", "60", "--timeout", str(args.timeout),
               "--grace", str(GRACE), "--tb-v1", "--keep-build"]
        rec["job"] = _timed(job, pdir / "job.time", log)
        try:
            rec["result"] = json.loads((work / "result.json").read_text())
        except (OSError, json.JSONDecodeError) as e:
            rec["errors"].append(f"result.json: {e}")
            rec["result"] = None
        say(f"job exit {rec['job']['rc']} error={(rec['result'] or {}).get('error')!r}")

        argv = model_argv((work / "sim.log").read_text(errors="replace"))
        cwd = work / "repo" / target.get("src_dir", "src")
        for k, traced in enumerate(RERUNS):
            _phase(pdir, 1 + k, f"rerun{k}-{'trace' if traced else 'notrace'}", say)
            out = pdir / f"run{k}"
            if out.exists():
                shutil.rmtree(out)
            out.mkdir()
            trace = out / f"{stem}_trace.vgch.zst"
            cmd = ["timeout", f"--kill-after={GRACE}", str(args.timeout)] + rerun_argv(
                argv, str(out), str(trace) if traced else None)
            r = _timed(cmd, pdir / f"run{k}.time", log, cwd=cwd)
            r.update(traced=traced, index=k, trace_bytes=trace.stat().st_size if trace.exists() else None,
                     capture_bytes=(out / "capture.avi").stat().st_size if (out / "capture.avi").exists() else None)
            try:
                tj = json.loads((out / "timing.json").read_text())
                r["timing"] = {key: tj.get(key) for key in ("status", "frames", "wall_seconds", "width", "height")}
            except (OSError, json.JSONDecodeError) as e:
                r["timing"] = {"error": str(e)}
            rec["runs"].append(r)
            say(f"rerun{k} traced={traced} exit {r['rc']} wall {(r['time'] or {}).get('wall_s')}")
            shutil.rmtree(out)

        _phase(pdir, 5, "samples", say)
        src = published / f"{stem}_trace.vgch.zst"
        local = pdir / src.name
        shutil.copyfile(src, local)
        sample = root / "tools" / "vgacap-build" / "vgacap-sample"
        for k, (variant, extra) in enumerate((("default", []), ("both", ["--sampler", SAMPLERS[0],
                                                                         "--sampler", SAMPLERS[1]]))):
            out = pdir / f"sample-{variant}"
            if out.exists():
                shutil.rmtree(out)
            out.mkdir()
            env = dict(os.environ, VGACAP_SAMPLE_DEBUG="1")
            cmd = ["timeout", f"--kill-after={GRACE}", str(args.timeout), str(sample), str(local), "--out", str(out), "--name", stem] + extra
            mark = log.stat().st_size
            r = _timed(cmd, pdir / f"sample-{variant}.time", log, env=env)
            with log.open() as f:
                f.seek(mark)
                said = f.read()
            r["variant"] = variant
            r["debug"] = " ".join(re.findall(r"trace_passes=\d+ blocks_decoded=\d+", said)) or None
            r["stores"] = {name: (out / name / f"{stem}_{name}_frames.rgb6.zst").stat().st_size
                           for name in SAMPLERS if (out / name / f"{stem}_{name}_frames.rgb6.zst").exists()}
            rec["samples"].append(r)
            say(f"sample {variant} exit {r['rc']} wall {(r['time'] or {}).get('wall_s')} {r['debug']}")
            shutil.rmtree(out)
        local.unlink()

        _phase(pdir, 6, "sizes", say)
        sizes: dict = {"total": _du(published), "samplers": {}}
        t = published / f"{stem}_trace.vgch.zst"
        sizes["trace"] = t.stat().st_size if t.exists() else None
        for name in SAMPLERS:
            d = published / name
            if not d.is_dir():
                continue
            store = d / f"{stem}_{name}_frames.rgb6.zst"
            pngs = list((d / "png").iterdir()) if (d / "png").is_dir() else []
            sizes["samplers"][name] = {
                "dir": _du(d), "store": store.stat().st_size if store.exists() else None,
                "png_bytes": _du(d / "png"), "png_files": len(pngs),
                "png_inodes": len({p.stat().st_ino for p in pngs}),
            }
        rec["sizes"] = sizes
    except Exception as e:   # recorded: the coordinator still gets this project's record
        import traceback
        rec["errors"].append(f"{type(e).__name__}: {e}")
        rec["traceback"] = traceback.format_exc()
        say(f"failed: {type(e).__name__}: {e}")
    rec["finished"] = now()
    rec["host_load_end"] = os.getloadavg()
    raw = Path(args.raw)
    raw.mkdir(parents=True, exist_ok=True)
    tmp = raw / f"{s}__{m}.json.tmp"
    tmp.write_text(json.dumps(rec, indent=2) + "\n")
    tmp.rename(raw / f"{s}__{m}.json")
    _phase(pdir, 7, "done", say)
    return 0 if not rec["errors"] else 1


# ---------------------------------------------------------------------------
# On the host: the coordinator
# ---------------------------------------------------------------------------

def _scope_props(unit: str) -> dict:
    p = subprocess.run(["systemctl", "--user", "show", unit, "-p", "MemoryCurrent", "-p", "MemoryPeak",
                        "-p", "TasksCurrent", "-p", "ActiveState"], capture_output=True, text=True)
    out = {}
    for line in p.stdout.splitlines():
        k, _, v = line.partition("=")
        out[k] = int(v) if v.isdigit() else v
    return out


def on_host(args: argparse.Namespace) -> int:
    root = args.root
    sys.path.insert(0, str(root / "harness"))
    import runqueue  # the queue's scope limits and unit names, so the pilot runs as the queue does

    plan = json.loads(Path(args.plan).read_text())
    pilot = root / "work" / "pilot"
    raw = pilot / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def say(msg: str) -> None:
        with lock:
            print(f"{now()} {msg}", flush=True)

    say(f"pilot start: {len(plan['ids'])} projects, {args.jobs} at once, timeout {args.timeout:g}, "
        f"load {os.getloadavg()} on {os.cpu_count()} CPUs")
    targets = {t["id"]: t for t in json.loads((root / "harness" / "targets.json").read_text())["targets"]}
    # The whole project runs in one scope: the job's own worst case, plus the re-runs and samples.
    runtime = runqueue.runtime_max_sec(args.timeout, runqueue.GRACE) + (len(RERUNS) + 2) * int(args.timeout + GRACE)
    polls: dict[str, dict] = {}
    scope_peaks: dict[str, dict] = {}
    units: dict[str, str] = {}
    procs: dict[str, subprocess.Popen] = {}
    queue = list(plan["ids"])
    min_free = shutil.disk_usage(root).free

    def start(pid: str) -> None:
        t = targets[pid]
        unit = "ttvga-pilot-" + runqueue.scope_unit(t["shuttle"], t["macro"])[len("ttvga-job-"):]
        units[pid] = unit + ".scope"
        cmd = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--unit", unit,
               "-p", f"MemoryMax={runqueue.SCOPE_MEMORY}", "-p", f"CPUQuota={runqueue.SCOPE_CPU}",
               "-p", f"TasksMax={runqueue.SCOPE_TASKS}", "-p", f"RuntimeMaxSec={runtime}", "-p", "OOMPolicy=continue",
               "--", sys.executable, str(Path(__file__).resolve()), "--on-host-project", pid, "--root", str(root),
               "--timeout", str(args.timeout), "--raw", str(raw)]
        say(f"{pid}: start: {' '.join(cmd)}")
        procs[pid] = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
        polls[pid] = {}
        scope_peaks[pid] = {"memory_peak": 0, "tasks_peak": 0}

    def phase_of(pid: str) -> dict:
        t = targets[pid]
        try:
            return json.loads((pilot / t["shuttle"] / t["macro"] / "phase").read_text())
        except (OSError, json.JSONDecodeError):
            return {"index": 0, "name": "job", "t0": time.time()}

    def finish(pid: str, rc: int) -> None:
        t = targets[pid]
        path = raw / f"{t['shuttle']}__{t['macro']}.json"
        try:
            rec = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            rec = {"id": pid, "errors": [f"no record (scope exit {rc})"]}
        rec["poll"] = polls[pid]
        rec["scope"] = dict(scope_peaks[pid], unit=units[pid], exit=rc, runtime_max_sec=runtime,
                            memory_max=runqueue.SCOPE_MEMORY, cpu_quota=runqueue.SCOPE_CPU,
                            tasks_max=runqueue.SCOPE_TASKS)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=2) + "\n")
        tmp.rename(path)
        say(f"{pid}: finished, scope exit {rc}, MemoryPeak {scope_peaks[pid]['memory_peak']}, "
            f"peak tasks {scope_peaks[pid]['tasks_peak']}")

    def stop_scopes() -> None:
        """Stop every scope still running (a pilot stopped part way leaves none behind)."""
        alive = [units[pid] for pid, proc in procs.items() if proc.poll() is None]
        if alive:
            say(f"stopping {len(alive)} scopes: {' '.join(alive)}")
            subprocess.run(["systemctl", "--user", "stop", *alive])

    def on_signal(signum, frame):
        say(f"signal {signum}: stopping the scopes")
        stop_scopes()
        sys.exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, on_signal)
    atexit.register(stop_scopes)

    last_progress = 0.0
    while queue or procs:
        while queue and len(procs) < args.jobs:
            start(queue.pop(0))
        for pid, proc in list(procs.items()):
            t = targets[pid]
            ph = phase_of(pid)
            props = _scope_props(units[pid])
            pk = scope_peaks[pid]
            for key, prop in (("memory_peak", "MemoryPeak"), ("tasks_peak", "TasksCurrent")):
                if isinstance(props.get(prop), int):
                    pk[key] = max(pk[key], props[prop])
            entry = polls[pid].setdefault(ph["name"], {"work_bytes_peak": 0, "scratch_bytes_peak": 0,
                                                       "pilot_bytes_peak": 0, "memory_current_peak": 0,
                                                       "tasks_peak": 0})
            work = root / "work" / t["shuttle"] / t["macro"]
            for key, path in (("work_bytes_peak", work), ("scratch_bytes_peak", work / "scratch"),
                              ("pilot_bytes_peak", pilot / t["shuttle"] / t["macro"])):
                if (n := _du(path)) is not None:
                    entry[key] = max(entry[key], n)
            for key, prop in (("memory_current_peak", "MemoryCurrent"), ("tasks_peak", "TasksCurrent")):
                if isinstance(props.get(prop), int):
                    entry[key] = max(entry[key], props[prop])
            if (rc := proc.poll()) is not None:
                del procs[pid]
                finish(pid, rc)
        min_free = min(min_free, shutil.disk_usage(root).free)
        if time.monotonic() - last_progress >= PROGRESS_S or (not queue and not procs):
            last_progress = time.monotonic()
            state = {}
            for pid in plan["ids"]:
                if pid in procs:
                    ph = phase_of(pid)
                    state[pid] = {"done": ph["index"], "elapsed_in_phase": time.time() - ph["t0"]}
                elif pid in queue:
                    state[pid] = {"done": 0, "elapsed_in_phase": 0.0}
                else:
                    state[pid] = {"done": RUNS_PER_PROJECT, "elapsed_in_phase": 0.0}
            runs_left, secs = eta(plan["expected"], state)
            total = RUNS_PER_PROJECT * len(plan["ids"])
            finish_at = datetime.now(timezone.utc) + timedelta(seconds=secs)
            load = os.getloadavg()[0]
            say(f"progress: runs {total - runs_left}/{total} done, {runs_left} remaining, "
                f"{len(procs)} projects running, ETA {secs / 3600:.2f} h, finish {finish_at.isoformat(timespec='minutes')} "
                f"({finish_at.astimezone().strftime('%H:%M %Z')}), load {load:.0f}/{os.cpu_count()} = "
                f"{load / (os.cpu_count() or 1):.2f}, root free min {min_free / 1e9:.0f} GB")
        if queue or procs:
            time.sleep(POLL_S)
    (raw / "DONE").write_text(now() + f"\nroot_free_min_bytes {min_free}\n")
    say("pilot finished")
    return 0


# ---------------------------------------------------------------------------
# Locally
# ---------------------------------------------------------------------------

def expected_seconds(results: Path, pid: str) -> list[float]:
    """Each run's expected seconds from the previous run: the job (with derive at 10%), then 4 simulations."""
    tm = json.loads((results / pid / "result.json").read_text())["timings"]
    sim = tm["simulate"]
    job = tm.get("fetch", 0) + tm.get("build", 0) + sim + tm.get("encode", 0) + 0.1 * sim
    return [round(job, 1)] + [round(sim, 1)] * len(RERUNS)


def local(args: argparse.Namespace) -> int:
    from ttvga import RESULTS_DIR, remote

    host = remote.resolve_host(args.host)
    tools = tomllib.loads(remote.TOOLS_TOML.read_text())
    ids = [line.strip() for line in Path(args.ids).read_text().splitlines() if line.strip() and not line.startswith("#")]
    pilot = f"{remote.REMOTE_ROOT}/work/pilot"
    if not args.pull_only:
        state = remote.ssh(host, f"tmux has-session -t {SESSION} && echo running || "
                                 f"{{ [ -f ~/{pilot}/raw/DONE ] && echo done || echo idle; }}",
                           check=False, capture=True)
        what = state.stdout.strip().splitlines()[-1] if state.stdout.strip() else "unknown"
        print(f"{now()} host pilot state: {what}", flush=True)
        if what == "idle":
            plan = {"ids": ids, "expected": {pid: expected_seconds(RESULTS_DIR, pid) for pid in ids}}
            plan_file = Path("tmp") / "t20-plan.json"
            plan_file.parent.mkdir(exist_ok=True)
            plan_file.write_text(json.dumps(plan, indent=2) + "\n")
            remote.rsync(host, [str(Path(__file__).resolve()), str(plan_file)], f"{pilot}/")
            cmd = (f"{remote.host_python(tools)} ~/{pilot}/pilot_measure.py --on-host --plan ~/{pilot}/t20-plan.json "
                   f"--root ~/{remote.REMOTE_ROOT} --jobs {args.jobs} --timeout {args.timeout:g} "
                   f">> ~/{remote.REMOTE_ROOT}/work/pilot.log 2>&1")
            remote.ssh(host, f"tmux new-session -d -s {SESSION} {shlex.quote(cmd)}")
            print(f"{now()} started: {cmd}", flush=True)
        elif what == "unknown":
            print(f"{now()} cannot tell the host's state: {state.stderr}", flush=True)
            return 1
        if args.no_wait:
            return 0
        while True:
            p = remote.ssh(host, f"[ -f ~/{pilot}/raw/DONE ] && echo done || "
                                 f"{{ tmux has-session -t {SESSION} && echo running || echo gone; }}",
                           check=False, capture=True)
            state = p.stdout.strip()
            if state == "done":
                break
            if state == "gone":
                print(f"{now()} the pilot's tmux session ended without raw/DONE", flush=True)
                return 1
            time.sleep(60)
    remote.rsync_from(host, f"{pilot}/raw/", Path(args.out),
                      extra=["--include", "*.json", "--include", "DONE", "--exclude", "*"])
    p = remote.ssh(host, f"echo $HOME; uname -n; hostname -f; cat ~/{remote.REMOTE_ROOT}/host.toml", capture=True)
    home, node, fqdn, conf = p.stdout.split("\n", 3)
    conf = tomllib.loads(conf)
    paths = {conf["staging_dir"]: "<staging_dir>", conf["frames_root"]: "<frames_root>",
             f"{home.strip()}/{remote.REMOTE_VIDEOS}": "<videos>", home.strip(): "~",
             fqdn.strip(): "<host>", node.strip(): "<host>"}
    for path in Path(args.out).glob("*.json"):
        path.write_text(redact(path.read_text(), paths))
    print(f"{now()} pulled {pilot}/raw/*.json into {args.out}", flush=True)
    return 0


def upload_listing(args: argparse.Namespace) -> int:
    runs = parse_rsync_log(Path(args.upload_listing).read_text(errors="replace"))
    print("| start (host local) | files | duration (s) |")
    print("| --- | ---: | ---: |")
    for r in runs[-args.last:]:
        print(f"| {r['start']} | {r['files']:,} | {r['duration_s']:.0f} |")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host")
    ap.add_argument("--ids", help="file of <shuttle>/<macro> ids, one a line")
    ap.add_argument("--out", help="where raw/*.json is pulled to")
    ap.add_argument("--jobs", type=int, default=11)
    ap.add_argument("--timeout", type=float, default=10800.0)
    ap.add_argument("--no-wait", action="store_true", help="start the pilot and return")
    ap.add_argument("--pull-only", action="store_true", help="only pull raw/*.json")
    ap.add_argument("--report", metavar="RAW_DIR", help="print measurements.md's tables")
    ap.add_argument("--upload-listing", metavar="RSYNC_LOG", help="print the upload's recent listings")
    ap.add_argument("--last", type=int, default=10)
    ap.add_argument("--on-host", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--on-host-project", metavar="ID", dest="id", help=argparse.SUPPRESS)
    ap.add_argument("--plan", help=argparse.SUPPRESS)
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--raw", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.report:
        sys.stdout.write(report(Path(args.report)))
        return 0
    if args.upload_listing:
        return upload_listing(args)
    if args.id:
        return on_host_project(args)
    if args.on_host:
        return on_host(args)
    if not (args.host and args.out and (args.ids or args.pull_only)):
        ap.error("--host, --ids and --out are needed")
    return local(args)


if __name__ == "__main__":
    sys.exit(main())
