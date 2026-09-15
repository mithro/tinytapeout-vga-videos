# SPDX-License-Identifier: Apache-2.0
"""`tt-vga index`: list every project and what came out of its simulation.

Three files are produced from `data/targets.json` and the collected results:

- `data/index.json`, one record per project: who wrote it, where the source
  is, what the simulation measured, and the name, size and checksum of each
  video file. This is the machine-readable form for anything built later.
- `data/index.html`, a page that lists the projects with their poster
  images and links to the clips. It uses paths relative to itself, so
  dropping it at the root of the video directory (`--upload`) makes that
  directory browsable, and it keeps working if the directory is later
  served over HTTP.
- `docs/videos.md`, the same list as a table, so the repository alone says
  what exists without fetching 200 GB of video.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone

from ttvga import DATA_DIR, ROOT
from ttvga.analyze import SUCCESS, analyze_all
from ttvga.report import VERDICT_ORDER
from ttvga.targets import load_targets

INDEX_JSON = DATA_DIR / "index.json"
INDEX_HTML = DATA_DIR / "index.html"
VIDEOS_MD = ROOT / "docs" / "videos.md"
PROJECT_URL = "https://tinytapeout.com/chips/{shuttle}/{macro}"
CLIPS = ("60s.avi", "30s.avi", "10s.avi")


def record(target: dict, result: dict | None) -> dict:
    """One project's entry: what it is, what was simulated, what came out."""
    timing = (result or {}).get("timing") or {}
    videos = (result or {}).get("videos") or {}
    frames, fps = timing.get("frames"), timing.get("fps")
    entry = {
        "id": target["id"],
        "shuttle": target["shuttle"],
        "macro": target["macro"],
        "title": target["title"],
        "author": target["author"],
        "address": target["address"],
        "tiles": target["tiles"],
        "language": target["language"],
        "repo": target["repo"],
        "commit": target["commit"],
        "page": PROJECT_URL.format(**target),
        "clock_hz": target["clock_hz"],
        "pmods": target["pmods"],
        "verdict": (result or {}).get("verdict", "pending"),
        "reason": (result or {}).get("reason", ""),
        "has_video": bool(videos),
        "video": {
            "dir": f"{target['shuttle']}/{target['macro']}",
            "files": {name: {"bytes": v.get("bytes"), "sha256": v.get("sha256")}
                      for name, v in sorted(videos.items())},
            "mode": timing.get("mode"),
            "width": timing.get("width"),
            "height": timing.get("height"),
            "fps": round(fps, 3) if fps else None,
            "seconds": round(frames / fps, 2) if frames and fps else None,
            "frames": frames,
            "distinct_frames": timing.get("distinct_frames"),
            "colours": timing.get("colours"),
            "mean_frame_delta": timing.get("mean_frame_delta"),
            "pixels_ever_changed": timing.get("pixels_ever_changed"),
            "hsync_active_low": timing.get("hsync_active_low"),
            "vsync_active_low": timing.get("vsync_active_low"),
            "line_clocks": timing.get("line_clocks"),
            "lines": timing.get("lines"),
            "clocks_per_pixel": timing.get("clocks_per_pixel"),
        },
        "simulation": {
            "clock_hz": timing.get("clock_hz"),
            "clocks": timing.get("clocks_simulated"),
            "wall_seconds": timing.get("wall_seconds"),
            "clocks_per_wall_second": timing.get("clocks_per_wall_second"),
            "auto_ui_in": (result or {}).get("auto_ui_in"),
            "qspi": (result or {}).get("qspi"),
            "override": (result or {}).get("override"),
            "host": (result or {}).get("host"),
            "finished": (result or {}).get("finished"),
            "tools": (result or {}).get("tools"),
        },
    }
    if not entry["has_video"]:
        entry["video"] = {"dir": entry["video"]["dir"], "files": {}}
    return entry


def size(n: int | None) -> str:
    if not n:
        return ""
    return f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n / 1e3:.0f} kB"


