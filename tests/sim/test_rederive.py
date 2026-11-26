# SPDX-License-Identifier: Apache-2.0
"""job.py --rederive: the published trace derived again, without fetching, building or simulating."""

from __future__ import annotations

import json
import os
import re
import signal
import sys
from pathlib import Path

import pytest

from tests.sim import jobroot
from tests.sim.test_job import frames_txt, go, root, sha, stem, tree  # noqa: F401 (fixtures)
from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

import job  # noqa: E402
import publish  # noqa: E402

pytestmark = pytest.mark.sim

KEPT_LOGS = ("build.log", "sim.log")


def frames_and_hashes(pub) -> dict[str, bytes]:
    """Every frames.txt and hash file of a published project, and its trace."""
    return {k: v for k, v in tree(pub).items()
            if v is not None and (Path(k).name in ("frames.txt", "TRACE_SHA256")
                                  or Path(k).name.startswith("frame_hashes.") or k.endswith(".vgch.zst"))}


def frames_and_hashes_of(files: dict) -> dict[str, bytes]:
    return {k: v for k, v in files.items()
            if v is not None and (Path(k).name in ("frames.txt", "TRACE_SHA256") or Path(k).name.startswith("frame_hashes."))}


def test_rederive_reproduces_frames(root, go):
    rc, first = go("bars640")
    assert (rc, first["error"]) == (0, None)
    pub = jobroot.published(root, "bars640")
    work = jobroot.work(root, "bars640")
    before = frames_and_hashes(pub)
    assert any(k.endswith("centre-v1/frames.txt") for k in before)
    work_frames = tree(work / "frames")
    logs = {name: (work / name).read_bytes() for name in KEPT_LOGS}
    changed = (root.parent / "staging" / "changed.log").read_text().splitlines()

    rc, r = go("bars640", "--rederive")
    assert (rc, r["rederive_error"]) == (0, None), r.get("derive_log_tail")
    assert frames_and_hashes(pub) == before
    assert tree(work / "frames") == work_frames
    assert r["rederived_at"] and r["rederived_at"].endswith("+00:00")
    assert r["timings"]["rederive"] >= 0
    # Only the re-derived fields change; the run's own record is kept.
    for key in ("started", "finished", "error", "stage", "timing", "videos", "tools", "published", "test_hooks"):
        assert r[key] == first[key], key
    assert {k: v for k, v in r["timings"].items() if k != "rederive"} == first["timings"]
    assert r["trace"] == first["trace"]
    assert r["samplers"] == first["samplers"]
    assert (r["tb_v1"], r["tb_v1_check"], r["harness"]) == (first["tb_v1"], "off", "test")
    # The simulation's logs stay; the trace was published again (one more changed.log line).
    assert {name: (work / name).read_bytes() for name in KEPT_LOGS} == logs
    assert len((root.parent / "staging" / "changed.log").read_text().splitlines()) == len(changed) + 1
    assert not (work / "scratch").exists()


def test_rederive_applies_centre_window(root, go):
    rc, first = go("bars640")
    assert rc == 0
    pub = jobroot.published(root, "bars640")
    assert frames_txt(pub / "centre-v1" / "frames.txt")["window_offset"] == "0 0"
    jobroot.set_override(root, "bars640", {"centre_window": {"dx": 2, "dy": 1}})
    rc, r = go("bars640", "--rederive")
    assert (rc, r["rederive_error"]) == (0, None), r.get("derive_log_tail")
    assert frames_txt(pub / "centre-v1" / "frames.txt")["window_offset"] == "2 1"
    assert r["samplers"]["centre-v1"]["sampler_status"] == "ok"
    assert r["rederive_override"].startswith(f"{jobroot.SHUTTLE}/{jobroot.macro_for('bars640')}.json sha256:")
    assert re.fullmatch(r"[0-9a-f]{40}", r["rederive_tools"]["vgacap"])
    work_txt = jobroot.work(root, "bars640") / "frames" / "centre-v1" / "frames.txt"
    assert work_txt.read_bytes() == (pub / "centre-v1" / "frames.txt").read_bytes()

    # A window that does not fit is a derive error: nothing is published and result.json says so.
    before = tree(pub)
    jobroot.set_override(root, "bars640", {"centre_window": {"dx": 400, "dy": 0}})
    rc, bad = go("bars640", "--rederive")
    assert rc == 1
    assert bad["rederive_error"].startswith("centre_window 400,0 does not fit: ")
    assert tree(pub) == before
    assert bad["rederived_at"] == r["rederived_at"]
    assert bad["samplers"] == r["samplers"]


