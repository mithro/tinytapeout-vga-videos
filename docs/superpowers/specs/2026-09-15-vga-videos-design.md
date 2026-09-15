# Tiny Tapeout VGA videos: design

Status: draft for review, 2026-09-15.

## Goal

For every Tiny Tapeout project whose pinout matches the Tiny VGA Pmod, run a
simulation of the design, decode the VGA output, and produce 10, 30 and 60
second videos showing what a viewer would expect to see on a monitor. Check
each video is actually useful, and when it is not, have an AI agent work out
why (project broken, not really VGA, wrong stimulus, harness bug, other).

There are 440 such projects across 24 shuttles (as of 2026-09-15, from the
`tinytapeout-project-search` database). The work runs for weeks to months,
will be interrupted, and must always be resumable from the committed state.

## Non-goals (for now)

- Title cards, outros and YouTube upload. The raw clips are produced so that
  a later pass can add those.
- Long-term hosting (data.wafer.space or similar). Videos stay on the
  simulation host for now.
- Gate-level simulation. Phase 2, see the end of this document.
- Audio (75 projects also match the TT Audio Pmod). Recorded later if wanted.

## What we build on

- **Project list**: `data/projects.json` from
  <https://github.com/mithro/tinytapeout-project-search>, which already holds
  `repo`, `commit`, `source_files`, `top_module`, `clock_hz`, `language`,
  `pinout` and the inferred Pmod matches for every project on every shuttle.
  This repo does not re-fetch anything from tinytapeout.com.
