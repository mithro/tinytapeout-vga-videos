# VGA library source: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visitors at tinytapeout.fpgas.online, using either the board page or the customised
Commander, can load any of about 445 prebuilt Tiny Tapeout VGA bitstreams from the VGA archive
onto a FabricFox board. This is a third source, `library`, beside the packaged demos and
visitor uploads.

**Architecture:**
- The archive holds `fpga-library.json` and content-addressed `.bin` files, which the harness
  session publishes.
- The site backend on tweed fetches and checks them, then pushes the bytes into a separate
  library cache in the fpgas-tt daemon on the Pi.
- Loading uses the daemon's existing `load_design` path, with `clock_hz` and `ui_in` applied
  in the same REPL step.
- board.js and the Commander both list the site's checked index and call one site load route.

**Tech Stack:**

| Repository | Stack |
|---|---|
| daemon | Python 3.11, aiohttp, pytest |
| site | Django, requests, pytest, `node --test` |
| Commander | Solid.js and TypeScript, vitest |
| videos | Python, uv, pytest |

**Spec:** `docs/superpowers/specs/2026-11-26-fpga-library-source-design.md` (this repository,
commit `06140b6`, branch `fpga-library-spec`). Read the spec section each task names before
starting.

## Global Constraints

- The schema is exactly spec section 1. Readers ignore unknown keys. No `count`, `source_id`,
  `status` or `warnings` keys.
- The id rule:
  1. Take `lower(<shuttle> + "_" + <macro without the leading "tt_um_">)`.
  2. Map every character outside `[a-z0-9_]` to `_`.
  3. If the result is over 40 characters: its first 31 characters, then `_`, then the first 8
     lowercase hex digits of the SHA-256 of the UTF-8 string `<shuttle>/<macro>`, which keeps
     its original case and `tt_um_`.

  A macro without `tt_um_` is an error.
- Names: `^[a-z0-9_]{1,40}\Z`. Bitstreams: at most 262144 bytes, with the preamble
  `7E AA 99 7E` in the first 68 bytes.
- `clock_hz` is from 1 to 200000000. `ui_in` is an int from 0 to 255, or null; a bool is never
  accepted as an int.
- Archive base URL (fixed): `https://data.wafer.space/big-storage/tinytapeout-vga-videos/`.
- Daemon library: `--library-dir` defaults to `/var/lib/fpgas-tt/library`, and
  `--library-max-bytes` to `16777216`. It is LRU by the mtime of `<id>.json` and never touches
  uploads.
- Every POST from a page carries `X-CSRFToken`. No view is `csrf_exempt`.
- Python is run through `uv run` (never bare `python`, never `python -c`). Never
  `2>/dev/null`. Never `/tmp`: logs go to `<worktree>/tmp/` (gitignored in all five repos).
  Never pipe a command into grep or tail; log to a file, then grep the file.
- Workflow:
  - Each task gets its own worktree and branch: `<repo>/.worktrees/<branch>`, created with
    `git worktree add -b <branch> .worktrees/<branch> <base>`.
  - Make small commits and push after each one (`git push -u origin <branch>`).
  - A task ends at "push branch". The controller opens the PR to Tim after independent review.
- Commit trailer, on every commit:

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01M4cwEsPm9kJ96LQeYKwqhK
  ```
- Follow each repo's own `CLAUDE.md`. In the daemon and the site: ruff, line length 120, and
  docstrings in the existing plain-English style. In the Commander: prettier, an SPDX header,
  and base branch `fpgas-online`.
- No hardware access except in Task 11.

## Review Focus

These are the five conditions most likely to bite a user that no task's main tests cover. Each
has its pinning test in the task named.

1. **The archive serves the index before the `.bin` it names** (the onward rsync reorders
   them). The user should see "may still be syncing", not a 502 stack. Test
   `test_load_bin_404_says_still_syncing` in Task 5.
2. **Two browser tabs press Load on the same board at once.** The second should get 409 "a
   library load is already running", and the first should still finish. Test
   `test_second_concurrent_load_gets_409` in Task 5.
3. **A search with no matches, or a filter change while on page 7.** The page should reset to
   1, show "0 of N designs", and never show a negative or empty page range. Test
   `paging clamps and resets` in Task 6.
4. **A library entry evicted on the Pi while it is the enabled design.** `/designs` no longer
   lists it, but `enabled` still names it. The gallery and the Commander should show it as
   running without crashing. Tests `test_enabled_library_design_not_in_cache_still_lists_enabled`
   in Task 2, and `enabled id missing from list does not throw` in Task 8.
5. **The site's cache is cold and the archive is down on the first request.** That should be a
   clean 502 "VGA library unavailable", and the panel should offer Retry. Test
   `test_index_cold_and_archive_down_is_502` in Task 5.

---

## Task 1: Schema module, checker CLI and fixture (tinytapeout-vga-videos)

**Repo:** `~/github/TinyTapeout/tinytapeout-vga-videos`. Branch `fpga-library-schema` off
`origin/main`. Spec section 1.

**Files:**
- Create: `ttvga/fpgalibrary.py`
- Create: `tests/fixtures/fpga-library/fpga-library.json`
- Create: `tests/fixtures/fpga-library/<shuttle>/<macro>/<id>-<sha12>.bin` (5 files)
- Create: `tests/fixtures/fpga-library/make_fixture.py`, which writes the bins and the hashes
  into the JSON, so the fixture can be rebuilt
- Modify: `ttvga/cli.py:16-22` (register the parser)
- Test: `tests/test_fpgalibrary.py`

**Interfaces:**
- Produces:
  - `library_id(shuttle: str, macro: str) -> str`, which raises `ValueError` when the macro
    lacks `tt_um_`;
  - `validate(doc: object) -> list[str]`: each violation as `"designs[3].ui_in: must be int
    0..255 or null"`, empty when valid;
  - `check_bins(doc: dict, root: Path) -> list[str]`;
  - `load(path: Path) -> object`;
  - `FOREIGN: tuple[str, ...] = ("/*/*/*.bin", "/fpga-library.json")`;
  - `add_parser(sub)`, which adds `fpga-library-check <file> [--bins DIR]` and exits 0 or 1,
    printing each violation;
  - the fixture path `tests/fixtures/fpga-library/`, which Tasks 2, 4 and 8 copy.

