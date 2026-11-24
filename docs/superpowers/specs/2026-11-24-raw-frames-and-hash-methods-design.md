# Raw signal traces, pluggable samplers and pluggable frame hashes

Status: design, fifth revision (after four independent reviews, the owner's
answers and the vgacap session's answers), awaiting the owner's review
(2026-11-24).

## Why

The pipeline keeps one 64-bit hash per captured frame
(`data/results/<shuttle>/<macro>/frame_hashes.txt`), and other
implementations of the same designs (the iCE40 VGA Playground harness, the
handheld harness) compare against those hashes. A hash only says *whether*
two frames differ. Finding out *why* needs the data, and the pipeline has
never kept it: `tb.cpp` decodes the pins into frames as it simulates and
pipes them to ffmpeg as lossy MJPEG (`tb.cpp:464`), which is deleted after
the clips are encoded (`job.py:383`). Worse, how the pins become pixels is
baked into the testbench, and that decoding is wrong for some designs (see
Layer 2): fixing it today means simulating again.

The owner's decisions (2026-11-24):

- Keep the raw signals, clocks and data, as the record. Frames and
  everything else are derived from that record later.
- How pixels are sampled is independent of how frames are processed:
  samplers and hash methods are separate, pluggable, named stages.
- Hashes are only an optimisation for deciding quickly whether frames match.
- Everything is published on data.wafer.space, including a PNG of every
  frame for viewing in a browser. The large final outputs live on the
  host's bulk data volume; temporary files may use the faster root NVMe
  volume while a job runs.
- Traces open in GTKWave and Surfer.
- Recording and deriving must cost little next to the simulation itself.
- Python on the host may be upgraded and may use packages from PyPI.
- The trace format, decoders and tools come from vgacap, extended there with
  the session that maintains it, not copied here.

## Three layers

    simulation --> TRACE --(sampler S)--> FRAMES(S) --(hash method H)--> HASHES(S, H)
                   record                 derived                       derived

Each arrow is a named, versioned, pluggable step. Anything derived can be
recomputed from the trace without simulating again, and every derived file
names what made it (sampler id, and hash method id for hashes).

## Layer 1: the trace

### What is recorded

Every pin of the Tiny Tapeout user module, at both halves of every clock,
from the first reset clock to the end of the run (reset, calibration and
capture alike):

| signal | bits |
| --- | --- |
| clk | 1 |
| rst_n | 1 |
| ena | 1 |
| ui_in | 8 |
| uio_in | 8 |
| uo_out | 8 |
| uio_out | 8 |
| uio_oe | 8 |

43 bits per sample, two samples per clock, taken where `tick()` settles
each half (`tb.cpp:344-351`): sample `2c` after the clk-low `eval()` of
clock `c`, sample `2c + 1` after the clk-high `eval()` and, when the QSPI
model is in use, after its response has been applied and re-evaluated
(`tb.cpp:349-350`). That second sample is exactly the state `tb.cpp` reads
`uo_out` from today (`tb.cpp:516`). Inputs are recorded as well as outputs,
so the trace shows exactly what stimulus the design saw (reset, `.inputs`
events, the gamepad shifting, the QSPI model).

Bit layout of a sample (bit 0 least significant): `uo_out` in bits 0-7,
`uio_out` 8-15, `uio_oe` 16-23, `ui_in` 24-31, `uio_in` 32-39, `rst_n` 40,
`ena` 41, `clk` 42. `uo_out` is the low byte so a sampler can take it, with
hsync and vsync, by masking.

Clock numbering, used everywhere in this design (trace, `frames.txt`, hash
files, tools): clocks are numbered by tick from 0, clock 0 being the first
reset clock, as the published hash files already say. Clock `c` is samples
`2c` (clk low) and `2c + 1` (clk high). `tb.cpp`'s `clock` variable is
incremented at the end of each tick (`tb.cpp:352`), so an event it observes
when `clock == C` happened in clock `C - 1`. `capture_after_clock` keeps its
published meaning: the value of `tb.cpp`'s `clock` when calibration ended,
which is the number of clocks before capture, so capture's first clock is
clock `capture_after_clock`. A frame's start clock is the clock in whose
clk-high sample the sampler sees the frame begin. `--from/--to` take clock
numbers, from inclusive, to exclusive.

Time: the header records `clock_hz`; sample `n` is at
`round(n * 10^12 / (2 * clock_hz))` picoseconds, computed in exact integer
arithmetic from `n` (not by accumulating a rounded step), so no sample is
more than half a picosecond from its true time and there is no drift. At
25.175 MHz a half clock is 19,860.97 ps.

### The clock in a run-encoded trace

The trace is stored as runs (a value and how many samples it lasts). `clk`
changes every sample, so if it were compared like the other bits no two
samples would ever be equal and there would be no runs. The format therefore
marks one bit as the sample clock: its value in sample `n` is
`clk0 XOR (n & 1)`, where `clk0` is stored once. Runs compare the other 42
bits; the reader regenerates `clk` exactly for every sample. The encoder
checks the rule on every sample (in simulation the testbench drives `clk`,
so it always holds) and fails loudly if it ever does not. Nothing is lost:
the clock is recorded, just not repeated.

### Size and format

Raw, the 408 current runs simulated 7.07e11 clocks in total (clock rates
from 23 to 100 MHz; the longest run 6.0e9 clocks), so at 6 bytes per sample
and two samples per clock the raw trace would be 8.5 TB. Runs cut that by
orders of magnitude, since most pins rarely change and `uo_out` repeats
every frame, but by how much is unmeasured. The bulk volume has tens of TB
free. A run (all 42 non-clock bits unchanged) can in principle last longer
than 2^32 samples, as the longest simulation is 1.2e10 samples, so run
lengths are unbounded in the format (see Shared code).

The stored trace is a sequence of independently compressed blocks (each a
separate zstd frame holding whole VGCH chunks for a stretch of samples, at
most 16 MiB of chunks per block, within VGCH's `VGACAP_MAX_CHUNK_LEN`),
followed by an index of `(first sample, byte offset)` per block, in a chunk
type a plain VGCH reader skips, so a reader without seeking can still stream
the decompressed blocks. A block always begins at a chunk boundary and a run
never spans two blocks, so seeking never splits a run. Reading a
clock range (`--from/--to`, `frames compare`) seeks to the right block
instead of decompressing from the start. Within a block, a stretch where runs
do not pay (busy content such as noise, which run encoding makes larger) is
written as a RAW chunk instead, the per-buffer fallback vgacap's RLE research
already recommends.

Rollout step 2 measures three candidate stored formats and the owner picks
one:

1. **sigrok session (`.sr`)**: the logic-analyser format, viewable in
   PulseView. Real hardware captured with a logic analyser produces the same
   format. Compression is zip (deflate), likely the largest of the three.
2. **FST**: change-based and compressed, read by GTKWave and Surfer
   directly. Written with fstapi from the run encoding (not by Verilator's
   tracer, which records through its generic tracing machinery and is
   expected to cost far more than the budget allows).
3. **VGCH with runs, zstd-compressed**: vgacap's own stream format. Probably
   the smallest and fastest to read; viewed by exporting to FST or VCD.

Whatever is chosen, the format, the sample-to-time rule and the bit layout
are documented precisely enough to read without our code. VGCH with runs
is the internal form between the encoder and the samplers in every case;
the stored file is either it or an export of it.

### How it is written

Inside `tb.cpp`, in C, through vgacap's C99 stream writer (extended as
agreed, see Shared code): each half clock the 42 non-clock bits are packed
into one 64-bit word and compared with the previous one; only a change ends
a run. That is a compare and a branch per sample, a few nanoseconds against
the hundreds of nanoseconds a simulated clock takes. Finished blocks are
handed to a second thread (double-buffered) that compresses them with
vendored zstd and writes them with buffered I/O into the job's scratch
directory on the fast root volume, so compression does not run on the
simulation's thread. Busy designs produce up to about one run per clock,
some 35 MB/s of encoded data at the fastest simulation, which that thread
compresses at a low zstd level.
No per-sample pipe, no Python in the hot path, and raw samples never reach
any disk. The existing in-testbench decoding (mode detection, frames for
the clips, statistics in timing.json) stays as it is for now: the clips are
out of scope.

### Viewing in GTKWave and Surfer

Both viewers read VCD and FST: GTKWave natively, Surfer through the `wellen`
library, whose README says it "provides a common interface to read both FST
and VCD waveform files" (github.com/ekiwi/wellen). Surfer's own pages did
not render when checked, so opening the files in Surfer is an explicit
rollout check, not an assumption.

- `vgacap-export --format fst|vcd [--from CLOCK --to CLOCK]` (wrapped as
  `tt-vga trace export`) writes a trace, or a clock range of it, as FST (the
  default: compressed, fast to load) or VCD (plain text). FST is written with
  GTKWave's `fstapi` C library (MIT licence), vendored in vgacap. The export
  is driven by the reader's run callbacks, so one run is one value change and
  idle pins cost nothing.
- Timescale 1 ps, times as defined above.
- Signals: the module's ports under one scope named after the project
  (`clk`, `rst_n`, `ena`, `ui_in[7:0]`, `uio_in[7:0]`, `uo_out[7:0]`,
  `uio_out[7:0]`, `uio_oe[7:0]`). A second scope adds decoded signals:
  `hsync`, `vsync`, `r[1:0]`, `g[1:0]`, `b[1:0]` and `rgb6`, from the same
  signal map libvgaframe uses, and `frame` (frame number) from a sampler's
  frame boundaries, so waveform and frames cannot disagree.
- A GTKWave save file (`.gtkw`) is written as text beside the export with
  those signals grouped and radixes set; if Surfer has a documented
  equivalent (a state or command file), one is written for it too.
- A whole run is up to 6e9 clocks with `uo_out` changing up to once a clock
  in the active area, which is large in any viewer, so `--from/--to` (one
  frame, or the first second after reset) is the normal way in, using the
  block index to start near the range; `frames compare` prints the clock
  range of a mismatching frame ready to pass to it.
- The same tool exports vgacap's hardware captures, which are VGCH too.

The pinned oss-cad-suite already has `gtkwave`, `surfer`, `fst2vcd` and
`vcd2fst`. Its `surfer` binary needs glibc 2.43 and does not run on the
simulation host (Debian 13, glibc 2.41), which does not matter: the viewers
run on a desktop, and the tests check files with `fst2vcd`.

## Performance budget

The baseline, from the 408 current runs: the simulation runs at a median of
2.56 million clocks per wall second (0.25 slowest, 4.61 fastest), a median
of 603 s per project, 104 CPU hours in total. At the fastest that is about
220 ns per simulated clock.

Targets, each measured in rollout step 2 against the same project simulated
without a trace:

- Recording the trace: at most 5% added to simulation wall time, about
  10 ns per clock at the fastest project. That allows a compare, a branch and
  an occasional block hand-off per sample on the simulation thread; it rules
  out Python, a pipe write per sample, and any per-sample allocation or
  system call. Compression runs on the second thread; its CPU counts in the
  next target.
- Everything after the simulation, plus the compressor thread (samplers,
  hash methods, PNGs, pages, copying to the bulk volume): at most 5% of the
  simulation's CPU time for the same project. The hardest case is a short
  simulation with almost every frame distinct: tt07's `dvd_screensaver`,
  379 s of simulation and 3,568 distinct frames of 3,600, so a budget of
  about 19 s. Estimates for it, per sampler: the sampler itself, about 1.1e9
  pixel picks, around a second in C; SHA-256 of every captured frame (1.1 GB;
  this host's CPUs have no SHA extensions, so a portable implementation at
  roughly 200-400 MB/s), 3-6 s; the legacy FNV, for `tb-v1` only and once per
  distinct frame, about 4 s; PNGs at zlib level 1, once per distinct frame
  and shared between samplers where frames are identical, a few seconds.
  With two samplers that is close to the budget, so `dvd_screensaver` is in
  the step 2 pilot. If it is over, the fixes in order are: hashing on a
  thread overlapped with sampling (wall time, not CPU, but it keeps the job
  short); a faster SHA-256 (multi-buffer AVX2, hashing several frames at
  once); and, for projects at `cpp = 1` where step 2 shows the two samplers
  give identical frames, running the second sampler only on request. A
  typical project (603 s median, far fewer
  distinct frames) is well inside.
- Memory: fixed per job (the encoder's block, one clock-resolution frame and
  one rgb6 frame per sampler), independent of run length.

If a target is missed, the step 3 report gives the profile and the fix, not
just the number.

## Layer 2: samplers, trace to frames

A sampler turns a trace into frames. It owns everything between the pins
and the pixels: finding sync, the mode, which clock each pixel is read at,
the active window, and where each frame starts. Every sampler reads
`uo_out` from the clk-high sample of each clock (sample `2c + 1`), the state
`tb.cpp` reads today. A sampler needs the run's parameters (`clock_hz`,
`calib_seconds`, `seconds`), so the trace header records them, together with
the project id and the override used (`calib_seconds` comes from the
project's override or the job default, `job.py:195`). Samplers live in vgacap (C, working on the runs, so a
long stretch with no change costs one step), each with an id, a definition
precise enough to reimplement, and a Python reference implementation used
only by the tests.

