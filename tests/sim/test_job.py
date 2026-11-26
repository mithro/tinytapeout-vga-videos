# SPDX-License-Identifier: Apache-2.0
"""job.py end to end on the test designs: trace, derive, encode, publish, and the tb-v1 rule."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from tests.sim import jobroot, vgch
from tests.sim.helpers import info
from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

import job  # noqa: E402

pytestmark = pytest.mark.sim

FNV = "frame_hashes.fnv1a64-tb2026-rgb888.txt"
CENTRE_HASHES = "frame_hashes.sha256-rgb6.txt"


@pytest.fixture
def root(dev, tmp_path):
    dev.require("verilator", "vgacap_sample", "tracetool")
    return jobroot.make_root(tmp_path, dev)


@pytest.fixture
def go(root, monkeypatch):
    """Run job.main() for a design in-process; return (exit code, result.json)."""

    def run(design: str, *extra: str, seconds: str = "0.2") -> tuple[int, dict]:
        argv = ["job.py", "--targets", str(root / "targets.json"), "--id", jobroot.target_id(design),
                "--root", str(root), "--videos", str(root.parent / "videos"),
                "--seconds", seconds, "--calib-seconds", "0.1", "--no-qspi", *extra]
        monkeypatch.setattr(sys, "argv", argv)
        rc = job.main()
        return rc, json.loads((jobroot.work(root, design) / "result.json").read_text())

    return run


def stem(design: str) -> str:
    return f"{jobroot.SHUTTLE}_{jobroot.macro_for(design)}"


def tree(path: Path) -> dict[str, bytes | None]:
    """Every entry under `path`: file bytes, or None for a directory."""
    if not path.exists():
        return {}
    out = {}
    for p in sorted(path.rglob("*")):
        out[str(p.relative_to(path))] = None if p.is_dir() else p.read_bytes()
    return out


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frames_txt(path: Path) -> dict[str, str]:
    """The `key: value` header lines of a frames.txt."""
    out = {}
    for line in path.read_text().splitlines():
        k, sep, v = line.partition(": ")
        if sep and k not in out:
            out[k] = v
    return out


def test_job_publishes_trace_and_centre_v1(root, go, dev):
    rc, r = go("bars640")
    assert (rc, r["error"]) == (0, None), r.get("sim_log_tail")
    assert r["stage"] == "publish" and r["published"] is True
    pub = jobroot.published(root, "bars640")
    trace = pub / f"{stem('bars640')}_trace.vgch.zst"
    assert trace.is_file()
    for name in ("frames.txt", CENTRE_HASHES, f"{stem('bars640')}_centre-v1_frames.rgb6.zst", "index.html"):
        assert (pub / "centre-v1" / name).is_file(), name
    assert (pub / "centre-v1" / "png" / "000000.png").is_file()
    assert not (pub / "tb-v1").exists()
    # result.json
    t = r["trace"]
    ti = info(dev, trace)
    assert t == {"file": trace.name, "sha256": sha(trace), "bytes": trace.stat().st_size,
                 "blocks": int(ti["blocks"]), "clocks": int(ti["clocks"]),
                 "uo_out_sha256": t["uo_out_sha256"], "uo_out_sha256_clocks": [0, int(ti["clocks"])],
                 "fast_path": True}
    assert len(t["uo_out_sha256"]) == 64 and t["blocks"] >= 1
    assert r["harness"] == "test"
    assert r["tb_v1"] == {"state": "none", "trace_sha": None, "dropped": False}
    assert r["tb_v1_check"] == "off"
    assert r["test_hooks"] is False
    assert r["samplers"]["centre-v1"]["sampler_status"] == "ok"
    assert set(r["samplers"]) == {"centre-v1"}
    assert {"fetch", "build", "simulate", "derive", "encode", "publish"} <= set(r["timings"])
    assert r["derive_cpu_seconds"] > 0
    assert "frame_hashes_count" not in r["timing"]
    assert any(n.endswith("_60s.mp4") for n in r["videos"])
    # The trace's META(open).
    assert ti["open.project"] == jobroot.target_id("bars640")
    assert ti["open.override"] == "none"
    assert ti["open.simulator"].startswith("Verilator")
    assert ti["open.harness"] == "test"
    assert ti["close.status"] == "ok"
    # work/: frames.txt kept for collect; no scratch left.
    work = jobroot.work(root, "bars640")
    assert (work / "frames" / "centre-v1" / "frames.txt").read_bytes() == (pub / "centre-v1" / "frames.txt").read_bytes()
    assert sorted(p.name for p in (work / "frames").rglob("*")) == ["centre-v1", "frames.txt"]
    assert not (work / "scratch").exists()
    assert not (work / "out").exists()
    # Published modes, whatever the umask of the caller.
    for p in [pub, *pub.rglob("*")]:
        mode = stat.S_IMODE(p.stat().st_mode)
        assert mode == (0o755 if p.is_dir() else 0o644), (p, oct(mode))
    changed = (root.parent / "staging" / "changed.log").read_text().splitlines()
    assert [line.split(" ", 1)[1] for line in changed] == [jobroot.target_id("bars640")]


def test_job_tb_v1_on_request(root, go):
    rc, r = go("bars640", "--tb-v1")
    assert (rc, r["error"]) == (0, None), r.get("derive_log_tail")
    assert r["tb_v1"] == {"state": "current", "trace_sha": r["trace"]["sha256"], "dropped": False}
    assert r["tb_v1_check"] == "match"
    assert set(r["samplers"]) == {"centre-v1", "tb-v1"}
    pub = jobroot.published(root, "bars640")
    assert (pub / "tb-v1" / FNV).is_file()
    assert (pub / "tb-v1" / "TRACE_SHA256").read_text() == r["trace"]["sha256"] + "\n"
    # C4: the trace's SHA stays out of what collect brings into git.
    frames = jobroot.work(root, "bars640") / "frames" / "tb-v1"
    assert sorted(p.name for p in frames.iterdir()) == sorted(["frames.txt", FNV])
    assert (frames / FNV).read_bytes() == (pub / "tb-v1" / FNV).read_bytes()
    assert (frames / "frames.txt").read_bytes() == (pub / "tb-v1" / "frames.txt").read_bytes()


def test_job_default_rerun_keeps_tb_v1_stale(root, go):
    rc, first = go("bars640", "--tb-v1")
    assert (rc, first["error"]) == (0, None)
    pub = jobroot.published(root, "bars640")
    frames = jobroot.work(root, "bars640") / "frames"
    tb_pub, tb_work = tree(pub / "tb-v1"), tree(frames / "tb-v1")
    centre_before = (pub / "centre-v1" / "frames.txt").read_bytes()
    assert tb_pub and tb_work

    src = (jobroot.DESIGNS / "bars640.v").read_text()
    changed = src.replace("active ? bar : 3'b000, vsync, active ? bar : 3'b000",
                          "active ? ~bar : 3'b000, vsync, active ? ~bar : 3'b000")
    assert changed != src
    jobroot.change_design(root, "bars640", changed)
    rc, second = go("bars640")
    assert (rc, second["error"]) == (0, None)
    assert second["trace"]["sha256"] != first["trace"]["sha256"]
    assert second["tb_v1"] == {"state": "stale", "trace_sha": first["trace"]["sha256"], "dropped": False}
    assert second["tb_v1_check"] == "off"
    assert tree(pub / "tb-v1") == tb_pub
    assert tree(frames / "tb-v1") == tb_work
    assert (pub / "centre-v1" / "frames.txt").read_bytes() != centre_before
    assert (frames / "centre-v1" / "frames.txt").read_bytes() == (pub / "centre-v1" / "frames.txt").read_bytes()
    assert sha(pub / f"{stem('bars640')}_trace.vgch.zst") == second["trace"]["sha256"]


def test_job_default_rerun_keeps_seeded_tb_v1(root, go):
    seeded = jobroot.work(root, "bars640") / "frames" / "tb-v1" / FNV
    seeded.parent.mkdir(parents=True)
    seeded.write_text("# converted before traces existed\n")
    before = tree(seeded.parent)
    rc, r = go("bars640")
    assert (rc, r["error"]) == (0, None)
    assert tree(seeded.parent) == before
    assert r["tb_v1"] == {"state": "stale", "trace_sha": None, "dropped": False}
    assert not (jobroot.published(root, "bars640") / "tb-v1").exists()


def test_job_drop_tb_v1(root, go):
    rc, _ = go("bars640", "--tb-v1")
    assert rc == 0
    with pytest.raises(SystemExit) as e:
        go("bars640", "--tb-v1", "--drop-tb-v1")
    assert e.value.code == 2
    rc, r = go("bars640", "--drop-tb-v1")
    assert (rc, r["error"]) == (0, None)
    assert r["tb_v1"] == {"state": "none", "trace_sha": None, "dropped": True}
    assert not (jobroot.published(root, "bars640") / "tb-v1").exists()
    assert not (jobroot.work(root, "bars640") / "frames" / "tb-v1").exists()
    assert (jobroot.work(root, "bars640") / "frames" / "centre-v1" / "frames.txt").is_file()


def test_job_probe_keeps_only_the_rerun_trace(root, go, dev):
    rc, r = go("needs_ui2")
    assert (rc, r["error"]) == (0, None), r.get("sim_log_tail")
    assert r["auto_ui_in"] == 4
    assert r["samplers"]["centre-v1"]["sampler_status"] == "ok"
    pub = jobroot.published(root, "needs_ui2")
    traces = sorted(p.name for p in pub.rglob("*.vgch*"))
    assert traces == [f"{stem('needs_ui2')}_trace.vgch.zst"]
    t = vgch.read(pub / traces[0], dev)
    assert t.value(0) >> 24 & 0xff == 0x04
    assert {v >> 24 & 0xff for _, v, _ in t.runs} == {0x04}
    assert not (jobroot.work(root, "needs_ui2") / "probe").exists()


def test_job_killed_model_samples_truncated_trace(root, go, monkeypatch):
    monkeypatch.setenv("TTVGA_TB_IGNORE_SIGTERM", "1")
    rc, r = go("noisy", "--test-hooks", "--timeout", "15", "--grace", "1", seconds="30")
    assert rc == 1
    assert r["error"] == "wall-clock limit", r.get("sim_log_tail")
    assert r["published"] is True
    assert r["test_hooks"] is True
    assert "[killed]" in r["sim_log_tail"]
    assert "encode" not in r["timings"]
    pub = jobroot.published(root, "noisy")
    assert frames_txt(pub / "centre-v1" / "frames.txt")["status"] == "truncated"
    assert r["trace"]["blocks"] >= 1
    work = jobroot.work(root, "noisy")
    assert not (work / "scratch").exists()
    assert (work / "frames" / "centre-v1" / "frames.txt").is_file()


def test_job_no_sync_publishes_trace_only(root, go):
    rc, r = go("nosync")
    assert (rc, r["error"]) == (0, None), r.get("sim_log_tail")
    assert r["timing"]["status"] == "no-sync"
    assert r["auto_ui_in"] is None
    assert r["published"] is True and r["stage"] == "publish"
    assert "encode" not in r["timings"]
    assert r["videos"] == {}
    assert r["samplers"]["centre-v1"]["frames"] == 0
    pub = jobroot.published(root, "nosync")
    assert (pub / f"{stem('nosync')}_trace.vgch.zst").is_file()
    assert frames_txt(pub / "centre-v1" / "frames.txt")["frames"] == "0"
    assert list((pub / "centre-v1" / "png").iterdir()) == []


def test_job_failure_keeps_previous_output(root, go):
    rc, _ = go("bars640")
    assert rc == 0
    pub = jobroot.published(root, "bars640")
    frames = jobroot.work(root, "bars640") / "frames"
    before_pub, before_frames, inode = tree(pub), tree(frames), pub.stat().st_ino
    jobroot.set_override(root, "bars640", {"skip": "skipped for the test"})
    rc, r = go("bars640")
    assert rc == 1
    assert r["error"] == "skipped for the test"
    assert r["published"] is False
    assert tree(pub) == before_pub and pub.stat().st_ino == inode
    assert tree(frames) == before_frames
    assert not (jobroot.work(root, "bars640") / "scratch").exists()


def test_job_mismatch_publishes_nothing(root, go, monkeypatch):
    rc, _ = go("bars640", "--tb-v1")
    assert rc == 0
    pub = jobroot.published(root, "bars640")
    frames = jobroot.work(root, "bars640") / "frames"
    before_pub, before_frames = tree(pub), tree(frames)
    changed_log = (root.parent / "staging" / "changed.log").read_text()
    real = job.derive.derive

    def mismatched(*a, **kw):
        res = real(*a, **kw)
        return dataclasses.replace(res, tb_v1_check="mismatch", error="tb-v1 differs from tb.cpp at frame 3")

    monkeypatch.setattr(job.derive, "derive", mismatched)
    rc, r = go("bars640", "--tb-v1")
    assert rc == 1
    assert r["error"] == "tb-v1 differs from tb.cpp at frame 3"
    assert r["tb_v1_check"] == "mismatch"
    assert r["published"] is False and r["stage"] == "derive"
    assert tree(pub) == before_pub
    assert tree(frames) == before_frames
    assert (root.parent / "staging" / "changed.log").read_text() == changed_log
    assert not (jobroot.work(root, "bars640") / "scratch").exists()


def test_job_encode_failure_still_publishes(root, go):
    ffmpeg = root / "tools" / "ffmpeg" / "bin" / "ffmpeg"
    ffmpeg.unlink()
    ffmpeg.write_text("#!/bin/sh\necho 'ffmpeg: broken for the test' >&2\nexit 1\n")
    ffmpeg.chmod(0o755)
    rc, r = go("bars640")
    assert rc == 1
    assert r["stage"] == "publish" and r["published"] is True
    assert r["timing"]["ffmpeg_status"] != 0
    assert r["error"] == f"the capture's ffmpeg failed (ffmpeg_status {r['timing']['ffmpeg_status']})"
    pub = jobroot.published(root, "bars640")
    assert (pub / f"{stem('bars640')}_trace.vgch.zst").is_file()
    assert (pub / "centre-v1" / "frames.txt").is_file()
    assert r["samplers"]["centre-v1"]["frames"] > 0
    assert os.listdir(pub / "centre-v1" / "png")


def test_job_trace_fast_path_false_on_forced_fallback(root, go):
    """With tb.cpp's forced fallback compiled in (a test hook), result.json says trace.fast_path false."""
    jobroot.set_override(root, "bars640", {"verilator_flags": ["-CFLAGS", "-DTTVGA_TEST_FORCE_FALLBACK"]})
    rc, r = go("bars640", "--test-hooks")
    assert (rc, r["error"]) == (0, None), r.get("build_log_tail")
    assert r["test_hooks"] is True
    assert r["trace"]["fast_path"] is False
    # The line comes early; encode output pushes it out of the 4000-character tail.
    assert job.TRACE_FALLBACK in (jobroot.work(root, "bars640") / "sim.log").read_text()
    assert r["published"] is True