- **Reference simulator**: the Tiny Tapeout VGA Playground
  (<https://github.com/TinyTapeout/vga-playground>, `src/sim/vga.ts`). It is
  browser-only (Verilator compiled to WASM), so it cannot be run headlessly,
  but it defines the conventions we copy:
  - Tiny VGA bit layout on `uo_out`: hsync bit 7, vsync bit 3,
    R1 G1 B1 in bits 0 to 2, R0 G0 B0 in bits 4 to 6 (2 bits per channel).
  - Reset: `ena=1`, `rst_n=0` for 10 clocks, then `rst_n=1`.
  - Sync polarity is detected by measuring which phase of each sync signal
    is shorter; the shorter phase is the pulse.
  - The Playground samples one pixel per clock and assumes 25.175 MHz. We
    generalise this (see "Decoding").
  - Project sources come from `info.yaml` `project.source_files` under
    `src/`, plus files pulled in by `` `include `` and `$readmemh/b`.
- **Toolchain**: YosysHQ oss-cad-suite (Verilator, Icarus, Yosys, cocotb)
  installs into a home directory without root. A static ffmpeg build does
  too. No system packages are needed on the hosts.

## Architecture

```
laptop (orchestrator, has `claude`)          remote host (dedicated user ttvga)
┌───────────────────────────────┐            ┌──────────────────────────────────┐
│ tt-vga targets   → data/targets.json       │ ~/ttvga/tools/   oss-cad-suite,  │
│ tt-vga run --host  ── ssh/rsync ─────────▶ │                  ffmpeg, uv      │
│   bootstrap, sync harness, start queue     │ ~/ttvga/work/<shuttle>/<macro>/  │
│ tt-vga collect   ◀── rsync results ──────  │   src/ (clone)  build/  frames/  │
│ tt-vga analyze   → data/results/*.json     │   sim.log  timing.json  *.avi    │
│ tt-vga diagnose  → claude -p, overrides    │ ~/ttvga/videos/<shuttle>/<macro>/│
│ tt-vga report    → docs/status.md          │   10s.avi 30s.avi 60s.avi poster │
└───────────────────────────────┘            └──────────────────────────────────┘
```

The host is named only on the command line (`--host ttvga@example`) or in
`TTVGA_HOST`. An optional local config at
`~/.config/tinytapeout-vga-videos/config.toml` may hold named hosts; it is
outside the repository and never committed. Nothing in the repository names
a machine.

### Components (Python package `ttvga`, run with `uv`)

| Module | Role |
| --- | --- |
| `ttvga/targets.py` | Filter the project-search data to Tiny VGA matches; write `data/targets.json` (one record per project: shuttle, macro, repo, commit, sources, top, clock_hz, other Pmods, language). |
| `ttvga/harness/` | Files shipped to the host: `tb.cpp` (Verilator testbench), `build.py`, `run.py`, `decode.py`, `encode.py`. |
| `ttvga/remote.py` | SSH/rsync wrapper: `bootstrap`, `sync`, `queue`, `status`, `collect`. Uses `ssh -o BatchMode=yes`, `tmux` for the long-running queue. |
| `ttvga/queue.py` | Job runner executed on the host: takes `targets.json`, runs N jobs in parallel (default cores/2), writes one `result.json` per project, skips projects already done unless `--redo`. |
| `ttvga/analyze.py` | Turns `timing.json` + frame statistics into a verdict. |
| `ttvga/diagnose.py` | Runs `claude -p` locally on failures, records the structured answer, applies harness fixes as overrides. |
| `ttvga/report.py` | Writes `docs/status.md` (counts per verdict per shuttle) and `data/status.json`. |
| `overrides/<shuttle>/<macro>.yaml` | Human or agent supplied per-project tweaks: clock, input script, extra Verilator flags, source patches, `skip: reason`. Committed. |
| `data/results/<shuttle>/<macro>.json` | Committed outcome per project: verdict, timings, frame stats, diagnosis history, video paths and hashes. Small; the videos are not committed. |
| `PROGRESS.md` | Running work log, appended every session, committed often. |

### Per-project pipeline on the host

1. **Fetch**: `git clone --depth 1 --no-checkout` the project repo, then
   `git fetch origin <commit>` and check out that commit only. Copy
   `src/<source_files>` plus any `` `include `` and `$readmem` files into
   `work/<shuttle>/<macro>/src/`. Record the fetch failure if the repo or
   commit is gone.
2. **Build**: `verilator --cc --exe --build -O2 --x-assign fast
   --x-initial fast -Wno-fatal --top-module <top> tb.cpp <sources>`. Add
   `--timing` when the sources are SystemVerilog or use delays. Any
   non-Verilog language project (HardCaml, Chisel, Clash, Spade, VHDL) is
   expected to ship generated Verilog in `source_files`; if not, verdict
   `unsupported-language`. Analog projects are skipped up front.
3. **Simulate**: `tb.cpp` drives `clk` at the project's `clock_hz`
   (25.175 MHz when 0 or missing), applies the reset sequence, then replays
   the input script (default: `ui_in = 0`, `uio_in = 0`). Every clock it
   appends `uo_out` to a run-length-encoded stream (value, count). Runs for
   `60 s + 2 frames` of simulated time or until a wall-clock limit (default
   30 min), whichever first. With 1.5 G cycles for 60 s at 25 MHz and
   Verilator at 5 to 20 M cycles/s, most projects take 1 to 5 minutes.
4. **Decode** (`decode.py`): from the `uo_out` stream, detect sync polarity
   (shorter phase is the pulse), measure the hsync period and vsync period
   in clocks, and pick the closest known mode:

   | Mode | Clock (MHz) | Line clocks | Lines | Active |
   | --- | --- | --- | --- | --- |
   | 640x480@60 | 25.175 | 800 | 525 | 640x480 |
   | 640x480@60, 2 clk/px | 50.35 | 1600 | 525 | 640x480 |
   | 800x600@60 | 40 | 1056 | 628 | 800x600 |
   | 1024x768@60 | 65 | 1344 | 806 | 1024x768 |
   | unknown | | measured | measured | full line minus sync |

   Clocks per pixel = line clocks / mode line pixels (rounded). Pixels are
   sampled once per pixel period at the start of the period. Frames are
   cut at vsync, lines at hsync, then cropped to the active area (for a
   known mode) or to the bounding box of non-black content (unknown mode).
   Output: `frames/NNNNNN.ppm` (2-bit colour scaled to 8-bit, 0/85/170/255)
   and `timing.json` (polarity, periods, mode, clocks per pixel, frame
   count, dropped/short lines).
5. **Encode** (`encode.py`): ffmpeg, `-c:v mjpeg -q:v 2`, container `.avi`,
   frame rate = measured vsync rate (about 60 fps), native resolution. One
   60 s encode from all frames, then 10 s and 30 s cut from the same frame
   sequence (`-t`). Also `poster.png` (a frame from about 5 s in, when
   content has usually settled) and `contact.png` (a 4x4 sheet of frames
   spread over the clip) for quick human review. Files are named
   `<shuttle>_<macro>_60s.avi` and so on under `~/ttvga/videos/`.
6. **Result**: `result.json` with stage reached, verdict inputs, timings,
   wall time, tool versions, sha256 of each video.

### Analysis and verdicts (`analyze.py`)

| Verdict | Rule |
| --- | --- |
| `fetch-failed` | repo or commit not reachable |
| `build-failed` | Verilator error (log kept) |
| `unsupported-language` | no Verilog sources |
| `sim-timeout` | wall-clock limit hit before 60 s of frames |
| `no-sync` | no periodic hsync/vsync found in the first 2 s |
| `bad-timing` | sync found but periods unstable (> 1% jitter between frames) or fewer than 300 frames in 60 s |
| `blank` | more than 95% of frames are a single colour |
| `static` | frames exist but fewer than 2 distinct frames in 60 s (may be fine: a static image project; flagged for the agent to confirm) |
| `x-propagation` | Verilator reported X or the stream never leaves an all-zero/all-one state after reset |
| `ok` | stable timing, known or plausible mode, content present |

`static` and `ok` both produce videos; the others may produce partial
videos which are kept for debugging but not counted as deliverables.

### Diagnosis (`diagnose.py`)

For each project whose verdict is not `ok` (and for `static`), run the
Claude Code CLI locally in non-interactive mode:

```
claude -p --output-format json --max-turns 6 --model <model> < bundle.md
```

The bundle holds: project docs (description, how it works, how to test,
external hardware, pinout from the project-search data), the source files
(trimmed to a size limit, largest files summarised), the build/sim log
tail, `timing.json`, `result.json`, the contact sheet image, and the
harness source so the agent can spot harness bugs. It asks for a JSON
answer:

```json
{"cause": "project-broken | not-vga | wrong-inputs | wrong-clock |
           harness-bug | tool-limitation | static-by-design | other",
 "confidence": "high|medium|low",
 "explanation": "...",
 "fix": {"clock_hz": 50000000, "inputs": [...], "verilator_flags": [...],
         "patch": "unified diff or null", "skip": "reason or null"}}
```

A returned `fix` is written to `overrides/<shuttle>/<macro>.yaml`, the
project is re-queued, and the outcome is appended to the result's
`diagnosis` list. At most two automatic attempts per project; after that
it is left for a human with the agent's notes. `harness-bug` findings are
reported separately since they may affect every project. Cost and token
usage from the CLI's JSON output are logged to `data/diagnosis_usage.jsonl`.
Never more than two diagnosis runs in parallel.

### Stimulus (input scripts)

The default is all inputs low. That is right for most self-running demos
but wrong for the 64 projects that also match the Gamepad Pmod and for
designs that wait for a button. Input scripts are YAML lists of events:

```yaml
inputs:
  - at: 0s        # simulated time (or clocks)
    ui_in: 0b00000000
  - at: 3s
    ui_in: 0b00000001
gamepad:                    # optional: drive the Gamepad Pmod protocol
  - at: 5s
    press: [start]
  - at: 8s
    hold: [right]
    for: 2s
```

The gamepad block is expanded by a small emulator of the Pmod's serial
protocol (latch, clock, data on the `ui_in` pins the project declares).
Generic scripts are tried first: `idle`, then `press-everything` (each
input toggled in turn) for projects that look idle; the agent can supply a
project-specific script.

### Remote runner

- `tt-vga bootstrap --host ttvga@HOST`: installs oss-cad-suite, static
  ffmpeg and uv under `~/ttvga/tools/` on the host (idempotent, version
  pinned in `ttvga/tools.toml`), checks `verilator --version` and
  `ffmpeg -version`.
- `tt-vga sync --host`: rsync `ttvga/harness/`, `data/targets.json` and
  `overrides/` to `~/ttvga/`.
- `tt-vga queue start|stop|status --host`: runs `queue.py` inside `tmux`
  (session `ttvga`), with `--jobs N` and an optional `--only shuttle` or
  `--only shuttle/macro`. The queue writes `queue.log` and per-job
  `result.json`; it is safe to kill and restart at any time since each job
  is atomic (written to a temp dir and renamed on completion).
- `tt-vga collect --host`: rsync every `result.json`, log tail,
  `timing.json`, `poster.png` and `contact.png` back into `data/results/`
  and `data/review/` (posters and contact sheets are committed; they are
  small PNGs). Videos are listed with size and hash but stay on the host.
- Nothing runs as `tim`, `ansible` or `root`. The dedicated user is
  `ttvga` (see `docs/host-setup.md`). The orchestrator connects with an SSH
  key authorised for that user.

### Interruption and resume

- Every state-changing step writes a file and the next step reads files, so
  a killed orchestrator or an exhausted token budget loses at most the
  in-flight job.
- `PROGRESS.md` is appended at the end of every working session (and
  mid-session for anything non-obvious): date, what was done, what was
  learned, what is next, open questions. It is committed together with the
  results it describes. A reader with only the repository can resume.
- `data/status.json` and `docs/status.md` are regenerated by
  `tt-vga report` and committed, so the counts in the README are never
  hand-maintained.

### Throughput estimate

440 projects, 60 s each at 25 MHz = 1.5 G cycles per project. At 10 M
cycles/s that is 150 s of simulation plus about 30 s of decode and encode.
On an 88-core host with 40 parallel jobs the whole set is a few hours of
compute per pass. The wall time of the project is dominated by the
diagnose-fix-retry loop and by human review, not by simulation.

### Phase 2: gate-level simulation

Tiny Tapeout designs are small (mostly 1x1 and 1x2 tiles), so gate-level
simulation of the taped-out netlist is feasible and shows what the chip
really does, including synthesis bugs and X issues that RTL hides. Items
to research when phase 1 is producing videos:

- Where the final netlists live per shuttle (the shuttle repos hold only
  docs and stats; the `tt_um_*.v` powered netlists are in the shuttle
  build artifacts or the project repos' GDS action artifacts).
- Cell models per PDK: sky130A `sky130_fd_sc_hd` Verilog models,
  IHP `sg13g2_stdcell` models, gf180mcu models. Installable via `ciel`
  (formerly volare) into the host's home directory.
- Expected slowdown of 20 to 100 times, so 10 s clips may be the gate-level
  deliverable, and Verilator with `--timing` or Icarus for cells with
  specify blocks.
- Compare RTL and gate-level frames to flag divergence.

### Phase 3 (later, out of scope)

Title card and outro, YouTube upload, publishing to data.wafer.space,
audio capture for TT Audio projects.
