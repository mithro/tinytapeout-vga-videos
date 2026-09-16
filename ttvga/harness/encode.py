#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Turn a raw capture into the published clips and previews. Runs on the host.

The simulation writes `capture.avi`, motion JPEG at near-lossless quality,
because that is cheap to produce a frame at a time while Verilator runs. It is
not the deliverable: browsers will not play motion JPEG in an AVI container.
This module transcodes that capture into what a browser can actually play, and
renders the still and moving previews the index page uses.

Two codecs are written for every clip. H.264 in MP4 plays on everything and,
measured on this material, is both smaller and about four times faster to
encode than VP9; WebM is published beside it because it is what YouTube
prefers and what a caller may ask for. A `<video>` element listing both lets
the browser take whichever it understands.

Every published file carries `<shuttle>_<macro>` in its name, so a clip that
has been downloaded, attached or uploaded still says which project it is.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

# Clips are published at twice the design's own resolution, scaled with
# nearest-neighbour so the pixel edges stay hard. This is not for extra
# detail, which does not exist: 4:2:0 chroma is subsampled by two in each
# axis, so at twice size the colour plane lands back exactly on the design's
# own pixel grid and every pixel keeps its own colour. At native size each
# pair of neighbouring pixels would have to share one, which is ruinous on
# the flat saturated colours these designs draw. It also makes the frame
# dimensions even, which yuv420p requires and several designs are not.
UPSCALE = "scale=iw*2:ih*2:flags=neighbor"

# A ceiling on the bit rate, not a target. Quality-based encoding suits these
# designs: most draw flat colour and land around 0.5 Mbit/s, nowhere near this.
# A handful draw per-pixel noise, which is incompressible, and produced 850 MB
# for one minute of video -- too big to stream, and slower to encode than
# everything else put together. Measured on the worst of them, this cap takes
# that minute from 850 MB to 96 MB. The noise is visibly coarser and nothing
# else changes, which is the right trade for showing what a design puts out.
MAX_BITRATE = "12M"
BUFSIZE = "24M"

# VP9 has to be written limited range, and this is not cosmetic: a full range
# VP9 stream does not play in Chrome at all on a machine using its hardware
# decoder, whatever the matrix says. Tested on one clip against a browser that
# failed on the published file -- full range failed with both a bt470bg and a
# bt709 matrix, limited range played with either, so the range alone decides
# it. Software decoders (ffmpeg, VLC, a Chromium without GPU decode) play the
# full range file happily, which is why this survived the earlier checks.
#
# The conversion costs almost nothing here. These designs drive two bits per
# channel, so every pixel is one of 0, 85, 170 or 255, and limited range has
# 219 levels to place four values in.
#
# The MP4 is left full range: H.264 hardware decoding does not have the same
# trouble, and re-encoding it would cost a generation for no gain.
WEBM_COLOUR = "scale=out_range=tv:out_color_matrix=bt709"
WEBM_COLOUR_FLAGS = ["-color_range", "tv", "-colorspace", "bt709",
                     "-color_trc", "bt709", "-color_primaries", "bt709"]

# Lengths published for every project, longest first: the shorter clips are cut
# from the longest one rather than encoded again.
LENGTHS = (60, 30, 10)

# The contact sheet's grid lines. A pale neutral, because the frames
# themselves often have coloured borders that a strong colour would echo.
GRID_COLOUR = "0xd8d5e0"
GRID_GAP = 6
GIF_WIDTH = 320
GIF_FPS = 12
GIF_SECONDS = 8.0
# Where the poster frame and the animation both begin. By then most designs
# have drawn something, and starting both at the same instant is what stops the
# thumbnail jumping when the animation replaces it.
PREVIEW_START = 5.0

# The captured audio, if the design drove the Audio Pmod pin. It arrives as
# mono 32 bit float at this rate; ffmpeg resamples it when encoding.
AUDIO_RAW = "capture.f32"
AUDIO_RATE = 192000
# The captured signal is a PWM bit averaged into 0..1, so it carries a large DC
# offset. Removing it costs nothing audible -- 20 Hz is below the Audio Pmod's
# own passband -- and without it the track wastes most of its headroom and can
# click at the start and end.
AUDIO_FILTER = "highpass=f=20"
AUDIO_MP4 = ["-c:a", "aac", "-b:a", "128k"]
AUDIO_WEBM = ["-c:a", "libopus", "-b:a", "128k"]

QUIET = ["-hide_banner", "-loglevel", "error", "-y"]


