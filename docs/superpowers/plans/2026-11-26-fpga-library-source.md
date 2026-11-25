# VGA library source: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visitors at tinytapeout.fpgas.online can load any of about 445 prebuilt Tiny Tapeout
VGA bitstreams from the VGA archive onto a FabricFox board. They can do it from the board page
or from the customised Commander. This adds a third source, `library`, next to the packaged
demos and visitor uploads.

**Architecture:**
- The harness publishes `fpga-library.json` and content-addressed `.bin` files in the archive.
- The site backend on tweed checks them against the schema. It pushes the bytes into a
  separate library cache in the fpgas-tt daemon, under a redis lock and one 50 s deadline.
- Loading reuses the daemon's `load_design`. In the same REPL step it releases the `ui_in`
  pins the daemon drove before. It drives the entry's `ui_in_mask` bits directly, never through
  `tt.mode`.
- board.js and the Commander take all library metadata from the site's index.

**Tech Stack:**

| Repo | Stack |
|---|---|
| fpgas.online-tt (daemon) | Python 3.11, aiohttp, pytest |
| fpgas.online-site (site) | Django, requests, redis cache, pytest, `node --test` |
| tt-commander-app (Commander) | Solid.js, TypeScript, vitest |
| tinytapeout-vga-videos (videos) | Python, uv, pytest |
| fpgas.online-infra (infra) | Ansible |

**Spec:** `docs/superpowers/specs/2026-11-26-fpga-library-source-design.md`, revision 5
(commit `4d29646`, branch `fpga-library-spec` of tinytapeout-vga-videos). Every task names the
spec sections it implements. Read them first.

## Global Constraints

**Schema and names**
- The schema is exactly spec section 1, including `ui_in_mask` and `fmax_hz`. NaN and Infinity
  are refused on write and on read. A bool is never accepted where an int is required.
- The id rule (Ruling AC):
  1. Take `lower(<shuttle> + "_" + <macro without leading "tt_um_">)`.
  2. Map every character outside `[a-z0-9_]` to `_`.
  3. If the result is over 40 characters, keep the first 31 characters, then `_`, then the
     first 8 lowercase hex digits of the SHA-256 of the UTF-8 `<shuttle>/<macro>`. That string
     keeps its original case and its `tt_um_`.
- A design name matches `^[a-z0-9_]{1,40}\Z`.
- A bitstream is at most 262144 bytes, with the preamble `7E AA 99 7E` in its first 68 bytes.
- `clock_hz` is 1 to 200000000. `ui_in_mask` is 0 to 255. `ui_in` is null when the mask is 0;
  otherwise it is 0 to 255 with `ui_in & ~ui_in_mask == 0`.

**Board behaviour (Ruling AD)**
- The daemon never sets `tt.mode` and never calls `clock_project_stop`.
- Every enable releases the pins listed in the board global `_fo_ui_driven`. Every library
  load also releases every bit outside its mask, so all eight when the mask is 0.
- Releasing a pin (Ruling AF): only a pin in `_fo_ui_driven` that `GPIO_OE` (bit
  `_fo_p.gpio_num`, address from `rpregs.GPIO_OE_EXPR`) shows the RP2350 driving gets latch 0
  and `time.sleep_ms(1)`; then `Pin.IN`, then `Pin.PULL_DOWN`. Every other released pin goes
  straight to `Pin.IN` and `Pin.PULL_DOWN` and is never made an output.
- `safe.py`'s output-enable register is chosen by chip (Ruling AG, Task 2): `0xd0000030` on
  the RP2350, `0xd0000020` on the RP2040.
- The release runs after the hash check and before `_fo_reader` is built and
  `_fo_touched = True`.
- Only mask bits are driven, and a mask of 0 drives nothing. Each pin's latch is set before the
  pin becomes an output. Unmasked bits are never recorded in `_fo_ui_driven`.
- The daemon library cap comes from `--library-max-bytes`. Its default is the env var
  `FPGAS_TT_LIBRARY_MAX_BYTES`, else 16777216.
- The library store never touches uploads.

**Site**
- Archive base: `https://data.wafer.space/big-storage/tinytapeout-vga-videos/`.
- The load route has one deadline of 50 s.
- The lock lives in `caches["ttsite"]` (redis db 2, its own, `KEY_PREFIX "ttsite"`) with a 70 s TTL.
  Redis down means 503.
- Every page POST carries `X-CSRFToken`. No view is `csrf_exempt`.

**Commands**
- Python runs through `uv run`. Never bare `python`, never `python -c`.
- Never `2>/dev/null`. Never `/tmp`. Logs go to `<worktree>/tmp/`, which all five repos
  gitignore.
- Redirect each command of a chain separately, for example `cmd1 >> tmp/x.log 2>&1; cmd2 >>
  tmp/x.log 2>&1`. Grep the log; never pipe into grep or tail.

**Branches and commits**
- One worktree and one branch per task: `git worktree add -b <branch> .worktrees/<branch>
  <base>`. Stacked tasks branch from the previous task's branch.