The fixture's five entries (spec section 1, Reference validator):

| id | shuttle/macro | build_status | ui_in | paths |
|---|---|---|---|---|
| `ttsky25a_vga_example` | `ttsky25a/tt_um_vga_example` | `ok` | null | all set |
| `tt05_flappy_vga_cutout1` | `tt05/tt_um_flappy_vga_cutout1` | `timing-fail`, `fmax_mhz` 17.08 | null | all set |
| `ttihp25a_yuri_panchul_sea_battl_09a2562b` | `ttihp25a/tt_um_yuri_panchul_sea_battle_vga_game` | `ok` | null | all set |
| `ttsky25b_lukasdragoste_vga_patterns` | `ttsky25b/tt_um_lukasdragoste_vga_patterns` | `ok` | 5 | all set |
| `ttihp26a_vga_example` | `ttihp26a/tt_um_vga_example` | `ok` | null | `poster`, `preview_gif`, `video_10s_webm` null |

Each bin is 4096 bytes: `ff 00 00 ff 7e aa 99 7e`, then zeros, with byte 8 set to the entry's
index (0 to 4) so the hashes differ. Use `validation: "none"`, `qspi: "none"` and
`verdict: "ok"` throughout, except `verdict: "barely-moving"` on the fourth entry.

- [ ] **Step 1: Write the failing tests** in `tests/test_fpgalibrary.py`:
  - `test_library_id_examples`: the four example rows of spec section 1, exactly.
  - `test_library_id_hashed_is_40_chars`: for
    `("ttsky25a", "tt_um_rebeccargb_vga_timing_experiments")`, the result is
    `"ttsky25a_rebeccargb_vga_timing__4638a050"` and its length is 40.
  - `test_library_id_hash_uses_original_case`: `library_id("tt07", "tt_um_MichaelBell_rle_vga")`
    equals `"tt07_michaelbell_rle_vga"` (not cut). For a made-up macro with 50 uppercase letters,
    the last 8 characters equal `sha256(b"tt07/tt_um_" + upper)[:8]`.
  - `test_library_id_refuses_non_tt_um`: `ValueError`.
  - `test_fixture_is_valid`: both `validate(load(fixture))` and `check_bins(doc, fixture_dir)`
    are empty.
  - `test_each_rule_is_enforced`: parametrised, one mutation per row of the spec's entry and
    top-level tables, plus these: a duplicate id; an id equal to `idle_display`; an id equal to
    `tt_um_vga_pattern`; `bin` not equal to `<shuttle>/<macro>/<id>-<sha12>.bin`; a path with
    `..`; an absolute `https://` poster; `ui_in` set to `True`; `pinout.uo_out` with 7
    elements; an unknown top-level key (allowed); `generated` without `Z`. Each case asserts
    that exactly one violation's prefix names the field.
  - `test_check_bins_catches`: a wrong size, a wrong hash, a missing preamble and a missing
    file. Each gives one violation.
  - `test_cli_exit_codes`: `main(["fpga-library-check", str(fixture), "--bins",
    str(fixture_dir)]) == 0`. On a mutated copy in `tmp_path` it returns 1 and prints the
    violation.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_fpgalibrary.py -v >> tmp/t1.log 2>&1`,
  then grep the log. Expected: they fail, with `ModuleNotFoundError: ttvga.fpgalibrary`.
- [ ] **Step 3: Write `make_fixture.py`, then run it** (`uv run
  tests/fixtures/fpga-library/make_fixture.py`) and commit its output. The demo names to check
  against live in the module as `DEMO_NAMES = ("tt_um_counter_7seg", "tt_um_factory_test",
  "tt_um_pwm_breathe", "tt_um_uart_hello", "tt_um_vga_pattern")`. Add a comment naming
  tinytapeout-fpga-demos `da7d10d` as their source.
- [ ] **Step 4: Implement `ttvga/fpgalibrary.py` and register it in `cli.py`.** Write one rule
  function per key, driven by a table, so that each rule appears exactly once.
- [ ] **Step 5: Run the whole suite.** `uv run pytest >> tmp/t1.log 2>&1`. Expected: everything
  passes.
- [ ] **Step 6: Commit** ("fpgalibrary: schema 1 checker, id rule and fixture"), then push the
  branch.

## Task 2: Daemon library store, routes and listing (fpgas.online-tt)

**Repo:** `~/github/fpgas-online/fpgas.online-tt`. Branch `library-source` off `origin/main`.
Spec section 2, except `ui_in`.

**Files:**
- Create: `src/fpgas_tt/library.py` (the store and the metadata checks)
- Modify: `src/fpgas_tt/designs.py:100-160` (`_meta`, `design_names`, `design_file`,
  `validate_bitstream`, `_listing`, `list_designs`, `enable_design`)
- Modify: `src/fpgas_tt/server.py` (`create_app`, the routes, `build_parser`, `main`, the module
  docstring)
- Modify: `README.md` (route table), `CLAUDE.md` (module list, invariant note)
- Create: `tests/data/library/` (a copy of Task 1's fixture; its first line `_comment` names the
  source commit)
- Test: `tests/test_library.py` (store), `tests/test_server.py`, `tests/test_designs.py`

**Interfaces:**
- Consumes: Task 1's fixture, copied.
- Produces:
  - `library.LIBRARY_DIR_DEFAULT = Path("/var/lib/fpgas-tt/library")` and
    `library.LIBRARY_MAX_BYTES_DEFAULT = 16 * 1024 * 1024`;
  - `library.STORED_KEYS`, the 21-key tuple of spec section 2, Store;
  - `library.check_meta(meta: object) -> str | None`, the first violation or None (the rules
    of spec section 1; the 40-character id rule is checked with `designs.NAME_RE`);
  - `library.store(library_dir: Path, meta: dict, data: bytes, max_bytes: int) -> tuple[bool,
    list[str]]`, returning `(created, evicted)`;
  - `library.entries(library_dir) -> list[dict]`, each `{"id", "bin_sha256", "bin_bytes",
    "used_at"}`;
  - `library.names(library_dir) -> set[str]`;
  - `library.meta(library_dir, id) -> dict | None`;
  - `library.touch(library_dir, id) -> None`;
  - `library.used_bytes(library_dir) -> int`.

  `designs.py` functions gain a `library_dir: Path` parameter after `uploads_dir`:
  `design_names`, `design_file`, `_listing`, `list_designs` and `enable_design`. In
  `enable_design` it goes after `uploads_dir` and before the keyword-only `waited`. Task 3
  adds `ui_in`.

  The wire contract is exactly spec section 2: `GET /library`, `POST /library/{id}`,
  `/designs` with the top-level `library` object and each design's `library: null | {...}`.
  `app["library_dir"]` and `app["library_max_bytes"]` are set in `create_app(...,
  library_dir=..., library_max_bytes=...)`.

- [ ] **Step 1: Write the failing store tests** in `tests/test_library.py`:
  - `test_store_writes_bin_then_json_and_lists_it`;
  - `test_same_sha_push_is_idempotent_and_refreshes_lru` (returns `(False, [])`; the mtime
    increases);
  - `test_new_build_replaces_old_bytes`;
  - `test_lru_evicts_oldest_until_it_fits`: `max_bytes = 3*4096`, push 4, and the first is
    evicted;
  - `test_eviction_never_touches_uploads`: an uploads dir with 16 files is unchanged;
  - `test_entry_without_json_is_not_listed`;
  - `test_check_meta_rules`: parametrised over the same mutations as Task 1's
    `test_each_rule_is_enforced` for entry keys;
  - `test_concurrent_stores_lose_nothing`: 8 threads each push a distinct id, under a cap that
    fits all 8, and all 8 are listed.
- [ ] **Step 2: Write the failing designs and server tests.**
  - In `tests/test_designs.py`:
    - `test_precedence_demo_then_library_then_upload`;
    - `test_upload_refused_for_cached_library_id` (`ValidationError` with status 409, message
      contains `is a VGA library design`);
    - `test_listing_reports_library_entries_with_metadata` (`source == "library"`; the
      `library` object has exactly the 11 keys of the spec's `/designs` example; demos and
      uploads have `library is None`);
    - `test_enabled_library_design_not_in_cache_still_lists_enabled` (Review Focus 4: the board
      reports an enabled id that is not cached, and `list_designs` returns that `enabled` with
      no exception);
    - `test_enable_reads_library_bin_and_touches_lru`.
  - In `tests/test_server.py`:
    - `test_get_library`;
    - `test_designs_has_top_level_library_key` (`{"max_bytes": 16777216, "used_bytes": n}`);
    - `test_push_checks`: parametrised over the spec's `POST /library/{id}` table, one case per
      row, asserting status and error text;
    - `test_push_created_then_idempotent_200`;
    - `test_push_counts_as_activity`;
    - `test_library_routes_obey_fpga_only`: 404 on `IS_OTHER`, 503 on `NOT_NAMED`;
    - `test_cli_library_flags`: `build_parser().parse_args([])` gives
      `/var/lib/fpgas-tt/library` and `16777216`.
- [ ] **Step 3: Run them.** `uv run pytest tests/test_library.py tests/test_designs.py
  tests/test_server.py >> tmp/t2.log 2>&1`. Expected: the new tests fail and the old ones pass.
- [ ] **Step 4: Implement.**
  - Writes use `tempfile.mkstemp` in the directory, then `os.replace`, as `store_upload` does
    (designs.py:166-185).
  - `_LIBRARY_LOCK = threading.Lock()` lives in `library.py`.
  - `POST /library/{id}` reuses `bitstream_upload`'s bounded part loop (server.py:243-260). Move
    it into a helper `_read_parts(request, limits: dict[str, int]) -> dict[str, bytes] |
    web.Response`, used by both routes; this must not change `/bitstream`'s behaviour or its
    tests. The limits are `meta` 32768 bytes and `file` `MAX_BITSTREAM_BYTES`.
  - The store runs in `asyncio.to_thread`.
- [ ] **Step 5: Run the full suite and the linter.** `uv run pytest >> tmp/t2.log 2>&1; uv run
  ruff check >> tmp/t2.log 2>&1`. Expected: all pass, and ruff is clean.
- [ ] **Step 6: Update the README and CLAUDE.md.** Commit in three commits: the store; the
  routes and listing; the docs. Then push the branch.

## Task 3: `ui_in` on enable (fpgas.online-tt)

**Repo:** fpgas.online-tt. Branch `library-ui-in` off `library-source` (stacked; its PR goes
after Task 2's). Spec section 2, `POST /designs/{name}/enable`.

**Files:**
- Modify: `src/fpgas_tt/designs.py` (`LOAD_CODE`, `_load_steps`, `load_design`,
  `enable_design`)
- Modify: `src/fpgas_tt/safe.py:84-95` (use the shared guard)
- Modify: `src/fpgas_tt/server.py:181-218` (body checks)
- Modify: `README.md`
- Test: `tests/test_designs.py`, `tests/test_server.py`, `tests/test_safe.py`

**Interfaces:**
- Consumes: Task 2's signatures.
- Produces:
  - `designs.UI_IN_GUARD: str`, the per-pin guard loop with no indentation. Callers indent it.
    It needs `_fo_tt`, `Pin` and `time` in scope, and it fills `_fo_held: list[int]`.
  - `enable_design(runner, name, clock_hz, ui_in, demos_dir, uploads_dir, library_dir, *,
    waited=0.0) -> {"enabled", "clock_hz", "ui_in", "ui_in_held"}`.
  - `load_design(runner, name, data, clock_hz, ui_in, *, overall) -> list[int]`, which returns
    the held pins.
  - `_load_steps(name, data, clock_hz, ui_in) -> list[str]`.

- [ ] **Step 1: Write the failing tests.**
  - `test_load_code_unchanged_when_ui_in_is_null`: compare `_load_steps(n, d, 1000, None)[-1]`
    with a snapshot of today's output, kept as `tests/data/load_code_no_ui_in.txt` and
    generated before any change.
  - `test_ui_in_sets_mode_guards_pins_then_value`: the last step contains, in this order,
    `ASIC_RP_CONTROL`, `ui_in.value = 0`, `PULL_DOWN`, `ui_in.value = 5`,
    `print('ui_in_held=`, and `print('enabled')`. All of it comes after the clock line, and
    `ui_in.value = 5` sits inside the success path (after `_fo_ok = True`).
  - `test_enable_returns_ui_in_held`: the fake REPL replies `ui_in_held=[3]\nenabled`, and the
    result has `ui_in_held == [3]`.
  - `test_safe_code_unchanged`: compare `safe.safe_code(False)` and `safe.safe_code(True)` with
    snapshots taken before the change (`tests/data/safe_code_*.txt`).
  - `test_enable_body_ui_in`: parametrised. `true`, `-1`, `256`, `"5"` and `5.0` give 400 `ui_in
    must be an integer between 0 and 255`. `5` and `null` give 200, and the response echoes
    `ui_in`.
- [ ] **Step 2: Run them and record that they fail** (`tmp/t3.log`).
- [ ] **Step 3: Implement.** Extract the guard from `SAFE_CODE` into `UI_IN_GUARD` and import
  it in `safe.py`, so the snapshots stay identical. Add the `__UI_IN__` placeholder after
  `__CLOCK__`. Parse the `ui_in_held=` line from the last output before checking `enabled`.
- [ ] **Step 4: Run the full suite and ruff.** Expected: all pass.
- [ ] **Step 5: Commit** ("enable: ui_in applied with the pin guard in the load step"), then
  push the branch.

## Task 4: Site archive client and daemon client (fpgas.online-site)

**Repo:** `~/github/fpgas-online/fpgas.online-site`. Branch `vga-library` off `origin/main`.
Spec section 3: Setting, `ttsite/library.py` and Caching.

**Files:**
- Create: `ttsite/src/ttsite/library.py`
- Modify: `ttsite/src/ttsite/daemon.py` (add `library_state`, `library_push`, `Unsupported`)
- Modify: `pib/settings.py:216-220` (`TTSITE_LIBRARY_BASE_URL`)
- Create: `tests/data/fpga-library.json` (a copy of Task 1's fixture, with its `_comment`)
- Test: `tests/test_library.py`, `tests/test_daemon.py`, `tests/test_settings_import.py`

**Interfaces:**
- Consumes: Task 2's wire contract.
- Produces:
  - `library.ArchiveError(Exception)`, with `.message: str`;
  - `library.normalise(doc: object, base_url: str) -> tuple[dict, list[str]]`, returning the
    site wire format `{"schema": 1, "generated", "base_url", "designs"}` and the dropped
    reasons; it raises `ArchiveError("VGA library unavailable")` when the top level is invalid;
  - `library.index() -> tuple[bytes, str, int | None]`: the normalised body, the site ETag
    `"sha256:<16 hex>"`, and the stale age in seconds or None. It raises `ArchiveError` when it
    has neither a fresh copy nor one at most 24 h old.
  - `library.entry(id: str) -> dict | None`;
  - `library.fetch_bin(entry: dict) -> bytes`, which raises `ArchiveError` with the spec's
    exact messages;
  - `library.FRESH_SECONDS = 300`, `library.STALE_SECONDS = 86400`,
    `library.INDEX_MAX_BYTES = 4 * 1024 * 1024`;
  - `daemon.library_state(board) -> tuple[int, dict]`, which raises `daemon.Unsupported` on a
    404 with a non-JSON body;
  - `daemon.library_push(board, name: str, meta: dict, data: bytes) -> tuple[int, dict]`, with
    timeout `(3.05, 15.0)`.

- [ ] **Step 1: Write the failing tests.** Use a fake `requests.get` installed with
  `monkeypatch.setattr(library.requests, "get", ...)`, returning objects with `status_code`,
  `headers` and `iter_content`.
  - `test_normalise_fixture_keeps_all_and_adds_base_url`;
  - `test_normalise_drops_bad_entry_and_logs`, parametrised over three rule mutations;
  - `test_normalise_drops_both_duplicates`;
  - `test_normalise_refuses_bad_top_level`: schema 2, `designs` an object, and 2001 entries;
  - `test_index_sends_if_none_match_and_keeps_copy_on_304`;
  - `test_index_refuses_redirect`: a 301 raises, and the cache is untouched;
  - `test_index_caps_size`: 4 MiB + 1 byte raises;
  - `test_index_serves_stale_then_gives_up`: with the clock faked through `library.time` (an
    injected `now()`), the archive down after a good fetch gives stale age 400 at 700 s, and
    `ArchiveError` after 86400 + 300 s;
  - `test_fetch_bin_checks_size_hash_preamble`, parametrised;
  - `test_fetch_bin_404_message`: the message equals `archive file missing (the archive may
    still be syncing; try again in a few minutes)`;
  - `test_fetch_bin_never_leaves_base_host`: an entry whose `bin` was tampered with after
    normalising to `../x` raises before any request is made;
  - `test_library_state_old_daemon_is_unsupported`;
  - `test_library_push_sends_meta_and_file_parts`;
  - `test_setting_default`: `settings.TTSITE_LIBRARY_BASE_URL ==
    "https://data.wafer.space/big-storage/tinytapeout-vga-videos/"`.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_library.py tests/test_daemon.py
  tests/test_settings_import.py >> tmp/t4.log 2>&1`. Expected: the new tests fail.
- [ ] **Step 3: Implement.**
  - Duplicate the schema rules in `library.py` from the spec; do not import from
    tinytapeout-vga-videos.
  - Use `requests.get(..., allow_redirects=False, stream=True, timeout=(3.05, 10.0))` and read
    with `iter_content(65536)`, counting bytes.
  - Cache in `django.core.cache.cache` under the key `ttsite:library:index`.
- [ ] **Step 4: Run the full suite and ruff** (`tmp/t4.log`). Expected: all pass.
- [ ] **Step 5: Commit** ("ttsite: VGA library archive client"), then push the branch.

## Task 5: Site routes (fpgas.online-site)

**Repo:** fpgas.online-site. Branch `vga-library` (the same branch, after Task 4; one PR). Spec
section 3, Routes.

**Files:**
- Modify: `ttsite/src/ttsite/views.py` (add `api_library`, `api_library_load`)
- Modify: `ttsite/src/ttsite/urls.py:14-16`
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: Task 4's `library.index`, `library.entry`, `library.fetch_bin`,
  `daemon.library_state`, `daemon.library_push` and `daemon.Unsupported`, plus the existing
  `daemon.enable`.
- Produces:
  - URL names `ttsite-api-library` (`api/board/<slug:slug>/library`) and
    `ttsite-api-library-load` (`api/board/<slug:slug>/library/<str:name>/load`);
  - the load response: the daemon's enable body plus `"pushed": bool`.

- [ ] **Step 1: Write the failing tests.** Follow the existing `boards` fixture and monkeypatch
  `ttsite.daemon` and `ttsite.library`.
  - `test_library_index_etag_and_304`;
  - `test_library_index_gzip` (with `HTTP_ACCEPT_ENCODING="gzip"`, `Content-Encoding: gzip`);
  - `test_library_index_stale_header`;
  - `test_library_index_404_on_asic_board`;
  - `test_index_cold_and_archive_down_is_502` (Review Focus 5);
  - `test_library_off_when_setting_empty` (404);
  - `test_load_cached_entry_skips_fetch` (`fetch_bin` is not called; `pushed` is false);
  - `test_load_pushes_then_enables_with_index_values` (the enable body is exactly
    `{"clock_hz": 25175000, "ui_in": null}` for the first fixture entry, and `{"clock_hz":
    25175000, "ui_in": 5}` for the fourth);
  - `test_load_old_daemon_501` (the error is exactly `board software too old`);
  - `test_load_retries_once_after_404_enable`;
  - `test_load_unknown_id_404`;
  - `test_load_bad_name_404` (`Tt_UM`, 41 characters);
  - `test_load_bin_404_says_still_syncing` (Review Focus 1; status 502, and `error` carries the
    syncing message);
  - `test_second_concurrent_load_gets_409` (Review Focus 2: the lock key already set gives 409,
    and the key is removed after a normal load);
  - `test_load_requires_csrf` (`Client(enforce_csrf_checks=True)` without a token gives 403,
    and with the cookie and the `X-CSRFToken` header gives 200);
  - `test_load_clears_designs_cache`;
  - `test_load_skips_retry_after_20s` (with the clock injected).
- [ ] **Step 2: Run them and record that they fail** (`tmp/t5.log`).
- [ ] **Step 3: Implement both views.** `api_library` uses `@require_GET @gzip_page` and caches
  the board check under `ttsite:library:board:<slug>` for 60 s. `api_library_load` uses
  `@require_POST` and follows the spec's steps 1 to 7 exactly, with the lock released in
  `finally`.
- [ ] **Step 4: Run the full suite and ruff.** Expected: all pass.
- [ ] **Step 5: Commit** ("ttsite: VGA library index and load routes"), then push.

## Task 6: VGA library panel (fpgas.online-site)

**Repo:** fpgas.online-site. Branch `vga-library` (after Task 5). Spec section 3, The VGA
library panel, and the warnings table in section 1.

**Files:**
- Create: `ttsite/src/ttsite/static/ttsite/library.js`
- Modify: `ttsite/src/ttsite/static/ttsite/board.js:120-232`
- Modify: `ttsite/src/ttsite/templates/ttsite/board.html:36-50`
- Modify: `ttsite/src/ttsite/static/ttsite/ttsite.css`
- Modify: `ttsite/src/ttsite/views.py:50-70` (`library_enabled` in the board context)
- Create: `tests/js/library.test.mjs`, `tests/test_library_js.py` (copy the pattern of
  `tests/test_power_button_js.py`)
- Create: `tests/fake_library_server.py` (dev-server settings override for the manual check)
- Modify: `tests/test_static.py`, `tests/test_views.py`

**Interfaces:**
- Consumes: Task 5's routes, and the site wire format from Task 4.
- Produces: `library.js` exports, CommonJS and `window.ttsiteLibrary`, as `power-button.js`
  does:
  - `matches(entry, query: string) -> bool`;
  - `shuttleOrder(shuttles: string[]) -> string[]`, with
    `SHUTTLE_ORDER = ["ttsky26c","ttsky26a","ttihp26a","ttsky25b","ttsky25a","ttihp25b","ttihp25a","ttcad25a","ttgf0p3","ttgf0p2","ttgf0p1","ttihp0p4","ttihp0p2","ttihp0p1","tt10","tt09","tt08","tt07","tt06","tt05of","tt05","tt04","tt03p5","tt03"]`;
  - `page(items: any[], pageNo: number, perPage = 24) -> {items, pageNo, pages}`;
  - `badges(entry) -> {text: string, cls: "warn" | "info"}[]`;
  - `assetUrl(base: string, path: string | null) -> string | null`.

  The Commander (Task 8) copies `SHUTTLE_ORDER` and the badge texts verbatim.

- [ ] **Step 1: Write the failing node tests** in `tests/js/library.test.mjs`:
  - `matches all terms over title author shuttle id macro`;
  - `shuttle order newest first, unknown last alphabetically`;
  - `paging clamps and resets` (Review Focus 3: `page([], 7)` gives `{items: [], pageNo: 1,
    pages: 1}`; `page(30 items, 9)` gives `pageNo 2`, `pages 2`, and 6 items);
  - `badges match the spec table`: the second fixture entry gives `[{text: "timing: 17.08 MHz
    < 25.175 MHz", cls: "warn"}, {text: "not hardware-validated", cls: "warn"}]`, and the fourth
    includes `{text: "video: barely-moving", cls: "info"}`;
  - `assetUrl null stays null`.

  Add Python tests:
  - `test_board_html_has_library_section_when_enabled`, and its absence when the setting is
    empty;
  - `test_board_js_library_panel_behaviour` in `test_static.py`, grep-style like
    `test_board_js_has_gallery_and_upload_behaviour`: it asserts `loading = 'lazy'`,
    `/library/`, `/load`, `X-CSRFToken` and `board software too old`.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_library_js.py tests/test_static.py
  tests/test_views.py >> tmp/t6.log 2>&1`. Expected: the new tests fail.
- [ ] **Step 3: Implement.**
  - Write `library.js`.
  - In `board.js`, add a `mountLibrary(designsBody)` called from `render()`:
    - the panel states of the spec's table;
    - 24 cards per page;
    - posters with `loading="lazy" decoding="async" width="160" height="120"`;
    - the Load button posting to `api + '/library/' + encodeURIComponent(id) + '/load'` with
      `X-CSRFToken`.
  - The gallery list hides library entries except the enabled one.
  - Add the CSS classes the spec lists.
  - All text goes in with `textContent`.
- [ ] **Step 4: Run the full suite, ruff, and `node --test tests/js/`.** Expected: all pass.
- [ ] **Step 5: Check by hand in a browser against the Django dev server**, with
  `ttsite.daemon` and `ttsite.library` faked by `tests/fake_library_server.py`, a small
  `manage.py runserver` settings override that serves the fixture.
  - Search `sea`: 1 result.
  - Shuttle filter `tt05`: 1 result.
  - Paging: with the fixture copied to 60 entries (ids suffixed `_1`..`_12`), 3 pages.
  - Save a screenshot to `tmp/t6-panel.png`.
- [ ] **Step 6: Commit** ("ttsite: VGA library panel"), then push the branch.

## Task 7: Commander CSRF header (tt-commander-app)

**Repo:** `~/github/fpgas-online/tt-commander-app`. Branch `csrf-token` off
`origin/fpgas-online`. Spec section 4, CSRF. This is its own small PR (owner question 3).

**Files:**
- Modify: `src/components/EmbedApp.tsx` (`EmbedOptions.csrfToken?: () => string`)
- Modify: `src/model/fpgaDesigns.ts:67-84` and `:129-139` (`daemonJson` gains an `opts: {
  csrfToken?: () => string }` argument; `enableFpgaDesign(apiBase, name, clockHz?, ui_in:
  number | null = null)` always sends `{"clock_hz": clockHz ?? null, "ui_in": ui_in}`)
- Modify: `README.fpgas-online.md` (the options table)
- Test: `src/model/fpgaDesigns.spec.ts`

**Interfaces:**
- Produces:
  - `setCsrfToken(fn: (() => string) | undefined): void` in `fpgaDesigns.ts`, called by
    `EmbedApp` from `options.csrfToken`;
  - every non-GET `daemonJson` request carries `X-CSRFToken: fn()` when `fn` is set.

- [ ] **Step 1: Write the failing tests.**
  - `enable sends X-CSRFToken when a token getter is set`;
  - `GET designs sends no CSRF header`;
  - `enable sends explicit nulls` (the body is `{"clock_hz":null,"ui_in":null}` when no clock
    is given).
- [ ] **Step 2: Run them.** `npx vitest run src/model/fpgaDesigns.spec.ts >> tmp/t7.log
  2>&1`. Expected: they fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all the checks.** `npm run lint && npm run typecheck && npx vitest run >>
  tmp/t7.log 2>&1`. Expected: all pass.
- [ ] **Step 5: Commit** ("embed: send the host page's CSRF token on POST"), then push.

The `csrfToken: csrf` line in the site's `board.js` `mountCommander` options goes into Task 6's
branch as one extra commit made by this task's implementer (`board.js:108-116`). Unknown
options are ignored by the 0.2.0 bundle, so this is safe before the bump.

## Task 8: Commander library source (tt-commander-app)

**Repo:** tt-commander-app. Branch `library-source` off `csrf-token` (stacked). Spec section 4.

**Files:**
- Create: `src/model/fpgaLibrary.ts`, `src/model/fpgaLibrary.spec.ts`
- Modify: `src/model/fpgaDesigns.ts` (the `FpgaDesign` type, and the merge after
  `loadFpgaDesigns`)
- Modify: `src/model/shuttle.ts:7-21` (`Project.shuttle?: string`, `Project.source?: 'demo' |
  'upload' | 'library'`)
- Modify: `src/components/ProjectSelect.tsx:83-90`
- Modify: `src/components/BoardConfigPanel.tsx:58-90`, `:190-230`
- Copy: Task 1's fixture to `src/model/testing/fpga-library.json`
- Modify: `README.fpgas-online.md`
- Test: `src/model/fpgaLibrary.spec.ts`, `src/components/BoardConfigPanel.spec.tsx`

**Interfaces:**
- Consumes: Task 5's routes, Task 7's `setCsrfToken` and `daemonJson`, and Task 6's
  `SHUTTLE_ORDER` and badge texts (copied, not imported).
- Produces:
  - `LibraryEntry`, the site's entry type;
  - `loadFpgaLibrary(apiBase: string): Promise<void>`, which fills `fpgaLibrary.byId`;
  - `loadLibraryDesign(apiBase: string, id: string): Promise<{enabled: string; clock_hz:
    number | null; ui_in: number | null; ui_in_held: number[]; pushed: boolean}>`;
  - `libraryWarnings(e: LibraryEntry): {text: string; cls: 'warn' | 'info'}[]`;
  - `PROJECT_LIMIT = 100`.

- [ ] **Step 1: Write the failing tests.**
  - `library not loaded when designs lack the library key`;
  - `library entries follow board designs, sorted by shuttle order then title`;
  - `entries already on the board are not duplicated`;
  - `loadLibraryDesign posts {} with X-CSRFToken to /library/<id>/load`;
  - `warnings match the site table` (the same two cases as Task 6);
  - `enabled id missing from list does not throw` (Review Focus 4);
  - in `BoardConfigPanel.spec.tsx`:
    - `timing-fail library project shows warning icon and Alert, Load enabled`;
    - `Load on a library project calls the site load route`;
    - `ui_in shown after load`;
    - `search matches shuttle and macro`;
    - `options capped at 100 with a narrow-down line`.
- [ ] **Step 2: Run them and record that they fail** (`tmp/t8.log`).
- [ ] **Step 3: Implement.** Map the warnings onto `danger_level: 'medium'` and
  `danger_reason` joined with `; `. Never set `'high'`.
- [ ] **Step 4: Run lint, typecheck, vitest, `npm run build:embed`.** Expected: all pass, and
  `dist/embed/tt-commander-embed.js` is built.
- [ ] **Step 5: Commit** ("fpga: VGA library as a third design source"), then push.

## Task 9: The mirror leaves the harness's files alone (tinytapeout-vga-videos)

**Repo:** tinytapeout-vga-videos. Branch `fpga-library-foreign` off `fpga-library-schema`
(stacked on Task 1). Spec section 5.

**Files:**
- Modify: `ttvga/remote.py:283-316` (`mirror`)
- Modify: `docs/publishing.md` (a new section, "Files the FPGA harness owns")
- Test: `tests/test_mirror.py`

**Interfaces:**
- Consumes: `ttvga.fpgalibrary.FOREIGN`.
- Produces: `remote.mirror_script(src: str, dest: str, dry_run: bool) -> str`, extracted from
  `mirror` so the script can be tested without ssh.

- [ ] **Step 1: Write the failing tests.**
  - `test_mirror_excludes_foreign_and_never_deletes`: the script contains `--exclude
    '/*/*/*.bin'` and `--exclude /fpga-library.json` (as `shlex.quote` renders them), and no
    `--delete`.
  - `test_mirror_summary_counts_bitstreams`: the script contains `bitstreams:` and
    `fpga-library.json:`.
  - `test_foreign_is_the_one_list`: the excludes are built from `fpgalibrary.FOREIGN`.
- [ ] **Step 2: Run them and record that they fail** (`tmp/t9.log`).
- [ ] **Step 3: Implement.** In the docs, name the files, their owner (the tt-harness-fpga-vga
  session), the spec path, and the rule that no tool here replaces an archive directory
  wholesale.
- [ ] **Step 4: Run `uv run pytest`.** Expected: all pass.
- [ ] **Step 5: Commit** ("mirror: never overwrite the FPGA harness's files"), then push.
  Tell the controller that the untracked raw-traces plan in `.worktrees/pipeline-plan` (lines
  387-389) assumes `<shuttle>/<macro>/fpga/`, and must switch to `fpgalibrary.FOREIGN`. Do not
  edit that worktree.

## Task 10: Harness publisher, an interface contract (tt-harness-fpga-vga session)

**Executed by the tt-harness-fpga-vga session, not by this plan's controller.** The controller
sends the session this task and the spec, and waits for its branch. This task fixes only what
must come out (spec section 6). The session chooses its own files and tests.

**Contract:**
- The command is `tthfv publish --archive <dir>`. The path is never recorded in the repo.
- The id is `library_id` exactly as in the Global Constraints. It replaces `demo_name` on the
  `demos-export` branch (33 + 6 characters, `tt_um_` kept). The test vectors are the four rows
  of spec section 1, plus `ttsky25a/tt_um_rebeccargb_vga_timing_experiments` giving
  `ttsky25a_rebeccargb_vga_timing__4638a050`.
- The uniqueness checks are spec section 1's list, using the demo names from
  tinytapeout-fpga-demos at a commit recorded in the output's log.
- The output is schema 1 exactly. `title` carries no warning text.
- Write order: every bin, skipping existing names; then `fpga-library.json.tmp`; then
  `tt-vga fpga-library-check <tmp> --bins <archive>` (Task 1's CLI, run as a program), which
  must exit 0; then `rename`.
- Old bins are never deleted. Files are mode 0644 and directories 0755.
- Done when the session's branch is pushed, and its test run plus the check's exit code 0 on a
  dry run into a local directory are reported.
- Nothing is written to `/srv/data.wafer.space` until Tim has approved the format (owner
  question 2).

- [ ] **Step 1: Send the contract** to the tt-harness-fpga-vga session, with the spec path and
  the branch.
- [ ] **Step 2: Receive the session's pushed branch and its dry-run log.** Run `tt-vga
  fpga-library-check` on the dry-run output yourself and record the exit code in
  `tmp/t10.log`.

## Task 11: Hardware check on one FabricFox board

**When:** after Tim has deployed the daemon (Pi play), the site, and the Commander 0.3.0 pin,
and after the harness has published (spec section 8, steps 1 to 5). It is read-only apart from
the loads, and follows the spec's section 9, Hardware check.

**Files:**
- Create: `tmp/t11-hardware.log` in this worktree (not committed).
- Create: a claim at `~/github/TinyTapeout/tmp/board-claims/<board>-p<port>.json`.

- [ ] **Step 1: Claim the board.** Choose it as in owner question 4. Confirm it by USB serial,
  and check that `status.json` shows `clients == 0` and an idle display state of `loaded`.
  Write the claim (UTC times, expiry 30 min).
- [ ] **Step 2: Read-only checks.**
  - `curl -s https://tinytapeout.fpgas.online/api/board/<slug>/designs >>
    tmp/t11-hardware.log 2>&1`: the top-level `library` key is there. Record the upload names.
  - `curl -s .../library`: the count is about 445, and `ttsky25a_vga_example` is present.
- [ ] **Step 3: Load `ttsky25a_vga_example` from the board page** in a browser (Playwright),
  using the panel.
  - The response has `pushed: true`, then `/designs` shows `enabled == "ttsky25a_vga_example"`
    with `source: "library"`.
  - Take a camera screenshot to `tmp/t11-pattern.png`.
- [ ] **Step 4: Press Load again.** `pushed: false`.
- [ ] **Step 5: Load a library entry with `ui_in` not null through the Commander.** The Alert
  shows the inputs, and `ui_in_held == []`. Note from the site's nginx access log on tweed
  whether 0.2.0 Commander POSTs had answered 403. Read it only; do not reproduce.
- [ ] **Step 6: Restore.** Run vgacap's `tools/board_restart.py <ws link>`, wait for the idle
  display to read `loaded` (about 75 s), and check that the upload names equal Step 2's. Delete
  the claim. Abort at once and restore if `clients` goes above 0 at any point.
- [ ] **Step 7: Report** the log and the screenshots to the controller. The total time on the
  board is under 10 minutes.
