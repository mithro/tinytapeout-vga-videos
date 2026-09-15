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

# Clicking a poster swaps in the animation and starts it; clicking again puts
# the still back, so a page of 400 posters never loads 400 animations at once.
PLAY_SCRIPT = """<script>
document.addEventListener('click', function (event) {
  var button = event.target.closest('button.play');
  if (!button) return;
  var img = button.querySelector('img');
  var playing = button.classList.toggle('playing');
  var badge = button.querySelector('.badge');
  img.onerror = function () {                 // no animation for this one
    img.onerror = null;
    img.src = button.dataset.poster;
    button.classList.remove('playing');
    badge.textContent = 'no preview';
  };
  // A fresh query string restarts an animation that has already played.
  img.src = playing ? button.dataset.gif + '?' + Date.now() : button.dataset.poster;
  badge.textContent = playing ? 'stop' : 'play';
});
</script>"""


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


def count(n: float | None) -> str:
    """A big number in words a reader can hold: 660 billion, 1.2 trillion."""
    n = n or 0
    if n >= 1e12:
        return f"{n / 1e12:.2g} trillion"
    if n >= 1e9:
        return f"{n / 1e9:.0f} billion"
    if n >= 1e6:
        return f"{n / 1e6:.0f} million"
    return f"{n:.0f}"


def size(n: int | None) -> str:
    if not n:
        return ""
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    return f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n / 1e3:.0f} kB"


