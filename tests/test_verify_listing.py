# SPDX-License-Identifier: Apache-2.0
"""verify.py: the server's autoindex listings, the stale-file walk, and the frames subtree checks."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

import verify  # noqa: E402

import pytest  # noqa: E402

from tests.frames_txt import framesfile, to_pre_xxh3, write_frames_txt  # noqa: E402, F401

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = "https://example.org/archive/"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def autoindex(path: str, dirs=(), files=()) -> str:
    """An nginx autoindex page in the shape of the saved fixture."""
    rows = [f'<a href="{d}/">{d}/</a>                     26-Nov-2026 12:48       -' for d in dirs]
    rows += [f'<a href="{f}">{f}</a>                     26-Nov-2026 12:48    102K' for f in files]
    return (f"<html>\n<head><title>Index of /archive/{path}</title></head>\n<body>\n"
            f'<h1>Index of /archive/{path}</h1><hr><pre><a href="../">../</a>\n'
            + "\n".join(rows) + "\n</pre><hr></body>\n</html>\n")


def fake_fetch(pages: dict[str, str]):
    def fetch(url, timeout=None):
        if url not in pages:
            raise AssertionError(f"unexpected fetch {url}")
        return _Response(pages[url].encode())
    return fetch


def test_server_listing_parses_autoindex():
    page = (FIXTURES / "autoindex-tt05of-tt_um_dinogame.html").read_text()
    url = BASE + "tt05of/tt_um_dinogame/"
    dirs, files = verify.server_listing(BASE, "tt05of/tt_um_dinogame/", fetch=fake_fetch({url: page}))
    assert dirs == set()
    assert "tt05of_dinogame-dc03d0ecd3a2.bin" in files
    assert "tt05of_tt_um_dinogame_60s.mp4" in files and "tt05of_tt_um_dinogame_preview.gif" in files
    assert len(files) == 10 and ".." not in files and "../" not in files
    # A directory is listed by its name, without the slash.
    dirs, files = verify.server_listing(BASE, "tt05of/", fetch=fake_fetch(
        {BASE + "tt05of/": autoindex("tt05of/", dirs=["tt_um_dinogame"], files=["x%20y.txt"])}))
    assert dirs == {"tt_um_dinogame"} and files == {"x y.txt"}


def test_stale_on_server_ignores_bin_and_library(tmp_path):
    local = tmp_path / "archive"
    clip = local / "tt05of" / "tt_um_dinogame"
    clip.mkdir(parents=True)
    (clip / "tt05of_tt_um_dinogame_60s.mp4").write_bytes(b"x")
    (local / "frames" / "tt05of").mkdir(parents=True)
    pages = {
        BASE + "tt05of/": autoindex("tt05of/", dirs=["tt_um_dinogame", "tt_um_gone"]),
        BASE + "tt05of/tt_um_dinogame/": autoindex("tt05of/tt_um_dinogame/", files=[
            "tt05of_tt_um_dinogame_60s.mp4", "tt05of_dinogame-dc03d0ecd3a2.bin", "tt05of_tt_um_dinogame_old.avi"]),
        BASE + "frames/": autoindex("frames/", dirs=["tt05of"], files=["fpga-library.json"]),
        BASE + "frames/tt05of/": autoindex("frames/tt05of/"),
        BASE: autoindex("", dirs=["tt05of", "frames"], files=["fpga-library.json", "index.json"]),
    }
    fetch = fake_fetch(pages)
    stale = verify.stale_on_server(local, BASE, ["tt05of/", "frames/"], fetch=fetch)
    # The bitstream belongs to the FPGA session; a stale directory is listed once.
    assert stale == ["frames/fpga-library.json", "tt05of/tt_um_dinogame/tt05of_tt_um_dinogame_old.avi",
                     "tt05of/tt_um_gone/"]
    # The library is foreign only at the archive root.
    assert verify.stale_on_server(local, BASE, [""], fetch=fetch) == [
        "frames/fpga-library.json", "index.json",
        "tt05of/tt_um_dinogame/tt05of_tt_um_dinogame_old.avi", "tt05of/tt_um_gone/"]


# ---------------------------------------------------------------------------
# The frames subtree on the host
# ---------------------------------------------------------------------------

SHA = "ab" * 32


def project(framesfile, frames_root: Path, work: Path, pid: str, *, distinct: int = 2, pngs: int | None = None,
            result: dict | None = None, samplers=("centre-v1",), trace: bytes = b"trace") -> Path:
    shuttle, macro = pid.split("/")
    stem = f"{shuttle}_{macro}"
    d = frames_root / shuttle / macro
    d.mkdir(parents=True)
    if trace is not None:
        (d / f"{stem}_trace.vgch.zst").write_bytes(trace)
    for s in samplers:
        (d / s / "png").mkdir(parents=True)
        write_frames_txt(framesfile, d / s / "frames.txt", pid, s, f"{stem}_{s}_frames.rgb6.zst", distinct)
        (d / s / "index.html").write_text("<html></html>\n")
        (d / s / f"{stem}_{s}_frames.rgb6.zst").write_bytes(b"z")
        for n in range(distinct if pngs is None else pngs):
            (d / s / "png" / f"{n:06d}.png").write_bytes(b"png")
    base = {"id": pid, "published": True, "error": None, "test_hooks": False,
            "tb_v1": {"state": "none", "trace_sha": None, "dropped": False}}
    (work / pid).mkdir(parents=True)
    (work / pid / "result.json").write_text(json.dumps({**base, **(result or {})}))
    return d


def test_verify_frames_completeness(framesfile, tmp_path):
    root, work = tmp_path / "frames", tmp_path / "work"
    project(framesfile, root, work, "tt06/tt_um_good", samplers=("centre-v1", "tb-v1"))
    project(framesfile, root, work, "tt06/tt_um_fewpngs", distinct=3, pngs=2)
    project(framesfile, root, work, "tt06/tt_um_notrace", trace=None)
    project(framesfile, root, work, "tt06/tt_um_emptytrace", trace=b"")
    d = project(framesfile, root, work, "tt06/tt_um_nopage")
    (d / "centre-v1" / "index.html").unlink()
    d = project(framesfile, root, work, "tt06/tt_um_nostore")
    (d / "centre-v1" / "tt06_tt_um_nostore_centre-v1_frames.rgb6.zst").unlink()
    d = project(framesfile, root, work, "tt06/tt_um_noframes")
    (d / "centre-v1" / "frames.txt").unlink()
    project(framesfile, root, work, "tt06/tt_um_nopicture", distinct=0)
    failures, notes = verify.check_frames(root, work, framesfile)
    assert notes == []
    assert failures == [
        "tt06/tt_um_emptytrace: trace tt06_tt_um_emptytrace_trace.vgch.zst is empty",
        "tt06/tt_um_fewpngs: centre-v1: 2 PNGs, distinct_frames is 3",
        "tt06/tt_um_noframes: centre-v1: frames.txt missing",
        "tt06/tt_um_nopage: centre-v1: index.html missing",
        "tt06/tt_um_nostore: centre-v1: tt06_tt_um_nostore_centre-v1_frames.rgb6.zst missing",
        "tt06/tt_um_notrace: trace tt06_tt_um_notrace_trace.vgch.zst missing",
    ]


def test_verify_stale_tb_v1_is_a_note(framesfile, tmp_path):
    root, work = tmp_path / "frames", tmp_path / "work"
    project(framesfile, root, work, "tt06/tt_um_a", result={"tb_v1": {"state": "stale", "trace_sha": SHA, "dropped": False}})
    project(framesfile, root, work, "tt06/tt_um_b", result={"tb_v1": {"state": "stale", "trace_sha": None, "dropped": False}})
    project(framesfile, root, work, "tt06/tt_um_c", result={"tb_v1": {"state": "current", "trace_sha": SHA, "dropped": False}})
    failures, notes = verify.check_frames(root, work, framesfile)
    assert failures == []
    assert notes == [
        f"tt06/tt_um_a: tb-v1 files are from trace {SHA[:12]}, not the current trace",
        "tt06/tt_um_b: tb-v1 files are from trace before traces, not the current trace",
    ]


def test_verify_failed_project_is_a_failure(framesfile, tmp_path):
    root, work = tmp_path / "frames", tmp_path / "work"
    project(framesfile, root, work, "tt06/tt_um_a", result={"published": False, "error": "build failed: exit 2"})
    # Published with an error (an encode failure) is not a failed project.
    project(framesfile, root, work, "tt06/tt_um_b", result={"published": True, "error": "encode: ffmpeg exit 1"})
    failures, notes = verify.check_frames(root, work, framesfile)
    assert failures == ["tt06/tt_um_a: failed (previous output kept): build failed: exit 2"]
    assert notes == []


def test_verify_test_hooks_is_a_failure(framesfile, tmp_path):
    root, work = tmp_path / "frames", tmp_path / "work"
    project(framesfile, root, work, "tt06/tt_um_a", result={"test_hooks": True})
    failures, _ = verify.check_frames(root, work, framesfile)
    assert failures == ["tt06/tt_um_a: built with test hooks"]


def test_verify_refuses_a_pre_xxh3_frames_txt_and_hash_file(framesfile, tmp_path):
    root, work = tmp_path / "frames", tmp_path / "work"
    d = project(framesfile, root, work, "tt06/tt_um_old", samplers=("centre-v1", "tb-v1"))
    txt = d / "tb-v1" / "frames.txt"
    txt.write_text(to_pre_xxh3(txt.read_text()))
    (d / "centre-v1" / "frame_hashes.sha256-rgb6.txt").write_text(
        "hash_method: sha256-rgb6\n# SHA-256 of the frame as rgb6\n")
    failures, _ = verify.check_frames(root, work, framesfile)
    assert len(failures) == 2, failures
    assert failures[0].startswith("tt06/tt_um_old: centre-v1: frame_hashes.sha256-rgb6.txt: ")
    assert failures[1].startswith("tt06/tt_um_old: tb-v1: frames.txt: ")
    assert "sha256" in failures[0] and "sha256" in failures[1]
