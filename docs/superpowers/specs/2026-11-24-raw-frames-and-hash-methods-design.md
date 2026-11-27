# Raw signal traces, pluggable samplers and pluggable frame hashes

Status: approved by the owner on 2026-11-25, seventeenth revision, amended
2026-11-25 (`tb-v1` is legacy and runs only on request; see below), and amended 2026-11-27 (the frame hash is XXH3-128, method `xxh3-128-rgb6`, replacing SHA-256 on the owner's ruling that no secure hash is needed; vgacap PR 62). The
sixteenth independent review found no blocking and no medium problems.

## Why

The pipeline keeps one 64-bit hash per captured frame
(`data/results/<shuttle>/<macro>/frame_hashes.txt`), and other
implementations of the same designs (the iCE40 VGA Playground harness, the
handheld harness) compare against those hashes. A hash only says *whether*
two frames differ. Finding out *why* needs the data, and the pipeline has
never kept it: `tb.cpp` decodes the pins into frames as it simulates and
pipes them to ffmpeg as lossy MJPEG (`tb.cpp:463-465`), which is deleted after
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
clock `capture_after_clock`. A frame's start clock is defined by each sampler
(see Layer 2) and is always a clock number in this sense. `--from/--to` take clock
numbers, from inclusive, to exclusive.

Time: the header records `clock_hz` and the samples per clock `s` (2 for
these traces; 1 for vgacap's board captures, which have no clock bit; a new
format v2 header field, see Shared code);
sample `n` is at `round(n * 10^12 / (s * clock_hz))` picoseconds, computed in exact integer
arithmetic from `n` (not by accumulating a rounded step; `n * 10^12` reaches
about 1.2e22 for the longest run, beyond 64 bits, so the product is formed in
128-bit arithmetic, with a test near `n = 1.2e10`), so no sample is
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

Raw, the current runs (421, of which 408 produced a picture) simulated 7.08e11 clocks in total (clock rates
from 23 to 100 MHz; the longest run 6.0e9 clocks), so at 6 bytes per sample
and two samples per clock the raw trace would be 8.5 TB. Runs cut that by
orders of magnitude, since most pins rarely change and `uo_out` repeats
every frame, but by how much is unmeasured. The bulk volume has tens of TB
free. A run (all 42 non-clock bits unchanged) can in principle last longer
than 2^32 samples, as the longest simulation is 1.2e10 samples, so run
lengths are unbounded in the format (see Shared code).

The stored trace is a sequence of independently compressed blocks (each a
separate zstd frame holding whole VGCH chunks for a stretch of samples,
closed at 16 MiB of uncompressed chunk data (each chunk itself within
VGCH's `VGACAP_MAX_CHUNK_LEN`, `stream.h:33`) or after
2^24 clocks, whichever comes first, so even a static design's trace has a
block every 0.17-0.73 s of simulated time at the clock rates in use),
followed by an index. The file follows zstd's *seekable format* (zstd's
`contrib/seekable_format`, BSD licence, vendored with zstd): the index is a
seek table in a skippable frame with a fixed footer, found from the end of
the file, and plain `zstd -d` decompresses the whole file to the VGCH
stream, ignoring it, so a VGCH reader without seeking can still stream the
blocks. Each block starts with a small block-header chunk holding its first
sample number, so `--from/--to` maps a clock to a block through the seek
table and the block headers. A block always begins at a chunk boundary and a run
never spans two blocks (a run that would cross a boundary is split, so
every block starts fresh), so seeking never splits a run. Each block is a
complete zstd frame, so a trace cut short (the job killed after its grace
period) loses at most the last two blocks (the unfinished one and one
already handed to the compressor thread but not yet written): the reader rebuilds the missing
seek table by walking the zstd frames and decompressing only the start of
each block, to read its block header. Reading a
clock range (`--from/--to`, `frames compare`) seeks to the right block
instead of decompressing from the start. There is no RAW fallback for these
traces: VGCH's RAW chunk packs samples of at most 32 bits (`stream.h:58,62`),
and with two samples per clock a run of one sample (about 7-7.5 bytes) is only
slightly larger than a raw sample of the 42 stored bits (5.25-6 bytes),
while any longer run is smaller. Busy designs are handled by the
planar alternative under Performance budget, if step 2 shows they need it.

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
and designs with logic on both clock edges (the QSPI model's responses, for
example) up to two; at about 7-7.5 bytes a run that is 35-70 MB/s of encoded
data at the fastest simulation, compressed with zstd's fast levels. The
compressor thread lives in vgacap's host-side (optional) target, so other
host tools can use it; the board builds are unaffected.
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
  idle pins cost nothing. `clk` is the exception: it changes every sample, so
  a whole-run export is large; `--no-clk` leaves it out when only the other
  signals matter.
- Timescale 1 ps, times as defined above.
- Signals: the module's ports under one scope named after the project
  (`clk`, `rst_n`, `ena`, `ui_in[7:0]`, `uio_in[7:0]`, `uo_out[7:0]`,
  `uio_out[7:0]`, `uio_oe[7:0]`). A second scope adds decoded signals:
  `hsync`, `vsync`, `r[1:0]`, `g[1:0]`, `b[1:0]` and `rgb6`, from the same
  signal map libvgaframe uses, and, with `--sampler ID`, `frame` (frame
  number) from that sampler's frame boundaries, read from its `frames.txt`
  (whose runs give each frame's start clock), so waveform and frames cannot
  disagree and a clock range still needs no re-sampling; without
  `--sampler` there is no `frame` signal.
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
  simulation's CPU time for the same project.
  - Compression: zstd's fast levels run at roughly 0.5-1 GB/s a core on
    this host (an estimate; step 2 measures it), so the 35-70 MB/s of the
    busiest designs at the fastest simulation cost about 4-14% of a core,
    while most designs, with long blank intervals and slower simulations,
    cost far less. The busiest designs can therefore exceed the target on
    their own. If step 2 shows that, the format note's alternative applies
    to them: a planar chunk with `uo_out` alone as plain bytes per sample (two
    bytes a clock, both halves kept, no run overhead) and the other, rarely changing pins as
    change events. vgacap's EVNT chunk has a 64-bit clock but a 32-bit value,
    and those pins are 34 bits, so this alternative also needs a 64-bit
    event value in format v2; the format note covers both.
  - Reading the trace back: the trace is decompressed and walked once, and
    every sampler is fed from that one pass. For busy designs at the fastest
    simulation that is up to about two runs a clock, some 1e10 runs for the
    longest run, likely the largest post-simulation cost for busy, fast
    designs; nyancat and metaballs are in the pilot to measure it.
  - Post-simulation work per distinct frame. The hardest case is a short
  simulation with almost every frame distinct: tt07's `dvd_screensaver`,
  379 s of simulation and 3,568 distinct frames of 3,596, so a budget of
  about 19 s. Estimates for it, per sampler: the sampler itself, about 1.1e9
  pixel picks, around a second in C; SHA-256 of every captured frame (1.1 GB;
  this host's CPUs have no SHA extensions, so a portable implementation at
  roughly 200-400 MB/s), 3-6 s; the legacy FNV, for `tb-v1` only (see Layer 3) and once per
  distinct frame, about 4 s; PNGs at zlib level 1, once per distinct frame
  and shared between samplers where frames are identical, 5-10 s.
  On top of that come compressing each sampler's store (about 1.1 GB of
  distinct frames here, several seconds even at a fast zstd level), reading
  the trace back, and the compressor thread during the simulation. With two
  samplers this worst case is therefore likely *over* its 19 s, and step 2
  measures by how much (`dvd_screensaver` is in the pilot). The fixes that
  reduce CPU, in order: a faster store-compression level for stores of mostly
  distinct frames; a faster SHA-256 (multi-buffer AVX2, several frames at
  once); and, for projects at `cpp = 1` where step 2 shows the two samplers
  give identical frames, running the second sampler only on request.
  (Hashing on a thread overlapped with sampling shortens the job but saves no
  CPU, so it does not count as a fix here.) A
  typical project (603 s median, far fewer
  distinct frames) is well inside.
- Memory: fixed buffers per job (the encoder's two blocks, one
  clock-resolution frame and one rgb6 frame per sampler, `centre-v1`'s
  libvgaframe buffers of about 9.1 MB raw and 27 MB rgb24, its 1-bit
  activity map for the window diagnostics, about 1.1 MB, and each sampler's
  store compressor, which with long-distance matching and a 2^27-byte window
  needs roughly 128-300 MB; step 2 measures it and the queue's job count
  allows for it), plus two small
  tables that grow with the run: the SHA-256 of each distinct frame (32 bytes
  each, about 138 KB for the largest project, metaballs' 4,325) and the block index (the seek
  table's 8-12 bytes plus an 8-byte first sample number per block).

If a target is missed, the step 3 report gives the profile and the fix, not
just the number.

## Layer 2: samplers, trace to frames

A sampler turns a trace into frames. It owns everything between the pins
and the pixels: finding sync, the mode, which clock each pixel is read at,
the active window, and where each frame starts. Every sampler reads
`uo_out` from the clk-high sample of each clock (sample `2c + 1`), the state
`tb.cpp` reads today. A sampler needs the run's parameters (`clock_hz`,
`calib_seconds`, `seconds`), so the trace's opening metadata chunk records them, together with
the project id and the override used (`calib_seconds` comes from the
project's override or the job default, `job.py:195`). Samplers live in vgacap (C, working on the runs, so a
long stretch with no change costs one step), each with an id, a definition
precise enough to reimplement, and Python reference code used only by the
tests. The reference covers what is defined here: `tb-v1` (a direct port of
`tb.cpp`'s logic), the pixel pick and window rule of `centre-v1` applied to a
clock-resolution frame, the frame clock, and the hash methods. It does not
re-implement libvgaframe's timing learner (vgacap's Python package has no
learner, only the stream format, modes, synthetic streams and PPM output);
`centre-v1`'s timing is tested in C against vgacap's existing and new
learner tests.

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
    `tb.cpp`'s `clock` is a multiple of 65,536, until both syncs have been
    found and at least 8 vsync phases seen (`tb.cpp:373`; at most
    `calib_seconds`), which also fixes the polarities
    (`tb.cpp:361-378`);
  - mode: from `tb.cpp`'s own 11-mode table (`tb.cpp:39-51`), copied with
    the port and kept in that order, never the shared 12-mode table; the mode with
    the smallest summed error (line-count error plus hsync-share error, below
    0.03) among those with `cpp` = clocks per line / mode line pixels between
    0.9 and 4.5, with a fallback for non-standard line counts
    (`tb.cpp:400-446`);
  - capture starts at the next end of a vsync pulse; a line starts at the
    *end* of its hsync pulse (`tb.cpp:520-540`);
  - pixel index `p = floor((t + cpp/2) / cpp)`, with `t` the clocks since the
    line started, is read at the first clock at which `p` takes a new value
    and stored at column `p - hback`, row `y - vback` (`tb.cpp:541-553`).

  The port covers `tb.cpp:191-230` and `361-557` (calibration in the shared
  component, the rest in `tb-v1`), and is tested against
  `tb.cpp` itself: the same synthetic designs run through both must give the
  same frames. That test lives in this repository, which has Verilator and
  `tb.cpp` (vgacap has neither): it simulates small designs with `tb.cpp`,
  records their traces, and compares `vgacap-sample --sampler tb-v1` with
  `tb.cpp`'s own hashes. The frames it produces are also committed to vgacap
  as test vectors, so vgacap's own tests check `tb-v1` without Verilator.

  This is wrong for 47 projects, in two ways.
  - Pixel timing. For `cpp > 1` pixel `p` is read at `t = (p - 1/2) * cpp`,
    half a pixel before its period starts; at `cpp = 2` that is during pixel
    `p - 1`. This affects the 36 projects whose `cpp` is right (27 at 2.0,
    9 at 1.9062).
  - The clocks per pixel itself. `cpp` = clocks per line / the mode's line
    pixels assumes the design uses the mode's standard blanking. For 11
    projects the hsync pulse says otherwise: its width is an exact whole
    multiple of the matched mode's pulse while `cpp` is not. `nyan` (3
    shuttles): 832-clock lines, a 96-clock hsync (640x480@60's pulse at 1
    clock per pixel), `cpp` taken as 1.04. `MichaelBell_rle_vga` (3): 800-clock
    lines, a 64-clock hsync (640x480@75's at 1), taken as 0.9524.
    `MichaelBell_mandelbrot` (5): 3,584-clock lines, a 256-clock hsync
    (64 x 4), taken as 4.2667. These designs most likely run at 1, 1 and 4
    clocks per pixel with non-standard blanking, and `tb-v1` stretches or
    squeezes them horizontally (at 0.9524 it also skips about 5% of pixels).
- **`centre-v1`**: libvgaframe's timing learner (VESA-correct, glitch
  pulses rejected, locked once two consecutive frames agree, the first frame
  claimed retroactively; `frame.h:47-112`) supplies the lines and frames, at
  clock resolution; the sampler picks the pixels itself, from the raw
  clock-resolution frame, so libvgaframe's own crop (and its fallback of
  cropping to the bounding box of non-black pixels, wrong for designs with
  black borders) is never used.
  - When: the mode, `cpp` and the window below are fixed once per run, at
    `capture_after_clock`, from the shared calibration's measurements (sync
    periods, hsync width, polarities; the same moment and data `tb-v1` uses),
    and from the project's override, if it sets one (below). The run then has
    one mode, width and height per sampler, which `frames.txt`, the hash
    headers and the store layout rely on. If the timing changes later in the
    run, frames are still sampled with the fixed geometry and the run's
    status (`unstable-sync`) says so.
  - Mode and `cpp`: the measured clocks per line and lines per frame are
    matched, with `tb-v1`'s rule (smallest summed error), against vgacap's
    shared 12-mode pixel table: `tb.cpp`'s 11 modes plus vgacap's own
    720x400@70. (`tb-v1` does not use this table: it keeps `tb.cpp`'s 11
    modes in `tb.cpp`'s order, including the order its fallback searches,
    `tb.cpp:423-430`, because adding a mode could change which one it picks.)
  - Clocks per pixel, in this order:
    1. `cpp_l` = clocks per line / the mode's line pixels. If it is within
       0.01 (absolute, as `tb.cpp:439` rounds) of a whole number, `cpp` is
       that number.
    2. Otherwise, if the hsync pulse is within 2 clocks of a whole multiple
       `k >= 1` of the mode's hsync pixels, `cpp = k`: the design runs at a
       whole number of clocks per pixel with non-standard blanking.
    3. Otherwise `cpp = cpp_l`, a fraction.

    Checked against all 408 current results, this changes exactly the 11
    projects named above (to 1, 1 and 4) and no other: `tt_um_histefan_top`,
    for example, with 800-clock lines and a 97-clock hsync, stays at 1 by
    step 1, and the 1.9062 designs (183-clock hsync, 9 clocks from 2 x 96)
    stay fractional by step 3.
  - Window: the active width is the mode's width; the line's actual
    blanking, in pixels, is `B = clocks per line / cpp - hsync - width`,
    which can be more than the mode's (nyan: 832 clocks at 1 clock per
    pixel) or less (rle_vga: 800 clocks against 640x480@75's 840). The back
    porch is the mode's back porch scaled so that back and front porch share
    `B` in the mode's proportion, `hback' = round(B * hback / (hback +
    hfront))`; vertically the same with lines. For a design with the mode's own
    blanking this is exactly the mode's window, the same crop libvgaframe
    applies to a hardware capture in that mode, so simulation and hardware
    decode alike. The window is never moved automatically: many Tiny Tapeout
    designs use the VGA Playground's sync generator, which is one pixel and
    one line off VESA timing (`common/hvsync_generator.v:18-27` in
    tt-vga-testpatterns describes it), and moving the window to follow their
    content would make `centre-v1` disagree with hardware. Instead the main
    pass builds a 1-bit map of the clock positions that were ever non-black
    and records, as diagnostics, `outside` (below) and the offset in whole
    pixels and lines that would leave the fewest lit positions outside (ties
    to the smallest offset). A project's override (`overrides/<shuttle>/
    <macro>.yaml`, which already holds per-project settings) may set
    `centre_window: {dx: <pixels>, dy: <lines>}` after a person has looked at
    the frames; only then does the window move. It is a sampling setting,
    not a simulation one: `overrides.py` passes it through (it is added to
    `PLAIN_KEYS`, `overrides.py:56`, which otherwise drops unknown keys), the
    job hands it to `vgacap-sample` as an argument, and setting it later
    means re-sampling the stored trace (`tt-vga sample`, no simulation). The
    trace's opening metadata chunk records only the simulation-time settings; the window
    offset actually used is recorded in each `centre-v1` `frames.txt`. The window never extends past
    the line or the frame, and never starts inside the hsync or vsync pulse
    (libvgaframe writes the hsync pulse's clocks at the end of the previous
    row, `x >= clocks per line`, `frame.c:255-263`, never into columns 0 to
    hsync - 1 of their own row, so those columns read as missing; the vsync pulse's rows are written, except
    in the retroactive first frame, but are blanking by definition).
  - Checks recorded in `frames.txt`: the spacing of `uo_out` colour changes
    within the active area (all multiples of a whole `cpp`, or averaging
    `cpp` when it is fractional), the porches used, and `outside`, the number
    of non-black clocks outside the window over the whole run, 0 when the
    window is placed right, with the suggested offset. Step 2 checks them on
    the 11 projects whose `cpp` this changes; step 4 lists every project
    whose `outside` is not 0, with its suggested offset and frames, for a
    person to decide whether to set `centre_window`.
  - Non-standard line counts use `tb-v1`'s fallback: the height is every
    line after the vsync pulse, so the vertical blanking under Window is 0. With no mode at all, `tb-v1`'s "unknown" rule
    applies (`tb.cpp:441-444`): one clock per pixel, every clock after the
    hsync pulse and every line after the vsync pulse. None of the current 408
    projects needs it.
  - Input: libvgaframe counts clocks, so the sampler turns the trace's
    half-clock runs into runs of clk-high samples (one per clock) before
    calling `vgaframe_push` and `vgaframe_timing_push`, splitting runs longer
    than 2^32 - 1.
  - Coordinates: libvgaframe's column 0 is the hsync *leading* edge (the
    learner reports a line at the trailing edge but rebases x to the leading
    edge, `report_x`), and row 0 is the first line of the vsync pulse.
    vsync is sampled once per line, when a line is accepted, which is at the
    hsync *trailing* edge (`vsync_sample()` is called only in the
    trailing-edge branch, `timing.c:146-155`; the comment at `timing.c:13-14`
    saying "h entering its pulse" is out of date and is corrected as part of
    this work). So a line is in the vsync pulse if vsync is at its pulse
    level at the end of that line's hsync pulse, and the line is dated from
    its hsync leading edge. Designs such as tt-vga-testpatterns'
    `hvsync_generator`, which change vsync on the very clock hsync starts,
    are therefore unambiguous: by the trailing edge vsync has already
    changed. A test with that generator's exact timing asserts row 0, and any
    error found goes into libvgaframe's learner, not into the sampler.
  - Frame start clock: the clock of the hsync leading edge that begins row 0
    (the first line of the vsync pulse), computed from the runs. That is
    earlier than the moment libvgaframe reports the frame (it reports at the
    hsync trailing edge, and the first frame retroactively), and the same
    for the retroactive first frame as for every other.
  - The raw frame is only valid inside libvgaframe's frame callback (it is
    cleared after the frame is emitted), so the sampler picks its pixels
    inside the callback.
  - Only clocks the frame actually received carry libvgaframe's written bit
    (0x80). A pixel read from an unwritten clock is *missing*, not black: it
    is stored as 0, and the frame's number of missing pixels is recorded (a
    `missing` column in the `frames.txt` runs, 0 for complete frames).
  - Pixel `(p, y)` of the active area is read from frame line
    `vsync + vback' + y` at clock
    `x = floor((hsync + hback' + p + 1/2) * cpp)` from the line start, where
    `hsync` and `vsync` are the measured pulse widths in pixels and lines and
    `hback'` and `vback'` are the porches chosen under Window. Nothing is
    rounded before the final `floor`, so a fractional `cpp` (1.90625 today)
    needs no clock-domain mode. At `cpp = 1` this is clock
    `hsync + hback' + p`; at `cpp > 1` it is mid-pixel; at `cpp < 1`
    neighbouring pixels can share a clock, so none is left unread.

**`tb-v1` is legacy** (owner, 2026-11-25). It exists only to continue the
hashes published so far, which the other harnesses compare against, and to
cross-check `tb.cpp`'s own decoding; once those harnesses compare against
`centre-v1`, it goes away. So it is not run by default: `vgacap-sample` runs
`centre-v1` unless `--sampler tb-v1` is given, and the job runs `tb-v1` only
when asked (testing, and re-checking the published projects in rollout steps 2
and 4). Measured on the busiest synthetic trace (a new colour every active
clock), `centre-v1` alone costs about 16 ns a clock and both together about
25 (vgacap Milestone 10, Task 16a).

Because their line timing differs, the two can differ even at `cpp = 1`.
Rollout step 2 shows where and why. Which sampler is the reference for
comparisons is a decision (below).

## Layer 3: frames, and hash methods over them

Which frames: frame numbers come from one shared stage, the *frame clock*,
computed once per trace in vgacap and given to every sampler, so frame `k`
is the same picture in all of them and no sampler's own timing (and no
learner losing its lock) can renumber frames.
- Calibration: `tb.cpp`'s calibration (`SyncTracker`, `analyse` and the
  loop at `tb.cpp:361-378`) is ported once into vgacap as a shared component.
  It gives the sync polarities and `capture_after_clock`. `tb-v1` and the
  frame clock both use it; `centre-v1` does not need `tb-v1` to run.
