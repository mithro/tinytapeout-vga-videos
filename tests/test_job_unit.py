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
        return None

    def derive(trace, out, stem, **kw):
        (out / "centre-v1").mkdir()
        (out / "centre-v1" / "frames.txt").write_text("frames.txt\n")
        return job.derive.DeriveResult(
            samplers={"centre-v1": {"sampler_status": "ok", "frames": 3}}, trace_sha="c" * 64,
            uo_out_sha256="d" * 64, uo_out_sha256_clocks=(0, 100), tb_v1_check="off", error=None,
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
    assert not (work / "scratch").exists()
    assert sorted(p.name for p in (work / "kept").iterdir()) == ["centre-v1", "testpatterns_tt_um_vgacal_bars_trace.vgch.zst"]
    assert not (tmp_path / "videos").exists()
