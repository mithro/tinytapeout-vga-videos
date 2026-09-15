# SPDX-License-Identifier: Apache-2.0
"""`tt-vga diagnose <id>`: ask the local Claude Code CLI why a project's video is not right.

Ad hoc use while developing the pipeline. A fully automated pass over every
failure is a later step that needs the owner's go-ahead (see PROGRESS.md).

The agent gets a bundle directory with the project's documentation, its
sources (a shallow clone at the recorded commit), the harness source, the
result and timing data, log tails and the contact sheet, and answers with
a fixed JSON schema: a cause, an explanation, and an optional override
YAML that `--apply` writes to `overrides/<shuttle>/<macro>.yaml`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ttvga import DATA_DIR, HARNESS_DIR, OVERRIDES_DIR, RESULTS_DIR, ROOT
from ttvga.targets import load_targets, target_by_id

BUNDLE_DIR = DATA_DIR / "diagnosis"
REPO_CACHE = DATA_DIR / "cache" / "repos"
USAGE_LOG = DATA_DIR / "diagnosis_usage.jsonl"
DEFAULT_MODEL = "claude-sonnet-5"

CAUSES = ["project-broken", "not-vga", "wrong-inputs", "wrong-clock", "harness-bug", "tool-limitation",
          "static-by-design", "needs-stimulus", "other"]

SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string", "enum": CAUSES},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "explanation": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "override_yaml": {"type": ["string", "null"],
                          "description": "Contents for overrides/<shuttle>/<macro>.yaml, or null"},
        "harness_fix": {"type": ["string", "null"],
                        "description": "If the harness itself is wrong: what to change in tb.cpp/job.py"},
        "video_expectation": {"type": "string",
                              "description": "What a correct video of this project should show"},
    },
    "required": ["cause", "confidence", "explanation", "evidence", "override_yaml", "harness_fix",
                 "video_expectation"],
}

PROMPT = """\
You are diagnosing why an automated Verilator simulation of a Tiny Tapeout project did not
produce a good VGA video. Everything you need is in this directory; read the files, then answer.

Files:
- project.md: title, author, docs (how it works, how to test, external hardware), pinout, clock.
- result.json: the pipeline's outcome (stage reached, error, verdict, reason, timing statistics
  from the testbench, log tails). `timing` comes from the testbench: sync calibration, mode match,
  frame counts, distinct frames.
- src/: the project's Verilog sources at the taped-out commit (the same files the chip was built from).
- override.yaml: the per-project override in force, if any (empty means defaults).
- overrides.md: the override format you may use in your answer (clock, inputs, gamepad, patch, ...).
- harness/tb.cpp and harness/job.py: the testbench and job runner, in case the harness is at fault.
- contact.png / poster.png: frames from the clip, if any were produced.

Verdict meanings: no-sync = no periodic hsync/vsync within the calibration window;
bad-timing/unstable-sync = sync found but not a stable raster; blank = flat colour frames;
static = a stable picture that never changes; build-failed = Verilator error; ok = looks fine.

Decide the single most likely cause:
- wrong-inputs: the design needs ui_in/uio_in changes (a start button, a mode select, a reset
  pulse, a gamepad) to run. Give an override with `inputs:` or `gamepad:` events.
- wrong-clock: the declared clock is wrong or the design divides it; give `clock_hz`.
- needs-stimulus: the picture is valid but boring without input (a game waiting for a player).
  Give an override that plays the game a little, if the docs say how.
- static-by-design: a still image is the intended output. No override needed.
- not-vga: the pins are named like Tiny VGA but the design does not really drive a VGA raster.
- project-broken: the RTL itself cannot produce a raster (bug, missing files, unsynthesisable sim).
- harness-bug: the testbench/runner mishandles this design (say exactly what).
- tool-limitation: Verilator cannot simulate a construct the design relies on.
- other: anything else, with an explanation.

