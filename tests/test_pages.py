# SPDX-License-Identifier: Apache-2.0
"""pages: the per-sampler index.html, from a frames.txt read by vgacap's own reader."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from ttvga import devtools
from ttvga.harness import pages, vgacap_path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "frames"


@pytest.fixture(scope="module")
def framesfile():
    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    from vgacap import framesfile

    return framesfile


def load(framesfile, name):
    return framesfile.read_frames_txt(FIXTURES / name / "frames.txt")


def rows(html: str) -> list[list[str]]:
    body = re.search(r'<table id="frames">(.*?)</table>', html, re.S).group(1)
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if cells:
            out.append(cells)
    return out


def test_page_has_no_script_and_links_every_distinct_png(framesfile, tmp_path):
    ff = load(framesfile, "glitch")
    pages.write_sampler_page(tmp_path, ff, "test_glitch", "centre-v1")
    html = (tmp_path / "index.html").read_text()
    assert "<script" not in html.lower()
    assert not re.search(r"\son[a-z]+\s*=", html, re.I)
    assert (tmp_path / "index.html").read_bytes() == html.encode("utf-8")
    for n in range(len(ff.distinct)):
        assert f'href="png/{n}.png"' in html
        assert f'<img loading="lazy" src="png/{n}.png"' in html
    assert html.count("<img ") == len(ff.distinct)
    # Three views by :target, pixelated.
    for view in ("1x", "2x", "4x"):
        assert f'id="{view}"' in html and f'href="#{view}"' in html
        assert f'[id="{view}"]:target' in html
    assert "image-rendering: pixelated" in html
    # Deterministic: a second write is byte-identical.
    again = tmp_path / "again"
    again.mkdir()
    pages.write_sampler_page(again, ff, "test_glitch", "centre-v1")
    assert (again / "index.html").read_bytes() == (tmp_path / "index.html").read_bytes()


def test_page_rows_are_runs_and_cover_every_frame(framesfile, tmp_path):
    ff = load(framesfile, "glitch")
    assert any(f.distinct < 0 for f in ff.frames)
    pages.write_sampler_page(tmp_path, ff, "test_glitch", "centre-v1")
    html = (tmp_path / "index.html").read_text()
    got = rows(html)
    want = framesfile.runs(ff.frames)
    assert len(got) == len(want)
    expect_next = 0
    for cells, (first, count, d, start, _missing) in zip(got, want):
        assert cells[0] == f"{first}-{first + count - 1}"
        assert first == expect_next
        expect_next = first + count
        if d is None:
            assert cells[1:] == ["-", "-"]
        else:
            assert cells[1] == str(start)
            assert cells[2] == f'<a href="png/{d}.png">{d}</a>'
    assert expect_next == len(ff.frames)
    # Every frame number is findable by its range; the page says it chose one row per run.
    assert "one row per run of identical frames" in html


def test_single_frame_run_is_still_first_dash_last(framesfile, tmp_path):
    ff = load(framesfile, "bars640")
    pages.write_sampler_page(tmp_path, ff, "test_bars640", "centre-v1")
    got = rows((tmp_path / "index.html").read_text())
    assert got[0][0] == f"0-{framesfile.runs(ff.frames)[0][1] - 1}"


def test_page_escapes_text_and_makes_dir(framesfile, tmp_path):
    ff = load(framesfile, "bars640")
    ff.id = "a<b>&c"
    out = tmp_path / "new" / "dir"
    pages.write_sampler_page(out, ff, "s<tem", "centre-v1")
    html = (out / "index.html").read_text()
    assert "a<b>" not in html and "a&lt;b&gt;&amp;c" in html
    assert "s<tem" not in html


def test_multi_frame_runs_are_one_row_with_a_range(framesfile, tmp_path):
    base = load(framesfile, "glitch")
    fc = 420000
    spec = [0, 0, 0, -1, -1, 1, 1, 2]
    frames = [framesfile.Frame(d, 1000 + k * fc if d >= 0 else 0) for k, d in enumerate(spec)]
    ff = dataclasses.replace(base, frames=frames, distinct=base.distinct[:3])
    assert ff.frame_clocks == fc
    pages.write_sampler_page(tmp_path, ff, "synthetic", "centre-v1")
    got = rows((tmp_path / "index.html").read_text())
    assert [c[0] for c in got] == ["0-2", "3-4", "5-6", "7-7"]
    assert [c[1] for c in got] == ["1000", "-", str(1000 + 5 * fc), str(1000 + 7 * fc)]
    assert [c[2] for c in got][1] == "-"