- Counting: from `capture_after_clock` on, every end of a vsync pulse is
  counted per clock on the clk-high samples, exactly as `tb.cpp`'s capture
  loop counts them (`tb.cpp:520`): a pulse seen in clock `e - 1` and not in
  clock `e`, with `e - 1 >= capture_after_clock` (`tb.cpp` starts capture
  with `prev_v` false, `tb.cpp:480`, so a pulse that ends on capture's very
  first clock is not counted). The first counted end is frame 0's; the
  `k`-th after it is frame `k`'s. A sub-line glitch on vsync therefore adds a
  frame number for every sampler alike.
- Attaching: `tb-v1`'s frame `k` starts at the clock of the `k`-th end,
  exactly as in `tb.cpp`. A `centre-v1` frame is attached to the *latest*
  counted end in a closed range that depends only on libvgaframe's own
  decisions, not on the window: from the frame's start clock (the hsync
  leading edge of row 0) to the hsync *trailing* edge of row `v`, the first
  row libvgaframe judges to be outside the vsync pulse. libvgaframe judges
  vsync at each row's trailing edge (`timing.c:146-155`), so it saw vsync in
  the pulse at row `v - 1`'s trailing edge and out of it at row `v`'s, and the
  per-clock end lies between the two, inside the range. That holds whatever
  the back porch, and for designs such as `hvsync_generator`
  (`common/hvsync_generator.v:81-85`) that end vsync on the clock a line's
  hsync starts. Taking the latest end handles a glitch inside the pulse (two
  ends in range): the earlier end's number gets no frame. A frame number with
  no `centre-v1` frame attached, such as a glitch's, is a gap.
