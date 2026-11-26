# SPDX-License-Identifier: Apache-2.0
"""The per-sampler index.html: every captured frame by range, and the distinct frames as images.

Standard library only. frames.txt is read by vgacap's own `framesfile` (put on sys.path by
`vgacap_path`, which the caller does first); this module takes the `FramesFile` it returns and
groups frames with vgacap's `framesfile.runs`. The page is a pure function of its inputs: no
dates, no scripts, so a re-run writes identical bytes.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

_CSS = """\
body { font-family: sans-serif; margin: 1rem; }
nav a { margin-right: 1rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid #888; padding: 0.15rem 0.6rem; text-align: right; }
.grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.grid figure { margin: 0; }
.grid figcaption { font-size: 0.8rem; }
main img { image-rendering: pixelated; display: block; width: %(w)dpx; height: auto; }
[id="1x"]:target ~ main img { width: %(w1)dpx; }
[id="2x"]:target ~ main img { width: %(w2)dpx; }
[id="4x"]:target ~ main img { width: %(w4)dpx; }
"""


def write_sampler_page(dir: Path, ff, stem: str, sampler: str) -> None:
    """Write `dir/index.html` for one sampler's `FramesFile` `ff`; the PNGs are `dir/png/<n>.png`.

    The frame table has one row per run of identical frames (the page says so), giving the
    range as `first`-`last`; the distinct frames follow as a grid of lazily loaded images.
    """
    from vgacap import framesfile

    dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)
    runs = framesfile.runs(ff.frames, ff.frame_clocks)
    w = ff.width
    css = _CSS % {"w": w, "w1": w, "w2": 2 * w, "w4": 4 * w}
    title = escape(f"{stem} {sampler}")
    h = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title>",
        "<style>",
        css.rstrip("\n"),
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{title}</h1>",
        '<span id="1x"></span><span id="2x"></span><span id="4x"></span>',
        '<nav>View: <a href="#1x">1x</a><a href="#2x">2x</a><a href="#4x">4x</a></nav>',
        "<main>",
        "<p>"
        f"id {escape(ff.id)}; status {escape(ff.status)}; sampler status {escape(ff.sampler_status)}; "
        f"{ff.width}x{ff.height}; mode {escape(ff.mode)}; {len(ff.frames)} frames, {len(ff.distinct)} distinct."
        "</p>",
        "<h2>Frames</h2>",
        "<p>This page has one row per run of identical frames. "
        "Frames are shown as the range <code>first</code>-<code>last</code>, "
        "so every frame number is in exactly one row. "
        "A <code>-</code> is a gap: no picture was captured for those frames.</p>",
        '<table id="frames">',
        "<tr><th>Frames</th><th>Start clock</th><th>Distinct</th></tr>",
    ]
    for first, count, d, start, _missing in runs:
        if d is None:
            h.append(f"<tr><td>{first}-{first + count - 1}</td><td>-</td><td>-</td></tr>")
        else:
            h.append(f'<tr><td>{first}-{first + count - 1}</td><td>{start}</td>'
                     f'<td><a href="png/{d}.png">{d}</a></td></tr>')
    h += ["</table>", "<h2>Distinct frames</h2>", '<div class="grid">']
    for n in range(len(ff.distinct)):
        h.append(f'<figure><a href="png/{n}.png"><img loading="lazy" src="png/{n}.png" '
                 f'width="{ff.width}" height="{ff.height}" alt="distinct frame {n}"></a>'
                 f"<figcaption>{n}</figcaption></figure>")
    h += ["</div>", "</main>", "</body>", "</html>"]
    (dir / "index.html").write_bytes(("\n".join(h) + "\n").encode("utf-8"))
