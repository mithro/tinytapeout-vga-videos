#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that what is published is actually playable. Runs on the host.

Usage: verify.py --videos ~/public_html --root ~/ttvga [--decode 40]
       verify.py --root ~/ttvga --server-stale URL [--archive DIR]

Every check here exists because something got past the ones before it:

- a project can be missing a file, or hold one of zero bytes, when a run was
  stopped while it was being written;
- a clip can exist at a plausible size and still be truncated, so a sample is
  decoded from end to end rather than probed;
- a WebM can decode perfectly in every software player and still not play
  in Chrome on a machine with a hardware VP9 decoder, if it is full range.
  That one is checked on every file, because it is invisible otherwise;
- and a run's record can say it captured sound while the published clip is
  silent, because the encode that made the sound wrote somewhere else. The
  record is what the index believes, so the two have to be compared. The
  rate is checked with it: left to itself ffmpeg followed the 192 kHz capture
  into 96 kHz AAC, which is unusual enough that some decoders refuse it, and
  the clip plays perfectly everywhere it was tested.

The frames subtree (`frames_root` in host.toml) is checked too: each
project's trace is there and not empty, each sampler directory has its
frames.txt, index.html, store and one PNG per distinct frame, and the
project's last result.json neither failed (its previous output is still the
published one) nor was built with tb.cpp's test hooks. tb-v1 files left from
another trace are a note, never a failure.

`--server-stale URL` instead walks the server's public directory listings,
the only way to see what the upload put there, and prints what the archive no
longer has, for removal by hand. It never deletes. FOREIGN_PATTERNS are not
this pipeline's files and are never listed. It prints what it cannot see:
the files at the top, the files and server-only subdirectories directly in a
directory that serves its own index.html (its local subdirectories are walked
instead), and hrefs it cannot read.

Exits non-zero if anything fails, so it can gate a publish.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote

# As `ttvga.harness.verify` (tt-vga imports it for FOREIGN_PATTERNS) it takes its
# siblings from the package and leaves sys.path alone, so `hostconf` is loaded
# once. As a script on the host it puts its own directory on sys.path.
if __package__:
    from . import hostconf, vgacap_path
    from .encode import AUDIO_OUT_RATE, GIF_SECONDS, LENGTHS, clip_names, preview_names, stem_for
else:
    HERE = Path(__file__).resolve().parent
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import hostconf
    import vgacap_path
    from encode import AUDIO_OUT_RATE, GIF_SECONDS, LENGTHS, clip_names, preview_names, stem_for

# Files in the archive that the FPGA harness session owns (Ruling AA), relative
# to the archive root: its bitstreams `<id>-<sha256[:12]>.bin` in each
# `<shuttle>/<macro>/`, and its library file. This is the only copy of the list:
# `tt-vga mirror` excludes these, and nothing here reports them as stale.
FOREIGN_PATTERNS = ("*/*/*.bin", "fpga-library.json")

SAMPLERS = ("centre-v1", "tb-v1")


def is_foreign(rel: str) -> bool:
    """Whether a path relative to the archive root is one of FOREIGN_PATTERNS (`*` never crosses a `/`)."""
    return any(PurePosixPath(rel).full_match(p) for p in FOREIGN_PATTERNS)


# ---------------------------------------------------------------------------
# What is on the server but no longer in the archive
# ---------------------------------------------------------------------------

_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


