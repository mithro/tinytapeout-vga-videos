# SPDX-License-Identifier: Apache-2.0
"""Reference checker for `fpga-library.json`, schema 1.

The index lists prebuilt iCE40UP5K bitstreams of VGA designs. The harness
writes it, and the site, the daemon and the Commander read it. This module is
the one executable statement of the rules; it is run as a program
(`tt-vga fpga-library-check`) and never imported by the other repositories.

Deferral: a rule that depends on other fields is skipped while those fields are
themselves invalid, so one fault gives one violation. These fields are the
inputs (`DEFERRING_FIELDS`): `shuttle` and `macro` (for `id`, `bin` and the
media paths), `bin_sha256` (for `bin`) and `ui_in_mask` (for `ui_in`). An entry
with a bad input and a bad dependent field still fails and exits 1; the
dependent violation only shows up after the input is fixed. The CLI prints
"dependent checks deferred" in that case.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

# The packaged demos' `top_module` names, from tinytapeout-fpga-demos da7d10d
# (demos/<name>/info.yaml). A library id may not equal any of them.
DEMO_NAMES: tuple[str, ...] = (
    "tt_um_counter_7seg",
    "tt_um_factory_test",
    "tt_um_pwm_breathe",
    "tt_um_uart_hello",
    "tt_um_vga_pattern",
)
IDLE_NAME = "idle_display"  # the daemon's IDLE_NAME

MAX_DESIGNS = 2000
MAX_BIN_BYTES = 262144
PREAMBLE = bytes.fromhex("7eaa997e")
PREAMBLE_WINDOW = 68

SHUTTLE_RE = re.compile(r"[a-z0-9]{1,16}\Z")
MACRO_RE = re.compile(r"tt_um_[A-Za-z0-9_]{1,58}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GENERATED_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
VERDICT_RE = re.compile(r"[a-z-]{1,32}\Z")
PATH_RE = re.compile(r"[a-z0-9]{1,16}/tt_um_[A-Za-z0-9_]{1,58}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")
NAME_RE = re.compile(r"[a-z0-9_]{1,40}\Z")


def library_id(shuttle: str, macro: str) -> str:
    """The design's name on the Pi (Ruling AC)."""
    if not macro.startswith("tt_um_"):
        raise ValueError(f"macro {macro!r} does not start with tt_um_")
    name = re.sub(r"[^a-z0-9_]", "_", f"{shuttle}_{macro[len('tt_um_'):]}".lower())
    if len(name) > 40:
        digest = hashlib.sha256(f"{shuttle}/{macro}".encode()).hexdigest()[:8]
        name = f"{name[:31]}_{digest}"
    return name


def check_reserved(id: str) -> str | None:
    """A message when `id` is a name the library may not use, else None."""
    if id == IDLE_NAME:
        return f"{id!r} is the daemon's idle display name"
    if id in DEMO_NAMES:
        return f"{id!r} is a packaged demo's name"
    return None


# --- field rules: each returns None when the value passes, else the rule it breaks.

Rule = Callable[[Any], "str | None"]


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _int_range(lo: int, hi: int) -> Rule:
    def rule(v: Any) -> str | None:
        if not _is_int(v):
            return "must be an int"
        if not lo <= v <= hi:
            return f"must be {lo} to {hi}"
        return None

    return rule


def _pattern(regex: re.Pattern[str], what: str) -> Rule:
    def rule(v: Any) -> str | None:
        if not isinstance(v, str):
            return "must be a string"
        if not regex.match(v):
            return f"must be {what}"
        return None

    return rule


def _length(lo: int, hi: int) -> Rule:
    def rule(v: Any) -> str | None:
        if not isinstance(v, str):
            return "must be a string"
        if not lo <= len(v) <= hi:
            return f"must be {lo} to {hi} characters"
        return None

    return rule


def _choice(*options: str) -> Rule:
    def rule(v: Any) -> str | None:
        if not isinstance(v, str) or v not in options:
            return "must be one of " + ", ".join(options)
        return None

    return rule


