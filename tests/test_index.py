# SPDX-License-Identifier: Apache-2.0
import json

from ttvga.index import record, size, write_html, write_markdown

TARGET = {
    "id": "tt08/tt_um_x", "shuttle": "tt08", "macro": "tt_um_x", "title": "A demo", "author": "Someone",
    "address": "12", "tiles": "1x1", "language": "Verilog", "repo": "https://github.com/a/b",
    "commit": "abc123", "clock_hz": 25175000, "pmods": ["tiny-vga"],
}
RESULT = {
    "verdict": "ok", "reason": "lively", "host": "big", "finished": "2026-09-15T12:00:00+00:00",
    "auto_ui_in": 128, "qspi": None, "override": None, "tools": {"verilator": "5.053"},
    "videos": {"tt08_tt_um_x_60s.mp4": {"bytes": 154798650, "sha256": "aa"},
               "tt08_tt_um_x_60s.webm": {"bytes": 98000000, "sha256": "dd"},
               "tt08_tt_um_x_10s.mp4": {"bytes": 25820716, "sha256": "bb"},
               "tt08_tt_um_x_poster.png": {"bytes": 25620, "sha256": "cc"}},
    "timing": {"mode": "640x480@60", "width": 640, "height": 480, "fps": 59.94, "frames": 3596,
               "distinct_frames": 1200, "colours": 12, "mean_frame_delta": 0.0123,
               "pixels_ever_changed": 0.8, "clock_hz": 25175000, "clocks_simulated": 1510000000,
               "wall_seconds": 300.0, "clocks_per_wall_second": 5033333, "line_clocks": 800, "lines": 525,
               "clocks_per_pixel": 1.0, "hsync_active_low": True, "vsync_active_low": True},
}


def test_record_carries_identity_measurement_and_files():
    e = record(TARGET, RESULT)
    assert e["id"] == "tt08/tt_um_x" and e["author"] == "Someone"
    assert e["page"] == "https://tinytapeout.com/chips/tt08/tt_um_x"
    assert e["has_video"] and e["video"]["dir"] == "tt08/tt_um_x"
    assert e["video"]["files"]["tt08_tt_um_x_60s.mp4"]["bytes"] == 154798650
    assert e["video"]["stem"] == "tt08_tt_um_x"
    assert e["video"]["seconds"] == 59.99      # frames / fps
    assert e["video"]["colours"] == 12
    assert e["simulation"]["auto_ui_in"] == 128
    assert e["simulation"]["clocks"] == 1510000000


def test_record_without_a_result_is_still_listed():
    e = record(TARGET, None)
    assert e["verdict"] == "pending" and not e["has_video"]
    assert e["video"] == {"dir": "tt08/tt_um_x", "files": {}}


def test_size_is_human_readable():
    assert size(154798650) == "155 MB"
    assert size(25620) == "26 kB"
    assert size(None) == ""


def test_html_links_are_relative_to_the_video_root():
    page = write_html([record(TARGET, RESULT)], "now")
    assert 'src="tt08/tt_um_x/tt08_tt_um_x_poster.png"' in page
    assert 'href="tt08/tt_um_x/tt08_tt_um_x_60s.mp4"' in page
    assert 'href="tt08/tt_um_x/tt08_tt_um_x_60s.webm"' in page
    assert "<title>Tiny Tapeout VGA videos</title>" in page
    assert "A demo" in page and "640&times;480" in page


def test_markdown_table_has_one_row_per_project():
    md = write_markdown([record(TARGET, RESULT), record({**TARGET, "id": "tt09/tt_um_y", "macro": "tt_um_y"}, None)],
                        "now")
    rows = [l for l in md.splitlines() if l.startswith("| `")]
    assert len(rows) == 2
    assert "| `tt08/tt_um_x` |" in rows[0] and "ok" in rows[0] and "155 MB" in rows[0]
    assert "pending" in rows[1]


def test_json_is_serialisable():
    json.dumps(record(TARGET, RESULT))


def test_count_reads_as_words():
    from ttvga.index import count

    assert count(660_000_000_000) == "660 billion"
    assert count(1_230_000_000_000) == "1.2 trillion"
    assert count(0) == "0"


def test_stats_summarise_the_whole_set():
    from ttvga.index import stats

    entries = [record(TARGET, RESULT),
               record({**TARGET, "id": "tt09/tt_um_y", "macro": "tt_um_y", "shuttle": "tt09"}, None)]
    s = stats(entries)
    assert s["projects"] == 2 and s["with_video"] == 1
    assert s["verdicts"] == {"ok": 1, "pending": 1}
    assert s["modes"] == {"640x480@60": 1} and s["resolutions"] == {"640x480": 1}
    assert s["frame_rates"] == {"60": 1}
    assert s["video_bytes"] == 154798650 + 98000000 + 25820716 + 25620
    assert s["simulation"]["clocks_total"] == 1510000000
    assert s["helped_by"]["probed_input"] == 1 and s["helped_by"]["qspi_memory"] == 0
    assert s["liveliest"][0]["id"] == "tt08/tt_um_x"
    assert s["motion"]["median"] == 0.0123


def test_thumbnail_offers_the_animation_and_the_contact_sheet():
    page = write_html([record(TARGET, RESULT)], "now")
    assert 'data-gif="tt08/tt_um_x/tt08_tt_um_x_preview.gif"' in page
    assert 'data-poster="tt08/tt_um_x/tt08_tt_um_x_poster.png"' in page
    assert 'href="tt08/tt_um_x/tt08_tt_um_x_contact.png"' in page
    assert "button.play" in page                      # the handler is on the page
    assert 'aria-label="Play a preview of A demo"' in page