def run(cmd: list[str], log: Path, cwd: Path | None = None, timeout: float | None = None,
        env: dict[str, str] | None = None, grace: float = 0.0) -> int:
    """Run a command, appending its output to `log`. Returns the exit code (124 on timeout).

    With `grace`, a timeout first sends SIGTERM and waits that long for the
    command to finish on its own (the model then closes ffmpeg cleanly).
    """
    with log.open("a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n")
        f.flush()
        p = subprocess.Popen(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=env)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            f.write(f"\n[timeout after {timeout}s]\n")
            p.terminate()
            try:
                p.wait(timeout=grace or 5)
                f.write(f"[finished after SIGTERM, exit {p.returncode}]\n")
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                f.write("[killed]\n")
            return 124
        f.write(f"[exit {p.returncode}]\n")
        return p.returncode


def audio_input(src_dir: Path, rate: float | None = None) -> list[str]:
    """ffmpeg arguments for the captured audio, or nothing if there is none.

    The rate comes from the simulation's own record where there is one. Raw
    samples carry no rate of their own, so guessing it wrong here would not
    fail: it would silently play the sound at the wrong pitch.
    """
    raw = src_dir / AUDIO_RAW
    if not raw.exists() or raw.stat().st_size == 0:
        return []
    if rate is None:
        timing = src_dir / "timing.json"
        if timing.exists():
            try:
                rate = float(json.loads(timing.read_text()).get("audio_rate") or 0) or None
            except (json.JSONDecodeError, ValueError, TypeError):
                rate = None
    return ["-f", "f32le", "-ar", str(int(rate or AUDIO_RATE)), "-ac", "1", "-i", str(raw)]


def stem_for(shuttle: str, macro: str) -> str:
    """The prefix every published file for this project carries."""
    return f"{shuttle}_{macro}"


def clip_names(stem: str) -> list[str]:
    """Every clip published for a project, longest first."""
    return [f"{stem}_{secs}s.{ext}" for secs in LENGTHS for ext in ("mp4", "webm")]