Be concrete. Quote signal names and line numbers as evidence. Keep the explanation under 200 words.
Only propose an override you are fairly confident in; otherwise set override_yaml to null and say
what a person should try. Do not modify any files.
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clone_sources(target: dict, log: list[str]) -> Path | None:
    """Shallow clone of the project at its commit into data/cache/repos/. Returns the src dir."""
    dest = REPO_CACHE / target["shuttle"] / target["macro"]
    if not (dest / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        for cmd in (["git", "init", "-q"], ["git", "remote", "add", "origin", target["repo"]],
                    ["git", "fetch", "-q", "--depth", "1", "origin", target["commit"]],
                    ["git", "checkout", "-q", "FETCH_HEAD"]):
            p = subprocess.run(cmd, cwd=dest, env=env, capture_output=True, text=True)
            if p.returncode != 0:
                log.append(f"clone failed at {' '.join(cmd)}: {p.stderr.strip()}")
                return None
    return dest / "src" if (dest / "src").exists() else dest


def build_bundle(target: dict, result: dict, images: Path | None) -> Path:
    bundle = BUNDLE_DIR / target["shuttle"] / target["macro"]
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    notes: list[str] = []
    docs = target["docs"]
    pinout = "\n".join(f"| {k} | {v} |" for k, v in target["pinout"].items())
    (bundle / "project.md").write_text(f"""# {target['title']}

- id: {target['id']}  (shuttle {target['shuttle']}, address {target['address']})
- author: {target['author']}
- repo: {target['repo']} at {target['commit']}
- top module: {target['top_module']}; sources: {', '.join(target['source_files'])}
- language: {target['language']}; declared clock_hz: {target['clock_hz']} (0 = unknown, the harness then uses 25.175 MHz)
- tiles: {target['tiles']}; inferred Pmods: {', '.join(target['pmods'])}

## Description

{docs.get('description', '')}

## How it works

{docs.get('how_it_works', '')}

## How to test

{docs.get('how_to_test', '')}

## External hardware

{docs.get('external_hw', '')}

## Pinout

| pin | name |
| --- | --- |
{pinout}
""")
    (bundle / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    src = clone_sources(target, notes)
    if src is not None:
        shutil.copytree(src, bundle / "src", ignore=shutil.ignore_patterns(".git"))
    else:
        (bundle / "src").mkdir()
        (bundle / "src" / "MISSING.txt").write_text("\n".join(notes) + "\n")
    ov = OVERRIDES_DIR / target["shuttle"] / f"{target['macro']}.yaml"
    (bundle / "override.yaml").write_text(ov.read_text() if ov.exists() else "")
    (bundle / "overrides.md").write_text((ROOT / "ttvga" / "overrides.py").read_text().split('"""')[1])
    (bundle / "harness").mkdir()
    for name in ("tb.cpp", "job.py"):
        shutil.copy(HARNESS_DIR / name, bundle / "harness" / name)
    if images is not None:
        for name in ("contact.png", "poster.png"):
            if (images / name).exists():
                shutil.copy(images / name, bundle / name)
    (bundle / "PROMPT.md").write_text(PROMPT)
    return bundle


def run_claude(bundle: Path, model: str, budget: float, effort: str | None) -> dict:
    cmd = ["claude", "-p", "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--model", model, "--max-budget-usd", str(budget), "--no-session-persistence",
           "--allowedTools", "Read", "Glob", "Grep", "--add-dir", str(bundle),
           "--permission-mode", "dontAsk"]
    if effort:
        cmd += ["--effort", effort]
    prompt = f"{PROMPT}\nThe bundle directory is {bundle}. Start by reading {bundle}/project.md and {bundle}/result.json."
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1800)
    (bundle / "claude-output.json").write_text(p.stdout)
    (bundle / "claude-stderr.txt").write_text(p.stderr)
    if p.returncode != 0 and not p.stdout.strip():
        raise RuntimeError(f"claude exited {p.returncode}: {p.stderr.strip()[-2000:]}")
    out = json.loads(p.stdout)
    if isinstance(out, list):
        # Some CLI versions print the whole message list; the last "result" entry is the summary.
        results = [m for m in out if isinstance(m, dict) and m.get("type") == "result"]
        out = results[-1] if results else (out[-1] if out and isinstance(out[-1], dict) else {})
    return out


def run(args: argparse.Namespace) -> int:
    targets = load_targets()
    target = target_by_id(targets, args.id)
    result_path = RESULTS_DIR / target["shuttle"] / target["macro"] / "result.json"
    if not result_path.exists():
        sys.exit(f"tt-vga: no collected result for {args.id}; run `tt-vga collect` first")
    result = json.loads(result_path.read_text())
    images = Path(args.images) / target["shuttle"] / target["macro"] if args.images else None
    bundle = build_bundle(target, result, images)
    print(f"bundle: {bundle}")
    if args.dry_run:
        return 0
    started = now()
    out = run_claude(bundle, args.model, args.budget, args.effort)
    answer = out.get("structured_output") or out.get("result")
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except json.JSONDecodeError:
            answer = {"cause": "other", "confidence": "low", "explanation": answer, "evidence": [],
                      "override_yaml": None, "harness_fix": None, "video_expectation": ""}
    record = {
        "id": target["id"], "started": started, "finished": now(), "model": args.model,
        "verdict_before": result.get("verdict"), "answer": answer,
        "cost_usd": out.get("total_cost_usd"), "usage": out.get("usage"), "num_turns": out.get("num_turns"),
        "duration_ms": out.get("duration_ms"), "session_id": out.get("session_id"),
    }
    history = result.setdefault("diagnosis", [])
    history.append(record)
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    with USAGE_LOG.open("a") as f:
        f.write(json.dumps({k: record[k] for k in ("id", "finished", "model", "cost_usd", "usage", "num_turns")}) + "\n")
    print(json.dumps(answer, indent=2))
    print(f"cost: ${record['cost_usd']}  turns: {record['num_turns']}")
    if args.apply and answer.get("override_yaml"):
        ov = OVERRIDES_DIR / target["shuttle"] / f"{target['macro']}.yaml"
        ov.parent.mkdir(parents=True, exist_ok=True)
        header = f"# Proposed by tt-vga diagnose ({args.model}, {started}); cause: {answer['cause']}\n"
        ov.write_text(header + answer["override_yaml"].rstrip() + "\n")
        print(f"wrote {ov.relative_to(ROOT)}")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("diagnose", help="ask the local Claude CLI why one project's video is wrong (ad hoc)")
    p.add_argument("id", help="<shuttle>/<macro>")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default=None, help="CLI effort level, if supported")
    p.add_argument("--budget", type=float, default=1.0, help="max USD for this run")
    p.add_argument("--images", help="local directory holding <shuttle>/<macro>/{contact,poster}.png (from collect --images)")
    p.add_argument("--apply", action="store_true", help="write the proposed override YAML")
    p.add_argument("--dry-run", action="store_true", help="build the bundle only")
    p.set_defaults(func=run)