The output pixel format is the same for every sampler, **rgb6**: one byte
per pixel, `R << 4 | G << 2 | B`, each channel the two bits the design
drives (R = uo[0], uo[4]; G = uo[1], uo[5]; B = uo[2], uo[6]; first bit most
significant, `tb.cpp:550-552`; vgacap's TinyVGA signal map
`{7,3,0,4,1,5,2,6}` gives the same bits), 0..63. Display colour is
channel * 85.

The two initial samplers differ in how they find lines and frames as well
as in which clock they read a pixel at:

- **`tb-v1`**: a faithful port of `tb.cpp`'s own decoding into vgacap, so its
  frames reproduce every published hash. It is separate code from
  libvgaframe's timing, because `tb.cpp` works differently:
  - calibration: from the end of reset, sync levels are fed to a phase
    tracker (`SyncTracker` and `analyse`, `tb.cpp:191-230`), checked whenever
    `tb.cpp`'s `clock` is a multiple of 65,536, until both sync periods are
    stable (at most `calib_seconds`), which also fixes the polarities
    (`tb.cpp:361-378`);
  - mode: from `tb.cpp`'s own 11-mode table (`tb.cpp:39-51`), the mode with
    the smallest summed error (line-count error plus hsync-share error, below
    0.03) among those with `cpp` = clocks per line / mode line pixels between
    0.9 and 4.5, with a fallback for non-standard line counts
    (`tb.cpp:400-446`);
  - capture starts at the next end of a vsync pulse; a line starts at the
    *end* of its hsync pulse (`tb.cpp:520-540`);
  - pixel index `p = floor((t + cpp/2) / cpp)`, with `t` the clocks since the
    line started, is read at the first clock at which `p` takes a new value
    and stored at column `p - hback`, row `y - vback` (`tb.cpp:541-553`).

  The port covers `tb.cpp:191-230` and `361-557`, and is tested against
  `tb.cpp` itself: the same synthetic designs run through both must give the
  same frames.

  This is right only for `cpp = 1`. For `cpp > 1` (44 projects: 27 at 2.0,
  9 at 1.9062, 5 at 4.2667, 3 at 1.04) pixel `p` is read at
  `t = (p - 1/2) * cpp`, half a pixel before its period starts; at `cpp = 2`
  that is during pixel `p - 1`. For `cpp < 1` (3 projects at 0.9524,
  `tt_um_MichaelBell_rle_vga` on three shuttles) `p` advances by more than one
  on some clocks, so about 5% of pixels are never read and stay 0.
