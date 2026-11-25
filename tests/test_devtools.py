# SPDX-License-Identifier: Apache-2.0
"""The local dev-tools layout and the `require` check used by sim tests."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from ttvga import devtools

ROOT = Path(__file__).resolve().parent.parent


def test_paths_follow_the_env(tmp_path, monkeypatch):
    root = tmp_path / "dt"
    monkeypatch.setenv("TTVGA_DEV_TOOLS", str(root))
    p = devtools.paths()
    assert p.root == root
    assert p.verilator == root / "oss-cad-suite" / "bin" / "verilator"
    assert p.fst2vcd == root / "oss-cad-suite" / "bin" / "fst2vcd"
    assert p.vgacap_src == root / "vgacap-src"
    assert p.vgacap_build == root / "vgacap-build"
    assert p.ffmpeg_sink == ROOT / "tests" / "sim" / "ffmpeg_sink"


def test_paths_default_is_tmp_dev_tools(monkeypatch):
    monkeypatch.delenv("TTVGA_DEV_TOOLS", raising=False)
    assert devtools.paths().root == ROOT / "tmp" / "dev-tools"


def test_require_checks_only_named_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("TTVGA_DEV_TOOLS", str(tmp_path))
    p = devtools.paths()
    p.verilator.parent.mkdir(parents=True)
    p.verilator.write_text("")
    p.require("verilator")
    with pytest.raises(pytest.fail.Exception, match="tracetool") as e:
        p.require("tracetool")
    assert "uv run tt-vga dev-tools" in str(e.value)
    with pytest.raises(ValueError):
        p.require("nonsense")


def test_ffmpeg_sink_is_executable_and_silent():
    sink = devtools.paths().ffmpeg_sink
    assert sink.stat().st_mode & 0o111
    assert sink.read_text().splitlines() == ["#!/bin/sh", "exec cat > /dev/null"]


def test_pytest_basetemp_is_in_tmp():
    opts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    assert "--basetemp=tmp/pytest" in opts["addopts"]
    assert "-m 'not sim'" in opts["addopts"]
    assert any(m.startswith("sim:") for m in opts["markers"])
