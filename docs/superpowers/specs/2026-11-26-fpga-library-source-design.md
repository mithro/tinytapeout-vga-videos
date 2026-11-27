# The VGA library: a third design source on the FabricFox boards

Status: draft for the owner, 2026-11-26. Third revision. Revision 2 answered the first
independent review (graded "not ready"; findings C1-C2, I1-I10 and 20 minor) under the
controller's rulings AC and AD (below). Revision 3 answers the re-review (graded "ready with
fixes"; findings N1-N5 and minors r1-r8). Revision 4 answers the re-check (P1, m-a to m-d). Revision 5 answers the second re-check (Q1, q-a, q-b) under rulings AF and AG.

Owner decision (Tim, 2026-11-26): "Our custom commander app and the tinytapeout.fpgas.online
interface should be updated to allow loading of the bitstreams from the same archive the vga
images are published too as another alternative to the demos in the fpgas-online repo and
uploading your own bitstream."

## Controller rulings

These rulings bind this spec.

| Ruling | Says |
|---|---|
| Y | The library is a real third source, `library`, in the [fpgas-tt daemon](https://github.com/fpgas-online/fpgas.online-tt). It has its own cache directory on each Pi and is filled by the [site](https://github.com/fpgas-online/fpgas.online-site) backend on tweed. The site fetches the index and the bitstreams from one fixed archive URL, checks them, and pushes the bytes to the daemon, so the Pis make no outbound connections. Option A, where the site loads library designs as ordinary uploads, is rejected: it would evict other visitors' uploads. |
| AC | The id rule in section 1 stands. It replaces Ruling X's draft wording (`<shuttle>_<macro>`, cut to 40 characters plus a 6-hex hash) and the `demo_name` function on the harness's `demos-export` branch. Two independent checks found it collision-free: the harness session ran it over its 445 designs, and the reviewer ran it over the 440 targets in this repo. |
| AD | The daemon never changes `tt.mode` and never uses the SDK's "MCU controls inputs" mode. It drives the `ui_in` pins directly, as `safe.py` intends. It drives only the bits in the entry's `ui_in_mask`, which the harness publishes using its `effective_ui_in_mask` rule. Every library load makes the bits outside its mask inputs with the pull-down, released as described in section 2, including when the mask is 0, so a mask of 0 makes all eight bits inputs (controller ruling on m-a). "A mask of 0 drives nothing" still holds: no bit is driven. Every enable, whatever the source, first releases the pins the daemon drove before, so a later demo or upload never inherits a library design's inputs. |
| AF | Only pins in `_fo_ui_driven` get the 1 ms output-low discharge. Every other released pin goes straight to `Pin.IN` with the pull-down and is never made an output. The E9 input-enable workaround (PADS_BANK0 `GPIOn.IE = 0`) is used only if the hardware check shows the discharge alone is not enough. |
| AG | `safe.py:99` reads `0xd0000020` as the SIO output-enable register. That is `GPIO_OE` on the RP2040, but on the RP2350 it is the write-only `GPIO_OUT_CLR`; the RP2350's `GPIO_OE` is `0xd0000030`. A separate fpgas.online-tt PR, before the daemon's library work, picks the register by chip, with a test, and keeps `SAFE_CODE`'s structure. |
| BJ | Entries carry a bool `pdk_latches`: true when the design uses PDK latch or clock-gate cells. The publisher writes it on every entry, and it is required like every other key: it was optional only while the readers were deployed, and became required once the published index carried it on all 357 entries (2026-11-27). When true, both UIs show the warn badge `PDK latch cells: may not behave as on silicon`, which never disables Load. Provenance: on 2026-11-27, about 08:35 local, the FPGA session asked the owner, as item 4 of a numbered list, "Should the 11 latch-cell designs be listed with a warning, or stay unpublished as now?" The owner replied "(4) Yes." Because it was an either/or question, the FPGA session read that as "list with a warning" and said so back to the owner, who made no correction. The owner then confirmed it directly on 2026-11-27, in the controller session (AskUserQuestion answer: "List with the warning"). |

## Why

[tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) builds iCE40UP5K
bitstreams of the Tiny Tapeout VGA designs for the FabricFox boards (fpga-1 to fpga-4). There
are about 445 of them, each 104,090 bytes.

Today a board can load two kinds of design, and neither can carry the library:

- **The packaged demos.** Five of them come from
  [tinytapeout-fpga-demos](https://github.com/fpgas-online/tinytapeout-fpga-demos), as a deb
  in the Pi NFS root. A deb holding the library would bloat
  [the APT repo](https://github.com/fpgas-online/apt), which keeps every version in git.
- **Visitor uploads.** The Pi keeps at most 16 and evicts the oldest.

The archive at <https://data.wafer.space/big-storage/tinytapeout-vga-videos/> already holds a
poster, a preview and clips for each design. The bitstreams join them there, and both UIs pick
from that archive.

## What changes, per repository

| Repository | Change |
|---|---|
| [tinytapeout-vga-videos](https://github.com/mithro/tinytapeout-vga-videos) (this repo, owns the archive) | the schema, a fixture, the checker `tt-vga fpga-library-check`, and a mirror that leaves the harness's files alone |
| [tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) | `tthfv publish` writes the `.bin` files and `fpga-library.json` into the archive (the contract is in section 6) |
| [fpgas.online-tt](https://github.com/fpgas-online/fpgas.online-tt) (the daemon) | first, a fix PR for `safe.py`'s output-enable register (Ruling AG); then a library cache, `GET /library`, `POST /library/{id}`, library entries in `/designs`, and `ui_in` and `ui_in_mask` on enable |
| [fpgas.online-site](https://github.com/fpgas-online/fpgas.online-site) (the `ttsite` app) | an index proxy, a load route, a redis lock, the upload-name check, and the VGA library panel |
| [tt-commander-app](https://github.com/fpgas-online/tt-commander-app) (the fpgas-online fork, branch `fpgas-online`) | a CSRF header (shipped first), the `library` source, search by shuttle and macro, and warnings |
| [fpgas.online-infra](https://github.com/fpgas-online/fpgas.online-infra) | a systemd drop-in for the library cap; Tim re-runs the plays and bumps the Commander pin |

The TinyTapeout checkout `~/github/TinyTapeout/tt-commander-app` is the upstream app. It has no
FPGA support and is not touched.

Checkouts read, all clean and level with their remotes:

| Repository | HEAD |
|---|---|
| fpgas.online-tt | `6834ce9` |
| fpgas.online-site | `b8ce772` |
| tt-commander-app | `df74e3c` |
| fpgas.online-infra | `cc8b0e65` |
| tt-harness-fpga-vga | `112ff4b` |
| tinytapeout-vga-videos | `46b4a6e` |
| TT SDK (tt-micropython-firmware) | `15ba5ce` |

## How a load works

1. **Is the board new enough?** The page fetches `GET /api/board/<slug>/designs`. A new daemon
   puts a top-level `library` object in the answer. Without it, the board's software is too old
   for the library.
2. **The catalogue.** The page fetches `GET /api/board/<slug>/library`. The site answers from
   its checked copy of `fpga-library.json`. That copy is the only source of library metadata
   (findings I6, I10).
3. **Load.** The visitor presses Load. The page sends
   `POST /api/board/<slug>/library/<id>/load`.
4. **Lock and state.** The site takes the board's lock in redis, then asks the daemon
   `GET /library`. If the Pi already holds `<id>` with the index's `bin_sha256`, the site skips
   to step 6.
5. **Fetch and push.** The site fetches `<base><bin>` from the archive. It checks the size, the
   hash and the preamble, then sends the bytes in `POST /library/<id>`. The daemon checks them
   again and stores them. Storing may evict other library entries, never uploads.
6. **Enable.** The site sends `POST /designs/<id>/enable` with the entry's `clock_hz`, `ui_in`
   and `ui_in_mask`. The daemon releases any `ui_in` pins it drove before, loads the design
   exactly as it loads a demo or an upload, sets the clock, and drives the masked `ui_in` bits.
7. **Refresh.** The page reloads `/designs` and calls the Commander's `refreshDesigns()`. The
   Commander, when it is the one that loaded, calls `syncState()`.

The whole route runs under one 50 s wall-clock deadline. The Commander uses the same route.

## 1. `fpga-library.json`, schema 1

### Where

- Index: `<archive>/fpga-library.json`, beside the videos' `index.json`. The public URL is
  `https://data.wafer.space/big-storage/tinytapeout-vga-videos/fpga-library.json`.
- Bitstreams: `<archive>/<shuttle>/<macro>/<id>-<sha256[:12]>.bin`, in the design's existing
  video directory. The name holds part of the file's hash, so a file never changes. A rebuild
  gets a new name and the old file stays, so a page holding an older index can still load it.
- `<archive>` is `/srv/data.wafer.space/tinytapeout-vga-videos` on big-storage, a symlink into
  `/backups`. A sync copies it to data.wafer.space every five minutes.
- The onward rsync sorts names. `fpga-library.json` sorts before the `tt*/` directories, so
  during a sync **the new index always arrives before the bins it names**, for the length of
  that sync. The site reports this case as "may still be syncing". Owner question 2 asks for a
  second rsync pass.
- Only the tt-harness-fpga-vga session writes these files, and only after Tim has seen the
  format.

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
      "ui_in_mask": 0,
      "bin": "ttsky25a/tt_um_vga_example/ttsky25a_vga_example-0123456789ab.bin",
      "bin_bytes": 104090,
      "bin_sha256": "0123456789ab0123456789abcdef0123456789abcdef0123456789abcdef0123",
      "build_status": "ok",
      "fmax_hz": 31420000,
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

### JSON rules

These apply to the whole document.

- `NaN`, `Infinity` and `-Infinity` are refused, both when the index is written and when it is
  read. Writers use `allow_nan=False`. Python readers use a `parse_constant` that raises. The
  JavaScript readers never see these values, because the site normalises the document first.
- A bool is never accepted where an int or a number is required.
- Readers ignore unknown keys. A breaking change bumps `schema`.

### Top-level keys

Every key is required.

| Key | Type | Rule |
|---|---|---|
| `schema` | int | `1` |
| `generated` | string | UTC, `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` |
| `tthfv_commit` | string | `^[0-9a-f]{40}$` |
| `videos_repo_commit` | string | `^[0-9a-f]{40}$` |
| `designs` | array of objects | 0 to 2000 entries, in display order (see Order below) |

### Entry keys

Every key is required. A key whose type allows null is still present.

| Key | Type | Rule |
|---|---|---|
| `id` | string | equals `library_id(shuttle, macro)`; see The id rule |
| `shuttle` | string | `^[a-z0-9]{1,16}$` |
| `macro` | string | `^tt_um_[A-Za-z0-9_]{1,58}$`, original case |
| `title` | string | 1 to 200 characters; holds no warning text |
| `author` | string | 0 to 200 characters |
| `description` | string | 0 to 2000 characters |
| `docs_url` | string | empty, or `https://` and at most 500 characters |
| `repo_url` | string | empty, or `https://` and at most 500 characters |
| `commit` | string | `^[0-9a-f]{40}$` |
| `clock_hz` | int | 1 to 200000000 (the harness writes 25175000 where the project says 0) |
| `pinout` | object | the keys `ui_in`, `uo_out`, `uio`, each an array of exactly 8 strings of at most 64 characters |
| `ui_in_mask` | int | 0 to 255: the bits the board may drive on `ui_in` for this design. The harness computes it with `effective_ui_in_mask` (below) |
| `ui_in` | int or null | null when `ui_in_mask` is 0; otherwise an int from 0 to 255 with `ui_in & ~ui_in_mask == 0` |
| `bin` | string | exactly `<shuttle>/<macro>/<id>-<bin_sha256[:12]>.bin` |
| `bin_bytes` | int | 1 to 262144 |
| `bin_sha256` | string | `^[0-9a-f]{64}$` |
| `build_status` | string | `ok` or `timing-fail` |
| `fmax_hz` | int | from 1 to 1000000000: nextpnr's achieved frequency, in Hz like `clock_hz` |
| `validation` | string | `none`, `mcu` or `full-speed` (from the harness spec's Validate section) |
| `verdict` | string | `^[a-z-]{1,32}$`: the videos pipeline's render verdict |
| `qspi` | string | `none` or `emulated` |
| `pdk_latches` | bool | true when the design uses PDK latch or clock-gate cells (Ruling BJ) |
| `poster` | string or null | relative path; see The archive path rule |
| `preview_gif` | string or null | relative path; same rule |
| `video_10s_webm` | string or null | relative path; same rule |

`bin` can be worked out from the other fields. It is kept anyway, as a path that is checked:
readers refuse an entry whose `bin` differs from the derived path. That way a reader never has
to rebuild the rule to find the file, and an exporter bug shows up as a refused entry rather
than a wrong fetch.

#### `ui_in_mask` and the Welland HAT

On the Welland boards the Pi's Pmod HAT wires `ui_in[k]` and `uio[k]`, for k = 1 to 3, to the
same Pi GPIO. Each pair is therefore one electrical net. This is recorded in the harness's
hardware-validation spec, lines 49-56, and in `fpgas.online-tt src/fpgas_tt/safe.py:7-9`.

The harness's `effective_ui_in_mask` (hardware-validation spec, lines 122-127) works the mask
out like this:

- Start from the bits the design's inputs use.
- Drop `ui_in[k]`, for k = 1 to 3, for any design whose reference simulation ever enables
  `uio[k]` as an output (`uio_oe_any`). It is decided bit by bit, because each tie is its own
  net.
- Drop any bit the Welland census found driven by something else.

The harness publishes the mask it worked out. `ui_in` is the value from the override, already
limited to that mask.

`tt-vga fpga-library-check` refuses an entry where `ui_in & ~ui_in_mask` is not 0, or where
`ui_in` is null but the mask is not 0.

### The archive path rule

This rule covers `bin`, `poster`, `preview_gif` and `video_10s_webm`.

- The path matches
  `^[a-z0-9]{1,16}/tt_um_[A-Za-z0-9_]{1,58}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`.
- Its first two segments equal the entry's `shuttle` and `macro`.
- It contains no `..`.
- A reader joins it onto the one fixed base URL and never accepts an absolute URL.

### Order

The order of `designs` is the display order for both UIs. The harness writes the entries
grouped by shuttle, newest shuttle first, and sorted by title within each shuttle. It takes
shuttle dates from its manifest.

The order of the shuttle filter is the order in which each shuttle first appears in
`designs`. Neither UI keeps its own list of shuttles.

The checker requires the following:

- each shuttle's entries form one unbroken run;
- the ids are unique.

### The id rule (Ruling AC)

The id is the design's name on the Pi. It is also the name the SDK reports as enabled.

`library_id(shuttle, macro)` works like this:

1. Take `lower(<shuttle> + "_" + <macro with the leading "tt_um_" removed>)`.
2. Map every character outside `[a-z0-9_]` to `_`.
3. If the result is longer than 40 characters, keep its first 31 characters, then `_`, then
   the first 8 lowercase hex digits of the SHA-256 of the UTF-8 string `<shuttle>/<macro>`.
   That string keeps its original case and its `tt_um_` prefix. The result is then exactly 40
   characters.

A macro that does not start with `tt_um_` is an error; the rule never guesses. The result
always matches `^[a-z0-9_]{1,40}$`, the daemon's `NAME_RE` at
`fpgas.online-tt src/fpgas_tt/designs.py:41`.

The rule has been run twice. The harness session ran it over its 445 designs: 445 distinct ids,
10 of them hashed. The reviewer ran it over the 440 targets in `data/targets.json`: 440
distinct ids, none equal after case-folding, 10 hashed, and every one 40 characters or fewer.

| shuttle/macro | id |
|---|---|
| `tt05/tt_um_flappy_vga_cutout1` | `tt05_flappy_vga_cutout1` |
| `tt07/tt_um_MichaelBell_rle_vga` | `tt07_michaelbell_rle_vga` |
| `ttsky25a/tt_um_vga_example` | `ttsky25a_vga_example` |
| `ttihp25a/tt_um_yuri_panchul_sea_battle_vga_game` | `ttihp25a_yuri_panchul_sea_battl_09a2562b` |
| `ttsky25a/tt_um_rebeccargb_vga_timing_experiments` | `ttsky25a_rebeccargb_vga_timing__4638a050` |

Reserved names. The exporter and the checker both refuse:

- an id equal to another id;
- an id equal to a packaged demo's name. A demo's name is the `top_module` in its
  tinytapeout-fpga-demos `demos/<name>/info.yaml` (`tools/build.py:31`). At `da7d10d` those are
  `tt_um_counter_7seg`, `tt_um_factory_test`, `tt_um_pwm_breathe`, `tt_um_uart_hello` and
  `tt_um_vga_pattern`;
- an id equal to `idle_display`, the daemon's `IDLE_NAME`.

The rule's output always begins with a shuttle id, so it cannot produce any of these names. The
reserved-name check is a separate function, `check_reserved(id)`, kept as a guard and tested on
its own (finding m11).

`validate` checks each field against its first failing rule and stops there, so a field gives
at most one violation. For `id`, the first rule is "equals `library_id(shuttle, macro)`".

The daemon refuses the same reserved names when an entry is pushed (section 2).

### Warnings, worked out by readers

Both UIs compute the same badges from an entry. Neither ever disables Load because of a badge:
Tim said on 2026-11-24 that designs which fail timing are listed, with a visible warning.

| Condition | Badge text | Class |
|---|---|---|
| `build_status == "timing-fail"` and `fmax_hz < clock_hz` | `timing: <fmax_hz / 1e6, 2 decimals> MHz < <clock_hz / 1e6, 3 decimals> MHz`, for example `timing: 17.08 MHz < 25.175 MHz` | warn |
| `build_status == "timing-fail"` and `fmax_hz >= clock_hz` (Ruling AN: the main clock passes, another clock or a cross-domain path fails) | `timing not met on a secondary clock or path` | warn |
| `pdk_latches == true` (Ruling BJ) | `PDK latch cells: may not behave as on silicon` | warn |
| `validation == "none"` | `not hardware-validated` | info |
| `validation == "mcu"` | `validated at MCU speed only` | info |
| `qspi == "emulated"` | `QSPI emulated` | info |
| `verdict != "ok"` | `video: <verdict>` | info |
| `ui_in` not null and not 0 | `inputs set: 0x<ui_in as 2 hex digits>` | info |

`not hardware-validated` is an info badge, not a warning. Every entry has it in the first pass,
and a warning icon on all 445 entries would teach visitors to ignore warnings (finding m16).
The warn class, and the Commander's warning icon, mean a doubt about how the design behaves on
the FPGA: missed timing, or PDK latch cells (Ruling BJ; its provenance is in the rulings table).

### Reference checker and fixture (this repo)

The module `ttvga/fpgalibrary.py` holds:

| Name | What it does |
|---|---|
| `library_id(shuttle, macro)` | the id rule |
| `check_reserved(id)` | the reserved-name check |
| `validate(doc) -> list[str]` | every rule above, at most one violation per field |
| `check_bins(doc, root)` | checks each bin's size, hash and preamble |
| `load(path)` | reads a document, refusing NaN and Infinity |

`tt-vga fpga-library-check <file> [--bins <dir>]` exits 1 on any violation. The harness runs it
as a program. Nothing imports it, so the two repos have no code dependency.

The fixture is `tests/fixtures/fpga-library/fpga-library.json`, with its bins beside it under
the archive layout. It has five entries:

| Entry | What it covers |
|---|---|
| 1 | `ok`, `ui_in` null |
| 2 | `timing-fail` |
| 3 | a hashed id |
| 4 | `ui_in: 1`, `ui_in_mask: 1` |
| 5 | every media path null |

Each fixture bin is 4,096 bytes: `ff 00 00 ff 7e aa 99 7e`, then zeros, except that byte 8 holds
the entry's index (0 to 4), so the five hashes differ. The hashes in the fixture are the real
ones.

Other repos copy the fixture into their tests. The copy carries a `_comment` key naming the
source commit. Copying keeps each repo free of a dependency on this one.

## 2. Daemon (fpgas.online-tt)

### Store

| Item | Value |
|---|---|
| Directory | `--library-dir`, default `/var/lib/fpgas-tt/library`. It sits inside the unit's existing `StateDirectory=fpgas-tt` (`debian/fpgas-tt.service:13`) |
| Files | `<id>.bin` holds the bytes. `<id>.json` holds `{"id", "bin_sha256", "bin_bytes"}` and nothing else (finding I6) |
| Cap | `--library-max-bytes`, the total size of the `.bin` files. The default comes from the environment variable `FPGAS_TT_LIBRARY_MAX_BYTES`, else 16777216, about 160 designs |
| Eviction | least recently used, by the mtime of `<id>.json`. A push or an enable refreshes it (`os.utime`). `touch` ignores `FileNotFoundError`, because an entry can be evicted after it was read |
| Orphans | a `.bin` without its `.json` (a write cut short), a `.json` without its `.bin`, and leftover `.*.tmp` files are deleted under the lock at the start of each store. A `.bin` alone is never listed |
| Never touches | `--uploads-dir` and its 16-slot eviction, the demos, the idle design |
| Writes | `.bin` first, then `.json`. Each goes to a temp file and then `os.replace` |
| Lock | `library._LIBRARY_LOCK`, a `threading.Lock`, held for writes and evictions. Uploads keep `designs._STORE_LOCK` |
| Lifetime | the Pi root is `overlayroot=tmpfs` (`fpgas.online-infra ansible/roles/fixpi/templates/boot/cmdline.txt.j2:1`). The cache lives in RAM and is lost at reboot; the site pushes again when it needs to |

The FPGA Pis are Pi 4s with at least 1 GB of RAM (`fpgas.online-infra docs/pi/models.md:9`),
so 16 MiB is small. `ExecStart` is fixed in the deb (`debian/fpgas-tt.service:16`), so infra
changes the cap through a drop-in that sets `Environment=FPGAS_TT_LIBRARY_MAX_BYTES=<n>`. The
`ExecStart` line is not repeated.

`library.py` imports nothing from `designs.py`, which avoids a circular import. `designs.py`
checks names with `NAME_RE` before it calls into `library`.

### Name precedence

A name resolves to a demo first, then to a library entry, then to an upload. The lookup is in
`design_file`, `designs.py:154-163`.

| Case | Answer |
|---|---|
| `POST /bitstream` with a name that is a cached library id | 409, "`<id>` is a VGA library design; pick another" |
| `POST /library/{id}` where `{id}` is a demo name or `idle_display` | 409 |
| `POST /library/{id}` where an upload of the same name exists | stored; the response says `"hides_upload": true`, and the site passes that on to the visitor (finding m19) |

The site also refuses an upload whose name is in the library index (section 3, finding I5).
After that, only an upload made before the index existed can share a name with a library entry.

### `GET /designs`, changed

The answer gains a top-level `library` object, and library entries in `designs`:

```json
{
  "enabled": "ttsky25a_vga_example",
  "library": {"max_bytes": 16777216, "used_bytes": 208180},
  "designs": [
    {"name": "tt_um_vga_pattern", "title": "...", "author": "...", "description": "...",
     "docs_url": "...", "repo_url": "...", "clock_hz": 25175000, "pinout": {}, "source": "demo"},
    {"name": "my_upload", "title": "", "author": "", "description": "", "docs_url": "",
     "repo_url": "", "clock_hz": null, "pinout": {}, "source": "upload"},
    {"name": "ttsky25a_vga_example", "title": "", "author": "", "description": "",
     "docs_url": "", "repo_url": "", "clock_hz": null, "pinout": {}, "source": "library",
     "size": 104090}
  ]
}
```

- The top-level `library` object shows that the daemon supports the library. An old daemon
  does not send it.
- A library entry has the shape of an upload entry: `title`, `author`, `description`,
  `docs_url` and `repo_url` are `""`, `clock_hz` is null and `pinout` is `{}`. It adds
  `source: "library"` and `size` (finding N2). These are the same "unknown" placeholders an
  upload carries, so a client that reads `/designs` (the pinned 0.2.x Commander's
  `pinoutFromDesign` reads `d.pinout[k]`, `fpgaDesigns.ts:43-48`) never meets a missing key.
  They are not a second copy of the metadata: the real title, clock, pinout, inputs and
  warnings come only from the site's index, keyed by `name`.
- Demo and upload entries are unchanged.
- Only cached entries are listed. The listing reads the directory and stats each `.json`. It
  never hashes a `.bin`.

### `GET /library`, new

```json
{"max_bytes": 16777216, "used_bytes": 208180,
 "entries": [{"id": "ttsky25a_vga_example", "bin_sha256": "...", "bin_bytes": 104090,
              "used_at": "2026-11-26T04:10:00Z"}]}
```

- It answers only on FPGA boards, following the same `_fpga_only` rules as `/designs`
  (`server.py:131-137`).
- It never touches the REPL and never waits for `taken`.

### `POST /library/{id}`, new

The body is multipart with two parts:

- `meta`: JSON, at most 4 KiB, of the form `{"id", "bin_sha256", "bin_bytes"}`;
- `file`: the bytes, at most 256 KiB.

The parts are read with `bitstream_upload`'s bounded part reader (`server.py:234-258`), which
moves into a shared helper.

Checks, in order. The first failure answers.

| Check | Status | Error |
|---|---|---|
| the board is an FPGA board (`_fpga_only`) | 404 / 503 | as for `/designs` |
| `{id}` matches `NAME_RE` | 404 | `no such design` |
| multipart, with both parts | 400 | `multipart form with parts 'meta' and 'file' required` |
| total size at most `MULTIPART_MAX_BYTES` | 413 | `request body too large (limit ...)` |
| `meta` is a JSON object with exactly the three keys and the right types (no bool, no NaN) | 400 | `meta: <first violation>` |
| `meta.id == {id}` | 400 | `meta.id does not match the URL` |
| `{id}` is not a demo name or `idle_display` | 409 | the same text as `validate_bitstream` |
| `len(file) == meta.bin_bytes` | 400 | `bitstream is <n> bytes, meta says <m>` |
| `sha256(file) == meta.bin_sha256` | 400 | `bitstream does not match bin_sha256` |
| size and preamble (`validate_bitstream`) | 400 | the same text as today |

Results:

| Case | Status | Body |
|---|---|---|
| the same `bin_sha256` is already stored | 200 | `{"id", "bin_bytes", "bin_sha256", "evicted": [], "hides_upload"}`; the LRU time is refreshed |
| otherwise, stored (an older build is replaced, then older entries are evicted until the total fits) | 201 | the same body, with `evicted` listing the ids removed |
| `OSError` while storing | 500 | `the library entry could not be kept on the Pi` |

A push counts as activity (`activity.touch()`), as an upload does.

### `POST /designs/{name}/enable`, changed (Ruling AD)

The body is `{"clock_hz": int | null, "ui_in": int | null, "ui_in_mask": int}`.

- Every key is optional. A missing `clock_hz` or `ui_in` means null; a missing `ui_in_mask`
  means 0.
- Each value is checked like `clock_hz` already is (`server.py:195-201`): no bool, and an int in
  range.
  - `ui_in_mask` out of range: 400 `ui_in_mask must be an integer between 0 and 255`.
  - `ui_in` out of range: 400 `ui_in must be an integer between 0 and 255`.
  - `ui_in` with bits outside the mask: 400 `ui_in has bits outside ui_in_mask`.
  - `ui_in` null with a mask other than 0: 400 `ui_in_mask needs a ui_in`.
- The caller always supplies the values. For a library entry the site reads them from its index;
  for a demo the gallery already sends `clock_hz`. The daemon never fills them in itself, so each
  value has exactly one source.
- The answer is:

  ```json
  {"enabled": "<name>", "clock_hz": 25175000, "ui_in": 1,
   "ui_in_mask": 1, "ui_in_driven": [0], "ui_in_held": [], "ui_in_inputs": [1, 2, 3, 4, 5, 6, 7],
   "released": [0]}
  ```

  | Key | Lists |
  |---|---|
  | `ui_in_driven` | the bits now driven |
  | `ui_in_held` | bits in the mask left as inputs because something outside held them high |
  | `ui_in_inputs` | from the release line's `inputs` list (finding q-b): on a library load, the bits outside the new mask that the daemon had not driven, released straight to inputs with the pull-down (all eight when the mask is 0 and nothing was driven before); empty for a demo or upload |
  | `released` | from the release line's `released` list: bits a previous load had driven, discharged and released before this load |

The REPL changes all live in `LOAD_CODE` (`designs.py:227-272`). Nothing touches `tt.mode`. The
`DemoBoard.mode` setter stops the project clock and re-creates every pin
(`tt-micropython-firmware src/ttboard/demoboard.py:225-238`, `src/ttboard/pins/pins.py:165-251`,
`:279-285`), and the harness spec says never to switch the SDK into that mode (lines 131-133).

**Release, always, before the FPGA is touched.** A new `__RELEASE__` block runs inside the
`try` of `LOAD_CODE`, right after the buffer's size and hash checks, and before `_fo_reader` is
built and `_fo_touched = True` is set (`designs.py:254-257`; findings r7 and m-b). A load refused
for a damaged buffer therefore leaves the previous design running with its inputs as they were,
and an exception inside the release cannot make the `finally` (`designs.py:269-270`) report
nothing enabled while the old design still runs.

The release set is:

- on every load, the pins in the board-side global `_fo_ui_driven` (the pins the daemon drove
  last time; empty when the global is missing);
- on a library load, also every bit outside the new entry's `ui_in_mask`, so all eight bits when
  the mask is 0 (controller ruling on m-a).

The set is released in two ways (Ruling AF; findings P1 and Q1).

**Pins in `_fo_ui_driven`** (the daemon drove them for the previous load) are released in three
steps:

1. If the RP2350 is driving the pin, its output latch is set to 0 and it stays an output for
   1 ms (`time.sleep_ms(1)`). That discharges the pad. "Driving" is read from the hardware, not
   from the SDK: bit `_fo_p.gpio_num` of the SIO `GPIO_OE` register, at `0xd0000030` on the
   RP2350 (`SIO_BASE` `0xd0000000` plus `SIO_GPIO_OE_OFFSET` `0x030`; the `ui_in` pins, GPIO 17
   to 24, are all in that low bank). The address comes from the shared expression that Ruling
   AG's fix introduces, which picks `0xd0000020` on an RP2040.
2. The pin becomes `Pin.IN`.
3. The pin gets `Pin.PULL_DOWN`.

**Every other pin in the set** (on a library load, the bits outside the new mask that the daemon
did not drive) goes straight to `Pin.IN` and then `Pin.PULL_DOWN`. It is never made an output,
even for a moment.

Why the discharge exists. On RP2350 A2 silicon (erratum RP2350-E9), a Bank 0 pad with its input
buffer on and only the internal pull-down can stay at about 2 V once it has been high. So a
pull-down alone may leave a released pin looking high to the FPGA, and the guard may then report
that pin as held. Driving it low for 1 ms first leaves it low.

Why only the daemon's own pins are discharged:

- The discharge adds no driver to the net, because it only applies to a pin the RP2350 is
  already driving. It only changes that driver's level, for 1 ms.
- For pins in `_fo_ui_driven`, the outgoing design's mask already excluded every `ui_in[k]`
  whose tied `uio[k]` that design drives. So the discharge cannot fight the outgoing design on
  those pins. It can still fight a Pi GPIO configured as an output on a tied net, for 1 ms. The
  census found no such GPIO; the harness's census rules exclude it.
- For any other pin the RP2350 drives, the daemon has no mask for the running design. That pin
  may be driven by the SDK's `ASIC_RP_CONTROL` baseline or by a visitor's `write_ui_in`. A 1 ms
  low there could fight a design that drives the tied `uio[k]` high, two push-pull drivers on one
  net (finding Q1). Those pins are therefore never discharged.
- Such a pin, released by the pull-down alone, may keep looking high on A2 silicon. Ruling AF
  accepts that. If the hardware check shows it matters, the E9 workaround is used for those pins
  instead: clear the pad's input enable (PADS_BANK0 `GPIOn.IE = 0`). That drives nothing, and the
  pull-down then holds the pin low. MicroPython's next `Pin.init` sets IE again.

The board's stepping is not yet known. The hardware check reads it. If the boards are A4 (E9
fixed), that is recorded here and the discharge stays: it is harmless.

Then the block clears `_fo_ui_driven` and prints
`released=` followed by JSON `{"released": [...], "inputs": [...]}`:

- `released` lists the previous `_fo_ui_driven` (the discharged pins);
- `inputs` lists the other pins released on a library load: the bits outside the new mask that
  were not in `_fo_ui_driven`. It is empty otherwise.

The enable answer's `released` and `ui_in_inputs` both come from this line (finding q-b).

Further rules for the release:

- The release runs on every enable: demo, upload, library, and the idle display's own load
  (`idle.py:268`).
- On a demo or upload load it releases only pins this daemon drove. Pins a visitor set through
  the Commander's ui_in controls are left alone.
- A soft reset clears the global. What the SDK's own start does to the `ui_in` pins depends on
  the board's `config.ini` mode (see Input pins at rest, below); the daemon never relies on it.

**Drive, after the clock, only on success.** The `__UI_IN__` block goes after `__CLOCK__`, after
the `try`/`finally`. That position runs only when the load succeeded. With `ui_in` null or the
mask 0, the block is empty; the release has already made every bit an input. Otherwise the block
is:

```python
from machine import Pin
import time, json
_fo_tt = tt
_fo_held = []
_fo_ui_driven = []
for _fo_i in range(8):
    if not (__MASK__ >> _fo_i) & 1:
        continue
    _fo_p = getattr(_fo_tt.pins, 'ui_in%d' % _fo_i)
<UI_IN_GUARD at indent 4, held list "_fo_held">
    _fo_p.raw_pin.value((__UI_IN__ >> _fo_i) & 1)
    _fo_p.mode = Pin.OUT
    _fo_ui_driven.append(_fo_i)
print('ui_in=' + json.dumps({'driven': _fo_ui_driven, 'held': _fo_held}))
```

Notes on the drive block:

- The bits outside the mask were made inputs by the release (finding N1). They are never added
  to `_fo_ui_driven`.
- Each masked pin's output latch is set before the pin becomes an output, so the pin never
  drives a stale value. `mode = OUT` goes through `raw_pin.init(Pin.OUT, pull=...)`
  (`tt-micropython-firmware src/ttboard/pins/standard.py:61-64`), which leaves the latch alone
  (finding r1).
- Both answer lines are JSON, parsed with `designs._parse_json` like the daemon's other board
  replies (finding r6).
- The project clock is not touched, so it keeps running.
- The last line is still `enabled`. `load_design` already checks only the last line, so the
  idle display's path keeps working (finding r2).

**Input pins at rest (finding N1, not yet verified on a board).**

- The SDK's default `config.ini` mode is `ASIC_RP_CONTROL`
  (`tt-micropython-firmware src/config.ini:21-25`).
- In that mode, `begin_asiconboard` makes every `ui_in` pin that does not read high an output
  (`src/ttboard/pins/pins.py:234-251`). It does this at start and again on every re-init
  (`demoboard.py:157-162`).
- `fpga_mux.enable` resets only `uio` (`fpga_mux.py:144-160`).

So on a board with the default `config.ini`, the RP2350 may already drive `ui_in` today, for
demos and uploads too. The harness saw `ui_in[0]` read 1 (hardware-validation spec, line 52),
which suggests the Welland FPGA boards may not be in that mode. This spec does not know which.

The hardware check reads, read-only and before any load:

- `tt.mode_str`;
- the `ui_in` pin directions;
- `GPIO_OE`;
- the chip revision.

It records the results here.

Whatever it finds, every library load makes every bit outside its mask an input, the mask-0
case included. Demo and upload loads release only what the daemon drove, and otherwise leave the
SDK's pin state as it is today.

**One guard, two callers, with `SAFE_CODE` unchanged byte for byte (finding I3).**
`designs.ui_in_guard(indent: int, held: str) -> str` returns exactly these lines, each prefixed
by `indent` spaces:

```
_fo_p.mode = Pin.IN
_fo_p.pull = Pin.PULL_DOWN
time.sleep_ms(5)
if _fo_p():
    <held>.append(_fo_i)
    continue
```

The caller must have bound `_fo_p` and `_fo_i`, imported `Pin` and `time`, and be inside a `for`
loop.

- `safe.py` builds `SAFE_CODE` with `ui_in_guard(12, "_fo_r['held']")` in place of its six
  literal guard lines (`safe.py:91-96`). Its `_fo_p.mode = Pin.OUT` line stays where it is. The
  Python comments at `safe.py:89-90` sit outside the string, so they do not affect the bytes.
  `SAFE_CODE` is then identical byte for byte, and a snapshot test pins that.
- `LOAD_CODE` uses `ui_in_guard(4, "_fo_held")`, as in the block above.

**Signatures.** New parameters are keyword-only with defaults, so the existing call sites keep
working: `idle.py:268`, `tests/test_idle.py:244-391`, and about 30 calls in
`tests/test_designs.py` (finding m14).

```python
load_design(runner, name, data, clock_hz, *, ui_in=None, ui_in_mask=0, overall=ENABLE_OVERALL_TIMEOUT)
enable_design(runner, name, clock_hz, demos_dir, uploads_dir, *, library_dir=None, ui_in=None, ui_in_mask=0, waited=0.0)
```

`library_dir=None` means "no library". `server.py` always passes `app["library_dir"]`.

Nothing else about loading changes. A library design is read from `<id>.bin` and goes through
`enable_design` and `load_design`, with the same buffer, the same on-board SHA-256 and the same
SDK loader as an upload. The 25 s `ENABLE_OVERALL_TIMEOUT` still applies.

### Concurrency

| Case | Behaviour |
|---|---|
| Two pushes at once | `_LIBRARY_LOCK` puts them in order |
| A push and an upload at once | separate locks and directories; neither evicts the other's files |
| A push during a load | the push only writes files; `_read_design` has already read the load's bytes |
| An entry evicted between push and enable | the enable answers 404; the site may push again (section 3) |
| An enable while the REPL is busy | 409, as today |

### Docs

The README route table and `CLAUDE.md` both get the new routes and the library store.

`CLAUDE.md`'s invariant "nothing is fetched or generated after boot" still holds. The Pi fetches
nothing; the library arrives only by push from the gateway, over the per-port VLAN that already
carries `/bitstream`.

## 3. Site (fpgas.online-site, `ttsite`)

### Settings

- **`TTSITE_LIBRARY_BASE_URL`**, in `pib/settings.py`, defaults to `""` (Ruling BB, after the
  pre-merge review: the site play installs main's tip, so a default-on would change the live site
  before the daemon is on the Pis). fpgas.online-infra sets it to
  `"https://data.wafer.space/big-storage/tinytapeout-vga-videos/"` once the daemon with the library
  store is deployed. It must be `https://` and end in `/`. When it is empty, the panel is not
  rendered, the routes answer 404 and the upload check does nothing. No request can change it.
- **`api_enable` forwards only `clock_hz`** (Ruling BA): a body with `ui_in` or `ui_in_mask` is
  a 400, so only the library load route can send the index's values; the daemon also refuses them
  for any design that is not in the library store.
- **A new cache alias, `ttsite`**, for the lock (finding I1). It is redis
  `redis://127.0.0.1:6379/2` with `KEY_PREFIX: "ttsite"`: its own database (finding r5).
  Django's `RedisCache.clear()` is a `FLUSHDB`, so sharing database 1 with `poe` would let
  clearing either alias drop the other's keys, a held load lock included. Database 0 is the
  channel layer's.
  - The comment above `CACHES` (`pib/settings.py:192-202`) is rewritten to list all three
    stores and why each redis alias has its own database (finding m-d): db 0 for the channel
    layer, db 1 for `poe`, db 2 for `ttsite`, and the `default` cache staying locmem per
    worker.
  - It is needed because gunicorn runs three workers
    (`fpgas.online-infra ansible/roles/site/templates/gunicorn.service.j2:13`), and the `default`
    locmem cache is per worker.
  - If redis does not answer, the load route answers 503 `the site cannot take the board lock;
    try again`. That follows the `poe` rule at `settings.py:186-190`.

### `ttsite/library.py`, new

**The HTTP session.** It is a module-level `requests.Session()` with `trust_env = False`, so
`.netrc` and proxy environment variables are ignored (finding m9). Every request uses
`allow_redirects=False` and `stream=True`, and every response is closed in `finally`. A 3xx
answer raises `archive redirected; refusing`.

**The deadline.** Every function takes `deadline: float`, a `time.monotonic()` value. Each socket
read uses `timeout=(3.05, max(0.5, deadline - now))`. The loop over `iter_content(65536)` checks
`now < deadline` after each chunk, so an archive that trickles bytes runs into the deadline
instead of holding the request open (finding I4).

**`fetch_index(deadline)`.** It requests `BASE + "fpga-library.json"`, with `If-None-Match` set to
the last ETag the archive sent, and reads at most 4 MiB. The JSON is parsed with a
`parse_constant` that refuses NaN and Infinity.

| Archive answers | Result |
|---|---|
| 304 | keep the cached copy |
| 404 | `NotPublished` (finding I9) |
| anything else other than 200 | `ArchiveError` |

**`normalise(doc) -> (index, dropped)`.** It applies the schema 1 rules.

- A wrong top level refuses the whole document.
- A bad entry is dropped and logged, as `load_demo_index` does (`designs.py:93-95`). Every entry
  sharing an id is dropped. A shuttle whose entries are not contiguous drops the later entries.
- The output is the site's wire format, `{"schema": 1, "generated", "base_url": BASE,
  "designs": [...]}`, keeping the index order.

**`fetch_bin(entry, deadline) -> bytes`.** It reads at most 262,145 bytes, then checks:

1. status 200;
2. the length equals `bin_bytes`;
3. the sha256 equals `bin_sha256`;
4. the preamble is in the first 68 bytes.

| Failure | Message |
|---|---|
| 404 | `archive file missing: the archive is still syncing; try again in a few minutes` |
| any of checks 2 to 4 | `archive file does not match the index` |
| transport error or deadline | `archive unreachable` |

**SSRF guard.**

- The base URL is fixed.
- Paths come only from normalised entries, which have passed the path rule.
- The final URL's scheme and host must equal the base's.
- Redirects are refused.
- Every read is bounded in bytes and in time.
- The route's `<id>` is only looked up in the index; it is never put into a URL.

### Caching

- **The index.** It is kept in the `default` locmem cache (per worker; that is fine for data)
  under `ttsite:library:index:v<NORMALISE_VERSION>`. The entry is `(archive_etag, body_bytes,
  site_etag, fetched_at)`, where `body_bytes` is the normalised body. A 304 reuses it without
  normalising again, so the key names the normaliser's version: a change to what `normalise`
  keeps bumps `NORMALISE_VERSION`, and a copy made by older code is a miss, fetched in full
  without `If-None-Match` (version 2 keeps `pdk_latches`; version 3 requires it, so no copy
  carries the old default; Ruling BJ).
  - It is fresh for 300 s.
  - If the archive fails, the last good copy is served for up to 24 h, with the header
    `X-TTSite-Library-Stale: <age>`.
  - `NotPublished` is cached for 60 s as its own state, so that visitors arriving before the
    first publish do not each hit the archive.
- **The ETag.** It is weak, and says so: `W/"sha256-<first 32 hex of sha256(body_bytes)>"`
  (finding r4). It is computed on the uncompressed body, so one value names the content
  whatever the encoding. The view uses `django.views.decorators.http.condition(etag_func=...)`
  as its outer decorator and `gzip_page` inside it, so the 304 decision happens before
  compression. Django compares `If-None-Match` weakly, so a browser's echo matches with or
  without gzip (finding m8).

### Routes

| Route | Method | Answer |
|---|---|---|
| `api/board/<slug:slug>/library` | GET | the normalised index; 404 `{"error": "VGA library not published", "detail": ""}` when the archive has no `fpga-library.json`; 502 `VGA library unavailable` when the cache is cold and the archive is down |
| `api/board/<slug:slug>/library/<str:name>/load` | POST | load one design (below) |
| `api/board/<slug:slug>/bitstream` (existing) | POST | refuses a `name` that is an id in the index, with 409 `<name> is a VGA library design; pick another` (finding I5). The check calls `library.index(deadline)` with a 5 s deadline, so a worker that has never fetched the index fetches it (finding r3); when the archive is down and no copy exists, the upload goes ahead |

The index route checks the board with `_fpga_board_or_error` (`views.py:113`); the result is
cached for 60 s per slug. The index is the same for every board, but it sits under the board's
URL because the Commander only knows `apiBase`. It sends `Cache-Control: private, max-age=60`.

The load route takes an empty body, `{}`. The clock, `ui_in` and `ui_in_mask` all come from the
index. Django's `CsrfViewMiddleware` applies, and the page sends `X-CSRFToken`. The deadline is
`D = start + 50 s`, under nginx's 60 s default `proxy_read_timeout` for `/api/`
(`fpgas.online-infra ansible/roles/ttsite/templates/vhost.conf.j2:25-28`).

Load route, step by step:

| Step | What happens | Answers |
|---|---|---|
| 1 | Check the board. `name` must match `^[a-z0-9_]{1,40}$` and be in the index | 404 `no such library design` |
| 2 | Take the lock: `caches["ttsite"].add("library-load:<slug>", 1, timeout=70)`. The TTL is above the deadline. Release it in `finally` | 409 `a library load is already running on this board` if the key exists; 503 if redis is down |
| 3 | `daemon.library_state(board, deadline=D)` | transport failure: 502; an aiohttp text 404 (an old daemon): 501 `{"error": "board software too old", "detail": "this board's fpgas-tt daemon has no VGA library support yet"}` |
| 4 | If the state lists `name` with the index's `bin_sha256`, go to step 6 | |
| 5 | `fetch_bin`, then `daemon.library_push(board, name, data, sha, deadline=D)` | |
| 6 | If less than 27 s is left (the daemon's 25 s deadline plus a margin), stop | 504 `the load ran out of time; try again` (the bin is cached by now, so a retry is quick) |
| 7 | `daemon.enable(board, name, {"clock_hz", "ui_in", "ui_in_mask"} from the entry)`, with read timeout `min(30, D - now)` | |
| 8 | If step 7 answered 404 and step 5 has not run: if at least 32 s are left, push once; then apply step 6's rule again (finding N4): under 27 s left gives the 504, otherwise enable once more. Otherwise pass the 404 through | 504 `the load ran out of time; try again` |
| 9 | On success, delete `ttsite:designs:<slug>` | the enable body plus `"pushed": bool` and `"hides_upload": bool` |

Every daemon call takes the deadline. A connect timeout stays 3.05 s, and a read timeout is
`min(<its own>, D - now)`.

### The VGA library panel (board.js, board.html)

**Where it goes.** `board.html` gets a `<section id="tt-library">` between the gallery list and
"Upload your own bitstream". It is rendered only when the board has the gallery and the setting
is not empty.

**The gallery.** "Designs on this board" keeps the demos and uploads. It shows a library entry
only while that entry is enabled, and takes the entry's title from the index.

The panel's states:

| State | What the panel shows |
|---|---|
| `/designs` has no top-level `library` | "This board's software is too old for the VGA library." |
| the index is loading | "Loading the VGA library..." |
| the index route answered 404 `VGA library not published` | "The VGA library is not published yet." |
| any other index error | the error text, and a Retry button |
| the index has no designs | "The VGA library is empty." |
| ready | the controls and one page of cards |

**The controls.**

- A search box. Every whitespace-separated term must be a case-insensitive substring of
  `title`, `author`, `shuttle`, `id` or `macro`.
- A shuttle filter, a `<select>`: "All shuttles", then each shuttle in the order it first appears
  in the index.
- A count, for example "123 of 445 designs".

**Paging.** 24 cards per page, with Previous and Next buttons and "page i of n". Only the
current page is in the DOM. Changing the search or the filter goes back to page 1.

**A card shows:**

- the poster, as `<img loading="lazy" decoding="async" width="160" height="120" alt="">`, or a
  blank box when there is none;
- the title, and "by <author>";
- the shuttle and macro;
- the badges;
- `on this board` if `/designs` lists the id with source `library`;
- `Running` if the id is enabled;
- a Load button;
- Docs and Source links (through `safeUrl`), and a Video link (`base_url + video_10s_webm`).

**Load.** It disables every Run and Load button on the page, and shows "Loading <title>:
fetching from the archive, then programming the FPGA (up to a minute)...". On success it shows
`<title> is running`. When `hides_upload` is true it adds "an uploaded design with the same
name is hidden while this one is on the board". Then it runs `loadDesigns()` and
`refreshDesigns()`, as `enable()` does today (`board.js:185-188`). Errors go through `errMsg`.

**Code.**

- The pure parts go in a new file, `static/ttsite/library.js`: matching, shuttle order, paging,
  badges, URLs, and `renderPage(container, state, doc)`. It is CommonJS plus a browser global,
  like `management`'s `power-button.js`.
- `node --test` runs `tests/js/library.test.mjs`, using a small fake document, the same way the
  power-button tests fake their page.
- `board.js` imports it and handles the fetching and events.
- All text is set with `textContent`.
- The gallery's badge rule (`board.js:155-156`) learns about `library`.
- `board.js` passes `csrfToken: csrf` (its existing cookie reader, `board.js:130`) to
  `mountCommander`.

## 4. Commander (tt-commander-app, branch `fpgas-online`)

**Its own PR, shipped first (finding m20).**

- `EmbedOptions` gains `csrfToken?: () => string`.
- `daemonJson` (`src/model/fpgaDesigns.ts:67-84`) adds `X-CSRFToken` to every request that is
  not a GET.
- Today `enableFpgaDesign` (`fpgaDesigns.ts:129-139`) POSTs without a token. The 0.2.0 bundle has
  the same code (`git diff embed-v0.2.0 HEAD` on both files is empty). Django refuses such a POST
  with 403, so the Commander's Load does not work in production now. The site's tests did not
  catch it, because the test `Client` skips CSRF checks. The new site tests use
  `Client(enforce_csrf_checks=True)`.
- `enableFpgaDesign` sends `{"clock_hz": <hz or null>}` exactly as today. Old daemons ignore
  keys they do not know.

**The library source** comes in the second PR, stacked on the first.

- **`FpgaDesign`** (`fpgaDesigns.ts:9-19`): `source` becomes `'demo' | 'upload' | 'library'`. A
  library design from `/designs` carries only `name`, `source` and `size`. Everything else comes
  from the index.
- **`src/model/fpgaLibrary.ts`**, new:
  - the `LibraryEntry` type, the site's entry;
  - `loadFpgaLibrary(apiBase)`, which maps a 404 `VGA library not published` to the state
    `notPublished`;
  - `loadLibraryDesign(apiBase, id)`, which POSTs `{}`;
  - `libraryWarnings(entry)`, which follows the section 1 table.
- **Merge (findings I5, I10).** It runs after `loadFpgaDesigns`, and only when the top-level
  `library` key is present.
  - The board's demos and uploads come first, in the daemon's order.
  - Then come all index entries, in index order.
  - Projects are keyed by (`macro`, `source`). A library entry is never replaced by a demo or an
    upload with the same name, and the other way round.
  - Each project's `address` is its position in the merged list, as today.
  - A library entry's project has `source: 'library'` and `shuttle`, and its `clock_hz` comes
    from the index. If `/designs` lists a library entry the index does not have, the Commander
    shows it under its name.
  - `syncSelectionToEnabled` (`fpgaDesigns.ts:98-106`) picks the project whose `macro` equals
    `enabled` and whose `source` equals what `/designs` says for that name. If `/designs` does not
    list the name, it picks the library project.
- **Pinout and description (finding N2).** `PinoutPanel` (`src/components/PinoutPanel.tsx:44-52`)
  builds the pinout from `fpgaDesigns.byName[project.macro]`. For a library project it uses the
  index entry's `pinout` and `description` instead; the daemon's `/designs` entry holds only the
  upload-shape placeholders.
- **Search.** `ProjectSelect` (`ProjectSelect.tsx:83-90`) matches on `title`, `author`, `shuttle`
  and `macro`. It shows at most 100 options, with a helper line: "showing 100 of 445; type to
  narrow".
- **Load (finding I10).** The routing lives in `TTBoardDevice.selectFpgaDesign`
  (`src/ttcontrol/TTBoardDevice.ts:130-146`).
  - A project with `source === 'library'` calls `loadLibraryDesign`. The `ui_in` result goes into
    `designNotice`, and then the Commander calls `this.syncState()` (`TTBoardDevice.ts:103`),
    because the daemon changed the pins behind the REPL.
  - Every other project keeps `enableFpgaDesign`.
  - Errors go to `designError`, as today.
- **Warnings.** A library project with a warn badge gets `danger_level: 'medium'` and
  `danger_reason` set to the badges joined with `; `. That reuses the existing icon
  (`BoardConfigPanel.tsx:210-214`). `'high'` is never set, so Load is never disabled. An
  `Alert severity="info"` under the selector lists every badge, together with `designNotice`.
- **Release.** The second PR is tagged `embed-v0.3.0`. Tim bumps the pin,
  `tt_commander_embed_version` and `_sha256`, in
  `fpgas.online-infra ansible/inventory/host_vars/fpgas.online.yml:333-334`. The first PR is
  tagged `embed-v0.2.1` and pinned the same way.
- **The README.** `README.fpgas-online.md` documents `csrfToken`, the library source and the
  routes.

## 5. tinytapeout-vga-videos: the harness's files are not strays

The archive's design directories now hold files that this pipeline does not write: the `.bin`
files in `<shuttle>/<macro>/`, and `fpga-library.json` at the root. These rules keep the
pipeline from treating them as strays.

- The one list of harness-owned patterns is `ttvga.harness.verify.FOREIGN_PATTERNS =
  ("*/*/*.bin", "fpga-library.json")`, relative to the archive root. The raw-traces pipeline
  plan on `main` (`docs/superpowers/plans/2026-11-26-raw-traces-pipeline.md:719-721`, its
  Task 16) defines it and owns it (finding N3). `verify.py` is standard library only and is
  copied to the host, so the list lives there and nothing on the library side holds a copy.
- `tt-vga mirror` (`ttvga/remote.py:283-316`) still never uses `--delete`. Pipeline Task 16
  adds an `--exclude "/" + p` for each pattern and pins it with its own test in
  `tests/test_mirror.py`. The library work does not touch the excludes.
- The library work adds only the mirror summary lines `bitstreams: <n>` and
  `fpga-library.json: present|absent`, and a section in `docs/publishing.md` naming these files
  and their owner.
- Nothing here replaces or deletes an archive directory `<shuttle>/<macro>/` wholesale. The
  pipeline plan on `main` follows Ruling AA and keeps its frames out of these directories.

## 6. Harness publisher (tt-harness-fpga-vga): the interface contract

The tt-harness-fpga-vga session does this work. This section fixes what it must produce:

- `tthfv publish --archive <dir>`. The path is never recorded in the repo.
- The id rule from section 1 (Ruling AC). It replaces `demo_name` on `demos-export`
  (`tthfv/demos.py:53-59`). The reserved-name checks use the demo names from
  tinytapeout-fpga-demos at a commit recorded in the run's log.
- `ui_in_mask` comes from `effective_ui_in_mask` for the Welland tie profile. `ui_in` is the
  override's value, already limited to that mask, or null when the mask is 0.
- `fmax_hz` is an int. The JSON is written with `allow_nan=False`. The order follows section 1's
  Order rule. The title holds no warning text.
- The writes happen in this order:
  1. every `.bin`, skipping files already there;
  2. `fpga-library.json.tmp`;
  3. `tt-vga fpga-library-check <tmp> --bins <archive>`, which must exit 0;
  4. a `rename` of the tmp file into place.
- Old bins are never deleted. Files are mode 0644 and directories 0755.
- Nothing is written to `/srv/data.wafer.space` until Tim says the format is approved.

## 7. Security

**What a bitstream is.** A bitstream is configuration data for the iCE40. The SDK's loader clocks
it into the FPGA over SPI. The RP2350 and the Pi store it and copy it, and never execute it.

**Choosing a design.** The library gives a visitor no new choice of bytes. Anyone can already
upload any bitstream. A library visitor picks an id. The archive supplies the bytes, and
`bin_sha256` pins them.

**Trust in the archive.** Whoever can write to the archive, or to its HTTPS front, decides which
bitstream gets loaded. That is the same power an uploader has. The site checks size, hash and
preamble, and so does the daemon.

**The board now drives inputs (new exposure, finding C2).** Today the daemon itself drives no
`ui_in` pin on an FPGA board (the SDK's own mode may; see Input pins at rest in section 2). With
the library, it drives the bits in `ui_in_mask`. That is new, and
these limits apply:

- Only the masked bits are driven. On every library load, the unmasked bits (all eight when the
  mask is 0) are released to inputs with the pull-down, after a 1 ms discharge if the RP2350 was
  driving them (finding P1).
- A masked bit that something already holds high is left as an input.
- The mask leaves out each `ui_in[k]` tied to a `uio[k]` that the design ever drives in its
  reference simulation.
- Every enable releases the pins the daemon drove for the previous load.

What remains is this. The mask rests on the simulation: a design that drives `uio[k]` only in a
state the simulation never reached could still fight `ui_in[k]`. The harness's hardware
validation is meant to catch that case, and it has not run yet. Every entry therefore carries
`not hardware-validated`. Owner question 3 asks whether driving inputs before that validation is
acceptable.

**Pins the design drives.** A design can drive pins that the Pi's HAT also uses. Uploads already
can. Library builds use the same harness files as the demos (`tt_fpga_top.v`,
`tt_fpga_fabricfox.pcf`).

**SSRF.** The site uses only the fixed base and a checked relative path. It refuses redirects,
checks the host, ignores the proxy environment, and bounds every read in bytes and time.

**Load.**

- Each board allows one library load at a time, and the lock is shared across gunicorn workers.
- Each route has a 50 s deadline.
- The index is capped at 4 MiB, and each bin at 256 KiB.
- The index is cached for 5 minutes.
- On the Pi, the cache is capped by `--library-max-bytes`.

**Injection.** Pages set text only with `textContent`, and links must be `https://`. In the
daemon, file names come only from ids that pass `NAME_RE`, and the metadata is three typed keys.

**CSRF.**

- Every new POST requires the token.
- The Commander's POSTs are fixed.
- The power-cycle POST to `/snmp/toggle` (`board.js:72-76`) sends no token and is outside this
  work (finding m18).

## 8. Deploy order and partial deploys

1. **Commander CSRF PR.** Merge it, tag `embed-v0.2.1`, and bump the pin; Tim runs the site play.
   This fixes the Commander's Load and depends on nothing.
2. **Daemon PRs.** Merge the `safe.py` register fix (Ruling AG) first, then the library PRs. CI
   builds the deb, and the APT repo pulls it within 15 minutes.
   - The infra PR adds the drop-in (`onpi_tt_library_max_bytes`, default 16777216).
   - Tim re-runs the Pi play (`ansible/roles/onpi/tasks/tt.yml`), and the Pis restart the
     service.
3. **Site PR.** Merge it; Tim runs the site play.
4. **Commander library PR.** Merge it, tag `embed-v0.3.0`, bump the pin, and run the site play.
5. **Publish.** The harness session publishes once Tim has approved the format.

For `pdk_latches` (Ruling BJ), the readers went first: the site, with its cache version
bumped (`NORMALISE_VERSION` 2), and the Commander, then an index that sets the key on every
entry. Only then did the readers make the key required (`NORMALISE_VERSION` 3).
6. **Hardware check** (section 9).

| Deployed | Not yet | Result |
|---|---|---|
| site | daemon | the panel says "board software too old"; the load route answers 501; everything else is unchanged |
| site, daemon | archive files | the index route answers 404, and the panel says "The VGA library is not published yet." |
| daemon | site | the library stays empty; the old board.js and Commander ignore the `library` key; a library entry would show with the `other` badge, but none exist |
| site, daemon | Commander 0.3.0 | the board.js panel works; 0.2.x lists a loaded library design by its name only |
| Commander 0.3.0 | daemon | no `library` key, so the Commander shows no library entries |
| publisher writing `pdk_latches` | site and Commander with Ruling BJ | the old site and Commander drop the key, so latch designs are listed without a warning |

## 9. Testing

### tinytapeout-vga-videos

**`tests/test_fpgalibrary.py`** covers:

- every row of the id table, and a hashed id of exactly 40 characters;
- a macro without `tt_um_` is refused;
- `check_reserved` refuses `idle_display` and each demo name;
- one test per rule;
- NaN and Infinity are refused;
- `ui_in` with bits outside the mask is refused;
- `pdk_latches` is required and must be a bool (Ruling BJ);
- non-contiguous shuttles are refused;
- `--bins` mismatches are reported.

**The mirror summary test** (added to pipeline Task 16's `tests/test_mirror.py` after that task
lands) checks the `bitstreams:` and `fpga-library.json:` lines. The excludes and the absence of
`--delete` are pipeline Task 16's tests.

### fpgas.online-tt

**The `safe.py` register fix (Ruling AG), its own PR:** `SAFE_CODE` reads `0xd0000030` on an
RP2350 and `0xd0000020` on an RP2040, chosen on the board from SYSINFO `CHIP_ID`'s PART
field: `(0xd0000030 if (machine.mem32[0x40000000] >> 12) & 0xffff == 4 else 0xd0000020)`. PART is `0x0002` on the RP2040 and `0x0004` on the RP2350 (pico-sdk
`rp2040/.../sysinfo.h:30`, `rp2350/.../sysinfo.h:30`). No `sys` is imported, and the fake board
answers both chips.
Its other lines are unchanged. A test runs the selection for both chips against a fake
`machine.mem32`.

**The store:**

- store, replace, an idempotent push;
- LRU by bytes;
- orphans removed;
- `touch` after an eviction;
- uploads untouched, both ways;
- eight concurrent pushes.

**Designs:**

- precedence;
- an upload refused when it takes a cached library id;
- `hides_upload`;
- library entries listed in the upload shape plus `source` and `size`;
- an enabled id that is not cached.

**The REPL text:**

- `SAFE_CODE` matches its snapshot byte for byte;
- `__RELEASE__` is present on every load, and the idle display's load too;
- the drive block is absent when the mask is 0;
- with a mask, the drive block comes after `__CLOCK__`, and the text contains no `tt.mode` and no
  `clock_project_stop`;
- each latch is set before the pin becomes an output;
- on a library load the release set includes every unmasked bit (all eight for mask 0); on a
  demo or upload load it is `_fo_ui_driven` only;
- only a pin in `_fo_ui_driven` that `GPIO_OE` (bit `gpio_num`) shows as an output gets latch
  0, then `time.sleep_ms(1)`, before `Pin.IN` and `Pin.PULL_DOWN`; every other released pin
  goes straight to `Pin.IN` and `Pin.PULL_DOWN` and is never made an output (Ruling AF);
- the release sits after the hash check and before `_fo_reader` is built and
  `_fo_touched = True`;
- `released`, `ui_in_driven` and `ui_in_held` are parsed from the board's answer.

**The fake REPL:** a load with `ui_in: 1` and mask 1, then a demo load with null. The second load
releases bit 0.

**The server:**

- each row of the push table;
- the `ui_in` / `ui_in_mask` body rules;
- the top-level `library` key;
- the env-var default for the cap;
- the `_fpga_only` rules on the new routes.

### fpgas.online-site

**`tests/test_library.py`:**

- normalise;
- fetch with 200, 304 and 404 (`NotPublished`);
- stale copies;
- a redirect refused;
- oversize refused;
- NaN refused;
- a slow trickling archive stopped by the deadline;
- `trust_env` off;
- responses closed;
- the bin checks and the syncing message;
- `pdk_latches`: an entry without it dropped with `pdk_latches: missing`, a non-bool dropped
  with `pdk_latches: must be a bool`, and a copy cached by an older normaliser fetched in full,
  not revived by a 304.

**`tests/test_views.py`**, with the fake daemon (`monkeypatch` on `ttsite.daemon`):

- the ETag and 304 under `Accept-Encoding: gzip` with a `W/` `If-None-Match`;
- 404 when not published;
- 502 when the cache is cold and the archive is down;
- the cached skip;
- push, then enable with the index's values;
- 501 from an old daemon;
- the retry and its time rule, with the 27 s floor checked again before the second enable;
- 504 when time runs short;
- the lock taken through `caches["ttsite"]` (409 when held, 503 when redis is down);
- the upload-name refusal;
- CSRF with `Client(enforce_csrf_checks=True)`.

**`tests/js/library.test.mjs`:** matching, shuttle order derived from the index, paging bounds,
badge text (the latch badge only for a real `true`, with Load still enabled), and `renderPage`
on a fake document for each panel state.

### tt-commander-app

- the CSRF header;
- merging on (name, source);
- addresses;
- selection when a name has two sources;
- not published;
- the 100 cap;
- `selectFpgaDesign` routing, and `syncState` after a library load;
- the Pinout tab of an enabled library design, taken from the index;
- warnings that never disable Load;
- the latch badge only for a real `true`.

### Hardware check (one FabricFox board, after Tim's deploys)

Before starting:

- Write a claim in `~/github/TinyTapeout/tmp/board-claims/`.
- Confirm the board by its USB serial.
- Check `status.json`: `clients == 0`, and the idle display reads `loaded`.
- If anyone connects, stop and restore.

Steps:

1. **Read only.** `/designs` has the top-level `library` key; note the uploads it lists.
   `/library` has about 445 entries, including `ttsky25a_vga_example`. In the Commander REPL,
   without changing anything, read:
   - `tt.mode_str`;
   - each `tt.pins.ui_in<i>.mode_str`;
   - `hex(machine.mem32[0xd0000030])` (`GPIO_OE`);
   - SYSINFO `CHIP_ID` at `0x40000000`, both the raw value and the decoded revision: `m =
     machine.mem32[0x40000000]; n = m >> 28; print(hex(m), hex((m >> 12) & 0xffff), n,
     (n & 3) | ((n & 8) >> 1))`, which also prints the decoded PART (`0x4` on the RP2350). The
     raw nibble `n` is not the stepping. The SDK decodes it as `(n & 3) | ((n & 8) >> 1)`
     (pico-sdk `rp2350/pico_platform/platform.c:20-22`), where 2 means A2 and 4 means A4. An A4
     reads a raw nibble of 8 or more.

   Record them in section 2, Input pins at rest (findings N1 and P1). If the chip is A4, record
   that; the discharge step stays.
2. **First load.** On the board page, load `ttsky25a_vga_example`, the TinyVGA template that is
   the library's equivalent of the `tt_um_vga_pattern` demo. Expect `pushed: true`; `/designs`
   then shows it enabled with source `library`; the camera shows the pattern.
3. **Second load.** Load it again: `pushed: false`.
4. **Inputs and clock.** Through the Commander, load an entry with `ui_in` not null. Expect
   `ui_in_driven` to equal the mask's bits and `ui_in_held` to be empty. Then read the clock from
   the REPL: `tt.is_auto_clocking` must be True and `tt.auto_clocking_freq` equal to the entry's
   `clock_hz`. The camera must show a picture. Then read the levels of the pins this load
   released straight to inputs, as listed in its `ui_in_inputs` (finding s-a). If any reads 1,
   that is the case Ruling AF reserves the IE workaround for: report it to the controller.
5. **Release.** Load the `tt_um_vga_pattern` demo from the gallery. `released` lists the bits
   from step 4, and the clock is the demo's. Then read each released pin's level read-only
   (`getattr(tt.pins, 'ui_in%d' % i)()`). Each must read 0 (finding P1). With E9, the RP2350's
   own input reading and the level the FPGA sees are the same pad node. So this check reads the
   level after the pull-down, which is the level that matters (finding q-a). A demo load lists no
   straight-to-input pins; step 4 read those.
6. **Restore.** Run vgacap's `tools/board_restart.py`, wait for the idle display to read
   `loaded`, and check that the upload list matches step 1. Then delete the claim.

Stay under 10 minutes, and make no uploads.

## 10. Not in scope

- Validating the library designs on hardware (the harness does that).
- Timed `ui_in` sequences.
- A library deb.
- CORS on data.wafer.space.
- Links from the videos `index.html` to the bitstreams.
- The power-cycle POST's missing CSRF token.

## 11. Questions for the owner

1. **May the harness publish this schema 1 document into `/srv/data.wafer.space`?**
   Recommended: yes, once you have read this spec.
2. **Can the onward sync of `/srv/data.wafer.space` send the `*.bin` files before
   `fpga-library.json`?** For example, a second rsync pass for the index, or `--exclude
   fpga-library.json` on the first pass. That would end the window in which the index names
   bins that are not there yet. Recommended: yes, a two-pass sync. The site handles the window
   in any case.
3. **May the board drive the masked `ui_in` bits on the public boards before hardware
   validation, given that the mask rests on the simulation?** Recommended: yes. Only a handful
   of designs have `ui_in`, the mask already avoids the Welland HAT ties, and every enable
   releases the pins. If not, the harness publishes `ui_in_mask: 0` until `validation` is at
   least `mcu`.
4. **Which board for the hardware check?** Recommended: fpga-2 if no session holds it, else
   fpga-4 after asking the harness session.
