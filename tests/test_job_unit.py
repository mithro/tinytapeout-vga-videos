# SPDX-License-Identifier: Apache-2.0
"""job.py without a simulator: the build command, the tb-v1 rule and the testpatterns pseudo-shuttle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

import job  # noqa: E402
from tests.test_job_build import fake_project, fake_vgacap  # noqa: E402


def build_cmd(tmp_path, monkeypatch, test_hooks: bool | None) -> tuple[list[str], Path, Path]:
    src, build = fake_vgacap(tmp_path)
    target, repo = fake_project(tmp_path)
    cmds = []
    monkeypatch.setattr(job, "run", lambda cmd, log, **kw: cmds.append(cmd) or 1)
    log = tmp_path / "build.log"
    log.write_text("")
    kw = {} if test_hooks is None else {"test_hooks": test_hooks}
    job.build(target, {}, repo, tmp_path / "out", log, {"verilator": "verilator"}, src, build, **kw)
    (cmd,) = cmds
    return cmd, src, build


def test_vgacap_link_flags(tmp_path, monkeypatch):
    plain, src, build = build_cmd(tmp_path / "a", monkeypatch, None)
    off, _, _ = build_cmd(tmp_path / "b", monkeypatch, False)
    hooks, _, _ = build_cmd(tmp_path / "c", monkeypatch, True)
    link = job.vgacap_link_flags(src, build)
    i = plain.index("-LDFLAGS")
    assert plain[i - 2:i + 2] == link
    assert "-DTTVGA_TEST_HOOKS" not in plain
    # Without --test-hooks the command is unchanged (paths differ only by the tmp dir).
    assert [a.replace(str(tmp_path / "b"), str(tmp_path / "a")) for a in off] == plain
    # With it, one -CFLAGS -DTTVGA_TEST_HOOKS after the link flags' -CFLAGS, before tb.cpp.
    j = hooks.index("-DTTVGA_TEST_HOOKS")
    assert hooks[j - 1] == "-CFLAGS"
    assert hooks.index(link[1].replace(str(tmp_path / "a"), str(tmp_path / "c"))) < j < hooks.index(str(job.TB_CPP))
    assert len(hooks) == len(plain) + 2


def test_build_uses_src_dir(tmp_path, monkeypatch):
    src, build = fake_vgacap(tmp_path)
    repo = tmp_path / "repo"
    (repo / "designs" / "x" / "src").mkdir(parents=True)
    (repo / "designs" / "x" / "src" / "project.v").write_text("module tt_um_x (); endmodule\n")
    target = {"source_files": ["project.v"], "top_module": "tt_um_x", "src_dir": "designs/x/src"}
    calls = []
    monkeypatch.setattr(job, "run", lambda cmd, log, **kw: calls.append((cmd, kw)) or 1)
    log = tmp_path / "build.log"
    log.write_text("")
    assert job.build(target, {}, repo, tmp_path / "out", log, {"verilator": "v"}, src, build) == "verilator failed"
    ((cmd, kw),) = calls
    assert kw["cwd"] == repo / "designs" / "x" / "src"
    assert str(repo / "designs" / "x" / "src" / "project.v") in cmd


def test_model_cmd_trace_and_meta(tmp_path):
    target = {"id": "tst/tt_um_x", "shuttle": "tst", "macro": "tt_um_x", "clock_hz": 0, "pinout": {}}
    args = job.argparse.Namespace(calib_seconds=1.0, overrides=tmp_path, no_qspi=True,
                                  trace_meta=["project=tst/tt_um_x", "override=none",
                                              "simulator=Verilator 5", "harness=test"])
    base = job.model_cmd(target, {}, tmp_path, tmp_path / "out", {"ffmpeg": "ff"}, args, 1.0)
    assert "--trace" not in base and "--meta" not in base
    cmd = job.model_cmd(target, {}, tmp_path, tmp_path / "out", {"ffmpeg": "ff"}, args, 1.0,
                        trace=tmp_path / "t.vgch.zst")
    assert cmd[:len(base)] == base
    assert cmd[len(base):] == ["--trace", str(tmp_path / "t.vgch.zst"),
                               "--meta", "project=tst/tt_um_x", "--meta", "override=none",
                               "--meta", "simulator=Verilator 5", "--meta", "harness=test"]


def test_override_meta(tmp_path):
    assert job.override_meta(tmp_path, "tst", "tt_um_x") == "none"
    p = tmp_path / "tst" / "tt_um_x.json"
    p.parent.mkdir()
    p.write_bytes(b'{"ui_in": 4}\n')
    import hashlib
    assert job.override_meta(tmp_path, "tst", "tt_um_x") == (
        f"tst/tt_um_x.json sha256:{hashlib.sha256(p.read_bytes()).hexdigest()[:12]}")


@pytest.mark.parametrize("published, seeded, flags, want_carry, want", [
    (None, False, {}, [], {"state": "none", "trace_sha": None, "dropped": False}),
    (None, True, {}, [], {"state": "stale", "trace_sha": None, "dropped": False}),
    ("a" * 64, False, {}, ["tb-v1"], {"state": "stale", "trace_sha": "a" * 64, "dropped": False}),
    ("b" * 64, False, {}, ["tb-v1"], {"state": "current", "trace_sha": "b" * 64, "dropped": False}),
    ("", True, {}, ["tb-v1"], {"state": "stale", "trace_sha": None, "dropped": False}),
    ("a" * 64, True, {"tb_v1": True}, [], {"state": "current", "trace_sha": "b" * 64, "dropped": False}),
    ("a" * 64, True, {"drop": True}, [], {"state": "none", "trace_sha": None, "dropped": True}),
])
def test_tb_v1_rule(tmp_path, published, seeded, flags, want_carry, want):
    pub, frames = tmp_path / "pub", tmp_path / "frames"
    if published is not None:
        (pub / "tb-v1").mkdir(parents=True)
        if published:
            (pub / "tb-v1" / "TRACE_SHA256").write_text(published + "\n")
    if seeded:
        (frames / "tb-v1").mkdir(parents=True)
    carry, state = job.tb_v1_rule(tb_v1=flags.get("tb_v1", False), drop=flags.get("drop", False),
                                  published=pub, work_frames=frames, trace_sha="b" * 64)
    assert (carry, state) == (want_carry, want)


def test_job_testpatterns_not_published(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "HARNESS_VERSION").write_text("test\n")
    target = {"id": "testpatterns/tt_um_vgacal_bars", "shuttle": "testpatterns", "macro": "tt_um_vgacal_bars",
              "repo": "unused", "commit": "unused", "top_module": "tt_um_vgacal_bars", "source_files": [],
              "clock_hz": 0, "pinout": {}, "src_dir": "designs/bars/src"}
    (root / "targets.json").write_text(json.dumps({"targets": [target]}))
    work = root / "work" / "testpatterns" / "tt_um_vgacal_bars"
    (work / "kept" / "old").mkdir(parents=True)

    monkeypatch.setattr(job, "fetch", lambda *a, **kw: None)
    monkeypatch.setattr(job, "build", lambda *a, **kw: None)

    def simulate(*a, trace, **kw):
        (work / "out").mkdir(exist_ok=True)
        (work / "out" / "timing.json").write_text(json.dumps({"status": "ok", "frames": 3}))
        trace.write_bytes(b"trace")
        (work / "sim.log").write_text("tb: sync at clock 100\n")
        return None

    def derive(trace, out, stem, **kw):
        (out / "centre-v1").mkdir()
        (out / "centre-v1" / "frames.txt").write_text("frames.txt\n")
        return job.derive.DeriveResult(
            samplers={"centre-v1": {"sampler_status": "ok", "frames": 3}}, trace_sha="c" * 64,
            uo_out_xxh3_128="d" * 64, uo_out_xxh3_128_clocks=(0, 100), tb_v1_check="off", error=None,
            cpu_seconds=0.5, pngs_written=1, pngs_linked=2, info={"blocks": "1", "clocks": "100"})

    monkeypatch.setattr(job, "simulate", simulate)
    monkeypatch.setattr(job.derive, "derive", derive)
    monkeypatch.setattr(job, "encode", lambda *a, **kw: pytest.fail("testpatterns must not be encoded"))
    monkeypatch.setattr(job.publish, "install", lambda *a, **kw: pytest.fail("testpatterns must not be published"))
    monkeypatch.setattr(job.hostconf, "load", lambda *a, **kw: pytest.fail("testpatterns need no host.toml"))
    monkeypatch.setattr(sys, "argv", ["job.py", "--targets", str(root / "targets.json"), "--id", target["id"],
                                      "--root", str(root), "--videos", str(tmp_path / "videos")])
    assert job.main() == 0
    r = json.loads((work / "result.json").read_text())
    assert r["error"] is None and r["published"] is False
    assert r["stage"] == "derive"
    assert set(r["timings"]) == {"fetch", "build", "simulate", "derive"}
    assert r["trace"]["sha256"] == "c" * 64
    assert r["trace"]["fast_path"] is True
    assert not (work / "scratch").exists()
    assert sorted(p.name for p in (work / "kept").iterdir()) == ["centre-v1", "testpatterns_tt_um_vgacal_bars_trace.vgch.zst"]
    assert not (tmp_path / "videos").exists()


# ---- Hardening (review follow-up): run_derive's child, crashes, SIGTERM, timing.json, the fast path.

DTOOLS = {"vgacap_sample": "/nonexistent/vgacap-sample", "tracetool": "/nonexistent/tracetool"}


def _go_derive(tmp_path, timeout: float = 30.0):
    return job.run_derive(tmp_path / "t.vgch.zst", tmp_path / "scratch", "s_m", tb_v1=False, tb_hashes=None,
                          tools=DTOOLS, log=tmp_path / "derive.log", timeout=timeout)


def _gone(pid: int) -> bool:
    """The process no longer runs (it is reaped, or a zombie waiting for init)."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return True
    return state in ("Z", "X")


