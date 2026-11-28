# SPDX-License-Identifier: Apache-2.0
"""`tt-vga trace` and `tt-vga sample`: look at, export, slice and re-sample a raw trace locally.

The tools are the pinned vgacap build and tracetool under `$TTVGA_DEV_TOOLS` (see
`tt-vga dev-tools`). `sample` is the harness's own `derive`, run on this machine.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ttvga import devtools


def _fail(message: str) -> int:
    print(f"tt-vga: {message}", file=sys.stderr)
    return 1


def _run(cmd: list[Path | str]) -> int:
    return subprocess.run([str(c) for c in cmd], check=False).returncode


def trace_info(args: argparse.Namespace) -> int:
    d = devtools.paths()
    d.require("tracetool")
    return _run([d.tracetool, "info", args.trace])


def trace_export(args: argparse.Namespace) -> int:
    d = devtools.paths()
    d.require("vgacap_export")
    cmd: list[Path | str] = [d.vgacap_export, args.trace, "--format", args.format, "--out", args.out]
    if args.start is not None:
        cmd += ["--from", str(args.start)]
    if args.end is not None:
        cmd += ["--to", str(args.end)]
    if args.no_clk:
        cmd.append("--no-clk")
    if args.sampler_frames is not None:
        cmd += ["--frames", args.sampler_frames]
    return _run(cmd)


def trace_slice(args: argparse.Namespace) -> int:
    d = devtools.paths()
    d.require("tracetool")
    return _run([d.tracetool, "slice", args.trace, "--from", str(args.start), "--to", str(args.end),
                 "--out", args.out])


def _window(text: str) -> tuple[int, int]:
    try:
        dx, dy = (int(x) for x in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not DX,DY") from None
    return dx, dy


def sample(args: argparse.Namespace) -> int:
    d = devtools.paths()
    d.require("vgacap_sample", "tracetool")
    from ttvga.harness import derive, vgacap_path

    vgacap_path.add_src(d.vgacap_src)
    samplers = args.sampler or [derive.CENTRE]
    unknown = sorted(set(samplers) - {derive.CENTRE, derive.TB_V1})
    if unknown:
        return _fail(f"unknown sampler {unknown[0]!r}; known: {derive.CENTRE}, {derive.TB_V1}")
    trace, out = Path(args.trace), Path(args.out)
    name = args.name
    if name is None:
        proc = subprocess.run([str(d.tracetool), "info", str(trace)], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return _fail(f"tracetool info failed: {proc.stderr.strip()}")
        project = dict(line.split(": ", 1) for line in proc.stdout.splitlines()).get("open.project")
        if not project:
            return _fail("the trace has no META project; pass --name")
        name = project.replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    try:
        res = derive.derive(trace, out, name, tb_v1=derive.TB_V1 in samplers, centre_window=args.centre_window,
                            store_level=None, tools=derive.Tools(vgacap_sample=d.vgacap_sample, tracetool=d.tracetool),
                            log=out / "derive.log", tb_hashes=None)
    except derive.DeriveError as e:
        return _fail(str(e))
    for s, summary in res.samplers.items():
        print(f"{s}: {summary['sampler_status']}, {summary['frames']} frames, "
              f"{summary['distinct_frames']} distinct, {summary['mode']}")
    print(f"uo_out_xxh3_128: {res.uo_out_xxh3_128}")
    if res.error:
        return _fail(res.error)
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    t = sub.add_parser("trace", help="inspect, export or slice a raw trace (.vgch.zst)")
    ts = t.add_subparsers(dest="trace_command", required=True)

    p = ts.add_parser("info", help="print a trace's header, block and clock counts, META and close status")
    p.add_argument("trace")
    p.set_defaults(func=trace_info)

    p = ts.add_parser("export", help="write a trace as an FST or VCD waveform (wraps vgacap-export)")
    p.add_argument("trace")
    p.add_argument("--format", required=True, choices=("fst", "vcd"))
    p.add_argument("--out", required=True)
    p.add_argument("--from", dest="start", type=int, metavar="C", help="first clock")
    p.add_argument("--to", dest="end", type=int, metavar="C", help="clock to stop before")
    p.add_argument("--no-clk", action="store_true", help="leave the clock out")
    p.add_argument("--sampler-frames", metavar="FRAMES_TXT", help="frames.txt whose frame boundaries are added")
    p.set_defaults(func=trace_export)

    p = ts.add_parser("slice", help="copy clocks FROM to TO of a trace into a new trace")
    p.add_argument("trace")
    p.add_argument("--from", dest="start", type=int, required=True, metavar="C")
    p.add_argument("--to", dest="end", type=int, required=True, metavar="C")
    p.add_argument("--out", required=True)
    p.set_defaults(func=trace_slice)

    p = sub.add_parser(
        "sample", help="derive frames, hashes, PNGs and pages from a trace, locally",
        description="Run the harness's derive step on a local trace. To re-derive one project on the "
                    "host instead, use: tt-vga queue start --rederive --only <id>")
    p.add_argument("trace")
    p.add_argument("--out", required=True, metavar="DIR")
    p.add_argument("--sampler", action="append", metavar="ID", help="centre-v1 (default) or tb-v1; repeatable")
    p.add_argument("--centre-window", type=_window, metavar="DX,DY")
    p.add_argument("--name", metavar="PREFIX", help="file name prefix (default: META project, / as _)")
    p.set_defaults(func=sample)
