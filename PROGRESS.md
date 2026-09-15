# Progress log

Newest entry first. One entry per working session, plus mid-session notes
whenever something non-obvious is learned. This file is the resume point
if work stops for lack of credits or tokens: read it, then `docs/status.md`,
then the newest `data/results/` entries.

## 2026-09-15 (later): first pipeline, first video

Done:
- Dedicated `ttvga` user created on the big host (no sudo, no docker), key
  pair `~/.ssh/ttvga_ed25519` on the laptop, local host config in
  `~/.config/tinytapeout-vga-videos/config.toml` (short name `big`).
  Toolchain installed under `/home/ttvga/ttvga/tools/`: oss-cad-suite
  2026-09-14 (Verilator 5.053), ffmpeg n8.1.2 static, uv. Pinned in
  `ttvga/tools.toml`; `tt-vga bootstrap` re-installs on a fresh host.
- The request for the same user on the other three hosts could not be
  delivered: the ansible-owning Claude session is not reachable from this
  machine (the desktop session I could reach said it does not own the
  repo and pointed at a session named "ansible-main"). Needs the owner.
- `tt-vga targets`: 440 targets, 9 skipped (8 analog, 1 Wokwi).
- `ttvga/harness/tb.cpp` + `job.py` + `runqueue.py`: fetch at commit,
  Verilator build (auto-retry with --timing), simulate with sync
  calibration, decode, MJPEG via ffmpeg pipe, cuts, poster, contact sheet,
  atomic result.json. `tt-vga host-check|bootstrap|sync|queue|collect|
  analyze|report` on the laptop.
- First end-to-end run: tt08 Metaballs (50 MHz, 800x600@72), 3 s clip in
  22 s wall, 7.1 M clocks/s with the -Os default build. Now built with
  OPT_FAST=-O2; measure again.
- Five-project 60 s pilot started on the big host (5 parallel jobs):
  Metaballs, VGA donut (48 MHz, 2x2), Rebecca's VGA timing experiments,
  sushi demo, not-a-dinosaur. First result: timing experiments = no-sync
  after 1 s of calibration (probably needs ui_in to select a mode; a good
  first diagnosis case).

Learned:
- A harness file must not be called `queue.py`: it shadows the stdlib
  module and breaks `concurrent.futures`. Renamed to `runqueue.py`.
- The `tb` exit status is 3 for any non-ok timing status; job.py stops
  before encode when there is no raster at all.
- Hooks in this environment block inline python, stderr-to-null redirects
  and some compound commands; write scripts to files instead.

Pilot outcome (5 projects, 60 s each, 5 parallel jobs, 10 minutes wall):
- 4 of 5 produced good videos first time: Metaballs (800x600@72),
  VGA donut (48 MHz: 1525 clocks per 640x480 line, so 1.906 clocks per
  pixel; the first decoder only handled integer ratios and produced a
  stretched 1342-wide frame, now fixed by fractional resampling),
  sushi demo, not-a-dinosaur (runs without input, needs a jump button
  for a more interesting clip: "needs-stimulus").
- Rebecca's VGA timing experiments needed a write pulse on ui_in[7];
  with `overrides/tt09/...yaml` it is a stable 640x480@60 with the pattern
  changing at 20 s and 40 s.
- Speed: 6.7 to 7.1 M clocks per wall second per job; 60 s of video takes
  4 to 10 minutes of wall time per project. 440 projects on 40 jobs is
  about 1.5 hours.
- `tt-vga diagnose` tried once on the timing experiments (before the
  override was applied): model claude-sonnet-5, 8 turns, $0.19, correct
  cause (wrong-inputs) and a usable override. Note it could read the
  repo's existing override because the CLI runs inside the repo; for a
  fair test hide it or run before writing one.
- Overrides moved to YAML compiled on the laptop (seconds, button names)
  and Gamepad Pmod emulation added to tb.cpp; not yet exercised.
- Example images committed under `docs/examples/`.

Full run 2026-09-15 04:13 to 05:51 UTC (440 targets, 40 jobs, 60 s):
270 ok, 75 static, 30 build-failed, 20 blank, 13 no-sync, 7 bad-timing,
1 unstable-sync, 1 fetch-failed, 9 skipped, 14 crashed (job.py fell over
on an empty timing.json after the 30-minute kill). 345 videos.
Causes found and fixed in the harness:
- Submodule with an SSH URL hung `git submodule update` for 10 minutes
  (raybox-zero on four shuttles). Now rewritten to HTTPS.
- 15 projects instantiate sky130 cells in RTL (latches, clock gates,
  buffers: toivoh, MichaelBell, mole99, rebelmike, znah). The IHP
  re-hardens list a `sky130_polyfill.v` the project repo never had.
  Both are covered by Tiny Tapeout's polyfill (410 cells), now in
  `ttvga/harness/cells/` and passed to Verilator as a `-v` library file.
