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


def tb(exact, frame_clocks, line_clocks, lines, mode_line_clocks, mode_lines):
    return {"exact": exact, "frame_clocks": frame_clocks, "line_clocks": line_clocks, "lines": lines,
            "mode_line_clocks": mode_line_clocks, "mode_lines": mode_lines}


def centre(exact, frame_clocks, mode_frame_clocks, outside=0, suggested=(0, 0)):
    return {"exact": exact, "frame_clocks": frame_clocks, "mode_frame_clocks": mode_frame_clocks,
            "outside": outside, "suggested_offset": list(suggested)}


def both(framesfile, *, mode="640x480@60", centre_cpp=1.0, tb_cpp=1.0, frame_clocks=420000, outside=0,
         suggested=(0, 0)):
    return derive.windows({
        derive.CENTRE: ff_of(framesfile, derive.CENTRE, mode=mode, cpp=centre_cpp, frame_clocks=frame_clocks,
                             outside=outside, suggested=suggested),
        derive.TB_V1: ff_of(framesfile, derive.TB_V1, mode=mode, cpp=tb_cpp, frame_clocks=frame_clocks)})


def test_both_exact(framesfile):
    w = both(framesfile)
    assert w[derive.CENTRE] == centre(True, 420000, 420000)
    assert w[derive.TB_V1] == tb(True, 420000, 800, 525, 800, 525)


def test_centre_outside_flags_centre_only(framesfile):
    """Lit pixels outside centre-v1's window flag it; tb-v1's flag is its line and line count."""
    w = both(framesfile, outside=640, suggested=(0, -1))
    assert w[derive.CENTRE] == centre(False, 420000, 420000, 640, (0, -1))
    assert w[derive.TB_V1]["exact"] is True


def test_line_longer_than_the_mode(framesfile):
    """nyan's timing: 832-clock lines, 525 lines. tb-v1 stretches the mode's 800 to cpp 1.04."""
    w = both(framesfile, tb_cpp=1.04, frame_clocks=436800)
    assert w[derive.TB_V1] == tb(False, 436800, 832, 525, 800, 525)
    # centre-v1's `exact` is `outside` alone: the off-mode timing is data beside it.
    assert w[derive.CENTRE] == centre(True, 436800, 420000)


def test_same_product_different_factors_is_flagged(framesfile):
    """840 x 500 lines has the product of 640x480@60's 800 x 525; tb-v1 matched to 640x480@60 at 1.05 is flagged."""
    w = derive.windows({derive.TB_V1: ff_of(framesfile, derive.TB_V1, cpp=1.05, frame_clocks=420000)})
    assert w[derive.TB_V1] == tb(False, 420000, 840, 500, 800, 525)


def test_whole_cpp_above_one_is_exact(framesfile):
    w = both(framesfile, centre_cpp=2.0, tb_cpp=2.0, frame_clocks=840000)
    assert w[derive.CENTRE] == centre(True, 840000, 840000)
    assert w[derive.TB_V1] == tb(True, 840000, 1600, 525, 1600, 525)


def test_fractional_cpp_is_not_tb_v1_exact(framesfile):
    """vgadonut's timing: 1525-clock lines = 800 x 1.90625, 525 lines. The mode's line at a whole cpp is 1600."""
    w = both(framesfile, centre_cpp=1.90625, tb_cpp=1.90625, frame_clocks=800625)
    assert w[derive.CENTRE] == centre(True, 800625, 800625)
    assert w[derive.TB_V1] == tb(False, 800625, 1525, 525, 1600, 525)


def test_short_line_tb_v1_below_one_cpp_is_flagged(framesfile):
    """rle_vga's timing: 800-clock lines, 500 lines, matched to 640x480@75 (840 x 500)."""
    w = both(framesfile, mode="640x480@75", tb_cpp=800 / 840, frame_clocks=400000)
    assert w[derive.CENTRE] == centre(True, 400000, 420000)
    assert w[derive.TB_V1] == tb(False, 400000, 800, 500, 840, 500)


