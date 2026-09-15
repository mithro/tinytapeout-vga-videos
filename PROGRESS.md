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

Next:
- Read the pilot results (`tt-vga collect`, `analyze`, `report`), commit
  `docs/status.md`, copy one poster and contact sheet into `docs/examples/`.
- Fix whatever the pilot shows, then run all 440 with 40 jobs.
- Add the Gamepad Pmod emulator and the input-script expansion in job.py.
- Write `tt-vga diagnose` (ad hoc use only until the owner agrees to a
  full automated pass).

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