- The wall-clock limit used SIGKILL, losing the clip. tb.cpp now stops
  on SIGTERM, closes ffmpeg and writes timing.json with status
  sim-timeout; job.py gives it two minutes. Slow designs (toivoh demos,
  bouncy capsule, faaaa, galton, array_mult) get partial clips.
Still open after the fixes (for the diagnosis phase):
- Ring oscillators instantiate IHP/GF cells (3 projects): no models, and
  a ring oscillator is not meaningfully simulatable anyway.
- rejunity atari2600 uses generated ROM macros (`rom_2600_*`), cartrip a
  GDS-only nameplate macro, pixel_processor is VHDL (GHDL/yosys could
  convert), prime_quine trips a Verilator parse bug on `~&`.
- 20 blank: rle_vga (needs QSPI flash contents), pio_ram_emu (needs the
  RP2040 RAM emulator), tinygpu, mandelbrot, snake, vga_ca ... mostly
  external memory or input. 13 no-sync: crispy_vga, htfab vga_tester,
  photo_frame, spacewar, spi_mem: likely inputs or external hardware.
- 7 bad-timing: tomkeddie_a on six shuttles (vsync period looked shorter
  than two lines: check what the design puts on the vsync pin) and
  nitelich_conway.
- One repo is gone (alex-segura/tt06-pong).
Re-run of the 46 affected projects started 05:57 UTC. In parallel, the 19
no-sync/bad-timing projects were re-run with the new input-bit probe
(calibration-only run per single ui_in bit; first bit with sync wins,
recorded as `auto_ui_in`). Early probe results: photo_frame, vga_tester
and spi_mem stay no-sync (external hardware or serial commands needed).
Other notes:
- "static" now means exactly one distinct frame: Nyan cat alternates two
  frames and was wrongly called static. 71 static remain, mostly games
  waiting for a player (dino, snake, flappy, pong, 2048, maze, missile
  command, spacewar, gamepad demo) plus real still images (colour bars,
  pride flag, cbtest). These are the "needs-stimulus" set for the gamepad
  emulation and the diagnosis phase.
- Re-hardened projects renamed on the shuttle (tt_um_toivoh_demo_tt08/
  tt10 on ttihp25a) declare the original module name; job.py now falls
  back to the single tt_um_ module found in the sources. tt10 builds and
  syncs; tt08 still lacks `np_latch_registers`, a file the re-harden repo
  added (source list differs from the project repo at that commit).

After the polyfill re-run and the input probe (all 440 attempted):
288 ok, 71 static, 24 partial, 20 blank, 13 build-failed, 12 no-sync,
9 skipped, 1 each fetch-failed / bad-timing / unstable-sync. 383 videos.
- The input probe found the tennis game's pin-mapping select on all six
  shuttles (ui[7] high = Tiny VGA, low = Digilent, which puts sync on
  uio). Recorded as explicit overrides.
- The decoder now keeps the horizontal crop from a matching mode when the
  frame has a non-standard number of lines (tennis: 799-clock lines, 506
  lines), instead of falling back to a stretched raw crop.
- 24 projects are simply slow (0.24 to 3 Mclk/s: the toivoh demos, bouncy
  capsule, mandelbrot, galton, array_mult). They now get a partial clip
  instead of nothing; re-running with a 3 hour limit to finish them.
- Submodule fetch still hung with an insteadOf rewrite, so .gitmodules is
  rewritten to HTTPS directly (raybox-zero on four shuttles).
- `tt-vga stimulus` derives input scripts from the pin names the authors
  wrote in info.yaml: 55 overrides for static/blank/no-sync projects (16
  gamepad, the rest one pin at a time). Interface pins (video in, SPI,
  memory, config) are deliberately left alone. Re-running all 103.
- The Claude CLI hit its session limit during diagnosis (resets 16:10
  Adelaide). Two empty answers were removed from the results. Diagnosis
  so far: 3 real answers, $0.76 total, both causes correct.

QSPI Pmod model written (`ttvga/harness/qspi.h`): one flash and two PSRAMs
answering reads and remembering writes on the bidirectional pins, with the
pin map read from each project's own pin names (35 projects). First test:
Achtung on ttsky26c went from 3571 black frames to a picture of two
growing curves, exactly what the game should draw, because it keeps its
framebuffer in PSRAM. Flash holds an RGB332 test pattern unless an
override supplies a file, so flash-backed projects (photo frame, RLE
video player) will show that pattern rather than their intended artwork.
Re-running all 35.

State after the stimulus, QSPI and clobber-repair batches: 341 ok, 32
static, 380 with videos of 440. The stimulus batch alone turned 38 of 103
into ok; the QSPI model fixed tiny_shader (4 shuttles), atari2600 (2),
asicle2 (3), achtung (2), oguz, raybox-zero.

Two lessons worth keeping:
- Running two batches over overlapping projects let two jobs share a work
  directory and delete each other's output ("model exited 0 without
  timing.json", 16 projects). Each job now takes an exclusive lock.
- `tt-vga collect` failed while jobs were running because rsync exits 24
  when a file disappears mid-copy. That code is now accepted.

