# SPDX-License-Identifier: Apache-2.0
"""The naming of published files. The index page and the host harness must agree
on these exactly, so they are pinned here rather than written out twice."""

import sys

from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

from encode import LENGTHS, UPSCALE, clip_names, preview_names, stem_for  # noqa: E402


def test_stem_names_the_shuttle_and_the_project():
    assert stem_for("tt09", "tt_um_a1k0n_nyancat") == "tt09_tt_um_a1k0n_nyancat"


def test_every_published_file_carries_the_stem():
    stem = stem_for("ttsky26a", "tt_um_maze")
    for name in clip_names(stem) + preview_names(stem):
        assert name.startswith(stem + "_"), name


def test_clips_are_published_in_both_browser_codecs():
    names = clip_names(stem_for("tt08", "tt_um_x"))
    assert len(names) == len(LENGTHS) * 2
    for secs in LENGTHS:
        assert f"tt08_tt_um_x_{secs}s.mp4" in names
        assert f"tt08_tt_um_x_{secs}s.webm" in names
    # Nothing motion JPEG is published any more: browsers will not play it.
    assert not any(n.endswith(".avi") for n in names)


def test_the_longest_clip_comes_first():
    # The shorter clips are cut from the longest, so it has to be encoded first.
    assert LENGTHS[0] == max(LENGTHS)


def test_clips_are_upscaled_so_chroma_lands_on_the_pixel_grid():
    # 4:2:0 halves the chroma resolution; doubling first keeps one colour per
    # design pixel. Nearest-neighbour keeps the pixel edges hard.
    assert "iw*2:ih*2" in UPSCALE and "neighbor" in UPSCALE
