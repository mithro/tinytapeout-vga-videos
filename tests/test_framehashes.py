# SPDX-License-Identifier: Apache-2.0
import json

from ttvga import framehashes

LOG = ("\n$ Vtop --quiet\n"
       "\n$ Vtop --clock-hz 25175000\n"
       "tb: sync at clock 1703936: line 800 clocks, 525 lines, mode 640x480@60\n"
       "tb: ok: 3 frames\n[exit 0]\n")


def result(**timing):
    t = {"mode": "640x480@60", "width": 640, "height": 480, "clock_hz": 25175000,
         "clocks_per_pixel": 1.0}
    t.update(timing)
    return {"id": "tt08/tt_um_x", "timing": t, "sim_log_tail": LOG}


def write(tmp_path, r):
    p = tmp_path / "result.json"
    p.write_text(json.dumps(r))
    return p


def test_capture_clock_takes_the_last_sync_line():
    r = result()
    r["sim_log_tail"] = "tb: sync at clock 5\n" + LOG
    assert framehashes.capture_clock(r) == 1703936


def test_capture_clock_prefers_timing_then_full_log():
    assert framehashes.capture_clock(result(capture_after_clock=42)) == 42
    r = result()
    r["sim_log_tail"] = "tb: ok: 3 frames"          # the tail lost the sync line
    assert framehashes.capture_clock(r) is None
    assert framehashes.capture_clock(r, sim_log=LOG) == 1703936


def test_capture_clock_unknown_without_a_sync_line():
    r = result()
    r["sim_log_tail"] = "tb: no-sync after 100 clocks"
    assert framehashes.capture_clock(r) is None
    assert "capture_after_clock: unknown" in framehashes.render(result(frame_hashes=["00"]) | {"sim_log_tail": ""})


def test_export_writes_hashes_in_order_and_strips_result(tmp_path):
    p = write(tmp_path, result(frame_hashes=["aa01", "bb02", "aa01"]))
    assert framehashes.export(p) == "written"
    text = (tmp_path / "frame_hashes.txt").read_text()
    body = [l for l in text.splitlines() if l and not l.startswith("#") and ":" not in l]
    assert body == ["aa01", "bb02", "aa01"]
    assert "capture_after_clock: 1703936" in text
    assert "frames: 3" in text
    assert "id: tt08/tt_um_x" in text
    stripped = json.loads(p.read_text())["timing"]
    assert "frame_hashes" not in stripped and stripped["frame_hashes_count"] == 3


def test_export_keeps_file_for_an_already_stripped_result(tmp_path):
    p = write(tmp_path, result(frame_hashes=["aa01"]))
    framehashes.export(p)
    assert framehashes.export(p) == "kept"
    assert (tmp_path / "frame_hashes.txt").exists()


def test_export_removes_stale_file_when_the_run_has_no_frames(tmp_path):
    write(tmp_path, result(frame_hashes=["aa01"]))
    framehashes.export(tmp_path / "result.json")
    p = write(tmp_path, {"id": "tt08/tt_um_x", "timing": {"status": "no-sync"}})
    assert framehashes.export(p) == "removed"
    assert not (tmp_path / "frame_hashes.txt").exists()
