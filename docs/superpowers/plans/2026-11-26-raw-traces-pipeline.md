# Raw traces in the pipeline: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every simulation keep a raw pin trace and derive its frames, hashes, PNGs and pages from that trace through vgacap, cheaply enough to sit beside the simulation. Then re-run all 408 projects, check them, and publish the new data so other tooling (the FPGA and handheld harnesses) can compare against it properly.

**Architecture:**
- `tb.cpp` records every pin at both halves of every clock through vgacap's inline trace writer (`vgacap_trace_push`). The trace is a zstd seekable file in the job's scratch directory on the root NVMe volume.
- After the simulation, the job runs vgacap's `vgacap-sample` once over the trace: centre-v1 always, tb-v1 only on request. It reads the tool's PNG pipe and writes PNGs and pages.
- The finished project directory is then copied to staging on the bulk volume and swapped into a dedicated frames subtree of the archive with `renameat2(RENAME_EXCHANGE)`.
- The same derive step runs without simulating (`job.py --rederive`). `tt-vga trace|sample|frames` wrap the vgacap tools and use vgacap's Python file-format code through the vgacap pin.
- `collect` brings each sampler's `frames.txt` and the tb-v1 FNV file into git.
- Rollout runs in this order:
  1. host setup and the upload split, with the frames upload left off;
  2. an 11-project pilot that measures the budget and correctness;
  3. the owner report, whose recommended options are taken as rulings;
  4. the full opt-in tb-v1 re-run of all 408;
  5. the check against the committed FNV files;
  6. only then, turning on the frames upload and publishing.

**Tech Stack:**
- C++17 (`tb.cpp`, Verilator) and C99 (`tracetool.c`).
- vgacap at a pinned commit: `vgacap_trace`, `vgacap_sample`, `vgacap-sample`, `vgacap-export`, and its Python `vgacap.framesfile`, `vgacap.hashes`, `vgacap.timebase`, `vgacap.tbv1`, `vgacap.stream`. These Python modules use the standard library only.
- On the host: uv-managed CPython 3.14, standard library only (`compression.zstd`, `zlib`, `ctypes`). Locally: Python 3.14 via uv, with pytest.
- systemd user scopes and rsync.

**Spec:** `docs/superpowers/specs/2026-11-24-raw-frames-and-hash-methods-design.md` (revision 17, as amended at 97e74b1). Also binding:
- vgacap format note `tt-vga-capture/docs/design/2026-11-25-format-v2-runs.md` (branch `m10-format-note`): `RUNS`, skip-by-length, boards later.
- The rulings ledger `tt-vga-capture/.worktrees/m10-plan/.superpowers/sdd/2026-11-24-m10-simulation-traces/progress.md`, Rulings A-Z. In particular:
  - U: `sampler_status`;
  - S: `bad-window` is an error exit of `vgacap-sample`;
  - W: centre-v1 only by default;
  - X and Y: the FabricFox library, its ids, and the archive as the delivery route;
  - Z: a re-run never silently deletes tb-v1 files.
- Ruling AA (2026-11-26, from the FPGA library spec): bitstreams sit directly in the archive's `<shuttle>/<macro>/` directories as `<id>-<sha256[:12]>.bin`, with `fpga-library.json` at the archive root. The tt-harness-fpga-vga session owns them.
- The controller's I12 ruling (2026-11-26) rests on the owner's goal of the same day, "update all the VGA simulation output data to allow proper comparison by other tooling", which authorises proceeding through step 4. Decisions 2-4 take the spec's recommended options and are recorded as rulings in the step 3 report, which is sent to the owner. The re-run does not wait for his answer: an objection is applied afterwards by re-deriving. Host changes are made with `tim`'s sudo, committed through etckeeper, and listed in the report.
- vgacap's own format docs at the pinned commit, `docs/trace-format.md` and `docs/frames-format.md`, are authoritative for every byte of the trace, of `frames.txt` and of the hash files. This plan never restates them and never changes them.

## Global Constraints

Host and process rules (every task inherits them):
- **No hidden errors.** Never `2>/dev/null` (a hook blocks it). Never filter a command's output inline (`cmd | head`, `cmd | grep`). Every command writes in full to a log under the worktree's `tmp/` (`cmd >> tmp/<task>.log 2>&1`), and you grep or tail the log afterwards.
- **No `/tmp`.** Temporary files go under the repository's `tmp/` (ignored). pytest runs with `--basetemp=tmp/pytest` (set in `pyproject.toml`, Task 2). On the host, temporary files go under `~/ttvga/work/`.
- **Python through uv only** (`uv run ...`), never `python -c`. Scripts are files.
- **Small commits, each pushed at once** over SSH to `git@github.com:mithro/tinytapeout-vga-videos.git`.
  - Each task runs in its own worktree `.worktrees/<task-branch>` on its own branch. It is reviewed independently before it merges to `main`.
  - Each worktree sets `TTVGA_DEV_TOOLS` to one shared directory, the main checkout's `tmp/dev-tools`, so oss-cad-suite is downloaded once.
