# SPDX-License-Identifier: Apache-2.0
"""derive: vgacap-sample over a tb.cpp trace, PNGs from its pipe, pages, uohash and the tb-v1 check."""

from __future__ import annotations

import hashlib
from compression import zstd
from pathlib import Path

import pytest

from tests.sim.helpers import info, killed_trace, kv, tracetool
from tests.sim.tbv1 import FNV, simulate
from ttvga.harness import derive, pngio, vgacap_path

pytestmark = pytest.mark.sim

CENTRE_HASHES = "frame_hashes.xxh3-128-rgb6.txt"


@pytest.fixture(scope="module")
def tools(dev):
    dev.require("vgacap_sample", "tracetool")
    vgacap_path.add_src(dev.vgacap_src)
    return derive.Tools(vgacap_sample=dev.vgacap_sample, tracetool=dev.tracetool)


@pytest.fixture(scope="module")
def bars(models, dev, tmp_path_factory):
    """A bars640 run: (run directory, trace)."""
    out = tmp_path_factory.mktemp("bars640")
    simulate(models("bars640"), dev, out, "bars640")
    return out, out / "trace.vgch.zst"


def go(trace: Path, out: Path, tools, *, tb_v1=False, centre_window=None, tb_hashes=None,
       log: Path | None = None) -> derive.DeriveResult:
    return derive.derive(trace, out, "test_x", tb_v1=tb_v1, centre_window=centre_window, store_level=None,
                         tools=tools, log=log or out.parent / f"{out.name}.log", tb_hashes=tb_hashes)


def pngs(d: Path) -> list[Path]:
    return sorted((d / "png").iterdir())


def check_pngs_are_the_store(d: Path, sampler: str) -> None:
    from vgacap import framesfile

    ff = framesfile.read_frames_txt(d / "frames.txt")
    store = zstd.decompress((d / f"test_x_{sampler}_frames.rgb6.zst").read_bytes())
    n = ff.width * ff.height
    assert len(store) == len(ff.distinct) * n
    files = pngs(d)
    assert [p.name for p in files] == [f"{k:06d}.png" for k in range(len(ff.distinct))]
    for k, p in enumerate(files):
        assert pngio.read_rgb6(p) == (ff.width, ff.height, store[k * n:(k + 1) * n])
    html = (d / "index.html").read_text()
    for k in range(len(ff.distinct)):
        assert f'src="png/{k:06d}.png"' in html


def test_derive_centre_only_by_default(tools, dev, bars, tmp_path):
    _, trace = bars
    out = tmp_path / "out"
    r = go(trace, out, tools)
    assert r.error is None
    c = out / "centre-v1"
    for name in ("frames.txt", CENTRE_HASHES, "test_x_centre-v1_frames.rgb6.zst", "index.html"):
        assert (c / name).is_file(), name
    assert (c / "png").is_dir()
    assert not (out / "tb-v1").exists()
    assert r.tb_v1_check == "off"
    assert set(r.samplers) == {"centre-v1"}
    s = r.samplers["centre-v1"]
    assert s["sampler_status"] == "ok" and s["frames"] >= 2 and s["distinct_frames"] >= 1
    assert (s["width"], s["height"], s["mode"]) == (640, 480, "640x480@60")
    assert s["clocks_per_pixel"] == 1
    assert len(pngs(c)) == s["distinct_frames"] == r.pngs_written
    check_pngs_are_the_store(c, "centre-v1")
    assert r.trace_sha == hashlib.sha256(trace.read_bytes()).hexdigest()
    assert r.cpu_seconds > 0
    # uohash is tracetool's, over its default clock count clamped to the trace.
    u = kv(tracetool(dev, "uohash", trace).stdout)
    assert r.uo_out_xxh3_128 == u["uo_out_xxh3_128"]
    assert r.uo_out_xxh3_128_clocks == tuple(int(x) for x in u["uo_out_xxh3_128_clocks"].split())
    # C4: the trace hash is in no file the derive wrote except the tb-v1 sidecar.
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in (".txt", ".html"):
            assert r.trace_sha not in p.read_text(), p


