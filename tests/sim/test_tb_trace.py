# SPDX-License-Identifier: Apache-2.0
"""tb.cpp's raw pin trace (`--trace`, `--meta`), its META records and tb_frame_hashes.txt."""

from __future__ import annotations

import json
import os
import re
import resource
import signal
import subprocess
import time
from pathlib import Path

import pytest

from tests.sim import vgch
from tests.sim.helpers import HARNESS, base_args, meta_args, run, timing

pytestmark = pytest.mark.sim

CLK, RST, ENA = 1 << 42, 1 << 40, 1 << 41


def test_trace_pins_match_the_design(models, dev, tmp_path):
    model = models("uio_echo")
    p = run(model, dev, tmp_path, "--ui-in", "0x5a", design="uio_echo")
    assert p.returncode == 3, p.stderr     # no sync: uo_out is constant
    t = vgch.read(tmp_path / "trace.vgch.zst", dev)
    h = t.header
    assert (h.version, h.sample_bits, h.mode, h.samples_per_clock, h.clock_bit, h.clock_first) == (2, 43, 2, 2, 42, 0)
    assert h.clock_hz == 25_175_000
    assert t.samples >= 40
    for first, v, r in t.runs:
        for n in {first, first + r - 1}:   # a run's samples differ only in the clock bit
            s = t.value(n)
            assert bool(s & RST) == (n >= 20), n
            assert s & ENA, n
            assert (s >> 24) & 0xFF == 0x5A, n
            assert (s >> 8) & 0xF0 == 0x50, n
            assert (s >> 16) & 0xFF == 0xF0, n
            assert bool(s & CLK) == bool(n & 1), n
        # The value a run carries has the clock bit of its first sample.
        assert bool(v & CLK) == bool(first & 1)
    # The reset edge is a run boundary: samples 0-19 low, 20 on high.
    assert any(first == 20 for first, _, _ in t.runs)


def test_trace_meta(models, dev, tmp_path):
    p = run(models("bars640"), dev, tmp_path)
    assert p.returncode == 0, p.stderr
    t = vgch.read(tmp_path / "trace.vgch.zst", dev)
    assert t.metas[0]["meta"] == "open" and t.metas[-1]["meta"] == "close"
    op = t.meta("open")
    assert op["project"] == "test/bars640"
    assert op["calib_seconds"] == "0.1"
    assert op["seconds"] == "0.2"
    assert op["layout"] == "tt-um-43"
    assert op["harness"] == HARNESS
    assert op["override"] == "none"
    assert op["simulator"] == "verilator"
    cl = t.meta("close")
    tj = timing(tmp_path)
    assert cl["status"] == "ok" == tj["status"]
    assert int(cl["frames"]) == tj["frames"] > 0
    assert int(cl["capture_after_clock"]) == tj["capture_after_clock"]
    assert t.samples == 2 * tj["clocks_simulated"]


def test_trace_no_sync_is_closed(models, dev, tmp_path):
    p = run(models("nosync"), dev, tmp_path, design="nosync")
    assert p.returncode == 3, p.stderr
    cl = vgch.read(tmp_path / "trace.vgch.zst", dev).meta("close")
    assert cl["status"] == "no-sync" == timing(tmp_path)["status"]
    assert cl["frames"] == "0"
    assert (tmp_path / "tb_frame_hashes.txt").read_text() == ""