The testbench now measures how much a clip moves: how many of the 64
possible colours appear, what fraction of pixels change per frame, and
what fraction ever change. A new verdict "barely-moving" separates a
design stuck on a few pixels from a real animation, which is what
"verify a useful video" needs. Everything measured before that change
lacks the numbers, so a full re-run of all 440 with the final harness
gives one consistent dataset.

Still blank and content-dependent: the RLE video player (4 shuttles),
TinyGPU (2), the 8-bit processor, sandsim, badGPU. They read artwork or
programs from flash that nobody has; the modelled flash holds a test
pattern. Supplying a real image per project is an override away
(`flash: image.bin`) but needs the project's own format.

The 24 slow designs all finished their full 60 s clips with a 3 hour
limit (39 to 104 minutes each): 21 ok, 2 blank (retro console), 1 static
(array multiplier). So the wall-clock limit, not the designs, was the
problem.

Final full re-run of all 440 started 2026-09-15 12:05 UTC (40 jobs,
3 hour limit, `--redo`) so every project is measured by the same
harness, including the motion statistics. If this log has no later
entry, check `tt-vga queue status --host big`, then collect, analyze,
report and commit.

Next:
- Collect the full re-run, report, commit, and pick the examples for the
  README from the best-scoring clips.
- Ask the owner about the automated diagnosis pass over what is left.
- Judge the stimulus results: did pressing buttons produce motion?
- Remaining build failures need per-project work: generated ROM macros
  (atari2600), GDS-only macros (cartrip), VHDL (pixel_processor), a
  Verilator parse bug on `~&` (prime_quine), PDK ring oscillators
  (vgaringosc, vga_trng: not meaningfully simulatable), and one file the
  IHP re-harden added (toivoh_demo_tt08).
- The QSPI flash/PSRAM group (rle_vga, photo_frame, tinygpu, sandsim,
  achtung, madech, spi_mem) needs a behavioural memory model in the
  testbench: a framebuffer in PSRAM is common, so this is the single
  biggest remaining unlock. Design it next.
- Then review verdict groups: no-sync and blank first (most likely
  wrong-inputs / wrong-clock), static (stimulus), build-failed (source
  layout, SystemVerilog, includes).
- Exercise the gamepad emulation on a gamepad game.

## 2026-09-15: research and design

Done:
- Researched the Tiny Tapeout "simulator": it is the VGA Playground
  (Verilator in WASM, browser only). Copied its conventions into the design
  (bit layout, reset sequence, polarity detection, source discovery).
- Counted targets from tinytapeout-project-search: 440 Tiny VGA matches on
  24 shuttles; 312 at ~25 MHz, 49 with no clock given, 79 at other rates;
  420 Verilog/SystemVerilog; 64 also match the Gamepad Pmod; 87 known
  working on silicon.
- Probed hosts. Only one host gives the orchestrator passwordless sudo, so
  only there can the dedicated user be created without help. One host has a
  changed SSH host key. Details deliberately not recorded here.
- Created github.com/mithro/tinytapeout-vga-videos with the standard settings
  (v0.0 tag, merge commits only, protected main, tag ruleset vXX.ZZZ).
- Wrote the design spec (`docs/superpowers/specs/2026-09-15-vga-videos-design.md`)
  and host setup notes (`docs/host-setup.md`).

Decisions from the owner:
- Keep this log, commit often; work may stop at any time.
- Phase 1 is RTL simulation with Verilator; gate-level is phase 2.
- Videos stay on the big simulation host for now; later data.wafer.space,
  possibly YouTube with title card and outro (not now).
- Run only under a dedicated unprivileged user on the hosts.
- MJPEG, native resolution; storage is not a concern.
- At most two sub-agents at once.

Answers from the owner (2026-09-15):
- Start on the largest host now; the dedicated user on the other three
  hosts is to be requested from the Claude Code session that owns the
  hetzner-ansible repository (on the owner's desktop), not created by hand.
- The changed host key on one host was expected; accepted.
- A new dedicated key pair (`~/.ssh/ttvga_ed25519` on the laptop) is used
  for the `ttvga` user. Never committed.
- AI diagnosis may be used ad hoc while developing and debugging, but the
  fully automated diagnosis of all failures must NOT be started without
  asking and discussing first; it is one of the last things to do.
- Review images (poster, contact sheet) stay on the simulation host for
  now. Commit only a few as documentation examples. A GitHub Pages gallery
  may come later.
- Static output is "successful but potentially needs more work": report it
  as a success, then explore whether it is static by design or needs more
  stimulus.
- Defaults chosen by me, not asked: 30 minute wall-clock limit per
  simulation, MJPEG `-q:v 2` in AVI, repo settings as project-search.

Next:
- Get answers to the open questions.
- Scaffold the package: `targets`, `harness/tb.cpp`, `decode`, `encode`,
  `remote`, `queue`, tests.
- Pilot on 5 projects on one host, measure cycles/s, tune the decoder.
