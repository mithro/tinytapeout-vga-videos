# Raw frames and pluggable frame hashes

Status: design, revised after an independent review, awaiting the owner's
review (2026-11-24).

## Why

The pipeline keeps one 64-bit hash per captured frame
(`data/results/<shuttle>/<macro>/frame_hashes.txt`). Other implementations of
the same designs (the iCE40 VGA Playground harness, the handheld harness)
compare their output against those hashes. A hash can only say *whether* two
frames differ. When they differ, finding out *why* needs the pixels, and the
pipeline has never kept them: `tb.cpp` pipes frames to ffmpeg, which writes
`capture.avi` as MJPEG (lossy, `-q:v 2`, `tb.cpp:464`), and even that is
deleted after the clips are encoded (`job.py:383`).

The owner's decisions (2026-11-24):

- Keep lossless copies of the captured frames. They are the record.
- Hashes are only an optimisation for deciding quickly whether frames match.
- Hash methods are pluggable, and every hash file says which method made it.
- Frames are published beside the videos on data.wafer.space, and live on the
  host's bulk data volume, never its root volume.
- Two frame formats, a packed store and PNG, with tools to convert either way.

## Sizes

From the 408 current results: 1,475,096 captured frames. 543,730 of them are
distinct *by the current 64-bit FNV hash* (`tb.cpp:477,488`); the exact count
by SHA-256 comes out of rollout step 2, and any difference is an FNV
collision, which will be reported. 391 projects are 640x480, 13 are 800x600,
4 are 640x504. At one byte per pixel the distinct frames are about 172 GB
before compression. The compressed size is measured in rollout step 2 and
projected to all 408 projects before the full run (step 3).

## The pixel: rgb6

A design drives 2 bits per colour on `uo_out`: R = (uo[0], uo[4]),
G = (uo[1], uo[5]), B = (uo[2], uo[6]), first bit most significant
(`tb.cpp:550-552`). One pixel is stored as one byte:

    rgb6 = R << 4 | G << 2 | B        (0..63, top two bits zero)

This is exactly what came out of the pins, and the value `tb.cpp` already
uses for its colour count (`tb.cpp:497`). Display colour is each 2-bit
channel times 85. A frame is `width * height` rgb6 bytes, row-major, active
area only. Pixels inside the active area that were never sampled stay 0.

### Sampling, stated exactly (`sampling: tb-v1`)

Let `t` be the number of clocks since the end of the hsync pulse and `cpp`
the clocks per pixel. Pixel index `p = floor((t + cpp/2) / cpp)`; a pixel is
sampled at the first clock at which `p` reaches a new value, and stored at
column `p - hback` (`tb.cpp:541-553`). The code's comment calls this the
middle of the pixel period. That is only true for `cpp = 1`. Otherwise pixel
`p` is first reached at `t = (p - 1/2) * cpp`, which is half a pixel *before*
its nominal period starts. At `cpp = 2` that is the second clock of pixel
`p - 1`.

47 of the 408 projects have `cpp != 1` (27 at 2.0, 9 at 1.9062, 5 at 4.2667,
3 at 1.04, 3 at 0.9524). Every published hash used tb-v1, so the store
records the rule by name (`sampling: tb-v1` in `frames.txt`). Whether and
when to change it is a decision for the owner, below.

## What is stored, and where

Per project, under `frames/<shuttle>/<macro>/` in the published tree:

- `<shuttle>_<macro>_frames.rgb6.zst` -- the store. The distinct frames in
  order of first appearance, concatenated, as one zstd stream. Distinct frame
  `n` is at uncompressed byte offset `n * width * height`. One stream with
  long-distance matching (`zstd --long`) lets zstd use the similarity between
  frames, which compressing each frame alone would lose. The cost is random
  access: reading frame `n` means decompressing from the start, at most about
  2 GB for the largest project (metaballs, 4325 distinct 800x600 frames),
  around a second or two. Rollout step 2 measures this against one zstd frame
  per image (random access, worse compression) and picks the level; the
  choice and the numbers are recorded in docs/.
