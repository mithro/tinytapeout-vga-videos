# What the published videos are, and why

Every project publishes three lengths in two codecs, plus three previews.
Each decision below cost something to get right, so the reasoning and the
measurements behind it are recorded here rather than left in the code.

The encoder settings all live in one place, `ttvga/harness/encode.py`.

## What is published

For a project `<macro>` on shuttle `<shuttle>`, in
`~ttvga/<shuttle>/<macro>/`:

```
<shuttle>_<macro>_60s.mp4    H.264, the full clip
<shuttle>_<macro>_60s.webm   VP9, the full clip
<shuttle>_<macro>_30s.mp4    cut from the 60 s clip, not encoded again
<shuttle>_<macro>_30s.webm
<shuttle>_<macro>_10s.mp4
<shuttle>_<macro>_10s.webm
<shuttle>_<macro>_poster.png    one frame, about 5 s in, at native resolution
<shuttle>_<macro>_contact.png   16 frames across the clip, with grid lines
<shuttle>_<macro>_preview.gif   8 s of the clip at its own speed, 96 frames
```

Every name carries the shuttle and the project. A clip that has been
downloaded, attached to a message or uploaded still says what it is, instead
of being one more `60s.mp4` in a downloads folder.

## Why not motion JPEG, which is what the simulation writes

The simulation writes `capture.avi`, motion JPEG at near-lossless quality,
because that is cheap to produce one frame at a time while Verilator runs.
It is a capture format, not a delivery one: no browser ships an AVI demuxer,
so every link to one was a download rather than a video. The capture stays in
the work directory and is transcoded into what a browser can play.

The transcode is also a large saving, because motion JPEG codes every frame
independently and cannot exploit the fact that these designs mostly redraw
the same picture. One measured example, Nyan Cat on tt09: 857 MB of motion
JPEG became a 35 MB MP4.

## Why the clips are twice the design's resolution

A 640x480 design is published at 1280x960. The upscale is nearest-neighbour,
so each design pixel becomes a 2x2 block of identical pixels: no detail is
invented and nothing is blurred. Designs at other modes are doubled the same
way, 800x600 to 1600x1200.

The reason is chroma subsampling. Every H.264 or VP9 profile that browsers
reliably decode stores colour as `yuv420p`, which keeps **one colour sample
per 2x2 block of pixels**. Encoded at the native 640x480, two horizontally
adjacent design pixels of different colours are forced to share a single
colour sample. These designs draw flat, saturated, single-pixel detail —
text, sprites, dithered patterns — which is the worst case for that.

Doubling first puts the chroma grid back exactly on the design's own pixel
grid: the four pixels of each 2x2 block have identical colour, so whatever
the subsampling averages over them is that colour exactly, and every design
pixel keeps its own.

The alternative, encoding 4:4:4 at the native size, keeps colour per pixel
but is not reliably playable in a browser, which defeats the purpose.

Doubling also makes the frame dimensions even, which `yuv420p` requires and
several designs are not: one comes out 703 pixels wide.

The cost is small. The median published 60 s MP4 is 0.6 MB.

*Note: the chroma argument above is reasoning from how 4:2:0 works, not a
measurement. The measurements in the rest of this document are measurements.*

## Why both H.264 and VP9

H.264 in MP4 plays everywhere, including the older Safari and iOS versions
whose VP9 support cannot be relied on. VP9 in WebM is published beside it
because it is what YouTube prefers and what a caller may ask for. The index
page offers both and lets the browser choose.

VP9 is **not** the smaller or cheaper codec on this material, which is worth
knowing before assuming otherwise. Measured on ten seconds at 1280x960:

| codec        | size    | encode time |
| ------------ | ------- | ----------- |
| x264 crf 18  | 6.0 MB  | 5.0 s       |
| VP9 crf 32   | 6.8 MB  | 23.8 s      |
| VP9 crf 36   | 5.8 MB  | 22.1 s      |
| VP9 crf 40   | 4.7 MB  | 21.2 s      |

The two crf scales are not comparable: VP9 at 32 was both larger and four
times slower than H.264 at 18. VP9 is set to crf 36 so the WebM is not the
larger file. Dropping WebM entirely would roughly halve the pipeline's
running time.

## Why the WebM is limited range

VP9 must be written limited range (`tv`). A full range VP9 stream does not
play in Chrome at all on a machine that decodes VP9 in hardware: the video
element loads, reports its size and duration, and then never produces a
picture.

This is worth stating plainly because every check that does not involve a GPU
passes it. ffmpeg decodes the full range file, VLC decodes it, and a Chromium
running without GPU decode plays it start to finish with frames counted.
Only real Chrome on real hardware refuses.

Four variants of one clip, each tested in a browser that had failed on the
published file:

| range        | matrix     | plays |
| ------------ | ---------- | ----- |
| `pc` (full)  | `bt470bg`  | no    |
| `pc` (full)  | `bt709`    | no    |
| `tv` (limited) | `bt470bg` | yes   |
| `tv` (limited) | `bt709`  | yes   |

