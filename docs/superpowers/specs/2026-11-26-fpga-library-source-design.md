# The VGA library: a third design source on the FabricFox boards

Status: draft for the owner, 2026-11-26. Not yet reviewed.

Owner decision (Tim, 2026-11-26): "Our custom commander app and the tinytapeout.fpgas.online
interface should be updated to allow loading of the bitstreams from the same archive the vga
images are published too as another alternative to the demos in the fpgas-online repo and
uploading your own bitstream."

Controller ruling (Ruling Y, same day, binding here): the library is a real third source
`library` in the [fpgas-tt daemon](https://github.com/fpgas-online/fpgas.online-tt), with its own
cache directory on each Pi, filled by the [site](https://github.com/fpgas-online/fpgas.online-site)
backend on tweed. The site fetches the index and the bitstreams from one fixed archive URL,
checks them, and pushes the bytes to the daemon. The Pis make no outbound connections. Option A
(the site loads library designs as ordinary uploads) was rejected: it would evict other
visitors' uploads, and the 16-slot upload store on fpga-4 is already full.

## Why

[tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) builds iCE40UP5K bitstreams
of the Tiny Tapeout VGA designs for the FabricFox boards (fpga-1 to fpga-4). There are about 445
of them, each 104,090 bytes. Today a board can load two kinds of design. One is the five
packaged demos from [tinytapeout-fpga-demos](https://github.com/fpgas-online/tinytapeout-fpga-demos),
installed into the Pi NFS root as a deb. The other is a visitor upload; the Pi keeps at most 16
and evicts the oldest. Neither route can carry 445 designs:

- A deb that big would bloat [the APT repo](https://github.com/fpgas-online/apt), which keeps
  every version in git.
- The upload store holds 16 entries, shared by every visitor.

The archive already publishes a poster, a preview and clips for each design at
<https://data.wafer.space/big-storage/tinytapeout-vga-videos/>. The bitstreams go into that
archive too, and both UIs can pick from it.

## What changes, per repository

| Repository | Change |
|---|---|
| [tinytapeout-vga-videos](https://github.com/mithro/tinytapeout-vga-videos) (this repo, archive owner) | the schema of `fpga-library.json`, a fixture, a reference validator `tt-vga fpga-library-check`, and a mirror that leaves the harness's files alone |
| [tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) | `tthfv publish` writes the `.bin` files and `fpga-library.json` into the archive (interface contract below) |
| [fpgas.online-tt](https://github.com/fpgas-online/fpgas.online-tt) (daemon) | library cache, `GET /library`, `POST /library/{id}`, library entries in `/designs`, `ui_in` on enable |
| [fpgas.online-site](https://github.com/fpgas-online/fpgas.online-site) (`ttsite`) | index proxy, load route, the VGA library panel in `board.js` |
| [tt-commander-app](https://github.com/fpgas-online/tt-commander-app) (fpgas-online fork, branch `fpgas-online`) | source `library`, search by shuttle and id, warnings, `ui_in`, CSRF header |
| [fpgas.online-infra](https://github.com/fpgas-online/fpgas.online-infra) | no code change; Tim re-runs the Pi play and the site play, and bumps the Commander pin |

The TinyTapeout checkout of tt-commander-app (`~/github/TinyTapeout/tt-commander-app`) is the
upstream app. It has no FPGA support and is not touched.

Checkouts read for this spec (all clean, all level with their remotes):

| Repository | HEAD |
|---|---|
| fpgas.online-tt | `6834ce9` |
| fpgas.online-site | `b8ce772` |
| tt-commander-app (`fpgas-online`) | `df74e3c` |
| fpgas.online-infra | `cc8b0e65` |
| tt-harness-fpga-vga | `112ff4b` |
| tinytapeout-vga-videos | `46b4a6e` |

## How a load works

1. The page loads, and the board page fetches `GET /api/board/<slug>/designs`. On a new daemon
   the response has a top-level `library` object. If it is missing, the board's software is too
   old for the library.
2. The page fetches `GET /api/board/<slug>/library`. The site answers from its cache of
   `fpga-library.json`, which it fetched from the archive and checked entry by entry.
3. The visitor presses Load, and the page sends
   `POST /api/board/<slug>/library/<id>/load`.
4. The site asks the daemon `GET /library`. If the Pi already holds `<id>` with the index's
   `bin_sha256`, the site goes straight to step 6.
5. Otherwise the site fetches `<base><bin>` from the archive. It checks `bin_bytes`, the
   `bin_sha256` and the iCE40 preamble, then sends the bytes and the entry's metadata in
   `POST /library/<id>`. The daemon checks them again and stores them in its library cache. It
   may evict other library entries, never uploads.
6. The site sends `POST /designs/<id>/enable` with `{"clock_hz": <entry clock_hz>, "ui_in":
   <entry ui_in>}`. The daemon loads the design the same way it loads a demo or an upload, then
   sets the clock and `ui_in` in the same REPL step.
7. The page reloads `/designs` and calls the Commander's `refreshDesigns()`.

The Commander follows the same route (steps 2, 3 and 7), so there is only one way to load a
library design.

## 1. `fpga-library.json`, schema 1

### Where

- Index: `<archive>/fpga-library.json`, beside the videos' `index.json`. Publicly at
  `https://data.wafer.space/big-storage/tinytapeout-vga-videos/fpga-library.json`.
- Bitstreams: `<archive>/<shuttle>/<macro>/<id>-<sha256[:12]>.bin`, in the design's existing
  video directory. Each name contains part of the file's hash, so a file never changes once it
  is written. A rebuild gets a new name, and old files stay, so a page holding an older index
  still loads what it lists.
- `<archive>` is `/srv/data.wafer.space/tinytapeout-vga-videos` on big-storage. It is a symlink
  into `/backups` and is rsynced to data.wafer.space every five minutes.
- Only the tt-harness-fpga-vga session writes these files, and only after Tim has seen the
  format. No other session writes there.

### The document

```json
{
  "schema": 1,
  "generated": "2026-11-26T03:00:00Z",
  "tthfv_commit": "0123456789abcdef0123456789abcdef01234567",
  "videos_repo_commit": "89abcdef0123456789abcdef0123456789abcdef",
  "designs": [
    {
      "id": "ttsky25a_vga_example",
      "shuttle": "ttsky25a",
      "macro": "tt_um_vga_example",
      "title": "VGA Example",
      "author": "Uri Shaked",
      "description": "",
      "docs_url": "https://tinytapeout.com/chips/ttsky25a/tt_um_vga_example",
      "repo_url": "https://github.com/TinyTapeout/vga-playground-template",
      "commit": "0123456789abcdef0123456789abcdef01234567",
      "clock_hz": 25175000,
      "pinout": {
        "ui_in": ["", "", "", "", "", "", "", ""],
        "uo_out": ["R1", "G1", "B1", "VSync", "R0", "G0", "B0", "HSync"],
        "uio": ["", "", "", "", "", "", "", ""]
      },
      "ui_in": null,
      "bin": "ttsky25a/tt_um_vga_example/ttsky25a_vga_example-0123456789ab.bin",
      "bin_bytes": 104090,
      "bin_sha256": "0123456789ab0123456789abcdef0123456789abcdef0123456789abcdef0123",
      "build_status": "ok",
      "fmax_mhz": 31.42,
      "validation": "none",
      "verdict": "ok",
      "qspi": "none",
      "poster": "ttsky25a/tt_um_vga_example/ttsky25a_tt_um_vga_example_poster.png",
      "preview_gif": "ttsky25a/tt_um_vga_example/ttsky25a_tt_um_vga_example_preview.gif",
      "video_10s_webm": "ttsky25a/tt_um_vga_example/ttsky25a_tt_um_vga_example_10s.webm"
    }
  ]
}
```

### Top-level keys

Every key is required.

| Key | Type | Rule |
|---|---|---|
| `schema` | int | `1` |
| `generated` | string | UTC, `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` |
| `tthfv_commit` | string | `^[0-9a-f]{40}$` |
| `videos_repo_commit` | string | `^[0-9a-f]{40}$`, the tinytapeout-vga-videos commit whose results were used |
| `designs` | array of objects | 0 to 2000 entries, sorted by `id` |

### Entry keys

Every key is required, and keys typed "or null" are still present. Readers must ignore unknown
keys. A breaking change bumps `schema`.

| Key | Type | Rule |
|---|---|---|
| `id` | string | the daemon's design name; the id rule below |
| `shuttle` | string | `^[a-z0-9]{1,16}$` |
| `macro` | string | `^tt_um_[A-Za-z0-9_]{1,58}$` (original case) |
| `title` | string | 1 to 200 characters, no warning text in it |
| `author` | string | 0 to 200 characters |
| `description` | string | 0 to 2000 characters |
| `docs_url` | string | empty, or `https://` and at most 500 characters |
| `repo_url` | string | empty, or `https://` and at most 500 characters |
| `commit` | string | `^[0-9a-f]{40}$`, the project commit that was built |
| `clock_hz` | int | 1 to 200000000 (the harness writes 25175000 where the project says 0) |
| `pinout` | object | keys `ui_in`, `uo_out`, `uio`; each an array of exactly 8 strings of at most 64 characters |
| `ui_in` | int or null | 0 to 255: the value the board drives on `ui_in` after loading; null means drive nothing |
| `bin` | string | exactly `<shuttle>/<macro>/<id>-<bin_sha256[:12]>.bin` |
| `bin_bytes` | int | 1 to 262144 |
| `bin_sha256` | string | `^[0-9a-f]{64}$` |
| `build_status` | string | `ok` or `timing-fail` |
| `fmax_mhz` | number | above 0: nextpnr's achieved frequency |
| `validation` | string | `none`, `mcu` or `full-speed` (harness spec, Validate) |
| `verdict` | string | `^[a-z-]{1,32}$`, the videos pipeline's render verdict (`ok`, `barely-moving`, `static`, ...) |
| `qspi` | string | `none` or `emulated` |
| `poster` | string or null | relative path, the archive path rule below |
| `preview_gif` | string or null | relative path, the same rule |
| `video_10s_webm` | string or null | relative path, the same rule |

Archive path rule, for `bin`, `poster`, `preview_gif` and `video_10s_webm`: the path must match
`^[a-z0-9]{1,16}/tt_um_[A-Za-z0-9_]{1,58}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`. Its first two
segments must equal the entry's `shuttle` and `macro`. It must contain no `..`, no `//` and no
`%`. A reader joins it onto the one fixed base URL and never accepts an absolute URL.

Changes from the draft in the research notes, section 11:

| Draft | v1 | Why |
|---|---|---|
| `count` | removed | duplicates `len(designs)` |
| `source_id` | removed | duplicates `shuttle` + `/` + `macro` |
| `status` (`ok`, `timing-fail`, `no-validation`) | `build_status` (`ok`, `timing-fail`) | "not validated" was already in `validation` |
| `warnings` (free text) | removed | readers derive warnings from facts in the entry (the warnings table below); one representation each |
| paths optional | always present, string or null | one shape for every entry |

### The id rule

The id is the design's name on the Pi, and the name the SDK reports as enabled. The exporter
computes it like this:

1. Take `lower(<shuttle> + "_" + <macro with the leading "tt_um_" removed>)`.
2. Map every character outside `[a-z0-9_]` to `_`.
3. If the result is longer than 40 characters, keep its first 31 characters, add `_`, then add
   the first 8 hex digits (lowercase) of the SHA-256 of the UTF-8 string `<shuttle>/<macro>`.
   That string keeps the macro's original case and its `tt_um_` prefix. The result is exactly
   40 characters.

Every macro starts with `tt_um_`. If one does not, the exporter fails; it does not guess. The
result always matches `^[a-z0-9_]{1,40}$`, the daemon's `NAME_RE`
(`fpgas.online-tt src/fpgas_tt/designs.py:41`).

The harness session ran this rule over all 445 designs it builds. It produced 445 distinct ids,
and 10 were cut and hashed. Over the 440 projects in this repo's `data/targets.json`, it also
gives 440 distinct ids with 10 hashed. Examples:

| shuttle/macro | id |
|---|---|
| `tt05/tt_um_flappy_vga_cutout1` | `tt05_flappy_vga_cutout1` |
| `ttsky25a/tt_um_vga_example` | `ttsky25a_vga_example` |
| `ttihp25a/tt_um_yuri_panchul_sea_battle_vga_game` | `ttihp25a_yuri_panchul_sea_battl_09a2562b` |
| `ttsky25a/tt_um_rebeccargb_vga_timing_experiments` | `ttsky25a_rebeccargb_vga_timing__4638a050` |

The exporter checks uniqueness before it writes anything, and fails the whole run on any of
these:

- two ids that are equal;
- two ids that are equal after case-folding (this cannot happen with lowercase ids; the check
  stays as a guard);
- an id equal to the name of a packaged demo. A demo's name is the `top_module` in its
  tinytapeout-fpga-demos `demos/<name>/info.yaml` (tools/build.py:31). Today they are
  `tt_um_counter_7seg`, `tt_um_factory_test`, `tt_um_pwm_breathe`, `tt_um_uart_hello` and
  `tt_um_vga_pattern`;
- an id equal to `idle_display`, the daemon's `IDLE_NAME`.

The daemon refuses the same collisions on push (section 2).

Ids begin with a shuttle id such as `tt05_` or `ttsky25a_`. Demo names begin with `tt_um_`. A
collision between them is therefore not possible today; the checks stay because names on a Pi
are global.

### Warnings, derived by readers

Both UIs (board.js and the Commander) compute the same badges from the entry. Neither ever
disables Load because of a warning: Tim said on 2026-11-24 that timing-fail designs are listed
with a visible warning.

| Condition | Badge text | Class |
|---|---|---|
| `build_status == "timing-fail"` | `timing: <fmax_mhz> MHz < <clock_hz / 1e6> MHz` (fmax two decimals, clock three: `timing: 17.08 MHz < 25.175 MHz`) | warn |
| `validation == "none"` | `not hardware-validated` | warn |
| `validation == "mcu"` | `validated at MCU speed only` | info |
| `qspi == "emulated"` | `QSPI emulated` | info |
| `verdict != "ok"` | `video: <verdict>` | info |

The first pass has no hardware validation (harness README, Status), so every entry shows
`not hardware-validated` until the harness publishes `mcu` or `full-speed`.

### Reference validator and fixture (this repo)

- `ttvga/fpgalibrary.py` holds `validate(doc) -> list[str]`, which lists every violation of the
  rules above, `load(path)`, and the id rule as `library_id(shuttle, macro)`.
- `tt-vga fpga-library-check <file> [--bins <dir>]` exits 1 on any violation. With `--bins` it
  also reads each `bin` under `<dir>` and checks the size, hash and preamble. The harness
  session runs it as a program before publishing. It is not imported, so the repos keep no code
  dependency on each other.
- The fixture is `tests/fixtures/fpga-library/fpga-library.json`, with one `.bin` per entry
  under the same layout. It has five entries:
  - `ok`, `ui_in: null`;
  - `timing-fail`;
  - one hashed 40-character id;
  - `ui_in: 5`;
  - one entry whose `poster`, `preview_gif` and `video_10s_webm` are all null.

  The fixture bins are 4,096 bytes each: `ff 00 00 ff`, then `7e aa 99 7e`, then zeros. Their
  real hashes are recorded. Other repos copy the fixture into their own tests. The copy carries
  a header line naming the source commit; copying instead of depending keeps the repos separate
  (see the memory note on cross-project dependencies).

## 2. Daemon (fpgas.online-tt)

### Store

| Item | Value |
|---|---|
| Directory | `--library-dir`, default `/var/lib/fpgas-tt/library` (inside the unit's existing `StateDirectory=fpgas-tt`; no packaging change) |
| Files per entry | `<id>.bin` (the bytes) and `<id>.json` (the stored metadata, below); an entry exists only when both do |
| Cap | `--library-max-bytes`, default 16 MiB: total size of the `.bin` files, about 160 designs at 104,090 bytes |
| Eviction | least recently used, by the mtime of `<id>.json`; a push or an enable of the entry refreshes it with `os.utime` |
| Never touches | `--uploads-dir` (its 16-slot store and its eviction are unchanged), the demos, the idle design |
| Writes | `.bin` first and `.json` second, each to a temp file and then `os.replace`; a reader that sees `.json` sees the whole `.bin` |
| Lock | a new `_LIBRARY_LOCK` (a `threading.Lock`, like `_STORE_LOCK`) covers write and evict; uploads keep `_STORE_LOCK` |
| Lifetime | the Pi root is an overlay on tmpfs, so the cache is in RAM and is lost at reboot; the site pushes again when needed |

The 16 MiB cap is a RAM budget: under the tmpfs overlay these files live in the Pi's memory. It
is a command-line flag, so infra can change it without a release.

Stored metadata (`<id>.json`) is the pushed entry, reduced to the keys the daemon reports:
`id`, `shuttle`, `macro`, `title`, `author`, `description`, `docs_url`, `repo_url`, `commit`,
`clock_hz`, `pinout`, `ui_in`, `bin_sha256`, `bin_bytes`, `build_status`, `fmax_mhz`,
`validation`, `verdict`, `qspi`, `poster`, `preview_gif`. Each value is checked against the
schema 1 rules above before anything is written.

### Name precedence

Names on a Pi are global. A name resolves to a demo first, then a library entry, then an upload
(`design_file`, designs.py:155). The other rules follow from that:

- `POST /bitstream` refuses with 409 a name that is a cached library id ("`<id>` is a VGA
  library design; pick another").
- `POST /library/{id}` refuses with 409 a demo name or `idle_display`.
- An upload that already has the name of a later-cached library id stays on disk, hidden, just
  as a demo hides an upload today.

### `GET /designs` (changed)

The response gains a top-level `library` key, and new entries with `source: "library"`:

```json
{
  "enabled": "ttsky25a_vga_example",
  "library": {"max_bytes": 16777216, "used_bytes": 208180},
  "designs": [
    {"name": "tt_um_vga_pattern", "title": "...", "source": "demo", "library": null},
    {"name": "my_upload", "title": "", "source": "upload", "library": null},
    {"name": "ttsky25a_vga_example", "title": "VGA Example", "author": "Uri Shaked",
     "description": "", "docs_url": "https://...", "repo_url": "https://...",
     "clock_hz": 25175000, "pinout": {"ui_in": ["..."], "uo_out": ["..."], "uio": ["..."]},
     "source": "library",
     "library": {"shuttle": "ttsky25a", "macro": "tt_um_vga_example", "commit": "...",
                 "ui_in": null, "bin_sha256": "...", "build_status": "ok", "fmax_mhz": 31.42,
                 "validation": "none", "verdict": "ok", "qspi": "none",
                 "poster": "ttsky25a/tt_um_vga_example/ttsky25a_tt_um_vga_example_poster.png",
                 "preview_gif": "ttsky25a/tt_um_vga_example/ttsky25a_tt_um_vga_example_preview.gif"}}
  ]
}
```

- The top-level `library` key shows that this daemon supports the library. An old daemon does
  not send it, and that is how the site and the Commander detect one.
- Every design carries `library`: null for demos and uploads, an object for library entries.
- Only cached entries are listed. The full catalogue is the site's index (section 3).
- The listing reads each `<id>.json` (about 1 KB each, at most about 160). It never hashes a
  `.bin`.

### `GET /library` (new)

```json
{"max_bytes": 16777216, "used_bytes": 208180,
 "entries": [{"id": "ttsky25a_vga_example", "bin_sha256": "...", "bin_bytes": 104090,
              "used_at": "2026-11-26T04:10:00Z"}]}
```

- It answers on FPGA boards only, with the same 404/503 rules as `/designs` (`_fpga_only`).
- It does not touch the REPL and does not wait for `taken`, so it is fast even while a load is
  running.

### `POST /library/{id}` (new)

The request is multipart with two parts:

- `meta`: a JSON object, at most 32 KiB, holding one schema-1 entry;
- `file`: the bytes, at most 256 KiB.

Reading reuses `bitstream_upload`'s bounded part reader, with a running total of at most
`MULTIPART_MAX_BYTES`.

Checks, in order. The first failure answers:

| Check | Status | Error |
|---|---|---|
| `{id}` matches `NAME_RE` | 404 | `no such design` |
| body is multipart with both parts | 400 | `multipart form with parts 'meta' and 'file' required` |
| total above `MULTIPART_MAX_BYTES` | 413 | `request body too large (limit ...)` |
| `meta` is JSON, an object, and passes the schema-1 entry rules | 400 | `meta: <first violation>` |
| `meta.id == {id}` | 400 | `meta.id does not match the URL` |
| `{id}` is a demo name / `idle_display` | 409 | as `validate_bitstream` |
| `len(file) == meta.bin_bytes` | 400 | `bitstream is <n> bytes, meta says <m>` |
| `sha256(file) == meta.bin_sha256` | 400 | `bitstream does not match bin_sha256` |
| size and preamble (`validate_bitstream`) | 400 | as today |

Results:

- An entry with the same `bin_sha256` is already stored: `200 {"id", "bin_bytes",
  "bin_sha256", "evicted": []}`. The metadata is rewritten and the LRU time refreshed, so a
  repeated push is cheap and idempotent.
- Otherwise the entry is stored, replacing any older build of the same id, and older entries
  are evicted until the total fits: `201` with the same body, `evicted` listing the ids removed.
- An `OSError` while storing: 500 `the library entry could not be kept on the Pi`.

A push counts as activity (`activity.touch()`), as an upload does, so the idle display does not
take the board in between push and enable. It does not touch the board.

### `POST /designs/{name}/enable` (changed)

- The body is `{"clock_hz": int | null, "ui_in": int | null}`. Both keys are optional, and a
  missing key means null. `ui_in` is checked like `clock_hz` (server.py:197-201): not a bool,
  an int from 0 to 255, else 400 `ui_in must be an integer between 0 and 255`.
- The caller always supplies the values. The daemon never fills them in from stored metadata,
  so a value has only one source: the caller reads the entry's `clock_hz` and `ui_in` and sends
  them, as the gallery already does for a demo's `clock_hz`.
- `ui_in` applies to every source (demo, upload, library).
- The response is `{"enabled": name, "clock_hz": int | null, "ui_in": int | null, "ui_in_held":
  [int, ...]}`. `ui_in_held` lists the pins left undriven because something outside held them
  high. It is empty when `ui_in` is null.

`ui_in` is applied in the same REPL step as the load (`LOAD_CODE`, designs.py:225-272). A
`__UI_IN__` placeholder goes after `__CLOCK__`, inside the success path only:

1. Set `tt.mode = RPMode.ASIC_RP_CONTROL`, so the RP2350 drives `ui_in`. The Commander's
   `enable_ui_in(True)` does the same (`tt-commander-app src/ttcontrol/ttcontrol.py:40-50`).
2. Set `tt.ui_in.value = 0`, so that any pin made an output starts low.
3. Run the contention guard that `safe.py` already uses on chip boards (safe.py:84-95). Each
   `tt.pins.ui_in<i>` becomes `Pin.IN` with `Pin.PULL_DOWN`. After 5 ms, a pin that reads high is
   recorded as held and left as an input. Every other pin becomes `Pin.OUT`.
4. Set `tt.ui_in.value = <ui_in>`.
5. Print `ui_in_held=<json list>`, then `enabled` as the last line, as today.

The guard's lines move into a shared constant, `designs.UI_IN_GUARD`, used by both `safe.py`
and `LOAD_CODE`, so both have one copy. With `ui_in` null, nothing is added to `LOAD_CODE`, so
demos and uploads load exactly as they do today.

The load path itself does not change. A library design is read from `<id>.bin` and goes
through `enable_design` and then `load_design`. That is the same buffer, the same SHA-256
check on the board and the same SDK loader as an upload. The 25 s deadline
(`ENABLE_OVERALL_TIMEOUT`) still applies.

### Concurrency

| Case | Behaviour |
|---|---|
| Two pushes at once | `_LIBRARY_LOCK` puts them in order; neither can evict the file the other is writing |
| A push during an upload | separate locks and directories; neither evicts the other's store |
| A push during a load | the push only writes files; the load has already read its bytes (`_read_design` runs before the REPL) |
| An entry evicted between push and enable | the enable answers 404 `no such design`; the site pushes once more (section 3) |
| An enable while the REPL is busy | unchanged: 409 `another task is running` |

### Docs and invariants

- Update the README route table and `CLAUDE.md`.
- `CLAUDE.md`'s invariant "nothing is fetched or generated after boot" still holds: the Pi
  fetches nothing. The library arrives only by push from the site, and only over the per-port
  VLAN from the gateway that already carries `/bitstream`.

## 3. Site (fpgas.online-site, `ttsite`)

### Setting

`TTSITE_LIBRARY_BASE_URL = "https://data.wafer.space/big-storage/tinytapeout-vga-videos/"` goes
in `pib/settings.py`, next to `TTSITE_COMMANDER_VERSION`. The rules:

- The URL ends in `/`.
- Empty turns the library off: the panel is not rendered, and the routes answer 404.
- No request can change it. Infra needs no change while this default holds.

### `ttsite/library.py` (new)

The archive client and the checks:

- `fetch_index()` sends `requests.get(BASE + "fpga-library.json", allow_redirects=False,
  timeout=(3.05, 10), stream=True)`. It sends `If-None-Match` with the archive ETag it last saw,
  and reads at most 4 MiB.
  - Any 3xx: error `archive redirected; refusing`.
  - 304: keep the cached copy.
  - Anything other than 200 or 304: an error.
- `normalise(doc) -> (index, dropped)` applies the schema-1 rules:
  - A document whose top level is wrong (not an object, `schema != 1`, `designs` not an array or
    longer than 2000) is rejected whole.
  - An entry that breaks a rule is dropped and logged, the same way `load_demo_index` treats bad
    demo names (designs.py:93-95).
  - Every entry that shares an id with another is dropped.
  - The output is the site's own wire format: `{"schema": 1, "generated", "base_url": BASE,
    "designs": [...]}`, with each entry's keys in schema order. The site adds `base_url`, so the
    page builds poster URLs without a second setting.
- `fetch_bin(entry) -> bytes`: `requests.get(BASE + entry["bin"], allow_redirects=False,
  timeout=(3.05, 10), stream=True)`. It reads at most 262,145 bytes, then checks, in order:
  status 200, length equal to `bin_bytes`, sha256 equal to `bin_sha256`, and the preamble in
  the first 68 bytes.
  - 404: `archive file missing (the archive may still be syncing; try again in a few minutes)`.
  - Any other failure: `archive file does not match the index` or `archive unreachable`.
- SSRF guard:
  - The base is fixed.
  - The path comes only from a normalised entry, so it has already passed the archive path rule.
  - The final URL's scheme and host must equal the base's.
  - Redirects are refused.
  - Each read is bounded by the timeouts above.
  - No user input reaches a URL. The id in the route is only looked up in the normalised index.

### Caching

- The normalised index lives in the `default` cache (locmem, per gunicorn worker) under
  `ttsite:library:index`. The value is `(archive_etag, body_bytes, site_etag, fetched_at)`.
- `site_etag` is `"sha256:<first 16 hex of sha256(body_bytes)>"`.
- The copy is fresh for 300 s. After that the next request refetches, conditionally.
- If the archive fails, the last good copy is served for up to 24 h, with response header
  `X-TTSite-Library-Stale: <age seconds>`. After that the route answers 502 `VGA library
  unavailable`.

### Routes

| Route | Method | Answer |
|---|---|---|
| `api/board/<slug>/library` | GET | the normalised index |
| `api/board/<slug>/library/<str:id>/load` | POST | load one design onto the board |

`GET api/board/<slug>/library`:

- The board check is `_fpga_board_or_error` (views.py:117), cached 60 s per slug, so a poll does
  not cost the fleet tables each time.
- It is gzipped (`django.views.decorators.gzip.gzip_page`); about 0.4 MB becomes about 60 KB.
- It sends `ETag: <site_etag>` and `Cache-Control: private, max-age=60`, and answers 304 on a
  matching `If-None-Match`.
- The index is the same for every board. The URL sits under the board because the Commander
  only knows `apiBase`.

`POST api/board/<slug>/library/<str:id>/load`:

- Body `{}`. The clock and `ui_in` come from the index, not from the client, so there is one
  source for them.
- Django's `CsrfViewMiddleware` applies (no `csrf_exempt`). The page sends `X-CSRFToken` from
  the `csrftoken` cookie, as `board.js` does for enable (board.js:204).

The load route's steps:

1. Board check (`_fpga_board_or_error`). Then `id` must match `^[a-z0-9_]{1,40}$` and be in the
   index, else 404 `no such library design`.
2. Per-board lock: `cache.add("ttsite:library:loading:<slug>", 1, 60)`. If the key is already
   there, answer 409 `a library load is already running on this board`. The key is deleted in
   `finally`.
3. `daemon.library_state(board)` (`GET /library`).
   - Transport failure: 502, as `_pass_through` does.
   - A 404 whose body is not JSON (aiohttp's default for an unknown route) means an old daemon:
     answer 501 `{"error": "board software too old", "detail": "this board's fpgas-tt daemon
     has no VGA library support yet"}`.
4. If the state lists `id` with the index's `bin_sha256`, skip to step 6.
5. `fetch_bin`, then `daemon.library_push(board, id, entry, data)` (multipart `meta` and
   `file`, timeout `(3.05, 15)`). A daemon error passes through.
6. `daemon.enable(board, id, json.dumps({"clock_hz": entry["clock_hz"], "ui_in":
   entry["ui_in"]}))`. If it answers 404 and step 5 did not run, push once more and enable
   again.
7. On success, delete `ttsite:designs:<slug>` and answer the daemon's enable body plus
   `"pushed": bool`.

Time budget: 3.05 s connect plus 10 s archive read plus 15 s push plus 30 s enable is under
nginx's default 60 s `proxy_read_timeout`. The retry in step 6 runs only when less than 20 s
have gone.

New `daemon.py` functions follow the existing `_pass_through` style: `library_state(board)` and
`library_push(board, name, meta, data)`.

### The VGA library panel (board.js, board.html)

Where it goes:

- `board.html` gets `<section class="tt-library" id="tt-library">` between the gallery list and
  "Upload your own bitstream", only when `board.has_gallery` and the setting is not empty.
- The gallery ("Designs on this board") keeps demos and uploads. It shows a library entry only
  while that entry is enabled, so it never grows to 160 cards.

Its states, in order:

| State | Shown |
|---|---|
| `/designs` has no top-level `library` | "This board's software is too old for the VGA library." No list, no fetch of the index |
| index loading | "Loading the VGA library..." |
| index error | the error text and a Retry button |
| index empty or 404 at the archive | "The VGA library is not published yet." |
| ready | the controls and one page of cards |

The controls:

- Search box: matches if every whitespace-separated term is a case-insensitive substring of any
  of `title`, `author`, `shuttle`, `id`, `macro`.
- Shuttle `<select>`: "All shuttles" plus each shuttle in the index, in order of first
  appearance in a fixed list kept in `library.js` (newest first), with unknown shuttles last,
  alphabetically.
- A count, for example "123 of 445 designs".

Paging: 24 cards per page, with Previous / Next and "page i of n". Only the current page's
cards are in the DOM. A new search or filter goes back to page 1.

A card shows:

- the poster, as `<img loading="lazy" decoding="async" width="160" height="120" alt="">`, from
  `base_url + poster`, or a blank box when `poster` is null;
- the title, then "by author";
- the shuttle and macro, in small type;
- the warning badges (the table in section 1);
- `on this board` when `/designs` lists the id as a library entry;
- `Running` when `enabled == id`;
- a Load button;
- Docs, Source and Video links. Docs and Source go through `safeUrl`. Video is `base_url +
  video_10s_webm` and opens in a new tab.

Load:

- While a load runs, every Run and Load button on the page is disabled.
- The message reads "Loading <title>: fetching from the archive, then programming the FPGA (up
  to a minute)...".
- Success: the message shows `<title> is running`, then `loadDesigns()` and the Commander's
  `refreshDesigns()` run, as `enable()` does today (board.js:209-212).
- Errors go through `errMsg`.

Code layout:

- The pure parts go in a new `static/ttsite/library.js`: matching, shuttle order, paging,
  badges and URL building. It is written as a CommonJS-and-browser module, like `management`'s
  `power-button.js`, so `node --test` can load it (`tests/js/library.test.mjs`, run by
  `tests/test_library_js.py`, the `test_power_button_js.py` pattern).
- `board.js` imports it and keeps the DOM code.
- All text is set with `textContent`.
- CSS goes in `ttsite.css`: `.tt-library`, `.tt-library-grid`, `.tt-badge--library`,
  `.tt-badge--warn`, `.tt-badge--info`. The gallery's badge rule (board.js:154) learns
  `library`.

## 4. Commander (tt-commander-app, branch `fpgas-online`)

- `FpgaDesign` (src/model/fpgaDesigns.ts:9-19): `source: 'demo' | 'upload' | 'library'`, plus
  `library: LibraryFacts | null`, the daemon's per-design `library` object.
- `src/model/fpgaLibrary.ts` (new):
  - `LibraryEntry` is the site's normalised entry.
  - `loadFpgaLibrary(apiBase)` sends `GET ${apiBase}/library` and stores the entries.
  - `loadLibraryDesign(apiBase, id)` sends `POST ${apiBase}/library/${id}/load` with body `{}`.
  - `libraryWarnings(entry)` implements the warnings table.
- The project list:
  - After `loadFpgaDesigns`, if the response has the top-level `library` key, the Commander
    loads the library and appends every entry not already in `byName` as a project.
  - The board's own designs come first, then the library sorted by shuttle (the same fixed
    order as `library.js`, copied) and then by title.
  - `Project` gains optional `shuttle` and `source`. `macro` stays the name or id, so
    `syncSelectionToEnabled` (fpgaDesigns.ts:98-106) keeps working.
  - Without the `library` key, no library entries are shown and nothing else changes.
- Search: `ProjectSelect` (ProjectSelect.tsx:83-90) matches on `['title', 'author', 'shuttle',
  'macro']`. The option list is capped at 100 matches, and a helper line reads "showing 100 of
  445; type to narrow". That keeps the `<For>` render small with about 450 options.
- Load: in `BoardConfigPanel`, a project whose source is `library` loads through
  `loadLibraryDesign`, even when it is already on the board, since the site skips the fetch
  then. Demos and uploads keep `enableFpgaDesign`, which now sends `ui_in: null` explicitly.
- Warnings:
  - A library project with any `warn` badge gets `danger_level: 'medium'` and `danger_reason`
    set to the badges joined with `; `. That reuses the existing warning icon and tooltip
    (BoardConfigPanel.tsx:210-214).
  - `danger_level: 'high'` is never set, so Load is never disabled by a warning.
  - An `Alert severity="warning"` under the selector lists every badge for the selected library
    design.
- `ui_in`: after a library load, the Alert says "inputs set to 0x05" when `ui_in` is not null,
  plus "pins held high: 3" when `ui_in_held` is not empty.
- CSRF:
  - `EmbedOptions` gains `csrfToken?: () => string`. `daemonJson` adds `X-CSRFToken` to every
    non-GET request when it is set, and board.js passes the cookie reader it already has.
  - Today's `enableFpgaDesign` POST sends no CSRF token, and Django's `CsrfViewMiddleware` is on
    (`pib/settings.py:65`), so the Commander's "Load design" is probably refused with 403 in
    production now. The hardware check confirms this before and after the fix.
  - The site's tests use Django's test `Client`, which skips CSRF checks by default. The new
    site tests use `Client(enforce_csrf_checks=True)`.
- Release: tag `embed-v0.3.0` (release-embed.yml). The site's pin
  (`tt_commander_embed_version` and `_sha256`, in fpgas.online-infra
  `ansible/inventory/host_vars/fpgas.online.yml:332`) is bumped by Tim after the release
  exists.
- The README (`README.fpgas-online.md`) documents the `csrfToken` option, the library source
  and the site routes it calls.

## 5. tinytapeout-vga-videos: the harness's files are not strays

The archive's per-design directories now hold files this pipeline did not write:
`<shuttle>/<macro>/*.bin`, and `fpga-library.json` at the root. The rules:

- `tt-vga mirror` (ttvga/remote.py:283-316) keeps using no `--delete`. It adds
  `--exclude '/*/*/*.bin' --exclude '/fpga-library.json'`, so a mirror can neither overwrite
  nor (should `--delete` ever come) remove them. A test pins both.
- The mirror's summary adds `bitstreams: <n>` and `fpga-library.json: present | absent`, so the
  files show up as known, not as unexplained extras.
- `ttvga.fpgalibrary.FOREIGN = ("/*/*/*.bin", "/fpga-library.json")` is the one list of
  harness-owned patterns. Anything here that lists, checks or tidies the archive (today only
  the mirror; later the stale-on-server check planned in the raw-traces pipeline plan) skips
  these.
- Nothing here replaces or deletes an archive directory `<shuttle>/<macro>/` wholesale. A future
  directory swap must keep `*.bin`. The raw-traces pipeline plan (in the `pipeline-plan`
  worktree, not yet committed) assumes a `<shuttle>/<macro>/fpga/` subdirectory; it must use
  these patterns instead.
- `docs/publishing.md` gains a section naming these files, their owner (the
  tt-harness-fpga-vga session) and this spec.

## 6. Harness publisher (tt-harness-fpga-vga): the interface contract

The tt-harness-fpga-vga session does this work. This spec only fixes what it must produce:

- `tthfv publish --archive <dir>` (the archive path is given on the command line and not
  recorded in the repo) exports every design admitted to the library (harness spec, Publish):
  builds `ok` or `timing-fail`, current, with a reference.
- It applies the id rule above. That replaces `demo_name` on the `demos-export` branch, which
  keeps `tt_um_` and uses 33 + 6 characters. It also applies the uniqueness checks, which use
  the demo names from tinytapeout-fpga-demos at a recorded commit.
- Write order:
  1. Every `<shuttle>/<macro>/<id>-<sha256[:12]>.bin`, skipping files already there (same name
     means same bytes).
  2. `fpga-library.json.tmp`, checked with `tt-vga fpga-library-check <tmp> --bins <archive>`.
  3. `rename` the tmp file over `fpga-library.json`.

  Bins never appear after the index that names them, at least on big-storage. The onward
  five-minute rsync can still reorder them, hence the site's "may still be syncing" message.
- Old `.bin` files are never deleted by the publisher.
- Files are mode 0644, directories 0755. The owner is the account that owns the archive; the
  harness session uses the same `--as-user` arrangement as `tt-vga mirror`.
- Nothing goes to `/srv/data.wafer.space` until Tim has seen this format and said so.
- The title holds no warning text (the `demos-export` exporter puts the warning into the title
  and description today). Warnings are derived by readers.

## 7. Security

- **What a bitstream is.** A bitstream is configuration data for the iCE40 only. The SDK's
  loader clocks it into the FPGA over SPI (`spi_transferPIO`). The RP2350 and the Pi store and
  copy it but never execute it. The library gives a visitor no new power: anyone can already
  upload an arbitrary bitstream to the same board (`POST /bitstream`). A library visitor picks
  an id; the bytes come from the archive and are pinned by `bin_sha256` in the index.
- **Trust in the archive.** Whoever can write the archive or its HTTPS front can choose which
  bitstream gets loaded. That is the same power a visitor upload has, so it is not an
  escalation. The site still checks size, hash and preamble, and the daemon checks them again,
  so a corrupted or truncated transfer is caught on the way.
- **Pin contention.** A design can drive pins the Pi's Pmod HAT also drives. The same is true of
  uploads; the library adds no new limit and no new exposure. Library builds use the same
  `tt_fpga_top.v` and `tt_fpga_fabricfox.pcf` as the demos (research section 4), so they drive
  only the demo harness's pins. `ui_in` is applied through the guard that never drives a pin
  something else holds high.
- **SSRF.** The site requests only the fixed base plus a checked relative path. It refuses
  redirects, checks the host, applies timeouts and size caps, and never lets a request choose a
  URL.
- **Load on the services.**
  - The site: one library load per board at a time, a 4 MiB cap on the index, a 256 KiB cap
    per bin, and an index cached for 5 minutes.
  - The archive: one ~100 KB fetch per load of an entry the Pi does not hold.
  - The Pi: its RAM is capped by `--library-max-bytes`.
- **Injection.** In the pages, every string goes in with `textContent`. Links must be
  `https://`, and image and video URLs are built only from validated relative paths. On the
  daemon, file names come only from `NAME_RE` ids, and the stored metadata is checked against
  the schema before it is written.
- **CSRF.** Every POST requires the token. This fixes the Commander's current gap.

## 8. Deploy order and partial deploys

Recommended order:

1. Merge the daemon PR. CI's build-deb publishes the rolling deb, and the APT repo pulls it
   within 15 minutes.
2. Tim re-runs the Pi play (`ansible/roles/onpi/tasks/tt.yml` installs `fpgas-online-tt` with
   `state: latest` into the shared NFS root), then the Pis restart the service.
3. Merge the site PR. Tim runs the site play (roles `site` and `ttsite`).
4. Merge the Commander PR and tag `embed-v0.3.0`. Tim bumps `tt_commander_embed_version` to
   `0.3.0`, with its sha256, and runs the site play again.
5. The harness session publishes into the archive once Tim has approved the format.
6. Hardware check (section 9).

Any partial deploy still works:

| Deployed | Not deployed | Result |
|---|---|---|
| site | daemon | the panel says "board software too old"; the load route answers 501; demos, uploads and the Commander are unchanged |
| site, daemon | archive files | the panel says "The VGA library is not published yet." |
| daemon | site | nothing pushes, so the library stays empty; `/designs` gains the `library` key, which the old board.js and Commander ignore |
| site, daemon | Commander 0.3.0 | the board.js panel works; the old Commander lists a loaded library design as a plain project, and its own Load stays as it is today |
| Commander 0.3.0 | daemon | no `library` key, so the Commander shows no library entries |

## 9. Testing

### tinytapeout-vga-videos

- `tests/test_fpgalibrary.py`:
  - the id rule, including the four example rows, a hashed id that is exactly 40 characters,
    and a non-`tt_um_` macro that is refused;
  - `validate` on the fixture: no violations;
  - one test for each rule, each mutating the fixture once;
  - `--bins` catching a wrong hash, a wrong size and a missing preamble.
- `tests/test_mirror.py`: the mirror script has both excludes, has no `--delete`, and prints the
  new summary lines.

### fpgas.online-tt

`tests/test_designs.py`:

- store, replace and idempotent push;
- LRU eviction by bytes, which never touches uploads, and uploads never touching the library;
- precedence demo > library > upload;
- upload refused for a cached library id;
- library listing metadata and `library: null` on the other sources;
- the `ui_in` REPL steps: with null, `LOAD_CODE` is unchanged byte for byte; with 5, the guard
  and the value are added; `ui_in_held` is parsed back;
- `safe.py` still produces the same `SAFE_CODE` after the guard moves into `UI_IN_GUARD`.

`tests/test_server.py`:

- `GET /library`;
- the `POST /library/{id}` check table, one test per row;
- the `/designs` `library` key;
- enable-body checks for `ui_in` (true, -1, 256, "5", 5, null);
- concurrent pushes and an upload, with nothing lost;
- the 404/503 identity rules on the new routes.

The pty-backed fake board and `tests/fakerepl.py` stand in for the board.

`tests/data/library/` holds a copy of the fixture.

### fpgas.online-site

`tests/test_library.py`:

- `normalise`: each rule, dropping one entry, dropping duplicates, and a whole document refused;
- `fetch_index` and `fetch_bin`, with a fake `requests`:
  - 200, 304 and a stale copy served;
  - a redirect refused, oversize refused, a timeout;
  - a hash, size or preamble mismatch;
  - 404 giving the "still syncing" message.

`tests/test_views.py`, with the fake daemon (`monkeypatch` on `ttsite.daemon` functions, the
existing pattern):

- the index route's ETag/304, gzip, and 404 on a non-FPGA board;
- the load route:
  - a cached entry is not fetched;
  - a push and then an enable sends `clock_hz` and `ui_in` from the index;
  - an old daemon answers 501;
  - an entry evicted before enable is retried once;
  - the per-board lock answers 409;
  - an unknown id answers 404;
  - CSRF is enforced, with `Client(enforce_csrf_checks=True)`.

`tests/test_daemon.py`: `library_state` (an old daemon's non-JSON 404) and `library_push`
(multipart shape).

`tests/js/library.test.mjs`: matching, shuttle order, paging bounds and badge text. The fixture
is copied to `tests/data/fpga-library.json`.

### tt-commander-app

- `src/model/fpgaLibrary.spec.ts`: load, merge order, no library without the key, the load
  route, and badges.
- `fpgaDesigns.spec.ts`: the CSRF header on POST, and `ui_in: null` sent on enable.
- `ProjectSelect` search over shuttle and macro, and the 100 cap, tested through
  `BoardConfigPanel.spec.tsx`.
- `BoardConfigPanel.spec.tsx`: the warning icon and Alert, and Load not disabled for
  timing-fail.

### tt-harness-fpga-vga

The harness session's own tests, plus `tt-vga fpga-library-check` run as a program on its
output.

### Hardware check (one FabricFox board, after Tim's deploys)

Etiquette:

- Write a claim in `~/github/TinyTapeout/tmp/board-claims/` for one board not claimed by
  another session (fpga-4 is the harness session's, fpga-1 the capture session's; ask first).
- Check `status.json`: `clients == 0`, and the idle display reads `loaded`.
- Abort if someone else connects.

Steps:

1. Read-only first.
   - `GET /api/board/<slug>/designs`: the response has the top-level `library` key.
   - `GET /api/board/<slug>/library`: about 445 entries, and `ttsky25a_vga_example` is among
     them.
2. In a browser, on the board page, search `vga_example`, choose shuttle `ttsky25a`, and press
   Load on `ttsky25a_vga_example`. This is the TinyVGA template example, the library's
   equivalent of the `tt_um_vga_pattern` demo; it rendered `ok` and has `ui_in: null`.
   - The site answers `pushed: true`.
   - `/designs` shows `enabled: "ttsky25a_vga_example"` and lists it with `source: "library"`.
   - The camera shows the pattern.
3. Press Load again: `pushed: false`, and it is faster.
4. Load one entry with `ui_in` not null, through the Commander this time. The Alert shows the
   inputs set, and `ui_in_held` is empty.
5. Confirm the Commander's CSRF fix: its Load works. Note whether 0.2.0 failed with 403 before
   the bump; read that from the site's nginx log, not by trying.
6. Restore the board: `tools/board_restart.py` from vgacap, then wait for the idle display to
   read `loaded` (about 75 s). Delete the claim. Uploads on the board are untouched; compare the
   `/designs` upload list from before and after.

The whole session stays under 10 minutes and makes no uploads.

## 10. Not in scope

- Hardware validation of the library designs (the harness's job).
- Scripted `ui_in` sequences (`ui_in_script`); v1 carries a constant only.
- A library deb, or putting library designs into tinytapeout-fpga-demos.
- CORS on data.wafer.space; no browser fetches a `.bin`.
- Links from the videos `index.html` to bitstreams.

## 11. Questions for the owner

1. **Pi RAM for the library cache.** The cache sits on the tmpfs overlay. Is 16 MiB per Pi
   (about 160 designs) acceptable? Recommended: yes, as the default flag value, revisited if
   the Pis report memory pressure.
2. **Showing the format before publishing.** Is this schema-1 document, as shown, the format the
   harness may publish? Recommended: yes. The harness writes into the archive after your OK on
   this spec.
3. **Commander CSRF.** Fix the Commander's missing CSRF token in this work (EmbedOptions
   `csrfToken`), or as its own PR first? Recommended: its own small PR first, because it
   probably breaks "Load design" today.
4. **Which board for the hardware check.** Recommended: fpga-2 if no session holds it (it is
   in neither the capture session's nor the harness session's split), else fpga-4 after asking
   the harness session.
