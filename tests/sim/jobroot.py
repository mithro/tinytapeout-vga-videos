# SPDX-License-Identifier: Apache-2.0
"""A local `job.py --root` for the job tests: the dev tools, a host.toml and file:// targets.

    make_root(tmp, dev) -> root

Layout (the host's, see `job.py`):
    tools/oss-cad-suite        -> the dev tools' oss-cad-suite
    tools/ffmpeg/bin/ffmpeg    -> /usr/bin/ffmpeg (the encode stage transcodes for real)
    tools/vgacap-src, tools/vgacap-build -> the dev tools'
    harness/HARNESS_VERSION    "test"
    host.toml                  frames_root (marked) and staging_dir, both under `tmp`
    targets.json               one target per design of tests/sim/designs/, each a file:// repository
    overrides/                 empty
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ttvga.devtools import DevTools

DESIGNS = Path(__file__).resolve().parent / "designs"
SHUTTLE = "tst"
HARNESS_VERSION = "test"
FFMPEG = Path("/usr/bin/ffmpeg")
_GIT_ENV = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_DATE": "2026-11-26T00:00:00Z", "GIT_COMMITTER_DATE": "2026-11-26T00:00:00Z"}


def macro_for(design: str) -> str:
    return f"tt_um_test_{design}"


def target_id(design: str) -> str:
    return f"{SHUTTLE}/{macro_for(design)}"


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ, **_GIT_ENV)
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {repo} failed (exit {p.returncode}): {p.stdout}{p.stderr}")
    return p.stdout.strip()


def _commit(repo: Path, verilog: str, message: str) -> str:
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "project.v").write_text(verilog)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _target(design: str, repo: Path, commit: str) -> dict:
    pinout = {f"{bus}[{i}]": "" for bus in ("ui", "uio") for i in range(8)}
    pinout.update({"uo[0]": "R1", "uo[1]": "G1", "uo[2]": "B1", "uo[3]": "vsync",
                   "uo[4]": "R0", "uo[5]": "G0", "uo[6]": "B0", "uo[7]": "hsync"})
    return {"id": target_id(design), "shuttle": SHUTTLE, "macro": macro_for(design),
            "repo": repo.resolve().as_uri(), "commit": commit, "top_module": macro_for(design),
            "source_files": ["project.v"], "language": "Verilog", "clock_hz": 0, "pinout": pinout}


def _symlink(link: Path, to: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(to)


def make_root(tmp: Path, dev: DevTools) -> Path:
    """Build a `--root` under `tmp` (see the module docstring) and return it."""
    tmp = Path(tmp).resolve()
    root = tmp / "root"
    tools = root / "tools"
    _symlink(tools / "oss-cad-suite", dev.root / "oss-cad-suite")
    _symlink(tools / "ffmpeg" / "bin" / "ffmpeg", FFMPEG)
    _symlink(tools / "vgacap-src", dev.vgacap_src)
    _symlink(tools / "vgacap-build", dev.vgacap_build)
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "HARNESS_VERSION").write_text(HARNESS_VERSION + "\n")
    (root / "overrides").mkdir()

    frames = tmp / "frames"
    frames.mkdir()
    (frames / ".ttvga-frames-root").write_text("")
    staging = tmp / "staging"
    staging.mkdir()
    (root / "host.toml").write_text(f'frames_root = "{frames}"\nstaging_dir = "{staging}"\n')

    targets = []
    for v in sorted(DESIGNS.glob("*.v")):
        repo = tmp / "repos" / v.stem
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        targets.append(_target(v.stem, repo, _commit(repo, v.read_text(), f"{v.stem}")))
    (root / "targets.json").write_text(json.dumps({"targets": targets}, indent=2) + "\n")
    return root


def frames_root(root: Path) -> Path:
    return root.parent / "frames"


def published(root: Path, design: str) -> Path:
    return frames_root(root) / SHUTTLE / macro_for(design)


def work(root: Path, design: str) -> Path:
    return root / "work" / SHUTTLE / macro_for(design)


def change_design(root: Path, design: str, verilog: str) -> str:
    """Commit new Verilog for `design` and point its target at the new commit; return the commit."""
    path = root / "targets.json"
    data = json.loads(path.read_text())
    (t,) = [t for t in data["targets"] if t["id"] == target_id(design)]
    t["commit"] = _commit(Path(t["repo"].removeprefix("file://")), verilog, f"{design} changed")
    path.write_text(json.dumps(data, indent=2) + "\n")
    return t["commit"]


def set_override(root: Path, design: str, override: dict) -> None:
    """Write the compiled override `overrides/<shuttle>/<macro>.json`."""
    path = root / "overrides" / SHUTTLE / f"{macro_for(design)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(override, indent=2) + "\n")