def motion(v: dict) -> str:
    """Share of pixels that change from one frame to the next, e.g. "0.004%"."""
    d = v.get("mean_frame_delta")
    if d is None:
        return ""
    if d == 0:
        return "0%"
    return f"{100 * d:.3g}%"


def ever(v: dict) -> str:
    """Share of pixels that change at any point in the clip."""
    e = v.get("pixels_ever_changed")
    return f"{100 * e:.3g}%" if e is not None else ""


def write_html(entries: list[dict], generated: str) -> str:
    by_shuttle: dict[str, list[dict]] = {}
    for e in entries:
        by_shuttle.setdefault(e["shuttle"], []).append(e)
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["verdict"]] = counts.get(e["verdict"], 0) + 1
    ok = sum(n for v, n in counts.items() if v in SUCCESS)
    order = [v for v in VERDICT_ORDER if counts.get(v)] + sorted(set(counts) - set(VERDICT_ORDER))

    out = [
        "<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Tiny Tapeout VGA videos</title>", "<style>",
        "body{font:14px/1.5 system-ui,sans-serif;margin:0;padding:1.5rem;background:#faf9fb;color:#1c1b2e}",
        "h1{font-weight:400;font-size:1.6rem;margin:0 0 .25rem}",
        "h2{font-weight:500;font-size:1.1rem;margin:2rem 0 .5rem;position:sticky;top:0;background:#faf9fb;padding:.4rem 0}",
        "p.lede{color:#555;margin:.25rem 0 1rem;max-width:60rem}",
        "table{border-collapse:collapse;width:100%;margin-bottom:1rem;background:#fff}",
        "th,td{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #e7e5ee;vertical-align:top}",
        "th{font-weight:500;color:#555;background:#f2f1f6;position:sticky;top:2.6rem}",
        "img{display:block;width:160px;height:auto;border:1px solid #e7e5ee;background:#000}",
        "td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}",
        ".v{display:inline-block;padding:.05rem .4rem;border-radius:.6rem;font-size:.85em;white-space:nowrap}",
        ".ok{background:#dcf5e3;color:#14532d}.static{background:#e8e6f6;color:#312a6d}",
        ".barely-moving{background:#fdf3d7;color:#6b4e00}.partial{background:#fdf3d7;color:#6b4e00}",
        ".bad{background:#fbe3e3;color:#7f1d1d}.skipped{background:#eee;color:#555}",
        "a{color:#544ead}", "code{font-family:ui-monospace,monospace;font-size:.9em}",
        "</style></head><body>",
        "<h1>Tiny Tapeout VGA videos</h1>",
        f'<p class="lede">Simulated output of every Tiny Tapeout project whose pinout matches the Tiny VGA Pmod. '
        f"{ok} of {len(entries)} projects have a watchable clip. Each has a 60, 30 and 10 second MJPEG at the "
        f"design's own resolution and frame rate, a poster frame and a contact sheet. Generated {generated}.</p>",
        "<p>" + " ".join(f'<span class="v {cls(v)}">{html.escape(v)} {counts[v]}</span>' for v in order) + "</p>",
    ]
    for shuttle, rows in by_shuttle.items():
        out.append(f"<h2>{html.escape(shuttle)} <small>({len(rows)} projects)</small></h2>")
        out.append("<table><tr><th>Preview</th><th>Project</th><th>Result</th><th>Video</th><th>Files</th></tr>")
        for e in rows:
            v, d = e["video"], e["video"].get("dir")
            preview = f'<a href="{d}/contact.png"><img src="{d}/poster.png" alt="" loading="lazy"></a>' if e["has_video"] else ""
            files = " ".join(f'<a href="{d}/{n}">{n[:-4]}</a> <span class="num">{size(v["files"][n]["bytes"])}</span>'
                             for n in CLIPS if n in v["files"])
            shape = (f'{v.get("width")}&times;{v.get("height")} {v.get("mode") or ""}<br>'
                     f'{v.get("fps") or 0:.1f} fps, {v.get("seconds") or 0:.0f} s<br>'
                     f'{motion(v)} of pixels change per frame, {ever(v)} ever<br>'
                     f'{v.get("colours") or 0} colours'
                     if e["has_video"] else "")
            out.append(
                "<tr>"
                f"<td>{preview}</td>"
                f'<td><strong>{html.escape(e["title"] or e["macro"])}</strong><br>{html.escape(e["author"] or "")}<br>'
                f'<code>{html.escape(e["macro"])}</code><br>'
                f'<a href="{html.escape(e["page"])}">chip page</a> &middot; '
                f'<a href="{html.escape(e["repo"])}">source</a></td>'
                f'<td><span class="v {cls(e["verdict"])}">{html.escape(e["verdict"])}</span><br>'
                f'<small>{html.escape(e["reason"])}</small></td>'
                f"<td>{shape}</td>"
                f"<td>{files}</td>"
                "</tr>")
        out.append("</table>")
    out.append("<p>Made by <a href=\"https://github.com/mithro/tinytapeout-vga-videos\">tinytapeout-vga-videos</a>. "
               "Project sources and documentation belong to their authors.</p></body></html>")
    return "\n".join(out) + "\n"