def _bool(v: Any) -> str | None:
    return None if isinstance(v, bool) else "must be a bool"


def _nullable_bool(v: Any) -> str | None:
    return None if v is None or isinstance(v, bool) else "must be true, false or null"


def _url(v: Any) -> str | None:
    if not isinstance(v, str):
        return "must be a string"
    if v and not (v.startswith("https://") and len(v) <= 500):
        return "must be empty, or https:// and at most 500 characters"
    return None


def _no_dotdot(v: str) -> bool:
    return ".." not in v


def _pinout(v: Any) -> list[tuple[str, str]]:
    """Violations as (sub-path, rule); the sub-path is "" for the object itself."""
    if not isinstance(v, dict):
        return [("", "must be an object")]
    out = []
    for key in ("ui_in", "uo_out", "uio"):
        labels = v.get(key)
        if not isinstance(labels, list) or len(labels) != 8:
            out.append((key, "must be an array of exactly 8 strings"))
        elif not all(isinstance(s, str) and len(s) <= 64 for s in labels):
            out.append((key, "must hold only strings of at most 64 characters"))
    return out


# Entry keys with a self-contained rule. Keys that depend on others (id, bin, the
# media paths, ui_in, pinout) are handled in `_entry_violations`.
SIMPLE_RULES: dict[str, Rule] = {
    "shuttle": _pattern(SHUTTLE_RE, "1 to 16 of a-z0-9"),
    "macro": _pattern(MACRO_RE, "tt_um_ followed by 1 to 58 of A-Za-z0-9_"),
    "title": _length(1, 200),
    "author": _length(0, 200),
    "description": _length(0, 2000),
    "docs_url": _url,
    "repo_url": _url,
    "commit": _pattern(COMMIT_RE, "40 lowercase hex digits"),
    "clock_hz": _int_range(1, 200000000),
    "ui_in_mask": _int_range(0, 255),
    "bin_bytes": _int_range(1, MAX_BIN_BYTES),
    "bin_sha256": _pattern(SHA_RE, "64 lowercase hex digits"),
    "build_status": _choice("ok", "timing-fail"),
    "fmax_hz": _int_range(1, 1000000000),
    "validation": _choice("none", "mcu", "full-speed"),
    "verdict": _pattern(VERDICT_RE, "1 to 32 of a-z and -"),
    "qspi": _choice("none", "emulated"),
    "pdk_latches": _bool,
    "synthesis_differs": _nullable_bool,
}
ENTRY_KEYS = (
    "id", "shuttle", "macro", "title", "author", "description", "docs_url", "repo_url", "commit",
    "clock_hz", "pinout", "ui_in_mask", "ui_in", "bin", "bin_bytes", "bin_sha256", "build_status",
    "fmax_hz", "validation", "verdict", "qspi", "pdk_latches", "synthesis_differs", "poster", "preview_gif", "video_10s_webm",
)  # fmt: skip
# Keys a reader accepts missing, for now (Ruling CH: missing `synthesis_differs` means null).
# Making one required is removing it from this set.
OPTIONAL_FOR_NOW = frozenset({"synthesis_differs"})
MEDIA_KEYS = ("poster", "preview_gif", "video_10s_webm")
# Fields whose invalidity defers the checks that depend on them (see the module docstring).
DEFERRING_FIELDS = frozenset({"shuttle", "macro", "bin_sha256", "ui_in_mask"})


def _media_rule(v: Any, shuttle: Any, macro: Any) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        return "must be a string or null"
    if not PATH_RE.match(v) or not _no_dotdot(v):
        return "must be a relative archive path <shuttle>/<macro>/<file> without .."
    if _valid(shuttle, "shuttle") and _valid(macro, "macro") and v.split("/")[:2] != [shuttle, macro]:
        return "must start with the entry's <shuttle>/<macro>/"
    return None


def _valid(value: Any, key: str) -> bool:
    return SIMPLE_RULES[key](value) is None