Each sampler emits every frame that ends before the trace ends, and drops a
frame cut off by the end of the trace.

`capture_after_clock` is derived from the trace, never only stored: the
shared calibration reproduces it. The trace's closing metadata chunk also records it with the run's
`status`, as a cross-check; a trace cut short has no closing chunk, so its
status is `truncated` and the derived value is used. `tb-v1`
additionally stops at `tb.cpp`'s frame target, as `tb.cpp` does, so it
reproduces the published frame counts. Frames before `capture_after_clock`
(reset and calibration) are in the trace but are not frames of the run.

A sampler emits every such frame. Each frame's XXH3-128 is computed
(that is the frame's identity) and frames are deduplicated by it; storing,
PNG encoding and the page work once per distinct frame.
For each sampler, per project, under `<project>/<sampler>/`:

- `<shuttle>_<macro>_<sampler>_frames.rgb6.zst`: the distinct frames in
  order of first appearance, one zstd stream with long-distance matching
  and a window of at most 2^27 bytes, the limit standard decoders (zstd's
  CLI and library, Python's `compression.zstd`) accept without options;
  distinct frame `n` is at uncompressed offset `n * width * height`. Reading
  one frame means decompressing from the start (at most about 2.1 GB for the
  largest project), a second or two; step 2 also measures one zstd frame per
  image instead.
- `frames.txt`: header (`id`, `status`, `sampler`, `pixel_format: rgb6`,
  `width`, `height`, `mode`, `clock_hz`, `clocks_per_pixel`,
  `capture_after_clock`, `frame_clocks`, `frames`, `distinct_frames`, and the
  store's file name, uncompressed length, and the XXH3-128 of its
  uncompressed contents; nothing in it depends on the zstd version, so
  re-running with a newer zstd changes nothing in git); one XXH3-128 per distinct frame, in
  store order; then the sequence as runs, `<first frame> <count> <distinct
  number> <start clock> <missing>` (`missing`, the frame's missing pixels,
  is 0 except for `centre-v1` frames that were not fully received). A frame's start clock is as defined for its sampler
  (for `tb-v1` the clock in whose clk-high sample the vsync pulse is seen to
  end; for `centre-v1` the hsync leading edge beginning the first line of the
  vsync pulse). `frame_clocks` is the median measured distance
  between consecutive frame starts, in whole clocks; a run ends when the
  content changes, the `missing` count changes, or a frame starts other than
  `frame_clocks` after the previous one.
- `frame_hashes.<method>.txt`, one per hash method computed for that
  sampler: `xxh3-128-rgb6` for every sampler; `fnv1a64-tb2026-rgb888` for
  `tb-v1` only, since it exists to continue the published hashes.
- `png/<n>.png` (n zero-padded to 6 digits): every distinct frame, 8-bit
  indexed with a 64-entry palette (index i is rgb6 value i), native
  resolution, written with zlib (the Python standard library's, which is C)
  by the job's glue. `vgacap-sample` writes each new distinct frame's rgb6
  bytes, with its sampler, number, width and height, to a pipe the glue
  reads as it goes, so PNG encoding never has to decompress the store again. A PNG converts back to the identical rgb6 bytes. Where a
  second sampler's distinct frame has the same width, height and XXH3-128 as
  one already written for the project (the shape is part of the key, since
  two frames of different shapes can have the same bytes, all black for
  example), its `png/<n>.png` is a hard link to that file (same
  filesystem) instead of a second encoding, so every sampler's `png/` holds
  every one of its distinct frames by number while identical frames are
  encoded and stored on the host once. (The upload copies hard links as
  separate files, so the server holds both; that only costs upload space.)
- `index.html`: every captured frame (number, start clock, distinct number)
  linking to its PNG; the distinct frames as a grid of the PNGs scaled down
  by CSS with `loading="lazy"`, so a browser fetches only what is on screen;
  and 1x/2x/4x views switched by links to `#1x`/`#2x`/`#4x` with CSS
  `:target` and `image-rendering: pixelated`. No scripts.

Hash methods each have an id, a definition, a C implementation in
`vgacap-sample` (the native tool that runs samplers and hash methods, see
Shared code), a Python reference for the tests, and committed
test vectors. Initial methods:

| id | algorithm | input |
| --- | --- | --- |
| `xxh3-128-rgb6` | XXH3-128 | the rgb6 bytes |
| `fnv1a64-tb2026-rgb888` | FNV-1a 64 loop, prime 0x100000001b3, offset basis 0x14650fb0739d0383 (the standard one with a digit lost) | RGB888, each channel = value * 85 |

Every hash file starts with `hash_method: <id>` and the method's definition
as comments, then its parameters as keys (for the FNV method,
`hash_offset_basis: 0x14650fb0739d0383`, the key consumers are told to read
today, README.md:88-90), then `id`, `status`, `sampler`, `mode`, `width`,
`height`, `clock_hz`, `clocks_per_pixel`, `capture_after_clock`, `frames`,
then one hash per frame, frame 0 first. A frame a sampler could not
produce (see Gaps) is a line holding `-` in place of a hash, so line `k` is
always frame `k`.

### Gaps

Frame `k` is defined by its vsync pulse, so a sampler that cannot produce
it (`centre-v1` before libvgaframe has measured the timing, or when its
learner throws its measurement away and starts again after a burst of
glitches) leaves a gap rather than renumbering. In `frames.txt` a gap is a
run whose distinct number is `-`; in hash files it is a `-` line; `frames
compare` treats a gap as "no data", not as a mismatch. libvgaframe today
emits a frame only once the learner is locked or has a mode, and skips an
all-black frame that has no mode (`frame.c:220`, `frame.c:117`); the raw
frame callback added for `centre-v1` (Shared code) therefore fires for every
frame boundary the learner reports, independent of lock, mode and content, so
gaps happen only where the learner itself has no frame boundary.

## Shared code: vgacap

The trace format, the encoder, the samplers and the export tool live in
vgacap (github.com/mithro/vgacap: the VGCH capture stream format,
`libvgaframe`, its Python mirror and tools), which already decodes VGA
captured from real boards. Where it lacks something, the feature is added
to vgacap with the session that maintains it and through its review, not
copied here (owner's decision 2026-11-24). A hardware capture and a
simulation trace are then read by the same code.

State checked against vgacap's `rtl` branch at e1bb8c1 (stacked on its open
PRs #1-#4, none merged). Two other vgacap branches touch the same code and
are coordinated with that session before the plan is written: `fw-picosdk`
(its writer change is commit 471e7de: `vgacap_writer_attach`, packed words
in one write, `src/stream/writer.c`; the branch itself is still moving), and
`pio-rle`, now vgacap PR #6 (stacked on #4, hardware-checked), streams
run-length data from the board's PIO in the existing `RLE ` chunk (32-bit
value and run) and does not change the stream format, so the format note
does not depend on it; if decision 1 adopts the new chunk, the board path
can emit it later. `fw-picosdk` has settled as vgacap PR #7 (stacked on #4,
hardware-checked). Its writer change is small and additive: a new
`vgacap_writer_attach(w, write, user, h)` sets up a writer for a stream
whose VGCH header was already written elsewhere (it emits nothing; `h` only
says how samples pack), and the chunk writers are refactored around it; no
chunk format or byte layout changed and nothing was removed or renamed. The
format note is written against `rtl` plus `vgacap_writer_attach`, the code
rebases onto `fw-picosdk` when it starts, and the format v2 writer
extensions (the new run-length chunk, 64-bit runs, samples per clock in the
header) work through both `vgacap_writer_init` and `vgacap_writer_attach`. *Here* means this project's session writing it on a
branch in vgacap; that session reviews before anything merges.

| need | in vgacap today | work | by |
| --- | --- | --- | --- |
| a sample of every pin (43 bits), two per clock, with the clock bit not breaking runs | VGCH stream, `sample_bits` 8/12/16/32 (`stream.h:58`); `RLE ` chunk (32-bit value + 32-bit run); `EVNT` (64-bit clock + value); C99 callback writer and reader, no allocation | format v2: samples up to 64 bits; one new run-length chunk (TASKS.md calls it RLE64; its value width follows `sample_bits`, 1 to 8 bytes) with a LEB128 run length, so runs are unbounded; header fields naming the sample-clock bit and the samples per clock `s`; the reader's run event carries the full 64-bit value of the run's first sample (so its clock bit is that sample's, and readers regenerate it for the rest of the run) (see The clock in a run-encoded trace). In the C writer and reader and the Python mirror, with round-trip tests. A design note in tt-vga-capture/docs/design/ first, for the owner's decision. The same chunk answers vgacap's pending compact-RLE decision (tt-vga-capture `docs/research/2026-11-24-board-rle-throughput.md`: on the RP2350, raw 700 k samples/s, today's 8-byte pairs 784 k, a u8 value + LEB128 run 1.46 M) | here |
| the trace container | VGCH chunks streamed into one file; the header has a `uint32` `clock_hz` and a free-text description of at most 255 bytes (`stream.h:56-66`) | independently compressed blocks in zstd's seekable format, whose seek table (a skippable frame at the end of the file) holds each block's compressed and uncompressed size, with each block's first sample number in its block-header chunk, as under Size and format; the seek table rebuilt by walking the blocks when it is missing; a metadata chunk of `key=value` lines, which a plain reader skips, written twice: an opening one with the run's parameters (project id, override, `clock_hz`, `calib_seconds`, `seconds`, simulator and harness versions) and a closing one with what is only known later (`capture_after_clock`, `status`, `frames`); the double-buffered compressor thread, in the host-side optional target | here |
| 64-bit values and long runs through the API | reader run events and `vgaframe_push` take a 32-bit value and 32-bit run (`stream.h:122`, `frame.h:180`) | the new chunk and the reader's run event carry a 64-bit value and a 64-bit run. libvgaframe keeps its 32-bit sample: the sampler extracts `uo_out` (which carries hsync and vsync) from the 64-bit sample, so the board path is unchanged. Runs over 2^32 - 1 are split into several `vgaframe_push` and `vgaframe_timing_push` calls, with a test that a split run gives the same result as an unsplit one (the learner counts clocks inside runs). Agreed with vgacap | here |
| decoding runs, not clocks | `vgaframe_push(f, sample, run)`, `vgaframe_timing_push(l, hs, vs, run)`: an unchanged run is one call | a benchmark first (a synthetic 1.5e9-clock run stream, against the budget), then the C entry point `vgacap-sample` links. No CPython binding | here |
| `tb-v1` | none (it is `tb.cpp`'s logic) | a port of `tb.cpp:379-557` (the no-sync and bad-timing decisions, mode, capture and pixel rule) as its own sampler on top of the shared calibration and frame clock, tested against `tb.cpp` itself | here |
| `centre-v1` | libvgaframe timing at clock resolution (one byte per clock: 6-bit colour + a written bit, in the `raw` buffer); no pixel rule; the frame callback gives only the cropped rgb24 | the raw clock-resolution frame (pointer, clocks per line, lines) delivered by a callback that fires for every frame boundary the learner reports, independent of lock, mode and content (unlike `emit()`, gated at `frame.c:219-220` and skipping all-black unmatched frames at `frame.c:117`). The raw and cover buffers are cleared today only inside `emit()` (`frame.c:171-176`), so on frames where `emit()` does not run they would still hold the previous frame's pixels, written bit set; the boundary handling therefore fires the raw callback first, then lets `emit()` run, then clears raw and cover on every boundary, keeping `emit()`'s own FRAM-mode clearing (`clear_lines`, `frame.c:173`). Tests: a shorter second frame has no written pixels past its own lines, and a retroactive first frame reads lines 0 to `vsync_lines - 1` as unwritten; valid only inside the frame callback, as `frame.h` will say. The shared 12-mode table: vgacap's 7 plus tb.cpp's other 5 (800x600@72 and @75, 1024x768@70, 1280x720@60, 1280x1024@60; `tb.cpp:39-51` gives their totals, sync widths, back porches and widths, from which the front porches follow, but not their sync polarities, which come from the VESA Display Monitor Timing standard (and CEA-861 for 1280x720@60), with a test that each entry's totals equal `tb.cpp`'s), keeping the existing clock-domain fields with a pixel-domain view beside them (the struct's meaning is unchanged), mirrored in the Python `vgacap.modes` with a new test that the C and Python tables agree field by field (there is none today: `tests/test_modes.c` checks only the C table's first entry and a few matches against it, never the Python table), and a test that the 12 are distinct as (clocks per line, lines per frame) pairs at one clock per pixel. Clock-per-line alone is not unique once the five are added (800x600@60 and @75 both have 1,056-clock lines), and `vgaframe_mode_match_cpl` (`frame.h:27-31`, used for FRAM windows at `frame.c:51`) relies on it being unique, so the five added modes carry a mark that `vgaframe_mode_match_cpl` skips (its comment, "unique across the built-in table" at `frame.c:46-47` and in `frame.h:27-28`, is updated to say so; the call is at `frame.c:51`), with a test that it gives the same result for every entry it gave before. The learner's own match on clocks and lines (`vgaframe_mode_match`, `timing.c:36`) does see the five, a deliberate change chosen with the vgacap session (its option (b)): a board capture in one of those modes, which today falls through to the fragile crop to the bounding box of non-black pixels, gets the correct table crop instead. Tests: a synthetic stream in each new mode gives the exact crop, and every existing entry still resolves as before. The mark is mirrored in the Python `vgacap.modes`. In streaming capture ttcap names no mode (the learner detects it from the signal), so the five are detected there with no ttcap change. ttcap's `--vga-mode` feeds only the frame and window programs (`frame_cfg()`, ttcap `capture.py:100-135`), which need clocks per line to be unique and a whole number of sample words (checked at `capture.py:131-135`), so it rejects the marked modes with an error saying why, with a test of that rejection. Then the centre pick; tests for row 0 with `hvsync_generator` timing and for missing pixels | here |
| modes outside the table | 7 modes (640x480 at 60/72/75, 720x400@70, 800x600 at 56/60, 1024x768@60) matched by clocks and lines; a timing learner (`frame.h:47-112`); buffers sized by the caller (`max_clocks_per_line`, `max_lines`) | nothing in the learner: clocks per pixel is not a libvgaframe concept, and its acceptance rules are relative (within 25% of the learned hsync width, at least half a line apart), so they scale. `centre-v1`'s libvgaframe is fed from the start of the trace, before the shared calibration in the same pass has measured anything, so it sizes the buffers for the largest timing the mode matching accepts (4.5 clocks per pixel times the widest table line, 1,688 pixels, is 7,596 clocks; and 1,200 lines, above which `centre-v1` treats a frame as bad timing, since the non-standard-line fallback has no upper bound of its own): about 9.1 MB of raw buffer and, because `vgaframe_init` requires an rgb24 buffer too (`frame.c:35`), about 27 MB of rgb24, fixed (the largest in use today, in different projects: 3,584-clock lines, 640x480@75 at 4.2667 clk/px, and 666-line frames, 800x600@72), and picks pixels itself (as under `centre-v1`). Tests: the learner at 762- and 3,584-clock lines. Agreed with vgacap | here |
| calibration and the frame clock | none (they are `tb.cpp`'s logic) | `tb.cpp`'s calibration (`tb.cpp:191-230`, `361-378`) ported once as a shared component, and the frame clock on top of it, used by `tb-v1`, `centre-v1` and any later sampler; tested against `tb.cpp` itself | here |
| the native sampler and hash tool | `vgacap-frames` decodes a stream to PPM files (`src/tools/vgacap_frames.c`) | `vgacap-sample`, a C tool beside it: reads a trace once (both samplers in one pass, sharing the decompression), runs the requested samplers and hash methods, and writes each sampler's store, `frames.txt` (with gaps) and hash files; the job and `tt-vga sample` call it | here |
| rgb6 output | the raw buffer holds the 6 bits; rgb24 is derived on emit | an rgb6 pointer beside rgb24 in `vgaframe_output_t`, checked against `R<<4 \| G<<2 \| B` with test vectors | here |
| compression, SHA-256, FST | none | vendored zstd (BSD), SHA-256 (public domain) and fstapi (MIT) under `third_party/` with licence files, as an optional CMake target so the board and RP1 builds stay dependency-free. vgacap compiles with `-Werror -Wconversion` (`CMakeLists.txt:8`); `add_compile_options` there applies to the whole directory, so the vendored sources live in their own subdirectory (`third_party/`, with its own `CMakeLists.txt`) which explicitly resets the inherited `COMPILE_OPTIONS` directory property
before setting its own relaxed flags (a subdirectory otherwise inherits the
parent's); they are not edited | here |
| FST/VCD export | none (`vgacap-dump` prints chunks as text) | `vgacap-export`, as described under Viewing; tested against a committed expected VCD from a synthetic stream, and `fst2vcd` of the FST output equal to the VCD output | here |

PNG output is not in vgacap (`vgacap-frames` writes PPM only,
`src/tools/vgacap_frames.c:5`); PNGs are written by this project's glue with
zlib, as above.

Also reused, not rewritten: `vgacap-dump` (stream inspector), and from
tt-vga-testpatterns the calibration designs (bars, grid, modes, prbs,
counter) with exact Python references (`tools/render.py`) and frame
comparison (`tools/check.py`, `tools/compare_capture.py`). The
calibration designs, simulated through this pipeline, must come out
pixel-exact under `centre-v1`: the end-to-end test that simulation and
hardware decode the same way. They reach the pipeline as extra targets:
- `tt-vga targets` (`ttvga/targets.py`) merges a committed
  `data/extra-targets.json` into `data/targets.json`, with entries under a
  pseudo-shuttle `testpatterns`: repository github.com/mithro/tt-vga-testpatterns
  at a pinned commit, each design's top module, and a new optional target
  field `src_dir` (`designs/<name>/src`), because `job.py` hard-codes the
  sources at `<repo>/src` (`job.py:92`, and the model runs from there, `job.py:225`), which becomes the default.
- `ui_in` comes from overrides (`job.py:197-200`) or the job's input probe
  (`job.py:254-258`), never from the target, so each variant has a committed
  `overrides/testpatterns/<macro>.yaml` setting it. Overrides, work
  directories and result ids are keyed by macro name, so each variant is its
  own pseudo-macro (`tt_um_vgacal_modes_m0`, `..._m1_hneg` and so on) with
  `top_module` set to the real design. For
  `tt_um_vgacal_modes` there is one variant per mode (`ui_in` 0, 1, 2) and
  the polarity cases (`ui_in` bits 2 and 3: inverted hsync, inverted vsync,
  both), which exercise the shared calibration's polarity detection.
- The designs produce one pixel per clock, so the geometry does not depend
  on the clock rate and the default 25.175 MHz serves every variant.
- They are run, but not published: `job.py` skips the clip encoding and the
  rename into the published tree for the `testpatterns` pseudo-shuttle (its
  trace and frames stay in the work directory), and `collect`, the index
  (`ttvga/index.py`) and the report (`ttvga/report.py`) leave it out of the
  Tiny Tapeout listings.

Dependency: vgacap pinned to a commit, built with its own CMake (C99, no
system dependencies) by `tt-vga bootstrap`; the Verilator model build links
it (see Code that changes).

Process (vgacap's): Milestone 10, "simulation traces", in tt-vga-capture's
`TASKS.md` (added in c2b5efe), and a plan at tt-vga-capture
`docs/superpowers/plans/2026-11-24-m10-simulation-traces.md`, written here
and reviewed there; the plan also adds to Milestone 10 in `TASKS.md` the
items it does not list yet (the block container and index, the metadata
chunks, the compressor thread, `vgacap-sample`, the 12-mode table with
ttcap's rejection of the added modes, and the raw-frame callback). vgacap
work branches off `main` once PRs #1-#4 are merged (until then off `rtl`,
rebased onto `fw-picosdk` for the writer changes if it merges first), one worktree per branch, small commits pushed
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
   (outside the published tree, on the same filesystem as it), keeping hard
   links (`rsync -aH`; Python's `shutil.copytree` would duplicate them);
3. moves it into place inside the published tree with renames on one
   filesystem, so the 5-minute upload never sees a half-copied project.
   `rename(2)` cannot replace a non-empty directory, so a project that
   already has output is swapped in with `renameat2(RENAME_EXCHANGE)` (Linux
   3.15 and later; ext4, which the bulk volume uses, supports it; called
   through `ctypes`, as Python's `os` has no wrapper), which exchanges the new
   directory and the old one in one step, then the old one, now in staging,
   is deleted. If the exchange is not available, two renames are used
   instead; an upload between them sees the project missing, which does
   nothing (the upload never deletes). Files the new output no longer has
   stay on the server until `tt-vga verify` lists them for removal (it reads
   the server's public directory listings over HTTPS, the only way to see
   it, since the upload account can only write);
4. deletes its scratch copy (a failed job deletes it too).

Root-volume use is temporary but large while jobs run (a compressed trace
plus PNGs per running job, measured in rollout step 2). The queue checks
free space before starting each job and waits while the root volume is
below a threshold (`min_free_root_gb`, defaulting from the step 2
measurements). The published tree belongs to another account (`tt-vga
mirror` copies into it as that account, `remote.py:286-289`), so an
administrator creates, once, two pipeline-owned directories on the bulk
volume: the frames root inside the published tree and the staging directory
next to it; `docs/host-setup.md` gains the two `install -d` lines (and
loses its claim that bootstrap installs uv, which `remote.py` does not do
today; after this work it does). The paths
are host configuration (`~/ttvga/host.toml` on the host: `frames_root`,
`staging_dir`, `min_free_root_gb`), never named in the repository.

In git, beside each `result.json`, under `frames/`: `frames/<sampler>/frames.txt` for each sampler
(about 60 MB per sampler across 408 projects before compression: about
35 MB of distinct-frame SHA-256 lines and about 25 MB of run lines, the
current hash files having 839,992 content changes; git compresses hex to
about half) and `frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` (the existing files,
moved and given the new header; the conversion asserts that each moved
file's hash lines are byte-identical to the `frame_hashes.txt` it came from
and that their number equals the project's `frame_hashes_count` in
`result.json`). Other hash files are published, not committed.
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

- `ttvga/tools.toml` gains a `[uv]` tarball entry (version, release URL and
  `strip = 1`, like the ffmpeg entry; none of the entries has a checksum
  today, and adding them is a separate improvement) and a `[python]` table
  with a version. Bootstrap's loop treats every entry as a tarball
  and reads its `check`, `dir` and `url` (`remote.py:130-143`), so the loop
  skips `[python]`, and a separate step after it runs `uv python install`. uv is installed on the host today but not
  pinned.
- vgacap is cloned by bootstrap at its pinned commit (the host has git) and
  built with the host's existing toolchain: g++ and make, which Verilator
  models already need, and cmake, which the host has today (3.31.6, a Debian
  package, checked 2026-11-24) and which `host-check` (`remote.py:112`) is
  extended to check for; its compression, hashing and FST code is vendored
  C, so no new system package is needed.
- The host harness stays standard-library only. If the `zstandard` fallback
  is ever needed, it comes from PyPI through a `pyproject.toml` and
  `uv.lock` for the harness that bootstrap syncs with uv.
- Locally, `requires-python` moves from `>=3.11` (`pyproject.toml:7`) to
  `>=3.14`, deliberately, so local tools and host scripts run the same
  Python.

## Runs that do not finish normally

- `sim-timeout` and `unstable-sync`: the trace up to the stop and the frames
  decoded from it are kept, with `status` saying so.
- Input-probe runs (`job.py:236-253`): no trace (no `--trace`).
- No picture (no-sync, bad-timing): the trace is kept, as the evidence for
  why there was no picture; samplers produce no frames.
- Killed outright after the grace period, with no timing.json: today the
  job returns an error at once (`job.py:227-230`); it is changed to run
  `vgacap-sample` on the trace up to its last complete block first, with
  status `truncated` (no closing metadata chunk), keeping the frames it
  holds, and then report the error.
- build-failed, fetch-failed, skipped: nothing.
- A project that had output and now has none: the job removes its stale
  directory from the published tree and `collect` removes the stale files
  from git. The upload never deletes on the server, so `tt-vga verify` lists
  published directories that no longer exist locally, for removal there.

## Re-deriving without simulating

Setting `centre_window`, adding a sampler or adding a hash method all mean
deriving again from stored traces. That is a job mode of its own:
`job.py --rederive` (started for many projects by
`tt-vga queue start --rederive [--only ...]`, like a normal run) skips fetch,
build and simulation; it reads the project's published trace, runs
`vgacap-sample` with the current samplers, hash methods and override,
writes the PNGs and pages, does the same scratch, staging and swap steps as
a normal job, refreshes `work/<shuttle>/<macro>/frames/` so `collect` brings
the new `frames.txt` back, and records `rederived_at` in `result.json`. It
costs only the post-simulation budget. `tt-vga sample` is the same step for
one project from the command line.

## Tools (`tt-vga ...`)

- `trace info|export|slice`: header and signal statistics; FST or VCD for
  GTKWave and Surfer (with a `.gtkw` file), or another stored format; cut a
  clock range (one frame, say) into a small trace. A slice is for viewing
  only: it has no calibration period, so samplers are not run on it.
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
  thread; `--trace PATH` (the job passes it to every simulation run except input
  probes) and no trace when it is absent (probe runs, ad hoc runs). When the
  default inputs give no picture and a probe finds inputs that do, the job
  simulates again with those inputs and keeps that run's trace; the first
  run's trace is deleted, since the kept run supersedes it; its own decoding for the clips is untouched, and it still hashes every
  frame it decodes, but writes the list to its own file in the run's output
  directory instead of into timing.json (`tb.cpp:590-608`). `result.json`'s
  `frame_hashes_count` goes with it (nothing but the tests reads it); the
  frame counts are in `frames.txt`. When the job is asked to run `tb-v1`
  (it is off by default; see Layer 2), it compares
  that list with `tb-v1`'s `fnv1a64-tb2026-rgb888` output on every run that
  ended with a list (status `ok`, `unstable-sync`, or `sim-timeout`, which
  stops on SIGTERM and still writes it) and fails the job if they differ; a
  run whose list is missing (the model was killed outright) records
  `tb_v1_check: not-run` in its result instead, so `tb-v1` is checked against the decoding
  that makes the clips whenever `tb-v1` is run; a run without it records
  `tb_v1_check: off`.
- `job.py`: writes everything for the published tree with umask 022 (files
  0644, directories 0755), so the upload account can read it; the Verilator
  build (`job.py:120-125`) gains vgacap's include
  directory in `-CFLAGS` and its static library and `-pthread` (for the
  compressor thread) in `-LDFLAGS`; the job runs
  `vgacap-sample` after the simulation, writes PNGs and pages, and
  does the scratch, staging and rename steps.
- `ttvga/harness/`: the glue above; `runqueue.py` the free-space wait and the
  `--rederive` mode (see Re-deriving without simulating).
- `ttvga/remote.py`: every host script through the pinned Python (the two
  one-line JSON status reads at `remote.py:116,207` may stay on the system
  Python); `collect` brings back each sampler's `frames.txt` and the
  committed hash file (replacing `remote.py:263-265`): the job also writes
  them under its work directory (`work/<shuttle>/<macro>/frames/<sampler>/`),
  and `collect`'s rsync of the work tree, whose filter today includes only
  `result.json` (`remote.py:261-262`), also includes `frames.txt` and
  `frame_hashes.fnv1a64-tb2026-rgb888.txt`, anchored to
  `<shuttle>/<macro>/frames/*/` (a running job's scratch directory under
  `work/` holds files of the same names, which must not be picked up), which
  lands them at
  `data/results/<shuttle>/<macro>/frames/<sampler>/`, so `collect` needs no
  knowledge of the frames root. That rsync never deletes, so `collect` then
  removes stale `frames/` files, but only for projects whose host work
  directory has a `frames/` directory, that is, projects already run by the
  new pipeline. It learns which those are from a listing it fetches from the
  host in the same step (one `find` over the work tree), not from the local
  copy, where every project has `frames/tb-v1/` after the conversion; a project not yet re-run keeps its converted
  `frames/tb-v1/` files however often `collect` runs (after the step 2 pilot,
  for example); bootstrap builds vgacap and installs uv's
  Python.
- `ttvga/tools.toml`: `[uv]`, `[python]`, and `[vgacap]` (its git URL and
  pinned commit, which bootstrap clones and builds; the tarball loop skips it
  like `[python]`).
- `ttvga/framehashes.py` and `tests/test_framehashes.py` are removed; a
  one-off script moves and re-heads the 408 existing hash files.
- `ttvga/targets.py`: merges `data/extra-targets.json`; `ttvga/overrides.py`:
  `centre_window` in `PLAIN_KEYS`; `ttvga/index.py` and `ttvga/report.py`:
  leave the `testpatterns` pseudo-shuttle out; `job.py` also: the optional
  `src_dir`, no encoding or publishing for `testpatterns`, and sampling a
  killed model's trace before reporting the error.
- `ttvga/cli.py`: the `trace` and `frames` subcommands and `sample` (thin
  wrappers over `vgacap-export` and `vgacap-sample`, plus the Python
  `frames diff/compare/to-png/from-png`); `ttvga/harness/verify.py`: lists
  published directories and files on the server that no longer exist
  locally, from its HTTPS directory listings.
- `tb.cpp`'s comment at `tb.cpp:236-241`, which names `framehashes.py` and
  `frame_hashes.txt`, is updated to the new files.
- README.md (lines 82-92) and docs/host-setup.md are rewritten (the latter
  also wrongly says the ffmpeg build is pinned by checksum, line 35), and
  PROGRESS.md gets a new entry saying `frame_hashes.txt` and
  `framehashes.py` (described at PROGRESS.md:13-14) are replaced; its older
  entries stay as the history they are.
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
2. Run 11 projects: nyancat, metaballs (800x600), a static one, a QSPI one,
   the 640x504 tennis game, one at `cpp = 2`, one at 1.9062, and the three
   whose clocks per pixel `centre-v1` derives differently from `tb-v1`
   (`tt_um_nyan`, `MichaelBell_rle_vga`, `MichaelBell_mandelbrot`), plus
   tt07's `dvd_screensaver` (the hardest case for the post-simulation
   budget). For the three, check the colour-change spacing and that
   `outside` is 0.
   Simulate each without and with the trace to measure the overhead against
   the budget; measure trace size per candidate format, store and PNG sizes,
   and sampler, hashing and PNG CPU time. Check `tb-v1` reproduces the
   published FNV hashes exactly. Compare XXH3-128 and FNV distinct counts
   (543,730 today is a count of distinct FNV values, `tb.cpp:477,488`). Show
   `tb-v1` against `centre-v1` frame by frame, with `frames diff` on any
   difference. Export one frame of each as FST and VCD, check with
   `fst2vcd`, and open them in GTKWave and in Surfer on a desktop, with
   screenshots. Simulate the tt-vga-testpatterns calibration designs
   through `data/extra-targets.json` (including `tt_um_vgacal_modes` in
   720x400) and check `centre-v1` is pixel-exact against their references. For the `cpp != 1` projects, compare
   both samplers against a hardware capture of the same design (vgacap on a
   Welland board or the iCE40 harness) where one exists.
3. Report to the owner, projected to all 408: trace size per format, store
   and PNG sizes (including how many PNGs the second sampler adds after
   sharing identical frames), run time, root-volume use per job, and the
   upload's file-listing time with the extra files (today 62,641 entries take
   about 25 s each 5-minute run, per the upload's own log on the host,
   `/var/lib/data-upload/rsync.log`, 2026-11-24 runs).
4. Re-run all projects (several hours, progress reported on the usual
   cadence). Check `tb-v1` reproduces all 408 committed FNV files; any
   project that does not is investigated, not accepted. Publish.

## Decisions for the owner

1. Now: vgacap's new run-length chunk (value width from `sample_bits`,
   LEB128 run, a sample-clock bit), presented with its design note. It is
   needed whatever the stored format.
2. After step 3: the stored trace format. VGCH with runs is what the
   samplers read and what the block index seeks in, so storing it keeps
   everything re-derivable directly, and FST, VCD or sigrok files are made
   from it on demand by `vgacap-export`. Storing FST or sigrok instead would
   need an importer back to runs (not in the work list), FST would hold `clk`
   as a change every half clock, and seeking would depend on those formats'
   own indexes. Recommended: VGCH with runs, unless step 3 shows another is
   much smaller.
3. Which sampler is the reference the other harnesses should match: `tb-v1`
   (matches everything published so far, wrong for 47 projects: 36 by
   pixel timing and 11 by a mis-derived clocks per pixel) or `centre-v1`. `centre-v1` is computed and published for every project; `tb-v1` only when
   it is run on request, since it is legacy (owner, 2026-11-25). Recommended:
   `centre-v1`, once step 2 shows it pixel-exact on the calibration designs
   (which all run at one clock per pixel) and, for the `cpp != 1` projects,
   in agreement with hardware captures where they exist and visibly right
   (`frames diff` against `tb-v1`) where they do not, keeping `tb-v1`
   published for continuity.
4. The upload's file listing. Projected now: about 543,730 PNGs per
   sampler, roughly 1.1 million files with two samplers, against the 62,641
   listed today in about 25 s, so roughly 7.5 minutes per listing, longer
   than the 5-minute upload interval. Step 3 measures it, but this decision
   is almost certainly needed. Options: a longer upload interval; the upload
   skipping the frames tree unless the pipeline marks it changed; or a
   separate, slower upload for the frames tree.

## Not in scope

- How the clips are made (they still come from `tb.cpp`'s own decoding; a
  later change could make them from a sampler's frames), and their two
  copies.
- Audio: it is in the trace (`uio_out`, `uio_oe`), so it can later be
  derived from the trace too, but the current audio path is unchanged.