- **Commit trailer**, on every commit: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01M4cwEsPm9kJ96LQeYKwqhK`.
- **ISO dates** (`2026-11-26`) in files, logs and commit messages.
- **Progress reports.** Long runs report progress with an ETA (remaining time and finish clock time) on the CLAUDE.md cadence: every 60 s under 10 minutes, every 5 minutes under 4 hours, every 15 minutes beyond. A background Monitor reads the job's log file, never a live pipe, and computes the ETA from observed throughput.
- **Load.** A load average around 90 on this 88-thread host is normal. Judge load as load/88 plus `ps -eo pcpu --sort=-pcpu`, logged in full.
- **No host names in the repository.** Hosts come from `--host`. Host paths come from `~/ttvga/host.toml` on the host (`frames_root`, `staging_dir`, `min_free_root_gb`). Where this plan needs a host path it writes `<archive>`, the published VGA archive, whose real path is in the host setup memory note.
- **Third-party Verilog.**
  - It is built and run only as the dedicated unprivileged `ttvga` user on the host (the existing sandbox: `FORBIDDEN_USERS` in `ttvga/remote.py`).
  - From Task 10 on, each job runs inside a `systemd-run --user --scope` with `MemoryMax`, `CPUQuota` and `TasksMax`. The scope limits resources only, not file access.
  - Nothing `ttvga` writes is trusted by the root-owned upload: Task 19 validates `changed.log`, and Task 6 allow-lists what is published.
  - Locally, only this repository's own test designs (`tests/sim/designs/`) are simulated.
- **Wall-clock limit.** The queue's job count is small: 24 for the full re-run unless the pilot rules otherwise. Every pilot and re-run job uses `--timeout 10800`, the reference run's limit (`PROGRESS.md`); the slowest committed run took 6,380.7 s.

Pipeline rules from the spec, the owner and the rulings:
- **tb-v1 is legacy and runs only on request** (`job.py --tb-v1`, `tt-vga queue start --tb-v1`). Without it the job runs centre-v1 only, computes no new FNV file, and records `tb_v1_check: off`. The step 4 re-run is an explicit `--tb-v1` run.
- **A run never deletes tb-v1 files** (Ruling Z). This holds for the published `tb-v1/`, for the host's `work/<s>/<m>/frames/tb-v1/`, and for git's `data/results/<s>/<m>/frames/tb-v1/`. Only `--drop-tb-v1` removes them, for when the owner retires tb-v1.
- **`tb_v1` in `result.json`.** Every run writes `"tb_v1": {"state": S, "trace_sha": T, "dropped": D}`:
  - `S = "current"` when tb-v1 was made from this run's trace. That is a `--tb-v1` run, or a carry-over whose recorded `trace_sha` equals this run's `trace.sha256` (for example a `--rederive` of the same trace).
  - `S = "stale"` when tb-v1 files exist from another trace. `T` is that trace's SHA-256, or `null` for the converted files made before traces existed.
  - `S = "none"` when there are none.
  - `D` is `true` only after `--drop-tb-v1`.
  - `tt-vga verify` reports `stale` as a note, never as a failure.
- **`trace.sha256`** is the SHA-256 (lowercase hex) of the trace file's bytes. It appears only in `result.json` (`trace.sha256` and `tb_v1.trace_sha`) and in the published, uncommitted sidecar `tb-v1/TRACE_SHA256`, never in a committed `frames.txt` or hash file. Those depend only on the trace's content and the sampler, so a normal re-run adds nothing to git (spec, Where things live).
- **A failed job publishes nothing.** "Failed" means fetch, build or simulation failure without a usable trace, any derive error (including `tb_v1_check: mismatch` and `bad-window`), or a publish allow-list violation. The previous published directory stays exactly as it was, and `result.json` records the error. `tt-vga verify` lists such projects as `failed (previous output kept)`. This replaces the spec's "removes its stale directory" (controller's I13 ruling).
- **What is published on a successful run.** A no-picture run (no-sync, bad-timing) is a success: it publishes its trace and `frames: 0` files. A killed model with a trace publishes its truncated frames, then reports its error. Publishing does not depend on `encode`: an encode failure still publishes the trace and frames.
- **Clock numbering** is the spec's: clock 0 is the first reset clock; clock `c` is samples `2c` (clk low) and `2c + 1` (clk high); `--from/--to` are clocks, from inclusive, to exclusive.
- **`clock_hz` is an integer** in hertz everywhere. `tb.cpp` refuses a non-integer `--clock-hz`, or one above 4,294,967,295, when `--trace` is given (exit 2).
- **Permissions.** Everything written for the published tree is written with umask 022 (files 0644, directories 0755).
- **The host harness** (`ttvga/harness/`) is standard-library only and runs under the pinned uv Python 3.14. It imports vgacap's Python package from the pinned clone, `~/ttvga/tools/vgacap-src/python`, put on `sys.path` by `ttvga/harness/vgacap_path.py`. Local tools use `devtools.paths().vgacap_src / "python"` the same way. Nothing from vgacap is copied, and the sibling harness repositories are never imported.
- **The vgacap pin.** `ttvga/tools.toml [vgacap]` names a commit SHA of the M10 stack, chosen when Task 1 starts: `m10-export`, or `m10-perf` if it has landed with the same interfaces. Task 18 moves it to vgacap `main` once PRs #14-#22 have merged. PRs #1-#13 are expected on `main` early in execution.
- **Published names.**
  - `<stem>` is `encode.stem_for(shuttle, macro)` (`<shuttle>_<macro>`).
  - Trace: `<stem>_trace.vgch.zst`.
  - Store: `<stem>_<sampler>_frames.rgb6.zst` (written by `vgacap-sample --name <stem>`).
  - Frames subtree: `<frames_root>/<shuttle>/<macro>/`, with `<frames_root>` = `<archive>/frames`. This is never inside an archive `<shuttle>/<macro>/` directory, where the mirrored clips and the FPGA bitstreams live.

## Review Focus

1. **A model killed outright** (it ignores SIGTERM and gets SIGKILL after the grace period) **mid-block.** The job samples the trace's complete blocks with status `truncated`, publishes them, then reports the error. It never leaves the scratch directory behind. Test: Task 9 `test_job_killed_model_samples_truncated_trace`.
2. **A project re-run while the upload or a viewer reads its published directory.** The swap is one `renameat2(RENAME_EXCHANGE)`: at no instant is the project half-copied, and the old directory is deleted only after the exchange. Test: Task 6 `test_swap_never_exposes_partial_directory`.
3. **A default re-run of a project that so far has only the converted tb-v1 file.** That file stays in git and on the host; `result.json` says `tb_v1.state: stale`. Tests: Task 9 `test_job_default_rerun_keeps_seeded_tb_v1`, and Task 11 `test_collect_never_removes_tb_v1_without_drop`.
4. **`collect` while a job is running on the host, or before the re-run.** A running job's scratch `frames.txt` is never pulled in. A host `result.json` written by the old pipeline (with its full hash list and no `tb_v1`) is never pulled over a converted one. Test: Task 11 `test_collect_filter_ignores_scratch_and_old_results`.
5. **A `frames_root` that points at the archive itself or a clips directory.** `hostconf.load` and `publish.install` refuse it before anything is replaced. Tests: Task 6 `test_load_refuses_archive_root` and `test_install_refuses_unmarked_directory`.

---

## File structure

| file | responsibility |
| --- | --- |
| `ttvga/tools.toml` (modify) | `[uv]` tarball, `[python]` version, `[vgacap]` git URL + commit |
| `ttvga/remote.py` (modify) | bootstrap, host-check, scripts run on the pinned Python, `collect` of `frames/`, queue flags, mirror exclusions |
| `ttvga/devtools.py` (new) | `tt-vga dev-tools`: the pinned oss-cad-suite and vgacap under `$TTVGA_DEV_TOOLS` |
| `ttvga/harness/tb.cpp` (modify) | `--trace`, `--meta`, the inline push, META(open/close), `tb_frame_hashes.txt` |
| `ttvga/harness/tracetool.c` (new) | `tracetool info\|slice\|uohash` over vgacap's trace reader and writer |
| `ttvga/harness/vgacap_path.py` (new) | puts the pinned vgacap Python on `sys.path`; `tools(root) -> dict` of the vgacap tool paths |
| `ttvga/harness/hostconf.py` (new) | read and check `~/ttvga/host.toml` |
| `ttvga/harness/publish.py` (new) | allow-list, staging copy, carry, exchange, `changed.log` |
| `ttvga/harness/pngio.py`, `pages.py` (new) | indexed 64-colour PNG write and read; per-sampler `index.html` |
| `ttvga/harness/derive.py` (new) | `vgacap-sample` + PNG pipe + `tracetool uohash` + tb-v1 check, into scratch |
| `ttvga/harness/job.py`, `runqueue.py`, `verify.py` (modify) | the job flow, `--rederive`, the tb-v1 flags, free-space wait, scopes, verify notes |
| `ttvga/traces.py`, `ttvga/frames.py` (new) | `tt-vga trace ...`, `tt-vga sample`, `tt-vga frames ...` |
| `ttvga/targets.py`, `overrides.py`, `index.py`, `report.py` (modify) | `data/extra-targets.json`, `src_dir`, `centre_window`, `testpatterns` left out, FPGA links |
| `ttvga/framehashes.py`, `tests/test_framehashes.py` (delete) | replaced by `frames/` |
| `scripts/convert_frame_hashes.py`, `scripts/export_tbv1_vectors.py`, `scripts/pilot_measure.py`, `scripts/pilot_formats.py`, `scripts/check_tbv1_against.py` (new) | one-off and rollout scripts |
| `data/extra-targets.json`, `overrides/testpatterns/*.yaml` (new) | the calibration designs |
| `tests/sim/` (new) | test designs, `ffmpeg_sink`, `jobroot.py`, the Verilator tests (`-m sim`) |
| `docs/consumers.md` (new); `docs/host-setup.md`, `docs/publishing.md`, `README.md`, `PROGRESS.md` (modify) | the consumer note and the docs |

Test-run convention, used in every task's run steps: `uv run pytest <files> -v >> tmp/t<N>.log 2>&1` (add `-m sim` for `tests/sim/`), then read the summary line in the log. "Fail" means the new tests fail and nothing else does. "Pass" means everything passes.

---

## Phase 1: tools

### Task 1: pinned uv, Python 3.14 and vgacap on the host

**Files:**
- Modify: `ttvga/tools.toml`, `ttvga/remote.py`, `pyproject.toml` (`requires-python = ">=3.14"`), `uv.lock`.
- Create: `ttvga/harness/vgacap_path.py`.
- Test: `tests/test_remote_bootstrap.py`.

**Interfaces:**
- Produces:
  - **`tools.toml`:**
    - `[uv]`: `version`, `url` of the astral-sh/uv release tarball for x86_64-unknown-linux-gnu, `dir = "uv"`, `strip = 1`, `check = "uv/uv"`;
    - `[python] version = "3.14.7"`;
    - `[vgacap] git = "https://github.com/mithro/vgacap"`, `commit = "<40-hex SHA>"`.
  - `remote.tarball_tools(tools: dict) -> dict`: the entries with a `url`. The tarball loop skips `[python]` and `[vgacap]`.
  - `remote.vgacap_build_commands(src: str, build: str, commit: str) -> list[str]`:
    - shallow fetch and checkout of `commit` into `src`;
    - `cmake -S src -B build -DCMAKE_BUILD_TYPE=Release`;
    - `cmake --build build -j 8 --target vgacap-sample vgacap-export vgacap-dump vgacap_trace vgacap_sample`;
    - writing `build/PINNED`. A different pin rebuilds.
  - `remote.bootstrap_script(tools: dict) -> str`: the tarball loop, `uv python install <version>`, then `vgacap_build_commands("vgacap-src", "vgacap-build", commit)` under `~/ttvga/tools`.
  - `remote.host_python(tools) -> str`: `~/ttvga/tools/uv/uv run --no-project --python <version> python`.
    - Every host script (`runqueue.py`, `job.py`, `verify.py`, `rerender.py`) starts through it.
    - The two one-line JSON reads (the `host-check` queue line and the `queue stop` PID read) may stay on `python3`.
  - `remote.queue_command(args, host, tools) -> str`: the queue start command, factored out of `queue()`.
  - `vgacap_path.add(root: Path) -> None` puts `<root>/tools/vgacap-src/python` on `sys.path`. `vgacap_path.tools(root: Path) -> dict` gives `vgacap_sample`, `vgacap_export`, `vgacap_dump` and `tracetool` under `<root>/tools/vgacap-build/` (Task 4 adds `tracetool`).
  - `host-check` also prints:
    - `cmake --version` (MISSING if absent);
    - the vgacap pin built and the Python version;
    - `loginctl show-user ttvga -p Linger`;
    - whether `host.toml` exists.
  - `remote.harness_version(repo: Path = ROOT) -> str`: `sha256(tree + "\n" + blob + "\n")[:16]` (hex), with `tree = git rev-parse HEAD:ttvga/harness` and `blob = git rev-parse HEAD:ttvga/tools.toml`. `tools.toml` carries the vgacap pin and the oss-cad-suite (Verilator) and ffmpeg versions, so a pin or toolchain change changes the key. `-dirty` is appended when `git status --porcelain -- ttvga/harness ttvga/tools.toml` is non-empty. A commit anywhere else (PROGRESS, collected data, docs) leaves it unchanged, so neither `--redo-unless-harness` nor the trace's META(open) `harness=` changes with it. Overrides and `data/targets.json` are not in the key; Task 23 Step 1 checks them for the projects the key would skip.
  - `push_harness` also writes `harness/HARNESS_VERSION`, holding `harness_version()`.

- [ ] **Step 1: Choose the vgacap commit.**
  - Log `git -C ~/github/TinyTapeout/vgacap log --oneline -1 m10-perf m10-export main` to `tmp/t1.log`.
  - Take the tip of `m10-perf` if its branch says its interfaces are unchanged and its `ctest` log passes, else `m10-export`.
  - Record the SHA and the reason in a comment in `tools.toml`.
- [ ] **Step 2: Write the failing tests** in `tests/test_remote_bootstrap.py`:
  - `test_tarball_loop_skips_python_and_vgacap`: the keys are `{"oss-cad-suite", "ffmpeg", "uv"}`.
  - `test_bootstrap_installs_python_and_builds_vgacap_at_the_pin`: the script contains `uv python install 3.14.7`, the pinned commit, `-DCMAKE_BUILD_TYPE=Release` and `PINNED`.
  - `test_host_scripts_run_under_the_pinned_python`: `queue_command(...)` starts with `host_python(tools)`.
  - `test_vgacap_commit_is_a_full_sha`: matches `^[0-9a-f]{40}$`.
  - `test_vgacap_path_adds_the_pinned_python`.
  - `test_harness_version_ignores_commits_elsewhere`: in a scratch git repository under `tmp/pytest` with a `ttvga/harness/` file, a commit touching only `README.md` leaves `harness_version()` unchanged; a commit touching `ttvga/harness/x` changes it; a commit touching only `ttvga/tools.toml` (the vgacap `commit` line) changes it; an uncommitted change in either appends `-dirty`, and one elsewhere does not.
- [ ] **Step 3: Run** `tests/test_remote_bootstrap.py`: 6 fail.
- [ ] **Step 4: Implement**, set `requires-python = ">=3.14"`, then `uv lock`.
- [ ] **Step 5: Run** the whole suite: pass.
- [ ] **Step 6: Bootstrap the host** (logs to `tmp/t1-bootstrap.log`): `uv run tt-vga bootstrap --host big`, then `uv run tt-vga host-check --host big`. Expected: `vgacap-sample` built, Python 3.14.7, cmake found. Linger and `host.toml` stay missing until Task 18.
- [ ] **Step 7: Commit and push.**

### Task 2: local dev tools and the `sim` test marker

**Files:**
- Create: `ttvga/devtools.py`, `tests/conftest.py`, `tests/sim/__init__.py`, `tests/sim/ffmpeg_sink` (executable: `#!/bin/sh` then `exec cat > /dev/null`, so `tb.cpp`'s `popen` writes never raise SIGPIPE).
- Modify: `ttvga/cli.py`, `pyproject.toml`:
  - `[tool.pytest.ini_options] addopts = "--basetemp=tmp/pytest -m 'not sim'"`;
  - `markers = ["sim: needs tt-vga dev-tools (Verilator and vgacap)"]`.
- Test: `tests/test_devtools.py`.

**Interfaces:**
- Produces:
  - `tt-vga dev-tools`: installs the pinned oss-cad-suite tarball under `$TTVGA_DEV_TOOLS` (default `tmp/dev-tools`) and runs `remote.vgacap_build_commands` there. It is idempotent: `PINNED`, plus the oss-cad-suite `check` path.
  - `ttvga.devtools.paths() -> DevTools`, a dataclass of `Path`s:
    - `root`, `verilator`, `fst2vcd`;
    - `vgacap_src`, `vgacap_build`, `vgacap_sample`, `vgacap_export`, `vgacap_dump`;
    - `tracetool` (built by Task 4);
    - `ffmpeg_sink` (`tests/sim/ffmpeg_sink`).
  - `tests/conftest.py` fixture `dev_tools() -> DevTools`.
    - `DevTools.require(*names: str) -> None` checks only the named tools (for example `dev_tools.require("verilator", "vgacap_sample")`). When one is missing it **fails** with "run `uv run tt-vga dev-tools` first" and names it. It never skips. The fixture itself checks nothing, so Task 3's tests run before Task 4 has built `tracetool`; every sim test calls `require` with the tools it uses.
    - `uv run pytest` alone deselects `sim`; `uv run pytest -m sim` runs it.
- [ ] **Step 1: Write the failing tests:**
  - `test_paths_follow_the_env` (`TTVGA_DEV_TOOLS` set to a `tmp/pytest` path);
  - `test_require_checks_only_named_tools` (a root with `verilator` present and `tracetool` absent: `require("verilator")` passes, `require("tracetool")` fails naming it);
  - `test_pytest_basetemp_is_in_tmp`.
- [ ] **Step 2: Run:** 3 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run tt-vga dev-tools >> tmp/t2.log 2>&1`, then the suite: pass.
- [ ] **Step 5: Commit and push.**

## Phase 2: recording

### Task 3: `tb.cpp` writes the trace

**Files:**
- Modify: `ttvga/harness/tb.cpp`, `ttvga/harness/job.py` (only `vgacap_link_flags`).
- Create: `tests/sim/designs/`: Verilog with Apache-2.0 headers; each top is `tt_um_test_<name>` with the Tiny Tapeout ports:
  - `bars640.v`: 640x480@60, cpp 1, 8 bars whose order rotates each frame;
  - `bars_cpp2.v`: one pixel per 2 clocks, run at 50,350,000 Hz;
  - `frac.v`: 1,525-clock lines (cpp 1.90625), at 48,000,000 Hz;
  - `nosync.v`: constant `uo_out`;
  - `glitch.v`: `bars640` with a 1-clock vsync glitch inside the pulse of every 4th frame;
  - `playground.v`: the VGA Playground's `hvsync_generator` timing;
  - `uio_echo.v`: `uio_out = ui_in`, `uio_oe = 0xF0`.
- Create: `tests/sim/build.py` (`build_model(design: str, dev: DevTools, out: Path) -> Path`), `tests/sim/vgch.py` (it reads a decompressed trace through `vgacap.stream` from `dev.vgacap_src / "python"`), `tests/sim/test_tb_trace.py`.

**Interfaces:**
- Consumes: vgacap `trace.h` (`vgacap_trace_create`, `vgacap_trace_push`, `vgacap_trace_finish`, `vgacap_trace_abandon`) and `stream.h` (`vgacap_header_init_v2`).
- Produces:
  - `job.vgacap_link_flags(vgacap_src: Path, vgacap_build: Path) -> list[str]`:
    - `-CFLAGS -I<src>/include`;
    - `-LDFLAGS "<build>/libvgacap_trace.a <build>/libvgacap_stream.a <build>/third_party/libvgacap_zstd.a -pthread"`, with the library paths checked to exist (a `FileNotFoundError` names a missing one).
    - `tests/sim/build.py` uses it with `job.build`'s other flags.
  - New options:
    - `--trace PATH`: no trace without it.
    - `--meta KEY=VALUE`, repeatable: the job passes `project`, `override`, `simulator` and `harness`. A bad key, a duplicate key or a value with a newline exits 2.
    - `tb.cpp` adds `meta=open`, `calib_seconds` and `seconds` (the argument strings as given), and `layout=tt-um-43`.
  - Header: `vgacap_header_init_v2(&h, 43, 2, 42, 0)`, `mode = 2`, `clock_hz` = the integer `--clock-hz`. The zstd level is the constant `kTraceZstdLevel = 1`, which the pilot may change.
  - Pushes, one per half clock:
    - one `push` after the clk-low `eval()` of each tick;
    - one after the clk-high `eval()` and, with QSPI, after the response re-eval;
    - the value is `uo_out | uio_out<<8 | uio_oe<<16 | ui_in<<24 | uio_in<<32 | rst_n<<40 | ena<<41 | clk<<42`, as the ports hold it at that moment.
    - A push returning -1 sets `g_stop`, and the run ends with exit 4 and the writer's message on stderr.
  - META(close):
    - It is written on every path that writes timing.json, with `capture_after_clock`, `status` (the value written to timing.json) and `frames` (0 on the fail paths).
    - SIGTERM reaches the normal path and so finishes the trace.
    - The exits that write no timing.json (cannot write it, cannot start ffmpeg) call `vgacap_trace_abandon` and unlink the trace.
  - A test hook compiled in only when `TTVGA_TEST_HOOKS` is defined: then `TTVGA_TB_IGNORE_SIGTERM=1` in the environment makes `tb.cpp` ignore SIGTERM. A production model has no such code, so no environment can make it unkillable except by SIGKILL. `tests/sim/build.py` defines it (`-CFLAGS -DTTVGA_TEST_HOOKS`). Task 9 adds `job.py --test-hooks`, the only other way in; `runqueue.py` and `tt-vga queue` never pass it and refuse it (exit 2). Used only by Task 9's killed-model test.
  - The frame hash list leaves timing.json and goes to `<out>/tb_frame_hashes.txt`: one 16-digit lowercase hex per line, frame 0 first, written on every path that writes timing.json.
  - The comment at the FNV constant names `frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`.
- [ ] **Step 1: Write the failing tests** (all `@pytest.mark.sim`).
  - Every run uses `--seconds 0.2 --calib-seconds 0.1 --no-audio --quiet --ffmpeg <dev.ffmpeg_sink>`, on a model built once per session under `tmp/pytest`.
  - `test_trace_pins_match_the_design`, on `uio_echo` with `--ui-in 0x5a`:
    - samples 0-19 have `rst_n = 0` and sample 20 onwards `rst_n = 1`;
    - `ena = 1` everywhere and `ui_in = 0x5a`;
    - `uio_out & 0xF0 == 0x50` and `uio_oe == 0xF0`;
    - the clock bit is `n & 1`.
  - `test_trace_meta`:
    - META(open) has `project=test/bars640`, `calib_seconds=0.1`, `seconds=0.2`, `layout=tt-um-43` and the passed `harness`;
    - META(close) has `status=ok`, and `frames` and `capture_after_clock` equal to timing.json's.
  - `test_trace_no_sync_is_closed`: exit 3, META(close) has `status=no-sync` and `frames=0`.
  - `test_trace_sigterm_is_closed`: `--seconds 30`, SIGTERM after 2 s. The stream ends with META(close) `status=sim-timeout`.
  - `test_tb_frame_hashes_moved`.
  - `test_trace_refuses_fractional_clock`: exit 2 before simulating.
  - `test_trace_refuses_duplicate_meta`: exit 2.
  - `test_ignore_sigterm_hook_absent_in_production`: a model built without `-DTTVGA_TEST_HOOKS` and run with `TTVGA_TB_IGNORE_SIGTERM=1` still stops on SIGTERM with `status=sim-timeout`.
  - `test_no_trace_without_option`.
- [ ] **Step 2: Run** `tests/sim/test_tb_trace.py`: 9 fail.
- [ ] **Step 3: Implement.** The push is the inline `vgacap_trace_push`, with branch-free packing.
- [ ] **Step 4: Run:** pass. Also time `bars640` at `--seconds 2` with and without `--trace`: 3 interleaved runs each, `/usr/bin/time -v` into the log. Put the ns/clock difference in the commit message.
- [ ] **Step 5: Commit and push.**

### Task 4: `tracetool` (info, slice, uohash)

**Files:**
- Create: `ttvga/harness/tracetool.c` (C99, `-Wall -Wextra -Werror`).
- Modify: `ttvga/remote.py` (bootstrap builds it after vgacap), `ttvga/devtools.py`, `ttvga/harness/vgacap_path.py`.
  - The build is `cc -std=c99 -O2 -I<src>/include -I<src>/third_party/sha256 tracetool.c`, then the trace, stream, sha256 and zstd static libraries of the vgacap build, then `-pthread -o <build>/tracetool`.
  - The library paths are found in the build tree, not guessed.
- Test: `tests/sim/test_tracetool.py`.

**Interfaces:**
- Produces:
  - **`tracetool info TRACE`** prints `key: value` lines:
    - the header fields, `samples`, `clocks`, `blocks`, `table_rebuilt`;
    - every META(open) and META(close) key, as `open.<key>` and `close.<key>` (`close.status: truncated` when there is none);
    - `changes.<port>: <n>` for each tt-um-43 port except `clk`.
  - **`tracetool slice TRACE --from CLOCK --to CLOCK --out PATH`**: a trace of samples `[2*from, 2*to)`, renumbered from sample 0.
    - META(open) is copied, with `slice_from_clock` and `slice_to_clock` added.
    - META(close) is written only when the original has one, with the original's `status`, `capture_after_clock=0` and `frames=0`. The slice of a truncated trace has none, so it reads as truncated by the format's own rule.
    - Exit 2 if the range is empty or past the end.
  - **`tracetool uohash TRACE [--clocks N]`** prints `uo_out_sha256_clocks: 0 <M>` and `uo_out_sha256: <64 hex>`.
    - It is SHA-256 over byte `c` = `uo_out` of sample `2c + 1`, for `0 <= c < M`, the half-open clock range `[0, M)`.
    - `M = min(N, clocks in trace)`, with `N` default 33,554,432 (2^25).
- [ ] **Step 1: Write the failing tests:**
  - `test_info_on_killed_trace`: `bars640`, `--seconds 30 --trace`. Poll every second (each poll logged): copy the growing file and run `tracetool info` on the copy, which rebuilds the table; once the copy reports `blocks >= 2`, SIGKILL the model (bounded: fail the test after 120 s). Expected: `table_rebuilt: 1`, `close.status: truncated`, `blocks >= 1`. A SIGTERMed run gives `table_rebuilt: 0` and `close.status: sim-timeout`.
  - `test_info_counts`: on `uio_echo`, `changes.ui_in: 0`, `changes.rst_n: 1`, `clocks == samples / 2`.
  - `test_slice_round_trip`: slice `[1000, 2000)` of `bars640`.
    - The VCDs of the slice and of the same range of the original (`vgacap-export`) have identical value changes once each VCD time is turned back into a sample number by the trace's time rule.
    - The slice's samples are the original's minus 2000.
  - `test_slice_of_truncated_has_no_close`.
  - `test_uohash_matches_python`: a Python reference over `tests/sim/vgch.py`'s reading, `M = 50,000`.
- [ ] **Step 2: Run:** 5 fail.
- [ ] **Step 3: Implement** on `vgacap_trace_read_runs`.
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 5: tb-v1 against `tb.cpp`, and vgacap's Task 18 vectors

**Files:**
- Create: `tests/sim/test_tbv1_matches_tb.py`, `scripts/export_tbv1_vectors.py`.

**Interfaces:**
- Consumes: Task 3's designs; `vgacap-sample TRACE --out DIR --name PREFIX --sampler tb-v1`.
- Produces:
  - **The comparison test.** For every Task 3 design, `vgacap-sample --sampler tb-v1` on the trace must give:
    - hash lines in `tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` equal to `tb_frame_hashes.txt`, line for line;
    - `frames`, `mode`, `width`, `height` and `capture_after_clock` equal to timing.json's (read with `vgacap.framesfile.read_hash_file`);
    - `clocks_per_pixel` within 5e-5 of timing.json's 4-decimal value.
  - **`scripts/export_tbv1_vectors.py --out tmp/tbv1-vectors`.** For the cases `bars640`, `bars_cpp2`, `frac`, `glitch`, `nosync` and `playground` it writes:
    - `<case>/trace.vgch`: `zstd -d` of the trace;
    - `<case>/frames.txt` and `<case>/frame_hashes.fnv1a64-tb2026-rgb888.txt`: from `vgacap-sample --sampler tb-v1` on `trace.vgch`, after the test above has passed;
    - `MANIFEST.txt`: `<sha256>  <case>/<file>` lines, then `generator: tinytapeout-vga-videos <commit>` and `vgacap: <pin>`.
    - Each `trace.vgch` is at most 1 MiB. The script fails otherwise; shorten that case's `--seconds`, but never below 2 captured frames.
- [ ] **Step 1: Write the test.**
- [ ] **Step 2: Run** it (`-m sim`): it should pass.
  - A difference is a tb-v1 port bug. Stop, write the case to `tmp/tbv1-mismatch/` and report it to the controller for the vgacap session.
  - Do not change `tb.cpp`.
- [ ] **Step 3: Run the export script** (log to `tmp/t5.log`).
- [ ] **Step 4: Commit and push** the test and the script, not the vectors.
- [ ] **Step 5: Hand off** (controller): message the vgacap session ("Tiny Tapeout board direct VGA capture") with:
  - the absolute path of `tmp/tbv1-vectors/` in this worktree and the commit;
  - that vgacap Task 18 copies `<case>/{trace.vgch,frames.txt,frame_hashes.fnv1a64-tb2026-rgb888.txt}` to `vgacap/tests/vectors/tbv1/<case>/`;
  - that `MANIFEST.txt` has the checksums.

## Phase 3: deriving and publishing

### Task 6: host config and the publishing primitives

**Files:**
- Create: `ttvga/harness/hostconf.py`, `ttvga/harness/publish.py`.
- Test: `tests/test_publish.py`.

**Interfaces:**
- Produces:
  - **`hostconf.HostConfig(frames_root: Path, staging_dir: Path, min_free_root_gb: float)`** and **`hostconf.load(root: Path) -> HostConfig`**, which reads `<root>/host.toml`. It raises `hostconf.ConfigError` naming the key or the reason when:
    - the file or a path key is missing (`min_free_root_gb` defaults to 100.0 until Task 20 sets it);
    - `frames_root` lacks the marker file `.ttvga-frames-root` (created once by Task 18's setup);
    - `frames_root` holds `index.html` or `index.json` (it would be the archive itself);
    - `staging_dir` is inside `frames_root`;
    - the two are on different filesystems (`st_dev`).
  - **`publish.ALLOWED`**: the only names scratch may hold:
    - `<stem>_trace.vgch.zst`;
    - `<sampler>/frames.txt`, `<sampler>/frame_hashes.<method>.txt`, `<sampler>/<stem>_<sampler>_frames.rgb6.zst`, `<sampler>/index.html` and `<sampler>/png/NNNNNN.png`, for `<sampler>` in `tb-v1` and `centre-v1`;
    - `tb-v1/TRACE_SHA256`.
    - `publish.check_allowed(scratch, stem) -> list[str]` returns the violations (also symlinks, devices and anything not a regular file or directory).
  - **`publish.exchange(a: Path, b: Path) -> bool`**: `renameat2(AT_FDCWD, a, AT_FDCWD, b, RENAME_EXCHANGE)` through `ctypes.CDLL(None, use_errno=True)`. It returns False only on `ENOSYS` or `EINVAL` (not supported) and raises `OSError` otherwise.
  - **`publish.install(scratch: Path, conf: HostConfig, shuttle: str, macro: str, log: Path, carry: list[str] = ()) -> None`**, in this order:
    1. refuse, with `PublishError`, an allow-list violation, or a published `<frames_root>/<shuttle>/<macro>` that exists but lacks the marker `.ttvga-frames`, or that holds anything named `*.bin` or `fpga*`;
    2. `os.umask(0o022)`, and create `<frames_root>/<shuttle>` if missing;
    3. remove a leftover `<staging>/<shuttle>_<macro>.new` or `.old`;
    4. `rsync -aH --delete scratch/ <staging>/<shuttle>_<macro>.new/`, and write the marker `.ttvga-frames` into it;
    5. for each name in `carry`, `cp -al <published>/<name> <staging>/<shuttle>_<macro>.new/<name>` (same filesystem);
    6. `exchange` with the published directory if it exists, else `os.rename`, then delete the old one;
    7. if `exchange` is unsupported: rename the old one to `.old`, rename the new one into place, delete `.old`;
    8. append `<ISO time> <shuttle>/<macro>\n` to `<staging_dir>/changed.log` in one `os.write` on an `O_APPEND` descriptor (Task 19 reads it).
- [ ] **Step 1: Write the failing tests**, all under `tmp/pytest`:
  - `test_install_new_project`;
  - `test_install_replaces_with_exchange`;
  - `test_install_keeps_hard_links`;
  - `test_install_fallback_two_renames` (monkeypatched `exchange`);
  - `test_install_recovers_leftover_old`;
  - `test_install_carries_tb_v1` (a published `tb-v1/` with `carry=["tb-v1"]` appears in the new directory with the same inodes);
  - `test_swap_never_exposes_partial_directory`: a thread lists the published directory in a loop during 50 installs of a 200-file tree, and every listing is the complete old set or the complete new set;
  - `test_modes_are_0644_0755`;
  - `test_install_refuses_unmarked_directory` (and one holding `x.bin`);
  - `test_install_refuses_disallowed_file` (a `../x`-style name, a symlink, `notes.txt`);
  - `test_changed_log_lines_are_whole`;
  - `test_load_requires_paths`;
  - `test_load_refuses_archive_root` (an `index.json` in `frames_root`);
  - `test_load_refuses_unmarked_root`;
  - `test_load_refuses_two_filesystems` (monkeypatched `os.stat`).
- [ ] **Step 2: Run:** 15 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 7: PNGs and pages

**Files:**
- Create: `ttvga/harness/pngio.py`, `ttvga/harness/pages.py`.
- Test: `tests/test_pngio.py`, `tests/test_pages.py`, and fixtures:
  - `tests/fixtures/frames/{bars640,glitch}/frames.txt`, written by `vgacap-sample` on Task 3's traces and committed;
  - `tests/sim/test_fixtures_current.py`, which regenerates them and compares.

**Interfaces:**
- Consumes: `vgacap.framesfile.read_frames_txt(path) -> FramesFile`, with fields `frames: list[Frame]`, `distinct`, `frame_clocks`, ... (vgacap `python/vgacap/framesfile.py`).
- Produces:
  - `pngio.PALETTE: bytes`: 64 RGB entries, entry `i` = `((i>>4)&3)*85, ((i>>2)&3)*85, (i&3)*85`.
  - `pngio.write_rgb6(path, width, height, rgb6: bytes, level: int = 1) -> None`: 8-bit indexed, `PLTE` of 64 entries, filter 0, `zlib`.
  - `pngio.read_rgb6(path) -> tuple[int, int, bytes]`: it accepts only what `write_rgb6` writes, else `ValueError`.
  - `pages.write_sampler_page(dir: Path, ff: FramesFile, stem: str, sampler: str) -> None` writes `dir/index.html`:
    - the captured frames as one row per run of identical frames: "frames `first`-`last`", the start clock of `first`, the distinct number linking `png/<n>.png`, or `-` for a gap. Every frame number is findable by its range. This is the chosen form of the spec's "every captured frame", and it keeps a 3,600-frame page small;
    - the distinct frames as a grid of `<img loading="lazy">`;
    - `#1x`/`#2x`/`#4x` views with CSS `:target` and `image-rendering: pixelated`;
    - no scripts.
- [ ] **Step 1: Write the failing tests:**
  - `test_png_round_trip_is_byte_identical` (random rgb6 at 640x480, 1x1 and 1280x1024);
  - `test_png_palette_index_is_rgb6`;
  - `test_read_refuses_other_pngs`;
  - `test_page_has_no_script_and_links_every_distinct_png`;
  - `test_page_rows_are_runs_and_cover_every_frame` (glitch fixture: gap rows say `-`).
- [ ] **Step 2: Run:** 5 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** both suites (`-m sim` for the fixture test): pass.
- [ ] **Step 5: Commit and push.**

### Task 8: the derive step

**Files:**
- Create: `ttvga/harness/derive.py`.
- Test: `tests/sim/test_derive.py`, `tests/test_derive_unit.py`.

**Interfaces:**
- Consumes:
  - Tasks 4, 6 and 7.
  - `vgacap-sample TRACE --out DIR --name PREFIX [--sampler tb-v1] [--sampler centre-v1] [--centre-window DX,DY] [--store-level N] [--png-fd FD]`. Exit 0, 1 or 2. A bad window exits 1 after writing every file.
  - `vgacap.framesfile`.
- Produces:
  - `derive.Tools(vgacap_sample: Path, tracetool: Path)`.
  - `derive.derive(trace: Path, out: Path, stem: str, *, tb_v1: bool, centre_window: tuple[int, int] | None, store_level: int | None, tools: Tools, log: Path, tb_hashes: Path | None) -> DeriveResult`. In order, it:
    1. refuses a trace whose `tracetool info` has `open.slice_from_clock` (`DeriveError`);
    2. computes `trace_sha` (`hashlib.sha256`, 1 MiB reads);
    3. runs `vgacap-sample <trace> --out <out> --name <stem> --sampler centre-v1 [--sampler tb-v1] [--centre-window DX,DY] [--store-level N] --png-fd <w>`. A reader thread parses each record (`"<sampler> <distinct> <width> <height>\n"` + `w*h` bytes) and writes `<out>/<sampler>/png/<distinct:06d>.png`. A frame with the same `(width, height, sha256(rgb6))` as an earlier PNG is hard-linked to it instead of encoded again;
    4. writes `pages.write_sampler_page` for each sampler;
    5. runs `tracetool uohash`;
    6. with tb-v1, writes `<out>/tb-v1/TRACE_SHA256` (the hex and a newline);
    7. sets `tb_v1_check`: `match` or `mismatch` when `tb_v1` and `tb_hashes` exist (hash lines compared line for line); `not-run` when `tb_v1` without `tb_hashes`; `off` when not `tb_v1`.
  - `DeriveResult(samplers: dict[str, dict], trace_sha: str, uo_out_sha256: str, uo_out_sha256_clocks: tuple[int, int], tb_v1_check: str, error: str | None, cpu_seconds: float, pngs_written: int, pngs_linked: int)`. `samplers[s]` is `{sampler_status, frames, distinct_frames, mode, width, height, clocks_per_pixel}` from `vgacap.framesfile.read_frames_txt`.
  - `error` is set for:
    - `vgacap-sample` exit 2, or exit 1 other than a bad window: stderr's last line;
    - `centre-v1/frames.txt` `sampler_status: bad-window` (Ruling U): `"centre_window <dx>,<dy> does not fit"`, with vgacap-sample's message appended;
    - `tb_v1_check == "mismatch"`: `"tb-v1 differs from tb.cpp at frame <k>"`.
- [ ] **Step 1: Write the failing tests** (`-m sim` unless noted):
  - `test_derive_centre_only_by_default`:
    - on `bars640`, `out/centre-v1/` holds `frames.txt`, `frame_hashes.sha256-rgb6.txt`, the store, `index.html` and `png/`;
    - there is no `out/tb-v1`, and `tb_v1_check == "off"`;
    - each PNG equals the store's bytes at `n * w * h` (store read with `compression.zstd`).
  - `test_derive_tb_v1_on_request_links_identical_pngs`: `match`, hard links, and `TRACE_SHA256` equal to `trace_sha`.
  - `test_derive_tb_v1_mismatch_fails`: a doctored `tb_hashes`.
  - `test_derive_no_sync_writes_empty_files`.
  - `test_derive_truncated_trace`: a trace killed as in Task 4's `test_info_on_killed_trace` gives `status: truncated` and `frames > 0`.
  - `test_derive_bad_window_is_an_error`: `centre_window=(400, 0)` sets the error, and centre-v1 still has `frames: 0`.
  - `test_derive_refuses_a_slice` (unit, stub `tracetool`).
- [ ] **Step 2: Run:** 7 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 9: `job.py`: trace, derive, publish

**Files:**
- Modify: `ttvga/harness/job.py`.
- Create: `tests/sim/jobroot.py`: `make_root(tmp: Path, dev: DevTools) -> Path` builds a local `--root`:
  - `tools/oss-cad-suite` is a symlink to the dev tools' oss-cad-suite;
  - `tools/ffmpeg/bin/ffmpeg` is a symlink to `/usr/bin/ffmpeg` (the encode stage transcodes for real);
  - `tools/vgacap-src` and `tools/vgacap-build` are symlinks to the dev tools;
  - `harness/HARNESS_VERSION` holds `test`;
  - `host.toml` points at a marked `frames` directory and a staging directory under `tmp/pytest`;
  - `targets.json` holds `file://` git repositories made from `tests/sim/designs/`.
- Test: `tests/sim/test_job.py`, `tests/test_job_unit.py`.

**Interfaces:**
- Consumes: Tasks 3, 6, 7 and 8; `vgacap_path`.
- Produces:
  - **The `tools` dict** of `main()` gains `vgacap_sample`, `vgacap_export`, `tracetool`, `vgacap_src` and `vgacap_build`, from `vgacap_path.tools(args.root)`. `vgacap_path.add(args.root)` runs at start-up.
  - **`build()`** adds `vgacap_link_flags`.
  - **`src_dir`.** `build()` and `simulate()` use `target.get("src_dir", "src")`, in both places (sources and the model's cwd).
  - **`model_cmd(..., trace: Path | None)`** adds `--trace <trace>` and the `--meta` arguments:
    - `project=<id>`;
    - `override=<shuttle>/<macro>.json sha256:<12 hex of the compiled override, or none>`;
    - `simulator=<first line of verilator --version>`;
    - `harness=<HARNESS_VERSION>`.
    - Probe runs pass no trace. After a successful probe, the first run's trace is deleted before the re-run.
  - **`--grace SECONDS`**: default 120, the simulation's SIGTERM-to-SIGKILL grace.
  - **`--test-hooks`** (test-only, default off): `build()` then adds `-CFLAGS -DTTVGA_TEST_HOOKS` to its Verilator command (after `vgacap_link_flags`' `-CFLAGS`), compiling in Task 3's SIGTERM hook; `result.json` records `test_hooks: true`, and Task 16's `verify` treats a published project with `test_hooks: true` as a failure. Without the flag the command is unchanged (`test_vgacap_link_flags` also checks the define is absent).
  - **Scratch.** `work/scratch/` is the project's output directory: the trace, plus `<sampler>/...`. Each job creates it fresh and deletes it at the end on every path.
  - **Stages:** `STAGES = ("fetch", "build", "simulate", "derive", "encode", "publish")`.
    - A model killed with a trace left, which leaves no timing.json (or an empty one), still goes through `derive` and `publish`, and the job then returns the original error.
    - No-sync and bad-timing: derive, skip encode, publish.
    - An encode failure: the error is recorded and `publish` still runs.
    - The failures (fetch, build, a simulation with no trace, a derive `error`, a `PublishError`): `publish` does not run, the previous published directory is untouched, and `work/frames/` is untouched.
  - **`work/frames/`.** On a successful derive the job copies `scratch/centre-v1/frames.txt` to `work/frames/centre-v1/frames.txt`, replacing it. With tb-v1 it copies `frames.txt` and the FNV file to `work/frames/tb-v1/`, replacing them. `work/frames/tb-v1/` is otherwise left as it is.
  - **The tb-v1 flags.** `--tb-v1` and `--drop-tb-v1`, both default off; together they exit 2. They drive the `tb_v1` rule of Global Constraints:
    - With `--tb-v1`: state `current`, with this trace's SHA.
    - Neither flag, with a published `tb-v1/`: `carry=["tb-v1"]` goes to `publish.install`. The state is `current` if its `TRACE_SHA256` equals this run's `trace_sha`, else `stale` with that SHA.
    - Neither flag, with no published `tb-v1/` but `work/frames/tb-v1/` present (seeded by Task 17): state `stale`, `trace_sha` null.
    - Neither flag and neither present: state `none`.
    - `--drop-tb-v1`: no carry. Remove `work/frames/tb-v1/`. Set `{"state": "none", "trace_sha": null, "dropped": true}`.
  - **`result.json`** gains:
    - `harness` (`HARNESS_VERSION`);
    - `tb_v1`;
    - `tb_v1_check`;
    - `trace` = `{"file", "sha256", "bytes", "blocks", "clocks", "uo_out_sha256", "uo_out_sha256_clocks": [0, M]}`;
    - `samplers`;
    - `timings.derive` and `timings.publish`;
    - `derive_cpu_seconds`;
    - `published` (true only when `publish` ran).
    - `timing.frame_hashes_count` is no longer written.
  - **`testpatterns`.** Derive runs, but there is no encode and no publish. Scratch moves to `work/kept/`.
  - **umask** 022 throughout.
- [ ] **Step 1: Write the failing tests:**
  - `test_job_publishes_trace_and_centre_v1`;
  - `test_job_tb_v1_on_request` (`tb_v1.state == "current"`);
  - `test_job_default_rerun_keeps_tb_v1_stale`: a `--tb-v1` run, then a default run of a changed design. `tb-v1/` and `work/frames/tb-v1/` are byte-identical to before, the state is `stale` with the first trace's SHA, and centre-v1 is replaced;
  - `test_job_default_rerun_keeps_seeded_tb_v1`: `work/frames/tb-v1/` seeded by hand. The file is unchanged and the state is `stale` with `trace_sha` null;
  - `test_job_drop_tb_v1` (and `--tb-v1 --drop-tb-v1` exits 2);
  - `test_job_probe_keeps_only_the_rerun_trace` (add `tests/sim/designs/needs_ui2.v`, which syncs only with `ui_in = 0x04`): `auto_ui_in == 4`, one trace, `ui_in` 0x04 from clock 0;
  - `test_job_killed_model_samples_truncated_trace`: `--test-hooks`, `TTVGA_TB_IGNORE_SIGTERM=1`, `--timeout 5 --grace 1`. Expected: `error == "wall-clock limit"`, `published: true`, and published `centre-v1/frames.txt` says `status: truncated`;
  - `test_job_no_sync_publishes_trace_only`;
  - `test_job_failure_keeps_previous_output`: a publish, then the `skip` override. The published directory and `work/frames/` are unchanged and `published: false`;
  - `test_job_mismatch_publishes_nothing` (a monkeypatched derive returning the error);
  - `test_job_encode_failure_still_publishes`;
  - `test_job_testpatterns_not_published` (unit);
  - `test_vgacap_link_flags` (unit).
- [ ] **Step 2: Run** `tests/sim/test_job.py` and `tests/test_job_unit.py`: 13 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass. Then the whole suite.
- [ ] **Step 5: Commit and push.**

### Task 10: re-deriving, the queue and scopes

**Files:**
- Modify: `ttvga/harness/job.py`, `ttvga/harness/runqueue.py`, `ttvga/remote.py`.
- Test: `tests/sim/test_rederive.py`, `tests/test_runqueue.py`.

**Interfaces:**
- Produces:
  - **`job.py --rederive`.**
    - It skips the start-up removal of `result.json`, `build.log` and `sim.log`, and skips fetch, build and simulate.
    - It reads the published `<frames_root>/<shuttle>/<macro>/<stem>_trace.vgch.zst` (error `"no published trace"`) and copies it into scratch.
    - It runs `derive` with the current override's `centre_window` and the tb-v1 flags (`tb_hashes` None, so `--tb-v1` gives `tb_v1_check: not-run`), applies Task 9's carry and `tb_v1` rules, and publishes.
    - It refreshes `work/frames/` as Task 9 does.
    - It updates `result.json` in place: `samplers`, `trace`, `tb_v1`, `tb_v1_check`, `rederived_at` (ISO UTC), `timings.rederive`, `harness`. Everything else is kept.
  - **`runqueue.py`** gains:
    - `--rederive`: selects projects whose `result.json` has `trace`;
    - `--tb-v1` and `--drop-tb-v1`, passed on, plus `--timeout`;
    - `--redo-unless-harness VERSION`: re-run a project unless its `result.json` has `trace`, `harness == VERSION` and, with `--tb-v1`, `tb_v1_check == "match"`. This lets a crashed re-run restart where it stopped;
    - a free-space wait before each job: while `shutil.disk_usage(root).free < min_free_root_gb * 1e9`, it logs `waiting for free space: <n> GB free, need <m>` once a minute.
  - **Scopes.** Each job runs as `systemd-run --user --scope --quiet --collect --unit ttvga-job-<shuttle>-<macro> -p MemoryMax=<mem> -p CPUQuota=<cpu> -p TasksMax=64 -- <host python> job.py ...`.
    - `--scope-memory` defaults to `6G`, and `--scope-cpu` to `200%`.
    - A preflight runs `systemd-run --user --scope true`. If it fails, the queue exits with that error. There is no unconfined fallback.
  - **`tt-vga queue start`** passes `--rederive`, `--tb-v1`, `--drop-tb-v1` (which also requires `--yes-drop-tb-v1`), `--redo-unless-harness`, `--scope-memory` and `--scope-cpu` through.
- [ ] **Step 1: Write the failing tests:**
  - `test_rederive_reproduces_frames` (`-m sim`: every `frames.txt` and hash file is byte-identical, and `rederived_at` is set);
  - `test_rederive_applies_centre_window` (`-m sim`);
  - `test_rederive_keeps_tb_v1_current` (`-m sim`: a `--tb-v1` job, then a default `--rederive` of the same trace. tb-v1 files are unchanged and the state is `current`);
  - `test_queue_waits_for_free_space`;
  - `test_queue_job_command_is_a_scope`;
  - `test_queue_refuses_without_user_manager`;
  - `test_queue_redo_unless_harness_skips_done`;
  - `test_queue_refuses_test_hooks`.
- [ ] **Step 2: Run:** 8 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 11: `collect`, and the end of `framehashes.py`

**Files:**
- Modify: `ttvga/remote.py` (`collect`).
- Create: `ttvga/harness/list_results.py`.
- Delete: `ttvga/framehashes.py`, `tests/test_framehashes.py`.
- Test: `tests/test_collect.py`.

**Interfaces:**
- Produces:
  - **`remote.host_listing(host) -> HostListing`**: one SSH step that prints:
    - `find ~/ttvga/work -mindepth 5 -maxdepth 5 -path '*/*/*/frames/*/*' -type f`, giving `<s>/<m>/frames/<sampler>/<file>` paths only (never `repo/` or `build/`);
    - from a small script file, `ttvga/harness/list_results.py`, run under the host Python: for each `work/<s>/<m>/result.json`, parsed with `json.load` (a file that does not parse is listed as an error, logged), one JSON line `{"id", "harness": bool, "dropped": bool}` (`harness` is whether the parsed object has the key; `dropped` is `tb_v1.dropped`).
    - The result is `HostListing(new_results: set[str], frames_files: dict[str, set[str]], dropped: set[str])`.
  - **`remote.collect_filter(listing) -> list[str]`**: rsync arguments with `--files-from`:
    - `<id>/result.json` for ids in `new_results` only. An old-pipeline host result, with its full hash list and no `tb_v1`, never overwrites a converted local one;
    - every path in `frames_files` that matches exactly `^[A-Za-z0-9_]+/[A-Za-z0-9_]+/frames/(centre-v1|tb-v1)/frames\.txt$` or `^[A-Za-z0-9_]+/[A-Za-z0-9_]+/frames/tb-v1/frame_hashes\.fnv1a64-tb2026-rgb888\.txt$`;
    - never anything under `/testpatterns/`, `scratch/` or `kept/`.
  - **`remote.remove_stale_frames(results: Path, listing) -> list[Path]`**: for ids in `new_results`, it deletes local `frames/centre-v1/*` files the host lacks. It deletes `frames/tb-v1/*` only for ids in `dropped`. It returns what it removed.
  - There is no more `framehashes.export`.