- **`centre-v1`**: libvgaframe's timing learner (VESA-correct, glitch
  pulses rejected, locked once two consecutive frames agree, the first frame
  claimed retroactively; `frame.h:33-112`) supplies the lines and frames, at
  clock resolution; the sampler picks the pixels itself, from the raw
  clock-resolution frame, so libvgaframe's own crop (and its fallback of
  cropping to the bounding box of non-black pixels, wrong for designs with
  black borders) is never used.
  - Mode and `cpp`: the measured clocks per line and lines per frame are
    matched, with `tb-v1`'s rule (smallest summed error), against one shared
    pixel-mode table: `tb.cpp`'s 11 modes plus vgacap's 720x400@70, 12 in
    all, kept in vgacap as the single table both samplers use. `cpp` = clocks
    per line / the mode's line pixels, a real number. Non-standard line
    counts use `tb-v1`'s fallback (the mode's horizontal timing, every line
    after the vsync pulse).
  - Coordinates: libvgaframe's column 0 is the hsync *leading* edge (the
    learner reports a line at the trailing edge but rebases x to the leading
    edge, `report_x`), and row 0 is the first line of the vsync pulse
    (vsync is sampled once per line, at the hsync leading edge; confirmed by
    the vgacap session from `src/frame/timing.c`). Many designs, including
    tt-vga-testpatterns' `hvsync_generator`, change vsync on the very clock
    hsync starts, so whether that line counts as in-pulse depends on the
    order of sample and run handling; a test with that generator's exact
    timing asserts row 0, and if it is off by one the fix goes into
    libvgaframe's learner, not into the sampler.
  - The raw frame is only valid inside libvgaframe's frame callback (it is
    cleared after the frame is emitted), so the sampler picks its pixels
    inside the callback.
  - Only clocks the frame actually received carry libvgaframe's written bit
    (0x80). A pixel read from an unwritten clock is *missing*, not black: it
    is stored as 0, and the frame's number of missing pixels is recorded (a
    `missing` column in the `frames.txt` runs, 0 for complete frames).
  - Pixel `(p, y)` of the active area is read from frame line
    `vsync + vback + y` at clock
    `x = floor((hsync + hback + p + 1/2) * cpp)` from the line start, where
    `hsync`, `hback`, `vsync` and `vback` are the mode's values in pixels and
    lines. Nothing is rounded before the final `floor`, so fractional `cpp`
    (1.90625, 4.2667, 0.9524) needs no clock-domain mode. At `cpp = 1` this
    is clock `hsync + hback + p`; at `cpp > 1` it is mid-pixel; at `cpp < 1`
    neighbouring pixels can share a clock, so none is left unread.

