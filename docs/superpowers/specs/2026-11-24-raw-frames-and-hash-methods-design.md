# Raw frames and pluggable frame hashes

Status: design, awaiting review (2026-11-24).

## Why

The pipeline keeps one 64-bit hash per captured frame
(`data/results/<shuttle>/<macro>/frame_hashes.txt`). Other implementations of
the same designs (the iCE40 VGA Playground harness, the handheld harness)
compare their output against those hashes. A hash can only say *whether* two
frames differ. When they differ, finding out *why* needs the pixels, and the
pipeline has never kept them: `tb.cpp` pipes frames to ffmpeg, which writes
`capture.avi` as MJPEG (lossy, `-q:v 2`), and even that is deleted after the
clips are encoded.

The owner's decisions (2026-11-24):

- Keep lossless copies of the captured frames. They are the record.
- Hashes are only an optimisation for deciding quickly whether frames match.
- Hash methods are pluggable, and every hash file says which method made it.
- Frames are published beside the videos on data.wafer.space.
- Two frame formats, packed and PNG, with tools to convert either way.

## Sizes

From the 408 current results: 1,475,096 frames, 543,730 of them distinct.
391 projects are 640x480, 13 are 800x600, 4 are 640x504. At one byte per
pixel the distinct frames are about 172 GB before compression; flat VGA art
should compress far below that, but this is to be measured (step 1 of the
rollout) before the full run. big-storage has 776 GB free.

## The pixel: rgb6

A design drives 2 bits per colour on `uo_out`: R = (uo[0], uo[4]),
G = (uo[1], uo[5]), B = (uo[2], uo[6]), first bit most significant. One pixel
is stored as one byte:

    rgb6 = R << 4 | G << 2 | B        (0..63, top two bits zero)

This is exactly what came out of the pins, and it is the value `tb.cpp`
already uses for its colour count. Display colour is each 2-bit channel
times 85.

A frame is `width * height` rgb6 bytes, row-major, active area only, each
pixel sampled in the middle of its pixel period, exactly as `tb.cpp`
captures today. Pixels the design never drove inside the active area stay 0,
as now.

## What is stored per project

Where it lives on the host: the frame store goes in the published tree (the
directory mirrored to data.wafer.space), which sits on a bulk data volume.
It must never be on the host's root volume, and there is one copy, not a
staging copy plus a published one; the simulation's work directories stay on
the fast root volume and only hold frames until they are packed. The actual
paths are local configuration, like the host name.

On the host and on data.wafer.space, under `<shuttle>/<macro>/`:

- `<shuttle>_<macro>_frames.rgb6.zst` -- the canonical store. Each distinct
  frame once, in order of first appearance, each as its own zstd frame
  appended to the file (any zstd decoder reads the whole file as one stream of
  `n * width * height` bytes; the index below gives each frame's offset for
  random access).

In git, beside `result.json`:

- `frames.txt` -- the index and the sequence. A header (`id`, `width`,
  `height`, `pixel_format: rgb6`, `capture_after_clock`, `frames`,
  `distinct_frames`), then one line per distinct frame
  (`<sha256-rgb6> <byte offset> <byte length>` in the .zst), then one line per
  captured frame (`<frame number> <start clock> <sha256-rgb6>`). The start
  clock is the clock at which that frame's vsync pulse ended; with it a
  mismatch can be told apart as different pixels or the same pixels at a
  different time.
- `frame_hashes.<method>.txt` -- one per hash method, see below.

The SHA-256 of the rgb6 bytes is the frame's identity: it names the frame in
the store and in `frames.txt`. It is chosen for that job because two
different frames must never share a name; the 64-bit FNV is not safe for it
across half a million frames.

PNG is the viewing and exchange format: 8-bit indexed, a 64-entry palette in
which index i is rgb6 value i (colour = channel * 85). Converting a PNG back
gives the identical rgb6 bytes, so either format can be the input to every
tool. PNGs are made on demand by the tools; they are not published in bulk
(543,730 small files), unless review decides otherwise.

## Hash methods

A method is the combination of an algorithm, its parameters, and the bytes
fed to it. All three change the value, so all three are in the method's
name. Methods are a registry in `ttvga/framehash.py`; each entry has an id,
a one-paragraph definition written precisely enough to reimplement without
our code (the other harnesses must not import this repository), and a Python
function from rgb6 frame bytes to a hex string.

Initial methods:

| id | algorithm | input |
| --- | --- | --- |
| `sha256-rgb6` | SHA-256 | the rgb6 bytes |
| `fnv1a64-tb2026-rgb888` | FNV-1a 64 loop, prime 0x100000001b3, offset basis 0x14650fb0739d0383 (the standard one with a digit lost) | RGB888, each channel value * 85 |

The second is the method of every hash published so far; its files are
renamed from `frame_hashes.txt` to `frame_hashes.fnv1a64-tb2026-rgb888.txt`.
A standard-basis FNV or any other method can be added later and computed
from the store without simulating again.

Every hash file starts with `hash_method: <id>` and the method's definition
as comment lines, then `id`, `width`, `height`, `frames`, then one hash per
frame, frame 0 first. The method id is also in the file name, so two methods'
files never overwrite each other and a file is never ambiguous on its own.

## Where the work happens

- `tb.cpp` keeps each distinct frame (exact byte comparison, not just the hash)
  and writes them, plus per-frame start clocks, to the run's output directory.
  It no longer hashes for publication; `distinct_frames` and the other
  statistics stay in timing.json.
- `job.py` packs the frames into the .zst, writes `frames.txt` and every
  registered hash method's file, and keeps all of it when it cleans up. The
  MJPEG intermediate and clip encoding are unchanged.
- `tt-vga collect` brings back `frames.txt` and the hash files; the .zst stays
  on the host and is published by `tt-vga mirror` with the clips.

## Tools (`tt-vga frames ...`)

- `to-png STORE|frames.txt FRAME... -o DIR` and `from-png PNG...` -- convert
  either way; a round trip is byte-identical.
- `hash --method ID` -- compute any registered method from a store or PNGs, to
  add a method or check a file.
- `diff A B` -- A and B are frames from either side (a store and frame number,
  or a PNG): count of differing pixels, their bounding box, per-channel
  differences, and a PNG showing the differences. This is the tool for "the
  hashes don't match, why?".
- `compare frames.txt OTHER` -- align two whole runs by hash, report the first
  mismatching frame and whether it is a shift in time (same frames, different
  start clocks or offset) or different content.

## Rollout

1. Implement on a branch with tests (rgb6 packing, PNG round trip, each hash
   method against known vectors, store offsets).
2. Run 5 projects of different kinds (nyancat, metaballs at 800x600, a static
   one, a QSPI one, the 640x504 tennis game); measure the compressed size and
   check the `fnv1a64-tb2026-rgb888` values computed from the stored frames
   equal the published ones exactly.
3. Report the measured size projected to all 408 before the full run.
4. Re-run all projects (several hours, progress reported per the usual
   cadence); verify the regenerated legacy hashes equal all 408 committed
   files; publish; tell the two harness sessions about the new files.

## Not in scope

- Keeping blanking intervals or sync-level timing per pixel. The start clock
  per frame covers time shifts; finer timing would come later if a mismatch
  needs it.
- Changing what the videos are made from.