- [ ] **Step 1: Write the failing tests** (real `rsync` between two `tmp/pytest` trees):
  - `test_collect_filter_ignores_scratch_and_old_results`: `scratch/centre-v1/frames.txt` is not copied, and an old host `result.json` holding `timing.frame_hashes` does not replace the local one;
  - `test_collect_never_removes_tb_v1_without_drop`: the host has no `frames/tb-v1/`, and the local converted file stays;
  - `test_collect_removes_tb_v1_after_drop`;
  - `test_collect_leaves_out_testpatterns`;
  - `test_collect_ignores_frames_named_files_in_repo` (a `repo/x/frames/centre-v1/frames.txt` on the host side is never collected);
  - `test_list_results_parses_json` (a result whose log tail contains the text `"harness"` but has no such key is `harness: false`);
  - `test_collect_no_longer_imports_framehashes`.
- [ ] **Step 2: Run:** 7 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 12: extra targets, `src_dir`, `centre_window`, `testpatterns`

**Files:**
- Create: `data/extra-targets.json`; `overrides/testpatterns/tt_um_vgacal_{bars,grid,prbs,counter}.yaml`; `overrides/testpatterns/tt_um_vgacal_modes_{m0,m1,m2,m0_hneg,m0_vneg,m0_hvneg}.yaml`.
- Modify: `ttvga/targets.py`, `ttvga/overrides.py` (`"centre_window"` in `PLAIN_KEYS`, validated as `{dx: int, dy: int}`), `ttvga/index.py`, `ttvga/report.py`.
  - `ttvga/analyze.py` needs no change: it reads `data/results/`, and `collect` never brings `testpatterns` there (Task 11).