class NotAListing(Exception):
    """The server answered a directory with something other than an autoindex page."""


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs += [v for k, v in attrs if k == "href" and v]
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def server_listing(base_url: str, path: str, fetch=urllib.request.urlopen,
                   dropped: list[str] | None = None) -> tuple[set[str], set[str]]:
    """The directory names and file names in the server's autoindex page for `path` (relative to `base_url`).

    nginx's autoindex: one `<a href>` per entry, a directory's ending in `/`. A leading `./` (written
    before a name that would read as a URL scheme) is removed. The parent link `../` and the sort links
    (`?C=N;O=D`) are skipped. Any other href that is not a single-segment name (a query, a fragment, a
    scheme, an absolute link, a `/` inside) is not taken: it is appended to `dropped` when given, as
    something the walk cannot see. A page that is not an autoindex listing (a directory with its own
    index.html) raises NotAListing.
    """
    url = base_url + quote(path)
    with fetch(url, timeout=60) as r:
        body = r.read().decode("utf-8", errors="replace")
    parser = _Links()
    parser.feed(body)
    if not parser.title.startswith("Index of "):
        raise NotAListing(f"{url} is not a directory listing (title {parser.title.strip()[:80]!r})")
    dirs, files = set(), set()
    for href in parser.hrefs:
        if href == "../" or href.startswith("?"):
            continue
        rel = href[2:] if href.startswith("./") else href
        is_dir = rel.endswith("/")
        name = unquote(rel[:-1] if is_dir else rel)
        bad = (any(c in rel for c in "?#") or rel.startswith("/") or not name or name in (".", "..")
               or "/" in name or (_SCHEME.match(rel) and not href.startswith("./")))
        if bad:
            if dropped is not None:
                dropped.append(f"{path}{href}")
            continue
        (dirs if is_dir else files).add(name)
    return dirs, files


def top_level_hrefs(base_url: str, fetch=urllib.request.urlopen) -> set[str]:
    """The first path segments of the relative links on the page at `base_url`, as `<name>/` roots.

    The archive's top is its index.html, not a listing; the directories it links to are walked too,
    so a top-level directory that is only on the server is still seen when the page links it.
    """
    with fetch(base_url, timeout=60) as r:
        body = r.read().decode("utf-8", errors="replace")
    parser = _Links()
    parser.feed(body)
    roots = set()
    for href in parser.hrefs:
        rel = href[2:] if href.startswith("./") else href
        if _SCHEME.match(rel) or rel.startswith(("/", "#", "?", "..")) or "/" not in rel:
            continue
        name = unquote(rel.split("/", 1)[0])
        if name and name not in (".", ".."):
            roots.add(name + "/")
    return roots


def stale_on_server(local: Path, base_url: str, roots, fetch=urllib.request.urlopen,
                    unlisted: list[str] | None = None, dropped: list[str] | None = None) -> list[str]:
    """Paths on the server, under each of `roots`, that `local` (the archive) no longer has. Sorted.

    `roots` are directories relative to `base_url` ("" for the top, otherwise
    ending in `/`), walked recursively. A directory missing locally is listed
    once, with its trailing `/`, and not walked; so is a root the server has and
    the archive does not. FOREIGN_PATTERNS are never listed. A directory the
    server answers with its own index.html (the local copy has one) cannot be
    listed: it is appended to `unlisted` when given, and its local
    subdirectories are walked in its place. A root, or such a subdirectory, the
    server does not have (404) has nothing stale. Hrefs the listing cannot read
    go to `dropped` (see server_listing). Never deletes.
    """
    stale: list[str] = []
    todo = list(roots)
    may_404 = set(todo)
    while todo:
        path = todo.pop()
        try:
            dirs, files = server_listing(base_url, path, fetch=fetch, dropped=dropped)
        except NotAListing:
            if (local / path / "index.html").is_file():
                if unlisted is not None:
                    unlisted.append(path)
                for sub in sorted((local / path).iterdir()):
                    if sub.is_dir() and not sub.is_symlink():
                        todo.append(f"{path}{sub.name}/")
                        may_404.add(f"{path}{sub.name}/")
                continue
            raise
        except urllib.error.HTTPError as e:
            if e.code == 404 and path in may_404:
                continue
            raise
        if path and not (local / path).is_dir():
            if not is_foreign(path[:-1]):
                stale.append(path)
            continue
        for name in files:
            rel = path + name
            if not is_foreign(rel) and not os.path.lexists(local / rel):
                stale.append(rel)
        for name in dirs:
            rel = path + name + "/"
            if (local / rel).is_dir():
                todo.append(rel)
            elif not is_foreign(rel[:-1]):
                stale.append(rel)
    return sorted(stale)


