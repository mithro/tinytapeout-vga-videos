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

# Lengths published for every project, longest first: the shorter clips are cut
# from the longest one rather than encoded again.
LENGTHS = (60, 30, 10)

# The contact sheet's grid lines. A pale neutral, because the frames
# themselves often have coloured borders that a strong colour would echo.
GRID_COLOUR = "0xd8d5e0"
GRID_GAP = 6
GIF_WIDTH = 320
GIF_FPS = 12
# How long the animation plays for. It covers the whole clip regardless: frames
# are sampled evenly across the full length and replayed at GIF_FPS, so this is
# the length of the preview, not the length of video it represents.
GIF_SECONDS = 8.0

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


def stem_for(shuttle: str, macro: str) -> str:
    """The prefix every published file for this project carries."""
    return f"{shuttle}_{macro}"


def clip_names(stem: str) -> list[str]:
    """Every clip published for a project, longest first."""
    return [f"{stem}_{secs}s.{ext}" for secs in LENGTHS for ext in ("mp4", "webm")]


def preview_names(stem: str) -> list[str]:
    """The poster, contact sheet and animation published for a project."""
    return [f"{stem}_poster.png", f"{stem}_contact.png", f"{stem}_preview.gif"]


def transcode(src: Path, videos: Path, stem: str, log: Path, ffmpeg: str) -> str | None:
    """Write the full-length clip in both codecs, then cut the shorter ones.

    Keyframes are forced at each cut point so the shorter clips can be copied
    straight out of the long one: without them a copy would end mid-group and
    the last second or so would decode as garbage.
    """
    cuts = ",".join(str(s) for s in LENGTHS[1:])
    full = LENGTHS[0]

    mp4 = videos / f"{stem}_{full}s.mp4"
    if run([ffmpeg, *QUIET, "-i", str(src), "-vf", UPSCALE,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-maxrate", MAX_BITRATE, "-bufsize", BUFSIZE,
            "-force_key_frames", cuts, "-movflags", "+faststart", str(mp4)], log, timeout=3600) != 0:
        return "ffmpeg h264 failed"

    # VP9 at its default deadline is far slower than x264 for no visible gain
    # on flat pixel art; `good` with `cpu-used 2` and row threading is the
    # usual compromise.
    #
    # crf 36 rather than a lower number: measured on a 10 second clip, VP9 at
    # crf 32 produced a *larger* file than x264 at crf 18 because the two
    # scales are not comparable. 36 lands at about the same size and quality
    # as the MP4, so the WebM is a real alternative rather than a bigger one.
    #
    # libvpx spells the cap differently from x264: once `-crf` is given,
    # `-b:v` stops being a target and becomes the ceiling, so it carries
    # MAX_BITRATE here where x264 takes `-maxrate`.
    webm = videos / f"{stem}_{full}s.webm"
    if run([ffmpeg, *QUIET, "-i", str(src), "-vf", UPSCALE,
            "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", MAX_BITRATE, "-pix_fmt", "yuv420p",
            # `cpu-used` is VP9's speed against compression knob, and it has to
            # be turned up here. At 2, VP9 was taking twenty-one of every
            # twenty-two encoder slots on the host and single clips were running
            # twelve minutes, which put the whole set at about seven hours for a
            # format that measures no smaller than the MP4 beside it. At 4 the
            # files grow a few per cent and the run becomes tractable.
            # `tile-columns` lets a 1280-wide frame be split across threads.
            "-deadline", "good", "-cpu-used", "4", "-row-mt", "1", "-threads", "4",
            "-tile-columns", "2",
            "-force_key_frames", cuts, str(webm)], log, timeout=7200) != 0:
        return "ffmpeg vp9 failed"

    for secs in LENGTHS[1:]:
        for ext, extra in (("mp4", ["-movflags", "+faststart"]), ("webm", [])):
            source = videos / f"{stem}_{full}s.{ext}"
            if run([ffmpeg, *QUIET, "-i", str(source), "-t", str(secs), "-c", "copy",
                    *extra, str(videos / f"{stem}_{secs}s.{ext}")], log, timeout=600) != 0:
                return f"ffmpeg cut {secs}s {ext} failed"

    missing = [n for n in clip_names(stem) if not (videos / n).exists()]
    return ("failed to write " + ", ".join(missing)) if missing else None


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

    # A frame from about 5 s in: by then most designs have drawn something.
    poster_at = min(5.0, duration / 2)
    run([ffmpeg, *QUIET, "-ss", f"{poster_at:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", "scale=iw/2:-1", str(videos / f"{stem}_poster.png")], log, timeout=600)

    # 16 frames spread across the clip, half size, with grid lines between them
    # so one frame's black background cannot be mistaken for its neighbour's.
    step = max(1, frames // 16)
    run([ffmpeg, *QUIET, "-i", str(src),
         "-vf", f"select='not(mod(n\\,{step}))',scale=iw/4:-1,"
                f"tile=4x4:padding={GRID_GAP}:margin={GRID_GAP}:color={GRID_COLOUR}",
         "-frames:v", "1", str(videos / f"{stem}_contact.png")], log, timeout=900)

    # A short animation for the index page, covering the whole clip rather than
    # a window of it: a design that only changes after forty seconds looked
    # static in a six second excerpt taken from the start. Frames are sampled
    # evenly across the full length and retimed to GIF_FPS, which makes the
    # preview a time-lapse of the entire video.
    #
    # `fps` picks the frames and `setpts` retimes them, but `fps` also fixes
    # the stream's frame rate at the sampling rate. Once `setpts` has pulled
    # the timeline in, the encoder drops frames to get back to that rate: a
    # sixty second clip came out as fourteen frames. The output `-r` below
    # sets the rate the retimed frames actually have, which stops the drop.
    if duration > GIF_SECONDS:
        sample_fps = (GIF_SECONDS * GIF_FPS) / duration
        speed = GIF_FPS / sample_fps
        timing = f"fps={sample_fps:.6f},setpts=PTS/{speed:.6f},"
    else:
        timing = f"fps={GIF_FPS},"
    # The source draws at most 64 colours, so a generated palette is exact, and
    # nearest-neighbour scaling keeps the pixel edges hard instead of smearing.
    run([ffmpeg, *QUIET, "-i", str(src),
         "-vf", f"{timing}scale={GIF_WIDTH}:-1:flags=neighbor,split[a][b];"
                f"[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none",
         "-r", str(GIF_FPS), "-loop", "0", str(videos / f"{stem}_preview.gif")], log, timeout=900)

    missing = [n for n in preview_names(stem) if not (videos / n).exists()]
    return ("failed to render " + ", ".join(missing)) if missing else None