def tally(values) -> list[tuple[str, int]]:
    """Count values, most common first, skipping the ones nothing has."""
    counts: dict[str, int] = {}
    for v in values:
        if v in (None, "", 0):
            continue
        counts[str(v)] = counts.get(str(v), 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def stats(entries: list[dict]) -> dict:
    """Figures worth knowing about the whole set: what was made, and what it cost."""
    videos = [e for e in entries if e["has_video"]]
    byte_total = sum(f.get("bytes") or 0 for e in entries for f in e["video"].get("files", {}).values())
    seconds = [e["video"]["seconds"] for e in videos if e["video"].get("seconds")]
    deltas = sorted(e["video"]["mean_frame_delta"] for e in videos
                    if e["video"].get("mean_frame_delta") is not None)
    wall = [e["simulation"]["wall_seconds"] for e in entries if (e["simulation"] or {}).get("wall_seconds")]
    clocks = [e["simulation"]["clocks"] for e in entries if (e["simulation"] or {}).get("clocks")]
    rates = sorted(e["simulation"]["clocks_per_wall_second"] for e in entries
                   if (e["simulation"] or {}).get("clocks_per_wall_second"))

    def median(xs):
        return xs[len(xs) // 2] if xs else None

    def liveliest(n=10):
        ranked = sorted(videos, key=lambda e: -(e["video"].get("mean_frame_delta") or 0))
        return [{"id": e["id"], "title": e["title"], "motion": e["video"]["mean_frame_delta"],
                 "ever": e["video"].get("pixels_ever_changed"), "colours": e["video"].get("colours")}
                for e in ranked[:n]]

    def slowest(n=10):
        ranked = sorted((e for e in entries if (e["simulation"] or {}).get("wall_seconds")),
                        key=lambda e: -e["simulation"]["wall_seconds"])
        return [{"id": e["id"], "title": e["title"], "wall_seconds": e["simulation"]["wall_seconds"],
                 "clocks_per_wall_second": e["simulation"].get("clocks_per_wall_second")}
                for e in ranked[:n]]

    return {
        "projects": len(entries),
        "with_video": len(videos),
        "verdicts": dict(tally(e["verdict"] for e in entries)),
        "shuttles": dict(tally(e["shuttle"] for e in entries)),
        "video_bytes": byte_total,
        "video_seconds": round(sum(seconds), 1),
        "modes": dict(tally(e["video"].get("mode") for e in videos)),
        "resolutions": dict(tally(f'{e["video"].get("width")}x{e["video"].get("height")}' for e in videos)),
        "frame_rates": dict(tally(round(e["video"]["fps"]) for e in videos if e["video"].get("fps"))),
        "clocks_per_pixel": dict(tally(e["video"].get("clocks_per_pixel") for e in videos)),
        "colours": dict(tally(e["video"].get("colours") for e in videos)),
        "sync_polarity": dict(tally(
            ("hsync low" if e["video"].get("hsync_active_low") else "hsync high") +
            (", vsync low" if e["video"].get("vsync_active_low") else ", vsync high") for e in videos)),
        "design_clock_hz": dict(tally(e["clock_hz"] for e in entries)),
        "tiles": dict(tally(e["tiles"] for e in entries)),
        "languages": dict(tally(e["language"] for e in entries)),
        "motion": {
            "median": median(deltas),
            "still": sum(1 for d in deltas if d == 0),
            "under_0.1_percent": sum(1 for d in deltas if 0 < d < 0.001),
            "over_1_percent": sum(1 for d in deltas if d > 0.01),
        },
        "helped_by": {
            "probed_input": sum(1 for e in entries if (e["simulation"] or {}).get("auto_ui_in") is not None),
            "qspi_memory": sum(1 for e in entries if (e["simulation"] or {}).get("qspi")),
            "input_script": sum(1 for e in entries if ((e["simulation"] or {}).get("override") or {}).get("inputs")),
            "gamepad_script": sum(1 for e in entries if ((e["simulation"] or {}).get("override") or {}).get("gamepad")),
        },
        "simulation": {
            "wall_seconds_total": round(sum(wall)),
            "wall_seconds_median": median(sorted(wall)),
            "clocks_total": sum(clocks),
            "clocks_per_wall_second_median": median(rates),
        },
        "liveliest": liveliest(),
        "slowest": slowest(),
    }


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


def bars(title: str, counts: dict, limit: int = 8, unit: str = "") -> str:
    """A small labelled bar chart, widest value first."""
    items = list(counts.items())[:limit]
    if not items:
        return ""
    top = max(n for _, n in items)
    rows = "".join(
        f'<tr><th>{html.escape(str(k))}{unit}</th><td class="num">{n}</td>'
        f'<td class="bar"><span style="width:{100 * n / top:.1f}%"></span></td></tr>'
        for k, n in items)
    return f'<section class="stat"><h3>{html.escape(title)}</h3><table class="chart">{rows}</table></section>'


def write_stats_html(s: dict) -> str:
    sim = s["simulation"]
    m = s["motion"]
    helped = s["helped_by"]
    hours = sim["wall_seconds_total"] / 3600
    facts = [
        ("Projects", f'{s["projects"]}'),
        ("With video", f'{s["with_video"]}'),
        ("Video", f'{size(s["video_bytes"])} in {s["video_seconds"] / 60:.0f} minutes of footage'),
        ("Simulated", f'{count(sim["clocks_total"])} clock cycles'),
        ("Machine time", f"{hours:.0f} hours, median {sim['wall_seconds_median'] / 60:.0f} minutes per project"),
        ("Speed", f'{(sim["clocks_per_wall_second_median"] or 0) / 1e6:.1f} million cycles per second, median'),
        ("Motion", f'median {100 * (m["median"] or 0):.3g}% of pixels change per frame; '
                   f'{m["over_1_percent"]} clips change more than 1%, {m["still"]} not at all'),
        ("Needed help", f'{helped["probed_input"]} a probed input, {helped["input_script"]} an input script, '
                        f'{helped["gamepad_script"]} a gamepad, {helped["qspi_memory"]} a modelled memory'),
    ]
    out = ['<section id="stats"><h2>Statistics</h2><table class="facts">']
    out += [f"<tr><th>{html.escape(k)}</th><td>{v}</td></tr>" for k, v in facts]
    out.append("</table><div class=\"charts\">")
    out.append(bars("Video mode", s["modes"]))
    out.append(bars("Frame rate", s["frame_rates"], unit=" fps"))
    out.append(bars("Colours used", s["colours"]))
    out.append(bars("Design clock", {f"{int(k) / 1e6:g} MHz": v for k, v in s["design_clock_hz"].items()}))
    out.append(bars("Sync polarity", s["sync_polarity"], limit=4))
    out.append(bars("Tiles", s["tiles"], limit=6))
    out.append("</div>")
    out.append('<div class="charts">')
    out.append("<section class=\"stat\"><h3>Liveliest clips</h3><table class=\"chart\">" + "".join(
        f'<tr><th><a href="#{html.escape(e["id"].replace("/", "-"))}">{html.escape(e["title"] or e["id"])}</a></th>'
        f'<td class="num">{100 * (e["motion"] or 0):.2g}%</td></tr>' for e in s["liveliest"]) + "</table></section>")
    out.append("<section class=\"stat\"><h3>Slowest to simulate</h3><table class=\"chart\">" + "".join(
        f'<tr><th><a href="#{html.escape(e["id"].replace("/", "-"))}">{html.escape(e["title"] or e["id"])}</a></th>'
        f'<td class="num">{(e["wall_seconds"] or 0) / 60:.0f} min</td></tr>' for e in s["slowest"]) + "</table></section>")
    out.append("</div></section>")
    return "\n".join(out)


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
        ".play{display:block;padding:0;border:0;background:none;cursor:pointer;position:relative}",
        ".play .badge{position:absolute;left:.3rem;bottom:.4rem;background:rgba(28,27,46,.75);color:#fff;",
        "  border-radius:.8rem;padding:0 .4rem;font-size:.75rem;line-height:1.4}",
        ".play:hover .badge,.play:focus-visible .badge{background:#544ead}",
        ".play.playing .badge{background:#8afbfd;color:#1c1b2e}",
        ".play:focus-visible{outline:2px solid #544ead;outline-offset:2px}",
        ".frames{font-size:.8rem}",
        "td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}",
        ".v{display:inline-block;padding:.05rem .4rem;border-radius:.6rem;font-size:.85em;white-space:nowrap}",
        ".ok{background:#dcf5e3;color:#14532d}.static{background:#e8e6f6;color:#312a6d}",
        ".barely-moving{background:#fdf3d7;color:#6b4e00}.partial{background:#fdf3d7;color:#6b4e00}",
        ".bad{background:#fbe3e3;color:#7f1d1d}.skipped{background:#eee;color:#555}",
        "a{color:#544ead}", "code{font-family:ui-monospace,monospace;font-size:.9em}",
        "#stats{margin:1rem 0 2rem}",
        ".facts{max-width:60rem}.facts th{width:11rem;position:static}",
        ".charts{display:flex;flex-wrap:wrap;gap:1rem;margin-top:1rem}",
        ".stat{flex:1 1 20rem;background:#fff;border:1px solid #e7e5ee;padding:.5rem .75rem}",
        ".stat h3{font-size:.95rem;font-weight:500;margin:.25rem 0 .5rem}",
        ".chart th{background:none;font-weight:400;position:static;white-space:nowrap}",
        ".chart td,.chart th{border:0;padding:.15rem .4rem}",
        ".chart td.bar{width:60%}",
        ".chart td.bar span{display:block;height:.7rem;background:#8afbfd;border:1px solid #544ead}",
        "</style></head><body>",
        "<h1>Tiny Tapeout VGA videos</h1>",
        f'<p class="lede">Simulated output of every Tiny Tapeout project whose pinout matches the Tiny VGA Pmod. '
        f"{ok} of {len(entries)} projects have a watchable clip. Each has a 60, 30 and 10 second MJPEG at the "
        f"design's own resolution and frame rate, a poster frame and a contact sheet. Generated {generated}.</p>",
        "<p>" + " ".join(f'<span class="v {cls(v)}">{html.escape(v)} {counts[v]}</span>' for v in order) + "</p>",
        write_stats_html(stats(entries)),
    ]
    for shuttle, rows in by_shuttle.items():
        out.append(f"<h2>{html.escape(shuttle)} <small>({len(rows)} projects)</small></h2>")
        out.append("<table><tr><th>Preview</th><th>Project</th><th>Result</th><th>Video</th><th>Files</th></tr>")
        for e in rows:
            v, d = e["video"], e["video"].get("dir")
            # The poster is the still; clicking it swaps in the animation.
            preview = (f'<button class="play" type="button" data-poster="{d}/poster.png" '
                       f'data-gif="{d}/preview.gif" aria-label="Play a preview of '
                       f'{html.escape(e["title"] or e["macro"], quote=True)}">'
                       f'<img src="{d}/poster.png" alt="" loading="lazy">'
                       f'<span class="badge">play</span></button>'
                       f'<a class="frames" href="{d}/contact.png">all frames</a>') if e["has_video"] else ""
            files = " ".join(f'<a href="{d}/{n}">{n[:-4]}</a> <span class="num">{size(v["files"][n]["bytes"])}</span>'
                             for n in CLIPS if n in v["files"])
            shape = (f'{v.get("width")}&times;{v.get("height")} {v.get("mode") or ""}<br>'
                     f'{v.get("fps") or 0:.1f} fps, {v.get("seconds") or 0:.0f} s<br>'
                     f'{motion(v)} of pixels change per frame, {ever(v)} ever<br>'
                     f'{v.get("colours") or 0} colours'
                     if e["has_video"] else "")
            out.append(
                f'<tr id="{html.escape(e["id"].replace("/", "-"))}">'
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
               "Project sources and documentation belong to their authors.</p>")
    out.append(PLAY_SCRIPT)
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def cls(verdict: str) -> str:
    if verdict in ("ok", "static", "barely-moving", "partial", "skipped"):
        return verdict
    return "bad"


def write_markdown(entries: list[dict], generated: str) -> str:
    s = stats(entries)
    sim = s["simulation"]
    top = lambda d, n=4: ", ".join(f"{k} ({v})" for k, v in list(d.items())[:n])  # noqa: E731
    lines = ["# Videos", "",
             f"Generated {generated} by `tt-vga index`. Do not edit by hand.", "",
             "## Statistics", "",
             f'- Projects: {s["projects"]}, with video: {s["with_video"]}',
             f'- Footage: {size(s["video_bytes"])} holding {s["video_seconds"] / 60:.0f} minutes',
             f'- Simulated: {count(sim["clocks_total"])} clock cycles in '
             f'{sim["wall_seconds_total"] / 3600:.0f} hours of machine time',
             f'- Speed: {(sim["clocks_per_wall_second_median"] or 0) / 1e6:.1f} million cycles per second (median), '
             f'{sim["wall_seconds_median"] / 60:.0f} minutes per project (median)',
             f'- Motion: median {100 * (s["motion"]["median"] or 0):.3g}% of pixels change per frame; '
             f'{s["motion"]["over_1_percent"]} clips change more than 1%, {s["motion"]["still"]} not at all',
             f'- Modes: {top(s["modes"])}',
             f'- Frame rates: {top({k + " fps": v for k, v in s["frame_rates"].items()})}',
             f'- Design clocks: {top({f"{int(k) / 1e6:g} MHz": v for k, v in s["design_clock_hz"].items()})}',
             f'- Helped by: {s["helped_by"]["probed_input"]} a probed input, '
             f'{s["helped_by"]["input_script"]} an input script, {s["helped_by"]["gamepad_script"]} a gamepad, '
             f'{s["helped_by"]["qspi_memory"]} a modelled memory',
             "",
             "## Projects", "",
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
    INDEX_JSON.write_text(json.dumps({"generated": generated, "count": len(entries),
                                      "stats": stats(entries), "projects": entries}, indent=2) + "\n")
    INDEX_HTML.write_text(write_html(entries, generated))
    VIDEOS_MD.write_text(write_markdown(entries, generated))
    with_video = sum(1 for e in entries if e["has_video"])
    print(f"{len(entries)} projects, {with_video} with video -> "
          f"{INDEX_JSON.relative_to(ROOT)}, {INDEX_HTML.relative_to(ROOT)}, {VIDEOS_MD.relative_to(ROOT)}")
    if args.upload:
        from ttvga.remote import REMOTE_VIDEOS, resolve_host, rsync

        host = resolve_host(args.host)
        rsync(host, [str(INDEX_HTML), str(INDEX_JSON)], f"{REMOTE_VIDEOS}/")
        print(f"uploaded to {host.ssh}:{REMOTE_VIDEOS}/")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("index", help="list every project and its video (JSON, HTML and Markdown)")
    p.add_argument("--upload", action="store_true", help="copy the index next to the videos on the host")
    p.add_argument("--host", help="user@host, or a name from the local config file")
    p.set_defaults(func=run)