def test_rounded_cpp_leaves_the_line_unmeasured(framesfile):
    """tomkeddie_a's timing: 799 x 506. tb-v1 rounds 799/800 to cpp 1, so 404,294 is not whole 800-clock lines."""
    w = derive.windows({derive.TB_V1: ff_of(framesfile, derive.TB_V1, frame_clocks=404294)})
    assert w[derive.TB_V1] == tb(False, 404294, None, None, 800, 525)


def test_unknown_mode_is_not_exact(framesfile):
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, mode="unknown"),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1, mode="unknown")})
    assert w[derive.TB_V1] == tb(False, 420000, None, None, None, None)
    assert w[derive.CENTRE] == centre(True, 420000, None)


@pytest.mark.parametrize("sampler", [derive.CENTRE, derive.TB_V1])
def test_a_mode_missing_from_vgacap_is_raised(framesfile, sampler):
    with pytest.raises(derive.DeriveError, match="mode '640x480@61'"):
        derive.windows({sampler: ff_of(framesfile, sampler, mode="640x480@61")})


def test_tb_v1_has_no_720x400():
    assert "720x400@70" in derive.mode_totals()[derive.CENTRE]
    assert "720x400@70" not in derive.mode_totals()[derive.TB_V1]


def test_a_cpp_off_the_line_grid_is_raised(framesfile):
    """A cpp that is not a whole number of clocks over the mode's 800 pixels cannot come from tb-v1."""
    with pytest.raises(derive.DeriveError, match="not a whole line over 800 pixels"):
        derive.windows({derive.TB_V1: ff_of(framesfile, derive.TB_V1, cpp=1.0001234)})


def test_fewer_than_two_frames_is_not_exact(framesfile):
    """frame_clocks is 0 with fewer than two frames: tb-v1's line count is not known."""
    w = derive.windows({derive.TB_V1: ff_of(framesfile, derive.TB_V1, frames=1)})
    assert w[derive.TB_V1] == tb(False, 0, None, None, 800, 525)


@pytest.mark.parametrize("status", ["no-sync", "bad-timing", "bad-window"])
def test_no_window_is_null_and_tb_v1_stands_alone(framesfile, status):
    """A sampler without a window has `window: null`; tb-v1's flag does not need centre-v1's."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE, status=status),
                        derive.TB_V1: ff_of(framesfile, derive.TB_V1)})
    assert w[derive.CENTRE] is None
    assert w[derive.TB_V1] == tb(True, 420000, 800, 525, 800, 525)


def test_centre_alone(framesfile):
    """A run without tb-v1 flags centre-v1 only."""
    w = derive.windows({derive.CENTRE: ff_of(framesfile, derive.CENTRE)})
    assert set(w) == {derive.CENTRE}


@pytest.mark.parametrize("name", ["bars640", "glitch"])
def test_committed_centre_fixtures(framesfile, name):
    """The committed centre-v1 fixtures: 640x480@60 timing, one row lit outside the window."""
    ff = framesfile.read_frames_txt(FIXTURES / "frames" / name / "frames.txt")
    assert derive.windows({derive.CENTRE: ff})[derive.CENTRE] == centre(False, 420000, 420000, 640, (0, -1))


def test_pilot_nyan(framesfile):
    """tt08/tt_um_nyan's published frames.txt (pilot, vgacap 4a3c670): both samplers flagged."""
    d = FIXTURES / "pilot-frames" / "tt08__tt_um_nyan"
    read = {s: framesfile.read_frames_txt(d / s / "frames.txt") for s in (derive.CENTRE, derive.TB_V1)}
    assert read[derive.TB_V1].clocks_per_pixel == 1.04
    assert derive.windows(read) == {
        derive.CENTRE: centre(False, 436800, 420000, 4472, (8, -1)),
        derive.TB_V1: tb(False, 436800, 832, 525, 800, 525),
    }