# ---------------------------------------------------------------------------
# The frames subtree: complete, and what the last run of each project says
# ---------------------------------------------------------------------------

def check_frames(frames_root: Path, work: Path, framesfile) -> tuple[list[str], list[str]]:
    """(failures, notes) for every project directory `<frames_root>/<shuttle>/<macro>/`.

    `work` is the host's `<root>/work`, which holds each project's result.json.
    `framesfile` is vgacap's reader module: every frames.txt and hash file is read with it, so a
    pre-XXH3 file fails here with vgacap's own message.
    """
    failures: list[str] = []
    notes: list[str] = []
    for d in sorted(p for p in frames_root.glob("*/*") if p.is_dir() and not p.is_symlink()):
        pid = f"{d.parent.name}/{d.name}"
        stem = stem_for(d.parent.name, d.name)
        trace = d / f"{stem}_trace.vgch.zst"
        if not trace.is_file():
            failures.append(f"{pid}: trace {trace.name} missing")
        elif trace.stat().st_size == 0:
            failures.append(f"{pid}: trace {trace.name} is empty")
        samplers = [s for s in SAMPLERS if (d / s).is_dir()]
        if not samplers:
            failures.append(f"{pid}: no sampler directory")
        for s in samplers:
            store = f"{stem}_{s}_frames.rgb6.zst"
            missing = [n for n in ("frames.txt", "index.html", store) if not (d / s / n).is_file()]
            for n in missing:
                failures.append(f"{pid}: {s}: {n} missing")
            if "frames.txt" in missing:
                continue
            try:
                distinct = len(framesfile.read_frames_txt(d / s / "frames.txt").distinct)
            except (OSError, ValueError) as e:
                failures.append(f"{pid}: {s}: frames.txt: {e}")
                distinct = None
            for hf in sorted((d / s).glob("frame_hashes.*.txt")):
                try:
                    framesfile.read_hash_file(hf)
                except (OSError, ValueError) as e:
                    failures.append(f"{pid}: {s}: {hf.name}: {e}")
            pngs = len(list((d / s / "png").glob("*.png"))) if (d / s / "png").is_dir() else 0
            if distinct is not None and pngs != distinct:
                failures.append(f"{pid}: {s}: {pngs} PNGs, distinct_frames is {distinct}")

        result_path = work / pid / "result.json"
        if not result_path.is_file():
            continue
        try:
            result = json.loads(result_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            failures.append(f"{pid}: result.json does not parse: {e}")
            continue
        if not result.get("published") and result.get("error"):
            failures.append(f"{pid}: failed (previous output kept): {result['error']}")
        if result.get("test_hooks"):
            failures.append(f"{pid}: built with test hooks")
        tb = result.get("tb_v1") or {}
        if tb.get("state") == "stale":
            sha = tb.get("trace_sha")
            notes.append(f"{pid}: tb-v1 files are from trace {sha[:12] if sha else 'before traces'}, "
                         "not the current trace")
    return failures, notes


def probe(ffprobe: str, path: Path, entries: str, stream: str = "v:0") -> str:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", stream,
                          "-show_entries", entries, "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return out.stdout.strip()


def claims_audio(root: Path, name: str) -> bool:
    """Whether this project's own record says the run captured its sound."""
    result = root / "work" / name / "result.json"
    if not result.exists():
        return False
    try:
        timing = (json.loads(result.read_text()).get("timing") or {})
    except (json.JSONDecodeError, OSError):
        return False
    return bool(timing.get("audio_driven")) and bool(timing.get("audio_samples"))


def decodes(ffmpeg: str, path: Path) -> tuple[bool, str]:
    """Decode every frame and throw it away: catches truncation a probe misses."""
    p = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True)
    return p.returncode == 0, p.stderr.strip()[:160]


