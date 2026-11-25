# Raw traces in the pipeline: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every simulation keep a raw pin trace and derive its frames, hashes, PNGs and pages from that trace through vgacap, cheaply enough to sit beside the simulation, then re-run all 408 projects and publish the new data so other tooling (the FPGA and handheld harnesses) can compare against it properly.

**Architecture:**
- `tb.cpp` records every pin at both halves of every clock through vgacap's inline trace writer (`vgacap_trace_push`), into a zstd seekable trace in the job's scratch directory on the root NVMe volume.
- After the simulation, the job runs vgacap's `vgacap-sample` once over the trace (centre-v1 always, tb-v1 only on request), reads its PNG pipe, writes PNGs and pages, and moves the finished project directory into the published tree on the bulk volume with one `renameat2(RENAME_EXCHANGE)`.
- The same derive step runs without simulating (`job.py --rederive`); `tt-vga trace|sample|frames` wrap the vgacap tools and add Python frame tools. `collect` brings each sampler's `frames.txt` (and the tb-v1 FNV file) into git.
- Rollout: an 11-project pilot that measures the budget, an owner report whose recommended options are taken as rulings, the upload fix, then the full opt-in tb-v1 re-run of all 408, the check against the committed FNV files, and publishing.

**Tech Stack:** C++17 (`tb.cpp`, Verilator), C99 (`tracetool.c`), vgacap (pinned commit; `vgacap_trace`, `vgacap_sample`, `vgacap-sample`, `vgacap-export`), uv-managed CPython 3.14 on the host (standard library only, `compression.zstd`, `zlib`, `ctypes`), Python 3.14 locally via uv with pytest, systemd user scopes, rsync.

**Spec:** `docs/superpowers/specs/2026-11-24-raw-frames-and-hash-methods-design.md` (revision 17 as amended at 97e74b1). Also binding:
- vgacap format note `tt-vga-capture/docs/design/2026-11-25-format-v2-runs.md` (branch `m10-format-note`): `RUNS`, skip-by-length, boards later.
- vgacap rulings ledger `tt-vga-capture/.worktrees/m10-plan/.superpowers/sdd/2026-11-24-m10-simulation-traces/progress.md`, Rulings A-W (U: `sampler_status`; S: `bad-window` is an error exit of `vgacap-sample`; W: centre-v1 only by default).
- vgacap's own format docs at the pinned commit: `docs/trace-format.md`, `docs/frames-format.md`. They are authoritative for every byte of the trace, `frames.txt` and hash files; this plan never restates them.

## Global Constraints