- Test: extend `tests/test_targets.py`, `tests/test_overrides.py`, `tests/test_index.py`.

**Interfaces:**
- Produces:
  - **`data/extra-targets.json`**: `{"targets": [...]}` in `data/targets.json`'s record format:
    - shuttle `testpatterns`;
    - `repo` `https://github.com/mithro/tt-vga-testpatterns`, `commit` its current `main` SHA;
    - `src_dir` `designs/<design>/src`;
    - `top_module`, `source_files` and pinout from each design's `info.yaml`;
    - `clock_hz` 25,175,000.
    - The macros are the four other designs, plus six `tt_um_vgacal_modes` pseudo-macros (`top_module tt_um_vgacal_modes`): `m0` (`ui_in` 0), `m1` (1), `m2` (2, 720x400@70), `m0_hneg` (4), `m0_vneg` (8), `m0_hvneg` (12).
  - `targets.write_targets` merges it. A duplicate `id` is an error.
  - `targets.PUBLISHED_EXCLUDED_SHUTTLES = ("testpatterns",)`: `index.py` and `report.py` skip it.
  - Each `overrides/testpatterns/<macro>.yaml` sets `ui_in` only.
- [ ] **Step 1: Write the failing tests:**
  - `test_extra_targets_merged`;
  - `test_extra_target_duplicate_id_fails`;
  - `test_centre_window_passes_through`;
  - `test_centre_window_rejects_non_int`;
  - `test_index_and_report_leave_out_testpatterns`.