Because their line timing differs, the two can differ even at `cpp = 1`.
Rollout step 2 shows where and why. Which sampler is the reference for
comparisons is a decision (below).

## Layer 3: frames, and hash methods over them

A sampler emits every captured frame. Each frame's SHA-256 is computed
(that is the frame's identity) and frames are deduplicated by it; storing,
the legacy FNV, PNG encoding and the page all work once per distinct frame.
For each sampler, per project, under `<project>/<sampler>/`:

- `<shuttle>_<macro>_<sampler>_frames.rgb6.zst`: the distinct frames in
  order of first appearance, one zstd stream with long-distance matching;
  distinct frame `n` is at uncompressed offset `n * width * height`. Reading
  one frame means decompressing from the start (at most about 2.1 GB for the
  largest project), a second or two; step 2 also measures one zstd frame per
  image instead.
- `frames.txt`: header (`id`, `status`, `sampler`, `pixel_format: rgb6`,
  `width`, `height`, `mode`, `clock_hz`, `clocks_per_pixel`,
  `capture_after_clock`, `frame_clocks`, `frames`, `distinct_frames`, and the
  store's file name, compressed size, and the SHA-256 of its uncompressed
  contents, which does not depend on the zstd version); one SHA-256 per distinct frame, in
  store order; then the sequence as runs, `<first frame> <count> <distinct
  number> <start clock> <missing>` (`missing`, the frame's missing pixels,
  is 0 except for `centre-v1` frames that were not fully received). A frame's start clock is the clock at which the
  sampler began it (for `tb-v1` the end of a vsync pulse, for `centre-v1`
  libvgaframe's frame start). `frame_clocks` is the median measured distance
  between consecutive frame starts, in whole clocks; a run ends when the
  content changes or a frame starts other than `frame_clocks` after the
  previous one.
- `frame_hashes.<method>.txt`, one per hash method.
- `png/<n>.png` (n zero-padded to 6 digits): every distinct frame, 8-bit
  indexed with a 64-entry palette (index i is rgb6 value i), native
  resolution, written with zlib (the Python standard library's, which is C)
  by the job's glue. A PNG converts back to the identical rgb6 bytes. Where a
  second sampler's distinct frame has the same SHA-256 as one already written
  for the project, its page links to that PNG instead of writing another, so
  identical frames are stored once.
- `index.html`: every captured frame (number, start clock, distinct number)
  linking to its PNG; the distinct frames as a grid of the PNGs scaled down
  by CSS with `loading="lazy"`, so a browser fetches only what is on screen;
  and 1x/2x/4x views switched by links to `#1x`/`#2x`/`#4x` with CSS
  `:target` and `image-rendering: pixelated`. No scripts.

Hash methods each have an id, a definition, a C implementation in the same
native tool as the samplers, a Python reference for the tests, and committed
test vectors. Initial methods:

| id | algorithm | input |
| --- | --- | --- |
| `sha256-rgb6` | SHA-256 | the rgb6 bytes |
| `fnv1a64-tb2026-rgb888` | FNV-1a 64 loop, prime 0x100000001b3, offset basis 0x14650fb0739d0383 (the standard one with a digit lost) | RGB888, each channel = value * 85 |

Every hash file starts with `hash_method: <id>` and the method's definition
as comments, then its parameters as keys (for the FNV method,
`hash_offset_basis: 0x14650fb0739d0383`, the key consumers are told to read
today, README.md:91), then `id`, `status`, `sampler`, `mode`, `width`,
`height`, `clock_hz`, `clocks_per_pixel`, `capture_after_clock`, `frames`,
then one hash per frame, frame 0 first.

## Shared code: vgacap

The trace format, the encoder, the samplers and the export tool live in
vgacap (github.com/mithro/vgacap: the VGCH capture stream format,
`libvgaframe`, its Python mirror and tools), which already decodes VGA
captured from real boards. Where it lacks something, the feature is added
to vgacap with the session that maintains it and through its review, not
copied here (owner's decision 2026-11-24). A hardware capture and a
simulation trace are then read by the same code.

State checked against vgacap's `rtl` branch at e1bb8c1 (stacked on its open
PRs #1-#4, none merged). *Here* means this project's session writing it on a
branch in vgacap; that session reviews before anything merges.

| need | in vgacap today | work | by |
| --- | --- | --- | --- |
| a sample of every pin (43 bits), two per clock, with the clock bit not breaking runs | VGCH stream, `sample_bits` 8/12/16/32 (`stream.h:58`); `RLE ` chunk (32-bit value + 32-bit run); `EVNT` (64-bit clock + value); C99 callback writer and reader, no allocation | format v2: samples up to 64 bits; one new run-length chunk whose value width follows `sample_bits` (1 to 8 bytes) with a LEB128 run length, so runs are unbounded; a header field naming the sample-clock bit (see The clock in a run-encoded trace). In the C writer and reader and the Python mirror, with round-trip tests. A design note in tt-vga-capture/docs/design/ first, for the owner's decision. The same chunk answers vgacap's pending compact-RLE decision (tt-vga-capture `docs/research/2026-11-24-board-rle-throughput.md`: on the RP2350, raw 700 k samples/s, today's 8-byte pairs 784 k, a u8 value + LEB128 run 1.46 M) | here |
| 64-bit values and long runs through the API | reader run events and `vgaframe_push` take a 32-bit value and 32-bit run (`stream.h:122`, `frame.h:180`) | the new chunk and the reader's run event carry a 64-bit value and a 64-bit run. libvgaframe keeps its 32-bit sample: the sampler extracts `uo_out` (which carries hsync and vsync) from the 64-bit sample, so the board path is unchanged. Runs over 2^32 - 1 are split into several `vgaframe_push` and `vgaframe_timing_push` calls, with a test that a split run gives the same result as an unsplit one (the learner counts clocks inside runs). Agreed with vgacap | here |
| decoding runs, not clocks | `vgaframe_push(f, sample, run)`, `vgaframe_timing_push(l, hs, vs, run)`: an unchanged run is one call | a benchmark first (a synthetic 1.5e9-clock run stream, against the budget), then the C entry point the native sampler tool links. No CPython binding | here |
| `tb-v1` | none (it is `tb.cpp`'s logic) | a port of `tb.cpp:191-230` and `361-557` as its own sampler, tested against `tb.cpp` itself | here |
| `centre-v1` | libvgaframe timing at clock resolution (one byte per clock: 6-bit colour + a written bit, in the `raw` buffer); no pixel rule; the frame callback gives only the cropped rgb24 | the raw clock-resolution frame (pointer, clocks per line, lines) added to `vgaframe_output_t` and emitted whether or not a mode matched; valid only inside the frame callback, as `frame.h` will say. The shared 12-mode table: vgacap's 7 plus tb.cpp's other 5 (800x600@72 and @75, 1024x768@70, 1280x720@60, 1280x1024@60), keeping the existing clock-domain fields with a pixel-domain view beside them (the struct's meaning is unchanged), mirrored in the Python `vgacap.modes` with the existing C/Python agreement test, and a test that the 12 are pairwise distinct in clocks per line and lines per frame at one clock per pixel, so the board path never mis-names a mode. Then the centre pick; tests for row 0 with `hvsync_generator` timing and for missing pixels | here |
| modes outside the table | 7 modes (640x480 at 60/72/75, 720x400@70, 800x600 at 56/60, 1024x768@60) matched by clocks and lines; a timing learner (`frame.h:18-83`); buffers sized by the caller (`max_clocks_per_line`, `max_lines`) | nothing in the learner: clocks per pixel is not a libvgaframe concept, and its acceptance rules are relative (within 25% of the learned hsync width, at least half a line apart), so they scale. The sampler sizes the buffers (3,584 x 525 bytes for the longest lines, 640x480@75 at 4.2667 clk/px) and picks pixels itself (as under `centre-v1`). Tests: the learner at 762- and 3,584-clock lines. Agreed with vgacap | here |
| rgb6 output | the raw buffer holds the 6 bits; rgb24 is derived on emit | an rgb6 pointer beside rgb24 in `vgaframe_output_t`, checked against `R<<4 \| G<<2 \| B` with test vectors | here |
| compression, SHA-256, FST | none | vendored zstd (BSD), SHA-256 (public domain) and fstapi (MIT) under `third_party/` with licence files, as an optional CMake target so the board and RP1 builds stay dependency-free. vgacap compiles with `-Werror -Wconversion` (`CMakeLists.txt:8`); the vendored sources get their own, relaxed flags in that target and are not edited | here |
| FST/VCD export | none (`vgacap-dump` prints chunks as text) | `vgacap-export`, as described under Viewing; tested against a committed expected VCD from a synthetic stream, and `fst2vcd` of the FST output equal to the VCD output | here |

PNG output is not in vgacap (`vgacap-frames` writes PPM only,
`src/tools/vgacap_frames.c:5`); PNGs are written by this project's glue with
zlib, as above.

Also reused, not rewritten: `vgacap-dump` (stream inspector), and from
tt-vga-testpatterns the calibration designs (bars, grid, modes, prbs,
counter) with exact Python references (`tools/render.py`) and frame
comparison (`tools/check.py`, `tools/compare_capture.py`). The calibration designs, simulated
through this pipeline, must come out pixel-exact under `centre-v1`: the
end-to-end test that simulation and hardware decode the same way.

Dependency: vgacap pinned to a commit, built with its own CMake (C99, no
system dependencies) by `tt-vga bootstrap`; the Verilator model build links
it (see Code that changes).

Process (vgacap's): Milestone 10, "simulation traces", in tt-vga-capture's
`TASKS.md` (on its main, c2b5efe), and a plan at tt-vga-capture
`docs/superpowers/plans/2026-11-24-m10-simulation-traces.md`, written here
and reviewed there. vgacap work branches off `main` once PRs #1-#4 are
merged (until then off `rtl`), one worktree per branch, small commits pushed
as they go, review before merge. Order: (1) the format design note, to the
owner; (2) the libvgaframe benchmark; (3) vendored zstd, SHA-256 and fstapi;
(4) the format v2 writer and reader, the samplers, rgb6 and `vgacap-export`.

## Where things live

On the host, the final outputs live on the bulk data volume inside the
published tree (so they appear on data.wafer.space), one pipeline-owned
directory per project:

    <frames root>/<shuttle>/<macro>/
        <shuttle>_<macro>_trace.<ext>
        <sampler>/{store, frames.txt, frame_hashes.*.txt, png/, index.html}

Working files are on the fast root NVMe volume; only the finished output
moves to the bulk volume (owner's decision 2026-11-24). A job:

1. writes the trace, runs the samplers and hash methods, and builds the
   project's whole output directory (PNGs, pages and all) in a scratch
   directory under its work directory on the root volume;
2. copies the finished directory to a staging directory on the bulk volume
   (outside the published tree, on the same filesystem as it);
3. moves it into place inside the published tree with renames on one
   filesystem, so the 5-minute upload never sees a half-copied project.
   `rename(2)` cannot replace a non-empty directory, so a project that
   already has output is replaced in two renames: the old directory to the
   staging area, then the new one into place, then the old one deleted. An
   upload between the two renames sees the project missing, which does
   nothing (the upload never deletes); files the new output no longer has
   stay on the server until `tt-vga verify` lists them for removal;
4. deletes its scratch copy (a failed job deletes it too).

Root-volume use is temporary but large while jobs run (a compressed trace
plus PNGs per running job, measured in rollout step 2). The queue checks
free space before starting each job and waits while the root volume is
below a threshold (`min_free_root_gb`, defaulting from the step 2
measurements). The published tree belongs to another account (`tt-vga
mirror` copies into it as that account, `remote.py:286-289`), so an
administrator creates, once, two pipeline-owned directories on the bulk
volume: the frames root inside the published tree and the staging directory
next to it; `docs/host-setup.md` gains the two `install -d` lines. The paths
are host configuration (`~/ttvga/host.toml` on the host: `frames_root`,
`staging_dir`, `min_free_root_gb`), never named in the repository.

In git, beside each `result.json`: `<sampler>/frames.txt` for each sampler
(about 35 MB per sampler across 408 projects; git compresses hex to about
half) and `tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` (the existing files,
moved and given the new header with their values unchanged, which the
conversion asserts). Other hash files are published, not committed.
Re-running a project that finished normally gives identical files, so adds
nothing to git. A run stopped by the wall-clock limit (`sim-timeout`)
depends on the host's speed and is not reproducible; none of the current
408 is one.

The clips stay where they are, in two copies; that predates this design and
is out of scope.

## Python and tools on the host

All host-side Python (runqueue, job, verify, rerender, and the glue that
runs the native tools and writes PNGs and pages) runs under a uv-managed
CPython 3.14 instead of the system `python3` (Debian 3.13): `remote.py`
starts every host script through it (`remote.py:187,228,252`;
`runqueue.py:89` passes its interpreter on to jobs). Checked on the host
2026-11-24: uv fetched CPython 3.14.7 into the pipeline user's home and the
standard library's `compression.zstd` worked; PyPI's `zstandard` on 3.13
also worked and is the fallback. Pinning:

- `ttvga/tools.toml` gains a `[uv]` entry, pinned by version and release URL
  like the other two entries (which have no checksums today; adding
  checksums to all three is a separate improvement), and a `python` version
  that bootstrap installs with `uv python install`. uv is installed on the
  host today but not pinned.
- vgacap pinned to a commit, built by bootstrap with the host's existing
  toolchain (cmake, g++, make, as Verilator models already need); its
  compression, hashing and FST code is vendored C, so no system package is
  needed.
- Locally, `requires-python` moves from `>=3.11` (`pyproject.toml:7`) to
  `>=3.14`, deliberately, so local tools and host scripts run the same
  Python.

## Runs that do not finish normally

- `sim-timeout` and `unstable-sync`: the trace up to the stop and the frames
  decoded from it are kept, with `status` saying so.
- Input-probe runs (`job.py:236-253`): no trace (no `--trace`).
- No picture (no-sync, bad-timing): the trace is kept, as the evidence for
  why there was no picture; samplers produce no frames.
- build-failed, fetch-failed, skipped: nothing.
- A project that had output and now has none: the job removes its stale
  directory from the published tree and `collect` removes the stale files
  from git. The upload never deletes on the server, so `tt-vga verify` lists
  published directories that no longer exist locally, for removal there.

## Tools (`tt-vga ...`)

- `trace info|export|slice`: header and signal statistics; FST or VCD for
  GTKWave and Surfer (with a `.gtkw` file), or another stored format; cut a
  clock range (one frame, say) into a small trace.
- `sample --sampler ID`: run a sampler over a trace, to add one or check one.
- `frames to-png|from-png`: byte-identical round trip.
- `frames hash --method ID`: compute any hash method over a sampler's frames.
- `frames diff A B`: A and B are frames from a store (`STORE:N` distinct, or
  `STORE@F` captured) or PNGs. Prints the number of differing pixels, their
  bounding box, per channel how many differ, and the ten most common
  (A value -> B value) pairs; writes A, B and a difference mask as PNGs.
- `frames compare RUN_A RUN_B`: RUN is a `frames.txt` or a hash file of one
  method. Reports the first frame at which the two disagree, then looks for a
  constant frame offset k (|k| <= 120) under which the rest agree (same
  frames at a different time); with two `frames.txt`, start-clock
  differences; with the stores present, `frames diff` on the first
  mismatching pair; with the traces present, that frame's clock range in
  both, ready for `trace export --from/--to`.

## Code that changes

- `tb.cpp`: writes the trace through the vgacap writer and its compressor
  thread; `--trace PATH` (job runs always pass it) and no trace when it is
  absent, which is what probe runs and ad hoc runs get; no longer writes the `frame_hashes` list into timing.json
  (`tb.cpp:590-608`). Its own decoding for the clips is untouched.
- `job.py`: the Verilator build (`job.py:120-125`) gains vgacap's include
  directory in `-CFLAGS` and its static library in `-LDFLAGS`; the job runs
  the native sampler tool after the simulation, writes PNGs and pages, and
  does the scratch, staging and rename steps.
- `ttvga/harness/`: the glue above; `runqueue.py` the free-space wait.
- `ttvga/remote.py`: every host script through the pinned Python; `collect`
  brings back each sampler's `frames.txt` and the committed hash file
  (replacing `remote.py:263-265`); bootstrap builds vgacap and installs uv's
  Python.
- `ttvga/tools.toml`: `[uv]` and `python`.
- `ttvga/framehashes.py` and `tests/test_framehashes.py` are removed; a
  one-off script moves and re-heads the 408 existing hash files.
- README.md (lines 82-92) and docs/host-setup.md are rewritten.
- The two harness sessions are told before the files move: the new paths,
  `frames.txt`, the traces, the samplers, and that `hash_offset_basis` is
  unchanged.

## Rollout

1. Implement, in the order under Shared code, with tests: the format v2
   round trip (including runs over 2^32 and the sample-clock bit); the
   time rule; FST and VCD export against a committed expected VCD, and
   `fst2vcd` of the FST equal to the VCD; `tb-v1` against `tb.cpp` itself on
   synthetic designs; both samplers on synthetic traces with known pixels at
   `cpp` 0.95, 1, 1.9 and 2; rgb6 and PNG round trip; hash methods against
   committed vectors; `compare` on constructed shifted and differing runs;
   the stale-file cases.
2. Run 8 projects: nyancat, metaballs (800x600), a static one, a QSPI one,
   the 640x504 tennis game, one at `cpp = 2`, one at `cpp = 0.9524`, and
   tt07's `dvd_screensaver` (the hardest case for the post-simulation
   budget).
   Simulate each without and with the trace to measure the overhead against
   the budget; measure trace size per candidate format, store and PNG sizes,
   and sampler, hashing and PNG CPU time. Check `tb-v1` reproduces the
   published FNV hashes exactly. Compare SHA-256 and FNV distinct counts
   (543,730 today is a count of distinct FNV values, `tb.cpp:477,488`). Show
   `tb-v1` against `centre-v1` frame by frame, with `frames diff` on any
   difference. Export one frame of each as FST and VCD, check with
   `fst2vcd`, and open them in GTKWave and in Surfer on a desktop, with
   screenshots. Simulate the tt-vga-testpatterns calibration designs
   (including `tt_um_vgacal_modes` in 720x400) and check `centre-v1` is
   pixel-exact against their references. For the `cpp != 1` projects, compare
   both samplers against a hardware capture of the same design (vgacap on a
   Welland board or the iCE40 harness) where one exists.
3. Report to the owner, projected to all 408: trace size per format, store
   and PNG sizes (including how many PNGs the second sampler adds after
   sharing identical frames), run time, root-volume use per job, and the
   upload's file-listing time with the extra files (today 62,641 entries take
   about 25 s each 5-minute run).
4. Re-run all projects (several hours, progress reported on the usual
   cadence). Check `tb-v1` reproduces all 408 committed FNV files; any
   project that does not is investigated, not accepted. Publish.

## Decisions for the owner

1. Now: vgacap's new run-length chunk (value width from `sample_bits`,
   LEB128 run, a sample-clock bit), presented with its design note. It is
   needed whatever the stored format.
2. After step 3: the stored trace format (sigrok, FST, or VGCH with runs).
3. Which sampler is the reference the other harnesses should match: `tb-v1`
   (matches everything published so far, wrong for 47 projects) or
   `centre-v1`. Both are computed and published either way. Recommended:
   `centre-v1`, once step 2 shows it pixel-exact on the calibration designs
   (which all run at one clock per pixel) and, for the `cpp != 1` projects,
   in agreement with hardware captures where they exist and visibly right
   (`frames diff` against `tb-v1`) where they do not, keeping `tb-v1`
   published for continuity.
4. If step 3 shows the upload's listing is too slow: a longer upload
   interval, or the upload skipping the frames tree unless the pipeline marks
   it changed.

## Not in scope

- How the clips are made (they still come from `tb.cpp`'s own decoding; a
  later change could make them from a sampler's frames), and their two
  copies.
- Audio: it is in the trace (`uio_out`, `uio_oe`), so it can later be
  derived from the trace too, but the current audio path is unchanged.
