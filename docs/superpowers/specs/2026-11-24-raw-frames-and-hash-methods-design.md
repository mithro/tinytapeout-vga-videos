# Raw signal traces, pluggable samplers and pluggable frame hashes

Status: design, third revision (after two independent reviews and the
owner's answers), awaiting the owner's review (2026-11-24).

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
Samplers): fixing it today means simulating again.

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
- Python on the host may be upgraded and may use packages from PyPI.

## Three layers

    simulation --> TRACE --(sampler S)--> FRAMES(S) --(hash method H)--> HASHES(S, H)
                   record                 derived                       derived

Each arrow is a named, versioned, pluggable step. Anything derived can be
recomputed from the trace without simulating again, and every derived file
names what made it (sampler id, and hash method id for hashes).

## Layer 1: the trace

### What is recorded

Every pin of the Tiny Tapeout user module, at both edges of every clock,
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

43 bits per sample, two samples per clock (clk low, clk high: the values
after `eval()` in each half of `tick()`, `tb.cpp:344-351`, including the QSPI
model's response). Inputs are recorded as well as outputs, so the trace
shows exactly what stimulus the design saw (reset, `.inputs` events, the
gamepad shifting, the QSPI model). The trace header records the clock
frequency, so sample `n` is at time `n / (2 * clock_hz)`.

### Size and format

Raw, a 60 s run at 25.175 MHz is about 3.0e9 samples, 18 GB at 6 bytes a
sample, and about 7.4 TB for 408 projects. The data is extremely
repetitive (clk alternates, inputs rarely change, the picture repeats every
frame), so it should compress by one or two orders of magnitude, but that
is unmeasured. The bulk volume has tens of TB free. Rollout step 2 measures
three candidate formats and the owner picks one:

1. **sigrok session (`.sr`)**: the logic-analyser format, viewable in
   PulseView. Real hardware captured with a logic analyser produces the same
   format, so a hardware capture and a simulation can be compared with the
   same tools. Compression is zip (deflate), likely the largest of the three.
2. **FST**: Verilator writes it natively (`--trace-fst`, ports only),
   viewable in GTKWave; change-based, so idle signals cost nothing.
3. **Planar zstd**: each signal group as its own byte stream, compressed
   with zstd `--long`. Probably the smallest and fastest to read
   sequentially; needs our tool (or a documented short script) to view.

Whatever is chosen, the format, the sample-to-time rule and the bit layout
are documented precisely enough to read without our code, and
`tt-vga trace export` converts to the other two.

### Viewing in GTKWave and Surfer

Whatever the stored format, a trace must open in GTKWave and in Surfer
(owner's requirement, 2026-11-24). Both read VCD and FST: GTKWave natively,
Surfer through the `wellen` library, whose README says it "provides a common
interface to read both FST and VCD waveform files"
(github.com/ekiwi/wellen; Surfer's own pages did not render when checked, so
opening the files in Surfer is an explicit rollout check rather than an
assumption). So:

- `tt-vga trace export --format fst|vcd [--from CLOCK --to CLOCK]` writes
  the trace, or a clock range of it, as FST (the default: compressed, and
  fast to load) or VCD (plain text, read by everything). The writer is GTKWave's
  `fstapi` C library (MIT licence), vendored in vgacap, driven from the
  run-encoded trace so only changes are written.
- The signals are the module's ports under one scope named after the
  project (`clk`, `rst_n`, `ena`, `ui_in[7:0]`, `uio_in[7:0]`, `uo_out[7:0]`,
  `uio_out[7:0]`, `uio_oe[7:0]`), with the timescale set from `clock_hz` so
  times read in real nanoseconds. A second scope adds decoded convenience
  signals: `hsync`, `vsync`, `r[1:0]`, `g[1:0]`, `b[1:0]` and the 6-bit
  `rgb6`, plus `frame` (the frame number) once a sampler has run.
- A GTKWave save file (`.gtkw`) is written beside the export with those
  signals grouped and the radixes set; if Surfer has a documented equivalent
  (a state or command file), one is written for it too.
- A whole 60 s run is about 1.5e9 clocks with `uo_out` changing up to once a
  clock in the active area, which is large in any viewer, so `trace slice`
  and `--from/--to` (for example one frame, or the first second after reset)
  are the normal way to look at a trace; `frames compare` prints the clock
  range of a mismatching frame ready to pass to them.

The tools are already in the pinned oss-cad-suite (`gtkwave`, `surfer`,
`fst2vcd`, `vcd2fst`). Its `surfer` binary needs glibc 2.43 and does not run
on the simulation host (Debian 13, glibc 2.41), which does not matter: the
viewers run on a desktop, and the tests check files with `fst2vcd`.

### How it is written

Inside `tb.cpp`, in C, through vgacap's C99 stream writer (extended as
needed, see Shared code): each half-clock the pins are packed into one
64-bit word and compared with the previous one, and only changes are
encoded (runs). That is a compare and a branch per sample, a few
nanoseconds, against the hundreds of nanoseconds a simulated clock takes
(see Performance budget). The encoded runs are compressed in the same
process in large blocks and written with buffered I/O into the job's
scratch directory on the fast root volume (see Where things live). No
per-sample pipe, no Python in the hot path, and raw samples never reach any
disk. FST via Verilator's own tracer stays a candidate only if step 2 shows
it fits the budget; it records every change through Verilator's generic
tracing machinery, which is expected to cost far more. The existing in-testbench decoding (mode
detection, frames for the clips, statistics in timing.json) stays as it is
for now: the clips are out of scope.

## Performance budget

The owner's requirement (2026-11-24): keeping the record and deriving
frames from it must not cost significant resources compared with simulating
the design. The baseline, from the 408 current runs: the simulation runs at
a median of 2.56 million clocks per wall second (0.25 slowest, 4.61
fastest), a median of 603 s per project, 104 CPU hours in total. At the
fastest that is about 220 ns per simulated clock.

Targets, each measured in rollout step 2 against the same project simulated
without a trace:

- Recording the trace: at most 5% added to simulation wall time, so about
  10 ns per clock at the fastest project. This rules out Python, a pipe
  write per sample, and anything per-clock that allocates or makes a system
  call; it is a compare, a branch and an occasional buffered write.
- Everything after the simulation (samplers, hash methods, PNGs, pages,
  copying to the bulk volume): at most 5% of the simulation's CPU time for
  the same project. Samplers work on the encoded runs, hash methods and PNG
  encoding run once per distinct frame, and only the native code touches
  per-clock data.
- Memory: a fixed buffer per job (the encoder's block and one frame per
  sampler), independent of run length.

If a target is missed, step 3 reports it with the profile and the fix, not
just the number.

## Layer 2: samplers, trace to frames

A sampler turns a trace into frames. It owns everything between the pins
and the pixels: finding sync, the mode, which clock each pixel is read at,
the active window, and where each frame starts. Samplers are a registry
(`ttvga/harness/samplers/`), each with an id, a definition precise enough to
reimplement, and an implementation in C in vgacap's `libvgaframe` (extended
as needed), working directly on the encoded runs so a long run of unchanged
pins costs one step, not one per clock. A Python reference implementation
exists for each sampler for the tests only.

