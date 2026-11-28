# SPDX-License-Identifier: Apache-2.0
"""derive.windows: each sampler's `window` flag in result.json (docs/consumers.md, "Sampler windows")."""

from __future__ import annotations

from pathlib import Path

import pytest

from ttvga.harness import derive

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def ff_of(framesfile, sampler: str, *, mode: str = "640x480@60", cpp: float = 1.0, frame_clocks: int = 420000,
          outside: int = 0, suggested: tuple[int, int] = (0, 0), status: str = "ok", frames: int = 3):
    """A FramesFile with the fields the flag reads; frames start `frame_clocks` apart."""
    centre = framesfile.Centre((0, 0), (48, 33), outside, suggested, 0, 0) if sampler == derive.CENTRE else None
    n = frames if status == "ok" else 0
    return framesfile.FramesFile(
        id="t/x", status="ok", sampler=sampler, sampler_status=status, width=640, height=480, mode=mode,
        clock_hz=25175000, clocks_per_pixel=cpp, capture_after_clock=0, store="x.rgb6.zst",
        store_length=640 * 480 if n else 0, store_xxh3_128="0" * 31 + "1", distinct=["0" * 32] if n else [],
        frames=[framesfile.Frame(0, 1000 + k * frame_clocks, 0) for k in range(n)], centre=centre)


def test_mode_totals_come_from_vgacap(framesfile):
    from vgacap import modes, tbv1

    t = derive.mode_totals()
    assert t[derive.CENTRE]["640x480@60"] == (800, 525) == (modes.MODES["640x480@60"].cpl, modes.MODES["640x480@60"].lpf)
    assert t[derive.TB_V1]["640x480@75"] == (840, 500)
    assert set(t[derive.CENTRE]) == {m.name for m in modes.TABLE}
    assert set(t[derive.TB_V1]) == {m[0] for m in tbv1.TB_MODES}
    # The two tables agree on every mode they share.
    for name, lf in t[derive.TB_V1].items():
        assert t[derive.CENTRE][name] == lf


def test_both_exact(framesfile):
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE), derive.TB_V1: ff_of(framesfile, derive.TB_V1)})
    assert w[derive.CENTRE] == {"exact": True, "frame_clocks": 420000, "mode_frame_clocks": 420000,
                                "outside": 0, "suggested_offset": [0, 0]}
    assert w[derive.TB_V1] == {"exact": True, "frame_clocks": 420000, "mode_frame_clocks": 420000}


def test_centre_outside_flags_centre_only(framesfile):
    """Lit pixels outside centre-v1's window flag it; tb-v1's flag is from the timing alone."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, outside=640, suggested=(0, -1)),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1)})
    assert w[derive.CENTRE] == {"exact": False, "frame_clocks": 420000, "mode_frame_clocks": 420000,
                                "outside": 640, "suggested_offset": [0, -1]}
    assert w[derive.TB_V1]["exact"] is True


def test_line_longer_than_the_mode_flags_both(framesfile):
    """nyan's timing: 832-clock lines, 525 lines. centre-v1 takes cpp 1, tb-v1 stretches the mode's 800 to 1.04."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, frame_clocks=436800),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1, cpp=1.04, frame_clocks=436800)})
    assert w[derive.CENTRE]["exact"] is False and w[derive.CENTRE]["outside"] == 0
    assert w[derive.TB_V1] == {"exact": False, "frame_clocks": 436800, "mode_frame_clocks": 420000}


def test_whole_cpp_above_one_is_exact(framesfile):
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, cpp=2.0, frame_clocks=840000),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1, cpp=2.0, frame_clocks=840000)})
    assert w[derive.CENTRE]["exact"] and w[derive.TB_V1]["exact"]
    assert w[derive.TB_V1]["mode_frame_clocks"] == 840000


def test_fractional_cpp_on_the_mode_is_exact(framesfile):
    """vgadonut's timing: 1525-clock lines = 800 x 1.90625, 525 lines; both samplers take cpp 1.90625."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, cpp=1.90625, frame_clocks=800625),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1, cpp=1.90625, frame_clocks=800625)})
    assert w[derive.CENTRE]["exact"] and w[derive.TB_V1]["exact"]


def test_short_line_tb_v1_below_one_cpp_is_flagged(framesfile):
    """rle_vga's timing: 800-clock lines, 500 lines, matched to 640x480@75 (840 x 500)."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, mode="640x480@75", frame_clocks=400000),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1, mode="640x480@75", cpp=800 / 840,
                                            frame_clocks=400000)})
    assert w[derive.CENTRE] == {"exact": False, "frame_clocks": 400000, "mode_frame_clocks": 420000,
                                "outside": 0, "suggested_offset": [0, 0]}
    assert w[derive.TB_V1] == {"exact": False, "frame_clocks": 400000, "mode_frame_clocks": 420000}


def test_unknown_mode_is_not_exact(framesfile):
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1, mode="unknown")})
    assert w[derive.TB_V1] == {"exact": False, "frame_clocks": 420000, "mode_frame_clocks": None}


def test_fewer_than_two_frames_is_not_exact(framesfile):
    """frame_clocks is 0 with fewer than two frames: the timing is not known, so not exact."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, frames=1)})
    assert w[derive.CENTRE]["frame_clocks"] == 0 and w[derive.CENTRE]["exact"] is False


@pytest.mark.parametrize("status", ["no-sync", "bad-timing", "bad-window"])
def test_no_window_is_null(framesfile, status):
    """A sampler without a window has `window: null`; tb-v1 without centre-v1's cpp is not exact."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, status=status),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1)})
    assert w[derive.CENTRE] is None
    assert w[derive.TB_V1] == {"exact": False, "frame_clocks": 420000, "mode_frame_clocks": None}


def test_centre_alone(framesfile):
    """A run without tb-v1 flags centre-v1 only."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE)})
    assert set(w) == {derive.CENTRE}


@pytest.mark.parametrize("name", ["bars640", "glitch"])
def test_committed_centre_fixtures(framesfile, name):
    """The committed centre-v1 fixtures: 640x480@60 timing, one row lit outside the window."""
    ff = framesfile.read_frames_txt(FIXTURES / "frames" / name / "frames.txt")
    assert derive.windows({derive.CENTRE: ff})[derive.CENTRE] == {
        "exact": False, "frame_clocks": 420000, "mode_frame_clocks": 420000,
        "outside": 640, "suggested_offset": [0, -1]}


def test_pilot_nyan(framesfile):
    """tt08/tt_um_nyan's published frames.txt (pilot, vgacap 4a3c670): both samplers flagged."""
    d = FIXTURES / "pilot-frames" / "tt08__tt_um_nyan"
    read = {s: framesfile.read_frames_txt(d / s / "frames.txt") for s in (derive.CENTRE, derive.TB_V1)}
    assert read[derive.TB_V1].clocks_per_pixel == 1.04
    w = derive.windows(read)
    assert w == {
        derive.CENTRE: {"exact": False, "frame_clocks": 436800, "mode_frame_clocks": 420000,
                        "outside": 4472, "suggested_offset": [8, -1]},
        derive.TB_V1: {"exact": False, "frame_clocks": 436800, "mode_frame_clocks": 420000},
    }