def test_derive_tb_v1_on_request_links_identical_pngs(tools, bars, tmp_path):
    run_dir, trace = bars
    out = tmp_path / "out"
    r = go(trace, out, tools, tb_v1=True, tb_hashes=run_dir / "tb_frame_hashes.txt")
    assert r.error is None
    assert r.tb_v1_check == "match"
    assert set(r.samplers) == {"centre-v1", "tb-v1"}
    t = out / "tb-v1"
    assert (t / FNV).is_file() and (t / CENTRE_HASHES).is_file()
    assert (t / "TRACE_SHA256").read_text() == r.trace_sha + "\n"
    check_pngs_are_the_store(t, "tb-v1")
    check_pngs_are_the_store(out / "centre-v1", "centre-v1")
    # bars640 samples to the same pixels with both samplers: every tb-v1 PNG is a
    # hard link to the centre-v1 PNG of the same frame, not a second encoding.
    total = r.samplers["centre-v1"]["distinct_frames"] + r.samplers["tb-v1"]["distinct_frames"]
    assert r.pngs_written + r.pngs_linked == total
    assert r.pngs_linked >= 1
    c_inodes = {p.stat().st_ino for p in pngs(out / "centre-v1")}
    linked = [p for p in pngs(t) if p.stat().st_ino in c_inodes]
    assert len(linked) == r.pngs_linked
    assert all(p.stat().st_nlink >= 2 for p in linked)
    # Without tb_hashes there is nothing to compare against.
    r2 = go(trace, tmp_path / "out2", tools, tb_v1=True)
    assert (r2.tb_v1_check, r2.error) == ("not-run", None)
    # A tb_hashes path that does not exist is not-run too, and the log says why.
    missing = tmp_path / "missing.txt"
    r3 = go(trace, tmp_path / "out3", tools, tb_v1=True, tb_hashes=missing, log=tmp_path / "out3.log")
    assert (r3.tb_v1_check, r3.error) == ("not-run", None)
    assert f"tb-v1 check not run: tb.cpp's hashes {missing} do not exist" in (tmp_path / "out3.log").read_text()


def test_derive_tb_v1_mismatch_fails(tools, bars, tmp_path):
    run_dir, trace = bars
    lines = (run_dir / "tb_frame_hashes.txt").read_text().splitlines()
    assert len(lines) >= 3
    k = 2
    lines[k] = "0" * len(lines[k]) if lines[k] != "0" * len(lines[k]) else "1" * len(lines[k])
    doctored = tmp_path / "tb_frame_hashes.txt"
    doctored.write_text("\n".join(lines) + "\n")
    r = go(trace, tmp_path / "out", tools, tb_v1=True, tb_hashes=doctored)
    assert r.tb_v1_check == "mismatch"
    assert r.error == f"tb-v1 differs from tb.cpp at frame {k}"
    # A shorter tb.cpp list differs at its end.
    short = tmp_path / "short.txt"
    short.write_text("\n".join((run_dir / "tb_frame_hashes.txt").read_text().splitlines()[:-1]) + "\n")
    r = go(trace, tmp_path / "out-short", tools, tb_v1=True, tb_hashes=short)
    assert r.error == f"tb-v1 differs from tb.cpp at frame {len(lines) - 1}"


def test_derive_no_sync_writes_empty_files(tools, models, dev, tmp_path):
    run_dir = tmp_path / "run"
    simulate(models("nosync"), dev, run_dir, "nosync")
    out = tmp_path / "out"
    r = go(run_dir / "trace.vgch.zst", out, tools, tb_v1=True, tb_hashes=run_dir / "tb_frame_hashes.txt")
    assert r.error is None
    assert r.tb_v1_check == "match"
    for s in ("centre-v1", "tb-v1"):
        d = out / s
        assert r.samplers[s]["sampler_status"] == "no-sync"
        assert (r.samplers[s]["frames"], r.samplers[s]["distinct_frames"]) == (0, 0)
        assert (d / "frames.txt").is_file() and (d / "index.html").is_file()
        assert (d / "png").is_dir() and pngs(d) == []
    assert (r.pngs_written, r.pngs_linked) == (0, 0)
    assert len(r.uo_out_xxh3_128) == 32


def test_derive_truncated_trace(tools, models, dev, tmp_path_factory, tmp_path):
    trace = killed_trace(models, dev, tmp_path_factory)
    assert info(dev, trace)["close.status"] == "truncated"
    out = tmp_path / "out"
    r = go(trace, out, tools)
    assert r.error is None
    from vgacap import framesfile

    ff = framesfile.read_frames_txt(out / "centre-v1" / "frames.txt")
    assert ff.status == "truncated"
    assert r.samplers["centre-v1"]["frames"] > 0
    assert len(pngs(out / "centre-v1")) == r.samplers["centre-v1"]["distinct_frames"] > 0


def test_derive_bad_window_is_an_error(tools, bars, tmp_path):
    _, trace = bars
    out = tmp_path / "out"
    r = go(trace, out, tools, centre_window=(400, 0))
    assert r.error is not None
    assert r.error.startswith("centre_window 400,0 does not fit: ")
    assert r.samplers["centre-v1"]["sampler_status"] == "bad-window"
    assert r.samplers["centre-v1"]["frames"] == 0
    assert (out / "centre-v1" / "index.html").is_file()
    assert pngs(out / "centre-v1") == []


def test_derive_sampler_failure_is_an_error(tools, bars, tmp_path):
    """vgacap-sample exiting 1 for anything but a bad window sets the error to its last stderr line."""
    _, trace = bars
    bad = tmp_path / "bad.vgch.zst"
    bad.write_bytes(trace.read_bytes()[:64])
    with pytest.raises(derive.DeriveError):
        go(bad, tmp_path / "out", tools)   # tracetool info refuses it first
    # The trace is fine, but the output directory cannot be made.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    r = go(trace, blocker / "out", tools, log=tmp_path / "blocked.log")
    assert r.error is not None
    assert r.samplers == {}