Host and process rules (every task inherits them):
- Never `2>/dev/null` (a hook blocks it). Long or noisy commands write to a log under the worktree's `tmp/` (`cmd >> tmp/<name>.log 2>&1`), then grep or tail the log.
- Never `/tmp`. Temporary files go under the repository's `tmp/` (ignored). pytest runs with `--basetemp=tmp/pytest` (set in `pyproject.toml`, Task 2). On the host, temporary files go under `~/ttvga/work/`.
- Python through uv only (`uv run ...`), never `python -c`; scripts are files.
- Small commits, each pushed at once over SSH to `git@github.com:mithro/tinytapeout-vga-videos.git`. Each task runs in its own worktree `.worktrees/<task-branch>` on its own branch, reviewed independently before it merges to `main`.
- Commit trailer, on every commit:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01M4cwEsPm9kJ96LQeYKwqhK`.
- ISO dates (`2026-11-26`) in files, logs and commit messages.
- Long runs report progress with an ETA (remaining time and finish clock time) on the CLAUDE.md cadence: every 60 s under 10 minutes, every 5 minutes under 4 hours, every 15 minutes beyond. A background Monitor reads the job's log file (never a live pipe) and computes the ETA from observed throughput.
- Load average around 90 on this 88-thread host is normal; judge load as load/88 plus `ps -eo pcpu --sort=-pcpu`.
- The repository never names a host or a host path. Hosts come from `--host`; host paths come from `~/ttvga/host.toml` on the host (`frames_root`, `staging_dir`, `min_free_root_gb`).
- Third-party Verilog is built and run only as the dedicated unprivileged `ttvga` user on the host (the existing sandbox: `FORBIDDEN_USERS` in `ttvga/remote.py`), and from Task 10 on, each job inside a `systemd-run --user --scope` with `MemoryMax`, `CPUQuota` and `TasksMax` set. Locally, only this repository's own test designs (`tests/sim/designs/`) are simulated.
- The queue uses a small job count: 24 for the full re-run unless the pilot (Task 19) rules otherwise.

Pipeline rules from the spec and the owner:
- `tb-v1` is legacy and runs only on request: `job.py --tb-v1` (and `tt-vga queue start --tb-v1`). Without it the job runs centre-v1 only, writes no FNV file, and records `tb_v1_check: off`. The step 4 re-run is an explicit `--tb-v1` run.
- Clock numbering is the spec's: clock 0 is the first reset clock; clock `c` is samples `2c` (clk low) and `2c + 1` (clk high); `--from/--to` are clocks, from inclusive, to exclusive.
- `clock_hz` is an integer in hertz everywhere. `tb.cpp` refuses a non-integer `--clock-hz` or one above 4,294,967,295 when `--trace` is given (exit 2).
- Every file written for the published tree is written with umask 022 (files 0644, directories 0755).
- The host harness (`ttvga/harness/`) is standard-library only and runs under the pinned uv Python 3.14.
- vgacap is the one shared leaf dependency (owner, 2026-11-24): its tools and libraries are used, never copied. Small readers of its file formats (frames.txt, hash files) may be written here; the sibling harness repositories are never imported.
- vgacap pin: `ttvga/tools.toml [vgacap]` names a commit SHA of the M10 stack (`m10-export`, or `m10-perf` if it has landed with the same interfaces), chosen when Task 1 starts, and moved to vgacap `main` by Task 18 once PRs #14-#22 have merged. vgacap PRs #1-#13 are expected on `main` early in execution.
- Published file names: `<stem>` is `encode.stem_for(shuttle, macro)` (`<shuttle>_<macro>`). Trace: `<stem>_trace.vgch.zst`. Store: `<stem>_<sampler>_frames.rgb6.zst` (written by `vgacap-sample --name <stem>`).

## Review Focus

1. **A model killed outright (SIGKILL after the grace period) mid-block.** The job samples the trace's complete blocks with status `truncated`, keeps the frames, publishes them, then reports the error; it never publishes nothing and never leaves the scratch directory behind. Test: Task 9 `test_job_killed_model_samples_truncated_trace`.
2. **A project re-run while the upload or a viewer reads its published directory.** The swap is one `renameat2(RENAME_EXCHANGE)`; at no instant is the project half-copied, and the old directory is deleted only after the exchange. Test: Task 6 `test_swap_never_exposes_partial_directory`.
3. **A probe run (no picture with default inputs, a probe finds `ui_in`).** Probe runs write no trace; the first full run's trace is deleted and only the kept run's trace is published. Test: Task 9 `test_job_probe_keeps_only_the_rerun_trace`.
4. **`collect` while a job is running on the host.** The running job's scratch directory holds files named `frames.txt`; they are never pulled into git, and stale `frames/` files are removed only for projects whose host work directory has `frames/`. Test: Task 11 `test_collect_filter_ignores_scratch_and_keeps_unrerun_projects`.
5. **A `centre_window` override that does not fit (`bad-window`).** The job records the error naming the override, still writes centre-v1's files with `frames: 0`, and does not publish a project directory that claims frames it does not have. Test: Task 8 `test_derive_bad_window_is_an_error`.

---

## File structure

| file | responsibility |
| --- | --- |
| `ttvga/tools.toml` (modify) | `[uv]` tarball, `[python]` version, `[vgacap]` git URL + commit |
| `ttvga/remote.py` (modify) | bootstrap (uv, Python, vgacap build, tracetool), host-check, pinned-Python script runs, `collect` of `frames/`, queue flags |
| `ttvga/devtools.py` (new) | `tt-vga dev-tools`: the same pinned oss-cad-suite and vgacap built under `tmp/dev-tools/` for local tests and tools |
| `ttvga/harness/tb.cpp` (modify) | `--trace`, `--meta`, the inline push, META(open/close) on every exit, `tb_frame_hashes.txt` |
| `ttvga/harness/tracetool.c` (new) | `tracetool info|slice|uohash`: small C over vgacap's trace reader and writer |
| `ttvga/harness/hostconf.py` (new) | read `~/ttvga/host.toml` |
| `ttvga/harness/framesfile.py` (new) | minimal reader of vgacap's `frames.txt` and hash files (header dict, distinct SHA list, runs) |
| `ttvga/harness/pngio.py` (new) | indexed 64-colour PNG write and read with `zlib` |
| `ttvga/harness/pages.py` (new) | per-sampler `index.html` |
| `ttvga/harness/derive.py` (new) | run `vgacap-sample` + PNG pipe + `tracetool uohash` + tb-v1 check into a scratch output directory |
| `ttvga/harness/publish.py` (new) | staging copy (`rsync -aH`), exchange, stale removal, `changed.log` |
| `ttvga/harness/job.py`, `runqueue.py`, `verify.py` (modify) | the job flow, `--rederive`, `--tb-v1`, free-space wait, scopes, server stale listing |
| `ttvga/traces.py`, `ttvga/frames.py` (new) | `tt-vga trace ...`, `tt-vga sample`, `tt-vga frames ...` |
| `ttvga/targets.py`, `overrides.py`, `index.py`, `report.py` (modify) | `data/extra-targets.json`, `src_dir`, `centre_window`, `testpatterns` left out, FPGA links |
| `ttvga/framehashes.py`, `tests/test_framehashes.py` (delete) | replaced by `frames/` |
| `scripts/convert_frame_hashes.py` (new, one-off) | move and re-head the 408 FNV files |
| `scripts/export_tbv1_vectors.py` (new) | vgacap Task 18's vectors |
| `scripts/pilot_measure.py` (new) | step 2 measurements |
| `data/extra-targets.json`, `overrides/testpatterns/*.yaml` (new) | the calibration designs |
| `tests/sim/` (new) | Verilog test designs and the Verilator tests (`-m sim`) |
| `docs/consumers.md` (new), `docs/host-setup.md`, `README.md`, `PROGRESS.md` (modify) | the consumer note and the rewritten docs |

---

## Phase 1: tools

### Task 1: pinned uv, Python 3.14 and vgacap on the host

**Files:**
- Modify: `ttvga/tools.toml`, `ttvga/remote.py`, `pyproject.toml` (`requires-python = ">=3.14"`), `uv.lock`.
- Test: `tests/test_remote_bootstrap.py`.

**Interfaces:**
- Produces:
  - `tools.toml`: `[uv]` (`version`, `url` of the astral-sh/uv release tarball for x86_64-unknown-linux-gnu, `dir = "uv"`, `strip = 1`, `check = "uv/uv"`); `[python] version = "3.14.7"`; `[vgacap] git = "https://github.com/mithro/vgacap"`, `commit = "<40-hex SHA>"`.
  - `remote.tarball_tools(tools: dict) -> dict` (the entries with a `url`; `[python]` and `[vgacap]` are skipped by the tarball loop).
  - `remote.bootstrap_script(tools: dict) -> str`: after the tarball loop, `uv python install <version>`, then a clone of vgacap into `~/ttvga/tools/vgacap-src` at the pinned commit (`git fetch --depth 1 origin <commit>` + checkout), `cmake -S vgacap-src -B vgacap-build -DCMAKE_BUILD_TYPE=Release` and `cmake --build vgacap-build -j 8 --target vgacap-sample vgacap-export vgacap-dump vgacap_trace vgacap_sample`, then `tracetool` (Task 4) built with `cc -O2` against that build. A file `vgacap-build/PINNED` holds the commit; a different pin rebuilds.
  - `remote.host_python(tools) -> str`: `~/ttvga/tools/uv/uv run --no-project --python <version> python`; every host script (`runqueue.py`, `job.py`, `verify.py`, `rerender.py`) starts through it. The two one-line JSON reads (`host-check` queue line, `queue stop` PID read) may stay on `python3`.
  - `host-check` also prints `cmake --version` (MISSING if absent), the vgacap pin built, the Python version, and `loginctl show-user ttvga -p Linger` (Linger=yes is needed by Task 10).
  - `push_harness` also writes `harness/HARNESS_VERSION` holding `git describe --always --dirty` of this repository, so every result names its harness (Task 3 puts it in META).

- [ ] **Step 1: Choose the vgacap commit.** `git -C ~/github/TinyTapeout/vgacap log --oneline -1 m10-perf m10-export main`; take the tip of `m10-perf` if its branch says its interfaces are unchanged and its tests pass (`ctest` log in its worktree), else `m10-export`. Record the SHA and why in `tools.toml` as a comment.
- [ ] **Step 2: Write the failing tests** in `tests/test_remote_bootstrap.py`:
  - `test_tarball_loop_skips_python_and_vgacap`: `tarball_tools(tomllib.loads(TOOLS_TOML.read_text()))` has keys `{"oss-cad-suite", "ffmpeg", "uv"}`.
  - `test_bootstrap_installs_python_and_builds_vgacap_at_the_pin`: the script contains `uv python install 3.14.7`, the pinned commit, `-DCMAKE_BUILD_TYPE=Release` and `PINNED`.
  - `test_host_scripts_run_under_the_pinned_python`: the queue start command string built by `queue()` (factor it into `queue_command(args, host, tools) -> str`) starts with `host_python(tools)`.
  - `test_vgacap_commit_is_a_full_sha`: matches `^[0-9a-f]{40}$`.
- [ ] **Step 3: Run them:** `uv run pytest tests/test_remote_bootstrap.py -v >> tmp/t1.log 2>&1`; expect 4 failures.
- [ ] **Step 4: Implement** the functions above in `ttvga/remote.py`; `requires-python = ">=3.14"`, then `uv lock`.
- [ ] **Step 5: Run the whole suite:** `uv run pytest -v >> tmp/t1.log 2>&1`; all pass.
- [ ] **Step 6: Run on the host:** `uv run tt-vga bootstrap --host big >> tmp/t1-bootstrap.log 2>&1`, then `uv run tt-vga host-check --host big >> tmp/t1-bootstrap.log 2>&1`. Expected: `vgacap-sample` built, Python 3.14.7, cmake found. Linger may say `no` until Task 10.
- [ ] **Step 7: Commit and push.**

### Task 2: local dev tools and the `sim` test marker

**Files:**
- Create: `ttvga/devtools.py`, `tests/conftest.py`, `tests/sim/__init__.py`.
- Modify: `ttvga/cli.py`, `pyproject.toml` (`[tool.pytest.ini_options] addopts = "--basetemp=tmp/pytest"`, `markers = ["sim: needs tt-vga dev-tools (Verilator and vgacap)"]`).
- Test: `tests/test_devtools.py`.

**Interfaces:**
- Produces:
  - `tt-vga dev-tools [--root tmp/dev-tools]`: installs the pinned oss-cad-suite tarball (`tools.toml`) and clones and builds vgacap at the pin, as Task 1's host script does, plus `tracetool` once Task 4 exists. Idempotent (the `PINNED` file).
  - `ttvga.devtools.paths(root: Path = DEFAULT_ROOT) -> DevTools`, a dataclass with `verilator`, `fst2vcd`, `vgacap_build` (dir), `vgacap_src` (dir), `vgacap_sample`, `vgacap_export`, `vgacap_dump`, `tracetool` (all `Path`). `TTVGA_DEV_TOOLS` overrides the root.
  - `tests/conftest.py`: fixture `dev_tools() -> DevTools`. Tests marked `sim` use it; when the tools are missing it **fails** with "run `uv run tt-vga dev-tools` first" (never skips), and `uv run pytest` without `-m sim` deselects them (`addopts` gets `-m "not sim"`; sim runs use `-m sim`).

- [ ] **Step 1: Write the failing tests:** `test_paths_follow_the_pin` (paths under the given root; `vgacap_sample == root/"vgacap-build"/"vgacap-sample"`), `test_pytest_basetemp_is_in_tmp` (reads `pyproject.toml`: `--basetemp=tmp/pytest`).
- [ ] **Step 2: Run them; expect failures.**
- [ ] **Step 3: Implement**, sharing the install and build commands with Task 1 through one function `remote.vgacap_build_commands(src: str, build: str, commit: str) -> list[str]` so host and local builds cannot drift.
- [ ] **Step 4:** `uv run tt-vga dev-tools >> tmp/t2.log 2>&1`; then `uv run pytest -v >> tmp/t2.log 2>&1`; all pass.
- [ ] **Step 5: Commit and push.**

## Phase 2: recording

### Task 3: `tb.cpp` writes the trace

**Files:**
- Modify: `ttvga/harness/tb.cpp`.
- Create: `tests/sim/designs/` (Verilog, Apache-2.0 headers): `bars640.v` (640x480@60, cpp 1, 8 bars whose order rotates each frame), `bars_cpp2.v` (the same, one pixel per 2 clocks, run at 50,350,000 Hz), `frac.v` (1,525-clock lines, cpp 1.90625, at 48,000,000 Hz), `nosync.v` (constant `uo_out`), `glitch.v` (`bars640` with a 1-clock vsync glitch inside the pulse of every 4th frame), `playground.v` (the VGA Playground's `hvsync_generator` timing, one pixel and one line off VESA), `uio_echo.v` (drives `uio_out = ui_in`, `uio_oe = 0xF0`, to check input and bidir bits). All have a top `tt_um_test_<name>` with the Tiny Tapeout ports.
- Create: `tests/sim/build.py` (`build_model(design: str, dev: DevTools, out: Path) -> Path`, the Verilator command of `job.build` with the flags of Task 9's `vgacap_link_flags`), `tests/sim/test_tb_trace.py`.

**Interfaces:**
- Consumes: vgacap `trace.h` (`vgacap_trace_create`, `vgacap_trace_push`, `vgacap_trace_finish`), `stream.h` (`vgacap_header_init_v2`).
- Produces (the contract Task 9 calls):
  - New options: `--trace PATH` (no trace when absent) and `--meta KEY=VALUE` (repeatable; the job passes `project`, `override`, `simulator`, `harness`). `tb.cpp` itself adds `meta=open`, `calib_seconds` and `seconds` (the argument strings exactly as given), `layout=tt-um-43`. A bad key or a value with a newline exits 2.
  - Header: `vgacap_header_init_v2(&h, 43, 2, 42, 0)`, `mode = 2` (event), `clock_hz` = the integer `--clock-hz`. zstd level 1 (the constant `kTraceZstdLevel`, which the pilot may change).
  - One `push(bits)` after the clk-low `eval()` of each tick (clk 0) and one after the clk-high `eval()` and, with QSPI, after the response re-eval (clk 1): `uo_out | uio_out<<8 | uio_oe<<16 | ui_in<<24 | uio_in<<32 | rst_n<<40 | ena<<41 | clk<<42`, the values Verilator's ports hold at that moment. A push returning -1 sets `g_stop` and the run ends with exit 4 and the writer's message on stderr.
  - META(close) on every path that writes timing.json: `capture_after_clock` (tb's `clock` when calibration ended), `status` (`ok`, `sim-timeout`, `unstable-sync`, `no-sync`, `bad-timing`, the value written to timing.json), `frames` (tb's `frames`, 0 on the fail paths). SIGTERM reaches the normal path and so finishes the trace.
  - The frame hash list leaves timing.json and goes to `<out>/tb_frame_hashes.txt`, one 16-digit lowercase hex per line, frame 0 first, written on every path that writes timing.json (empty on fail paths). The comment at the FNV constant names `frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` instead of `framehashes.py`/`frame_hashes.txt`.
  - Nothing else in the decoding, the clips or timing.json changes.

- [ ] **Step 1: Write the failing tests** in `tests/sim/test_tb_trace.py` (all `@pytest.mark.sim`; each builds its design once per session into `tmp/pytest/...` and runs with `--seconds 0.2 --calib-seconds 0.1 --no-audio --quiet --ffmpeg true`; `uio_echo` also `--ui-in 0x5a`):
  - `test_trace_pins_match_the_design`: the trace of `uio_echo`, decompressed with `zstd -d` and read by vgacap's Python stream reader (`python/vgacap/stream.py` at the pin, imported by a helper `tests/sim/vgch.py` that puts `dev_tools.vgacap_src / "python"` on `sys.path`), shows samples 0-19 with `rst_n = 0`, sample 20 onwards `rst_n = 1`, `ena = 1` everywhere, `ui_in = 0x5a`, `uio_out & 0xF0 == 0x50`, `uio_oe == 0xF0`, and the clock bit `n & 1`.
  - `test_trace_meta`: META(open) has `project=test/bars640`, `calib_seconds=0.1`, `seconds=0.2`, `layout=tt-um-43`, `harness=...` as passed; META(close) has `status=ok`, `frames` equal to timing.json's `frames`, `capture_after_clock` equal to timing.json's.
  - `test_trace_no_sync_is_closed`: `nosync` exits 3; the trace has META(close) `status=no-sync`, `frames=0`.
  - `test_trace_sigterm_is_closed`: `bars640` with `--seconds 30`, SIGTERM after 2 s: the decompressed stream ends with META(close) `status=sim-timeout`.
  - `test_tb_frame_hashes_moved`: timing.json has no `frame_hashes` key; `tb_frame_hashes.txt` has `frames` lines.
  - `test_trace_refuses_fractional_clock`: `--clock-hz 25175000.5 --trace x` exits 2 before simulating.
  - `test_no_trace_without_option`: without `--trace` no `.zst` file appears in the out directory.
- [ ] **Step 2: Run:** `uv run pytest -m sim tests/sim/test_tb_trace.py -v >> tmp/t3.log 2>&1`; expect failures.
- [ ] **Step 3: Implement** in `tb.cpp`. The push is the inline `vgacap_trace_push`; pack the 43 bits with no branches; nothing per sample beyond that.
- [ ] **Step 4: Run the tests again; all pass.** Also time `bars640` at `--seconds 2` with and without `--trace` (3 interleaved runs each, `/usr/bin/time -v` into the log) and note the ns/clock difference in the commit message; the budget is checked properly in Task 19.
- [ ] **Step 5: Commit and push.**

### Task 4: `tracetool` (info, slice, uohash)

**Files:**
- Create: `ttvga/harness/tracetool.c` (C99, `-Wall -Wextra -Werror`).
- Modify: `ttvga/remote.py` and `ttvga/devtools.py` (build it: `cc -std=c99 -O2 -I<vgacap-src>/include -I<vgacap-src>/third_party/sha256 tracetool.c <vgacap-build>/libvgacap_trace.a <vgacap-build>/libvgacap_stream.a <vgacap-build>/third_party/libvgacap_sha256.a <vgacap-build>/third_party/libvgacap_zstd.a -pthread -o tracetool`; the exact library paths are read from the build tree, not guessed).
- Test: `tests/sim/test_tracetool.py`.

**Interfaces:**
- Produces:
  - `tracetool info TRACE`: `key: value` lines: the header fields, `samples`, `clocks`, `blocks`, `table_rebuilt`, every META(open) and META(close) key prefixed `open.`/`close.` (`close.status: truncated` when absent), then for each port of the tt-um-43 layout `changes.<port>: <n>` (value changes, clk excluded).
  - `tracetool slice TRACE --from CLOCK --to CLOCK --out PATH`: a new trace of samples `[2*from, 2*to)`, renumbered from sample 0, META(open) copied with `slice_from_clock=<from>` and `slice_to_clock=<to>` added, META(close) `status=<original or truncated>`, `capture_after_clock=0`, `frames=0`. Exit 2 if the range is empty or past the end.
  - `tracetool uohash TRACE [--clocks N]` prints `uo_out_sha256_clocks: 0 <M>` and `uo_out_sha256: <64 hex>`: SHA-256 over byte `c` = `uo_out` of sample `2c + 1`, for clocks `0 <= c < M`, `M = min(N, clocks in trace)`, `N` default 33,554,432 (2^25). This is the trace-content hash the FPGA harness asked for: no sampler is involved, and its own convention (byte i = `uo_out` after rising edge i, rst_n low for clocks 0-9) is ours.
- [ ] **Step 1: Write the failing tests:** `test_info_on_killed_trace` (`bars640` with `--seconds 30 --trace`, SIGKILL after 3 s: `table_rebuilt: 1`, `close.status: truncated`, `blocks >= 1`; and a SIGTERMed run: `table_rebuilt: 0`, `close.status: sim-timeout`), `test_info_counts` (on `uio_echo`: `changes.ui_in: 0`, `changes.rst_n: 1`, `clocks == samples / 2`); `test_slice_round_trip` (slice `[1000, 2000)` of `bars640`: `info` says 2,000 samples; vgacap-export VCD of the slice equals the VCD of the same range of the original with times shifted by `time(2000)`, compared value-change by value-change in the test); `test_slice_refused_by_sample` (Task 8's `derive` and `tt-vga sample` refuse a trace with `open.slice_from_clock`; this test only checks the key is present); `test_uohash_matches_python` (a Python reference over `zstd -d` output of a short trace, clocks `M = 50,000`).
- [ ] **Step 2: Run; expect failures. Step 3: Implement** on `vgacap_trace_read_runs`. **Step 4: Run; pass.** **Step 5: Commit and push.**

### Task 5: tb-v1 against `tb.cpp`, and vgacap's Task 18 vectors

**Files:**
- Create: `tests/sim/test_tbv1_matches_tb.py`, `scripts/export_tbv1_vectors.py`.

**Interfaces:**
- Consumes: Task 3's designs and outputs; `vgacap-sample TRACE --out DIR --name PREFIX --sampler tb-v1`.
- Produces:
  - The spec's comparison test: for every design of Task 3, `vgacap-sample --sampler tb-v1` on the trace gives `tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` whose hash lines (after `frames: N`) equal `tb_frame_hashes.txt` line for line, and whose `frames`, `mode`, `width`, `height`, `capture_after_clock` equal timing.json's (`clocks_per_pixel` is compared as a float to timing.json's 4-decimal value within 5e-5).
  - `scripts/export_tbv1_vectors.py --out tmp/tbv1-vectors`: for the cases `bars640`, `bars_cpp2`, `frac`, `glitch`, `nosync`, `playground`, writes `tmp/tbv1-vectors/<case>/trace.vgch` (the trace decompressed whole by `zstd -d`: a plain VGCH v2 stream, which vgacap's reader accepts), `frames.txt` and `frame_hashes.fnv1a64-tb2026-rgb888.txt` (both from `vgacap-sample --sampler tb-v1` on that `trace.vgch`, after the test above proved the hash lines are `tb.cpp`'s), and `tmp/tbv1-vectors/MANIFEST.txt` (`<sha256>  <case>/<file>` lines, then `generator: tinytapeout-vga-videos <commit>`, `vgacap: <pin>`). Each `trace.vgch` is at most 1 MiB (the script fails otherwise; shorten `--seconds` for that case, never below 2 captured frames).
- [ ] **Step 1: Write the test; Step 2: run it** (`-m sim`). Expected: it passes. A difference is a tb-v1 port bug: stop, write the case to `tmp/tbv1-mismatch/` and report it to the controller, who sends it to the vgacap session; do not change `tb.cpp`.
- [ ] **Step 3: Write and run the export script** (`uv run scripts/export_tbv1_vectors.py --out tmp/tbv1-vectors >> tmp/t5.log 2>&1`).
- [ ] **Step 4: Commit and push** the test and the script (not the vectors).
- [ ] **Step 5: Hand off** (controller): a message to the vgacap session ("Tiny Tapeout board direct VGA capture") giving the absolute path of `tmp/tbv1-vectors/` in this task's worktree, the commit, and that vgacap Task 18 copies `<case>/{trace.vgch,frames.txt,frame_hashes.fnv1a64-tb2026-rgb888.txt}` to `vgacap/tests/vectors/tbv1/<case>/`; `MANIFEST.txt` gives the checksums.

## Phase 3: deriving and publishing

### Task 6: host config and the publishing primitives

**Files:**
- Create: `ttvga/harness/hostconf.py`, `ttvga/harness/publish.py`.
- Test: `tests/test_publish.py`.

**Interfaces:**
- Produces:
  - `hostconf.HostConfig(frames_root: Path, staging_dir: Path, min_free_root_gb: float)`; `hostconf.load(root: Path) -> HostConfig` reads `<root>/host.toml` (`tomllib`); missing file or key raises `hostconf.ConfigError` naming the key (no defaults for the two paths; `min_free_root_gb` defaults to 100.0 until Task 19 sets it). Also checks `frames_root` and `staging_dir` are on one filesystem (`st_dev`), else `ConfigError`.
  - `publish.exchange(a: Path, b: Path) -> bool`: `renameat2(AT_FDCWD, a, AT_FDCWD, b, RENAME_EXCHANGE)` through `ctypes.CDLL(None, use_errno=True)`; returns False only on `ENOSYS`/`EINVAL` (not supported), raises `OSError` otherwise.
  - `publish.install(scratch: Path, conf: HostConfig, shuttle: str, macro: str, log: Path) -> None`: `os.umask(0o022)`; `rsync -aH --delete scratch/ <staging>/<shuttle>_<macro>.new/`; then if `<frames_root>/<shuttle>/<macro>` exists, `exchange` it with the `.new` directory, else `os.rename`; then delete the old one (now at `.new`). If `exchange` is unsupported: rename old to `<staging>/<shuttle>_<macro>.old`, rename new into place, delete old. Appends `<ISO time> <shuttle>/<macro>` to `<staging_dir>/changed.log` (Task 20 reads it).
  - `publish.remove(conf, shuttle, macro, log) -> bool`: moves a stale published project into staging and deletes it; appends to `changed.log`; returns whether there was one.
- [ ] **Step 1: Write the failing tests** (all under `tmp/pytest`): `test_install_new_project`, `test_install_replaces_with_exchange` (old content gone, new content present, staging empty after), `test_install_keeps_hard_links` (two hard-linked PNGs in scratch have the same inode in the published copy), `test_install_fallback_two_renames` (monkeypatch `exchange` to return False), `test_swap_never_exposes_partial_directory` (a thread lists the published directory in a loop during 50 installs of a 200-file tree; every listing is the complete old set or the complete new set), `test_modes_are_0644_0755`, `test_remove_stale`, `test_load_requires_paths`, `test_load_refuses_two_filesystems` (monkeypatch `os.stat`).
- [ ] **Step 2: Run; expect failures. Step 3: Implement. Step 4: Run; pass. Step 5: Commit and push.**

### Task 7: PNGs, the frames reader and pages

**Files:**
- Create: `ttvga/harness/pngio.py`, `ttvga/harness/framesfile.py`, `ttvga/harness/pages.py`.
- Test: `tests/test_pngio.py`, `tests/test_framesfile.py`, `tests/test_pages.py`, `tests/fixtures/frames/` (a `frames.txt` and hash files written by `vgacap-sample` on Task 3's `bars640` and `glitch` traces, committed, with a sim test `test_fixtures_are_current` that regenerates and compares them).

**Interfaces:**
- Produces:
  - `pngio.PALETTE: bytes` (64 RGB entries, entry `i` = `((i>>4)&3)*85, ((i>>2)&3)*85, (i&3)*85`); `pngio.write_rgb6(path: Path, width: int, height: int, rgb6: bytes, level: int = 1) -> None` (8-bit indexed, `PLTE` of 64 entries, filter 0 rows, `zlib.compress(level)`); `pngio.read_rgb6(path) -> tuple[int, int, bytes]` (accepts only what `write_rgb6` writes: 8-bit indexed, 64-entry palette, equal to `PALETTE`; anything else raises `ValueError`).
  - `framesfile.read_frames(path) -> Frames`: `header: dict[str, str]` (every `key: value` line before `distinct:`, in order), `distinct: list[str]` (SHA-256 hex), `runs: list[Run]` with `Run(first: int, count: int, distinct: int | None, start_clock: int | None, missing: int | None)`; `Frames.frame(k) -> tuple[int | None, int | None, int | None]` (distinct, start clock, missing; `None` for a gap; start clock of frame `first + i` is `start_clock + i * frame_clocks`). `framesfile.read_hashes(path) -> Hashes` (`method`, `header`, `hashes: list[str | None]`). Malformed input raises `framesfile.FormatError` with the line number. It reads the format of vgacap's `docs/frames-format.md` and checks only what it needs (keys present, runs contiguous from 0 and covering `frames`).
  - `pages.write_sampler_page(dir: Path, frames: Frames, stem: str, sampler: str) -> None`: `dir/index.html` as the spec says (every captured frame with number, start clock and distinct number, linking `png/<n>.png`; a grid of the distinct PNGs with `loading="lazy"`; `#1x`/`#2x`/`#4x` views with CSS `:target` and `image-rendering: pixelated`; no scripts); gaps listed as `-`. The page is a run-length table for long runs (one row per run, not per frame), so a 3,600-frame project is a few KB when its content repeats.
- [ ] **Step 1: Write the failing tests:** `test_png_round_trip_is_byte_identical` (random rgb6, 640x480 and 1x1 and 1280x1024), `test_png_palette_index_is_rgb6`, `test_read_refuses_other_pngs`, `test_frames_reader_on_vgacap_output` (fixture: header keys in vgacap's order, `distinct_frames == len(distinct)`, frame `k` start clocks), `test_frames_reader_gap` (glitch fixture: a gap run reads as `None`), `test_hash_reader_dash_is_gap`, `test_page_has_no_script_and_links_every_distinct_png`, `test_page_rows_are_runs`.
- [ ] **Step 2-4: Run (fail), implement, run (pass). Step 5: Commit and push.**

### Task 8: the derive step

**Files:**
- Create: `ttvga/harness/derive.py`.
- Test: `tests/sim/test_derive.py`, `tests/test_derive_unit.py`.

**Interfaces:**
- Consumes: Tasks 4, 6, 7; `vgacap-sample` (its usage text at the pin: `TRACE --out DIR --name PREFIX [--sampler tb-v1] [--sampler centre-v1] [--centre-window DX,DY] [--store-level N] [--png-fd FD]`; exit 0/1/2; bad-window exits 1 after writing every file).
- Produces:
  - `derive.Tools(vgacap_sample: Path, tracetool: Path)`.
  - `derive.derive(trace: Path, out: Path, stem: str, *, tb_v1: bool, centre_window: tuple[int, int] | None, tools: Tools, log: Path, tb_hashes: Path | None) -> DeriveResult`. It:
    1. refuses a trace whose `tracetool info` has `open.slice_from_clock` (`DeriveError`);
    2. runs `vgacap-sample <trace> --out <out> --name <stem> --sampler centre-v1 [--sampler tb-v1] [--centre-window DX,DY] --png-fd <w>` with a pipe; a reader thread parses each record (`"<sampler> <distinct> <width> <height>\n"` + `w*h` bytes) and writes `<out>/<sampler>/png/<distinct:06d>.png`, hard-linking to an earlier PNG of the same `(width, height, sha256(rgb6))` instead of encoding again;
    3. writes `pages.write_sampler_page` for each sampler;
    4. runs `tracetool uohash`;
    5. when `tb_v1` and `tb_hashes` exist, compares `tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`'s hash lines with `tb_hashes`' lines: `tb_v1_check` = `match` or `mismatch`; `tb_v1` with `tb_hashes` None: `not-run`; not `tb_v1`: `off`.
  - `DeriveResult(samplers: dict[str, dict], uo_out_sha256: str, uo_out_sha256_clocks: tuple[int, int], tb_v1_check: str, error: str | None, cpu_seconds: float, pngs_written: int, pngs_linked: int)`; `samplers[s]` holds `sampler_status`, `frames`, `distinct_frames`, `mode`, `width`, `height`, `clocks_per_pixel` (strings, from frames.txt's header).
  - `error` is set (and the caller fails the job) for: `vgacap-sample` exit 1 or 2 (stderr's last line), `tb_v1_check == "mismatch"` (`"tb-v1 differs from tb.cpp at frame <k>"`), and bad-window (`"centre_window <dx>,<dy> does not fit: <vgacap-sample's reason>"`).
- [ ] **Step 1: Write the failing tests** (`-m sim` unless noted):
  - `test_derive_centre_only_by_default`: `bars640`: `out/centre-v1/{frames.txt, frame_hashes.sha256-rgb6.txt, <stem>_centre-v1_frames.rgb6.zst, index.html, png/000000.png ...}`; no `out/tb-v1`; `tb_v1_check == "off"`; one PNG per distinct frame, each `read_rgb6` equal to the store's bytes at `n * w * h` (decompressed with `compression.zstd`).
  - `test_derive_tb_v1_on_request_links_identical_pngs`: `tb_v1=True` on `bars640`: `tb_v1_check == "match"`; every tb-v1 PNG whose frame equals a centre-v1 frame is a hard link (`st_ino` equal); `pngs_linked > 0`.
  - `test_derive_tb_v1_mismatch_fails`: a doctored `tb_hashes` with one line changed: `tb_v1_check == "mismatch"`, `error` names the frame.
  - `test_derive_no_sync_writes_empty_files`: `nosync`: `sampler_status == "no-sync"`, `frames == "0"`, no PNGs, no error.
  - `test_derive_truncated_trace`: a SIGKILLed trace made as in Task 4's `test_info_on_killed_trace`: frames.txt `status: truncated`, frames > 0.
  - `test_derive_bad_window_is_an_error`: `bars640` with `centre_window=(400, 0)`: `error` starts with `centre_window 400,0 does not fit`, `centre-v1/frames.txt` has `frames: 0`, and the result says so.
  - `test_derive_refuses_a_slice` (unit, with a stub `tracetool`).
- [ ] **Step 2-4: Run (fail), implement, run (pass). Step 5: Commit and push.**

### Task 9: `job.py`: trace, derive, publish

**Files:**
- Modify: `ttvga/harness/job.py`.
- Test: `tests/sim/test_job.py` (runs `job.py` locally against a local `--root` under `tmp/pytest`, with a local `targets.json` whose repos are `file://` git repositories made from `tests/sim/designs/`, a `host.toml` pointing at two directories under `tmp/pytest`, and `--videos` under `tmp/pytest`), `tests/test_job_unit.py`.

**Interfaces:**
- Consumes: Tasks 3, 6, 7, 8.
- Produces:
  - `job.vgacap_link_flags(vgacap_src: Path, vgacap_build: Path) -> list[str]`: `-CFLAGS -I<src>/include` and `-LDFLAGS "<trace lib> <stream lib> <zstd lib> -pthread"`, added to `build()`'s Verilator command.
  - `build()` and `simulate()` use `target.get("src_dir", "src")` instead of `repo_dir / "src"` (both places: sources and the model's cwd).
  - `model_cmd(..., trace: Path | None)` adds `--trace <trace>` and `--meta project=<id>`, `--meta override=<shuttle>/<macro>.json sha256:<12 hex of the compiled override file, or none>`, `--meta simulator=<verilator --version first line>`, `--meta harness=<HARNESS_VERSION>`. Probe runs pass no trace. After a successful probe, the first run's trace is deleted before the re-run writes its own.
  - The trace goes to `work/scratch/<stem>_trace.vgch.zst`; `work/scratch/` is the project's output directory (published layout: the trace plus `<sampler>/...`), created fresh by each job and deleted at the end on every path (success and failure).
  - New stage `derive` between `simulate` and `encode` (`STAGES = ("fetch", "build", "simulate", "derive", "encode")`), and `publish` after `encode`. Stage rules:
    - no timing.json because the model was killed (`rc == 124` or the file missing/empty) but a trace exists: run `derive` (status `truncated` comes from the trace), publish, then return the original error (`"wall-clock limit"` etc.);
    - no-sync/bad-timing: derive (samplers write `frames: 0` files), publish the trace and those files, skip encode (as today);
    - input-probe runs, build-failed, fetch-failed, skipped: no trace, nothing published; if the project has a published directory, `publish.remove` it.
  - `derive` writes `work/frames/<sampler>/frames.txt` and, with tb-v1, `work/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` (copies from scratch; the directory `work/frames/` is replaced whole each run).
  - `--grace SECONDS` (default 120, the existing SIGTERM-to-SIGKILL grace of the simulation run; tests lower it).
  - `--tb-v1` flag (default off). `result.json` gains: `tb_v1_check` (`match`, `not-run`, `off`; `mismatch` fails the job), `trace` = `{"file": "<stem>_trace.vgch.zst", "bytes": n, "blocks": n, "clocks": n, "uo_out_sha256": hex, "uo_out_sha256_clocks": [0, M]}`, `samplers` = Task 8's `samplers` dict, `timings.derive`, `timings.publish`, `derive_cpu_seconds`. `timing.frame_hashes_count` is no longer written.
  - The `testpatterns` pseudo-shuttle: derive yes; no `encode`, no `publish`, and its scratch output moves to `work/kept/` instead of being deleted (so the pilot can read it).
  - Everything written for the published tree under `os.umask(0o022)`.
- [ ] **Step 1: Write the failing tests:**
  - `test_job_publishes_trace_and_centre_v1`: a `bars640` target: the published project directory has the trace and `centre-v1/`; `work/frames/centre-v1/frames.txt` exists; `result.json` `tb_v1_check == "off"`, `trace.uo_out_sha256` 64 hex; scratch is gone.
  - `test_job_tb_v1_on_request`: with `--tb-v1`: `tb-v1/` published, `tb_v1_check == "match"`.
  - `test_job_probe_keeps_only_the_rerun_trace`: a design that syncs only with `ui_in = 0x04` (add `tests/sim/designs/needs_ui2.v`): `auto_ui_in == 4`, one trace published, its META(open) and `ui_in` bits show `0x04` from clock 0.
  - `test_job_killed_model_samples_truncated_trace`: `--timeout 3` on a long run with the grace shortened by a test-only `--grace 1` option: result `error == "wall-clock limit"`, published `centre-v1/frames.txt` says `status: truncated`.
  - `test_job_no_sync_publishes_trace_only`: `nosync`: trace and `frames: 0` files published, no clips.
  - `test_job_failure_removes_stale_output`: publish `bars640`, then break its source (`skip` override): the published directory is gone, `work/frames/` is gone.
  - `test_job_testpatterns_not_published` (unit with stubs).
  - `test_vgacap_link_flags` (unit).
- [ ] **Step 2-4: Run (fail), implement, run (pass):** `uv run pytest -m sim tests/sim/test_job.py -v >> tmp/t9.log 2>&1` and `uv run pytest -v >> tmp/t9.log 2>&1`.
- [ ] **Step 5: Commit and push.**

### Task 10: re-deriving, the queue and scopes

**Files:**
- Modify: `ttvga/harness/job.py`, `ttvga/harness/runqueue.py`, `ttvga/remote.py`.
- Test: `tests/sim/test_rederive.py`, `tests/test_runqueue.py`.

**Interfaces:**
- Produces:
  - `job.py --rederive`: no fetch, build or simulate; reads `<frames_root>/<shuttle>/<macro>/<stem>_trace.vgch.zst` (error `"no published trace"` if missing), copies it into scratch (hard link when on the same filesystem, else copy), runs `derive` with the current override's `centre_window` and `--tb-v1` as given, publishes, refreshes `work/frames/`, and updates `result.json` in place: `samplers`, `trace.uo_out_sha256*`, `tb_v1_check` (`not-run` when `--tb-v1`, since there is no `tb.cpp` list), `rederived_at` (ISO UTC), `timings.rederive`. Everything else in `result.json` is kept.
  - `runqueue.py`: `--rederive` (passes it on; selects projects whose `work/<s>/<m>/result.json` has a `trace`), `--tb-v1` (passes it on), and before starting each job waits while `shutil.disk_usage(root).free < min_free_root_gb * 1e9`, logging `waiting for free space: <n> GB free, need <m>` once a minute. Each job runs as `systemd-run --user --scope --quiet --collect --unit ttvga-job-<shuttle>-<macro> -p MemoryMax=<mem> -p CPUQuota=<cpu> -p TasksMax=64 -- <host python> job.py ...`; `--scope-memory` (default `6G`) and `--scope-cpu` (default `200%`: the simulation and the compressor thread). If `systemd-run --user` fails (no user manager, linger off) the queue exits at once with that error; it never falls back to running unconfined.
  - `tt-vga queue start --rederive --tb-v1 --scope-memory --scope-cpu` pass through; `--jobs` default stays from config.
  - Host setup (controller, with `tim`'s sudo, once): `sudo loginctl enable-linger ttvga`; check with `tt-vga host-check` (Linger=yes).
- [ ] **Step 1: Write the failing tests:** `test_rederive_reproduces_frames` (`-m sim`: job, then `--rederive`: every `frames.txt` and hash file byte-identical, `rederived_at` set); `test_rederive_applies_centre_window` (`-m sim`: override `centre_window: {dx: 1, dy: 0}` then rederive: `window_offset: 1 0`); `test_queue_waits_for_free_space` (monkeypatched `disk_usage`); `test_queue_job_command_is_a_scope` (the argv starts `systemd-run --user --scope` and has the three `-p` limits); `test_queue_refuses_without_user_manager` (monkeypatched `subprocess.run` returning 1 for a `systemd-run --user --scope true` preflight).
- [ ] **Step 2-4: Run (fail), implement, run (pass). Step 5: Commit and push.**

### Task 11: `collect`, and the end of `framehashes.py`

**Files:**
- Modify: `ttvga/remote.py` (`collect`).
- Delete: `ttvga/framehashes.py`, `tests/test_framehashes.py`.
- Test: `tests/test_collect.py`.

**Interfaces:**
- Produces:
  - `remote.collect_filter() -> list[str]`: rsync arguments that include `*/`, `result.json` at `<shuttle>/<macro>/result.json`, and `/*/*/frames/*/frames.txt` and `/*/*/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` anchored to the work root, excluding everything else (so `work/<s>/<m>/scratch/**` and `work/<s>/<m>/kept/**` never match), with `--prune-empty-dirs`.
  - `remote.host_rerun_projects(host) -> set[str]`: one `find ~/ttvga/work -mindepth 3 -maxdepth 3 -type d -name frames` over SSH, giving `<shuttle>/<macro>` ids.
  - `remote.remove_stale_frames(results: Path, rerun: set[str], present: dict[str, set[str]]) -> list[Path]`: for ids in `rerun` only, deletes local `frames/**` files that the host's `frames/` does not have (`present[id]` from an `rsync --list-only` of those paths, or from the `find` with `-type f` printed), returns what it removed. Projects not in `rerun` keep their converted `frames/tb-v1/` files.
  - No more `framehashes.export` call.
- [ ] **Step 1: Write the failing tests:** `test_collect_filter_ignores_scratch_and_keeps_unrerun_projects` (run the real `rsync` locally between two `tmp/pytest` trees with the filter: `scratch/centre-v1/frames.txt` is not copied, `frames/centre-v1/frames.txt` is; then `remove_stale_frames` with `rerun = {"a/x"}` removes `a/x/frames/tb-v1/...` when the host no longer has it and leaves `b/y/frames/tb-v1/...`), `test_collect_no_longer_imports_framehashes`.
- [ ] **Step 2-4: Run (fail), implement, run (pass). Step 5: Commit and push.**

### Task 12: extra targets, `src_dir`, `centre_window`, `testpatterns`

**Files:**
- Create: `data/extra-targets.json`, `overrides/testpatterns/tt_um_vgacal_{bars,grid,prbs,counter}.yaml`, `overrides/testpatterns/tt_um_vgacal_modes_{m0,m1,m2,m0_hneg,m0_vneg,m0_hvneg}.yaml`.
- Modify: `ttvga/targets.py`, `ttvga/overrides.py` (`"centre_window"` in `PLAIN_KEYS`, validated as `{dx: int, dy: int}`), `ttvga/index.py`, `ttvga/report.py`, `ttvga/analyze.py` if it lists shuttles.
- Test: `tests/test_targets.py`, `tests/test_overrides.py`, `tests/test_index.py` (extend).

**Interfaces:**
- Produces:
  - `data/extra-targets.json`: `{"targets": [...]}` in `data/targets.json`'s record format, shuttle `testpatterns`, `repo` `https://github.com/mithro/tt-vga-testpatterns`, `commit` its current `main` SHA (40 hex), `src_dir` `designs/<design>/src`, `top_module` the real design, `source_files` from each design's `info.yaml`, `clock_hz` 25,175,000, pinout as the design's `info.yaml`. Macros: the five designs, with `tt_um_vgacal_modes` replaced by its six pseudo-macros (`top_module tt_um_vgacal_modes`): `m0` (`ui_in` 0, 640x480@60), `m1` (1, 800x600@60), `m2` (2, 720x400@70), `m0_hneg` (4), `m0_vneg` (8), `m0_hvneg` (12).
  - `targets.write_targets` merges `extra-targets.json` (an `id` already present is an error).
  - `targets.PUBLISHED_EXCLUDED_SHUTTLES = ("testpatterns",)`: `index.py`, `report.py` and `analyze.py` skip those targets.
  - Each `overrides/testpatterns/<macro>.yaml` sets `ui_in` (and nothing else).
- [ ] **Step 1: Write the failing tests:** `test_extra_targets_merged`, `test_extra_target_duplicate_id_fails`, `test_centre_window_passes_through` (and `test_centre_window_rejects_non_int`), `test_index_and_report_leave_out_testpatterns`.
- [ ] **Step 2-4: Run (fail), implement, run (pass).** Then `uv run tt-vga targets >> tmp/t12.log 2>&1` and commit the regenerated `data/targets.json`.
- [ ] **Step 5: Commit and push.**

### Task 13: `tt-vga trace` and `tt-vga sample`

**Files:**
- Create: `ttvga/traces.py`. Modify: `ttvga/cli.py`.
- Test: `tests/sim/test_traces_cli.py`.

**Interfaces:**
- Consumes: `devtools.paths()`, Task 4, `vgacap-export` (usage at the pin: `TRACE --format fst|vcd --out FILE [--from CLOCK] [--to CLOCK] [--no-clk] [--frames FRAMES_TXT] [--scope NAME]`).
- Produces:
  - `tt-vga trace info TRACE` (prints `tracetool info`).
  - `tt-vga trace export TRACE --format fst|vcd --out FILE [--from C] [--to C] [--no-clk] [--sampler-frames FRAMES_TXT]` (thin wrapper; `--sampler-frames` is `vgacap-export --frames`; the `.gtkw` and `.sucl` files are vgacap's).
  - `tt-vga trace slice TRACE --from C --to C --out PATH`.
  - `tt-vga sample TRACE --out DIR [--sampler ID]... [--centre-window DX,DY] [--name PREFIX]`: runs Task 8's `derive` locally (PNGs and pages included), default prefix from META(open) `project` (`/` to `_`). For one project on the host the equivalent is `tt-vga queue start --rederive --only <id>` (said in `--help`).
- [ ] **Step 1: Write the failing tests:** `test_export_fst_equals_vcd` (`fst2vcd` of the FST equals the VCD's value changes on one frame of `bars640`), `test_sample_writes_both_on_request`, `test_slice_then_export`. **Step 2-4. Step 5: Commit and push.**

### Task 14: `tt-vga frames` to-png, from-png, hash, diff

**Files:**
- Create: `ttvga/frames.py` (subcommands registered in `cli.py`).
- Test: `tests/test_frames_cli.py`, `tests/sim/test_frames_hash.py`.

**Interfaces:**
- Produces:
  - `tt-vga frames to-png FRAMES_TXT --out DIR`: every distinct frame of the store named in `FRAMES_TXT` (same directory) to `DIR/<n:06d>.png`.
  - `tt-vga frames from-png DIR --frames FRAMES_TXT --out STORE`: PNGs back to the uncompressed store bytes, then zstd (`compression.zstd`, level 3); `test_round_trip` checks the decompressed bytes' SHA-256 equals `store_sha256`.
  - `tt-vga frames hash FRAMES_TXT --method ID --out FILE`: a hash file byte-identical to `vgacap-sample`'s for the same sampler (header copied from `frames.txt`'s values in vgacap's key order; the definition lines `ttvga.frames.DEFINITIONS[method]`, copied from vgacap `src/sample/hashes.c` at the pin). `sha256-rgb6` by `hashlib`; `fnv1a64-tb2026-rgb888` in pure Python over each distinct frame (slow, about 0.15 s a 640x480 frame; `--help` says so).
  - `ttvga.frames.load_frame(spec: str) -> tuple[int, int, bytes]`: `STORE:N` (distinct frame N), `STORE@F` (captured frame F via the `frames.txt` beside the store), or a PNG path.
  - `tt-vga frames diff A B --out DIR`: prints `differing_pixels`, `bbox: x0 y0 x1 y1` (exclusive end), `per_channel: r <n> g <n> b <n>`, and up to ten `<a> -> <b>: <count>` lines (rgb6 values, most common first, ties by value); writes `DIR/a.png`, `DIR/b.png`, `DIR/mask.png` (index 63 where different, 0 elsewhere). Different shapes: exit 1 with both shapes printed.
- [ ] **Step 1: Write the failing tests:** `test_to_png_from_png_round_trip`, `test_hash_matches_vgacap_sample` (`-m sim`, both methods, `bars640` with `--sampler tb-v1`), `test_hash_definitions_match_vgacap` (`-m sim`: the `# ` lines of a vgacap-written file equal `DEFINITIONS`), `test_diff_counts_and_bbox` (two constructed frames differing in a 3x2 block, one channel), `test_diff_shape_mismatch`, `test_load_frame_captured_vs_distinct`. **Step 2-4. Step 5: Commit and push.**

### Task 15: `tt-vga frames compare`

**Files:**
- Modify: `ttvga/frames.py`.
- Test: `tests/test_frames_compare.py`.

**Interfaces:**
- Produces: `ttvga.frames.compare(a: Path, b: Path) -> Comparison` and `tt-vga frames compare RUN_A RUN_B`. RUN is a `frames.txt` or a hash file of one method (two hash files must share a method; a `frames.txt` against a hash file compares the `frames.txt`'s distinct SHA-256 only against a `sha256-rgb6` file, else exit 2). Per-frame identity: SHA-256 (frames.txt) or the hash value; a gap (`-`) is "no data", never a mismatch.
  - `Comparison(first_mismatch: int | None, offset: int | None, offset_agrees_from: int | None, start_clock_deltas: dict[int, int] | None, frames_a: int, frames_b: int, gaps_a: int, gaps_b: int)`.
  - Algorithm: the first frame `k` where both have data and differ; then the constant offset `d`, `|d| <= 120`, smallest `|d|` first, then negative before positive, under which every frame `j >= k` with data in both `a[j]` and `b[j + d]` agrees and at least 10 such pairs exist; with two `frames.txt`, the histogram of start-clock differences over frames with data in both.
  - Output lines: `first_mismatch: <k|none>`, `offset: <d|none>`, `start_clock_delta: <delta> x<count>` (up to five), and with the stores present `diff:` + `frames diff` of the first mismatching pair (`STORE@k` against `STORE@k+d` or `@k`), and with the traces present (`<stem>_trace.vgch.zst` two levels up) `trace_range_a: --from <c> --to <c + frame_clocks>` and the same for b.
- [ ] **Step 1: Write the failing tests** on constructed files written with the Task 7 reader's inverse (a small test writer in the test module): `test_identical`, `test_shift_by_3` (b = a delayed by 3 frames: `offset 3`), `test_shift_negative`, `test_real_difference_no_offset`, `test_gaps_are_not_mismatches`, `test_start_clock_deltas`, `test_methods_must_match`. **Step 2-4. Step 5: Commit and push.**

### Task 16: `verify`, the FPGA room in the archive, and index links

**Files:**
- Modify: `ttvga/harness/verify.py`, `ttvga/remote.py` (`mirror`, `verify` args), `ttvga/index.py`.
- Test: `tests/test_verify_listing.py`, `tests/test_mirror.py`, `tests/test_index.py`.

**Interfaces:**
- Produces:
  - `verify.server_listing(base_url: str, path: str, fetch=urllib.request.urlopen) -> tuple[set[str], set[str]]` (directories, files) from the server's HTTPS autoindex HTML (`<a href="...">` entries, `../` ignored), and `verify.stale_on_server(local: Path, base_url: str, roots: list[str]) -> list[str]`: recursive walk of the server under `roots` listing every directory and file the local tree lacks, printed under `stale on server (remove by hand):`. Run by `tt-vga verify --server-stale URL` (URL given on the command line, not recorded). It never deletes.
  - `verify.FOREIGN = ("fpga/", "fpga-library.json")`: paths owned by the tt-harness-fpga-vga session (`<shuttle>/<macro>/fpga/` and the archive root's `fpga-library.json`, owner decision 2026-11-26). `stale_on_server` and every completeness check skip them; `tt-vga mirror` keeps never deleting (no `--delete`) and adds `--exclude /*/*/fpga/ --exclude /fpga-library.json` so a mirror never overwrites them; a test pins both.
  - `verify.py` (host) also checks every published frames project: trace present and non-empty, each sampler directory has `frames.txt`, `index.html`, its store and `png/` count equal to `distinct_frames`.
  - `tt-vga index --fpga-ids FILE`: optional; `FILE` lists `<shuttle>/<macro>` ids (one per line) that have an `fpga/` directory in the archive, made on the host by `tt-vga mirror --fpga-ids-out FILE` (`find <dest> -mindepth 3 -maxdepth 3 -type d -name fpga`, printed relative). Each listed project's row in `index.html` gets a link `FPGA bitstream` to `<shuttle>/<macro>/fpga/`. The library format is the FPGA session's and the owner's; nothing here reads `fpga-library.json`.
- [ ] **Step 1: Write the failing tests:** `test_server_listing_parses_autoindex` (a saved nginx autoindex HTML in `tests/fixtures/`), `test_stale_on_server_ignores_fpga`, `test_mirror_excludes_fpga_and_never_deletes`, `test_index_links_fpga_when_listed`, `test_verify_frames_completeness` (a `tmp/pytest` tree with one PNG missing fails). **Step 2-4. Step 5: Commit and push.**

### Task 17: the FNV files move, and the consumer note

**Files:**
- Create: `scripts/convert_frame_hashes.py`, `docs/consumers.md`.
- Move: `data/results/<shuttle>/<macro>/frame_hashes.txt` (408) to `data/results/<shuttle>/<macro>/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`.
- Modify: each `result.json` (drop `timing.frame_hashes_count` after the check), `README.md` (lines 82-92 rewritten), `PROGRESS.md` (new entry: `frame_hashes.txt` and `framehashes.py` are replaced; older entries stay).
- Test: `tests/test_convert_frame_hashes.py`.

**Interfaces:**
- Produces:
  - `convert(old: Path, result: dict) -> str`: the new file's text in vgacap's hash-file format: `hash_method: fnv1a64-tb2026-rgb888`, the four definition lines as `# ` lines (`frames.DEFINITIONS`), `hash_offset_basis: 0x14650fb0739d0383`, `id`, `status` (timing's), `sampler: tb-v1`, `sampler_status: ok`, `mode`, `width`, `height`, `clock_hz`, `clocks_per_pixel` (recomputed as `tb.cpp` does: `line_clocks / mode.line_px`, rounded to the integer when within 0.01, then written by the `vgacap_fmt_double` rule, implemented here as `fmt_double(v: float) -> str`: the first `"%.{p}g"`, p 1..17, that reads back exactly and has no exponent, else the first that reads back), `capture_after_clock`, `frames`, then the hash lines unchanged.
  - Asserts, per project, failing the script: hash lines byte-identical to the old file's; their number equals `result.json`'s `timing.frame_hashes_count`; `capture_after_clock` is a number (not `unknown`); `clocks_per_pixel` rounded to 4 decimals equals timing's.
  - `docs/consumers.md`: see Step 4.
