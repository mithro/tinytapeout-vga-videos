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


def test_playground_link_pins_the_commit_that_was_simulated():
    from ttvga.index import playground

    url = playground(record(TARGET, RESULT))
    assert url == "https://vga-playground.com/?repo=https://github.com/a/b&ref=abc123"
    assert "playground" in write_html([record(TARGET, RESULT)], "now")


def test_clips_are_listed_as_a_table_of_length_by_codec():
    page = write_html([record(TARGET, RESULT)], "now")
    assert '<table class="clips">' in page
    assert "<th>webm</th>" in page and "<th>mp4</th>" in page
    assert '<th class="len">60s</th>' in page
    # 30 s is absent from the fixture, so that row is not offered at all.
    assert '<th class="len">30s</th>' not in page


def test_sticky_headings_sit_above_the_thumbnails():
    # `.play` is positioned and comes later in the document, so without an
    # explicit z-index the sticky heading and header row paint behind it.
    page = write_html([record(TARGET, RESULT)], "now")
    heading = next(l for l in page.splitlines() if l.startswith("h2{"))
    header = next(l for l in page.splitlines() if l.startswith("th{"))
    assert "position:sticky" in heading and "z-index:3" in heading
    assert "position:sticky" in header and "z-index:2" in header


def test_marks_separate_what_a_project_is_wired_to_from_what_the_run_used():
    """An outline badge says wired for it; a filled one says the run used it."""
    target = dict(TARGET, pmods=["tiny-vga", "gamepad", "tt-audio"])
    e = record(target, RESULT)
    assert e["uses"] == {"gamepad": True, "gamepad_driven": False,
                         "audio": True, "audio_captured": False}
    page = write_html([e], "now")
    assert '<span class="pmod" title="reads a Gamepad Pmod; nothing pressed it' in page
    assert ">gamepad</span>" in page and ">audio</span>" in page

    driven = record(target, dict(RESULT, override={"gamepad": [{"at": 3.0, "press": "a"}]},
                                 timing=dict(RESULT["timing"], audio_driven=True, audio_samples=2303084)))
    assert driven["uses"] == {"gamepad": True, "gamepad_driven": True,
                              "audio": True, "audio_captured": True}
    assert driven["video"]["has_audio"]
    page = write_html([driven], "now")
    assert '<span class="pmod on"' in page
    assert ">gamepad driven</span>" in page and ">audio captured</span>" in page


def test_a_gamepad_found_from_pin_names_is_marked_even_though_undeclared():
    """Two projects drive a gamepad without saying so; the run is the evidence."""
    e = record(TARGET, dict(RESULT, override={"gamepad": [{"at": 3.0, "press": "a"}]}))
    assert e["uses"]["gamepad"] and e["uses"]["gamepad_driven"]
    assert ">gamepad driven</span>" in write_html([e], "now")


def test_a_project_using_neither_pmod_gets_no_badge():
    page = write_html([record(TARGET, RESULT)], "now")
    assert 'class="pmod' not in page


def test_markdown_says_which_pmods_were_used():
    e = record(dict(TARGET, pmods=["tiny-vga", "gamepad", "tt-audio"]),
               dict(RESULT, override={"gamepad": [{"at": 3.0}]}))
    row = [ln for ln in write_markdown([e], "now").splitlines() if "`tt08/tt_um_x`" in ln][0]
    assert "| gamepad+, audio |" in row


def test_audio_is_found_from_the_pin_name_as_well_as_the_declaration():
    """Fourteen projects drive the Audio Pmod pin without listing the Pmod."""
    e = record(dict(TARGET, pinout={"uio[7]": "AudioPWM"}), RESULT)
    assert e["uses"]["audio"] and not e["uses"]["audio_captured"]
    assert ">audio</span>" in write_html([e], "now")
    quiet = record(dict(TARGET, pinout={"uio[7]": "addr_out[3]"}), RESULT)
    assert not quiet["uses"]["audio"]