def cls(verdict: str) -> str:
    if verdict in ("ok", "static", "barely-moving", "partial", "skipped"):
        return verdict
    return "bad"


def write_markdown(entries: list[dict], generated: str) -> str:
    lines = ["# Videos", "",
             f"Generated {generated} by `tt-vga index`. Do not edit by hand.", "",
             "One row per project. The clips themselves are on the simulation host under",
             "`videos/<shuttle>/<macro>/`; this table says what each one contains.", "",
             "Motion is the share of pixels that change from one frame to the next;",
             "ever is the share that change at any point in the clip.", "",
             "| Project | Title | Verdict | Size | fps | Motion | Ever | Colours | 60 s file |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for e in entries:
        v = e["video"]
        shape = f'{v.get("width")}x{v.get("height")}' if e["has_video"] else ""
        fps = f'{v.get("fps"):.1f}' if e["has_video"] and v.get("fps") else ""
        clip = size((v.get("files", {}).get("60s.avi") or {}).get("bytes"))
        title = (e["title"] or "").replace("|", "/")[:60]
        lines.append(f'| `{e["id"]}` | {title} | {e["verdict"]} | {shape} | {fps} | {motion(v)} | {ever(v)} | '
                     f'{v.get("colours") or ""} | {clip} |')
    return "\n".join(lines) + "\n"


def build() -> list[dict]:
    results = {r["id"]: r for r in analyze_all()}
    return [record(t, results.get(t["id"])) for t in load_targets()]


def run(args: argparse.Namespace) -> int:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entries = build()
    INDEX_JSON.write_text(json.dumps({"generated": generated, "count": len(entries), "projects": entries},
                                     indent=2) + "\n")
    INDEX_HTML.write_text(write_html(entries, generated))
    VIDEOS_MD.write_text(write_markdown(entries, generated))
    with_video = sum(1 for e in entries if e["has_video"])
    print(f"{len(entries)} projects, {with_video} with video -> "
          f"{INDEX_JSON.relative_to(ROOT)}, {INDEX_HTML.relative_to(ROOT)}, {VIDEOS_MD.relative_to(ROOT)}")
    if args.upload:
        from ttvga.remote import REMOTE_ROOT, resolve_host, rsync

        host = resolve_host(args.host)
        rsync(host, [str(INDEX_HTML), str(INDEX_JSON)], f"{REMOTE_ROOT}/videos/")
        print(f"uploaded to {host.ssh}:{REMOTE_ROOT}/videos/")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("index", help="list every project and its video (JSON, HTML and Markdown)")
    p.add_argument("--upload", action="store_true", help="copy the index next to the videos on the host")
    p.add_argument("--host", help="user@host, or a name from the local config file")
    p.set_defaults(func=run)