So the range decides it and the matrix does not. The encoder writes `tv` with
a `bt709` matrix, which is the conventional pairing and self-consistent.

The conversion costs almost nothing on this material. These designs drive two
bits per channel, so every pixel is one of 0, 85, 170 or 255, and limited
range has 219 levels to place four values in.

The MP4 is deliberately left full range: H.264 hardware decoding does not have
the same trouble, and re-encoding it would cost a generation for no gain.

Where the bad tags came from: the capture is MJPEG, which is `yuvj420p`, full
range, and ffmpeg labels it `bt470bg` with transfer and primaries
unspecified. Those tags were carried into the VP9 encode unexamined. Anything
derived from a JPEG-family source needs its colour metadata stated
deliberately rather than inherited.

## How good the transcode is

Measured on one frame of Nyan Cat, against the capture, at the published
resolution:

| codec                | PSNR    |
| -------------------- | ------- |
| H.264 crf 18         | 42.5 dB |
| VP9 crf 32           | 43.7 dB |

Above about 40 dB the difference is not visible. 

**Test on hardware, not only in software.** The colour range fault above was
invisible to ffmpeg, VLC and a software Chromium, and obvious in one click in
a normal browser.

**Measure at the geometry the codec saw.** Comparing the same frame against
the capture at the *design* resolution instead gave 22 dB, which looks like
a disaster and is not one: halving the published clip with the default
bicubic filter rings on hard pixel edges, and the comparison measures the
ringing. Either compare at the published size, or downscale with a filter
that point-samples.

## Why there is a bit rate ceiling

Most of these designs draw flat colour and encode to around 0.5 Mbit/s,
nowhere near any limit. A few draw per-pixel noise, which is incompressible,
and produced 850 MB for a single minute of video: too big to stream, and
slower to encode than every other project put together.

Raising the quality number does not fix that. Measured on the worst of them,
ten seconds at 1280x960:

| setting                    | size   | PSNR    |
| -------------------------- | ------ | ------- |
| crf 18, no ceiling         | 142 MB | 35.7 dB |
| crf 20, no ceiling         | 121 MB | 34.0 dB |
| crf 22, no ceiling         | 101 MB | 32.2 dB |
| crf 24, no ceiling         | 82 MB  | 30.2 dB |
| crf 18, 12 Mbit/s ceiling  | 16 MB  | 23.2 dB |

So the encoder keeps quality-based encoding, with a VBV ceiling of
12 Mbit/s. It is a ceiling and not a target: it never binds on the nine in
ten projects that sit two orders of magnitude below it, and nothing about
them changes. Where it does bind, the noise is visibly coarser, which is a
fair trade for a clip that will actually play.

After the ceiling, across the published set: median 60 s MP4 0.6 MB, largest
91 MB, none above 100 MB. Before it, 18 of the first 110 were above 100 MB
and the largest was 857 MB.

libvpx spells the ceiling differently from x264: once `-crf` is given, `-b:v`
stops being a target and becomes the ceiling, so it carries it there where
x264 takes `-maxrate`.

## How the shorter clips are cut

The 30 s and 10 s clips are copied out of the 60 s one rather than encoded
again, which matters most for VP9. Keyframes are forced at 10 s and 30 s so
a copy ends on a group boundary; without them the copy would end mid-group
and its last second would decode as garbage.

## How the animated preview is made

Eight seconds of the clip at the speed the design actually runs at, sampled
to 12 fps, beginning five seconds in. The poster frame is taken from that
same instant, which is the only arrangement where swapping the animation in
for the poster does not make the picture jump.

It has been the other way round. An earlier version sampled evenly across all
sixty seconds and replayed that at 12 fps, so the whole clip was covered in
eight seconds. That reads as a broken frame rate rather than a fast one:
consecutive frames are 625 ms apart, so anything moving teleports between
them. Coverage is worth less than legible motion here, because the contact
sheet already shows the whole clip and the animation is the only place the
motion can be judged at all.

One trap worth keeping, because it is silent and the result still looks like
a valid GIF: `fps` does not only pick frames, it also fixes the stream's
frame rate at the sampling rate, and the encoder will then drop frames to get
back to it. The output `-r` has to state the rate the frames actually have.
Measured while the preview was still a time-lapse:

| filter chain                                | frames | size    |
| ------------------------------------------- | ------ | ------- |
| `fps=1.6,setpts=PTS/7.5`, no output rate    | 14     | 0.6 MB  |
| `fps=1.6,setpts=PTS/7.5`, `-r 12`           | 99     | 1.3 MB  |
| `select` every 37th frame, `setpts=N/12/TB` | 98     | 3.9 MB  |

## Serving them

See [publishing.md](publishing.md). One thing belongs here too, because it
stops a correct clip from playing: an nginx `types` block inside a location
*replaces* nginx's own table rather than extending it, so anything it forgets
is served as `application/octet-stream`, and no browser will play a video or
animate a GIF handed to it under that type.
