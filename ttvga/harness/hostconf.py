# SPDX-License-Identifier: Apache-2.0
"""Read and check the host's `<root>/host.toml`. Runs on the host.

The host's paths live there and nowhere in the repository:

    frames_root = "/abs/path/to/archive/frames"   # the published frames subtree
    staging_dir = "/abs/path/to/staging"          # copies are made here, then swapped in
    min_free_root_gb = 100.0                      # optional

A wrong `frames_root` would let a publish replace a directory of the archive
itself, so `load` refuses anything that does not look like the frames subtree
made by the host setup: it must carry the marker `.ttvga-frames-root`, it must
not be the archive (no `index.html` or `index.json`), the staging directory
must not be inside it, and the two must be on one filesystem so the final
swap is a rename.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT_MARKER = ".ttvga-frames-root"
ARCHIVE_FILES = ("index.html", "index.json")
DEFAULT_MIN_FREE_ROOT_GB = 100.0


class ConfigError(Exception):
    """host.toml is missing, incomplete or names unsafe paths."""


@dataclass(frozen=True)
class HostConfig:
    frames_root: Path
    staging_dir: Path
    min_free_root_gb: float


def _path(data: dict, key: str, source: Path) -> Path:
    if key not in data:
        raise ConfigError(f"{source}: {key} is missing")
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{source}: {key} must be a path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"{source}: {key} must be an absolute path, not {value!r}")
    if not path.is_dir():
        raise ConfigError(f"{source}: {key} {path} is not a directory")
    return path


def load(root: Path) -> HostConfig:
    """Read `<root>/host.toml` and check it; raise ConfigError naming the key or the reason."""
    source = Path(root) / "host.toml"
    try:
        with open(source, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{source}: host.toml is missing") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{source}: host.toml is not valid TOML: {e}") from None

    frames_root = _path(data, "frames_root", source)
    staging_dir = _path(data, "staging_dir", source)
    min_free = data.get("min_free_root_gb", DEFAULT_MIN_FREE_ROOT_GB)
    if isinstance(min_free, bool) or not isinstance(min_free, (int, float)) or min_free < 0:
        raise ConfigError(f"{source}: min_free_root_gb must be a non-negative number, not {min_free!r}")

    if not (frames_root / ROOT_MARKER).is_file():
        raise ConfigError(f"{source}: frames_root {frames_root} has no {ROOT_MARKER} marker (made by the host setup)")
    for name in ARCHIVE_FILES:
        if os.path.lexists(frames_root / name):
            raise ConfigError(f"{source}: frames_root {frames_root} holds {name}: it is the archive, not its frames subtree")
    real_root, real_staging = frames_root.resolve(), staging_dir.resolve()
    if real_staging.is_relative_to(real_root):
        raise ConfigError(f"{source}: staging_dir {staging_dir} is inside frames_root {frames_root}")
    if os.stat(frames_root).st_dev != os.stat(staging_dir).st_dev:
        raise ConfigError(f"{source}: frames_root and staging_dir are on different filesystems")
    return HostConfig(frames_root, staging_dir, float(min_free))