- Commit small and push after each commit with `git push -u origin <branch>`.
- A task ends at "push branch". The controller opens PRs after independent review.
- Every commit ends with this trailer:

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01M4cwEsPm9kJ96LQeYKwqhK
  ```

**Repo conventions**
- Follow each repo's `CLAUDE.md`.
- Daemon and site: ruff, line length 120.
- Commander: prettier, SPDX headers, base branch `fpgas-online`.

**Hardware**
- No hardware access, except in Task 13.

## Review Focus

These five conditions are the likeliest to bite a visitor, and the main tests of each task do
not exercise them. Each one has its pinning test in the owning task.

1. **The index arrives before its bins.** The onward rsync sorts `fpga-library.json` first, so
   this is certain during every publish. The visitor should see the "still syncing" message,
   with no 502 trace. Test: `test_load_bin_404_says_still_syncing`, Task 7.
2. **The index is republished between page load and pressing Load, and the id is gone.** The
   panel should say the design is no longer in the library and reload the index. It should not
   leave a dead card. Test: `load of a vanished id reloads the index`, Task 8.
3. **A visitor has set inputs in the Commander's Interact tab, then someone loads a library
   design.** The release must free only the pins the daemon drove, never the visitor's. Test:
   `test_release_frees_only_daemon_driven_pins`, Task 4.
4. **The Pi reboots between the site's `GET /library` and its enable**, so the cache is empty.
   The site should push again and the load should succeed, once. Test:
   `test_load_retries_once_after_404_enable`, Task 7.
5. **A search that matches nothing, or a filter change while on page 7.** The panel should show
   page 1 and "0 of N designs", never a broken page range. Test: `paging clamps and resets`,
   Task 8.

---

## Task 1: Schema module, checker CLI and fixture (tinytapeout-vga-videos)

**Repo and branch:** `~/github/TinyTapeout/tinytapeout-vga-videos`, branch
`fpga-library-schema` off `origin/main`. **Spec:** section 1.

**Files:**
- Create: `ttvga/fpgalibrary.py`
- Create: `tests/fixtures/fpga-library/make_fixture.py`
- Create: `tests/fixtures/fpga-library/fpga-library.json`, plus 5 bins under
  `<shuttle>/<macro>/`
- Modify: `ttvga/cli.py:16-22`, to register the subcommand
- Test: `tests/test_fpgalibrary.py`

**Interfaces:**
- Produces:
  - `library_id(shuttle: str, macro: str) -> str`. Raises `ValueError` when the macro has no
    `tt_um_` prefix.
  - `check_reserved(id: str) -> str | None`.
  - `DEMO_NAMES: tuple[str, ...]`, the five names of spec section 1. Its comment cites
    tinytapeout-fpga-demos `da7d10d`.
  - `validate(doc: object) -> list[str]`. Each item reads like `"designs[3].ui_in: <rule>"`.
    A field gets at most one violation: its first failing rule.
  - `check_bins(doc: dict, root: Path) -> list[str]`.
  - `load(path: Path) -> object`. It uses a `parse_constant` that raises on NaN and Infinity.
  - `add_parser(sub)`, which adds `fpga-library-check <file> [--bins DIR]`. It exits 0, or 1
    after printing every violation.
  - The fixture directory `tests/fixtures/fpga-library/`. Tasks 3, 6 and 10 copy it, adding a
    `_comment` key naming the commit they copied from.

The five fixture entries, in display order. They are grouped by shuttle, so the run order
holds. All have `validation: "none"` and `qspi: "none"`.

| # | id | shuttle/macro | status | `ui_in` / mask | other |
|---|---|---|---|---|---|
| 0 | `ttsky25b_lukasdragoste_vga_patterns` | `ttsky25b/tt_um_lukasdragoste_vga_patterns` | `ok` | 1 / 1 | `verdict: "barely-moving"` |
| 1 | `ttsky25a_vga_example` | `ttsky25a/tt_um_vga_example` | `ok` | null / 0 | |
| 2 | `ttihp26a_vga_example` | `ttihp26a/tt_um_vga_example` | `ok` | null / 0 | `poster`, `preview_gif`, `video_10s_webm` null |
| 3 | `ttihp25a_yuri_panchul_sea_battl_09a2562b` | `ttihp25a/tt_um_yuri_panchul_sea_battle_vga_game` | `ok` | null / 0 | |
| 4 | `tt05_flappy_vga_cutout1` | `tt05/tt_um_flappy_vga_cutout1` | `timing-fail`, `fmax_hz` 17080000 | null / 0 | |

Each bin is 4096 bytes: `ff 00 00 ff 7e aa 99 7e`, then zeros, with byte 8 set to the entry's
row number.

- [ ] **Step 1: Write the failing tests**
  - `test_library_id_examples`: the five rows of the spec's id table, exactly.
  - `test_library_id_hashed_is_40_chars`: `("ttsky25a",
    "tt_um_rebeccargb_vga_timing_experiments")` gives
    `"ttsky25a_rebeccargb_vga_timing__4638a050"`, of length 40.
  - `test_library_id_refuses_non_tt_um`.
  - `test_check_reserved`: `idle_display` and each of the five demo names give a message;
    `ttsky25a_vga_example` gives None.
  - `test_fixture_is_valid`: `validate` and `check_bins` both return empty lists.
  - `test_each_rule_is_enforced`: parametrised with one mutation per rule in the spec's tables,
    plus these cases:
    - a duplicate id;
    - `bin` differing from the derived path;
    - a `..` path;
    - an absolute poster URL;
    - `ui_in: True`;
    - `ui_in: 3` with mask 1;
    - `ui_in: null` with mask 1;
    - 7 `uo_out` labels;
    - `generated` without a trailing `Z`;
    - `fmax_hz: 17.5`;
    - a non-contiguous shuttle;
    - an unknown top-level key, which is allowed and gives no violation.

    Each case asserts exactly one violation, whose prefix names the mutated field.
  - `test_load_refuses_nan`: a document containing `NaN` raises `ValueError`.
  - `test_check_bins_catches`: wrong size, wrong hash, no preamble, missing file. Each gives
    one violation.
  - `test_cli_exit_codes`: 0 on the fixture; 1 on a mutated copy in `tmp_path`, with the
    violation printed.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_fpgalibrary.py -v >> tmp/t1.log 2>&1`,
  then grep the log. Expected: they fail with `ModuleNotFoundError`.
- [ ] **Step 3: Write and run `make_fixture.py`** (`uv run
  tests/fixtures/fpga-library/make_fixture.py`). It writes the bins and the JSON with
  `allow_nan=False`.
- [ ] **Step 4: Implement `ttvga/fpgalibrary.py`.** Use one rule function per key, driven from
  a table. Register the parser in `cli.py`.
- [ ] **Step 5: Run the suite.** `uv run pytest >> tmp/t1.log 2>&1`. Expected: everything
  passes.
- [ ] **Step 6: Commit** "fpgalibrary: schema 1 checker, id rule and fixture", then push.

## Task 2: `safe.py` reads the right output-enable register (fpgas.online-tt, Ruling AG)

**Repo and branch:** `~/github/fpgas-online/fpgas.online-tt`, branch `safe-gpio-oe` off
`origin/main`. It is its own PR, and it lands before Tasks 3 and 4, because the library's guard
and release reuse `safe.py`'s pattern. **Spec:** controller rulings table (AG) and section 9,
fpgas.online-tt.

The bug: `SAFE_CODE` reads `machine.mem32[0xd0000020]` as the SIO output-enable register
(`src/fpgas_tt/safe.py:99`). On the RP2040 that is `GPIO_OE`. On the RP2350 it is the write-only
`GPIO_OUT_CLR` (pico-sdk `rp2350/hardware_regs/include/hardware/regs/sio.h:249`, `:254`), so
`driven` is wrong on the RP2350 chip boards. The RP2350's `GPIO_OE` is `0xd0000030` (`sio.h:380`).

**Files:**
- Create: `src/fpgas_tt/rpregs.py`. It holds `GPIO_OE_EXPR = "(0xd0000030 if 'RP2350' in
  sys.implementation._machine else 0xd0000020)"`, a board-side expression, with a docstring
  citing both pico-sdk headers. It imports nothing from the package, so `safe.py` and
  `designs.py` can both import it.
- Modify: `src/fpgas_tt/safe.py:67-107`. The `_fo_oe = machine.mem32[0xd0000020]` line becomes
  `_fo_oe = machine.mem32[` + `GPIO_OE_EXPR` + `]`, and `import sys` goes next to the existing
  `import machine`. No other line of `SAFE_CODE` changes.
- Test: `tests/test_safe.py`.

**Interfaces:**
- Produces: `rpregs.GPIO_OE_EXPR: str`. Task 4's release block uses it.

