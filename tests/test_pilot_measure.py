# SPDX-License-Identifier: Apache-2.0
"""scripts/pilot_measure.py: the pilot's parsing, re-run commands, ETA and budget tables (Task 20)."""

from __future__ import annotations

import importlib.util
import json

import pytest

from ttvga import ROOT

SCRIPT = ROOT / "scripts" / "pilot_measure.py"


@pytest.fixture(scope="module")
def pm():
    spec = importlib.util.spec_from_file_location("pilot_measure", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TIME_V = """\tCommand being timed: "/w/build/Vtop --clock-hz 25000000"
\tUser time (seconds): 420.51
\tSystem time (seconds): 3.20
\tPercent of CPU this job got: 99%
\tElapsed (wall clock) time (h:mm:ss or m:ss): 7:08.52
\tMaximum resident set size (kbytes): 51234
\tExit status: 0
"""


def test_parse_time_v_minutes(pm):
    t = pm.parse_time_v(TIME_V)
    assert t == {"wall_s": 428.52, "user_s": 420.51, "sys_s": 3.2, "cpu_s": 423.71, "max_rss_kb": 51234,
                 "exit_status": 0, "signal": None}


def test_parse_time_v_hours_and_signal(pm):
    text = ("Command terminated by signal 9\n" + TIME_V.replace("7:08.52", "1:02:03.50")
            .replace("Exit status: 0", "Exit status: 0"))
    t = pm.parse_time_v(text)
    assert t["wall_s"] == 3723.5
    assert t["signal"] == 9


def test_parse_time_v_missing_field_raises(pm):
    with pytest.raises(ValueError):
        pm.parse_time_v("\tUser time (seconds): 1.0\n")


SIM_LOG = """
$ /w/build/Vtop --clock-hz 25000000 --seconds 60.0 --calib-seconds 1.0 --out /w/out --ffmpeg /t/ffmpeg --ui-in 4 --trace /w/scratch/x_trace.vgch.zst --meta project=tt08/x --meta override=tt08/x.json sha256:0123 --meta simulator=Verilator 5.053 devel (mod) --meta harness=abc
tb: something
[exit 0]

$ /w/build/Vtop --clock-hz 25000000 --seconds 0.05 --calib-seconds 1.0 --out /w/probe --ffmpeg /t/ffmpeg --ui-in 1 --quiet
[exit 0]

$ /t/ffmpeg -hide_banner -i /w/out/capture.avi out.mp4
[exit 0]
"""


def test_model_argv_takes_the_last_traced_model_run(pm):
    argv = pm.model_argv(SIM_LOG)
    assert argv[0] == "/w/build/Vtop"
    assert "--quiet" not in argv
    assert argv[argv.index("--trace") + 1] == "/w/scratch/x_trace.vgch.zst"


def test_model_argv_none_without_a_model_line(pm):
    with pytest.raises(ValueError):
        pm.model_argv("$ /t/ffmpeg -i a b\n")


def test_rerun_argv_replaces_out_and_trace(pm):
    argv = pm.model_argv(SIM_LOG)
    plain = pm.rerun_argv(argv, "/p/run0", trace=None)
    assert plain == ["/w/build/Vtop", "--clock-hz", "25000000", "--seconds", "60.0", "--calib-seconds", "1.0",
                     "--ffmpeg", "/t/ffmpeg", "--ui-in", "4", "--out", "/p/run0"]
    traced = pm.rerun_argv(argv, "/p/run1", trace="/p/run1/t.vgch.zst")
    assert traced[-12:] == ["--out", "/p/run1", "--trace", "/p/run1/t.vgch.zst",
                            "--meta", "project=tt08/x", "--meta", "override=tt08/x.json sha256:0123",
                            "--meta", "simulator=Verilator 5.053 devel (mod)", "--meta", "harness=abc"]


RSYNC_LOG = """2026/11/27 11:33:04 [100] building file list
2026/11/27 11:33:28 [100] Number of files: 62,991 (reg: 62,203, dir: 788)
2026/11/27 11:33:28 [100] total size is 102.68G  speedup is 56,583.99
2026/11/27 11:38:04 [200] building file list
2026/11/27 11:38:04 [201] some other process line
2026/11/27 11:38:31 [200] Number of files: 70,001 (reg: 69,000, dir: 1,001)
2026/11/27 11:38:32 [200] total size is 103.00G  speedup is 1.00
2026/11/27 11:43:04 [300] building file list
"""


def test_parse_rsync_log_runs(pm):
    runs = pm.parse_rsync_log(RSYNC_LOG)
    assert [(r["pid"], r["files"], r["duration_s"]) for r in runs] == [(100, 62991, 24.0), (200, 70001, 28.0)]
    assert runs[1]["start"] == "2026-11-27T11:38:04"


def test_min_free_rule_rounds_up_to_10(pm):
    # 24 * 1.2 GB * 2 = 57.6 -> 60
    assert pm.min_free_root_gb(1.2e9) == 60
    assert pm.min_free_root_gb(1.25e9) == 60
    assert pm.min_free_root_gb(1.0e9) == 50   # 48 -> 50
    assert pm.min_free_root_gb(2.5e9) == 120  # exactly 120


def test_eta_uses_the_slowest_project(pm):
    plan = {"a": [100.0, 10.0, 10.0], "b": [1000.0, 500.0, 500.0]}
    done = {"a": {"done": 3, "elapsed_in_phase": 0.0}, "b": {"done": 1, "elapsed_in_phase": 100.0}}
    remaining_runs, remaining_s = pm.eta(plan, done)
    assert remaining_runs == 2
    assert remaining_s == pytest.approx(900.0)


def _raw(walls, cpus, *, derive_cpu=5.0, clocks=1_000_000_000, frames=3600, distinct=3000):
    runs = [{"traced": traced, "time": {"wall_s": w, "cpu_s": c, "max_rss_kb": 1000}}
            for traced, w, c in zip([False, True, False, True], walls, cpus)]
    return {"id": "tt08/x", "runs": runs, "job": {"time": {"wall_s": 1000.0, "cpu_s": 900.0, "max_rss_kb": 200000}},
            "result": {"derive_cpu_seconds": derive_cpu, "trace": {"clocks": clocks},
                       "samplers": {"centre-v1": {"frames": frames, "distinct_frames": distinct}},
                       "timings": {"derive": 6.0, "publish": 2.0}},
            "poll": {"job": {"work_bytes_peak": 2.0e9, "memory_peak": 3.0e8, "tasks_peak": 9}},
            "scope": {"memory_peak": 4.0e8, "tasks_peak": 12}}


def test_recording_row(pm):
    row = pm.recording_row(_raw([100.0, 104.0, 102.0, 106.0], [100.0, 105.0, 101.0, 106.0]))
    # without: mean 101, with: mean 105 -> +3.96%, 4 s over 1e9 clocks = 4 ns
    assert row["overhead_pct"] == pytest.approx(400 / 101, rel=1e-6)
    assert row["ns_per_clock"] == pytest.approx(4.0)
    assert row["ok"] is True


def test_postsim_row(pm):
    row = pm.postsim_row(_raw([100.0, 104.0, 102.0, 106.0], [100.0, 105.0, 100.0, 105.0], derive_cpu=2.0))
    # compressor 5 + derive 2 over 100 = 7%
    assert row["compressor_cpu_s"] == pytest.approx(5.0)
    assert row["post_pct"] == pytest.approx(7.0)
    assert row["budget_s"] == pytest.approx(5.0)
    assert row["ok"] is False


def test_report_markdown_has_one_table_per_target(pm, tmp_path):
    (tmp_path / "tt08__x.json").write_text(json.dumps(_raw([100.0, 104.0, 102.0, 106.0], [100.0, 105.0, 100.0, 105.0])))
    md = pm.report(tmp_path)
    for heading in ("Recording", "Post-simulation CPU", "Memory per job", "Root-volume peak per job"):
        assert f"## {heading}" in md
    assert "| tt08/x |" in md
    assert "min_free_root_gb = 100" in md   # 24 * 2.0 GB * 2 = 96 -> 100
    assert "lowest seen" not in md
    (tmp_path / "DONE").write_text("2026-11-27T04:28:18+00:00\nroot_free_min_bytes 772000000000\n")
    assert "lowest seen by the 5 s polls during the pilot: 772 GB" in pm.report(tmp_path)


def test_redact_replaces_host_paths(pm):
    text = '{"a": "/backups/st/x.new/\\n", "b": "/srv/frames/tt08/x", "c": "/home/u/ttvga/work"}'
    out = pm.redact(text, {"/backups/st": "<staging_dir>", "/srv/frames": "<frames_root>", "/home/u": "~"})
    assert out == '{"a": "<staging_dir>/x.new/\\n", "b": "<frames_root>/tt08/x", "c": "~/ttvga/work"}'
