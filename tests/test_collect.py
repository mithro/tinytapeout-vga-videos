# SPDX-License-Identifier: Apache-2.0
"""`tt-vga collect`: what comes into git from the host's work tree, with real rsync between two trees.

The host side is `tmp/pytest/.../host/work`, laid out as `~/ttvga/work` is; the
local side is a `data/results` stand-in. The listing script is the one collect
runs on the host, run here under bash with this interpreter.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from ttvga import HARNESS_DIR, remote

LIST_RESULTS = HARNESS_DIR / "list_results.py"
FNV = "frame_hashes.fnv1a64-tb2026-rgb888.txt"
NEW = {"id": "tt05/tt_um_a", "harness": "0123456789abcdef",
       "tb_v1": {"state": "stale", "trace_sha": None, "dropped": False}}


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def listing(work: Path) -> remote.HostListing:
    script = remote.listing_script(sys.executable, str(work), str(LIST_RESULTS))
    p = subprocess.run(["bash", "-s"], input=script, text=True, capture_output=True, check=True)
    return remote.parse_listing(p.stdout)


def collect(work: Path, results: Path) -> tuple[remote.HostListing, list[Path]]:
    found = listing(work)
    pulled = remote.pull_results(str(work) + "/", results, found, None)
    assert pulled.rejected == []
    return found, pulled.removed


def trees(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "host" / "work"
    results = tmp_path / "local" / "results"
    work.mkdir(parents=True)
    results.mkdir(parents=True)
    return work, results


def test_collect_filter_ignores_scratch_and_old_results(tmp_path):
    work, results = trees(tmp_path)
    # A running job: its scratch frames.txt, and the old pipeline's result.json still in place.
    put(work / "tt05/tt_um_a/scratch/centre-v1/frames.txt", "scratch\n")
    put(work / "tt05/tt_um_a/kept/centre-v1/frames.txt", "kept\n")
    put(work / "tt05/tt_um_a/result.json",
        json.dumps({"id": "tt05/tt_um_a", "timing": {"frame_hashes": ["00", "11"]}}))
    local = put(results / "tt05/tt_um_a/result.json", json.dumps({"id": "tt05/tt_um_a", "converted": True}))
    # A finished new-pipeline job beside it.
    put(work / "tt05/tt_um_b/result.json", json.dumps(NEW | {"id": "tt05/tt_um_b"}))
    put(work / "tt05/tt_um_b/frames/centre-v1/frames.txt", "b\n")
    found, _ = collect(work, results)
    assert found.new_results == {"tt05/tt_um_b"}
    paths = remote.collect_filter(found)
    assert paths == ["tt05/tt_um_b/frames/centre-v1/frames.txt", "tt05/tt_um_b/result.json"]
    assert not any("scratch" in p or "kept" in p for p in paths)
    assert json.loads(local.read_text()) == {"id": "tt05/tt_um_a", "converted": True}
    assert not (results / "tt05/tt_um_a/scratch").exists()
    assert not (results / "tt05/tt_um_a/kept").exists()
    assert (results / "tt05/tt_um_b/frames/centre-v1/frames.txt").read_text() == "b\n"
    assert json.loads((results / "tt05/tt_um_b/result.json").read_text())["harness"] == NEW["harness"]


def test_collect_never_removes_tb_v1_without_drop(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    put(work / "tt05/tt_um_a/frames/centre-v1/frames.txt", "centre\n")
    # The host has no frames/tb-v1/ (a default run); git has the converted file.
    converted = put(results / "tt05/tt_um_a/frames/tb-v1/" / FNV, "converted\n")
    stale_centre = put(results / "tt05/tt_um_a/frames/centre-v1/old.txt", "old\n")
    found, removed = collect(work, results)
    assert found.dropped == set()
    assert converted.read_text() == "converted\n"
    assert removed == [stale_centre]
    assert not stale_centre.exists()
    assert (results / "tt05/tt_um_a/frames/centre-v1/frames.txt").read_text() == "centre\n"


def test_collect_removes_tb_v1_after_drop(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json",
        json.dumps(NEW | {"tb_v1": {"state": "none", "trace_sha": None, "dropped": True}}))
    put(work / "tt05/tt_um_a/frames/centre-v1/frames.txt", "centre\n")
    fnv = put(results / "tt05/tt_um_a/frames/tb-v1/" / FNV, "converted\n")
    txt = put(results / "tt05/tt_um_a/frames/tb-v1/frames.txt", "tb\n")
    found, removed = collect(work, results)
    assert found.dropped == {"tt05/tt_um_a"}
    assert sorted(removed) == sorted([fnv, txt])
    assert not (results / "tt05/tt_um_a/frames/tb-v1").exists()
    assert (results / "tt05/tt_um_a/frames/centre-v1/frames.txt").exists()


def test_collect_leaves_out_testpatterns(tmp_path):
    work, results = trees(tmp_path)
    put(work / "testpatterns/tt_um_bars/result.json", json.dumps(NEW | {"id": "testpatterns/tt_um_bars"}))
    put(work / "testpatterns/tt_um_bars/frames/centre-v1/frames.txt", "bars\n")
    put(work / "testpatterns/tt_um_bars/frames/tb-v1/" / FNV, "bars\n")
    found, removed = collect(work, results)
    assert remote.collect_filter(found) == []
    assert removed == []
    assert not (results / "testpatterns").exists()


def test_collect_ignores_frames_named_files_in_repo(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    put(work / "tt05/tt_um_a/repo/x/frames/centre-v1/frames.txt", "deep\n")
    put(work / "tt05/tt_um_a/repo/frames/centre-v1/frames.txt", "depth 6\n")
    put(work / "tt05/tt_um_a/build/frames/centre-v1/frames.txt", "build\n")
    put(work / "tt05/repo/frames/centre-v1/frames.txt", "depth 5, not a project\n")
    put(work / "tt05/tt_um_a/frames/centre-v1/notes.txt", "not a collected name\n")
    put(work / "tt05/tt_um_a/frames/tb-v1/TRACE_SHA256", "ab" * 32 + "\n")
    put(work / "tt05/tt_um_a/frames/other-v1/frames.txt", "unknown sampler\n")
    found, _ = collect(work, results)
    assert all(p.count("/") == 4 for files in found.frames_files.values() for p in files)
    assert remote.collect_filter(found) == ["tt05/tt_um_a/result.json"]
    assert sorted(str(p.relative_to(results)) for p in results.rglob("*") if p.is_file()) == [
        "tt05/tt_um_a/result.json"]


def test_list_results_parses_json(tmp_path):
    work, _ = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json",
        json.dumps({"id": "tt05/tt_um_a", "sim_log_tail": 'saw "harness": "x" and "dropped": true'}))
    put(work / "tt05/tt_um_b/result.json", json.dumps(NEW | {"id": "tt05/tt_um_b"}))
    put(work / "tt05/tt_um_c/result.json", '{"harness": "cut off')
    p = subprocess.run([sys.executable, str(LIST_RESULTS), str(work)], text=True, capture_output=True)
    lines = [json.loads(line) for line in p.stdout.splitlines()]
    assert lines[:2] == [{"id": "tt05/tt_um_a", "harness": False, "dropped": False},
                         {"id": "tt05/tt_um_b", "harness": True, "dropped": False}]
    assert lines[2]["id"] == "tt05/tt_um_c" and "error" in lines[2]
    assert "tt05/tt_um_c" in p.stderr
    found = remote.parse_listing(p.stdout + remote.LISTING_MARK + "\n")
    assert found.new_results == {"tt05/tt_um_b"}
    assert found.errors == [lines[2]]


def test_collect_no_longer_imports_framehashes():
    assert importlib.util.find_spec("ttvga.framehashes") is None
    assert "framehashes" not in Path(remote.__file__).read_text()
    assert not hasattr(remote, "framehashes")


def test_collect_newline_named_directory_injects_nothing(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    put(work / "tt05/tt_um_a/frames/centre-v1/frames.txt", "a\n")
    put(work / "tt05/tt_um_b/result.json", json.dumps(NEW | {"id": "tt05/tt_um_b"}))
    put(work / "tt05/tt_um_b/frames/centre-v1/frames.txt", "b\n")
    # With newline-separated output this would list tt05/tt_um_a/frames/tb-v1/frames.txt.
    put(work / "zz\ntt05/tt_um_a/frames/tb-v1/frames.txt", "fake\n")
    script = remote.listing_script(sys.executable, str(work), str(LIST_RESULTS))
    raw = subprocess.run(["bash", "-s"], input=script, text=True, capture_output=True, check=True).stdout
    assert "zz" not in raw   # the host's find leaves it out
    found, _ = collect(work, results)
    assert remote.collect_filter(found) == [
        "tt05/tt_um_a/frames/centre-v1/frames.txt", "tt05/tt_um_a/result.json",
        "tt05/tt_um_b/frames/centre-v1/frames.txt", "tt05/tt_um_b/result.json"]
    assert not (results / "tt05/tt_um_a/frames/tb-v1").exists()
    assert (results / "tt05/tt_um_b/frames/centre-v1/frames.txt").read_text() == "b\n"
    # parse_listing drops such a path as well, should one reach it.
    text = json.dumps({"id": "tt05/tt_um_a", "harness": True, "dropped": False}) + "\n" + remote.LISTING_MARK + \
        "\nzz\ntt05/tt_um_a/frames/tb-v1/frames.txt\0tt05/tt_um_a/frames/centre-v1/frames.txt\0"
    assert remote.parse_listing(text).frames_files == {"tt05/tt_um_a": {"tt05/tt_um_a/frames/centre-v1/frames.txt"}}


def test_collect_missing_listed_file_is_not_fatal(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    put(work / "tt05/tt_um_b/result.json", json.dumps(NEW | {"id": "tt05/tt_um_b"}))
    found = listing(work)
    (work / "tt05/tt_um_a/result.json").unlink()   # a job started on the host after the listing
    pulled = remote.pull_results(str(work) + "/", results, found, None)
    assert pulled.rejected == []
    assert (results / "tt05/tt_um_b/result.json").exists()


def test_collect_never_copies_symlinks(tmp_path):
    work, results = trees(tmp_path)
    secret = put(tmp_path / "host" / "secret.txt", "secret\n")
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    link = work / "tt05/tt_um_a/frames/centre-v1/frames.txt"
    link.parent.mkdir(parents=True)
    link.symlink_to(secret)
    # find -type f leaves the symlink out of the listing; a forged listing still gets nothing across.
    found = listing(work)
    assert found.frames_files == {}
    found.frames_files = {"tt05/tt_um_a": {"tt05/tt_um_a/frames/centre-v1/frames.txt"}}
    pulled = remote.pull_results(str(work) + "/", results, found, None)
    dest = results / "tt05/tt_um_a/frames/centre-v1/frames.txt"
    assert not dest.is_symlink() and not dest.exists()
    assert pulled.rejected == []


def test_pull_rejects_a_non_regular_destination(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    put(work / "tt05/tt_um_a/frames/centre-v1/frames.txt", "a\n")
    found = listing(work)
    # A symlink already in the local tree where a collected file goes is deleted and reported.
    dest = results / "tt05/tt_um_a/frames/centre-v1/frames.txt"
    dest.parent.mkdir(parents=True)
    (work / "tt05/tt_um_a/frames/centre-v1/frames.txt").unlink()
    dest.symlink_to(tmp_path / "elsewhere")
    pulled = remote.pull_results(str(work) + "/", results, found, None)
    assert pulled.rejected == [dest]
    assert not dest.is_symlink()


def test_list_results_never_opens_a_symlink_or_fifo(tmp_path):
    import os
    work, _ = trees(tmp_path)
    target = put(tmp_path / "other.json", json.dumps(NEW))
    (work / "tt05/tt_um_a").mkdir(parents=True)
    (work / "tt05/tt_um_a/result.json").symlink_to(target)
    (work / "tt05/tt_um_b").mkdir(parents=True)
    os.mkfifo(work / "tt05/tt_um_b/result.json")
    p = subprocess.run([sys.executable, str(LIST_RESULTS), str(work)], text=True, capture_output=True, timeout=30)
    lines = [json.loads(line) for line in p.stdout.splitlines()]
    assert [x["id"] for x in lines] == ["tt05/tt_um_a", "tt05/tt_um_b"]
    assert all("not a regular file" in x["error"] for x in lines)


def test_remove_stale_frames_skips_a_symlinked_sampler_directory(tmp_path):
    work, results = trees(tmp_path)
    put(work / "tt05/tt_um_a/result.json", json.dumps(NEW))
    outside = put(tmp_path / "outside" / "keep.txt", "keep\n")
    (results / "tt05/tt_um_a/frames").mkdir(parents=True)
    (results / "tt05/tt_um_a/frames/centre-v1").symlink_to(outside.parent)
    found, removed = collect(work, results)
    assert removed == []
    assert outside.read_text() == "keep\n"