- [ ] **Step 1: Write the failing tests:** `test_fmt_double` (`25175000.0 -> "25175000"`, `1.90625 -> "1.90625"`, `800/840 -> "0.9523809523809523"`, `1.0 -> "1"`), `test_convert_keeps_hash_lines`, `test_convert_refuses_count_mismatch`, `test_converted_header_parses_with_framesfile` (Task 7's reader). **Step 2-3: Run (fail), implement.**
- [ ] **Step 4: Write `docs/consumers.md`**, for tt-harness-fpga-vga and tt-harness-handheld-vga, with a link for every file and tool named. It states, each as a short table or list:
  - What to read and where: in git (`data/targets.json`, skipping `shuttle: testpatterns`; `data/results/<s>/<m>/result.json`: `verdict`, `override`, `auto_ui_in`, `qspi`, `trace`, `samplers`, `tb_v1_check`; `data/results/<s>/<m>/frames/<sampler>/frames.txt`; `.../frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`); on `https://data.wafer.space/big-storage/tinytapeout-vga-videos/` (the archive, owner decision 2026-11-26) the per-project trace, stores, every hash file, PNGs and pages; formats by link to vgacap's `docs/trace-format.md` and `docs/frames-format.md` at the pinned commit.
  - Stimulus, exactly: clock 0 is the first reset clock; `ena = 1` from clock 0; `rst_n = 0` for clocks 0-9 and 1 from clock 10 (applied before clock 10's low half); `ui_in` and `uio_in` held at the override's values (or `auto_ui_in`) from clock 0, then changed only by the override's `.inputs` events (applied at the start of the tick whose `clock` equals the event clock) and the gamepad shifting; with the QSPI model, `uio_in` is the model's response; the design's initial state is Verilator's with `--x-initial fast` (state here what that means, checked against Verilator's docs at the pinned oss-cad-suite: zero unless the design initialises); byte `i` of the FPGA harness's `uo_out` dump is sample `2i + 1` of the trace (the clk-high sample, after rising edge `i`). All of this is in the trace itself, so the trace is the record.
  - The trace-content check: `result.json` `trace.uo_out_sha256` over clocks `trace.uo_out_sha256_clocks` (`[0, min(2^25, clocks)]`), byte `c` = `uo_out` of sample `2c + 1`. No sampler is involved.
  - Hash inputs: `sha256-rgb6` is SHA-256 over the frame as rgb6, one byte per pixel `R<<4 | G<<2 | B` (R = uo[0], uo[4]; G = uo[1], uo[5]; B = uo[2], uo[6]; first bit more significant), row-major, `width * height` bytes, starting at the window's first active pixel of its first active line; not RGB888. The FNV method is over RGB888 with each channel `value * 85`.
  - Frame starts and the cpp = 1 question: `tb-v1` starts a frame at the end of the vsync pulse, starts lines at the end of the hsync pulse and reads pixel `p` at clock `p` after it (at cpp 1), which is the FPGA harness's `ideal` convention ("first line start at or after vsync end, as tb.cpp does"), so for cpp = 1 table modes its one-sample-per-pixel crop is `tb-v1`'s frame. `centre-v1` differs in definition: its frame start is the hsync leading edge of the first vsync line, rows are counted from the start of the vsync pulse (`vsync + vback'`) and pixels from the hsync leading edge (`hsync + hback' + p`); at cpp 1 its pixels equal tb-v1's wherever the design's sync pulses have the mode's widths and vsync ends on a line boundary. Which projects actually agree is a measurement: the table comes from Task 19 and Task 21 (filled in there). For cpp != 1, compare the raw trace only.
  - The reference sampler (Task 20's ruling), `hash_offset_basis` unchanged, the FPGA room in the archive (`<s>/<m>/fpga/`, `fpga-library.json`, owned by the FPGA session), and the commit to pin (filled in by Task 23).
- [ ] **Step 5: Tell the harness sessions before the files move** (controller): send `docs/consumers.md`'s link (this branch, pushed) to "Tiny Tapeout FPGA bitstreams VGA playground" and to the tt-harness-handheld-vga session, saying `frame_hashes.txt` moves to `frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` with `hash_offset_basis` unchanged, and give one day's notice or their acknowledgement, whichever comes first.
- [ ] **Step 6: Run the conversion:** `uv run scripts/convert_frame_hashes.py >> tmp/t17.log 2>&1`; expected `converted 408`, no failures. Run the test suite.
- [ ] **Step 7: Commit and push** (script and tests; then the data move in its own commit; then docs).

### Task 18: vgacap pin to `main`, and host docs

**Files:**
- Modify: `ttvga/tools.toml`, `docs/host-setup.md`.

- [ ] **Step 1:** When vgacap PRs #14-#22 have merged (`git -C ~/github/TinyTapeout/vgacap fetch origin` then `git log --oneline origin/main -25 >> tmp/t18.log 2>&1`: the M10 commits are on `main`), set `[vgacap] commit` to `origin/main`'s SHA. If they have not merged when Task 19 starts, keep the stack pin and repeat this step before Task 22; Task 22 does not start on a pin outside `main` unless the controller records a ruling naming the SHA and the reason.
- [ ] **Step 2:** `uv run tt-vga dev-tools`, `uv run pytest -v` and `uv run pytest -m sim -v` (logs in `tmp/t18.log`); all pass. `uv run tt-vga bootstrap --host big` rebuilds on the host.
- [ ] **Step 3: Rewrite `docs/host-setup.md`:** the two `install -d -o ttvga -g ttvga -m 755` lines for the frames root (inside the published tree) and the staging directory (next to it, same filesystem), `host.toml`'s three keys, `sudo loginctl enable-linger ttvga`, bootstrap installs uv and Python 3.14 and builds vgacap (it did not install uv before), cmake is required, and remove the false claim that the ffmpeg build is pinned by checksum.
- [ ] **Step 4: Commit and push.**

## Phase 4: rollout

### Task 19: pilot (rollout step 2): the budget

**Files:**
- Create: `scripts/pilot_measure.py`, `docs/reports/2026-11-pilot/measurements.md` (results; date in the directory name is the month the pilot runs), `docs/reports/2026-11-pilot/raw/*.json` (per-run numbers).

**Interfaces:**
- The 11 projects: `tt08/tt_um_a1k0n_nyancat`, `tt08/tt_um_johshoff_metaballs` (800x600), `ttihp25a/tt_um_rebeccargb_colorbars` (static), `ttihp25a/tt_um_rejunity_atari2600` (QSPI), `tt05/tt_um_tomkeddie_a` (640x504), `ttihp25a/tt_um_cfib_demo` (cpp 2), `ttihp25a/tt_um_a1k0n_vgadonut` (cpp 1.9062), `tt08/tt_um_nyan`, `tt07/tt_um_MichaelBell_rle_vga`, `tt08/tt_um_MichaelBell_mandelbrot`, `tt07/tt_um_tinytapeout_dvd_screensaver`.
- `scripts/pilot_measure.py --host big --ids FILE --out docs/reports/2026-11-pilot/raw`: for each id, on the host, in a scope as Task 10's: `job.py --tb-v1 --keep-build`, then the kept `Vtop` twice more without `--trace` and twice with, interleaved, same cwd and arguments as the job's log shows, each under `/usr/bin/time -v` (wall, user+sys CPU, max RSS) with `--ffmpeg` writing to a scratch file; then `vgacap-sample` alone (default, and `--sampler tb-v1 --sampler centre-v1`) under `/usr/bin/time -v` with `VGACAP_SAMPLE_DEBUG=1`; the derive step's PNG and page time (from `result.json` timings); store and PNG sizes (`du -b`, file counts, hard links counted once); trace size; peak scratch use on the root volume (polled every 5 s by `du -sb` of the scratch directory into the log).

- [ ] **Step 1: Start the pilot:** `pilot_measure.py` itself starts the 11 jobs (`job.py --tb-v1 --keep-build`, each in a Task 10 scope, all 11 at once) and then the extra runs, in a tmux session on the host, logging to `~/ttvga/work/pilot.log`, which the Monitor reads. Expected total about 3-4 hours (the slowest sims are about an hour each, four runs each): report on the 5-minute cadence with an ETA from completed runs.
- [ ] **Step 2: Compute, per project, against the spec's targets,** into `measurements.md` (a table per target, one row per project, no prose in cells):
  - recording: `(wall with trace - wall without) / wall without`, target <= 5%; and ns per clock;
  - post-simulation CPU (compressor thread CPU = CPU with trace - CPU without; plus `derive_cpu_seconds`) / simulation CPU without trace, target <= 5%; `dvd_screensaver` shown with its 19 s budget;
  - memory per job (max RSS of the model and of `vgacap-sample`);
  - root-volume peak per job; `min_free_root_gb` set to `24 * peak * 2`, rounded up to 10 GB, recorded as a ruling and written to the host's `host.toml`.
- [ ] **Step 3: Fix path for a missed target** (each change measured on the same project before and after, interleaved, median of 3):
  - recording over 5%: first the zstd level (`kTraceZstdLevel` 1, then -1, -3, -5); then check the push compiles inline (`objdump -d` of `Vtop` for a call to `vgacap_trace_slow` only on the slow path); then, if a busy design is still over, the planar alternative of the format note (Alternative A) is a vgacap change: report the profile to the controller, who sends it to the vgacap session and puts the decision in the owner report.
  - post-simulation over 5%: in the spec's order: `--store-level` lower (1, then -1) for stores of mostly distinct frames (a derive option `store_level` chosen by the pilot's rule: `distinct_frames / frames > 0.5` gives the faster level); then a faster SHA-256 (vgacap work, via the controller); then running a second sampler only on request (already the default: tb-v1 is opt-in). Hashing on a thread does not count.
  - Each fix is a commit with its numbers; a target still missed after the list goes into the owner report with the profile and the remaining fix.
- [ ] **Step 4: Commit and push** the script, raw numbers and `measurements.md`.

### Task 20: pilot (rollout step 2): correctness, formats and viewers

**Files:**
- Modify: `docs/reports/2026-11-pilot/measurements.md`; create `docs/reports/2026-11-pilot/frames/` (diff PNGs, small), `scripts/pilot_formats.py`.

- [ ] **Step 1: tb-v1 against the published hashes.** For each of the 11, the new `frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` hash lines equal the converted committed file's (Task 17) exactly. Any difference stops this task: investigate (it is a `tb.cpp` trace-path or tb-v1 bug, or a non-reproducible run) and report; never accept it.
- [ ] **Step 2: Distinct counts.** Per project, distinct SHA-256 frames (frames.txt `distinct_frames` of tb-v1) against distinct FNV values (old timing `distinct_frames`); the 408-project total of distinct FNV values today is 543,730 (`tb.cpp:477,488`).
- [ ] **Step 3: tb-v1 against centre-v1, frame by frame:** `tt-vga frames compare` of the two `frames.txt` for each project, and `tt-vga frames diff` of the first differing pair, PNGs saved under `frames/`. For `tt_um_nyan`, `MichaelBell_rle_vga` and `MichaelBell_mandelbrot`: `clocks_per_pixel` is 1, 1 and 4 in centre-v1, `colour_changes_off_grid` is 0, and `outside` is 0 (else record the suggested offset; do not set `centre_window` here).
- [ ] **Step 4: Calibration designs.** `tt-vga queue start --only testpatterns` (the six modes variants included); for each, compare every centre-v1 distinct frame with tt-vga-testpatterns' `tools/render.py` reference for that design and `ui_in` (run with `uv run --project <tt-vga-testpatterns checkout>` from a script file; the counter design per frame number). Expected: pixel-exact, including 720x400 and the three polarity cases (polarity: frames.txt `mode` and the trace's calibration agree). Any difference is a centre-v1 bug for the vgacap session (controller), not a tolerance.
- [ ] **Step 5: Hardware where it exists.** For the cpp != 1 projects (`cfib_demo`, `vgadonut`, `MichaelBell_mandelbrot`): look for a vgacap hardware capture of the same design (Welland boards' claims and captures, and tt-harness-fpga-vga's results for these ids); where one exists, decode it with `vgacap-frames` and compare both samplers' frames by SHA-256 of rgb6; where none exists, record `none` and rely on Step 3's diffs.
- [ ] **Step 6: Formats.** `scripts/pilot_formats.py` measures, per project, the stored trace as VGCH (the file), as FST (`vgacap-export --format fst --no-clk` of the whole trace, and with `clk`), and as a sigrok session (`.sr`: a zip with `version` = `2`, a `metadata` file and `logic-1-<n>` raw sample chunks of 6 bytes a sample, deflated, written by the script over the first 2^24 clocks and extrapolated linearly to the run's clocks; the extrapolation is stated). Projected to all 408 with each project's clocks. Also the store as one zstd frame per distinct image (level 3, no long-distance matching) against the single long-distance stream, size and the time to read one frame from the middle (spec, Layer 3).
- [ ] **Step 7: Viewers.** For one frame of nyancat and of `cfib_demo`: `tt-vga trace export --format fst` and `--format vcd` with `--sampler-frames`, `fst2vcd` of the FST equal in value changes to the VCD; GTKWave screenshots made on the host with `xvfb-run` if Xvfb is installed (else none); the files and the `.gtkw`/`.sucl` copied to `docs/reports/2026-11-pilot/viewers/` only if under 5 MB each. Opening them in Surfer on a desktop is listed in the owner report as the owner's check (Surfer does not run on this host).
- [ ] **Step 8: Upload listing.** Time a listing of the published tree as the upload would see it: `rsync --dry-run --recursive --list-only` of the frames root (pilot projects only) and the file count, projected to 408 from the PNG counts; record today's 62,641 entries and about 25 s from `/var/lib/data-upload/rsync.log` (read only).
- [ ] **Step 9: Commit and push.**

### Task 21: owner report (rollout step 3), with the controller's rulings

**Files:**
- Create: `docs/reports/2026-11-pilot/report.md`.

- [ ] **Step 1: Write the report**, projected to all 408: trace size per format, store and PNG sizes (and how many PNGs tb-v1 adds after sharing identical frames), run time, root-volume use per job, the upload's listing time with the extra files, the budget table from Task 19 with profiles and fixes for any target missed, the correctness results of Task 20.
- [ ] **Step 2: Record the rulings** (the controller takes them where the spec recommends; each as "Ruling: <decision> - <reason from the numbers> - <cost if wrong>"):
  - Decision 2, stored format: VGCH with runs, unless FST or sigrok is at most half its projected size over 408.
  - Decision 3, reference sampler: `centre-v1`, provided Task 20 found it pixel-exact on every calibration design and, for the cpp != 1 projects, in agreement with hardware where a capture exists and visibly right in the diffs where none does; `tb-v1` stays published for continuity. If a condition fails, the ruling is `tb-v1` stays the reference and the failure goes to the owner as an open question; Task 22 still runs.
  - Decision 4, the upload: Task 22's option.
  - Job count for the re-run (24 unless memory or root-volume measurements say fewer) and `min_free_root_gb`.
  - Anything the owner must look at himself: Surfer, any target missed with no fix, any planar-format question.
- [ ] **Step 3: Publish and tell the owner:** commit and push; the controller publishes the report as an Artifact (private by default) and gives the owner the link.
- [ ] **Step 4: Fill in the consumer note's cpp = 1 agreement table** from Task 20 Step 3 (projects where tb-v1 and centre-v1 agree frame for frame), commit and push.

### Task 22: the upload's file listing (decision 4)

**Recommended option, taken as the ruling: the 5-minute upload skips the frames tree, and a separate frames upload sends only the projects the pipeline marks changed.** It keeps the clips' 5-minute latency, sends a re-run project within the next frames run, and avoids a 1.1-million-entry listing every interval. A longer interval delays everything; a separate slow upload still lists the whole frames tree every run.

**Files (host, under etckeeper, with `tim`'s sudo; the repository records only the design):**
- Modify: `/usr/local/sbin/data-upload-sync` (adds `--exclude=/<frames root relative to /srv/data.wafer.space>/`, given in `/etc/data-upload/frames.conf`, not in this repository).
- Create: `/usr/local/sbin/data-upload-frames-sync`, `/etc/systemd/system/data-upload-wafer-space-frames.{service,timer}` (every 15 minutes; the same sandboxing as the existing unit, plus `ReadOnlyPaths=` the staging directory).
- Create (repository): `docs/publishing.md` section "Frames upload" describing it (no host names or paths).

**Interfaces:**
- The frames sync reads `<staging_dir>/changed.log` (written by Task 6 as `ttvga`, world-readable) from the byte offset stored in its own `StateDirectory` (`/var/lib/data-upload-frames/offset`), takes the unique `<shuttle>/<macro>` ids since then, and runs one rsync (the existing options, no `--delete`) with `--files-from` listing those project directories (recursive), then stores the new offset only on rsync success (0, 23 or 24 as the existing script treats them). A weekly full listing of the frames tree (`OnCalendar=weekly` in the same timer's sibling, or an argument `--full`) reconciles anything missed.
- [ ] **Step 1:** Dry run both scripts with `DATA_UPLOAD_DRY_RUN=1` as `data-upload` (`sudo -u data-upload ...`), logs into this repository's `tmp/t22.log`: the main run's file count drops by the frames tree; the frames run lists exactly the pilot projects.
- [ ] **Step 2:** Install, `systemctl daemon-reload`, enable the timer, `etckeeper commit "data-upload: frames tree uploaded by changed projects (tinytapeout-vga-videos decision 4)"`. Watch two runs of each unit (`journalctl -u ...` into the log) and the listing time in `/var/lib/data-upload/rsync.log`.
- [ ] **Step 3:** Commit and push `docs/publishing.md`.

### Task 23: the full re-run and publishing (rollout step 4)

**Files:**
- Modify: `data/results/**` (collected), `docs/status.md`, `data/status.json`, `data/index.json`/`index.html` (regenerated), `docs/consumers.md`, `PROGRESS.md`, `README.md`.
- Create: `docs/reports/2026-11-rerun.md`.

- [ ] **Step 1: Preconditions** (controller checks and records): Task 18's pin is on vgacap `main` (or a recorded ruling); Tasks 19-22 merged; the host's harness synced; Linger=yes; `host.toml` has `min_free_root_gb` from Task 19; no outside user is using the host heavily (`ps -eo user,pcpu --sort=-pcpu | head -20` into the log). Record the pre-rerun commit SHA of `main` as `PRE`.
- [ ] **Step 2: Start the opt-in tb-v1 re-run of all 408:** `uv run tt-vga queue start --host big --redo --tb-v1 --jobs 24 >> tmp/t23-queue.log 2>&1` (the `testpatterns` pseudo-shuttle included, unpublished). Estimate: 104 CPU hours of simulation plus the pilot's measured overhead over 24 jobs, about 5 hours; report every 15 minutes if the estimate is 4 hours or more (else every 5), from `queue-state.json` (`done`, `failed`) and the median job time, with remaining time and finish clock time. Health checks follow the background-task rules: the whole process tree unfiltered, every wait's exit condition.
- [ ] **Step 3: Collect:** `uv run tt-vga collect --host big >> tmp/t23-collect.log 2>&1`; then `analyze`, `report`, `index` as today.
- [ ] **Step 4: The tb-v1 check of all 408.** A script step (`scripts/check_tbv1_against.py --base PRE`) compares, for each of the 408, the hash lines of `git show PRE:data/results/<s>/<m>/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` with the new file, and every result's `tb_v1_check` is `match`. Expected: 408 identical. Every project that is not is investigated (re-run once alone; `frames compare` against PRE; the trace exported around the first mismatch) and fixed or reported; none is accepted as is. Header differences other than the hash lines are listed separately (expected: none after Task 17's recomputed `clocks_per_pixel`).
- [ ] **Step 5: The `outside` list.** Every project whose centre-v1 `outside` is not 0, with its `suggested_offset` and links to its first frames, into `docs/reports/2026-11-rerun.md` for a person to decide `centre_window` (no override is set by this plan).
- [ ] **Step 6: Commit and push** the collected data in reviewable commits (one per shuttle group is fine), then the regenerated docs.
- [ ] **Step 7: Publish.** The frames tree is already in the published tree (each job swapped it in); the frames upload sends the changed projects. `tt-vga mirror --as-user tim --dest <archive>` (archive path from the host config note, not this repository) for the clips and index; then `tt-vga verify --host big` and `tt-vga verify --server-stale https://data.wafer.space/big-storage/tinytapeout-vga-videos/` (logs into `tmp/t23-verify.log`); stale server files listed for removal by hand, `fpga/` and `fpga-library.json` never among them.
- [ ] **Step 8: Tell the consumers.** Fill in `docs/consumers.md`'s pin line with the commit that holds the collected re-run (the `main` SHA after Step 6) and the reference sampler; commit and push; the controller sends that SHA and the note's link to "Tiny Tapeout FPGA bitstreams VGA playground" (it pins 148ccf5 today, moving to 87cea85) and to the handheld session.
- [ ] **Step 9: PROGRESS.md entry** (what ran, counts, the tb-v1 check result, time taken, sizes on the bulk volume, open items) and `README.md`'s frames section pointing at `docs/consumers.md`; commit and push.