def projects(videos: Path) -> list[tuple[str, str, Path]]:
    out = []
    for d in sorted(videos.glob("*/*")):
        if d.is_dir():
            out.append((f"{d.parent.name}/{d.name}", stem_for(d.parent.name, d.name), d))
    return out


def server_stale(args: argparse.Namespace, fetch=None) -> int:
    """`--server-stale URL`: print what the server holds that the archive does not. Deletes nothing.

    It also prints what it cannot see: the files at the top (served as index.html, not a listing),
    the files and server-only subdirectories directly in each directory that serves its own
    index.html, and hrefs it cannot read.
    """
    fetch = fetch or urllib.request.urlopen
    base = args.server_stale if args.server_stale.endswith("/") else args.server_stale + "/"
    local = args.archive
    if local is None:
        try:
            local = hostconf.load(args.root).frames_root.parent
        except (hostconf.ConfigError, OSError) as e:
            print(f"verify: --server-stale needs the archive: {e}", file=sys.stderr)
            return 1
    # The archive's top is its own index.html, not a listing: each top-level directory, local or linked
    # from the served page, is a root.
    local_roots = {d.name + "/" for d in local.iterdir() if d.is_dir() and not d.is_symlink()}
    roots = sorted(local_roots | top_level_hrefs(base, fetch=fetch))
    unlisted: list[str] = []
    dropped: list[str] = []
    stale = stale_on_server(local, base, roots, fetch=fetch, unlisted=unlisted, dropped=dropped)
    print(f"walked {len(roots)} top-level directories of {base} against {local} "
          f"({len(roots) - len(local_roots)} linked from the top page only)")
    print("cannot see (check by hand):")
    print(f"  the files at the top of {base} (it serves index.html, not a listing)")
    for path in sorted(unlisted):
        print(f"  the files and server-only subdirectories directly in {path} (it serves its own index.html)")
    for href in sorted(dropped):
        print(f"  an href the listing cannot read: {href!r}")
    print("stale on server (remove by hand):")
    for path in stale:
        print(f"  {path!r}" if not path.isprintable() else f"  {path}")
    print(f"{len(stale)} stale")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, default=Path.home() / "public_html")
    ap.add_argument("--root", type=Path, default=Path.home() / "ttvga")
    ap.add_argument("--decode", type=int, default=40, help="how many projects to decode in full (0 to skip)")
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--server-stale", metavar="URL",
                    help="only list what the server at URL (the archive's public listings) has that the archive "
                         "no longer has, for removal by hand")
    ap.add_argument("--archive", type=Path,
                    help="with --server-stale: the local archive (default: frames_root's parent, from host.toml)")
    args = ap.parse_args()

    if args.server_stale:
        return server_stale(args)

    bin_dir = args.root / "tools" / "ffmpeg" / "bin"
    ffmpeg, ffprobe = str(bin_dir / "ffmpeg"), str(bin_dir / "ffprobe")
    found = projects(args.videos)
    print(f"verifying {len(found)} projects in {args.videos}")
    failures: list[str] = []

    # 1. every file present and not empty
    incomplete = 0
    for name, stem, d in found:
        want = clip_names(stem) + preview_names(stem)
        missing = [w for w in want if not (d / w).exists()]
        empty = [w for w in want if (d / w).exists() and (d / w).stat().st_size == 0]
        if missing or empty:
            incomplete += 1
            failures.append(f"{name}: missing {missing}, empty {empty}")
    print(f"  complete: {len(found) - incomplete} of {len(found)}")

    # 2. colour range on every WebM: the fault that only a hardware decoder sees
    webms = sorted(args.videos.glob("*/*/*.webm"))
    ranges: Counter = Counter()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for path, out in zip(webms, pool.map(
                lambda p: probe(ffprobe, p, "stream=color_range,color_space"), webms)):
            ranges[out] += 1
            if not out.startswith("tv"):
                failures.append(f"{path.parent.parent.name}/{path.parent.name}/{path.name}: "
                                f"colour range {out or 'unknown'}, must be limited (tv)")
    print(f"  WebM colour range: {dict(ranges)}")

    # 3. previews are the length they should be
    odd = 0
    gifs = sorted(args.videos.glob("*/*/*_preview.gif"))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for path, out in zip(gifs, pool.map(lambda p: probe(ffprobe, p, "format=duration"), gifs)):
            try:
                d = float(out)
            except ValueError:
                d = 0.0
            if not 0.5 <= d <= GIF_SECONDS + 0.5:
                odd += 1
                failures.append(f"{path.parent.parent.name}/{path.parent.name}: preview is {d:.2f}s")
    print(f"  previews the right length: {len(gifs) - odd} of {len(gifs)}")

    # 4. a sample decoded end to end, with the cuts the length they claim
    if args.decode:
        sample = random.Random(0).sample(found, min(args.decode, len(found)))

        def check(item):
            name, stem, d = item
            bad = []
            for secs in LENGTHS:
                for ext in ("mp4", "webm"):
                    f = d / f"{stem}_{secs}s.{ext}"
                    if not f.exists():
                        continue
                    ok, err = decodes(ffmpeg, f)
                    if not ok:
                        bad.append(f"{f.name} does not decode: {err}")
                        continue
                    try:
                        dur = float(probe(ffprobe, f, "format=duration"))
                    except ValueError:
                        bad.append(f"{f.name} has no duration")
                        continue
                    if secs != LENGTHS[0] and abs(dur - secs) > 0.5:
                        bad.append(f"{f.name} is {dur:.2f}s, expected {secs}s")
            return name, bad

        broken = 0
        with ThreadPoolExecutor(max_workers=max(args.jobs // 2, 1)) as pool:
            for name, bad in pool.map(check, sample):
                if bad:
                    broken += 1
                    failures.extend(f"{name}: {b}" for b in bad)
        print(f"  decoded in full: {len(sample) - broken} of {len(sample)} sampled")

    # 5. a clip whose record claims sound has to have some
    claimed = [(name, stem, d) for name, stem, d in found if claims_audio(args.root, name)]
    if claimed:
        silent = 0
        for name, stem, d in claimed:
            bad = []
            # Every length, not only the full one: the short clips are cut from
            # it with `-c copy`, which carries the audio across, but that is
            # the sort of thing a later change to the cut could quietly drop.
            for f in (d / f"{stem}_{secs}s.{ext}" for secs in LENGTHS for ext in ("mp4", "webm")):
                if not f.exists():
                    continue
                rate = probe(ffprobe, f, "stream=sample_rate", stream="a:0")
                if not rate:
                    bad.append(f"{f.name} has no audio track")
                elif rate != AUDIO_OUT_RATE:
                    bad.append(f"{f.name} is {rate} Hz, expected {AUDIO_OUT_RATE}")
            if bad:
                silent += 1
                failures.append(f"{name}: run captured audio but {'; '.join(bad)}")
        print(f"  clips with the sound their record claims: {len(claimed) - silent} of {len(claimed)}")

    # 6. the frames subtree: complete, and no project failed or built with test hooks
    notes: list[str] = []
    try:
        conf = hostconf.load(args.root)
    except (hostconf.ConfigError, OSError) as e:
        failures.append(f"frames: host.toml: {e}")
    else:
        vgacap_path.add(args.root)
        from vgacap import framesfile
        frame_failures, notes = check_frames(conf.frames_root, args.root / "work", framesfile)
        n = sum(1 for p in conf.frames_root.glob("*/*") if p.is_dir() and not p.is_symlink())
        print(f"  frames projects without a problem: {n - len({f.split(':', 1)[0] for f in frame_failures})} of {n}")
        failures.extend(frame_failures)
    if notes:
        print("\nnotes:")
        for note in notes:
            print(f"  {note}")

    if failures:
        print(f"\n{len(failures)} problems:")
        for f in failures[:30]:
            print(f"  {f}")
        if len(failures) > 30:
            print(f"  ... and {len(failures) - 30} more")
    print(f"\nVERIFIED: {'yes' if not failures else 'NO'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
