# SPDX-License-Identifier: Apache-2.0
"""runqueue.py: selection, the free-space wait, each job in a systemd user scope, and the refusals."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tomllib
from collections import namedtuple
from pathlib import Path

import pytest

from ttvga import HARNESS_DIR, cli, remote

sys.path.insert(0, str(HARNESS_DIR))

import runqueue  # noqa: E402

TOOLS = tomllib.loads(remote.TOOLS_TOML.read_text())
Usage = namedtuple("Usage", "total used free")


def make_root(tmp_path: Path, min_free: float | None = None, ids: tuple[str, ...] = ("s1/tt_um_a",)) -> Path:
    """A queue --root: a valid host.toml and a targets.json with `ids`."""
    root = tmp_path / "root"
    frames, staging = tmp_path / "frames", tmp_path / "staging"
    for d in (root, frames, staging):
        d.mkdir(parents=True)
    (frames / ".ttvga-frames-root").write_text("")
    extra = f"min_free_root_gb = {min_free}\n" if min_free is not None else ""
    (root / "host.toml").write_text(f'frames_root = "{frames}"\nstaging_dir = "{staging}"\n{extra}')
    targets = [{"id": i, "shuttle": i.split("/")[0], "macro": i.split("/")[1]} for i in ids]
    (root / "targets.json").write_text(json.dumps({"targets": targets}) + "\n")
    return root


def _script(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def fake_systemd_run(tmp_path: Path, monkeypatch, body: str, linger: str = "yes") -> Path:
    """Put a `systemd-run` first on PATH that appends its argv to calls.log, then runs `body`.

    A `loginctl` beside it answers `linger` for Linger.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    _script(bin_dir / "systemd-run", f'#!/bin/sh\nprintf "%s\\n" "$*" >> {calls}\n{body}\n')
    _script(bin_dir / "loginctl", f'#!/bin/sh\necho {linger}\n')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return calls


def write_result(root: Path, tid: str, **fields) -> None:
    shuttle, macro = tid.split("/")
    path = root / "work" / shuttle / macro / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": tid, **fields}) + "\n")


def queue_args(root: Path, *extra: str) -> list[str]:
    return ["--root", str(root), "--targets", str(root / "targets.json"), "--jobs", "2", *extra]


def test_queue_waits_for_free_space(tmp_path, monkeypatch):
    root = make_root(tmp_path, min_free=10)
    frees = iter([4.0e9, 9.5e9, 10.0e9])
    seen = []
    monkeypatch.setattr(runqueue.shutil, "disk_usage",
                        lambda path: seen.append(Path(path)) or Usage(100e9, 0, next(frees)))
    sleeps, lines = [], []
    runqueue.wait_for_free_space(root, 10.0, lines.append, sleep=sleeps.append)
    assert lines == ["waiting for free space: 4.0 GB free, need 10",
                     "waiting for free space: 9.5 GB free, need 10"]
    assert sleeps == [60, 60]
    assert seen == [root] * 3


def test_queue_free_space_wait_ends_on_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(runqueue.shutil, "disk_usage", lambda path: Usage(100e9, 0, 1e9))
    stop = runqueue.threading.Event()
    lines = []
    assert runqueue.wait_for_free_space(tmp_path, 10.0, lines.append, stop=stop,
                                        sleep=lambda s: stop.set()) is False
    assert len(lines) == 1


def test_queue_runs_each_job_after_the_free_space_check(tmp_path, monkeypatch):
    root = make_root(tmp_path, min_free=10, ids=("s1/tt_um_a", "s1/tt_um_b"))
    calls = fake_systemd_run(tmp_path, monkeypatch, 'echo "job: done"')
    checks = []
    monkeypatch.setattr(runqueue, "wait_for_free_space",
                        lambda path, need, say, **kw: checks.append((Path(path), need)) or True)
    assert runqueue.main(queue_args(root)) == 0
    assert checks == [(root, 10.0), (root, 10.0)]
    lines = calls.read_text().splitlines()
    assert lines[0] == "--user --scope --quiet --collect true"
    assert len(lines) == 3


