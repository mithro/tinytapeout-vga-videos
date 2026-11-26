# SPDX-License-Identifier: Apache-2.0
"""Render the data-upload host files from these templates and a values file.

    uv run host/data-upload/render.py VALUES.toml OUT_DIR

The files here are what gets installed on the publishing host, except that every
host-specific value (host and account names, absolute host paths) is a
`{{NAME}}` placeholder: this repository never names a host.  VALUES.toml holds
one string per placeholder and is kept privately, beside the host's runbook.

Every placeholder must have a value and every value must be used, so a renamed
placeholder cannot leave a template half rendered.  OUT_DIR must not exist yet.
The scripts are written 0755, everything else 0644.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = {
    "data-upload-sync": 0o755,
    "data-upload-frames-sync": 0o755,
    "frames.conf": 0o644,
    "data-upload-wafer-space-frames.service": 0o644,
    "data-upload-wafer-space-frames.timer": 0o644,
    "data-upload-wafer-space-frames-full.service": 0o644,
    "data-upload-wafer-space-frames-full.timer": 0o644,
}
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
# Safe inside a sh assignment, a Python string literal and a unit file.
VALUE = re.compile(r"[A-Za-z0-9 ._/:@+-]*")


class RenderError(Exception):
    pass


def render(values: dict, out_dir: Path) -> None:
    for name, value in values.items():
        if not isinstance(value, str) or not VALUE.fullmatch(value):
            raise RenderError(f"value {name} = {value!r} must be a string of [A-Za-z0-9 ._/:@+-]")
    texts, used = {}, set()
    for name in TEMPLATES:
        text = (HERE / name).read_text()
        for key in PLACEHOLDER.findall(text):
            if key not in values:
                raise RenderError(f"{name}: no value for {{{{{key}}}}}")
            used.add(key)
        texts[name] = PLACEHOLDER.sub(lambda m: values[m.group(1)], text)
        if "{{" in texts[name] or "}}" in texts[name]:
            raise RenderError(f"{name}: a malformed placeholder is left after rendering")
    unused = sorted(set(values) - used)
    if unused:
        raise RenderError(f"values never used: {', '.join(unused)}")
    out_dir.mkdir(parents=True)
    for name, mode in TEMPLATES.items():
        path = out_dir / name
        path.write_text(texts[name])
        path.chmod(mode)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[0], "rb") as f:
        values = tomllib.load(f)
    try:
        render(values, Path(argv[1]))
    except (RenderError, FileExistsError) as e:
        print(f"render.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