- [ ] **Step 1: Write the failing tests**
  - `test_safe_code_reads_gpio_oe_by_chip`: evaluate `GPIO_OE_EXPR` with a fake `sys` whose
    `implementation._machine` is `"Raspberry Pi Pico 2 with RP2350"`, and get `0xd0000030`.
    With `"Raspberry Pi Pico with RP2040"` it gives `0xd0000020`.
  - `test_safe_code_uses_the_expression`: `safe.safe_code(False)` contains
    `machine.mem32[(0xd0000030 if 'RP2350'` and no longer contains `mem32[0xd0000020]`.
  - `test_safe_code_structure_unchanged`: apart from the `_fo_oe` line and the added
    `import sys` line, the lines of `safe.safe_code(False)` equal those of today's text. Keep
    today's text as `tests/data/safe_code_before_ag.txt`, written in this step from `main`.
  - In the existing `outcome()` tests, add a case with an RP2350 reply whose `driven` list now
    matches the pins made outputs.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_safe.py >> tmp/t2.log 2>&1`. Expected:
  the new tests fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the suite and ruff.** `uv run pytest >> tmp/t2.log 2>&1; uv run ruff check >>
  tmp/t2.log 2>&1`. Expected: all pass, and ruff is clean.
- [ ] **Step 5: Commit** "safe: read GPIO_OE at the RP2350's address on an RP2350", then push.
  Tell the controller the fix also changes what `/health`'s `safe_start` reports on RP2350
  chip boards.

## Task 3: Daemon library store, routes and listing (fpgas.online-tt)

**Repo and branch:** `~/github/fpgas-online/fpgas.online-tt`, branch `library-store` off
`safe-gpio-oe` (Task 2). **Spec:** section 2: Store, Name precedence, `GET /designs`, `GET /library`,
`POST /library/{id}`, Concurrency, Docs.

**Files:**
- Create: `src/fpgas_tt/library.py`. It must not import `designs`.
- Modify: `src/fpgas_tt/designs.py`:
  - `_meta` at lines 100-106;
  - `validate_bitstream` at 110-120;
  - `design_names` at 143-151;
  - `design_file` at 154-163;
  - `_listing` at 294-296;
  - `_read_design` at 299-303;
  - `list_designs` at 318-321;
  - `enable_design` at 324-342.
- Modify: `src/fpgas_tt/server.py`:
  - `create_app` at lines 78-112;
  - the routes;
  - move the part loop at 234-258 into `_read_parts`;
  - `build_parser` and `main`;
  - the module docstring.
- Modify: `README.md` and `CLAUDE.md`.
- Create: `tests/data/library/`, a copy of the Task 1 fixture.
- Test: `tests/test_library.py` (new), `tests/test_designs.py`, `tests/test_server.py`.

**Interfaces:**
- Consumes: the Task 1 fixture, copied.
- Produces, in `library.py`:
  - `LIBRARY_DIR_DEFAULT = Path("/var/lib/fpgas-tt/library")`.
  - `max_bytes_default() -> int`, which reads env `FPGAS_TT_LIBRARY_MAX_BYTES` and falls back
    to 16777216.
  - `check_meta(meta: object) -> str | None`. Exactly the keys `id`, `bin_sha256` and
    `bin_bytes`, typed, with no bools.
  - `store(library_dir: Path, id: str, sha256: str, data: bytes, max_bytes: int) ->
    tuple[bool, list[str]]`, returning `(created, evicted)`. It removes orphans first.
  - `entries(library_dir) -> list[dict]`, each `{"id", "bin_sha256", "bin_bytes", "used_at"}`.
  - `names(library_dir) -> set[str]`.
  - `touch(library_dir, id) -> None`. It ignores `FileNotFoundError`.
  - `used_bytes(library_dir) -> int`.
  - `bin_path(library_dir, id) -> Path`.
- Produces, in `designs.py` (keyword-only, so existing callers are unchanged):
  - `design_names(demos_dir, uploads_dir, *, library_dir=None)`;
  - `design_file(demos_dir, uploads_dir, name, *, library_dir=None)`;
  - `list_designs(runner, demos_dir, uploads_dir, *, library_dir=None)`;
  - `enable_design(runner, name, clock_hz, demos_dir, uploads_dir, *, library_dir=None,
    waited=0.0)`.
- Produces, in the app: `app["library_dir"]` and `app["library_max_bytes"]`;
  `create_app(..., library_dir=..., library_max_bytes=...)`.
- Wire: exactly spec section 2. That includes `hides_upload`, and library entries listed in the
  upload shape (`title`, `author`, `description`, `docs_url`, `repo_url` `""`, `clock_hz` null,
  `pinout` `{}`) plus `source: "library"` and `size`.

- [ ] **Step 1: Write the failing store tests** in `tests/test_library.py`:
  - `test_store_writes_bin_then_json_and_lists_it`;
  - `test_same_sha_push_is_idempotent_and_refreshes_lru`;
  - `test_new_build_replaces_old_bytes`;
  - `test_lru_evicts_oldest_until_it_fits`, with `max_bytes=3*4096` and 4 pushes;
  - `test_orphans_are_removed_and_never_counted`: a lone `.bin`, a lone `.json` and a
    `.x.tmp` file;
  - `test_touch_after_eviction_is_harmless`;
  - `test_eviction_never_touches_uploads`;
  - `test_check_meta_rules`, parametrised: an extra key, `bin_bytes: true`, `bin_sha256` in
    uppercase hex;
  - `test_concurrent_stores_lose_nothing`: 8 threads;
  - `test_max_bytes_default_reads_env`.
- [ ] **Step 2: Write the failing designs and server tests**
  - In `tests/test_designs.py`:
    - `test_precedence_demo_then_library_then_upload`;
    - `test_upload_refused_for_cached_library_id`;
    - `test_listing_reports_library_entries_in_upload_shape_with_size`;
    - `test_enabled_library_design_not_in_cache_still_lists_enabled`;
    - `test_enable_reads_library_bin_and_touches_lru`.
  - In `tests/test_server.py`:
    - `test_get_library`;
    - `test_designs_has_top_level_library_key`;
    - `test_push_checks`, parametrised with one case per row of the spec's check table,
      including the `_fpga_only` row;
    - `test_push_created_then_idempotent_200`;
    - `test_push_reports_hides_upload`;
    - `test_push_counts_as_activity`;
    - `test_cli_library_flags`;
    - `test_bitstream_upload_unchanged_after_part_reader_move`, which re-runs the existing
      upload limit cases through the shared helper.
- [ ] **Step 3: Run them.** `uv run pytest >> tmp/t3.log 2>&1`. Expected: only the new tests
  fail.
- [ ] **Step 4: Implement.** Writes go through `tempfile.mkstemp` and then `os.replace`, as
  `store_upload` does (designs.py:166-185). The lock is `library._LIBRARY_LOCK`. The store runs
  in `asyncio.to_thread`. `_read_parts(request, limits: dict[str, int]) -> dict[str, bytes] |
  web.Response` serves both multipart routes; the `meta` limit is 4096.
- [ ] **Step 5: Run the suite and ruff.** `uv run pytest >> tmp/t3.log 2>&1; uv run ruff check
  >> tmp/t3.log 2>&1`. Expected: all pass and ruff is clean.
- [ ] **Step 6: Commit three times and push.** The commits are the store, the routes and
  listing, and the docs.

## Task 4: Releasing and driving `ui_in` on enable (fpgas.online-tt)

**Repo and branch:** fpgas.online-tt, branch `library-ui-in` off `library-store`.
**Spec:** section 2, `POST /designs/{name}/enable` (Ruling AD).

**Files:**
- Modify: `src/fpgas_tt/designs.py`:
  - `LOAD_CODE` at lines 227-272;
  - `_load_steps` at 275-291;
  - `load_design` at 345-354;
  - `enable_design`.
- Modify: `src/fpgas_tt/safe.py:67-107`, so `SAFE_CODE` uses `ui_in_guard(12,
  "_fo_r['held']")`.
- Modify: `src/fpgas_tt/server.py:181-218`, the body checks.
- Modify: `README.md`.
- Create: these snapshot files, written before any code changes, from today's code:
  - `tests/data/safe_code_retry_false.txt` and `tests/data/safe_code_retry_true.txt`;
  - `tests/data/load_code_null_ui_in.txt`, the old last step for
    `_load_steps("x", data, 1000)`. It is used only to show what changes.
- Test: `tests/test_designs.py`, `tests/test_safe.py`, `tests/test_server.py`,
  `tests/test_idle.py` (call sites at lines 244-391; keyword defaults should keep them
  passing).

**Interfaces:**
- Consumes: Task 3's `enable_design` signature.
- Produces:
  - `ui_in_guard(indent: int, held: str) -> str`. Its text is exactly the six lines in spec
    section 2, each prefixed by `indent` spaces.
  - `_load_steps(name, data, clock_hz, *, ui_in=None, ui_in_mask=0, library=False) ->
    list[str]`. With `library=True` the release set adds every bit outside `ui_in_mask`.
  - `load_design(runner, name, data, clock_hz, *, ui_in=None, ui_in_mask=0, library=False,
    overall=ENABLE_OVERALL_TIMEOUT) -> dict`. `enable_design` passes `library=True` when
    `design_file` resolved the name to the library store. It returns `{"released": [...], "ui_in_driven":
    [...], "ui_in_held": [...], "ui_in_inputs": [...]}`.
  - `enable_design(..., *, library_dir=None, ui_in=None, ui_in_mask=0, waited=0.0)`. It
    returns `{"enabled", "clock_hz", "ui_in", "ui_in_mask", "ui_in_driven", "ui_in_held",
    "ui_in_inputs", "released"}`.
  - `idle.py:268` is unchanged in source. Its load now releases pins too.

- [ ] **Step 1: Write the snapshot files from the current code** (on top of Task 2's fix, so
  the snapshot holds the chip-selected register), using a short
  `tests/data/make_snapshots.py` run with `uv run`. Commit them alone.
- [ ] **Step 2: Write the failing tests**
  - `test_safe_code_byte_identical`: `safe.safe_code(False)` and `safe.safe_code(True)` equal
    the snapshots.
  - `test_ui_in_guard_text`: `ui_in_guard(4, "_fo_held")` equals the six spec lines, indented
    4 spaces, with `_fo_held.append(_fo_i)` at 8.
  - `test_release_block_on_every_load`: the last step of `_load_steps("x", d, None)` contains
    `globals().get('_fo_ui_driven')`, `rpregs.GPIO_OE_EXPR`'s text, `time.sleep_ms(1)`, `Pin.PULL_DOWN` and
    `print('released=' + json.dumps(`. All of it comes after the buffer's hash check and
    before both `_fo_reader = _fo_Reader(` and `_fo_touched = True` (findings r7 and m-b).
  - `test_release_discharges_only_daemon_driven_pins` (Ruling AF, finding Q1): the release has
    two loops. In the loop over the previous `_fo_ui_driven`, the latch-0 write and
    `time.sleep_ms(1)` sit under the `GPIO_OE` bit test (`>> _fo_p.gpio_num & 1`) and come
    before `Pin.IN`, which comes before `Pin.PULL_DOWN`. The loop over the other released pins
    (the unmasked bits of a library load, minus `_fo_ui_driven`) contains `Pin.IN` and
    `Pin.PULL_DOWN` and contains no `Pin.OUT`, no `raw_pin.value(` and no `sleep_ms`.
  - `test_release_reports_two_lists`: against the fake REPL, a library load with mask 1 after
    a load that drove bit 0 gives `released == [0]` and `ui_in_inputs == [1, 2, 3, 4, 5, 6, 7]`;
    a bit present in both sets is listed only under `released`.
  - `test_library_release_includes_unmasked_bits`: `_load_steps(..., ui_in=1, ui_in_mask=1,
    library=True)` releases `[1..7]` plus `_fo_ui_driven`; with `ui_in=None, ui_in_mask=0,
    library=True` it releases all of `range(8)`; with `library=False` it releases
    `_fo_ui_driven` only.
  - `test_release_exception_keeps_enabled_name`: the fake REPL raises inside the release; the
    reply leaves `tt.shuttle.enabled` as it was, because `_fo_touched` was never set.
  - `test_no_drive_block_when_mask_zero`: with `ui_in=None, ui_in_mask=0`, the step has no
    `raw_pin.value((`, the drive block's value write.
  - `test_drive_block_never_touches_mode_or_clock`: with `ui_in=1, ui_in_mask=1`:
    - the step contains no `tt.mode`, no `clock_project_stop` and no `RPMode`;
    - in the drive loop, `raw_pin.value((__UI_IN__` comes before `_fo_p.mode = Pin.OUT`;
    - the drive block comes after the clock line and after the `finally:` block;
    - `print('enabled')` is the last line.

    This test asserts no ordering against mode changes, because there are none.
  - `test_load_design_parses_released_driven_held`: the fake REPL replies
    `released={"released": [0], "inputs": [1, 2, 3, 4, 5, 6, 7]}`, `ui_in={"driven": [0],
    "held": []}` and `enabled`. The
    result is `{"released": [0], "ui_in_driven": [0], "ui_in_held": [], "ui_in_inputs": [1, 2,
    3, 4, 5, 6, 7]}`. Both lines are parsed with `_parse_json` (finding r6).
  - `test_release_frees_only_daemon_driven_pins` (Review Focus 3). Against the fake REPL:
    1. A load with `ui_in=1, mask=1`.
    2. Then the visitor's own `write_ui_in` sets bit 1 (simulated as board state).
    3. Then a demo load.

    The release lists `[0]` only, and bit 1 is untouched.
  - `test_enable_body_ui_in_rules`, parametrised:

    | body | status |
    |---|---|
    | `{"ui_in": true}` | 400 |
    | `{"ui_in": 256, "ui_in_mask": 255}` | 400 |
    | `{"ui_in": 3, "ui_in_mask": 1}` | 400, `ui_in has bits outside ui_in_mask` |
    | `{"ui_in": null, "ui_in_mask": 1}` | 400, `ui_in_mask needs a ui_in` |
    | `{"ui_in_mask": -1}` | 400 |
    | `{"ui_in": 1, "ui_in_mask": 1}` | 200, echoed |
    | `{}` | 200 |

  - `test_idle_display_load_releases_too`, added to `tests/test_idle.py`.
- [ ] **Step 3: Run them and record the failures.** `tmp/t4.log`.
- [ ] **Step 4: Implement.**
  - The `__RELEASE__` block goes inside the `try:` of `LOAD_CODE`, right after the hash check
    and before `_fo_reader = _fo_Reader(_fo_buf)` (so before `_fo_touched = True`). It
    imports `machine`, `time`, `json` and `from machine import Pin` itself.
  - The `__UI_IN__` block goes between `__CLOCK__` and `print('enabled')`, exactly as in the
    spec.
  - `SAFE_CODE` swaps its six guard lines for the function call.
- [ ] **Step 5: Run the suite and ruff.** Expected: all pass, and the snapshot test is green.
- [ ] **Step 6: Commit** "enable: release what the daemon drove, drive ui_in_mask bits
  directly", then push.

## Task 5: Infra drop-in for the library cap (fpgas.online-infra)

**Repo and branch:** `~/github/fpgas-online/fpgas.online-infra`, branch `tt-library-cap` off
`origin/main`. **Spec:** section 2 Store, and section 8 step 2.

**Files:**
- Modify: `ansible/roles/onpi/tasks/tt.yml`, adding a task in the "enabled" block after
  "Enable fpgas-tt.service".
- Create: `ansible/roles/onpi/templates/fpgas-tt-library.conf.j2`, which renders `[Service]`
  and `Environment=FPGAS_TT_LIBRARY_MAX_BYTES={{ onpi_tt_library_max_bytes }}`.
- Modify: `ansible/roles/onpi/defaults/main.yml`, adding `onpi_tt_library_max_bytes:
  16777216`.
- Test: the repo's own checks, `ansible-lint` and its CI targets (see the repo's `CLAUDE.md`).

**Interfaces:**
- Consumes: Task 3's env var name.
- Produces: `/etc/systemd/system/fpgas-tt.service.d/library.conf`, mode 0644, in the Pi root.

- [ ] **Step 1: Add the template, the default and the tasks.** First an
  `ansible.builtin.file` task creating `/etc/systemd/system/fpgas-tt.service.d` (mode 0755),
  then `ansible.builtin.template` to the drop-in path (finding r8). Add no handler: the Pi root is baked, and the service starts at boot.
- [ ] **Step 2: Run the repo's lint.** Log to `tmp/t5.log`. Expected: clean.
- [ ] **Step 3: Commit** "onpi: drop-in for the fpgas-tt library cap", then push.

## Task 6: Site archive client, lock cache and daemon client (fpgas.online-site)

**Repo and branch:** `~/github/fpgas-online/fpgas.online-site`, branch `vga-library-client` off
`origin/main`. **Spec:** section 3: Settings, `ttsite/library.py`, Caching.

**Files:**
- Create: `ttsite/src/ttsite/library.py`
- Modify: `ttsite/src/ttsite/daemon.py`, adding `library_state`, `library_push` and
  `Unsupported`, and a `deadline` keyword on `enable`.
- Modify: `pib/settings.py`:
  - `TTSITE_LIBRARY_BASE_URL` next to lines 216-220;
  - the `"ttsite"` alias in `CACHES` at lines 192-202, and the comment above `CACHES`
    rewritten to list db 0 (channel layer), db 1 (`poe`), db 2 (`ttsite`) and why each alias
    has its own database: `clear()` is a `FLUSHDB` (finding m-d).
- Modify: `tests/conftest.py:12-17`. The autouse fixture that swaps `poe` to locmem also
  swaps `ttsite` to `{"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
  "LOCATION": "ttsite"}`, because CI has no redis (finding N5).
- Create: `tests/data/fpga-library.json`, a copy of the Task 1 fixture.
- Test: `tests/test_library.py`, `tests/test_daemon.py`, `tests/test_settings_import.py`.

**Interfaces:**
- Consumes: Task 3's wire contract and Task 4's enable body.
- Produces, in `library.py`:
  - `ArchiveError(Exception)`, with `.message`.
  - `NotPublished(ArchiveError)`.
  - `SESSION`, a `requests.Session` with `trust_env = False`.
  - `normalise(doc: object, base_url: str) -> tuple[dict, list[str]]`.
  - `index(deadline: float) -> tuple[bytes, str, int | None]`, returning the body, the weak
    ETag `W/"sha256-<32 hex>"` (finding r4) and the stale age.
  - `entry(id: str, deadline: float) -> dict | None`.
  - `cached_ids() -> set[str] | None`, which returns None when there is no copy.
  - `fetch_bin(entry: dict, deadline: float) -> bytes`.
  - Constants: `FRESH_SECONDS = 300`, `STALE_SECONDS = 86400`, `NOT_PUBLISHED_SECONDS = 60`,
    `INDEX_MAX_BYTES = 4 * 1024 * 1024`.
- Produces, in `daemon.py`:
  - `library_state(board, *, deadline: float) -> tuple[int, dict]`. It raises
    `daemon.Unsupported` on a 404 whose body is not JSON.
  - `library_push(board, name, data: bytes, sha256: str, *, deadline: float) -> tuple[int,
    dict]`.
  - `enable(board, name, body: bytes, *, deadline: float | None = None)`.
  - Read timeouts are `min(<existing>, deadline - now)`.

- [ ] **Step 1: Write the failing tests.** The fake is `SESSION.get`, monkeypatched. It returns
  objects with `status_code`, `headers`, `iter_content` and `close`. The clock is injected as
  `library.now`.
  - `test_normalise_fixture_keeps_all_in_order_and_adds_base_url`
  - `test_normalise_drops_bad_entry_and_logs`
  - `test_normalise_drops_both_duplicates`
  - `test_normalise_drops_noncontiguous_shuttle`
  - `test_normalise_refuses_bad_top_level`
  - `test_index_refuses_nan`
  - `test_index_sends_if_none_match_and_keeps_copy_on_304`
  - `test_index_404_is_not_published_and_cached_60s`
  - `test_index_refuses_redirect`
  - `test_index_caps_size`
  - `test_index_serves_stale_then_gives_up`
  - `test_trickling_archive_hits_deadline`: one byte per 0.2 s of fake time, a 2 s deadline,
    raises `ArchiveError("archive unreachable")`.
  - `test_session_ignores_env_and_closes_responses`
  - `test_fetch_bin_checks_size_hash_preamble`
  - `test_fetch_bin_404_message`: equals the spec's text exactly.
  - `test_fetch_bin_never_leaves_base_host`
  - `test_library_state_old_daemon_is_unsupported`
  - `test_library_push_sends_meta_and_file_parts`: the `meta` part is exactly `{"id",
    "bin_sha256", "bin_bytes"}`.
  - `test_daemon_calls_cap_read_timeout_at_deadline`
  - `test_settings_library_base_and_ttsite_cache`: the alias LOCATION is
    `redis://127.0.0.1:6379/2` and its KEY_PREFIX is `ttsite`.
  - `test_conftest_swaps_ttsite_to_locmem`: inside a test, `caches["ttsite"]` is a
    `LocMemCache`.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_library.py tests/test_daemon.py
  tests/test_settings_import.py >> tmp/t6.log 2>&1`. Expected: the new tests fail.
- [ ] **Step 3: Implement.** The schema rules are duplicated from the spec; do not import from
  tinytapeout-vga-videos. Close every response in a `finally`.
- [ ] **Step 4: Run the suite and ruff.** Expected: all pass.
- [ ] **Step 5: Commit** "ttsite: VGA library archive client", then push.

## Task 7: Site routes and the upload-name check (fpgas.online-site)

**Repo and branch:** fpgas.online-site, branch `vga-library-routes` off `vga-library-client`.
**Spec:** section 3 Routes.

**Files:**
- Modify: `ttsite/src/ttsite/views.py`. Add `api_library` and `api_library_load`. Change
  `api_bitstream` (lines 161-177).
- Modify: `ttsite/src/ttsite/urls.py:12-14`.
- Test: `tests/test_views.py`.

**Interfaces:**
- Consumes: everything Task 6 produces.
- Produces:
  - URL names `ttsite-api-library` and `ttsite-api-library-load`.
  - `LOAD_DEADLINE_SECONDS = 50`, `LOCK_SECONDS = 70`, `ENABLE_MIN_SECONDS = 27`,
    `RETRY_MIN_SECONDS = 32`.
  - The load response: the daemon's enable body, plus `pushed` and `hides_upload`.
  - The index 404 body `{"error": "VGA library not published", "detail": ""}`.

- [ ] **Step 1: Write the failing tests.** Use the existing `boards` fixture. Monkeypatch
  `ttsite.daemon` and `ttsite.library`. Inject the clock as `views.now`.
  - Index route:
    - `test_library_index_etag_304_under_gzip`: `Accept-Encoding: gzip`, with `If-None-Match:
      W/"sha256-..."`, gives 304.
    - `test_library_index_stale_header`
    - `test_library_index_not_published_404`
    - `test_index_cold_and_archive_down_is_502`
    - `test_library_index_404_on_asic_board`
    - `test_library_off_when_setting_empty`
  - Load route, happy paths:
    - `test_load_cached_entry_skips_fetch`
    - `test_load_pushes_then_enables_with_index_values`: for fixture row 1 the enable body is
      exactly `{"clock_hz": 25175000, "ui_in": null, "ui_in_mask": 0}`; for row 0 it is
      `{"clock_hz": 25175000, "ui_in": 1, "ui_in_mask": 1}`.
    - `test_load_clears_designs_cache_and_passes_hides_upload`
  - Load route, failures:
    - `test_load_old_daemon_501`
    - `test_load_retries_once_after_404_enable` (Review Focus 4)
    - `test_load_no_retry_under_32s_left`
    - `test_load_504_when_under_27s_before_enable`
    - `test_load_retry_rechecks_enable_floor` (finding N4): the first enable answers 404 at
      34 s left, the retry push takes 9 s of fake time, so 25 s remain; the route answers 504
      `the load ran out of time; try again` and the second enable is never sent.
    - `test_load_bin_404_says_still_syncing` (Review Focus 1)
    - `test_load_unknown_id_404`
    - `test_load_bad_name_404`
  - Lock and CSRF:
    - `test_load_lock_uses_ttsite_cache`: a fake `caches["ttsite"]` whose `add` returns False
      gives 409. One whose `add` raises `redis.exceptions.ConnectionError` gives 503. The key
      is deleted after success and after failure.
    - `test_load_requires_csrf`: with `Client(enforce_csrf_checks=True)`, a request without a
      token gets 403; with the cookie and the header it gets 200.
  - Upload-name check:
    - `test_upload_refused_for_index_name`: 409 with the spec's text.
    - `test_upload_allowed_without_index_copy` (the archive is down and no copy exists)
    - `test_upload_check_fetches_a_cold_index` (finding r3): a worker with no copy calls
      `library.index` before deciding.
- [ ] **Step 2: Run them and record the failures.** `tmp/t7.log`.
- [ ] **Step 3: Implement.**
  - `api_library` takes `@require_GET`, then `@condition(etag_func=...)` outermost, then
    `@gzip_page`.
  - `api_library_load` takes `@require_POST` and follows the spec's load steps 1 to 9. The lock
    is released in `finally`.
- [ ] **Step 4: Run the suite and ruff.** Expected: all pass.
- [ ] **Step 5: Commit** "ttsite: VGA library index and load routes; refuse upload names in
  the library", then push.

## Task 8: VGA library panel (fpgas.online-site)

**Repo and branch:** fpgas.online-site, branch `vga-library-panel` off `vga-library-routes`.
**Spec:** section 3 Panel, and section 1 Warnings and Order.

**Files:**
- Create: `ttsite/src/ttsite/static/ttsite/library.js`.
- Modify: `ttsite/src/ttsite/static/ttsite/board.js`:
  - `render` at lines 146-172;
  - `enable` at 173-196;
  - the `mountCommander` options at 108-116, adding `csrfToken: csrf`;
  - the badge at 155-156.
- Modify: `ttsite/src/ttsite/templates/ttsite/board.html:36-50`.
- Modify: `ttsite/src/ttsite/static/ttsite/ttsite.css`.
- Modify: `ttsite/src/ttsite/views.py`, the board context in `board` at lines 49-70, to add
  `library_enabled`.
- Create: `tests/js/library.test.mjs`, and `tests/test_library_js.py`, which follows
  `tests/test_power_button_js.py`.
- Modify: `tests/test_static.py`, `tests/test_views.py`.

**Interfaces:**
- Consumes: Task 7's routes and bodies.
- Produces: `library.js`, exported both through CommonJS and as `window.ttsiteLibrary`.
  - `matches(entry, query) -> bool`
  - `shuttles(designs) -> string[]`, in order of first appearance
  - `filter(designs, query, shuttle) -> entry[]`
  - `page(items, pageNo, perPage = 24) -> {items, pageNo, pages}`
  - `badges(entry) -> {text, cls}[]`, exactly the spec's table
  - `assetUrl(base, path) -> string | null`
  - `renderPage(container, state, doc)`, which draws one panel state with `doc.createElement`
    and `textContent` only. `state.kind` is one of `"too-old"`, `"loading"`,
    `"not-published"`, `"error"`, `"empty"`, `"ready"`.

  The Commander (Task 10) copies the badge texts.

- [ ] **Step 1: Write the failing node tests.** They use a small fake document, as the
  power-button tests do.
  - `matches all terms over title author shuttle id macro`
  - `shuttles follow first appearance in the index`
  - `paging clamps and resets` (Review Focus 5): `page([], 7)` gives `{items: [], pageNo: 1,
    pages: 1}`; 30 items at page 9 give page 2 of 2, with 6 items.
  - `badges match the spec table`:
    - row 4 gives `{text: "timing: 17.08 MHz < 25.175 MHz", cls: "warn"}` and `{text: "not
      hardware-validated", cls: "info"}`;
    - row 0 includes `{text: "video: barely-moving", cls: "info"}` and `{text: "inputs set:
      0x01", cls: "info"}`.
  - `renderPage draws each state`: one assertion on the visible text of each state.
  - `load of a vanished id reloads the index` (Review Focus 2): a fake `fetch` answers the load
    with 404 `no such library design`; the controller function then calls the index fetch
    again and shows "no longer in the library".
  - In Python:
    - `test_board_html_has_library_section_when_enabled`, plus its absence when the setting is
      empty;
    - `test_board_js_wires_library_and_csrf`, a grep test: `/library/`, `/load`,
      `X-CSRFToken`, `csrfToken: csrf`, `loading = 'lazy'`.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_library_js.py tests/test_static.py
  tests/test_views.py >> tmp/t8.log 2>&1`. Expected: the new tests fail.
- [ ] **Step 3: Implement.**
  - `library.js` holds the logic and the drawing. `board.js` holds the fetches and events.
  - The gallery shows a library entry only while it is enabled, titled from the index.
  - CSS: `.tt-library`, `.tt-library-grid`, `.tt-badge--library`, `.tt-badge--warn`,
    `.tt-badge--info`.
- [ ] **Step 4: Run the suite, ruff, and `node --test tests/js/`.** Each goes to `tmp/t8.log`
  separately. Expected: all pass.
- [ ] **Step 5: Commit** "ttsite: VGA library panel", then push.

## Task 9: Commander CSRF header (tt-commander-app)

**Repo and branch:** `~/github/fpgas-online/tt-commander-app`, branch `csrf-token` off
`origin/fpgas-online`. It depends on nothing; the controller may run it first (spec section 8
step 1). **Spec:** section 4, the "Its own PR" part.

**Files:**
- Modify: `src/components/EmbedApp.tsx`, adding `EmbedOptions.csrfToken?: () => string` and
  calling `setCsrfToken`.
- Modify: `src/model/fpgaDesigns.ts:67-84`, in `daemonJson`.
- Modify: `README.fpgas-online.md`, the options table.
- Test: `src/model/fpgaDesigns.spec.ts`.

**Interfaces:**
- Produces: `setCsrfToken(fn: (() => string) | undefined): void` in `fpgaDesigns.ts`. When
  `fn` is set, every `daemonJson` request whose method is not GET sends `X-CSRFToken: fn()`.

- [ ] **Step 1: Write the failing tests**
  - `enable sends X-CSRFToken when a token getter is set`
  - `GET designs sends no CSRF header`
  - `no header when no getter is set`
- [ ] **Step 2: Run them.** `npx vitest run src/model/fpgaDesigns.spec.ts >> tmp/t9.log
  2>&1`. Expected: they fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the checks, each logged separately:** `npm run lint >> tmp/t9.log 2>&1;
  npm run typecheck >> tmp/t9.log 2>&1; npx vitest run >> tmp/t9.log 2>&1`. Expected: all pass.
- [ ] **Step 5: Commit** "embed: send the host page's CSRF token on POST", then push. After
  merge, Tim tags `embed-v0.2.1`.

## Task 10: Commander library source (tt-commander-app)

**Repo and branch:** tt-commander-app, branch `library-source` off `csrf-token`.
**Spec:** section 4, the "library source" part.

**Files:**
- Create: `src/model/fpgaLibrary.ts` and `src/model/fpgaLibrary.spec.ts`.
- Create: `src/model/testing/fpga-library.json`, a copy of the Task 1 fixture.
- Modify: `src/model/fpgaDesigns.ts`:
  - the `FpgaDesign` type at lines 9-19;
  - `designToProject` at 52-64;
  - `syncSelectionToEnabled` at 98-106;
  - `loadFpgaDesigns` at 109-127.
- Modify: `src/model/shuttle.ts:7-21`, adding `shuttle?: string` and `source?: 'demo' |
  'upload' | 'library'`.
- Modify: `src/ttcontrol/TTBoardDevice.ts:130-146`, `selectFpgaDesign`, plus a
  `designNotice` data field.
- Modify: `src/components/ProjectSelect.tsx:83-90`.
- Modify: `src/components/PinoutPanel.tsx:44-52`: a library project takes `pinout` and
  `description` from its index entry, not from `fpgaDesigns.byName` (finding N2).
- Modify: `src/components/BoardConfigPanel.tsx:190-235`.
- Modify: `README.fpgas-online.md`.
- Test: `src/model/fpgaLibrary.spec.ts`, `src/ttcontrol/TTBoardDevice.spec.ts`,
  `src/components/BoardConfigPanel.spec.tsx`, `src/components/PinoutPanel.spec.tsx`.

**Interfaces:**
- Consumes: Task 7's routes, Task 9's `setCsrfToken`, and Task 8's badge texts, copied.
- Produces:
  - the `LibraryEntry` type;
  - `fpgaLibrary` store `{state: 'idle' | 'loading' | 'ready' | 'notPublished' | 'error',
    byId}`;
  - `loadFpgaLibrary(apiBase: string): Promise<void>`;
  - `loadLibraryDesign(apiBase: string, id: string): Promise<{enabled: string; ui_in: number
    | null; ui_in_driven: number[]; ui_in_held: number[]; released: number[]; pushed: boolean;
    hides_upload: boolean}>`;
  - `libraryWarnings(e: LibraryEntry): {text: string; cls: 'warn' | 'info'}[]`;
  - `mergeProjects(designs: FpgaDesign[], library: LibraryEntry[]): Project[]`, keyed by
    (`macro`, `source`), with `address` = position in the list;
  - `PROJECT_LIMIT = 100`.

- [ ] **Step 1: Write the failing tests**
  - `library not loaded when designs lack the library key`
  - `merge keeps board designs first then index order, address is position`
  - `a library entry and an upload of the same name are two projects`
  - `selection prefers the source /designs reports for the enabled name`
  - `enabled id missing from list does not throw`
  - `notPublished state on 404`
  - `warnings match the site table`
  - In `TTBoardDevice.spec.ts`:
    - `selectFpgaDesign routes library projects to the load route and calls syncState`
    - `selectFpgaDesign keeps enableFpgaDesign for demos`
    - `load error goes to designError`
  - In `BoardConfigPanel.spec.tsx`:
    - `timing-fail shows warning icon and Load stays enabled`
    - `designNotice shows inputs set`
    - `search matches shuttle and macro`
    - `options capped at 100 with a narrow-down line`
  - In `PinoutPanel.spec.tsx`:
    - `Pinout tab of an enabled library design shows the index pinout`: `/designs` lists the
      entry in the upload shape (`pinout: {}`), the index entry has `uo_out` labels, and the
      tab shows `R1` for `uo[0]`.
    - `library entry missing from the index renders an empty pinout without throwing`.
- [ ] **Step 2: Run them and record the failures.** `tmp/t10.log`.
- [ ] **Step 3: Implement.** Map `warn` badges to `danger_level: 'medium'`, with
  `danger_reason` set to the badges joined by `; `. Never set `'high'`.
- [ ] **Step 4: Run lint, typecheck, vitest and `npm run build:embed`, each logged separately.**
  Expected: all pass, and `dist/embed/tt-commander-embed.js` exists.
- [ ] **Step 5: Commit** "fpga: VGA library as a third design source", then push. After
  merge, Tim tags `embed-v0.3.0`.

## Task 11: Docs and mirror summary for the harness's files (tinytapeout-vga-videos)

**Repo and branch:** tinytapeout-vga-videos, branch `fpga-library-foreign` off `origin/main`
**after** the raw-traces pipeline plan's Task 16 has merged. **Spec:** section 5.

Pipeline Task 16 (`docs/superpowers/plans/2026-11-26-raw-traces-pipeline.md:719-721` on
`main`) owns `verify.FOREIGN_PATTERNS`, the mirror's excludes and `tests/test_mirror.py`
(finding N3). This task does not change the excludes, holds no copy of the list, and does not
create `tests/test_mirror.py`.

**Files:**
- Modify: `ttvga/remote.py`, the summary lines of the mirror script (after Task 16's version).
- Modify: `docs/publishing.md`, adding a section "Files the FPGA harness owns" that names
  `<shuttle>/<macro>/*.bin` and `fpga-library.json`, their owner (the tt-harness-fpga-vga
  session), `verify.FOREIGN_PATTERNS` as the list, and the spec path.
- Modify: `tests/test_mirror.py`, created by Task 16; add one test.

**Interfaces:**
- Consumes: `ttvga.harness.verify.FOREIGN_PATTERNS`, and `remote.mirror_script(src: str,
  dest: str, dry_run: bool) -> str`, which pipeline Task 16 exposes (the controller carries
  this into that task's brief; finding m-c). This task adds its summary lines inside
  `mirror_script` and tests them through it.

- [ ] **Step 1: Write the failing test** `test_mirror_summary_counts_bitstreams`: the script
  prints `bitstreams:` (a `find` for `*.bin` under the destination) and `fpga-library.json:`
  (`present` or `absent`).
- [ ] **Step 2: Run it and record the failure.** `uv run pytest tests/test_mirror.py >>
  tmp/t11.log 2>&1`.
- [ ] **Step 3: Add the two summary lines and the docs section.**
- [ ] **Step 4: Run `uv run pytest >> tmp/t11.log 2>&1`.** Expected: all pass, including Task
  16's own mirror tests.
- [ ] **Step 5: Commit** "mirror: count the FPGA harness's files in the summary; document
  them", then push.

## Task 12: Harness publisher, the interface contract (tt-harness-fpga-vga session)

The tt-harness-fpga-vga session executes this task. The controller sends the session this task
and spec section 6, then waits for the pushed branch.

**Contract:**
- The command is `tthfv publish --archive <dir>`. The path is never recorded in the repo.
- The id is `library_id` exactly as in the Global Constraints (Ruling AC). It replaces
  `demo_name` at `tthfv/demos.py:53-59` on `demos-export`. The test vectors are the five rows of
  the spec's id table plus the hashed row.
- `ui_in_mask` comes from `effective_ui_in_mask` for the Welland tie profile.
  - `ui_in` is the override value, limited to the mask.
  - `ui_in` is null when the mask is 0.
- `fmax_hz` is an int.
- The JSON is written with `allow_nan=False`.
- Entries are ordered newest shuttle first, then by title, with each shuttle contiguous.
- No warning text goes in `title`.
- The output passes `tt-vga fpga-library-check`.
- The write order is:
  1. the bins, skipping existing names;
  2. `fpga-library.json.tmp`;
  3. the check, which must exit 0;
  4. `rename` into place.
- Old bins are never deleted. Files are mode 0644, directories 0755.
- Nothing is written to `/srv/data.wafer.space` until Tim has approved the format.

- [ ] **Step 1: Send the contract and the spec path** to the session.
- [ ] **Step 2: Receive the session's pushed branch and its dry-run output** in a local
  directory. Run `uv run tt-vga fpga-library-check <out>/fpga-library.json --bins <out> >>
  tmp/t12.log 2>&1`. Expected: exit 0, recorded in the log.

## Task 13: Hardware check on one FabricFox board

**When:** after spec section 8, steps 1 to 5 are deployed and published. **Spec:** section 9,
Hardware check.

**Files:**
- Create: `tmp/t13-hardware.log` and screenshots. They are not committed.
- Create: a claim at `~/github/TinyTapeout/tmp/board-claims/<board>-p<port>.json`.

- [ ] **Step 1: Claim the board.** Choose it per owner question 4. Confirm the USB serial.
  `status.json` must show `clients == 0` and the idle display `loaded`. Write the claim with
  UTC times and a 30-minute expiry.
- [ ] **Step 2: Read-only checks.** Log each `curl` to `tmp/t13-hardware.log`.
  - `/designs` has the top-level `library` key. Record the upload names.
  - `/library` has about 445 designs, including `ttsky25a_vga_example`.
  - In the Commander REPL, read only:
    - `print(tt.mode_str)`;
    - for i in 0..7, `print(getattr(tt.pins, 'ui_in%d' % i).mode_str)`;
    - `import machine; print(hex(machine.mem32[0xd0000030]))`, which prints `GPIO_OE`;
    - `m = machine.mem32[0x40000000]; n = m >> 28; print(hex(m), n, (n & 3) | ((n & 8) >> 1))`,
      which prints SYSINFO `CHIP_ID`, the raw revision nibble, and the SDK's decoded version
      (pico-sdk `rp2350/pico_platform/platform.c:20-22`): 2 means A2, 4 means A4. Record both
      the raw nibble and the decoded value.

    Record the results in the log and report them to the controller, which records them in
    spec section 2, Input pins at rest (findings N1 and P1). If the chip is A4, say so; the
    discharge step stays. Change nothing.
- [ ] **Step 3: Load from the board page.** Load `ttsky25a_vga_example` through the board page,
  driven by Playwright.
  - The response shows `pushed: true`.
  - `/designs` shows it enabled, with `source: "library"`.
  - Save a camera screenshot to `tmp/t13-pattern.png`.
- [ ] **Step 4: Load it again.** The response shows `pushed: false`.
- [ ] **Step 5: Load a `ui_in` entry through the Commander and check the clock.** Use the first
  entry with `ui_in` not null.
  - `ui_in_driven` equals the mask's bits, and `ui_in_held` is empty.
  - In the Commander REPL, run `print(tt.is_auto_clocking, tt.auto_clocking_freq)`. It must
    print `True` and the entry's `clock_hz`.
  - The camera shows a picture (`tmp/t13-ui-in.png`).
- [ ] **Step 6: Load the `tt_um_vga_pattern` demo from the gallery.** `released` lists Step 5's
  bits, and the clock is the demo's. Read each released pin's level read-only with
  `print([getattr(tt.pins, 'ui_in%d' % i)() for i in <released>])`. Every value must be 0
  (finding P1). The reading is taken on the pad node the FPGA sees, after the pull-down
  (finding q-a). Also read and record the levels of the pins released straight to inputs; if
  any reads 1, report it to the controller (the case Ruling AF reserves the IE workaround for).
- [ ] **Step 7: Restore.** Run vgacap `tools/board_restart.py <ws link>`. Wait for the idle
  display to show `loaded`. The upload names must equal Step 2's. Delete the claim. If `clients`
  ever goes above 0, stop at once and restore.
- [ ] **Step 8: Report the log and screenshots** to the controller. Total time on the board
  must be under 10 minutes.
