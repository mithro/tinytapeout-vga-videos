# SPDX-License-Identifier: Apache-2.0
"""job.build links tb.cpp with vgacap's trace writer (vgacap_link_flags)."""

import sys
from pathlib import Path

import pytest

from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

import job  # noqa: E402

LIBS = ("libvgacap_trace.a", "libvgacap_stream.a", "third_party/libvgacap_zstd.a")


def fake_vgacap(root: Path, missing: str | None = None) -> tuple[Path, Path]:
    src, build = root / "vgacap-src", root / "vgacap-build"
    (src / "include").mkdir(parents=True)
    for lib in LIBS:
        if lib != missing:
            (build / lib).parent.mkdir(parents=True, exist_ok=True)
            (build / lib).write_bytes(b"")
    return src, build


def fake_project(root: Path) -> tuple[dict, Path]:
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "project.v").write_text("module tt_um_x (); endmodule\n")
    return {"source_files": ["project.v"], "top_module": "tt_um_x"}, repo


def test_vgacap_link_flags(tmp_path):
    src, build = fake_vgacap(tmp_path)
    assert job.vgacap_link_flags(src, build) == [
        "-CFLAGS", f"-I{src}/include",
        "-LDFLAGS", f"{build}/libvgacap_trace.a {build}/libvgacap_stream.a "
                    f"{build}/third_party/libvgacap_zstd.a -pthread",
    ]


@pytest.mark.parametrize("lib", LIBS)
def test_vgacap_link_flags_names_a_missing_library(tmp_path, lib):
    src, build = fake_vgacap(tmp_path, missing=lib)
    with pytest.raises(FileNotFoundError, match=str(build / lib)):
        job.vgacap_link_flags(src, build)


def test_build_command_has_the_vgacap_flags(tmp_path, monkeypatch):
    src, build = fake_vgacap(tmp_path)
    target, repo = fake_project(tmp_path)
    cmds = []
    monkeypatch.setattr(job, "run", lambda cmd, log, **kw: cmds.append(cmd) or 1)
    log = tmp_path / "build.log"
    log.write_text("")
    error = job.build(target, {}, repo, tmp_path / "build", log, {"verilator": "verilator"}, src, build)
    assert error == "verilator failed"   # the fake run fails; only the command matters
    (cmd,) = cmds
    flags = job.vgacap_link_flags(src, build)
    i = cmd.index("-LDFLAGS")
    assert cmd[i - 2:i + 2] == flags
    assert cmd.index(str(job.TB_CPP)) > i
    assert "-DTTVGA_TEST_HOOKS" not in cmd


def test_build_refuses_without_vgacap(tmp_path, monkeypatch):
    src, build = fake_vgacap(tmp_path, missing="libvgacap_trace.a")
    target, repo = fake_project(tmp_path)
    monkeypatch.setattr(job, "run", lambda *a, **kw: pytest.fail("verilator must not run"))
    error = job.build(target, {}, repo, tmp_path / "build", tmp_path / "build.log", {"verilator": "v"}, src, build)
    assert error == f"vgacap library missing: {build / 'libvgacap_trace.a'}"