def preview_names(stem: str) -> list[str]:
    """The poster, contact sheet and animation published for a project."""
    return [f"{stem}_poster.png", f"{stem}_contact.png", f"{stem}_preview.gif"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def published_files(videos: Path) -> dict:
    """What a project has published, in the form `result.json` records it.

    Both the job that simulates a project and the pass that re-transcodes one
    have to write this, and the index page reads it to decide which clips to
    link. Three copies of the same few lines would be three chances for the
    page to disagree with the disk, so there is one.
    """
    if not videos.exists():
        return {}
    return {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(videos.iterdir()) if p.is_file()}


def transcode(src: Path, videos: Path, stem: str, log: Path, ffmpeg: str,
              audio_rate: float | None = None) -> str | None:
    """Write the full-length clip in both codecs, then cut the shorter ones.

    Keyframes are forced at each cut point so the shorter clips can be copied
    straight out of the long one: without them a copy would end mid-group and
    the last second or so would decode as garbage.
    """
    cuts = ",".join(str(s) for s in LENGTHS[1:])
    full = LENGTHS[0]

    audio = audio_input(src.parent, audio_rate)
    audio_opts = ([*AUDIO_MP4, "-af", AUDIO_FILTER, "-shortest"] if audio else ["-an"])
    mp4 = videos / f"{stem}_{full}s.mp4"
    if run([ffmpeg, *QUIET, "-i", str(src), *audio, "-vf", UPSCALE,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-maxrate", MAX_BITRATE, "-bufsize", BUFSIZE, *audio_opts,
            "-force_key_frames", cuts, "-movflags", "+faststart", str(mp4)], log, timeout=3600) != 0:
        return "ffmpeg h264 failed"

    if (err := encode_webm(src, videos / f"{stem}_{full}s.webm", log, ffmpeg, cuts,
                           upscale=True, audio=audio)):
        return err

    for secs in LENGTHS[1:]:
        for ext, extra in (("mp4", ["-movflags", "+faststart"]), ("webm", [])):
            source = videos / f"{stem}_{full}s.{ext}"
            if run([ffmpeg, *QUIET, "-i", str(source), "-t", str(secs), "-c", "copy",
                    *extra, str(videos / f"{stem}_{secs}s.{ext}")], log, timeout=600) != 0:
                return f"ffmpeg cut {secs}s {ext} failed"

    missing = [n for n in clip_names(stem) if not (videos / n).exists()]
    return ("failed to write " + ", ".join(missing)) if missing else None


def encode_webm(src: Path, dest: Path, log: Path, ffmpeg: str, cuts: str,
                upscale: bool, audio: list[str] | None = None) -> str | None:
    """Write one WebM. `upscale` is False when the source is already 2x.

    VP9 at its default deadline is far slower than x264 for no visible gain on
    flat pixel art; `good` with `cpu-used 4`, row threading and tile columns is
    the compromise that keeps a four hundred clip run inside an hour.

    crf 36 rather than a lower number: measured on a ten second clip, VP9 at
    crf 32 produced a larger file than x264 at crf 18, because the two crf
    scales are not comparable. libvpx also spells the bit rate ceiling
    differently from x264: once `-crf` is given, `-b:v` stops being a target
    and becomes the ceiling.
    """
    vf = f"{UPSCALE},{WEBM_COLOUR}" if upscale else WEBM_COLOUR
    # When re-encoding from a published MP4 the audio is already in it, so it
    # is copied across rather than taken from a raw file that may be long gone.
    if audio is None:
        audio, audio_opts = [], [*AUDIO_WEBM, "-map", "0:v:0", "-map", "0:a?"]
    else:
        audio_opts = ([*AUDIO_WEBM, "-af", AUDIO_FILTER, "-shortest"] if audio else ["-an"])
    if run([ffmpeg, *QUIET, "-i", str(src), *audio, "-vf", vf,
            "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", MAX_BITRATE, "-pix_fmt", "yuv420p",
            *WEBM_COLOUR_FLAGS, *audio_opts,
            "-deadline", "good", "-cpu-used", "4", "-row-mt", "1", "-threads", "4",
            "-tile-columns", "2", "-force_key_frames", cuts, str(dest)], log, timeout=7200) != 0:
        return "ffmpeg vp9 failed"
    return None


def rewrite_webm(videos: Path, stem: str, log: Path, ffmpeg: str) -> str | None:
    """Rebuild a project's WebM clips from its published MP4.

    Used to correct clips already published when the capture they came from is
    gone. The MP4 is the best source left and is already at the published size,
    so it is not upscaled again.
    """
    full = LENGTHS[0]
    src = videos / f"{stem}_{full}s.mp4"
    if not src.exists():
        return f"no {src.name}"
    cuts = ",".join(str(x) for x in LENGTHS[1:])
    if (err := encode_webm(src, videos / f"{stem}_{full}s.webm", log, ffmpeg, cuts, upscale=False)):
        return err
    for secs in LENGTHS[1:]:
        if run([ffmpeg, *QUIET, "-i", str(videos / f"{stem}_{full}s.webm"), "-t", str(secs),
                "-c", "copy", str(videos / f"{stem}_{secs}s.webm")], log, timeout=600) != 0:
            return f"ffmpeg cut {secs}s webm failed"
    return None


def render_previews(videos: Path, stem: str, log: Path, ffmpeg: str, frames: int, fps: float) -> str | None:
    """Poster, contact sheet and animation, from the published MP4.

    The MP4 is twice the design's own size, so the halving and quartering here
    put the poster back at native resolution and the contact sheet frames at
    half of it, which is what they were before the clips became browser-playable.
    """
    src = videos / f"{stem}_{LENGTHS[0]}s.mp4"
    if not src.exists():
        return f"no {src.name}"
    duration = frames / fps if fps else 0.0

    # The poster and the animation start at the same instant. They are two
    # views of one moment: the page shows the poster and swaps the animation in
    # on a click, so a poster taken from anywhere else makes the picture jump
    # backwards the moment it starts playing.
    start = min(PREVIEW_START, duration / 2) if duration else PREVIEW_START
    run([ffmpeg, *QUIET, "-ss", f"{start:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", "scale=iw/2:-1", str(videos / f"{stem}_poster.png")], log, timeout=600)

    # 16 frames spread across the clip, half size, with grid lines between them
    # so one frame's black background cannot be mistaken for its neighbour's.
    step = max(1, frames // 16)
    run([ffmpeg, *QUIET, "-i", str(src),
         "-vf", f"select='not(mod(n\\,{step}))',scale=iw/4:-1,"
                f"tile=4x4:padding={GRID_GAP}:margin={GRID_GAP}:color={GRID_COLOUR}",
         "-frames:v", "1", str(videos / f"{stem}_contact.png")], log, timeout=900)

    # A short animation for the index page, played at the speed the design
    # actually runs at. An earlier version sampled evenly across all sixty
    # seconds and replayed that at GIF_FPS, so the whole clip was covered but
    # consecutive frames were 625 ms apart: anything moving teleported, and the
    # result read as a broken frame rate rather than a fast one. Real time is
    # worth more than coverage here, because the contact sheet already shows
    # the whole clip and this is the only place the motion can be judged.
    #
    # `fps` resamples to GIF_FPS and `-r` states that the output really is that
    # rate. Both are needed: the filter alone leaves the encoder free to drop
    # frames back towards the source rate.
    length = min(GIF_SECONDS, duration - start) if duration else GIF_SECONDS
    run([ffmpeg, *QUIET, "-ss", f"{start:.3f}", "-t", f"{max(length, 1.0):.3f}", "-i", str(src),
         "-vf", f"fps={GIF_FPS},scale={GIF_WIDTH}:-1:flags=neighbor,split[a][b];"
                f"[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none",
         "-r", str(GIF_FPS), "-loop", "0", str(videos / f"{stem}_preview.gif")], log, timeout=900)

    missing = [n for n in preview_names(stem) if not (videos / n).exists()]
    return ("failed to render " + ", ".join(missing)) if missing else None