def derived_bin(entry: dict) -> str | None:
    """The path `bin` must equal, or None when its inputs are not valid themselves."""
    shuttle, macro, sha = entry.get("shuttle"), entry.get("macro"), entry.get("bin_sha256")
    if not (_valid(shuttle, "shuttle") and _valid(macro, "macro") and _valid(sha, "bin_sha256")):
        return None
    return f"{shuttle}/{macro}/{library_id(shuttle, macro)}-{sha[:12]}.bin"


def _entry_violations(entry: dict, seen_ids: set[str]) -> list[tuple[str, str]]:
    """(field, rule) pairs for one entry, at most one per field."""
    out: list[tuple[str, str]] = []
    for key in ENTRY_KEYS:
        if key not in entry:
            if key not in OPTIONAL_FOR_NOW:
                out.append((key, "missing"))
            continue
        value = entry[key]
        rule: str | None
        if key in SIMPLE_RULES:
            rule = SIMPLE_RULES[key](value)
        elif key == "id":
            rule = _id_rule(entry, value, seen_ids)
        elif key == "pinout":
            for sub, why in _pinout(value):
                out.append((f"pinout.{sub}" if sub else "pinout", why))
            continue
        elif key == "ui_in":
            rule = _ui_in_rule(entry, value)
        elif key == "bin":
            rule = _bin_rule(entry, value)
        else:  # media
            rule = _media_rule(value, entry.get("shuttle"), entry.get("macro"))
        if rule:
            out.append((key, rule))
    return out


def _id_rule(entry: dict, value: Any, seen_ids: set[str]) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    shuttle, macro = entry.get("shuttle"), entry.get("macro")
    if _valid(shuttle, "shuttle") and _valid(macro, "macro") and value != library_id(shuttle, macro):
        return f"must equal library_id(shuttle, macro) = {library_id(shuttle, macro)!r}"
    if not NAME_RE.match(value):
        return "must match ^[a-z0-9_]{1,40}$"
    reserved = check_reserved(value)
    if reserved:
        return reserved
    if value in seen_ids:
        return "duplicate id"
    return None


def _ui_in_rule(entry: dict, value: Any) -> str | None:
    mask = entry.get("ui_in_mask")
    if value is not None and _int_range(0, 255)(value) is not None:
        return "must be null or an int from 0 to 255"
    if not _valid(mask, "ui_in_mask"):
        return None  # the mask is already reported
    if value is None:
        return "must not be null when ui_in_mask is not 0" if mask else None
    if mask == 0:
        return "must be null when ui_in_mask is 0"
    if value & ~mask:
        return "has bits outside ui_in_mask"
    return None


def _bin_rule(entry: dict, value: Any) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    want = derived_bin(entry)
    if want is not None and value != want:
        return f"must equal {want!r}"
    if want is None and (not PATH_RE.match(value) or not _no_dotdot(value)):
        return "must be a relative archive path without .."
    return None


def validate(doc: object) -> list[str]:
    """Every rule of spec section 1; each field gives at most one violation."""
    if not isinstance(doc, dict):
        return ["document: must be a JSON object"]
    out: list[str] = []
    for key, rule in (
        ("schema", lambda v: None if _is_int(v) and v == 1 else "must be the int 1"),
        ("generated", _pattern(GENERATED_RE, "a UTC time like 2026-11-26T03:00:00Z")),
        ("tthfv_commit", _pattern(COMMIT_RE, "40 lowercase hex digits")),
        ("videos_repo_commit", _pattern(COMMIT_RE, "40 lowercase hex digits")),
    ):
        if key not in doc:
            out.append(f"{key}: missing")
        elif (why := rule(doc[key])) is not None:
            out.append(f"{key}: {why}")
    designs = doc.get("designs")
    if "designs" not in doc:
        out.append("designs: missing")
        return out
    if not isinstance(designs, list):
        return out + ["designs: must be an array"]
    if len(designs) > MAX_DESIGNS:
        out.append(f"designs: must hold 0 to {MAX_DESIGNS} entries")
    seen_ids: set[str] = set()
    seen_shuttles: set[str] = set()
    previous_shuttle: object = None
    for i, entry in enumerate(designs):
        if not isinstance(entry, dict):
            out.append(f"designs[{i}]: must be an object")
            continue
        problems = dict(_entry_violations(entry, seen_ids))
        shuttle = entry.get("shuttle")
        if "shuttle" not in problems and shuttle != previous_shuttle and shuttle in seen_shuttles:
            problems["shuttle"] = f"{shuttle!r} entries must form one unbroken run"
        out.extend(f"designs[{i}].{key}: {why}" for key, why in _in_key_order(problems))
        if isinstance(entry.get("id"), str) and "id" not in problems:
            seen_ids.add(entry["id"])
        if isinstance(shuttle, str):
            seen_shuttles.add(shuttle)
            previous_shuttle = shuttle
    return out