def test_queue_job_command_is_a_scope():
    args = runqueue.parse_args(["--root", "/r", "--targets", "/r/t.json", "--timeout", "10800",
                                "--seconds", "60", "--tb-v1"])
    t = {"id": "tt08/tt_um_x.y", "shuttle": "tt08", "macro": "tt_um_x.y"}
    cmd = runqueue.job_command(t, args)
    i = cmd.index("--")
    assert cmd[:i] == ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                       "--unit", "ttvga-job-tt08-tt_um_x.y",
                       "-p", "MemoryMax=6G", "-p", "CPUQuota=200%", "-p", "TasksMax=64",
                       "-p", f"RuntimeMaxSec={runqueue.runtime_max_sec(10800, runqueue.GRACE)}",
                       "-p", "OOMPolicy=continue"]
    assert cmd[i + 1:i + 3] == [sys.executable, str(HARNESS_DIR / "job.py")]
    rest = cmd[i + 3:]
    assert rest[rest.index("--id") + 1] == "tt08/tt_um_x.y"
    assert rest[rest.index("--timeout") + 1] == "10800.0"
    assert rest[rest.index("--grace") + 1] == str(float(runqueue.GRACE))
    assert "--tb-v1" in rest and "--rederive" not in rest and "--test-hooks" not in rest
    # The limits are options; the job's own flags pass through.
    args = runqueue.parse_args(["--root", "/r", "--scope-memory", "8G", "--scope-cpu", "150%",
                                "--rederive", "--drop-tb-v1"])
    cmd = runqueue.job_command(t, args)
    assert "MemoryMax=8G" in cmd and "CPUQuota=150%" in cmd
    assert "--rederive" in cmd and "--drop-tb-v1" in cmd and "--tb-v1" not in cmd


def test_scope_runtime_max_covers_the_worst_job():
    # Task 9: simulate + probes + derive 3T + G + 2790, fetch 2880, build 3600, encode 16000,
    # tool versions 60, and an hour for publish; rounded up to whole hours.
    worst = 3 * 10800 + 120 + 2790 + 2880 + 3600 + 16000 + 60 + 3600
    assert worst == 61450
    assert runtime_hours(runqueue.runtime_max_sec(10800, 120)) == 18
    assert runqueue.runtime_max_sec(10800, 120) >= worst
    assert runqueue.runtime_max_sec(1800, 120) >= 3 * 1800 + 120 + 28930


def runtime_hours(seconds: int) -> float:
    return seconds / 3600


@pytest.mark.parametrize("name, unit", [("tt08/tt_um_a-b.c", "ttvga-job-tt08-tt_um_a-b.c"),
                                        ("x y/m\\n", "ttvga-job-x\\x20y-m\\x5cn")])
def test_scope_unit_names_are_valid(name, unit):
    shuttle, macro = name.split("/")
    assert runqueue.scope_unit(shuttle, macro) == unit


