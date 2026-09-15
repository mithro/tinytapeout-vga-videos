# SPDX-License-Identifier: Apache-2.0
from ttvga.analyze import verdict


def timing(**kw):
    base = {"status": "ok", "frames": 3600, "distinct_frames": 3000, "uniform_frames": 0, "black_frames": 0,
            "mode": "640x480@60", "width": 640, "height": 480, "fps": 59.94}
    base.update(kw)
    return base


def test_stage_failures():
    assert verdict({"stage": "skipped", "error": "analog project"}) == ("skipped", "analog project")
    assert verdict({"stage": "fetch", "error": "fetch failed"})[0] == "fetch-failed"
    assert verdict({"stage": "build", "error": "verilator failed"})[0] == "build-failed"
    assert verdict({"stage": "simulate", "error": "wall-clock limit"})[0] == "sim-timeout"
    assert verdict({"stage": "simulate", "error": "model exited 1 without timing.json"})[0] == "sim-crashed"


def test_timing_status_wins_over_encode_error():
    r = {"stage": "simulate", "error": None, "timing": {"status": "no-sync", "hsync_transitions": 1}}
    assert verdict(r)[0] == "no-sync"
    r = {"stage": "encode", "error": "no 60s.avi", "timing": {"status": "bad-timing"}}
    assert verdict(r)[0] == "bad-timing"
    r = {"stage": "encode", "error": None, "timing": timing(status="unstable-sync")}
    assert verdict(r)[0] == "unstable-sync"


def test_content_verdicts():
    ok = {"stage": "encode", "error": None, "timing": timing()}
    assert verdict(ok)[0] == "ok"
    blank = {"stage": "encode", "error": None, "timing": timing(uniform_frames=3500, black_frames=3500)}
    assert verdict(blank) == ("blank", "3500/3600 frames are black (640x480@60)")
    static = {"stage": "encode", "error": None, "timing": timing(distinct_frames=1)}
    assert verdict(static)[0] == "static"
    assert verdict({"stage": "encode", "error": "poster failed", "timing": timing()})[0] == "encode-failed"