The output pixel format is the same for every sampler, **rgb6**: one byte
per pixel, `R << 4 | G << 2 | B`, each channel the two bits the design
drives (R = uo[0], uo[4]; G = uo[1], uo[5]; B = uo[2], uo[6]; first bit most
significant, `tb.cpp:550-552`), 0..63. Display colour is channel * 85.

Initial samplers:

- **`tb-v1`**: exactly what `tb.cpp` does today, so its frames reproduce
  every published hash. With `t` the clocks since the end of the hsync pulse
  and `cpp` the clocks per pixel, pixel index `p = floor((t + cpp/2) / cpp)`,
  read at the first clock at which `p` takes a new value, stored at column
  `p - hback` (`tb.cpp:541-553`). This is only right for `cpp = 1`:
  - for `cpp > 1` (44 projects: 27 at 2.0, 9 at 1.9062, 5 at 4.2667, 3 at
    1.04) pixel `p` is read at `t = (p - 1/2) * cpp`, half a pixel *before*
    its period starts; at `cpp = 2` that is during pixel `p - 1`;
  - for `cpp < 1` (3 projects at 0.9524, `tt_um_MichaelBell_rle_vga` on
    three shuttles) `p` advances by more than one on some clocks, so about 5%
    of pixels are never read and stay 0.
