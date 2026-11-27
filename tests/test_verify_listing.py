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

from tests.frames_txt import to_pre_xxh3, write_frames_txt  # noqa: E402

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


def test_server_listing_hrefs_it_cannot_read():
    page = autoindex("d/", files=["a.txt"]).replace(
        '<a href="a.txt">', '<a href="?C=N;O=D">Name</a> <a href="./b:c.txt">b:c.txt</a> '
        '<a href="x:y">x:y</a> <a href="/abs">abs</a> <a href="a.txt">')
    dropped: list[str] = []
    dirs, files = verify.server_listing(BASE, "d/", fetch=fake_fetch({BASE + "d/": page}), dropped=dropped)
    # A name nginx writes behind ./ is read; a bare scheme-like href and an absolute link are not.
    assert files == {"a.txt", "b:c.txt"} and dirs == set()
    assert dropped == ["d/x:y", "d//abs"]


def test_stale_on_server_walks_below_unlisted_and_server_only_roots(tmp_path):
    local = tmp_path / "archive"
    sampler = local / "frames" / "tt05" / "tt_um_a" / "centre-v1"
    (sampler / "png").mkdir(parents=True)
    (sampler / "index.html").write_text("<html></html>")
    (sampler / "png" / "000000.png").write_bytes(b"p")
    (local / "tt05" / "tt_um_a").mkdir(parents=True)
    (local / "tt05" / "tt_um_a" / "same.bin").write_bytes(b"b")
    page = "<html><head><title>tt-vga</title></head><body>a page</body></html>"
    pages = {
        BASE + "frames/": autoindex("frames/", dirs=["tt05"]),
        BASE + "frames/tt05/": autoindex("frames/tt05/", dirs=["tt_um_a"]),
        BASE + "frames/tt05/tt_um_a/": autoindex("frames/tt05/tt_um_a/", dirs=["centre-v1"]),
        BASE + "frames/tt05/tt_um_a/centre-v1/": page,
        BASE + "frames/tt05/tt_um_a/centre-v1/png/": autoindex(
            "frames/tt05/tt_um_a/centre-v1/png/", files=["000000.png", "000001.png"]),
        BASE + "tt05/": autoindex("tt05/", dirs=["tt_um_a"]),
        # A bitstream of the same name as a local file, another one, and one a level deeper: only the last
        # is outside FOREIGN_PATTERNS.
        BASE + "tt05/tt_um_a/": autoindex("tt05/tt_um_a/", dirs=["old"], files=["same.bin", "other.bin"]),
        BASE + "gone/": autoindex("gone/", files=["x.mp4"]),
    }
    unlisted: list[str] = []
    stale = verify.stale_on_server(local, BASE, ["frames/", "gone/", "tt05/"], fetch=fake_fetch(pages),
                                   unlisted=unlisted)
    assert unlisted == ["frames/tt05/tt_um_a/centre-v1/"]
    # Below the unlisted sampler directory, png/ is walked; the server-only root is one stale entry.
    assert stale == ["frames/tt05/tt_um_a/centre-v1/png/000001.png", "gone/", "tt05/tt_um_a/old/"]


def test_top_level_hrefs():
    page = ('<html><head><title>t</title></head><body><a href="tt05/tt_um_a/x_60s.mp4">a</a>'
            '<a href="./ttsky25a/tt_um_b/">b</a><a href="https://example.org/x/y">c</a>'
            '<a href="#tt05-tt_um_a">d</a><a href="index.json">e</a><a href="../up/z">f</a></body></html>')
    assert verify.top_level_hrefs(BASE, fetch=fake_fetch({BASE: page})) == {"tt05/", "ttsky25a/"}


def test_server_stale_prints_what_it_cannot_see(tmp_path, capsys):
    import argparse
    local = tmp_path / "archive"
    (local / "tt05" / "tt_um_a").mkdir(parents=True)
    (local / "tt05" / "tt_um_a" / "a_60s.mp4").write_bytes(b"m")
    sampler = local / "frames" / "tt05" / "tt_um_a" / "centre-v1"
    sampler.mkdir(parents=True)
    (sampler / "index.html").write_text("<html></html>")
    top = ('<html><head><title>tt-vga</title></head><body><a href="tt05/tt_um_a/a_60s.mp4">a</a>'
           '<a href="old/tt_um_z/z.mp4">z</a></body></html>')
    pages = {
        BASE: top,
        BASE + "frames/": autoindex("frames/", dirs=["tt05"]),
        BASE + "frames/tt05/": autoindex("frames/tt05/", dirs=["tt_um_a"]),
        BASE + "frames/tt05/tt_um_a/": autoindex("frames/tt05/tt_um_a/", dirs=["centre-v1"]),
        BASE + "frames/tt05/tt_um_a/centre-v1/": top,
        BASE + "tt05/": autoindex("tt05/", dirs=["tt_um_a"]),
        BASE + "tt05/tt_um_a/": autoindex("tt05/tt_um_a/", files=["a_60s.mp4", "x:y"]),
        BASE + "old/": autoindex("old/", dirs=["tt_um_z"]),
    }
    args = argparse.Namespace(server_stale=BASE.rstrip("/"), archive=local, root=None)
    assert verify.server_stale(args, fetch=fake_fetch(pages)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"walked 3 top-level directories of {BASE} against {local} (1 linked from the top page only)"
    assert f"  the files at the top of {BASE} (it serves index.html, not a listing)" in out
    assert "  the files directly in frames/tt05/tt_um_a/centre-v1/ (it serves its own index.html)" in out
    assert "  an href the listing cannot read: 'tt05/tt_um_a/x:y'" in out
    assert out[-2:] == ["  old/", "1 stale"]


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
        ff = write_frames_txt(framesfile, d / s / "frames.txt", pid, s, f"{stem}_{s}_frames.rgb6.zst", distinct)
        # The hash files vgacap-sample writes: XXH3-128 for both samplers, FNV for tb-v1.
        framesfile.write_hash_file(d / s / "frame_hashes.xxh3-128-rgb6.txt",
                                   framesfile.HashFile.from_frames(ff, "xxh3-128-rgb6", list(ff.distinct)))
        if s == "tb-v1":
            framesfile.write_hash_file(
                d / s / "frame_hashes.fnv1a64-tb2026-rgb888.txt",
                framesfile.HashFile.from_frames(ff, "fnv1a64-tb2026-rgb888", [f"{k:016x}" for k in range(distinct)]))
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
