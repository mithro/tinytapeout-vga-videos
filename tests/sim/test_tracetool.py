# SPDX-License-Identifier: Apache-2.0
"""tracetool: info, slice and uohash over traces written by tb.cpp."""

from __future__ import annotations

import xxhash
import signal
import subprocess
import time
from pathlib import Path

import pytest

from tests.sim import vgch
from tests.sim.helpers import base_args, info, killed_trace, kv, meta_args, run, tracetool

pytestmark = pytest.mark.sim

CLK = 1 << 42


def samples(t: vgch.Trace, lo: int, hi: int) -> list[int]:
    """Samples [lo, hi) with their clock bits, from the run list."""
    out = []
    for first, v, r in t.runs:
        a, b = max(first, lo), min(first + r, hi)
        for n in range(a, b):
            clk = t.header.clock_first ^ (n & 1)
            out.append((v & ~CLK) | (clk << 42))
    assert len(out) == hi - lo
    return out


@pytest.fixture(scope="module")
def bars(models, dev, tmp_path_factory):
    out = tmp_path_factory.mktemp("bars640")
    p = run(models("bars640"), dev, out)
    assert p.returncode == 0, p.stderr
    return out / "trace.vgch.zst"


def test_info_on_killed_trace(models, dev, tmp_path_factory):
    trace = killed_trace(models, dev, tmp_path_factory)
    i = info(dev, trace)
    assert i["table_rebuilt"] == "1"
    assert i["close.status"] == "truncated"
    assert int(i["blocks"]) >= 1
    assert int(i["samples"]) > 0 and i["clocks"] == str(int(i["samples"]) // 2)
    assert i["open.project"] == "test/noisy"


def test_info_on_finished_traces(models, dev, tmp_path):
    """A normal and a SIGTERMed run: the seek table is intact and the close status is the run's."""
    p = run(models("bars640"), dev, tmp_path / "ok")
    assert p.returncode == 0, p.stderr
    i = info(dev, tmp_path / "ok" / "trace.vgch.zst")
    assert (i["table_rebuilt"], i["close.status"], i["open.layout"]) == ("0", "ok", "tt-um-43")
    assert (i["version"], i["sample_bits"], i["samples_per_clock"], i["clock_bit"], i["clock_hz"]) == (
        "2", "43", "2", "42", "25175000")
    out = tmp_path / "term"
    out.mkdir()
    cmd = [str(models("bars640"))] + base_args(dev, out) + ["--trace", str(out / "trace.vgch.zst")]
    cmd += meta_args("bars640") + ["--seconds", "30"]
    m = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    time.sleep(2)
    m.send_signal(signal.SIGTERM)
    assert m.wait(timeout=60) == 3
    i = info(dev, out / "trace.vgch.zst")
    assert (i["table_rebuilt"], i["close.status"]) == ("0", "sim-timeout")


def test_info_prints_no_per_port_counts(models, dev, tmp_path):
    """`info` reads the header, index and META only: no run is decoded, so no per-port change counts."""
    p = run(models("uio_echo"), dev, tmp_path, "--ui-in", "0x5a", design="uio_echo")
    assert p.returncode == 3, p.stderr
    i = info(dev, tmp_path / "trace.vgch.zst")
    assert not [k for k in i if k.startswith("changes.")]
    assert int(i["clocks"]) == int(i["samples"]) // 2 > 0


def test_slice_round_trip(models, dev, bars, tmp_path):
    vgch._stream(dev)      # puts vgacap's python package on sys.path
    from vgacap import timebase

    sl = tmp_path / "slice.vgch.zst"
    tracetool(dev, "slice", bars, "--from", 1000, "--to", 2000, "--out", sl)
    orig, cut = vgch.read(bars, dev), vgch.read(sl, dev)

    # The slice's samples are the original's minus 2000.
    assert cut.samples == 2000
    assert samples(cut, 0, 2000) == samples(orig, 2000, 4000)

    # META: open copied plus the range; close copied with the original's status.
    o = orig.meta("open")
    c = cut.meta("open")
    assert c == {**o, "slice_from_clock": "1000", "slice_to_clock": "2000"}
    assert cut.meta("close") == {"meta": "close", "status": orig.meta("close")["status"],
                                 "capture_after_clock": "0", "frames": "0"}
    assert (cut.header.sample_bits, cut.header.samples_per_clock, cut.header.clock_bit,
            cut.header.clock_first) == (43, 2, 42, 0)

    # The VCDs of the slice and of the same range of the original have identical
    # value changes once each time is turned back into a sample number.
    hz, spc = 25_175_000, 2
    times = {timebase.sample_time_ps(n, spc, hz): n for n in range(5000)}
    assert len(times) == 5000

    def changes(vcd: Path, offset: int) -> list[tuple[int, str, str]]:
        out, n = [], None
        for line in vcd.read_text().splitlines():
            if line.startswith("#"):
                n = times[int(line[1:])] + offset
            elif line and line[0] in "01bB" and n is not None:
                value, _, ident = line.rpartition(" ") if line[0] in "bB" else (line[0], "", line[1:])
                out.append((n, ident, value))
        return out

    dev.require("vgacap_export")
    for name, trace, extra in (("slice", sl, []), ("orig", bars, ["--from", "1000", "--to", "2000"])):
        subprocess.run([str(dev.vgacap_export), str(trace), "--format", "vcd", "--out", str(tmp_path / f"{name}.vcd"),
                        *extra], check=True, capture_output=True, text=True)
    a = changes(tmp_path / "slice.vcd", 0)
    b = changes(tmp_path / "orig.vcd", -2000)
    assert len(a) > 50
    assert a == b


def test_slice_range_errors(dev, bars, tmp_path):
    out = tmp_path / "x.vgch.zst"
    clocks = int(info(dev, bars)["clocks"])
    for lo, hi in ((5, 5), (6, 5), (clocks - 1, clocks + 1), (clocks + 1, clocks + 2)):
        p = tracetool(dev, "slice", bars, "--from", lo, "--to", hi, "--out", out, check=False)
        assert p.returncode == 2, (lo, hi, p.stderr)
        assert not out.exists()
    # The very end is in range.
    tracetool(dev, "slice", bars, "--from", clocks - 10, "--to", clocks, "--out", out)
    assert int(info(dev, out)["clocks"]) == 10


def test_slice_of_truncated_has_no_close(models, dev, tmp_path_factory, tmp_path):
    trace = killed_trace(models, dev, tmp_path_factory)
    sl = tmp_path / "slice.vgch.zst"
    tracetool(dev, "slice", trace, "--from", 1000, "--to", 3000, "--out", sl)
    i = info(dev, sl)
    assert i["close.status"] == "truncated"
    assert not any(k.startswith("close.") and k != "close.status" for k in i)
    assert (i["samples"], i["clocks"], i["table_rebuilt"]) == ("4000", "2000", "1")
    assert i["open.slice_from_clock"] == "1000" and i["open.slice_to_clock"] == "3000"
    t = vgch.read(sl, dev)
    assert [m["meta"] for m in t.metas] == ["open"]
    # The killed file ends in a cut frame, which a plain zstd decoder rejects, so
    # compare through tracetool: a slice from clock 0 hashes like the original's first clocks.
    head = tmp_path / "head.vgch.zst"
    tracetool(dev, "slice", trace, "--from", 0, "--to", 2000, "--out", head)
    assert kv(tracetool(dev, "uohash", head).stdout) == kv(tracetool(dev, "uohash", trace, "--clocks", 2000).stdout)


def test_uohash_matches_python(dev, bars):
    M = 50_000
    t = vgch.read(bars, dev)
    data = bytes(s & 0xFF for s in samples(t, 0, 2 * M)[1::2])
    assert len(data) == M
    want = xxhash.xxh3_128_hexdigest(data)
    got = kv(tracetool(dev, "uohash", bars, "--clocks", M).stdout)
    assert got == {"uo_out_xxh3_128_clocks": f"0 {M}", "uo_out_xxh3_128": want}
    # Half-open: one clock fewer is a different hash, over M - 1 clocks.
    short = kv(tracetool(dev, "uohash", bars, "--clocks", M - 1).stdout)
    assert short["uo_out_xxh3_128_clocks"] == f"0 {M - 1}"
    assert short["uo_out_xxh3_128"] == xxhash.xxh3_128_hexdigest(data[:-1]) != want


def test_uohash_clamps_to_the_trace(dev, bars, tmp_path):
    sl = tmp_path / "s.vgch.zst"
    tracetool(dev, "slice", bars, "--from", 0, "--to", 3000, "--out", sl)
    got = kv(tracetool(dev, "uohash", sl).stdout)     # default N = 2^25 is past the end
    assert got["uo_out_xxh3_128_clocks"] == "0 3000"
    t = vgch.read(sl, dev)
    assert got["uo_out_xxh3_128"] == xxhash.xxh3_128_hexdigest(bytes(s & 0xFF for s in samples(t, 0, 6000)[1::2]))


def test_refuses_a_trace_whose_clock_starts_high(dev, tmp_path):
    """tracetool reads clock bit 42 as low in sample 0; a header that says otherwise is refused."""
    import struct

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return tag + struct.pack("<I", len(payload)) + payload

    vgch_payload = struct.pack("<HBBI8sBBHBBBB", 2, 43, 2, 25_175_000, bytes([7, 3, 0, 4, 1, 5, 2, 6]), 0, 0, 0, 2, 42, 1, 0)
    meta = b"meta=open\nproject=test/x\ncalib_seconds=0.1\nseconds=0.2\nlayout=tt-um-43\n"
    runs = struct.pack("<I", 1) + (0x100).to_bytes(6, "little") + bytes([8])
    plain = tmp_path / "high.vgch"
    plain.write_bytes(chunk(b"VGCH", vgch_payload) + chunk(b"META", meta) + chunk(b"BLKH", bytes(8)) + chunk(b"RUNS", runs))
    for cmd in (["info", plain], ["uohash", plain], ["slice", plain, "--from", 0, "--to", 2, "--out", tmp_path / "o"]):
        p = tracetool(dev, *cmd, check=False)
        assert p.returncode == 1 and "clock" in p.stderr, (cmd, p.returncode, p.stderr)
