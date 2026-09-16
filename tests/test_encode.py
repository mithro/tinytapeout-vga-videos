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


def _preview_calls(tmp_path, monkeypatch, frames, fps):
    """Run render_previews with ffmpeg stubbed, and hand back the commands."""
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    (tmp_path / "tt08_tt_um_x_60s.mp4").write_bytes(b"")
    for name in encode.preview_names("tt08_tt_um_x"):
        (tmp_path / name).write_bytes(b"")
    encode.render_previews(tmp_path, "tt08_tt_um_x", tmp_path / "log", "ffmpeg", frames=frames, fps=fps)
    gif = next(c for c in calls if c[-1].endswith("_preview.gif"))
    poster = next(c for c in calls if c[-1].endswith("_poster.png"))
    return gif, poster


def test_the_animation_plays_at_the_speed_the_design_runs_at(tmp_path, monkeypatch):
    """Real time, not a time-lapse: sampling across the whole clip put 625 ms
    between consecutive frames, which reads as a broken frame rate."""
    import encode

    gif, _ = _preview_calls(tmp_path, monkeypatch, frames=3600, fps=60.0)
    joined = " ".join(gif)
    assert f"fps={encode.GIF_FPS}," in joined
    assert "setpts" not in joined
    # The output rate has to agree with the filter, or the encoder drops frames
    # back towards the source rate and the animation arrives a few frames long.
    assert gif[gif.index("-r") + 1] == str(encode.GIF_FPS)


def test_the_poster_is_the_animation_first_frame(tmp_path, monkeypatch):
    """Clicking the thumbnail must not make the picture jump backwards."""
    import encode

    gif, poster = _preview_calls(tmp_path, monkeypatch, frames=3600, fps=60.0)
    assert gif[gif.index("-ss") + 1] == poster[poster.index("-ss") + 1]
    assert float(poster[poster.index("-ss") + 1]) == encode.PREVIEW_START


def test_a_short_clip_starts_the_preview_within_it(tmp_path, monkeypatch):
    """A clip shorter than PREVIEW_START would otherwise start past its end."""
    import encode

    gif, poster = _preview_calls(tmp_path, monkeypatch, frames=180, fps=60.0)
    start = float(poster[poster.index("-ss") + 1])
    assert 0 < start <= 3.0 / 2          # half of a three second clip
    assert gif[gif.index("-ss") + 1] == poster[poster.index("-ss") + 1]


def test_webm_is_written_limited_range(tmp_path, monkeypatch):
    """A full range VP9 stream does not play in Chrome on a machine using its
    hardware decoder. Tested against a browser that failed on the published
    file: full range failed with either matrix, limited range played with
    either, so the range is what decides it."""
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    encode.encode_webm(tmp_path / "in.mp4", tmp_path / "out.webm", tmp_path / "log",
                       "ffmpeg", "30,10", upscale=False)
    cmd = calls[0]
    assert cmd[cmd.index("-color_range") + 1] == "tv"
    assert "out_range=tv" in " ".join(cmd)
    # And it must not silently double the size of an already-published clip.
    assert "iw*2" not in " ".join(cmd)


def test_webm_upscales_only_when_asked(tmp_path, monkeypatch):
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    encode.encode_webm(tmp_path / "in.avi", tmp_path / "out.webm", tmp_path / "log",
                       "ffmpeg", "30,10", upscale=True)
    assert "iw*2:ih*2" in " ".join(calls[0])


def test_audio_is_muxed_when_the_design_drove_the_pin(tmp_path, monkeypatch):
    """The Audio Pmod carries one bit on uio[7]; the capture becomes a track."""
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    work = tmp_path / "work"
    work.mkdir()
    (work / "capture.avi").write_bytes(b"x")
    (work / encode.AUDIO_RAW).write_bytes(b"\0" * 4096)
    videos = tmp_path / "out"
    videos.mkdir()
    for n in encode.clip_names("tt08_tt_um_x"):
        (videos / n).write_bytes(b"x")
    encode.transcode(work / "capture.avi", videos, "tt08_tt_um_x", tmp_path / "log", "ffmpeg")

    mp4 = next(c for c in calls if c[-1].endswith("_60s.mp4"))
    assert "f32le" in mp4 and "aac" in mp4
    webm = next(c for c in calls if c[-1].endswith("_60s.webm"))
    assert "f32le" in webm and "libopus" in webm


def test_no_audio_track_when_the_pin_was_never_driven(tmp_path, monkeypatch):
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    work = tmp_path / "work"
    work.mkdir()
    (work / "capture.avi").write_bytes(b"x")          # no capture.f32 beside it
    videos = tmp_path / "out"
    videos.mkdir()
    for n in encode.clip_names("tt08_tt_um_x"):
        (videos / n).write_bytes(b"x")
    encode.transcode(work / "capture.avi", videos, "tt08_tt_um_x", tmp_path / "log", "ffmpeg")

    mp4 = next(c for c in calls if c[-1].endswith("_60s.mp4"))
    assert "-an" in mp4 and "f32le" not in mp4


def test_rewriting_webm_keeps_the_audio_already_in_the_mp4(tmp_path, monkeypatch):
    """The raw capture is long gone by then, so the track is copied across."""
    import encode

    calls = []
    monkeypatch.setattr(encode, "run", lambda cmd, *a, **k: calls.append(cmd) or 0)
    (tmp_path / "tt08_tt_um_x_60s.mp4").write_bytes(b"x")
    encode.rewrite_webm(tmp_path, "tt08_tt_um_x", tmp_path / "log", "ffmpeg")
    webm = next(c for c in calls if c[-1].endswith("_60s.webm"))
    assert "0:a?" in webm and "libopus" in webm


def test_audio_rate_comes_from_the_simulation_record(tmp_path):
    """Raw samples carry no rate, so guessing wrong would not fail loudly --
    it would play the sound at the wrong pitch."""
    import encode
    import json as _json

    (tmp_path / encode.AUDIO_RAW).write_bytes(b"\0" * 64)
    (tmp_path / "timing.json").write_text(_json.dumps({"audio_rate": 96000}))
    args = encode.audio_input(tmp_path)
    assert args[args.index("-ar") + 1] == "96000"

    # With nothing recorded it falls back to the rate the harness defaults to.
    (tmp_path / "timing.json").unlink()
    args = encode.audio_input(tmp_path)
    assert args[args.index("-ar") + 1] == str(encode.AUDIO_RATE)


def test_audio_is_encoded_at_an_ordinary_rate():
    """Left alone ffmpeg followed the 192 kHz capture and wrote 96 kHz AAC,
    which is unusual, less portable, and pointless above a 20 kHz filter."""
    import encode

    for opts in (encode.AUDIO_MP4, encode.AUDIO_WEBM):
        assert opts[opts.index("-ar") + 1] == "48000"
