# SPDX-License-Identifier: Apache-2.0
"""Tests for ttvga.targets against small synthetic project records."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest

from ttvga import ROOT, targets

VGA_PINOUT = {
    "uo[0]": "R1", "uo[1]": "G1", "uo[2]": "B1", "uo[3]": "vsync",
    "uo[4]": "R0", "uo[5]": "G0", "uo[6]": "B0", "uo[7]": "hsync",
}
PLAIN_PINOUT = {f"uo[{i}]": f"uo_out[{i}]" for i in range(8)}


def _main_repo_root() -> Path:
    """The main checkout's root even from a worktree (git's common dir is <main>/.git)."""
    res = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                         capture_output=True, text=True)
    return Path(res.stdout.strip()).parent if res.returncode == 0 else ROOT


LOCAL_PROJECTS = Path(os.environ.get(
    "TTVGA_PROJECTS_JSON",
    _main_repo_root().parent / "tinytapeout-project-search" / "data" / "projects.json"))


def project(shuttle: str, macro: str, address: int, **extra) -> dict:
    p = {
        "shuttle": shuttle, "macro": macro, "address": address, "title": macro, "author": "a",
        "repo": f"https://github.com/x/{macro}", "commit": "abc", "top_module": macro,
        "source_files": ["project.v"], "language": "Verilog", "clock_hz": 25175000, "tiles": "1x1",
        "pinout": VGA_PINOUT, "wokwi_id": None, "description": "d", "how_it_works": "h",
    }
    p.update(extra)
    return p


def write_source(tmp_path: Path, projects: list[dict]) -> Path:
    src = tmp_path / "projects.json"
    src.write_text(json.dumps({"projects": projects}))
    return src


def run_cli(tmp_path: Path, projects: list[dict], capsys) -> tuple[dict, str]:
    src = write_source(tmp_path, projects)
    out = tmp_path / "targets.json"
    args = argparse.Namespace(source=str(src), commit=targets.PROJECTS_COMMIT, out=out, pmod="tiny-vga", extra=None)
    assert targets.run(args) == 0
    return json.loads(out.read_text()), capsys.readouterr().out


def test_filters_by_pinout_and_excludes_groups(tmp_path, capsys):
    doc, _ = run_cli(tmp_path, [
        project("tt08", "tt_um_vga", 10),
        project("tt08", "tt_um_plain", 11, pinout=PLAIN_PINOUT),
        project("tt08", "tt_um_group", 12, type="group"),
        project("tt08", "tt_um_sub", 12, type="subtile", subtile_addr=3),
    ], capsys)
    assert [t["id"] for t in doc["targets"]] == ["tt08/tt_um_vga", "tt08/tt_um_sub"]
    t = doc["targets"][0]
    assert t["pmods"] == ["tiny-vga"]
    assert t["skip"] is None
    assert t["docs"] == {"description": "d", "how_it_works": "h", "how_to_test": "", "external_hw": ""}
    assert t["address"] == "10"
    assert doc["targets"][1]["address"] == "12/3"


@pytest.mark.parametrize("extra, reason", [
    ({"language": "Analog"}, "analog project"),
    ({"wokwi_id": 414120}, "wokwi project"),
    ({"wokwi_id": "414120"}, "wokwi project"),
    ({"source_files": []}, "no source files"),
    ({"source_files": None}, "no source files"),
    ({"top_module": ""}, "no top module"),
    ({"repo": "N/A"}, "repo not on github"),
    ({"repo": "https://gitlab.com/x/y"}, "repo not on github"),
])
def test_skip_rules(tmp_path, capsys, extra, reason):
    doc, _ = run_cli(tmp_path, [project("tt08", "tt_um_x", 1, **extra)], capsys)
    assert doc["targets"][0]["skip"] == reason
    assert doc["meta"]["skipped"] == 1


def test_wokwi_zero_is_not_skipped(tmp_path, capsys):
    doc, _ = run_cli(tmp_path, [project("tt08", "a", 1, wokwi_id=0), project("tt08", "b", 2, wokwi_id="0")], capsys)
    assert [t["skip"] for t in doc["targets"]] == [None, None]


def test_repo_normalisation(tmp_path, capsys):
    doc, _ = run_cli(tmp_path, [
        project("tt08", "a", 1, repo="git@github.com:owner/repo.git"),
        project("tt08", "b", 2, repo="https://github.com/owner/repo.git"),
    ], capsys)
    assert [t["repo"] for t in doc["targets"]] == ["https://github.com/owner/repo"] * 2
    assert [t["skip"] for t in doc["targets"]] == [None, None]


def test_ordering_and_meta(tmp_path, capsys):
    doc, out = run_cli(tmp_path, [
        project("tt09", "z", 5),
        project("tt09", "a", 5),
        project("tt08", "s1", 12, type="subtile", subtile_addr=10),
        project("tt08", "s0", 12, type="subtile", subtile_addr=2),
        project("tt08", "late", 100),
        project("tt08", "early", 9, language="Analog"),
        project("tt09", "wok", 1, wokwi_id=5),
    ], capsys)
    # shuttles keep source-file order (tt09 first here), then numeric address, sub-tile, macro
    assert [t["id"] for t in doc["targets"]] == [
        "tt09/wok", "tt09/a", "tt09/z", "tt08/early", "tt08/s0", "tt08/s1", "tt08/late",
    ]
    assert doc["meta"]["count"] == 7
    assert doc["meta"]["skipped"] == 2
    assert doc["meta"]["pmod"] == "tiny-vga"
    assert doc["meta"]["commit"] is None  # local file, not the pinned download
    assert "7 targets" in out and "analog project: 1" in out and "wokwi project: 1" in out
    assert "tt08: 4" in out and "tt09: 3" in out


def test_clock_hz_defaults_to_zero(tmp_path, capsys):
    doc, out = run_cli(tmp_path, [project("tt08", "a", 1, clock_hz=None)], capsys)
    assert doc["targets"][0]["clock_hz"] == 0
    assert "clock_hz unknown (0): 1" in out


def test_load_targets_and_target_by_id(tmp_path, capsys):
    run_cli(tmp_path, [project("tt08", "a", 1)], capsys)
    loaded = targets.load_targets(tmp_path / "targets.json")
    assert targets.target_by_id(loaded, "tt08/a")["macro"] == "a"
    with pytest.raises(KeyError):
        targets.target_by_id(loaded, "tt08/missing")


@pytest.mark.skipif(not LOCAL_PROJECTS.exists(), reason="local tinytapeout-project-search checkout not found")
def test_real_projects_json(tmp_path, capsys):
    out = tmp_path / "targets.json"
    args = argparse.Namespace(source=str(LOCAL_PROJECTS), commit=targets.PROJECTS_COMMIT, out=out, pmod="tiny-vga",
                              extra=None)
    assert targets.run(args) == 0
    doc = json.loads(out.read_text())
    assert doc["meta"]["count"] >= 400
    for t in doc["targets"]:
        assert t["id"] == f"{t['shuttle']}/{t['macro']}"
        assert isinstance(t["clock_hz"], int)
        if t["skip"] is None:
            assert t["repo"].startswith("https://github.com/")
            assert t["commit"] and t["top_module"] and t["source_files"]


def extra_record(macro: str, shuttle: str = "testpatterns") -> dict:
    return {"id": f"{shuttle}/{macro}", "shuttle": shuttle, "macro": macro, "skip": None, "clock_hz": 25175000}


def run_with_extra(tmp_path: Path, capsys, extra_records: list[dict]) -> dict:
    extra = tmp_path / "extra-targets.json"
    extra.write_text(json.dumps({"targets": extra_records}))
    src = write_source(tmp_path, [project("tt08", "tt_um_vga", 10)])
    out = tmp_path / "targets.json"
    args = argparse.Namespace(source=str(src), commit=targets.PROJECTS_COMMIT, out=out, pmod="tiny-vga",
                              extra=extra)
    assert targets.run(args) == 0
    capsys.readouterr()
    return json.loads(out.read_text())


def test_extra_targets_merged(tmp_path, capsys):
    doc = run_with_extra(tmp_path, capsys, [extra_record("tt_um_vgacal_bars"), extra_record("tt_um_vgacal_grid")])
    assert [t["id"] for t in doc["targets"]] == [
        "tt08/tt_um_vga", "testpatterns/tt_um_vgacal_bars", "testpatterns/tt_um_vgacal_grid"]
    assert doc["meta"]["count"] == 3


def test_extra_target_duplicate_id_fails(tmp_path, capsys):
    with pytest.raises(ValueError, match="duplicate"):
        run_with_extra(tmp_path, capsys, [extra_record("tt_um_vga", "tt08")])
    with pytest.raises(ValueError, match="duplicate"):
        run_with_extra(tmp_path, capsys, [extra_record("a"), extra_record("a")])


def test_committed_extra_targets_are_well_formed():
    extra = json.loads((ROOT / "data" / "extra-targets.json").read_text())["targets"]
    assert len(extra) == 10
    modes = {t["macro"]: t for t in extra if t["top_module"] == "tt_um_vgacal_modes"}
    assert sorted(modes) == [f"tt_um_vgacal_modes_{m}" for m in ("m0", "m0_hneg", "m0_hvneg", "m0_vneg", "m1", "m2")]
    for t in extra:
        assert t["shuttle"] == "testpatterns" and t["clock_hz"] == 25175000
        assert t["repo"] == "https://github.com/mithro/tt-vga-testpatterns"
        assert t["src_dir"] == f"designs/{t['top_module']}/src"
        assert len(t["commit"]) == 40 and t["skip"] is None