def test_run_derive_timeout_kills_the_group(tmp_path, monkeypatch):
    import subprocess
    import time

    pidfile = tmp_path / "sleep.pid"

    def slow(*a, **kw):
        p = subprocess.Popen(["sleep", "60"])
        pidfile.write_text(str(p.pid))
        time.sleep(60)

    monkeypatch.setattr(job.derive, "derive", slow)
    t0 = time.monotonic()
    assert _go_derive(tmp_path, timeout=1) == (None, "derive wall-clock limit")
    assert time.monotonic() - t0 < 20
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 10
    while not _gone(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert _gone(pid), f"sleep {pid} survived the derive child's group"
    assert "wall-clock limit (1 s): killed" in (tmp_path / "derive.log").read_text()


def test_run_derive_crash_is_reported(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise ValueError("boom")

    monkeypatch.setattr(job.derive, "derive", boom)
    res, error = _go_derive(tmp_path)
    assert res is None
    assert error.startswith("derive crashed: ") and "ValueError: boom" in error


def test_run_derive_derive_error_and_result(tmp_path, monkeypatch):
    def refuse(*a, **kw):
        raise job.derive.DeriveError("not a trace")

    monkeypatch.setattr(job.derive, "derive", refuse)
    assert _go_derive(tmp_path) == (None, "not a trace")

    want = job.derive.DeriveResult(
        samplers={"centre-v1": {"frames": 2}}, trace_sha="e" * 64, uo_out_xxh3_128="f" * 64,
        uo_out_xxh3_128_clocks=(0, 9), tb_v1_check="off", error="a sampler error", cpu_seconds=1.5,
        pngs_written=1, pngs_linked=0, info={"blocks": "1", "clocks": "9"})
    monkeypatch.setattr(job.derive, "derive", lambda *a, **kw: want)
    assert _go_derive(tmp_path) == (want, "a sampler error")


@pytest.mark.parametrize("text, rc, want", [
    ("", 124, "wall-clock limit"),
    ('{"status": "o', 124, "wall-clock limit"),
    ("", 1, "model exited 1 with an empty timing.json"),
    ('{"status": "o', 1, "model exited 1 with a truncated timing.json"),
    (None, 3, "model exited 3 without timing.json"),
    ('{"status": "ok"}', 0, "model exited 0 without a trace"),
])
def test_sim_problem(tmp_path, text, rc, want):
    if text is not None:
        (tmp_path / "timing.json").write_text(text)
    assert job._sim_problem(tmp_path, rc, tmp_path / "trace.vgch.zst") == want


def test_encode_refuses_truncated_timing(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "timing.json").write_text('{"status": "ok", "fra')
    error = job.encode(tmp_path, tmp_path / "videos", tmp_path / "sim.log", {"ffmpeg": "unused"}, "s_m")
    assert error.startswith("timing.json cannot be read: ")
    assert not (tmp_path / "videos").exists()


def test_trace_fast_path(tmp_path):
    log = tmp_path / "sim.log"
    filler = "tb: sync at clock 1\n" * 1000          # well past the 4000-character tail
    log.write_text("$ Vtop --trace x\n" + filler)
    assert job.trace_fast_path(log) is True
    log.write_text("$ Vtop --trace x\n" + job.TRACE_FALLBACK + "\n" + filler)
    assert job.trace_fast_path(log) is False
    log.write_text(f"note: {job.TRACE_FALLBACK}, quoted, not printed by tb.cpp\n")
    assert job.trace_fast_path(log) is True


def _fake_job(tmp_path, monkeypatch, shuttle: str = "tst"):
    """A root with one target whose stages are all stubs; returns (argv, work)."""
    import types

    root = tmp_path / "root"
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "HARNESS_VERSION").write_text("test\n")
    target = {"id": f"{shuttle}/tt_um_x", "shuttle": shuttle, "macro": "tt_um_x", "repo": "unused",
              "commit": "unused", "top_module": "tt_um_x", "source_files": [], "clock_hz": 0, "pinout": {}}
    (root / "targets.json").write_text(json.dumps({"targets": [target]}))
    frames_root = tmp_path / "frames"
    (frames_root / shuttle / "tt_um_x").mkdir(parents=True)
    monkeypatch.setattr(job.hostconf, "load", lambda *a, **kw: types.SimpleNamespace(frames_root=frames_root))
    monkeypatch.setattr(job, "fetch", lambda *a, **kw: None)
    monkeypatch.setattr(job, "build", lambda *a, **kw: None)
    monkeypatch.setattr(job, "encode", lambda *a, **kw: pytest.fail("must not encode"))
    monkeypatch.setattr(job.publish, "install", lambda *a, **kw: pytest.fail("must not publish"))
    monkeypatch.setattr(job.derive, "derive", lambda *a, **kw: pytest.fail("must not derive"))
    argv = ["job.py", "--targets", str(root / "targets.json"), "--id", target["id"], "--root", str(root),
            "--videos", str(tmp_path / "videos")]
    monkeypatch.setattr(sys, "argv", argv)
    return root / "work" / shuttle / "tt_um_x"


def _result(work: Path) -> dict:
    return json.loads((work / "result.json").read_text())


def test_stage_crash_is_recorded_and_nothing_published(tmp_path, monkeypatch):
    work = _fake_job(tmp_path, monkeypatch)

    def crash(*a, trace, **kw):
        trace.write_bytes(b"half a trace")
        raise RuntimeError("kaboom")

    monkeypatch.setattr(job, "simulate", crash)
    assert job.main() == 1
    r = _result(work)
    assert r["error"] == "stage crashed: simulate: RuntimeError: kaboom"
    assert r["stage"] == "simulate" and r["published"] is False
    assert "RuntimeError: kaboom" in r["traceback"]
    assert not (work / "scratch").exists()


def test_hostconf_oserror_is_setup(tmp_path, monkeypatch):
    work = _fake_job(tmp_path, monkeypatch)

    def denied(*a, **kw):
        raise PermissionError(13, "Permission denied", "host.toml")

    monkeypatch.setattr(job.hostconf, "load", denied)
    monkeypatch.setattr(job, "fetch", lambda *a, **kw: pytest.fail("must not fetch"))
    assert job.main() == 1
    r = _result(work)
    assert r["stage"] == "setup" and r["error"].startswith("host.toml: ") and r["published"] is False


def test_sigterm_records_and_cleans_up(tmp_path, monkeypatch):
    import os
    import signal
    import time

    work = _fake_job(tmp_path, monkeypatch)

    def terminated(*a, trace, **kw):
        trace.write_bytes(b"trace")
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(30)
        pytest.fail("SIGTERM did not interrupt the job")

    monkeypatch.setattr(job, "simulate", terminated)
    before = signal.getsignal(signal.SIGTERM)
    assert job.main() == 128 + signal.SIGTERM
    assert signal.getsignal(signal.SIGTERM) is before
    r = _result(work)
    assert r["error"] == "terminated by SIGTERM during simulate" and r["published"] is False
    assert not (work / "scratch").exists()