def _sigterm_after(model: Path, dev, out: Path, env: dict | None = None) -> tuple[int, str]:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(model)] + base_args(dev, out) + ["--trace", str(out / "trace.vgch.zst")] + meta_args("bars640")
    cmd += ["--seconds", "30"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    time.sleep(2)
    assert p.poll() is None, "the model finished before SIGTERM"
    p.send_signal(signal.SIGTERM)
    try:
        output, _ = p.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        p.kill()
        output, _ = p.communicate()
        pytest.fail("the model did not stop on SIGTERM")
    return p.returncode, output


def test_trace_sigterm_is_closed(models, dev, tmp_path):
    rc, output = _sigterm_after(models("bars640"), dev, tmp_path)
    assert rc == 3, output
    t = vgch.read(tmp_path / "trace.vgch.zst", dev)
    assert t.metas[-1]["meta"] == "close"
    assert t.meta("close")["status"] == "sim-timeout" == timing(tmp_path)["status"]


def test_tb_frame_hashes_moved(models, dev, tmp_path):
    p = run(models("bars640"), dev, tmp_path)
    assert p.returncode == 0, p.stderr
    tj = timing(tmp_path)
    assert "frame_hashes" not in tj
    lines = (tmp_path / "tb_frame_hashes.txt").read_text().splitlines()
    assert len(lines) == tj["frames"] > 8
    assert all(re.fullmatch(r"[0-9a-f]{16}", line) for line in lines)
    # The bars rotate by one bar a frame: a cycle of eight different frames.
    assert len(set(lines)) == tj["distinct_frames"] == 8
    assert lines[8:] == lines[:-8]


def test_trace_refuses_fractional_clock(models, dev, tmp_path):
    p = run(models("bars640"), dev, tmp_path, "--clock-hz", "25175000.5")
    assert p.returncode == 2, p.stderr
    assert "clock" in p.stderr
    assert not (tmp_path / "timing.json").exists()
    assert not (tmp_path / "trace.vgch.zst").exists()


def test_trace_refuses_duplicate_meta(models, dev, tmp_path):
    p = run(models("bars640"), dev, tmp_path, "--meta", "project=test/other")
    assert p.returncode == 2, p.stderr
    assert "project" in p.stderr
    assert not (tmp_path / "timing.json").exists()
    assert not (tmp_path / "trace.vgch.zst").exists()


@pytest.mark.parametrize("bad", ["Project=x", "9x=1", "x", "seconds=1", "layout=tt-um-43", "a=b\nc"])
def test_trace_refuses_bad_meta(models, dev, tmp_path, bad):
    p = run(models("bars640"), dev, tmp_path, "--meta", bad)
    assert p.returncode == 2, p.stderr
    assert not (tmp_path / "trace.vgch.zst").exists()


def test_ignore_sigterm_hook_absent_in_production(models, dev, tmp_path):
    env = dict(os.environ, TTVGA_TB_IGNORE_SIGTERM="1")
    rc, output = _sigterm_after(models("bars640", test_hooks=False), dev, tmp_path, env=env)
    assert rc == 3, output
    assert vgch.read(tmp_path / "trace.vgch.zst", dev).meta("close")["status"] == "sim-timeout"


def test_ignore_sigterm_hook_works_in_test_build(models, dev, tmp_path):
    """The hook Task 9's killed-model test relies on: with it, SIGTERM does nothing."""
    out = tmp_path
    cmd = [str(models("bars640"))] + base_args(dev, out) + ["--trace", str(out / "trace.vgch.zst")]
    cmd += meta_args("bars640") + ["--seconds", "30"]
    env = dict(os.environ, TTVGA_TB_IGNORE_SIGTERM="1")
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    time.sleep(2)
    p.send_signal(signal.SIGTERM)
    time.sleep(2)
    alive = p.poll() is None
    p.kill()
    p.wait()
    assert alive


def test_trace_closed_when_ffmpeg_fails(models, dev, tmp_path):
    """popen runs a shell, so a bad --ffmpeg shows only as failed writes: the run must still finish."""
    p = run(models("bars640"), dev, tmp_path, "--ffmpeg", str(tmp_path / "no-such-ffmpeg"))
    assert p.returncode == 0, p.stderr
    assert "writing to ffmpeg failed" in p.stderr
    tj = timing(tmp_path)
    assert tj["status"] == "ok" and tj["frames"] > 0
    assert tj["ffmpeg_status"] != 0
    cl = vgch.read(tmp_path / "trace.vgch.zst", dev).meta("close")
    assert cl["status"] == "ok"
    assert int(cl["frames"]) == tj["frames"]
    assert int(cl["ffmpeg_status"]) == tj["ffmpeg_status"]
    assert len((tmp_path / "tb_frame_hashes.txt").read_text().splitlines()) == tj["frames"]


def _limit_file_size():
    # Files past 16 KiB fail with EFBIG instead of killing the model (SIGXFSZ).
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))


def test_trace_removed_when_the_writer_fails(models, dev, tmp_path):
    """A write error (here RLIMIT_FSIZE) fails the writer: exit 4, its message, and no trace file left."""
    out = tmp_path
    cmd = [str(models("playground"))] + base_args(dev, out) + ["--trace", str(out / "trace.vgch.zst")]
    cmd += meta_args("playground") + ["--seconds", "1.5"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, preexec_fn=_limit_file_size)
    assert p.returncode == 4, p.stderr
    assert "tb: trace" in p.stderr
    assert not (out / "trace.vgch.zst").exists()
    assert (out / "timing.json").exists()


def test_no_trace_without_option(models, dev, tmp_path):
    out = tmp_path / "out"
    p = run(models("bars640"), dev, out, trace=False)
    assert p.returncode == 0, p.stderr
    assert timing(out)["status"] == "ok"
    assert sorted(f.name for f in out.iterdir()) == ["tb_frame_hashes.txt", "timing.json"]
