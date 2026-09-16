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


def test_the_animation_covers_the_whole_clip(tmp_path, monkeypatch):
    """The preview is a time-lapse of the entire video, not an excerpt of it."""
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    (tmp_path / "tt08_tt_um_x_60s.mp4").write_bytes(b"")
    for name in encode.preview_names("tt08_tt_um_x"):
        (tmp_path / name).write_bytes(b"")
    encode.render_previews(tmp_path, "tt08_tt_um_x", tmp_path / "log", "ffmpeg", frames=3600, fps=60.0)

    gif = next(c for c in calls if c[-1].endswith("_preview.gif"))
    # 60 s of video shown in 8 s at 12 fps: sample 1.6 frames of each source
    # second and replay them 7.5 times faster.
    assert "fps=1.600000,setpts=PTS/7.500000," in " ".join(gif)
    # Nothing is trimmed away: no seek, no duration limit.
    assert "-ss" not in gif and "-t" not in gif


def test_a_clip_shorter_than_the_preview_plays_at_its_own_speed(tmp_path, monkeypatch):
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    (tmp_path / "tt08_tt_um_x_60s.mp4").write_bytes(b"")
    for name in encode.preview_names("tt08_tt_um_x"):
        (tmp_path / name).write_bytes(b"")
    encode.render_previews(tmp_path, "tt08_tt_um_x", tmp_path / "log", "ffmpeg", frames=180, fps=60.0)

    gif = next(c for c in calls if c[-1].endswith("_preview.gif"))
    assert f"fps={encode.GIF_FPS}," in " ".join(gif) and "setpts" not in " ".join(gif)