- `frames.txt` -- the index, described below.
- `frame_hashes.<method>.txt` -- one per hash method computed for the run.
- `png/<n>.png` and `index.html` -- every distinct frame as a PNG and a page
  to browse them, see PNG below.

### Where on the host: one copy, on the bulk volume

The frames directory is owned by the pipeline user and sits inside the
published tree, which is on the bulk data volume. It is the only copy of the
store; there is no staging copy. A job builds the project's whole frames
directory in a second pipeline-owned directory on the *same* filesystem but
outside the published tree, and renames it into place when complete, so the
5-minute upload never sees a half-written one. Both paths are host configuration
(`~/ttvga/host.toml` on the host: `frames_dir`, `frames_tmp_dir`), never
named in the repository; `docs/host-setup.md` gains the two `install -d`
lines an administrator runs once. Nothing frame-related is written to the
root volume: `tb.cpp` streams distinct frames straight into a `zstd` process
(the same way it already feeds ffmpeg), and keeps only the current frame and
one 32-byte SHA-256 per distinct frame in memory.

The clips themselves still exist twice (the pipeline user's `public_html`
and the published tree, copied by `tt-vga mirror`). That predates this
design and is out of its scope; the same rename-into-place approach could
remove it later.

### In git

Beside each `result.json`:

