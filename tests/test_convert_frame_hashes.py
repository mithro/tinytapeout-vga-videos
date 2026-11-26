# SPDX-License-Identifier: Apache-2.0
"""scripts/convert_frame_hashes.py: the old frame_hashes.txt as vgacap's tb-v1 FNV file (Task 17)."""

from __future__ import annotations

import importlib.util
import re

import pytest

from ttvga import HARNESS_DIR, ROOT, devtools
from ttvga.harness import vgacap_path

SCRIPT = ROOT / "scripts" / "convert_frame_hashes.py"

HASHES = ["fed6fc9311f187de", "fed6fc9311f187de", "0123456789abcdef"]


@pytest.fixture(scope="module")
def vgacap():
    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    from vgacap import framesfile, tbv1

    return framesfile, tbv1


@pytest.fixture(scope="module")
def conv(vgacap):
    spec = importlib.util.spec_from_file_location("convert_frame_hashes", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def old_text(mode="640x480@60", width=640, height=480, cpp="1.0", capture="1703936", hashes=HASHES) -> str:
    """An old frame_hashes.txt, in the committed files' exact layout."""
    head = [
        "# Per-frame hashes from the simulation, frame 0 first, one per line.",
        "# Hash: FNV-1a 64 loop (prime 0x100000001b3) but with a NON-STANDARD offset basis,",
        "# hash_offset_basis below, not 0xcbf29ce484222325: tb.cpp's constant lost a digit.",
        "# Over the frame as RGB888, row-major, active area only, at native resolution,",
        "# each 2-bit channel stored as value * 85, pixels sampled mid-period.",
        "# Stimulus: ena=1, rst_n=0 for 10 clocks, then 1. Clock 0 is the first reset clock.",
        "# Frame 0 starts at the first end of a vsync pulse after capture_after_clock.",
        "id: tt_test/tt_um_example",
        "hash_offset_basis: 0x14650fb0739d0383",
        f"mode: {mode}",
        f"width: {width}",
        f"height: {height}",
        "clock_hz: 25175000",
        f"clocks_per_pixel: {cpp}",
        f"capture_after_clock: {capture}",
        f"frames: {len(hashes)}",
    ]
    return "\n".join(head + hashes) + "\n"


def result(line_clocks=800, mode="640x480@60", cpp=1.0, count=len(HASHES)) -> dict:
    return {"id": "tt_test/tt_um_example",
            "timing": {"status": "ok", "line_clocks": line_clocks, "mode": mode, "clocks_per_pixel": cpp,
                       "frame_hashes_count": count}}


def write_old(tmp_path, text: str):
    p = tmp_path / "frame_hashes.txt"
    p.write_text(text)
    return p


def test_convert_keeps_hash_lines(conv, vgacap, tmp_path):
    framesfile, _ = vgacap
    old = write_old(tmp_path, old_text())
    hf = conv.convert(old, result())
    assert hf.hashes == HASHES
    assert (hf.method, hf.sampler, hf.sampler_status, hf.status) == ("fnv1a64-tb2026-rgb888", "tb-v1", "ok", "ok")
    assert (hf.id, hf.mode, hf.width, hf.height) == ("tt_test/tt_um_example", "640x480@60", 640, 480)
    assert (hf.clock_hz, hf.capture_after_clock) == (25175000, 1703936)
    text = framesfile.format_hash_file(hf)
    assert text.endswith("frames: 3\n" + "".join(h + "\n" for h in HASHES))


def test_convert_refuses_count_mismatch(conv, tmp_path):
    old = write_old(tmp_path, old_text())
    with pytest.raises(conv.ConvertError, match="frame_hashes_count"):
        conv.convert(old, result(count=4))


def test_convert_refuses_capture_not_a_number(conv, tmp_path):
    old = write_old(tmp_path, old_text(capture="null"))
    with pytest.raises(conv.ConvertError, match="capture_after_clock"):
        conv.convert(old, result())


def test_convert_refuses_cpp_mismatch(conv, tmp_path):
    old = write_old(tmp_path, old_text())
    with pytest.raises(conv.ConvertError, match="clocks_per_pixel"):
        conv.convert(old, result(cpp=1.04))


def test_convert_refuses_unknown_mode(conv, tmp_path):
    old = write_old(tmp_path, old_text(mode="unknown"))
    with pytest.raises(conv.ConvertError, match="mode"):
        conv.convert(old, result(mode="unknown"))


def test_converted_file_reads_back(conv, vgacap, tmp_path):
    framesfile, _ = vgacap
    old = write_old(tmp_path, old_text())
    hf = conv.convert(old, result())
    new = tmp_path / "frame_hashes.fnv1a64-tb2026-rgb888.txt"
    framesfile.write_hash_file(new, hf)
    back = framesfile.read_hash_file(new)
    assert back == hf
    assert back.hashes == HASHES


@pytest.mark.parametrize(("line_clocks", "mode", "old_cpp", "timing_cpp", "want"), [
    (1525, "640x480@60", "1.9062", 1.9062, 1.90625),
    (800, "640x480@75", "0.9524", 0.9524, 0.9523809523809523),
    (1600, "640x480@60", "2.0", 2.0, 2.0),
])
def test_clocks_per_pixel_recomputed(conv, tmp_path, line_clocks, mode, old_cpp, timing_cpp, want):
    old = write_old(tmp_path, old_text(mode=mode, cpp=old_cpp))
    hf = conv.convert(old, result(line_clocks=line_clocks, mode=mode, cpp=timing_cpp))
    assert hf.clocks_per_pixel == want


def test_tb_modes_match_tb_cpp(vgacap):
    _, tbv1 = vgacap
    src = (HARNESS_DIR / "tb.cpp").read_text()
    table = re.search(r"const Mode MODES\[\] = \{\n(.*?)\n\};", src, re.S)
    assert table, "tb.cpp: no `const Mode MODES[]` table"
    rows = re.findall(r'\{"([^"]+)", (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\}', table.group(1))
    assert len(rows) == len(table.group(1).splitlines())
    assert tuple((r[0], *map(int, r[1:])) for r in rows) == tbv1.TB_MODES


def _tree(tmp_path, count=len(HASHES)):
    import json

    d = tmp_path / "results" / "tt_test" / "tt_um_example"
    d.mkdir(parents=True)
    (d / "frame_hashes.txt").write_text(old_text())
    (d / "result.json").write_text(json.dumps(result(count=count), indent=2) + "\n")
    return tmp_path / "results", d


def test_main_converts_tree_and_result_json(conv, vgacap, tmp_path, capsys):
    import json

    framesfile, _ = vgacap
    results, d = _tree(tmp_path)
    assert conv.main(["--results", str(results)]) == 0
    assert not (d / "frame_hashes.txt").exists()
    hf = framesfile.read_hash_file(d / "frames" / "tb-v1" / "frame_hashes.fnv1a64-tb2026-rgb888.txt")
    assert hf.hashes == HASHES
    res = json.loads((d / "result.json").read_text())
    assert "frame_hashes_count" not in res["timing"]
    assert res["tb_v1"] == {"state": "stale", "trace_sha": None, "dropped": False}
    assert "converted 1" in capsys.readouterr().out


def test_main_writes_nothing_when_a_check_fails(conv, tmp_path):
    results, d = _tree(tmp_path, count=99)
    before = {p: p.read_bytes() for p in d.rglob("*")}
    with pytest.raises(SystemExit, match="nothing was written"):
        conv.main(["--results", str(results)])
    assert {p: p.read_bytes() for p in d.rglob("*")} == before


def test_seed_commands_target_work_tb_v1(conv, tmp_path):
    from ttvga import remote

    results = tmp_path / "results"
    f = results / "s" / "m" / "frames" / "tb-v1" / "frame_hashes.fnv1a64-tb2026-rgb888.txt"
    (cmd,) = conv.seed_commands(remote.Host(ssh="ttvga@example.org"), results, [f])
    assert cmd[0] == "rsync" and cmd[-2] == str(f)
    assert cmd[-1] == "ttvga@example.org:ttvga/work/s/m/frames/tb-v1/"
