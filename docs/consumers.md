# Using this repository's simulation data

This note is for [tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) and
[tt-harness-handheld-vga](https://github.com/mithro/tt-harness-handheld-vga). It says which files to
read, what stimulus made them, and how to compare against them.

vgacap's format documents are the authority for every byte of the trace, of `frames.txt` and of the
hash files. This note links to them at the pinned commit
([`ttvga/tools.toml`](../ttvga/tools.toml), `[vgacap]`, `80f6aa3`) and never restates them:

- [trace-format.md](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/docs/trace-format.md)
- [frames-format.md](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/docs/frames-format.md)

## What exists today, and what is still to come

The re-run of all projects with traces (Task 23 of the [pipeline plan](superpowers/plans/2026-11-26-raw-traces-pipeline.md)) has not happened yet. Until it does:

- The archive has no `frames/` subtree. There are no traces, stores, PNGs, pages or `sha256-rgb6`
  files to download yet.
- No committed `result.json` has `trace`, `samplers`, `tb_v1_check` or `published`. Those come with
  the re-run.
- No committed `frames.txt` exists yet. Those come with the re-run.
- The FNV files moved from `data/results/<s>/<m>/frame_hashes.txt` to the tb-v1 path below in
  commit `e112cdb` (plan Task 17). The hash lines did not change, and neither did `hash_offset_basis`.
  Each converted `result.json` has `tb_v1` with state `stale` and `trace_sha` null.

## What to read, in git

| path | read |
|---|---|
| [`data/targets.json`](../data/targets.json) | `targets[]` |
| `data/results/<s>/<m>/result.json` | see the key table below |
| `data/results/<s>/<m>/frames/<sampler>/frames.txt` | the whole file |
| `data/results/<s>/<m>/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` | the whole file |

In [`data/targets.json`](../data/targets.json), skip every target whose `shuttle` is `testpatterns`.
Those are calibration designs from [`data/extra-targets.json`](../data/extra-targets.json). They are
simulated but never published ([`ttvga/targets.py`](../ttvga/targets.py), `PUBLISHED_EXCLUDED_SHUTTLES`).

`<sampler>` is `centre-v1` or `tb-v1`. [`tt-vga collect`](../ttvga/remote.py) brings exactly these three kinds of file into
git ([`ttvga/remote.py`](../ttvga/remote.py), `_FRAMES`). The other hash files are only in the archive.

The `result.json` keys to read:

| key | written by |
|---|---|
| `verdict` | [`ttvga/analyze.py`](../ttvga/analyze.py) |
| `override` | [`ttvga/harness/job.py`](../ttvga/harness/job.py) |
| `auto_ui_in` | [`ttvga/harness/job.py`](../ttvga/harness/job.py) |
| `qspi` | [`ttvga/harness/job.py`](../ttvga/harness/job.py) |
| `trace` | [`ttvga/harness/job.py`](../ttvga/harness/job.py) |
| `samplers` | [`ttvga/harness/derive.py`](../ttvga/harness/derive.py) |
| `tb_v1` | [`ttvga/harness/job.py`](../ttvga/harness/job.py) |
| `tb_v1_check` | [`ttvga/harness/derive.py`](../ttvga/harness/derive.py) |
| `published` | [`ttvga/harness/job.py`](../ttvga/harness/job.py) |

The verdicts are listed at the top of [`ttvga/analyze.py`](../ttvga/analyze.py). `tb_v1_check` is
`match`, `mismatch`, `not-run` or `off`.

## What to read, in the archive

The archive is <https://data.wafer.space/big-storage/tinytapeout-vga-videos/>.

| path | contents | owner |
|---|---|---|
| `<s>/<m>/` | the clips, poster, contact sheet, preview | this repository |
| `frames/<s>/<m>/` | the trace, stores, hash files, PNGs, pages | this repository |
| `<s>/<m>/<id>-<sha12>.bin` | FPGA bitstreams | the FPGA session (Ruling AA) |
| [`fpga-library.json`](https://data.wafer.space/big-storage/tinytapeout-vga-videos/fpga-library.json) | the bitstream index | the FPGA session (Ruling AA) |

On 2026-11-27, `fpga-library.json` listed 346 designs. [`ttvga/fpgalibrary.py`](../ttvga/fpgalibrary.py) checks
`fpga-library.json`. [`tt-vga mirror`](../ttvga/remote.py) excludes those files and [`tt-vga verify`](../ttvga/harness/verify.py) never lists them
([`ttvga/harness/verify.py`](../ttvga/harness/verify.py), `FOREIGN_PATTERNS`).

Inside `frames/<s>/<m>/` the only names published are those in `ALLOWED` in
[`ttvga/harness/publish.py`](../ttvga/harness/publish.py), with `<stem>` = `<s>_<m>`:

```
<stem>_trace.vgch.zst                        the raw trace (trace-format.md)
<sampler>/frames.txt                         frames-format.md
<sampler>/frame_hashes.<method>.txt          frames-format.md
<sampler>/<stem>_<sampler>_frames.rgb6.zst   the distinct frames (frames-format.md)
<sampler>/index.html                         the sampler's page
<sampler>/png/<NNNNNN>.png                   one PNG per distinct frame
tb-v1/TRACE_SHA256                           the SHA-256 of the trace tb-v1 was made from
```

Again: none of `frames/` exists yet. It appears with the Task 23 re-run.

## Stimulus, exactly

All of this is [`ttvga/harness/tb.cpp`](../ttvga/harness/tb.cpp), `tick` and the reset sequence after it.

- Clock 0 is the first reset clock.
- `ena` is 1 from clock 0.
- `rst_n` is 0 for clocks 0-9 and 1 from clock 10.
- `ui_in` and `uio_in` are held from clock 0 at the override's `ui_in` and `uio_in`, else 0. When the
  job's input probe found a value, `ui_in` is `auto_ui_in` instead
  ([`ttvga/harness/job.py`](../ttvga/harness/job.py), `model_cmd`).
- Apart from the QSPI model below, the inputs change only by:
  - an event of the override's `inputs` list ([`ttvga/overrides.py`](../ttvga/overrides.py)), applied at the start of the tick whose clock equals
    the event's clock, before that clock's falling and rising edges;
  - the gamepad emulation, which drives `ui_in` bits 6 (data), 5 (clock) and 4 (latch), one step per
    scan line (800 clocks until the line period is measured), when the override has a `gamepad` list.
- With the QSPI model (`qspi` in `result.json` set and not `off`), `uio_in` is the model's response.
  It is updated after each rising edge, and the design is evaluated again before the clk-high sample.
  `result.json` records `qspi` even when the job ran with `--no-qspi`, which turns the model off.
  Production runs never pass `--no-qspi`: the queue's job command does not have it
  ([`ttvga/harness/runqueue.py`](../ttvga/harness/runqueue.py), `job_command`). Only this
  repository's own tests use it.
- Without the QSPI model, `uio_in` is not the design's own `uio_out` read back. It stays at the
  value above.
- The initial state is [Verilator](https://verilator.org)'s `--x-initial fast`
  ([`ttvga/harness/job.py`](../ttvga/harness/job.py), `verilator_base`). The pinned [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-14) ([`ttvga/tools.toml`](../ttvga/tools.toml)) ships
  only the short help for it, `verilator --help`:

  ```
      --x-initial <mode>          Assign initial Xs to this value
  ```

  The model the pinned Verilator (5.053) builds with it sets every variable to 0 in its
  `_ctor_var_reset`, with no random reset. So every variable not set by the design's own initialisers (`initial` blocks, declaration
  initialisers, `$readmemh`) starts at 0.
- The trace's sample `2c` is clock `c` with clk low, sample `2c + 1` with clk high
  ([trace-format.md](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/docs/trace-format.md),
  "Clocks and time"). Byte `i` of a `uo_out` dump is sample `2i + 1`, `uo_out` after the rising edge
  of clock `i`.

## The trace-content check

`trace.uo_out_sha256` in `result.json` is the SHA-256 of the `uo_out` dump over the half-open clock
range `[0, M)`, one byte per clock, with `M = trace.uo_out_sha256_clocks[1]`. No sampler is involved.
[`tracetool uohash`](../ttvga/harness/tracetool.c) computes it. `M` is the trace's clock count or
2^25, whichever is smaller.

To check another simulation's dump against a trace, hash its first `M` bytes and compare.

## Hash inputs

| method | pixel bytes | bytes per pixel |
|---|---|---|
| `sha256-rgb6` | rgb6 | 1 |
| `fnv1a64-tb2026-rgb888` | RGB888 | 3 |

- **`sha256-rgb6`** is SHA-256 over the frame as rgb6, one byte per pixel: `R<<4 | G<<2 | B`.
  - R is `uo_out[0]`, `uo_out[4]`; G is `uo_out[1]`, `uo_out[5]`; B is `uo_out[2]`, `uo_out[6]`.
    The first bit is the more significant.
  - The bytes are row-major, `width * height` of them, from the sampler's first active pixel of its
    first active line.
  - It is not RGB888.
- **`fnv1a64-tb2026-rgb888`** is FNV-1a 64 over the same frame as RGB888, each 2-bit channel stored as
  `value * 85`. `hash_offset_basis` is unchanged: `0x14650fb0739d0383`, not the standard
  `0xcbf29ce484222325`. The FPGA harness's own hash uses the standard basis
  ([frame-definition.md](https://github.com/mithro/tt-harness-fpga-vga/blob/e5b96b2edbb43ee9ed916091b61fcc5c9fdf76ae/docs/frame-definition.md), "Hash").

Sources: [`hashes.py`](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/python/vgacap/hashes.py)
and [`tbv1.py`](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/python/vgacap/tbv1.py) (`_rgb6`).

## Frame starts, and cpp = 1

**tb-v1**
([`tbv1.py`](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/python/vgacap/tbv1.py), `sample`):

- A frame starts at the end of the vsync pulse: the first clock whose clk-high sample is outside it.
  `capture_after_clock` is in the spec's clock numbering, so consumers must not subtract 1. Frame 0
  starts at the first vsync end at a clock strictly greater than it.
- A line starts at the end of the hsync pulse, the same way.
- At cpp 1 it reads column `x` of a line at clock `x` after the line start. Pixel `p` of the frame is
  column `hback + p`, and row `y` is line `vback + y` after the frame start.

The FPGA harness cuts frames the same way: a line starts at the first sample after the hsync pulse,
and a frame at the first line start at or after the vsync end
([frame-definition.md](https://github.com/mithro/tt-harness-fpga-vga/blob/e5b96b2edbb43ee9ed916091b61fcc5c9fdf76ae/docs/frame-definition.md),
"Lines and frames" and "Mode table"). Its table has three modes, matched exactly at one clock per pixel. Their
back porches equal [`tb.cpp`](../ttvga/harness/tb.cpp)'s `MODES`:

| mode | hback | vback |
|---|---|---|
| 640x480@60 | 48 | 33 |
| 800x600@60 | 88 | 23 |
| 1024x768@60 | 160 | 29 |

So for a cpp = 1 design in one of these modes, the FPGA harness's one-sample-per-pixel crop is tb-v1's
frame. The stimulus must match too. The FPGA harness's `ideal` profile reads `uio` back and does not
replay timed or gamepad scripts (frame-definition.md, "Stimulus and initial state"). tb.cpp does
neither of those, so a design that reads its own `uio` outputs back, or has such a script, can differ.

**centre-v1**
([`centre.py`](https://github.com/mithro/vgacap/blob/80f6aa3fc3c5a7ebace8625bf4ab6d14c69373a2/python/vgacap/centre.py)):

- A frame starts at the hsync leading edge that begins the first line of the vsync pulse.
- Rows count from the start of the vsync pulse: row `y` is line `vsync + vback' + y`.
- Pixels count from the hsync leading edge: pixel `p` is at pixel position `hsync + hback' + p`, so at
  clock `floor((hsync + hback' + p + 0.5) * cpp)` after the edge.
- `hback'` and `vback'` are the `porches` line of its `frames.txt`.

Which projects agree frame for frame between tb-v1, centre-v1 and the FPGA crop is the table from
plan Tasks 21 and 22 (to fill in below). For cpp != 1, compare the raw trace only.

## tb-v1 freshness

Read `tb_v1` in `result.json` ([`ttvga/harness/job.py`](../ttvga/harness/job.py), `tb_v1_rule`):

| `tb_v1.state` | `tb_v1.trace_sha` |
|---|---|
| `current` | this run's `trace.sha256` |
| `stale` | the SHA-256 of an older trace |
| `stale` | `null` |
| `none` | `null` |

- `current`: the tb-v1 files were made from this run's trace.
- `stale`: the tb-v1 files were made from another trace, the one named by `trace_sha`. A stale file is
  still valid for the trace it came from.
- `stale` with `trace_sha` null: the converted files, made by the run before traces existed.
- `none`: there are no tb-v1 files.
- `tb_v1.dropped` is `true` only after [`job.py --drop-tb-v1`](../ttvga/harness/job.py).

A run never deletes tb-v1 files ([Ruling Z](superpowers/plans/2026-11-26-raw-traces-pipeline.md)), so a default re-run leaves them `stale`.

## To fill in later

- The reference sampler (plan Task 22).
- The table of projects that agree frame for frame (plan Tasks 21 and 22).
- The commit of this repository to pin (plan Task 23).