- [ ] **Step 2: Run:** 5 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass. Then `uv run tt-vga targets >> tmp/t12.log 2>&1` and commit the regenerated `data/targets.json`.
- [ ] **Step 5: Commit and push.**

### Task 13: `tt-vga trace` and `tt-vga sample`

**Files:**
- Create: `ttvga/traces.py`.
- Modify: `ttvga/cli.py`.
- Test: `tests/sim/test_traces_cli.py`.

**Interfaces:**
- Produces:
  - `tt-vga trace info TRACE`.
  - `tt-vga trace export TRACE --format fst|vcd --out FILE [--from C] [--to C] [--no-clk] [--sampler-frames FRAMES_TXT]`, a wrapper over `vgacap-export` (`--sampler-frames` is its `--frames`).
  - `tt-vga trace slice TRACE --from C --to C --out PATH`.
  - `tt-vga sample TRACE --out DIR [--sampler ID]... [--centre-window DX,DY] [--name PREFIX]`: Task 8's `derive`, run locally. The default prefix comes from META(open) `project`. `--help` says that one host project is re-derived with `tt-vga queue start --rederive --only <id>`.
- [ ] **Step 1: Write the failing tests:**
  - `test_export_fst_equals_vcd` (`fst2vcd` value changes);
  - `test_sample_writes_both_on_request`;
  - `test_slice_then_export`.