- **`centre-v1`**: each pixel is read at the clock containing the middle of
  its period, `t = floor((p + 1/2) * cpp)`, for every `p` in the active
  window. At `cpp > 1` that is mid-pixel; at `cpp < 1` neighbouring pixels can
  share a clock, so none is left unread. At `cpp = 1` it equals `tb-v1`.

Both share tb-v1's sync and mode detection, so they differ only in the pixel
clock rule. Which sampler is the reference for comparisons is a decision
(below).

## Layer 3: frames, and hash methods over them

For each sampler, per project, under `<project>/<sampler>/`:

- `<shuttle>_<macro>_<sampler>_frames.rgb6.zst`: the distinct frames in
  order of first appearance, one zstd stream with `--long`; distinct frame `n`
  is at uncompressed offset `n * width * height`. Reading one frame means
  decompressing from the start (at most about 2 GB for the largest project),
  a second or two; step 2 also measures one zstd frame per image instead.
- `frames.txt`: header (`id`, `status`, `sampler`, `pixel_format: rgb6`,
  `width`, `height`, `mode`, `clock_hz`, `clocks_per_pixel`,
  `capture_after_clock`, `frame_clocks`, `frames`, `distinct_frames`, and the
  store's file name, size and SHA-256); one SHA-256 per distinct frame (the
  frame's identity, in store order); then the sequence as runs, `<first
  frame> <count> <distinct number> <start clock>`. A frame's start clock is
  the clock at which its vsync pulse ended. `frame_clocks` is the median
  measured distance between consecutive frame starts, in whole clocks; a run
  ends when the content changes or a frame starts other than `frame_clocks`
  after the previous one.
- `frame_hashes.<method>.txt`, one per hash method.
- `png/<n>.png` (n zero-padded to 6 digits): every distinct frame, 8-bit
  indexed with a 64-entry palette (index i is rgb6 value i), native
  resolution. A PNG converts back to the identical rgb6 bytes.
- `index.html`: every captured frame (number, start clock, distinct number)
  linking to its PNG; the distinct frames as a grid of the PNGs scaled down
  by CSS with `loading="lazy"`, so a browser fetches only what is on screen;
  and 1x/2x/4x views switched by links to `#1x`/`#2x`/`#4x` with CSS
  `:target` and `image-rendering: pixelated`. No scripts.

Hash methods are a registry (`ttvga/harness/hashmethods.py`): id,
definition, an implementation in C (run by the same native tool as the
samplers, once per distinct frame, never per captured frame), a Python
reference implementation for the tests, and committed test vectors. Initial methods:

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

The trace format, the encoder, the samplers and the frame tools are not
written here. They come from vgacap (github.com/mithro/vgacap: the VGCH
capture stream format, `libvgaframe`, its Python mirror and tools), which
already decodes VGA captured from real boards. Where it lacks something this
design needs, the feature is added to vgacap, with the session that maintains
it and through its review, not copied here (owner's decision 2026-11-24).
That also means a hardware capture and a simulation trace are read by the
same code.

Agreed with the vgacap session on 2026-11-24 (its answer was checked against
vgacap's `rtl` branch, d5f2654, which stacks on its PRs #1-#3, not yet
merged). Who does what: *vgacap* means that session, *here* means this
project's session writing it on a branch in vgacap, reviewed by that session
before anything merges.

| need | in vgacap today | work | by |
| --- | --- | --- | --- |
| a sample of every pin (43 bits), two per clock | VGCH stream, `sample_bits` 8/12/16/32 (`include/vgacap/stream.h:58`); `RLE ` chunk (32-bit value + run); `EVNT` (64-bit clock + value); C99 callback writer and reader, no allocation | format v2: samples up to 64 bits, and one new run-length chunk whose value width follows the header's `sample_bits` (1 to 8 bytes) with a LEB128 run length. That single chunk also answers vgacap's pending compact-RLE decision (tt-vga-capture `docs/research/2026-11-24-board-rle-throughput.md`: on the RP2350, raw 700 k samples/s, today's 8-byte RLE pairs 784 k, a u8 value + LEB128 run 1.46 M), so 8-bit board captures and 43-bit simulation traces share one encoder, reader and sampler path. In the C writer and reader and the Python mirror, with round-trip tests; a design note in tt-vga-capture/docs/design/ first, for the owner's decision | here |
| decoding runs, not clocks | `vgaframe_push(f, sample, run)` and `vgaframe_timing_push(l, hs, vs, run)`: an unchanged run is one call | a benchmark first (`vgacap-frames` on a synthetic 1.5e9-clock run stream, against the budget), then a C entry point that the native sampler and hash tool link. No CPython binding: Python stays out of the per-clock path | here |
| samplers (`tb-v1`, `centre-v1`, `cpp < 1`) | libvgaframe works at clock resolution: one byte per clock (6-bit colour + a written bit) per line; no pixel-clock rule | the samplers as a column pick from the clock-resolution line, run once per distinct clock-level frame | here |
| modes outside the table | 7 modes (640x480 at 60/72/75, 720x400@70, 800x600 at 56/60, 1024x768@60), matched by clocks per line; line buffer `max_clocks_per_line` | 640x504, and lines up to about 3,400 clocks (`cpp` 4.27); a learner path for timings not in the table | here (offered to vgacap; this side takes it) |
| rgb6 output | the raw buffer already holds the 6 bits; rgb24 is derived on emit | an rgb6 pointer beside rgb24 in `vgaframe_output_t`, checked against `R<<4 | G<<2 | B` with test vectors (libvgaframe's bit order follows TinyVGA's signal map) | here |
| compression, SHA-256 | none | vendored zstd (BSD) and SHA-256 (public domain) under `third_party/` with licence files, as an optional CMake target so the board and RP1 builds stay dependency-free | here |
| FST/VCD export | none (`vgacap-dump` prints chunks as text) | `vgacap-export --format fst\|vcd [--from/--to]`, a C tool beside `vgacap-dump` and `vgacap-frames`, with fstapi (MIT) vendored in the same optional target; driven from the reader's run callbacks (one run, one value change); decoded hsync/vsync/r/g/b/rgb6 from libvgaframe's signal map and frame markers from its frame callback, so waveform and frames cannot disagree; timescale from the TIME chunk; `.gtkw` written as text. It exports board captures too | here |

Also reused, not rewritten: `vgacap-dump` (stream inspector), PNG/PPM output
from `vgacap-frames`, and from tt-vga-testpatterns the calibration designs
(bars, grid, modes, prbs, counter) with exact Python references
(`tools/render.py`) and frame comparison (`tools/check_frame.py`). The
calibration designs, simulated through this pipeline, must come out
pixel-exact: that is the end-to-end test that simulation and hardware decode
the same way.

Dependency: vgacap pinned to a commit, built with its own CMake (C99, no
dependencies) by `tt-vga bootstrap`; the native tools here link
`libvgacap`.

Process (vgacap's): Milestone 10, "simulation traces", in tt-vga-capture's
`TASKS.md` (added on its main, c2b5efe) and a plan at tt-vga-capture `docs/superpowers/plans/2026-11-24-m10-simulation-traces.md`, written here and
reviewed there; vgacap branches off `main` once PRs #1-#3 are merged (until
then off `rtl`), one worktree per branch, small commits pushed as they go,
review before merge. Order: (1) the 64-bit sample and RLE64 design note, to
the owner; (2) the libvgaframe benchmark; (3) samplers, rgb6 and
`vgacap-export`; (4) vendored zstd and SHA-256.

If the owner chooses sigrok or FST as the stored trace format (Decisions),
VGCH is still the internal form between the encoder and the samplers, and
the stored file is an export of it.

## Where things live

On the host, the final outputs of this design live on the bulk data volume
inside the published tree (so they appear on data.wafer.space), one
pipeline-owned directory per project:

    <frames root>/<shuttle>/<macro>/
        <shuttle>_<macro>_trace.<ext>
        <sampler>/{store, frames.txt, frame_hashes.*.txt, png/, index.html}

Working files are on the fast root NVMe volume; only the finished output
moves to the bulk volume (owner's decision 2026-11-24). A job:

1. writes the trace, runs the samplers and hash methods, and builds the
   project's whole output directory (PNGs, pages and all) in a scratch
   directory under its work directory on the root volume, where the many
   small reads and writes are fast;
2. copies the finished directory to a staging directory on the bulk volume
   (outside the published tree, on the same filesystem as it);
3. renames it into place inside the published tree in one step, so the
   5-minute upload never sees a half-copied project;
4. deletes its scratch copy.

Root-volume use is temporary but large while jobs run (a compressed trace
plus one sampler's PNGs per running job, measured in rollout step 2). The
queue checks free space before starting each job and waits while the root
volume is below a threshold (`min_free_root_gb` in host configuration, with
a default from the step 2 measurements), and a job that fails deletes its
scratch directory. The published tree belongs to another account
(`tt-vga mirror` copies into it as that account, `remote.py:286-289`), so an
administrator creates, once, two pipeline-owned directories on the bulk
volume: the frames root inside the published tree and the staging directory
next to it. These are the only changes outside the pipeline user's home;
`docs/host-setup.md` gains the two `install -d` lines. The paths are host
configuration (`~/ttvga/host.toml` on the host: `frames_root`,
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
runs the native trace, sampler and hash tools) runs under a uv-managed CPython 3.14 instead of the
system `python3` (Debian 3.13): `remote.py` starts every host script through
it (`remote.py:187,228,252`; `runqueue.py:89` passes its interpreter on to
jobs). Checked on the host 2026-11-24: uv fetched CPython 3.14.7 into the
pipeline user's home and the standard library's `compression.zstd` worked;
PyPI's `zstandard` on 3.13 also worked and is the fallback. Pinning:

- `ttvga/tools.toml` gains a `[uv]` entry (the uv release tarball, version
  and checksum, like the other tools; uv is installed today but not pinned)
  and a `python` version that bootstrap installs with `uv python install`.
- vgacap is a pinned dependency (a commit), built by `tt-vga bootstrap`
  with the toolchain already on the host (g++/make, as for Verilator
  models); its compression and hashing code is vendored C inside vgacap
  (zstd and SHA-256 are BSD/public-domain C), so no system package is
  needed.
- Locally, `requires-python` becomes `>=3.14`.

## Runs that do not finish normally

- `sim-timeout` and `unstable-sync`: the trace up to the stop and the frames
  decoded from it are kept, with `status` saying so.
- Input-probe runs (`job.py:236-253`): no trace (`tb.cpp --no-trace`).
- No picture (no-sync, bad-timing): the trace is kept, as the evidence for
  why there was no picture; samplers produce no frames.
- build-failed, fetch-failed, skipped: nothing.
- A project that had output and now has none: the job removes its stale
  directory from the published tree and `collect` removes the stale files
  from git. The upload never deletes on the server, so `tt-vga verify` lists
  published directories that no longer exist locally, for removal there.

## Tools (`tt-vga ...`)

- `trace info|export|slice`: header and signal statistics; export to FST or
  VCD for GTKWave and Surfer (with a `.gtkw` save file), or to the other
  stored formats; cut a clock range (one frame, say) into a small file.
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
  both, ready for `trace slice`.

## Code that changes

- `tb.cpp`: writes the trace; `--trace PATH`, `--no-trace`; no longer writes
  the `frame_hashes` list into timing.json (`tb.cpp:590-608`). Its own
  decoding for the clips is untouched.
- `ttvga/harness/`: the trace writer, samplers, hash methods, PNG and page
  writing, and the job steps that run them and rename the result into place.
- `ttvga/remote.py`: every host script through the pinned Python; `collect`
  brings back each sampler's `frames.txt` and the committed hash file
  (replacing `remote.py:263-265`); bootstrap as above.
- `ttvga/framehashes.py` and `tests/test_framehashes.py` are removed; a
  one-off script moves and re-heads the 408 existing hash files.
- README.md (lines 82-92) and docs/host-setup.md are rewritten.
- The two harness sessions are told before the files move: the new paths,
  `frames.txt`, the traces, the samplers, and that `hash_offset_basis` is
  unchanged.

## Rollout

1. Implement on a branch with tests: the trace writer and reader for each
   candidate format and conversion between them; FST and VCD export checked
   from a synthetic stream against a committed expected VCD, and `fst2vcd`
   of the FST output equal to the VCD output (no viewer needed); both samplers on synthetic
   traces with known pixels, at `cpp` of 0.95, 1, 1.9 and 2; rgb6 and PNG
   round trip; hash methods against committed vectors; `compare` on
   constructed shifted and differing runs; the stale-file cases.
2. Run 7 projects: nyancat, metaballs (800x600), a static one, a QSPI one,
   the 640x504 tennis game, one at `cpp = 2`, and one at `cpp = 0.9524`.
   Measure each project twice, without and with the trace, to get the
   overhead against the budget; then trace size per format, store and PNG
   sizes, and sampler, hashing and PNG CPU time. Check tb-v1 frames reproduce the published FNV
   hashes exactly. Compare SHA-256 and FNV distinct counts (543,730 today is
   a count of distinct FNV values, `tb.cpp:477,488`). Show tb-v1 against
   centre-v1 for the `cpp != 1` ones. Export one frame of each project as
   FST and VCD, check them with `fst2vcd`, and open them in GTKWave and in
   Surfer on a desktop, with screenshots in the step 3 report.
3. Report to the owner, projected to all 408: total trace size per format,
   store and PNG sizes, run time, and the upload's file-listing time with the
   extra files (today 62,641 entries take about 25 s each 5-minute run; the
   PNGs add about 544,000 per sampler published).
4. Re-run all projects (several hours, progress reported on the usual
   cadence). Check tb-v1 reproduces all 408 committed FNV files; any project
   that does not is investigated, not accepted. Publish.

## Decisions for the owner

1. The trace format, after step 3: sigrok, FST or planar zstd. Before
   that, and independent of it: vgacap's new run-length chunk (variable
   value width, LEB128 run), presented with its design note, since the
   encoder writes it whichever stored format is chosen.
2. Which sampler is the reference the other harnesses should match: `tb-v1`
   (matches everything published so far, wrong for 47 projects) or
   `centre-v1`. Both are computed and published either way. Recommended:
   `centre-v1`, once step 2 shows it is right on the 47, keeping `tb-v1`
   published for continuity.
3. If step 3 shows the upload's listing is too slow: a longer upload
   interval, or the upload skipping the frames tree unless the pipeline marks
   it changed.

## Not in scope

- How the clips are made (they still come from `tb.cpp`'s own decoding; a
  later change could make them from a sampler's frames), and their two
  copies.
- Audio: it is in the trace (`uio_out`, `uio_oe`), so it can later be
  derived from the trace too, but the current audio path is unchanged.
