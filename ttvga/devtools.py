# SPDX-License-Identifier: Apache-2.0
"""Local dev tools (Verilator, fst2vcd, vgacap) for the simulation tests, and `tt-vga dev-tools`.

The tools live under `$TTVGA_DEV_TOOLS` (default `tmp/dev-tools`), pinned by
`ttvga/tools.toml`, the same pins the host uses. Every worktree points the
variable at one shared directory so oss-cad-suite is downloaded once.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from ttvga import remote

ROOT = Path(__file__).resolve().parent.parent
ENV_VAR = "TTVGA_DEV_TOOLS"
# Names `DevTools.require` accepts: every Path field except `root`.
_NOT_TOOLS = {"root", "vgacap_src", "vgacap_build"}


@dataclass(frozen=True)
class DevTools:
    root: Path
    verilator: Path
    fst2vcd: Path
    vgacap_src: Path
    vgacap_build: Path
    vgacap_sample: Path
    vgacap_export: Path
    vgacap_dump: Path
    tracetool: Path
    ffmpeg_sink: Path

    def require(self, *names: str) -> None:
        """Fail the calling test, never skip it, if any named tool is missing."""
        import pytest

        known = {f.name for f in fields(self)} - _NOT_TOOLS
        for name in names:
            if name not in known:
                raise ValueError(f"unknown dev tool {name!r}; known: {sorted(known)}")
        missing = [n for n in names if not getattr(self, n).exists()]
        if missing:
            detail = ", ".join(f"{n} ({getattr(self, n)})" for n in missing)
            pytest.fail(f"missing dev tool(s): {detail}; run `uv run tt-vga dev-tools` first")


def paths() -> DevTools:
    root = Path(os.environ.get(ENV_VAR) or ROOT / "tmp" / "dev-tools")
    suite = root / "oss-cad-suite" / "bin"
    build = root / "vgacap-build"
    return DevTools(
        root=root,
        verilator=suite / "verilator",
        fst2vcd=suite / "fst2vcd",
        vgacap_src=root / "vgacap-src",
        vgacap_build=build,
        vgacap_sample=build / "vgacap-sample",
        vgacap_export=build / "vgacap-export",
        vgacap_dump=build / "vgacap-dump",
        tracetool=build / "tracetool",
        ffmpeg_sink=ROOT / "tests" / "sim" / "ffmpeg_sink",
    )


def install_script(tools: dict) -> str:
    """Shell script that installs oss-cad-suite and builds vgacap, run with the dev-tools root as cwd."""
    oss = tools["oss-cad-suite"]
    vg = tools["vgacap"]
    build = "\n".join(remote.vgacap_build_commands("vgacap-src", "vgacap-build", vg["commit"], vg["git"]))
    return f"""
set -e
mkdir -p dl
if [ ! -x {oss['check']} ]; then
  echo "installing oss-cad-suite {oss['version']}"
  curl -sSL -o dl/oss-cad-suite.tar {shlex.quote(oss['url'])}
  tar xf dl/oss-cad-suite.tar
  rm -f dl/oss-cad-suite.tar
else
  echo "oss-cad-suite: present"
fi
if [ -f vgacap-build/PINNED ] && [ "$(cat vgacap-build/PINNED)" = "{vg['commit']}" ]; then
  echo "vgacap: present at {vg['commit']}"
else
  echo "building vgacap {vg['commit']}"
{build}
fi
"""


def dev_tools(args: argparse.Namespace) -> int:
    tools = tomllib.loads(remote.TOOLS_TOML.read_text())
    root = paths().root
    root.mkdir(parents=True, exist_ok=True)
    return subprocess.run(["bash", "-s"], input=install_script(tools), text=True, cwd=root).returncode


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dev-tools", help="install the pinned Verilator and vgacap under $TTVGA_DEV_TOOLS")
    p.set_defaults(func=dev_tools)