def test_rederive_keeps_tb_v1_current(root, go):
    rc, first = go("bars640", "--tb-v1")
    assert (rc, first["tb_v1_check"]) == (0, "match")
    pub = jobroot.published(root, "bars640")
    work = jobroot.work(root, "bars640")
    tb_pub, tb_work = tree(pub / "tb-v1"), tree(work / "frames" / "tb-v1")
    assert tb_pub and tb_work

    rc, r = go("bars640", "--rederive")
    assert (rc, r["rederive_error"]) == (0, None)
    assert tree(pub / "tb-v1") == tb_pub
    assert tree(work / "frames" / "tb-v1") == tb_work
    assert r["tb_v1"] == {"state": "current", "trace_sha": first["trace"]["sha256"], "dropped": False}
    assert r["tb_v1_check"] == "off"
    assert set(r["samplers"]) == {"centre-v1"}

    # With --tb-v1 tb-v1 is made again from the same trace; with no tb.cpp hashes it is not checked.
    rc, r = go("bars640", "--rederive", "--tb-v1")
    assert (rc, r["rederive_error"]) == (0, None)
    assert r["tb_v1_check"] == "not-run"
    assert r["tb_v1"]["state"] == "current"
    assert frames_and_hashes(pub / "tb-v1") == frames_and_hashes_of(tb_pub)
    assert tree(work / "frames" / "tb-v1") == tb_work


def test_rederive_needs_a_published_trace(root, go):
    jobroot.set_override(root, "bars640", {"skip": "not this time"})
    rc, first = go("bars640")
    assert (rc, first["published"]) == (1, False)
    jobroot.set_override(root, "bars640", {})
    rc, r = go("bars640", "--rederive")
    assert rc == 1
    assert r["rederive_error"] == "no published trace"
    assert r["error"] == "not this time" and r["rederived_at"] is None
    assert not jobroot.published(root, "bars640").exists()


def test_rederive_needs_a_result(root, monkeypatch, capsys):
    argv = ["job.py", "--targets", str(root / "targets.json"), "--id", jobroot.target_id("bars640"),
            "--root", str(root), "--rederive"]
    monkeypatch.setattr(sys, "argv", argv)
    assert job.main() == 2
    assert "--rederive needs" in capsys.readouterr().err


def test_rederive_sigterm_during_swap_is_recorded(root, go, monkeypatch):
    """SIGTERM between the swap and its record is held: result.json says what was published."""
    rc, first = go("bars640")
    assert rc == 0
    real = publish.exchange

    def exchange(a, b):
        os.kill(os.getpid(), signal.SIGTERM)
        return real(a, b)

    monkeypatch.setattr(publish, "exchange", exchange)
    jobroot.set_override(root, "bars640", {"centre_window": {"dx": 2, "dy": 1}})
    rc, r = go("bars640", "--rederive")
    assert rc == 143
    assert r["rederive_error"] == "terminated by SIGTERM during publish"
    assert r["rederived_at"] is not None
    pub = jobroot.published(root, "bars640")
    assert frames_txt(pub / "centre-v1" / "frames.txt")["window_offset"] == "2 1"
    work_txt = jobroot.work(root, "bars640") / "frames" / "centre-v1" / "frames.txt"
    assert work_txt.read_bytes() == (pub / "centre-v1" / "frames.txt").read_bytes()
    assert not (jobroot.work(root, "bars640") / "scratch").exists()


def test_job_sigterm_during_swap_is_recorded(root, go, monkeypatch):
    """The same for a full run: published, tb_v1 and the trace summary are all in result.json."""
    assert go("bars640")[0] == 0   # the exchange (and so the SIGTERM) needs a published copy
    real = publish.exchange

    def exchange(a, b):
        os.kill(os.getpid(), signal.SIGTERM)
        return real(a, b)

    monkeypatch.setattr(publish, "exchange", exchange)
    rc, r = go("bars640")
    assert rc == 143
    assert r["error"] == "terminated by SIGTERM during publish"
    assert r["published"] is True
    assert r["tb_v1"] == {"state": "none", "trace_sha": None, "dropped": False}
    assert r["trace"]["sha256"] == sha(jobroot.published(root, "bars640") / f"{stem('bars640')}_trace.vgch.zst")
    assert (jobroot.work(root, "bars640") / "frames" / "centre-v1" / "frames.txt").is_file()


def test_rederive_honours_skip(root, go):
    rc, first = go("bars640")
    assert rc == 0
    pub = jobroot.published(root, "bars640")
    before = tree(pub)
    jobroot.set_override(root, "bars640", {"skip": "broken for now"})
    rc, r = go("bars640", "--rederive")
    assert rc == 1
    assert r["rederive_error"] == "broken for now"
    assert r["rederived_at"] is None and r["samplers"] == first["samplers"]
    assert tree(pub) == before