- `frames.txt`, the index:
  - header: `id`, `status` (ok, unstable-sync or sim-timeout), `sampling`
    (`tb-v1`), `pixel_format: rgb6`, `width`, `height`, `mode`, `clock_hz`,
    `clocks_per_pixel`, `capture_after_clock`, `frame_clocks` (the nominal
    clocks per frame), `frames`, `distinct_frames`, `store` (the store's file
    name and its compressed size and SHA-256);
  - one line per distinct frame: its SHA-256 (the frame's identity, the order
    is the store's order);
  - the sequence, as runs: `<first frame> <count> <distinct number>
    <start clock of the first frame>`, a new run starting whenever the frame
    content changes or a frame starts at other than `frame_clocks` after the
    previous one. A frame's start clock is the clock at which its vsync
    pulse ended.
- `frame_hashes.fnv1a64-tb2026-rgb888.txt`, the existing files renamed and
  given the new header (their hash values unchanged; the conversion asserts
  this).

Size: the distinct-frame lines are 65 bytes each, about 35 MB in total; the
runs add a few MB at most. Git compresses hex to about half. The other hash
files are published with the store, not committed: the SHA-256 per frame
can already be read from `frames.txt`, and committing every method would
grow the repository with each method added. Simulation is deterministic, so
re-running a project produces identical files and adds nothing to git; only
a project whose output really changed rewrites its files.

SHA-256 is the identity because two different frames must never share a
name. The 64-bit FNV is not safe for that across half a million frames.

### PNG

PNG is the viewing and exchange format: 8-bit indexed, a 64-entry palette in
which index i is rgb6 value i (colour = channel * 85), at the design's native
resolution. Converting a PNG back gives the identical rgb6 bytes, so either
format can be the input to every tool.

The owner decided (2026-11-24) that every distinct frame is also published as
a PNG, so it can be looked at in a browser on data.wafer.space:

- `frames/<shuttle>/<macro>/png/<n>.png`, `n` the distinct frame number,
  zero-padded to 6 digits, so the directory lists in frame order. The PNGs
  are written by `job.py` after the run, reading the store with the
  standard library's `compression.zstd` and encoding PNG with `zlib`. The
  whole project directory (store, index, hash files, PNGs, page) is built in
  the temporary directory and renamed into place in one step, replacing the
  previous one, so the upload never sees a half-built project.
- `frames/<shuttle>/<macro>/index.html`: a static page listing every captured
  frame (number, start clock, distinct number) with links to its PNG, the
  distinct frames as a grid of thumbnails, and the frame shown at 1x/2x/4x
  with `image-rendering: pixelated` so pixels stay sharp. No scripts are
  needed to read it.
- The PNGs are derived copies: the `.zst` store stays the canonical record,
  and `tt-vga verify` checks every published PNG decodes to the store's
  bytes.

Cost, to be measured in rollout step 2: about 543,730 extra files. Their
size is unknown until measured (flat VGA art should compress to a few KB a
frame). The file count matters more for the 5-minute upload, which checks
every file on every run: today's 62,641 entries take about 25 s to list, so
roughly ten times as many could take several minutes, every 5 minutes. Step
3 reports the measured listing time; if it is too slow, the options (for the
owner) are a longer upload interval, or the upload skipping the frames tree
except when the pipeline marks it changed.

## Hash methods

A method is the combination of an algorithm, its parameters, and the bytes
fed to it. All three change the value, so all three are in the method's id.
`ttvga/hashmethods.py` is the registry. Each entry has an id, a definition
written precisely enough to reimplement without our code (the other
harnesses must not import this repository), and a reference implementation
from rgb6 frame bytes to a hex string. Test vectors (a few frames and their
expected hash under every method) are committed and checked by the tests.

Initial methods:

| id | algorithm | input |
| --- | --- | --- |
| `sha256-rgb6` | SHA-256 | the rgb6 bytes |
| `fnv1a64-tb2026-rgb888` | FNV-1a 64 loop, prime 0x100000001b3, offset basis 0x14650fb0739d0383 (the standard one with a digit lost) | RGB888, each channel = value * 85 |

Speed: `tb.cpp` computes both initial methods natively while capturing
(SHA-256 through OpenSSL's libcrypto, present on the host; FNV as now), and
the tests check the native output against the Python reference. A method
added later is computed from the store by `tt-vga frames hash`; the Python
reference is fine for that (pure Python FNV is a loop of 921,600 steps per 640x480 frame,
a large fraction of a second each, so slow methods get a native or vectorised implementation when they
are needed for every frame, not before).

Every hash file has this header, then one hash per frame, frame 0 first:
`hash_method: <id>`, the method's definition as comment lines, `id`,
`status`, `sampling`, `mode`, `width`, `height`, `clock_hz`,
`clocks_per_pixel`, `capture_after_clock`, `frames`. The method id is also
in the file name, so files never overwrite each other and none is ambiguous
on its own.

## Runs that do not finish normally

- `sim-timeout` (stopped by the wall-clock limit, `tb.cpp:232`) and
  `unstable-sync`: the frames captured so far are stored and indexed as
  usual, with `status` saying so.
- Input-probe runs (`job.py:236-253`) and calibration: no frames are
  written; `tb.cpp` gets `--no-frames`.
- No picture (no-sync, bad-timing, build-failed, fetch-failed, skipped): no
  store and no index. If an earlier run had frames, the job deletes the stale
  store from the published tree and `collect` deletes the stale `frames.txt`
  and hash file. The upload never deletes on the server, so `tt-vga verify`
  lists published stores that no longer exist locally, for removal there.

## Where the work happens

- `tb.cpp`: rgb6 frame buffer; SHA-256 per frame and the set of distinct
  ones; distinct frames piped to `zstd` writing the temporary store; writes
  `frames.txt` and the two initial hash files to its output directory. It no
  longer writes the `frame_hashes` list into timing.json (`tb.cpp:590-608`);
  `frames`, `distinct_frames` and the other statistics stay there. RGB888 is
  still produced for ffmpeg, as now.
- `job.py` (standard library only, now Python 3.14, see below): passes the
  store paths from `host.toml`, writes the store's size and SHA-256 into
  `frames.txt`, writes the PNGs and `index.html` from the store, renames
  the finished project directory into the frames directory, keeps
  `frames.txt` and the hash files in the work directory, and handles the
  stale-file cases above.
- `ttvga/remote.py`: `collect` brings back `frames.txt` and the
  `fnv1a64-tb2026-rgb888` hash file instead of exporting hashes from
  result.json (`remote.py:263-265`).
- `ttvga/framehashes.py` is removed, its tests (`tests/test_framehashes.py`)
  replaced by tests of `ttvga/hashmethods.py` and `ttvga/framestore.py`; a
  one-off script renames and re-heads the 408 existing hash files.
- README.md (the frame hashes paragraph, lines 82-92) and docs/host-setup.md
  are rewritten for the new files.
- Python 3.14 everywhere, for the standard library's `compression.zstd`
  (checked on the host 2026-11-24: uv fetched CPython 3.14.7 into the
  pipeline user's home and `compression.zstd` round-tripped a test buffer).
  The host's queue and jobs stop using the system `python3` (Debian 3.13)
  and run under a uv-managed CPython pinned in `ttvga/tools.toml`, which
  `tt-vga bootstrap` installs into the pipeline user's home like the other
  tools (uv is already there). The harness stays free of third-party
  packages. Locally, `requires-python` becomes `>=3.14`; uv provides it.
  PyPI's `zstandard` works too (also checked) and is the fallback if 3.14
  causes trouble. PNG is written and read with `zlib`.

## Tools (`tt-vga frames ...`)

Each takes frames from a store (`STORE:N`, distinct frame N, or `STORE@F`,
captured frame F via `frames.txt`) or from a PNG.

- `to-png SRC... -o DIR`, `from-png PNG... -o STORE` -- convert either way; a
  round trip is byte-identical (tested).
- `hash --method ID SRC` -- compute any registered method, to add a method's
  file or check one.
- `diff A B [-o DIR]` -- prints the number of differing pixels, their
  bounding box, for each channel how many pixels differ, and the ten most
  common (A value -> B value) pairs; writes A, B and a difference mask as
  PNGs. This is the tool for "the hashes don't match, why?".
- `compare RUN_A RUN_B` -- each RUN is a `frames.txt` or a hash file of the
  same method. Reports the first frame at which the two disagree. It then
  looks for a constant frame offset k (|k| <= 120 frames) under which the
  rest of the two sequences agree; finding one means the same frames arrived
  at a different time (a different reset or start), not different content.
  With two `frames.txt` it also reports start-clock differences, and with the
  stores present it runs `diff` on the first mismatching pair.

## Decision needed: the sampling rule

Fixing the sampling for `cpp != 1` (sample at `floor((p + 1/2) * cpp)`,
the true middle of pixel p) changes the frames of those 47 projects, so their
published hashes would no longer match. Options:

1. Keep tb-v1 for this run, verify the store against every published hash
   (rollout step 4), then fix the sampling as a separate change and re-run
   only the 47, published as `sampling: tb-v2` with new hash files. With the
   raw frames kept, the difference between v1 and v2 can be shown exactly.
   (Recommended.)
2. Fix it first. One fewer re-run, but the 47 projects' new frames cannot be
   checked against anything already published.
3. Leave tb-v1 as the definition.

## Rollout

1. Implement on a branch with tests: rgb6 packing, PNG round trip, every hash
   method against the committed vectors, native against reference, store
   offsets, the sequence runs, `compare` on constructed shifted and differing
   runs, the stale-file cases.
2. Run 5 projects of different kinds (nyancat, metaballs at 800x600, a static
   one, a QSPI one, the 640x504 tennis game). Measure the store size and
   packing time for: one stream at zstd levels 3, 9 and 19 with `--long`,
   and one zstd frame per image; and the PNGs' total size and writing time.
   Check the `fnv1a64-tb2026-rgb888` values are identical to the published
   ones, and compare SHA-256 and FNV distinct counts.
3. Report the measured sizes and times projected to all 408 projects, the
   chosen store layout, and the upload's file-listing time with the PNGs
   (measured with a dry run over a tree of that many files), before the full
   run.
4. Re-run all projects (several hours, progress reported on the usual
   cadence). Check the regenerated FNV hashes equal all 408 committed files
   (any project that differs is investigated, not accepted). Publish. Tell the
   two harness sessions about `frames.txt`, the stores and the renamed hash
   files.

## Not in scope

- Keeping blanking intervals or per-pixel timing. The start clock of each
  frame covers time shifts; finer timing can come later if a mismatch needs
  it.
- Changing what the videos are made from, or the two copies of the clips.