- [ ] **Step 2: Run:** 3 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 14: `tt-vga frames` to-png, from-png, hash, diff

**Files:**
- Create: `ttvga/frames.py`.
- Test: `tests/test_frames_cli.py`, `tests/sim/test_frames_hash.py`.

**Interfaces:**
- Consumes: `vgacap.framesfile` (`read_frames_txt`, `HashFile.from_frames`, `write_hash_file`) and `vgacap.hashes` (`sha256_rgb6`, `fnv1a64_tb2026_rgb888`).
- Produces:
  - `tt-vga frames to-png FRAMES_TXT --out DIR`.
  - `tt-vga frames from-png DIR --frames FRAMES_TXT --out STORE`, written with `compression.zstd`.
  - `tt-vga frames hash FRAMES_TXT --method ID --out FILE`:
    - It hashes each distinct frame with `vgacap.hashes` and writes through `vgacap.framesfile.write_hash_file(HashFile.from_frames(...))`, so the file is byte-identical to `vgacap-sample`'s.
    - FNV in Python is slow (about 0.15 s per 640x480 frame); `--help` says so.
  - `ttvga.frames.load_frame(spec: str) -> tuple[int, int, bytes]`, for `STORE:N`, `STORE@F` or a PNG.
  - `tt-vga frames diff A B --out DIR` prints:
    - `differing_pixels`;
    - `bbox: x0 y0 x1 y1` (exclusive end);
    - `per_channel: r <n> g <n> b <n>`;
    - up to ten `<a> -> <b>: <count>` lines;
    - and writes `a.png`, `b.png` and `mask.png`.
    - Different shapes exit 1.
- [ ] **Step 1: Write the failing tests:**
  - `test_to_png_from_png_round_trip`;
  - `test_hash_matches_vgacap_sample` (`-m sim`, both methods);
  - `test_diff_counts_and_bbox`;
  - `test_diff_shape_mismatch`;
  - `test_load_frame_captured_vs_distinct`.
- [ ] **Step 2: Run:** 5 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 15: `tt-vga frames compare`

**Files:**
- Modify: `ttvga/frames.py`.
- Test: `tests/test_frames_compare.py`.

**Interfaces:**
- Produces: `ttvga.frames.compare(a: Path, b: Path) -> Comparison` and `tt-vga frames compare RUN_A RUN_B`.
  - **Inputs.** RUN is a `frames.txt` or a hash file, read with `vgacap.framesfile`.
    - Two hash files must share a method.
    - A `frames.txt` compares against a `sha256-rgb6` file only; anything else exits 2.
    - A gap is "no data", never a mismatch.
  - **`Comparison`** has `first_mismatch: int | None`, `offset: int | None`, `start_clock_deltas: dict[int, int] | None`, `frames_a`, `frames_b`, `gaps_a`, `gaps_b`.
  - **Rule.**
    1. Find the first frame `k` where both have data and differ.
    2. Then find the constant offset `d`, with `|d| <= 120`: smallest `|d|` first, negative before positive. Every `j >= k` with data in both `a[j]` and `b[j + d]` must agree, over at least 10 pairs.
    3. With two `frames.txt`, also build the histogram of start-clock differences.
  - **Output:**
    - `first_mismatch`, `offset`, and up to five `start_clock_delta: <delta> x<count>` lines;
    - with the stores present, `frames diff` of the first mismatching pair;
    - with the traces present, `trace_range_a/b: --from <c> --to <c + frame_clocks>`.
- [ ] **Step 1: Write the failing tests.** The input files are built with `vgacap.framesfile.write_frames_txt`.
  - `test_identical`;
  - `test_shift_by_3`;
  - `test_shift_negative`;
  - `test_real_difference_no_offset`;
  - `test_gaps_are_not_mismatches`;
  - `test_start_clock_deltas`;
  - `test_methods_must_match`.
- [ ] **Step 2: Run:** 7 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 16: `verify`, the FPGA files in the archive, index links

**Files:**
- Modify: `ttvga/harness/verify.py`, `ttvga/remote.py` (`mirror`, `verify`), `ttvga/index.py`.
- Test: `tests/test_verify_listing.py`, `tests/test_mirror.py`, extend `tests/test_index.py`.

**Interfaces:**
- Produces:
  - **`verify.FOREIGN_PATTERNS = ("*/*/*.bin", "fpga-library.json")`**, relative to the archive root (Ruling AA). These are the FPGA session's bitstreams `<id>-<sha256[:12]>.bin` in each `<shuttle>/<macro>/`, and its library file.
    - `verify.stale_on_server` and every completeness check skip them.
    - `tt-vga mirror` keeps never deleting (no `--delete`, pinned by a test). It adds `--exclude /*/*/*.bin --exclude /fpga-library.json --exclude /frames/`, so it never writes over those files or the frames subtree.
    - It refuses a `--dest` that holds `.ttvga-frames-root`.
  - **`verify.server_listing(base_url, path, fetch=urllib.request.urlopen) -> tuple[set[str], set[str]]`** parses the server's autoindex HTML. **`verify.stale_on_server(local, base_url, roots) -> list[str]`** walks it recursively. They are run by `tt-vga verify --server-stale URL`, and print `stale on server (remove by hand):`. They never delete.
  - **`verify.py` on the host**, for each project under `frames_root`:
    - the trace is present and non-empty;
    - each sampler directory has `frames.txt`, `index.html` and the store, with a `png/` count equal to `distinct_frames`;
    - a `result.json` with `published: false` and an `error` prints `<id>: failed (previous output kept): <error>`. This is a failure;
    - a `result.json` with `test_hooks: true` prints `<id>: built with test hooks`. This is a failure;
    - `tb_v1.state == "stale"` prints, under `notes:`, `<id>: tb-v1 files are from trace <trace_sha[:12] or "before traces">, not the current trace`. This is a note, not a failure.
  - **`tt-vga index --fpga-ids FILE`**: an optional list of `<shuttle>/<macro>` ids that have a bitstream in the archive. `tt-vga mirror --fpga-ids-out FILE` makes it on the host with `find <dest> -mindepth 3 -maxdepth 3 -name '*.bin'` (ids taken from the path, logged in full). Each listed row in `index.html` links "FPGA bitstream" to the project's directory in the archive. Nothing here reads `fpga-library.json`; its format is the FPGA session's and the owner's.
- [ ] **Step 1: Write the failing tests:**
  - `test_server_listing_parses_autoindex`, against a saved nginx autoindex page in `tests/fixtures/`;
  - `test_stale_on_server_ignores_bin_and_library`;
  - `test_mirror_excludes_foreign_and_never_deletes`;
  - `test_mirror_refuses_frames_root_dest`;
  - `test_index_links_fpga_when_listed`;
  - `test_verify_frames_completeness`;
  - `test_verify_stale_tb_v1_is_a_note`;
  - `test_verify_failed_project_is_a_failure`;
  - `test_verify_test_hooks_is_a_failure`.
- [ ] **Step 2: Run:** 9 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run:** pass.
- [ ] **Step 5: Commit and push.**

### Task 17: the FNV files move, the host is seeded, the consumer note

**Files:**
- Create: `scripts/convert_frame_hashes.py`, `docs/consumers.md`.
- Move: each of the 408 files `data/results/<s>/<m>/frame_hashes.txt` to `data/results/<s>/<m>/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`.
- Modify: each `result.json` (drop `timing.frame_hashes_count` after the check; add `"tb_v1": {"state": "stale", "trace_sha": null, "dropped": false}`), `README.md` (lines 82-92 rewritten), `PROGRESS.md` (a new entry).
- Test: `tests/test_convert_frame_hashes.py`.

