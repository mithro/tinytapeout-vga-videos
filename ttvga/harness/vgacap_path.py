# SPDX-License-Identifier: Apache-2.0
"""Find the pinned vgacap clone and build under a ttvga root (standard library only).

`<root>/tools/vgacap-src` and `<root>/tools/vgacap-build` are made by
`tt-vga bootstrap` at the commit pinned in `ttvga/tools.toml`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def add_src(src: Path) -> None:
    """Put the Python package of the vgacap clone at `src` on sys.path (local dev-tools use this)."""
    path = str(Path(src) / "python")
    if path not in sys.path:
        sys.path.insert(0, path)


def add(root: Path) -> None:
    """Put the pinned vgacap Python package on sys.path."""
    add_src(Path(root) / "tools" / "vgacap-src")


def tools(root: Path) -> dict:
    """Paths of the built vgacap executables."""
    build = Path(root) / "tools" / "vgacap-build"
    return {name: build / name.replace("_", "-") for name in ("vgacap_sample", "vgacap_export", "vgacap_dump", "tracetool")}
