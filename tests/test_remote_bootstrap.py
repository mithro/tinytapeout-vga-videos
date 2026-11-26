# SPDX-License-Identifier: Apache-2.0
"""The pinned uv, Python 3.14 and vgacap bootstrap on the host, and the harness version key."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from ttvga import remote
from ttvga.harness import vgacap_path

TOOLS = tomllib.loads(remote.TOOLS_TOML.read_text())


def test_tarball_loop_skips_python_and_vgacap():
    assert set(remote.tarball_tools(TOOLS)) == {"oss-cad-suite", "ffmpeg", "uv"}


def test_bootstrap_installs_python_and_builds_vgacap_at_the_pin():
    script = remote.bootstrap_script(TOOLS)
    assert "uv python install --no-bin 3.14.7" in script
    assert TOOLS["vgacap"]["commit"] in script
    assert "-DCMAKE_BUILD_TYPE=Release" in script
    assert "PINNED" in script
    assert "--target vgacap-sample vgacap-export vgacap-dump vgacap_trace vgacap_sample" in script


def test_host_scripts_run_under_the_pinned_python():
    args = argparse.Namespace(jobs=4, seconds=60.0, timeout=1800.0, only="", limit=0, redo=False,
                              redo_unless_harness=None, rederive=False, tb_v1=False, drop_tb_v1=False,
                              yes_drop_tb_v1=False, scope_memory=None, scope_cpu=None)
    host = remote.Host(ssh="ttvga@example.invalid", jobs=4)
    cmd = remote.queue_command(args, host, TOOLS)
    assert cmd.startswith(remote.host_python(TOOLS))
    assert "~/ttvga/tools/uv/uv run --no-project --python 3.14.7 python" in cmd


def test_vgacap_commit_is_a_full_sha():
    assert re.fullmatch(r"[0-9a-f]{40}", TOOLS["vgacap"]["commit"])


def test_vgacap_path_adds_the_pinned_python(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    vgacap_path.add(tmp_path)
    assert str(tmp_path / "tools" / "vgacap-src" / "python") in sys.path
    t = vgacap_path.tools(tmp_path)
    assert set(t) == {"vgacap_sample", "vgacap_export", "vgacap_dump", "tracetool"}
    assert t["vgacap_sample"] == tmp_path / "tools" / "vgacap-build" / "vgacap-sample"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    *args], check=True, capture_output=True)


def _commit(repo: Path, rel: str, text: str) -> None:
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", f"change {rel}")


def test_harness_version_ignores_commits_elsewhere(tmp_path):
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "ttvga/harness/job.py", "a\n")
    _commit(repo, "ttvga/tools.toml", 'commit = "1"\n')
    _commit(repo, "README.md", "r\n")
    v0 = remote.harness_version(repo)
    assert re.fullmatch(r"[0-9a-f]{16}", v0)

    _commit(repo, "README.md", "r2\n")
    assert remote.harness_version(repo) == v0

    _commit(repo, "ttvga/harness/x", "x\n")
    v1 = remote.harness_version(repo)
    assert v1 != v0

    _commit(repo, "ttvga/tools.toml", 'commit = "2"\n')
    v2 = remote.harness_version(repo)
    assert v2 not in (v0, v1)

    (repo / "README.md").write_text("dirty elsewhere\n")
    assert remote.harness_version(repo) == v2
    (repo / "ttvga/harness/x").write_text("dirty\n")
    assert remote.harness_version(repo) == v2 + "-dirty"
    _git(repo, "checkout", "ttvga/harness/x")
    (repo / "ttvga/tools.toml").write_text('commit = "3"\n')
    assert remote.harness_version(repo) == v2 + "-dirty"


def test_uv_state_lives_under_ttvga_tools():
    for text in (remote.bootstrap_script(TOOLS), remote.host_python(TOOLS)):
        assert "UV_PYTHON_INSTALL_DIR=~/ttvga/tools/python" in text
        assert "UV_CACHE_DIR=~/ttvga/tools/uv-cache" in text
        assert "UV_PYTHON_BIN_DIR=~/ttvga/tools/bin" in text
    assert "uv python install --no-bin 3.14.7" in remote.bootstrap_script(TOOLS)
    py = remote.host_python(TOOLS)
    assert "UV_PYTHON_PREFERENCE=only-managed" in py
    assert "UV_PYTHON_DOWNLOADS=never" in py


def test_bootstrap_guards_on_pinned_and_clears_it_before_cmake():
    script = remote.bootstrap_script(TOOLS)
    assert f'"$(cat vgacap-build/PINNED)" = "{TOOLS["vgacap"]["commit"]}"' in script
    assert script.index("rm -f vgacap-build/PINNED") < script.index("cmake -S")


def test_host_check_reports_a_missing_interpreter(monkeypatch):
    seen = {}
    monkeypatch.setattr(remote, "resolve_host", lambda spec: remote.Host(ssh="ttvga@example.invalid"))
    monkeypatch.setattr(remote, "ssh", lambda host, script, **kw: seen.update(script=script) or subprocess.CompletedProcess([], 0))
    remote.host_check(argparse.Namespace(host=None))
    assert "uv python find 3.14.7" in seen["script"]
    assert "MISSING" in seen["script"]
    assert "loginctl show-user" in seen["script"] and "2>&1" in seen["script"]


def test_tracetool_is_built_against_the_vgacap_libraries_found_in_the_build_tree():
    cmds = "\n".join(remote.tracetool_build_commands("src", "bld", "tracetool.c"))
    assert "cc -std=c99 -O2 -Wall -Wextra -Werror -Isrc/include -Isrc/third_party/sha256" in cmds
    for lib in ("libvgacap_trace.a", "libvgacap_stream.a", "libvgacap_sha256.a", "libvgacap_zstd.a"):
        assert f"find bld -name {lib}" in cmds
    assert cmds.rstrip().endswith("-pthread -o bld/tracetool")
    assert "building tracetool" in remote.bootstrap_script(TOOLS)
    assert "-o vgacap-build/tracetool" in remote.bootstrap_script(TOOLS)
