# SPDX-License-Identifier: Apache-2.0
"""`tt-vga targets`: pick the projects whose pinout matches a Pmod.

The input is `data/projects.json` from the tinytapeout-project-search
repository (one record per project across every shuttle, built from each
shuttle's `shuttle_index.json` and the projects' `info.yaml`). It is fetched
from GitHub at a pinned commit and cached under `data/cache/`, or read from a
local checkout with `--source`. Pmod compatibility is inferred from the pin
names with `ttsearch.pmods.detect_pmods`, exactly as the search site does.

The output, `data/targets.json`, keeps one record per matching project with
the fields the rest of the pipeline needs (repo, commit, sources, top module,
clock) plus a `skip` reason for projects we know we cannot simulate.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ttsearch.pmods import detect_pmods

from ttvga import DATA_DIR, TARGETS_JSON

PROJECTS_COMMIT = "be8587d67ec064ab1acd63d21cc0f9a593eb9897"
PROJECTS_URL = "https://raw.githubusercontent.com/mithro/tinytapeout-project-search/{commit}/data/projects.json"
CACHE_DIR = DATA_DIR / "cache"
USER_AGENT = "tinytapeout-vga-videos (+https://github.com/mithro/tinytapeout-vga-videos)"
GITHUB_HTTPS = "https://github.com/"
GITHUB_SSH = "git@github.com:"

Project = dict[str, Any]


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def fetch_projects(source: str, commit: str = PROJECTS_COMMIT) -> Path:
    """Return a local path to projects.json, downloading it to the cache if needed."""
    if not is_url(source):
        return Path(source)
    cached = CACHE_DIR / f"projects-{commit}.json"
    if not cached.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        json.loads(data)  # refuse to cache a broken download
        cached.write_bytes(data)
    return cached


def load_projects(path: Path) -> list[Project]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)["projects"]


def normalise_repo(repo: str | None) -> str:
    repo = (repo or "").strip()
    if repo.startswith(GITHUB_SSH):
        repo = GITHUB_HTTPS + repo[len(GITHUB_SSH):]
    return repo.removesuffix(".git").rstrip("/")


def address_str(project: Project) -> str:
    sub = project.get("subtile_addr")
    if sub is None or sub == "":
        return str(project["address"])
    return f"{project['address']}/{sub}"


def skip_reason(project: Project, target: Project) -> str | None:
    wokwi = project.get("wokwi_id")
    if project.get("language") == "Analog":
        return "analog project"
    if wokwi and str(wokwi) != "0":
        return "wokwi project"
    if not target["source_files"]:
        return "no source files"
    if not target["top_module"]:
        return "no top module"
    if not target["repo"].startswith(GITHUB_HTTPS):
        return "repo not on github"
    return None


def make_target(project: Project, pmods: list[str]) -> Project:
    target = {
        "id": f"{project['shuttle']}/{project['macro']}",
        "shuttle": project["shuttle"],
        "macro": project["macro"],
        "address": address_str(project),
        "title": project.get("title") or "",
        "author": project.get("author") or "",
        "repo": normalise_repo(project.get("repo")),
        "commit": project.get("commit") or "",
        "top_module": project.get("top_module") or "",
        "source_files": list(project.get("source_files") or []),
        "language": project.get("language") or "",
        "clock_hz": int(project.get("clock_hz") or 0),
        "tiles": project.get("tiles") or "",
        "pinout": dict(project.get("pinout") or {}),
        "pmods": pmods,
        "docs": {k: project.get(k) or "" for k in ("description", "how_it_works", "how_to_test", "external_hw")},
    }
    target["skip"] = skip_reason(project, target)
    return target


def _sub_addr(project: Project) -> int:
    sub = project.get("subtile_addr")
    return -1 if sub is None or sub == "" else int(sub)


def select_targets(projects: list[Project], pmod: str = "tiny-vga") -> list[Project]:
    """Filter and sort the project records into target records."""
    shuttle_order = {s: i for i, s in enumerate(dict.fromkeys(p["shuttle"] for p in projects))}
    matches = []
    for project in projects:
        if project.get("type") == "group":
            continue
        pmods = detect_pmods(project.get("pinout"))
        if pmod in pmods:
            matches.append((project, pmods))
    matches.sort(key=lambda m: (shuttle_order[m[0]["shuttle"]], int(m[0]["address"]), _sub_addr(m[0]), m[0]["macro"]))
    return [make_target(p, pmods) for p, pmods in matches]


def write_targets(targets: list[Project], out: Path, source: str, commit: str | None, pmod: str) -> dict[str, Any]:
    doc = {
        "meta": {
            "source": source,
            "commit": commit,
            "pmod": pmod,
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(targets),
            "skipped": sum(1 for t in targets if t["skip"]),
        },
        "targets": targets,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    return doc


def summary(doc: dict[str, Any]) -> str:
    targets = doc["targets"]
    reasons = collections.Counter(t["skip"] for t in targets if t["skip"])
    shuttles = collections.Counter(t["shuttle"] for t in targets)
    lines = [f"{doc['meta']['count']} targets for {doc['meta']['pmod']}, {doc['meta']['skipped']} skipped"]
    lines += [f"  skip {reason}: {n}" for reason, n in reasons.most_common()]
    lines += [f"  {shuttle}: {n}" for shuttle, n in shuttles.items()]
    lines.append(f"  clock_hz unknown (0): {sum(1 for t in targets if t['clock_hz'] == 0)}")
    return "\n".join(lines)


def load_targets(path: Path = TARGETS_JSON) -> list[Project]:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)["targets"]


def target_by_id(targets: list[Project], id: str) -> Project:
    for target in targets:
        if target["id"] == id:
            return target
    raise KeyError(id)


def run(args: argparse.Namespace) -> int:
    source = args.source or PROJECTS_URL.format(commit=args.commit)
    path = fetch_projects(source, args.commit)
    targets = select_targets(load_projects(path), args.pmod)
    doc = write_targets(targets, Path(args.out), source, args.commit if is_url(source) else None, args.pmod)
    print(summary(doc))
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("targets", help="select the projects whose pinout matches a Pmod", description=__doc__)
    p.add_argument("--source", metavar="PATH_OR_URL", help="projects.json path or URL (default: GitHub at --commit)")
    p.add_argument("--commit", default=PROJECTS_COMMIT, help="tinytapeout-project-search commit to fetch")
    p.add_argument("--out", type=Path, default=TARGETS_JSON, help=f"output file (default: {TARGETS_JSON})")
    p.add_argument("--pmod", default="tiny-vga", help="Pmod id from ttsearch.pmods (default: tiny-vga)")
    p.set_defaults(func=run)
    return p