def test_queue_refuses_without_user_manager(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    calls = fake_systemd_run(tmp_path, monkeypatch,
                             'echo "Failed to connect to user scope bus via local transport: '
                             'No such file or directory" >&2; exit 1')
    rc = runqueue.main(queue_args(root))
    assert rc == 1
    err = capsys.readouterr().err
    assert "systemd-run --user --scope true failed (exit 1)" in err
    assert "Failed to connect to user scope bus" in err
    assert "Failed to connect to user scope bus" in (root / "queue.log").read_text()
    # Only the preflight ran: no job was started unconfined or otherwise.
    assert calls.read_text().splitlines() == ["--user --scope --quiet --collect true"]
    assert not (root / "work").exists()


def test_queue_refuses_without_systemd_run(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert runqueue.main(queue_args(root)) == 1
    assert "systemd-run --user --scope true failed" in capsys.readouterr().err


def test_queue_redo_unless_harness_skips_done(tmp_path, monkeypatch):
    ids = ("s1/done", "s1/old", "s1/notrace", "s1/none", "s1/nomatch", "s1/notrun", "s1/stopped", "s1/unpublished")
    root = make_root(tmp_path, ids=ids)
    trace = {"file": "x", "sha256": "0" * 64}
    ok = {"trace": trace, "published": True, "error": None}
    write_result(root, "s1/done", **ok, harness="V2", tb_v1_check="match")
    write_result(root, "s1/old", **ok, harness="V1", tb_v1_check="match")
    write_result(root, "s1/notrace", trace=None, published=False, error="verilator failed", harness="V2",
                 tb_v1_check="not-run")
    write_result(root, "s1/nomatch", **ok, harness="V2", tb_v1_check="off")
    write_result(root, "s1/notrun", **ok, harness="V2", tb_v1_check="not-run")
    # The reviewer's case: a trace from this harness, but stopped before it was published.
    write_result(root, "s1/stopped", trace=trace, harness="V2", published=False,
                 error="terminated by SIGTERM during encode", tb_v1_check="match")
    # A mismatch (or any derive error) publishes nothing.
    write_result(root, "s1/unpublished", trace=trace, harness="V2", published=False,
                 error="tb-v1 does not match tb.cpp", tb_v1_check="mismatch")

    def pending(*extra):
        args = runqueue.parse_args(queue_args(root, *extra))
        targets = json.loads((root / "targets.json").read_text())["targets"]
        return [t["id"] for t in runqueue.select_pending(targets, args)]

    # Without --tb-v1: a published result with a trace from this harness, not stopped, is done.
    assert pending("--redo-unless-harness", "V2") == ["s1/old", "s1/notrace", "s1/none", "s1/stopped",
                                                      "s1/unpublished"]
    # With --tb-v1, it must also have matched tb.cpp.
    assert pending("--redo-unless-harness", "V2", "--tb-v1") == ["s1/old", "s1/notrace", "s1/none", "s1/nomatch",
                                                                  "s1/notrun", "s1/stopped", "s1/unpublished"]
    # A stopped run that did publish (SIGTERM after the swap) is still run again.
    write_result(root, "s1/stopped", trace=trace, harness="V2", published=True,
                 error="terminated by SIGTERM during publish", tb_v1_check="match")
    assert "s1/stopped" in pending("--redo-unless-harness", "V2")
    # The plain queue runs only what has no result; --redo runs everything.
    assert pending() == ["s1/none"]
    assert pending("--redo") == list(ids)
    # --rederive picks the projects with a trace.
    with_trace = ["s1/done", "s1/old", "s1/nomatch", "s1/notrun", "s1/stopped", "s1/unpublished"]
    assert pending("--rederive") == with_trace


def test_queue_rederive_done_means_this_campaign(tmp_path):
    """Ruling BD: under --rederive, done is re-derived since the campaign started, without an error."""
    ids = ("s1/fresh", "s1/before", "s1/never", "s1/failed", "s1/oldharness", "s1/tbcurrent", "s1/tbstale")
    root = make_root(tmp_path, ids=ids)
    trace = {"file": "x", "sha256": "0" * 64}
    base = {"trace": trace, "published": True, "error": None, "harness": "V2", "tb_v1_check": "off"}
    write_result(root, "s1/fresh", **base, rederived_at="2026-11-28T01:00:00+00:00", rederive_error=None)
    write_result(root, "s1/before", **base, rederived_at="2026-11-27T23:59:59+00:00", rederive_error=None)
    write_result(root, "s1/never", **base, rederived_at=None)
    write_result(root, "s1/failed", **base, rederived_at="2026-11-28T01:00:00+00:00",
                 rederive_error="no published trace")
    write_result(root, "s1/oldharness", **{**base, "harness": "V1"}, rederived_at="2026-11-28T01:00:00+00:00",
                 rederive_error=None)
    write_result(root, "s1/tbcurrent", **{**base, "tb_v1_check": "not-run"},
                 tb_v1={"state": "current", "trace_sha": "0" * 64, "dropped": False},
                 rederived_at="2026-11-28T02:00:00+00:00", rederive_error=None)
    write_result(root, "s1/tbstale", **base, tb_v1={"state": "stale", "trace_sha": None, "dropped": False},
                 rederived_at="2026-11-28T02:00:00+00:00", rederive_error=None)

    def pending(*extra):
        args = runqueue.parse_args(queue_args(root, *extra))
        targets = json.loads((root / "targets.json").read_text())["targets"]
        return [t["id"] for t in runqueue.select_pending(targets, args)]

    since = ("--rederive", "--redo-unless-harness", "V2", "--since", "2026-11-28T00:00:00Z")
    assert pending(*since) == ["s1/before", "s1/never", "s1/failed", "s1/oldharness"]
    # With --tb-v1, tb-v1 must also be current (a re-derive's check is not-run).
    assert pending(*since, "--tb-v1") == ["s1/fresh", "s1/before", "s1/never", "s1/failed", "s1/oldharness",
                                          "s1/tbstale"]
    # A timestamp without a zone is UTC.
    assert pending("--rederive", "--redo-unless-harness", "V2", "--since", "2026-11-28T01:30:00") == \
        ["s1/fresh", "s1/before", "s1/never", "s1/failed", "s1/oldharness"]


@pytest.mark.parametrize("extra", [["--rederive", "--redo-unless-harness", "V2"], ["--since", "not a time"]])
def test_queue_rederive_restart_needs_since(tmp_path, extra, capsys):
    with pytest.raises(SystemExit) as e:
        runqueue.parse_args(queue_args(make_root(tmp_path), *extra))
    assert e.value.code == 2
    assert "--since" in capsys.readouterr().err


def test_queue_redo_unless_harness_runs_only_the_rest(tmp_path, monkeypatch):
    root = make_root(tmp_path, ids=("s1/done", "s1/old"))
    write_result(root, "s1/done", trace={"sha256": "a"}, harness="V2", published=True, error=None)
    write_result(root, "s1/old", trace={"sha256": "a"}, harness="V1", published=True, error=None)
    calls = fake_systemd_run(tmp_path, monkeypatch, 'echo "job: ok"')
    assert runqueue.main(queue_args(root, "--redo-unless-harness", "V2")) == 0
    jobs = calls.read_text().splitlines()[1:]
    assert len(jobs) == 1 and "--id s1/old " in jobs[0] and "--unit ttvga-job-s1-old " in jobs[0]


@pytest.mark.parametrize("extra", [["--redo", "--redo-unless-harness", "V"], ["--tb-v1", "--drop-tb-v1"]])
def test_queue_refuses_conflicting_options(tmp_path, extra):
    with pytest.raises(SystemExit) as e:
        runqueue.parse_args(queue_args(make_root(tmp_path), *extra))
    assert e.value.code == 2


def test_queue_refuses_test_hooks(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    calls = fake_systemd_run(tmp_path, monkeypatch, "true")
    with pytest.raises(SystemExit) as e:
        runqueue.main(queue_args(root, "--test-hooks"))
    assert e.value.code == 2
    assert "--test-hooks" in capsys.readouterr().err
    assert not calls.exists()
    with pytest.raises(SystemExit) as e:
        cli.main(["queue", "start", "--host", "ttvga@example.invalid", "--test-hooks"])
    assert e.value.code == 2
    assert "--test-hooks" in capsys.readouterr().err


def remote_args(*argv: str) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    remote.add_parsers(p.add_subparsers())
    return p.parse_args(["queue", "start", "--host", "ttvga@example.invalid", *argv])


def test_tt_vga_queue_passes_the_new_options():
    host = remote.Host(ssh="ttvga@example.invalid", jobs=4)
    cmd = remote.queue_command(remote_args("--rederive", "--tb-v1", "--redo-unless-harness", "abc123",
                                           "--since", "2026-11-28T00:00:00Z",
                                           "--scope-memory", "8G", "--scope-cpu", "150%",
                                           "--timeout", "10800"), host, TOOLS)
    for part in ("--rederive", "--since 2026-11-28T00:00:00Z", "--tb-v1", "--redo-unless-harness abc123", "--scope-memory 8G",
                 "--scope-cpu 150%", "--timeout 10800.0"):
        assert f" {part}" in cmd, part
    assert "--drop-tb-v1" not in cmd and "--test-hooks" not in cmd
    plain = remote.queue_command(remote_args(), host, TOOLS)
    for part in ("--rederive", "--tb-v1", "--redo-unless-harness", "--scope-memory", "--scope-cpu"):
        assert part not in plain
    dropped = remote.queue_command(remote_args("--drop-tb-v1", "--yes-drop-tb-v1"), host, TOOLS)
    assert " --drop-tb-v1" in dropped


def test_tt_vga_queue_drop_tb_v1_needs_yes(capsys):
    args = remote_args("--drop-tb-v1")
    with pytest.raises(SystemExit) as e:
        remote.queue_command(args, remote.Host(ssh="ttvga@example.invalid"), TOOLS)
    assert "--yes-drop-tb-v1" in str(e.value)


def test_runqueue_knows_every_option_tt_vga_passes(tmp_path):
    cmd = remote.queue_command(remote_args("--rederive", "--tb-v1", "--redo-unless-harness", "abc",
                                           "--since", "2026-11-28T00:00:00Z", "--allow-no-linger",
                                           "--scope-memory", "8G", "--scope-cpu", "150%",
                                           "--only", "tt08", "--limit", "3", "--jobs", "5"),
                               remote.Host(ssh="ttvga@example.invalid"), TOOLS)
    argv = cmd.split("runqueue.py", 1)[1].split()
    args = runqueue.parse_args([a.strip("'") for a in argv])
    assert (args.rederive, args.tb_v1, args.redo_unless_harness, args.scope_memory, args.scope_cpu,
            args.allow_no_linger) == (True, True, "abc", "8G", "150%", True)
    assert args.since.isoformat() == "2026-11-28T00:00:00+00:00"


def test_tt_vga_queue_rederive_restart_needs_since():
    with pytest.raises(SystemExit) as e:
        remote.queue_command(remote_args("--rederive", "--redo-unless-harness", "abc"),
                             remote.Host(ssh="ttvga@example.invalid"), TOOLS)
    assert "--since" in str(e.value)


def test_queue_refuses_without_linger(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path)
    calls = fake_systemd_run(tmp_path, monkeypatch, 'echo "job: done"', linger="no")
    assert runqueue.main(queue_args(root)) == 1
    err = capsys.readouterr().err
    assert "linger is not on" in err and "--allow-no-linger" in err
    assert calls.read_text().splitlines() == ["--user --scope --quiet --collect true"]   # no job
    # --allow-no-linger starts anyway, and says so in the log.
    assert runqueue.main(queue_args(root, "--allow-no-linger")) == 0
    assert len(calls.read_text().splitlines()) == 3
    assert "warning: linger is not on" in (root / "queue.log").read_text()


def test_queue_stops_when_scopes_start_failing(tmp_path, monkeypatch, capsys):
    """systemd-run failing before job.py runs, with the preflight now failing too: no more jobs."""
    root = make_root(tmp_path, ids=("s1/a", "s1/b", "s1/c"))
    flag = tmp_path / "preflight-ok-once"
    flag.write_text("")
    calls = fake_systemd_run(tmp_path, monkeypatch, f"""
case "$*" in
  *" true") if [ -f {flag} ]; then rm {flag}; exit 0; fi
           echo "Failed to connect to user scope bus" >&2; exit 1;;
  *) echo "Failed to start transient scope unit: Connection reset" >&2; exit 1;;
esac""")
    assert runqueue.main(queue_args(root, "--jobs", "1")) == 1
    lines = calls.read_text().splitlines()
    assert len([line for line in lines if "--unit " in line]) == 1
    assert len([line for line in lines if line.endswith(" true")]) == 2
    log = (root / "queue.log").read_text()
    assert "scopes failing (systemd-run --user --scope true failed (exit 1)" in log
    assert "starting no more jobs" in log
    assert "stopped early" in capsys.readouterr().err


def test_queue_goes_on_after_a_failed_job(tmp_path, monkeypatch):
    """A job that ran and failed (its `job:` line), or a systemd-run failure while scopes still work, is one failure."""
    root = make_root(tmp_path, ids=("s1/a", "s1/b"))
    calls = fake_systemd_run(tmp_path, monkeypatch, """
case "$*" in
  *" true") exit 0;;
  *s1/a*) echo "Unit ttvga-job-s1-a.scope already exists." >&2; exit 1;;
  *) echo "job: s1/b: stage=build error='verilator failed'"; exit 1;;
esac""")
    assert runqueue.main(queue_args(root, "--jobs", "1")) == 0
    assert len([line for line in calls.read_text().splitlines() if "--unit " in line]) == 2


def test_started_job():
    assert runqueue.started_job("job: x: stage=publish error=None\n", "")
    assert runqueue.started_job("", "job: x: already running elsewhere, skipped\n")
    assert not runqueue.started_job("", "Failed to start transient scope unit\n")