def _in_key_order(problems: dict[str, str]) -> list[tuple[str, str]]:
    order = {k: n for n, k in enumerate(ENTRY_KEYS)}
    return sorted(problems.items(), key=lambda kv: order.get(kv[0].split(".")[0], len(order)))


def check_bins(doc: dict, root: Path) -> list[str]:
    """Each bin's existence, size, hash and preamble, one violation per entry at most."""
    out = []
    for i, entry in enumerate(doc.get("designs", [])):
        rel = entry.get("bin") if isinstance(entry, dict) else None
        if not isinstance(rel, str) or not PATH_RE.match(rel) or not _no_dotdot(rel):
            continue  # validate() reports it
        path = root / rel
        try:
            size = path.stat().st_size
            data = path.read_bytes() if size <= MAX_BIN_BYTES else b""
        except OSError as exc:
            out.append(f"designs[{i}].bin: cannot read {rel}: {exc.strerror}")
            continue
        if size > MAX_BIN_BYTES:
            why = f"is {size} bytes, over {MAX_BIN_BYTES}"
        elif len(data) != entry.get("bin_bytes"):
            why = f"is {len(data)} bytes, bin_bytes says {entry.get('bin_bytes')}"
        elif hashlib.sha256(data).hexdigest() != entry.get("bin_sha256"):
            why = "does not match bin_sha256"
        elif PREAMBLE not in data[:PREAMBLE_WINDOW]:
            why = "has no 7E AA 99 7E preamble in its first 68 bytes"
        else:
            continue
        out.append(f"designs[{i}].bin: {rel} {why}")
    return out


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not allowed in fpga-library.json")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text} is not a finite number")
    return value


def load(path: Path) -> object:
    """Read a document, refusing NaN, Infinity and numbers too large for a float."""
    return json.loads(
        Path(path).read_text(encoding="utf-8"), parse_constant=_refuse_constant, parse_float=_finite_float
    )


def add_parser(sub) -> None:
    p = sub.add_parser("fpga-library-check", help="check an fpga-library.json against schema 1")
    p.add_argument("file", type=Path)
    p.add_argument("--bins", type=Path, help="archive root holding the bins; checks size, hash and preamble")
    p.set_defaults(func=_run)


def _field_of(violation: str) -> str:
    """`designs[3].ui_in_mask: ...` gives `ui_in_mask`."""
    return violation.split(":", 1)[0].rpartition(".")[2]


def _run(args) -> int:
    try:
        doc = load(args.file)
    except (OSError, ValueError, RecursionError) as exc:
        print(f"{args.file}: {type(exc).__name__}: {exc}")
        return 1
    try:
        problems = validate(doc)
        if args.bins is not None and isinstance(doc, dict) and isinstance(doc.get("designs"), list):
            problems += check_bins(doc, args.bins)
    except RecursionError as exc:
        print(f"{args.file}: RecursionError: {exc}")
        return 1
    for line in problems:
        print(line)
    if any(_field_of(line) in DEFERRING_FIELDS for line in problems):
        print("dependent checks deferred: fix the shuttle, macro, bin_sha256 and ui_in_mask violations, then recheck")
    if not problems:
        print(f"{args.file}: ok, {len(doc['designs'])} designs")
    return 1 if problems else 0