**Interfaces:**
- Consumes: `vgacap.framesfile.HashFile`, `vgacap.framesfile.write_hash_file`, `vgacap.timebase.fmt_double` and `vgacap.tbv1.TB_MODES` (vgacap's copy of `tb.cpp:39-51`, checked equal to the table in this repository's `tb.cpp` by `test_tb_modes_match_tb_cpp`, which parses `tb.cpp`).
- Produces:
  - `convert(old: Path, result: dict) -> HashFile`:
    - `method` `fnv1a64-tb2026-rgb888`;
    - `id`, `status` (timing's), `sampler` `tb-v1`, `sampler_status` `ok`;
    - `mode`, `width`, `height`, `clock_hz` and `capture_after_clock` from the old header;
    - `clocks_per_pixel` recomputed as `tb.cpp` does: `timing.line_clocks / mode.line_px`, with `mode` from `TB_MODES` by name, replaced by its rounded value when within 0.01. A mode named `unknown`, or one missing from the table, makes the script fail (none of the 408 has one);
    - the hash lines unchanged.
    - `write_hash_file` writes it.
  - The script fails if, for any project:
    - the hash lines are not byte-identical to the old file's;
    - their number differs from `timing.frame_hashes_count`;
    - `capture_after_clock` is not a number;
    - `clocks_per_pixel` rounded to 4 decimals differs from timing's.
  - `scripts/convert_frame_hashes.py --seed-host HOST` also rsyncs each converted file to the host's `~/ttvga/work/<s>/<m>/frames/tb-v1/`, as `ttvga` and logged, so the host's copy matches git (C5).
  - `docs/consumers.md`: see Step 4.
- [ ] **Step 1: Write the failing tests:**
  - `test_convert_keeps_hash_lines`;
  - `test_convert_refuses_count_mismatch`;
  - `test_converted_file_reads_back` (`vgacap.framesfile.read_hash_file`);
  - `test_clocks_per_pixel_recomputed` (1525/800 gives `1.90625`; 800/840 gives `0.9523809523809523`);
  - `test_tb_modes_match_tb_cpp`.
- [ ] **Step 2: Run:** 5 fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Write `docs/consumers.md`**, for tt-harness-fpga-vga and tt-harness-handheld-vga, with a link for every file and tool named:
  - **What to read, in git:**
    - `data/targets.json`, skipping `shuttle: testpatterns`;
    - `data/results/<s>/<m>/result.json`: `verdict`, `override`, `auto_ui_in`, `qspi`, `trace`, `samplers`, `tb_v1`, `tb_v1_check`, `published`;
    - `.../frames/<sampler>/frames.txt`;
    - `.../frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt`.
  - **What to read, in the archive** (`https://data.wafer.space/big-storage/tinytapeout-vga-videos/`): the clips in `<s>/<m>/`; the traces, stores, every hash file, PNGs and pages in `frames/<s>/<m>/`; the FPGA bitstreams and `fpga-library.json`, owned by the FPGA session (Ruling AA). The formats are given by links to vgacap's `docs/trace-format.md` and `docs/frames-format.md` at the pin.
  - **Stimulus, exactly:**
    - clock 0 is the first reset clock;
    - `ena = 1` from clock 0;
    - `rst_n = 0` for clocks 0-9 and 1 from clock 10;
    - `ui_in` and `uio_in` are held at the override's values (or `auto_ui_in`) from clock 0;
    - the inputs change only by the override's `.inputs` events (at the start of the tick whose `clock` equals the event clock) and the gamepad shifting;
    - with the QSPI model, `uio_in` is the model's response;
    - the initial state is Verilator's `--x-initial fast`. State here what that means, checked against Verilator's docs at the pinned oss-cad-suite;
    - byte `i` of a `uo_out` dump is sample `2i + 1` (after rising edge `i`).
  - **The trace-content check:** `trace.uo_out_sha256` over the half-open clock range `[0, M)`, `M = trace.uo_out_sha256_clocks[1]`. No sampler is involved.
  - **Hash inputs:**
    - `sha256-rgb6` is computed over rgb6 bytes (`R<<4 | G<<2 | B`; R = uo[0], uo[4]; G = uo[1], uo[5]; B = uo[2], uo[6]; first bit more significant), row-major, `width * height` bytes from the window's first active pixel of its first active line. It is not RGB888.
    - The FNV method is computed over RGB888, each channel `value * 85`, with `hash_offset_basis` unchanged.
  - **Frame starts and cpp = 1.**
    - tb-v1 starts a frame at the end of the vsync pulse and lines at the end of the hsync pulse. At cpp 1 it reads pixel `p` at clock `p` after the line start. That is the FPGA harness's `ideal` convention, so for cpp = 1 table modes its one-sample-per-pixel crop is tb-v1's frame.
    - centre-v1 starts a frame at the hsync leading edge of the first vsync line. It counts rows from the vsync pulse start (`vsync + vback'`) and pixels from the hsync leading edge (`hsync + hback' + p`).
    - Which projects agree frame for frame is the table from Tasks 21 and 22. For cpp != 1, compare the raw trace only.
  - **tb-v1 freshness:** `tb_v1.state` and `trace_sha`. A stale file is valid for the trace it came from (`null`: the run before traces existed).
  - **To fill in later:** the reference sampler (Task 22) and the commit to pin (Task 23).
- [ ] **Step 5: Tell the harness sessions before the files move** (controller). Send the note's link (this branch, pushed) to "Tiny Tapeout FPGA bitstreams VGA playground" and to the tt-harness-handheld-vga session, with the file move and `hash_offset_basis` unchanged. Wait for their acknowledgement or one day, whichever is first.
- [ ] **Step 6: Convert and seed:** `uv run scripts/convert_frame_hashes.py --seed-host big >> tmp/t17.log 2>&1`. Expected: `converted 408`, `seeded 408`. Then run the suite.
- [ ] **Step 7: Commit and push:** the script and tests first, the data move in its own commit, then the docs.

## Phase 4: rollout

### Task 18: vgacap pin to `main`, host setup, host docs

**Files:**
- Modify: `ttvga/tools.toml`, `docs/host-setup.md`.

- [ ] **Step 1: Move the pin.**
  - When vgacap PRs #14-#22 have merged (fetch, then log `git log --oneline origin/main -25` to `tmp/t18.log`), set `[vgacap] commit` to `origin/main`'s SHA.
  - If they have not merged by then, keep the stack pin and repeat this step before Task 23.
  - Task 23 does not start on a pin outside `main` unless the controller records a ruling naming the SHA and the reason.
- [ ] **Step 2: Test the pin.** Run `uv run tt-vga dev-tools`, `uv run pytest -v` and `uv run pytest -m sim -v` (log `tmp/t18.log`): pass. Then `uv run tt-vga bootstrap --host big`.
- [ ] **Step 3: Host setup** (controller, with `tim`'s sudo; every command and its output go to `tmp/t18-host.log`, and the list goes into the Task 22 report):
  - The frames subtree is **not** created here: Task 19 creates it after the main upload excludes it, so not even the empty directory and its marker reach the server.
  - `sudo install -d -o ttvga -g ttvga -m 755 <staging>`, a directory outside the published tree on the same filesystem (on `/backups`, next to the publish tree's real directory).
  - `sudo loginctl enable-linger ttvga`.
  - As `ttvga`, write `~/ttvga/host.toml` (`frames_root`, `staging_dir`, `min_free_root_gb = 100`).
  - Record the two paths in the host setup memory note, not in the repository.
  - `uv run tt-vga host-check --host big`: Linger=yes, `host.toml` present (`hostconf.load` is checked in Task 19, once the frames subtree exists).
- [ ] **Step 4: Rewrite `docs/host-setup.md`:**
  - the frames subtree and the staging directory (`install -d` lines with placeholders) and their markers;
  - `host.toml`;
  - linger;
  - that bootstrap installs uv and Python 3.14 and builds vgacap and `tracetool`;
  - that cmake is required;
  - and drop the false claim that the ffmpeg build is pinned by checksum.
- [ ] **Step 5: Commit and push.**

### Task 19: the upload split (decision 4), with the frames upload left off

**Ruling** (the controller's, under the I12 ruling; recorded in the Task 22 report):
- The 5-minute upload skips the frames subtree.
- A separate frames upload sends only the projects the pipeline has logged as changed, with a weekly full pass.
- It is installed now, before the pilot, so no frames reach the server early. Its timer stays **disabled** until Task 23's check has passed (C3).
- Why: it keeps the clips' 5-minute latency and avoids a listing of about 1.1 million entries every interval. A longer interval delays everything. A separate slow upload still lists the whole tree on every run.

**Files:**
- Host, under etckeeper, with `tim`'s sudo:
  - modify `/usr/local/sbin/data-upload-sync`: `--exclude=/<frames subtree relative to the publish root>/`, read from `/etc/data-upload/frames.conf`;
  - create `/usr/local/sbin/data-upload-frames-sync`;
  - create `/etc/systemd/system/data-upload-wafer-space-frames.{service,timer}`: every 15 minutes, the existing unit's sandboxing, plus `ReadOnlyPaths=` the staging directory and its own `StateDirectory=data-upload-frames`.
- Repository: `docs/publishing.md`, section "Frames upload". It describes the design without hosts or paths, and states what the job scope confines (resources only) and what the upload trusts (nothing `ttvga` writes, unvalidated). It also names the residual risk: the checks run before rsync, so `ttvga` could swap a checked path component for a symlink between check and transfer; `--safe-links` covers symlinks inside the transfer only. The window is short and the account is the pipeline's own, and the post-transfer re-check below detects it.

**Interfaces:**
- `data-upload-frames-sync [--full]`:
  - It reads `<staging_dir>/changed.log` from the byte offset in `/var/lib/data-upload-frames/offset`, through the last complete line only. If the offset is past the end (the log was shrunk), it starts from 0.
  - It accepts only lines matching `^[0-9T:+-]+ [A-Za-z0-9_]+/[A-Za-z0-9_]+$` whose project directory exists and passes the containment check: neither the project directory nor its shuttle directory is a symlink (`lstat`), and `realpath` of each is inside `realpath` of the frames subtree. Everything else is logged and skipped.
  - It also refuses (logs and skips) a project that contains any symlink (`find <project> -type l`, output logged in full), and passes `--safe-links` and `--no-implied-dirs` to rsync as further guards.
  - After the transfer it re-runs the containment and symlink checks on every project it sent, and logs `realpath changed during transfer: <id>` for any that now fails (for a person to look at and delete on the server by hand); it then exits non-zero so the journal shows it.
  - It builds each path itself, and runs one rsync with the existing options, plus `-r` and `--files-from` (no `--delete`).
  - On exit 0 or 23 it stores the new offset. On 24, or any other failure, it keeps the old offset, so those projects are retried next time.
  - `--full` (weekly, from a second timer) syncs the whole frames subtree.
- [ ] **Step 1: Exclude first.** Install the main upload's exclusion (`data-upload-sync` and `frames.conf`), dry run it with `DATA_UPLOAD_DRY_RUN=1` as `data-upload` (log `tmp/t19.log`: the `--exclude` is on its command line), restart its timer, and `etckeeper commit "data-upload: skip the VGA frames subtree (tinytapeout-vga-videos decision 4)"`. Watch one real run in `/var/lib/data-upload/rsync.log` (read only).
- [ ] **Step 2: Create the frames subtree** (only now): `sudo install -d -o ttvga -g ttvga -m 755 <archive>/frames`, then `sudo -u ttvga touch <archive>/frames/.ttvga-frames-root`. Record the path in the host setup memory note. Check that `hostconf.load` accepts `host.toml`, with a script file run as `ttvga`. The next main upload run lists nothing under it (`rsync.log`).
- [ ] **Step 3: Dry run the frames upload** with `DATA_UPLOAD_DRY_RUN=1` as `data-upload`. Given a hand-made `changed.log` with one valid line, one invalid line, one partial last line and one line naming a symlinked project (a symlink `<frames>/test/link -> /etc`, made as `ttvga` and removed afterwards), plus a test project directory with a file and one with a symlink inside, it lists exactly the valid, symlink-free project, and the log shows the post-transfer re-check passing.
- [ ] **Step 4: Install the frames units.** `systemctl daemon-reload`, and **do not enable** the frames timers. `etckeeper commit "data-upload: frames upload installed, disabled (tinytapeout-vga-videos decision 4)"`. Watch two main runs: file count and listing time in `rsync.log`.
- [ ] **Step 5: Commit and push** `docs/publishing.md`.

### Task 20: pilot (rollout step 2): the budget

**Files:**
- Create: `scripts/pilot_measure.py`, `docs/reports/2026-11-pilot/measurements.md`, `docs/reports/2026-11-pilot/raw/*.json`.

**Interfaces:**
- **The 11 projects:**
  - `tt08/tt_um_a1k0n_nyancat`;
  - `tt08/tt_um_johshoff_metaballs` (800x600);
  - `ttihp25a/tt_um_rebeccargb_colorbars` (static);
  - `ttihp25a/tt_um_rejunity_atari2600` (QSPI);
  - `tt05/tt_um_tomkeddie_a` (640x504);
  - `ttihp25a/tt_um_cfib_demo` (cpp 2);
  - `ttihp25a/tt_um_a1k0n_vgadonut` (cpp 1.9062);
  - `tt08/tt_um_nyan` (1.04);
  - `ttihp25a/tt_um_MichaelBell_rle_vga` (0.9524);
  - `tt08/tt_um_MichaelBell_mandelbrot` (4.2667);
  - `tt07/tt_um_tinytapeout_dvd_screensaver`.
- **`scripts/pilot_measure.py --host big --ids FILE --out docs/reports/2026-11-pilot/raw`.** It starts, in a tmux session on the host, with a log `~/ttvga/work/pilot.log` that the Monitor reads, for each id in its own Task 10 scope, all 11 at once:
  - `job.py --tb-v1 --keep-build --timeout 10800`;
  - then the kept `Vtop` 2 times without `--trace` and 2 times with it, interleaved, with the job's cwd and arguments. That is five runs per project, the job included;
  - each under `/usr/bin/time -v` (wall, user+sys CPU, max RSS), with `--ffmpeg` writing to a scratch file;
  - then `vgacap-sample` alone (default, and with both samplers) under `/usr/bin/time -v` with `VGACAP_SAMPLE_DEBUG=1`;
  - the derive timings from `result.json`;
  - store, PNG and trace sizes (`du -b`; hard links counted once);
  - the peak scratch use, polled every 5 s.
  - The pilot's frames go to the frames subtree, which Task 19 keeps off the upload. The pilot publishes nothing to the server.
- [ ] **Step 1: Sync and start.** Run `uv run tt-vga sync --host big` first, so the pilot uses the pinned Python and this harness.
  - ETA: the projects' previous `wall_seconds` times five runs. The longest, mandelbrot at 3,569 s, sets the end: about 5 hours.
  - Report every 15 minutes from `pilot.log`, with the remaining runs and the finish clock time.
- [ ] **Step 2: Compute against the spec's targets**, per project, into `measurements.md`: one table per target, one row per project, no prose in cells.
  - Recording: `(wall with trace - wall without) / wall without` must be at most 5%. Also give ns per clock.
  - Post-simulation CPU: the compressor CPU (CPU with trace minus CPU without), plus `derive_cpu_seconds`, over the simulation CPU without the trace. It must be at most 5%. Give `dvd_screensaver`'s against its 19 s budget.
  - Memory per job.
  - Root-volume peak per job. Rule `min_free_root_gb = 24 * peak * 2`, rounded up to 10 GB, and write it into `host.toml`.
- [ ] **Step 3: Fix path for a missed target.** Measure each change on the same project before and after, interleaved, median of 3.
  - Recording over 5%:
    1. `kTraceZstdLevel` 1, then -1, -3, -5;
    2. `objdump -d` of `Vtop` (logged) to confirm the push is inline;
    3. then the format note's planar alternative, which is vgacap work: send the profile to the controller for the vgacap session and the report.
  - Post-simulation over 5%, in the spec's order:
    1. `store_level` lower (1, then -1) when `distinct_frames / frames > 0.5`, as a `derive` rule;
    2. a faster SHA-256 (vgacap work, through the controller);
    3. the second sampler only on request (already the default).
    - Hashing on a thread does not count as a fix.
  - Each fix is a commit with its numbers. A target still missed goes into the report with the profile.
- [ ] **Step 4: Commit and push.**

### Task 21: pilot (rollout step 2): correctness, formats, viewers

**Files:**
- Modify: `docs/reports/2026-11-pilot/measurements.md`.
- Create: `docs/reports/2026-11-pilot/frames/`, `docs/reports/2026-11-pilot/viewers/`, `scripts/pilot_formats.py`.

- [ ] **Step 1: tb-v1 against the published hashes.** For each of the 11, the new FNV hash lines equal the committed converted file's. Any difference stops the task: investigate it and report it. It is never accepted.
- [ ] **Step 2: Distinct counts.** Compare distinct SHA-256 frames with distinct FNV values per project. Record the 408-project total today, 543,730 FNV values.
- [ ] **Step 3: tb-v1 against centre-v1**, frame by frame.
  - For each project, run `tt-vga frames compare` on the two `frames.txt`, and `tt-vga frames diff` on the first differing pair. Save the PNGs.
  - For `tt08/tt_um_nyan`, `ttihp25a/tt_um_MichaelBell_rle_vga` and `tt08/tt_um_MichaelBell_mandelbrot`, check:
    - centre-v1 `clocks_per_pixel` is 1, 1 and 4;
    - `colour_changes_off_grid` is 0;
    - `outside` is 0. Otherwise record the suggested offset, and set no override.
  - Write the list of cpp = 1 projects where the two samplers agree frame for frame.
- [ ] **Step 4: Calibration designs.**
  - Run `tt-vga queue start --only testpatterns --timeout 10800`.
  - Compare each centre-v1 distinct frame with tt-vga-testpatterns' `tools/render.py` reference for that design and `ui_in`. Run it from a script file with `uv run --project <tt-vga-testpatterns checkout>`.
  - It must be pixel-exact, including 720x400 and the three polarity cases. A difference is a centre-v1 bug for the vgacap session (via the controller).
- [ ] **Step 5: Hardware, where it exists.**
  - For `cfib_demo`, `vgadonut`, `rle_vga` and `mandelbrot`, look for a vgacap capture (the Welland board claims and captures, and tt-harness-fpga-vga's results).
  - Where one exists, decode it with `vgacap-frames` and compare by rgb6 SHA-256. Where none exists, record `none`.
- [ ] **Step 6: Formats.** `scripts/pilot_formats.py` measures, per project:
  - VGCH (the file);
  - FST: `vgacap-export --format fst` with and without `--no-clk`;
  - sigrok `.sr`: a zip of `version` (`2`), `metadata` and `logic-1-<n>` chunks of 6-byte samples, deflated, written over the first 2^24 clocks and extrapolated linearly (the extrapolation stated);
  - the store as one zstd frame per distinct image (level 3, no long-distance matching) against the single long-distance stream: size, and the time to read one frame from the middle.
  - Project each to all 408.
- [ ] **Step 7: Viewers.**
  - For one frame each of nyancat and `cfib_demo`, export FST and VCD with `--sampler-frames`, and check the FST's `fst2vcd` value changes equal the VCD's.
  - Screenshot GTKWave (`/usr/bin/gtkwave`) and Surfer (`/usr/local/bin/surfer`, 0.7.0) under `xvfb-run` on the host, loading the `.gtkw` and `.sucl`.
  - Copy the screenshots, and files under 5 MB, to `viewers/`.
- [ ] **Step 8: Upload listing.**
  - Count the files the frames upload would list for all 408, projected from the pilot's per-project counts.
  - Time an `rsync --dry-run -r --list-only` of the pilot's projects (logged).
  - Record today's 62,641 entries in about 25 s, from `/var/lib/data-upload/rsync.log` (read only).
- [ ] **Step 9: Commit and push.**

### Task 22: the owner report (rollout step 3)

**Files:**
- Create: `docs/reports/2026-11-pilot/report.md`.

- [ ] **Step 1: Write the report**, projected to all 408. It covers:
  - trace size per format;
  - store and PNG sizes, and how many PNGs tb-v1 adds after sharing;
  - run time and root-volume use per job;
  - the upload listing;
  - the budget table, with the profile and fix for each target missed;
  - the correctness results.
- [ ] **Step 2: Record the rulings** (I12 ruling), each as "Ruling: <decision> - <reason from the numbers> - <cost if wrong>":
  - **Decision 2, the stored format:** VGCH with runs, unless FST or sigrok is at most half its projected size.
  - **Decision 3, the reference sampler:** centre-v1, if Task 21 found it pixel-exact on every calibration design and right on the cpp != 1 projects (in agreement with hardware where there is a capture, visibly right in the diffs where there is none). tb-v1 stays published for continuity. If a condition fails, tb-v1 stays the reference and the failure is the open question.
  - **Decision 4:** Task 19's split, now with the measured listing.
  - The re-run's job count (24 unless memory or root volume say fewer) and `min_free_root_gb`.
  - The host changes made with `tim`'s sudo (Task 18 Step 3, Task 19), with their etckeeper commits.
  - Anything left for the owner (a target missed with no fix, a planar-format question).
- [ ] **Step 3: Send it.** Commit and push. The controller publishes the report as an Artifact (private) and sends Tim the link with a short summary. Task 23 does not wait for his answer: an objection to a ruling is applied afterwards by re-deriving (or, for the stored format, by re-exporting).
- [ ] **Step 4: Fill in the consumer note's cpp = 1 agreement table** (Task 21 Step 3) and the reference sampler, then commit and push.

### Task 23: the full re-run, the check, publishing (rollout step 4)

**Files:**
- Modify: `data/results/**`, `docs/status.md`, `data/status.json`, `index.html`/`index.json`, `docs/consumers.md`, `PROGRESS.md`, `README.md`.
- Create: `scripts/check_tbv1_against.py`, `docs/reports/2026-11-rerun.md`.

- [ ] **Step 1: Preconditions.** The controller checks each and records it in `tmp/t23.log`:
  - the pin is on vgacap `main` (or a recorded ruling);
  - Tasks 18-22 are merged and the harness is synced;
  - Linger=yes, and `host.toml` has `min_free_root_gb` from Task 20;
  - the frames timer is still disabled;
  - the limit is `--timeout 10800`, the reference run's limit;
  - `ps -eo user,pcpu,etime,args --sort=-pcpu` is logged in full and read for outside users.
  - Record `main`'s SHA as `PRE`, and the current `harness_version()` as `KEY`.
  - List the projects `--redo-unless-harness KEY` would skip (on the host, the `result.json` files with `trace`, `harness == KEY` and `tb_v1_check: match`; logged in full). Expected: the 11 pilot projects if neither `ttvga/harness/` nor `tools.toml` has changed since Task 20, else none. A pin move in Task 18 or any harness fix after the pilot changes `KEY`, so the pilot projects re-run with everything else.
  - For every project on that list, check that `git diff <pilot commit> PRE -- overrides/<s>/<m>.* data/targets.json` changes nothing for it (logged). Any that changed goes in an explicit `--redo --only <ids>` queue run before Step 2.
- [ ] **Step 2: Start the opt-in tb-v1 re-run** of all 408 (the `testpatterns` pseudo-shuttle included, unpublished): `uv run tt-vga queue start --host big --redo-unless-harness KEY --tb-v1 --timeout 10800 --jobs 24 >> tmp/t23-queue.log 2>&1`.
  - ETA: the sum of each project's previous `wall_seconds` times the pilot's overhead factor, over 24 slots, with a tail of at least the longest single run (6,381 s for `ttcad25a/tt_um_toivoh_demo_deluxe`). That is about 5-6 hours.
  - Report every 15 minutes from `queue-state.json` and `queue.log`, with remaining time and finish clock time.
  - After a crash, restart with the same command and the same `KEY`: `--redo-unless-harness` skips the finished projects. If a fix had to change the harness or `tools.toml` before the restart, `KEY` changes and every project re-runs; that is intended (the runs must share one harness).
- [ ] **Step 3: Collect.** Run `uv run tt-vga collect --host big >> tmp/t23-collect.log 2>&1`, then `analyze`, `report` and `index`.
- [ ] **Step 4: The tb-v1 check of all 408.** `scripts/check_tbv1_against.py --base PRE` compares, for each project:
  - the hash lines of `git show PRE:data/results/<s>/<m>/frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` with the new file's;
  - `tb_v1_check == "match"` and `tb_v1.state == "current"`.
  - It must find all 408 identical. A project that is not is investigated: re-run it alone, run `frames compare` against `PRE`, and export the trace around the first mismatch. It is then fixed, or the step stops and reports. Nothing is accepted as is.
  - Header differences are listed separately, by key, with `status` and `sampler_status` shown apart. None is expected after Task 17's recomputed `clocks_per_pixel`.
- [ ] **Step 5: The `outside` list.** Every project whose centre-v1 `outside` is not 0, with its `suggested_offset` and links to its first frames, goes into `docs/reports/2026-11-rerun.md`. No override is set here.
- [ ] **Step 6: Commit and push** the collected data in reviewable commits (one per shuttle group), then the regenerated docs.
- [ ] **Step 7: Publish**, only after Step 4 has passed:
  - Enable the frames timers (`systemctl enable --now data-upload-wafer-space-frames.timer` and the weekly one) and `etckeeper commit`. Watch the first run in the journal and in `rsync.log`.
  - Mirror the clips and the index: `tt-vga mirror --as-user tim --dest <archive> --fpga-ids-out tmp/fpga-ids.txt`, then `tt-vga index --fpga-ids tmp/fpga-ids.txt`, and mirror again.
  - Verify: `tt-vga verify --host big` (no failures; stale tb-v1 notes expected to be none after the `--tb-v1` run) and `tt-vga verify --server-stale https://data.wafer.space/big-storage/tinytapeout-vga-videos/` (logs `tmp/t23-verify.log`).
  - Stale server files are listed for removal by hand. The bitstreams and `fpga-library.json` are never among them.
- [ ] **Step 8: Tell the consumers.** Fill in `docs/consumers.md`'s pin with the `main` SHA after Step 6, then commit and push. The controller sends that SHA and the note's link to "Tiny Tapeout FPGA bitstreams VGA playground" (it pins 148ccf5 today and is moving to 87cea85) and to the handheld session.
- [ ] **Step 9: PROGRESS.md entry and README.**
  - The entry covers what ran, the counts, the tb-v1 check, the time taken, the sizes on the bulk volume and the open items.
  - `README.md`'s frames section points at `docs/consumers.md`.
  - Commit and push.
