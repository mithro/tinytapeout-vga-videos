# SPDX-License-Identifier: Apache-2.0
"""Write the tb-v1 test vectors for vgacap (its Task 18): a trace of each test
design, and vgacap-sample's tb-v1 frames.txt and FNV file for it.

    uv run scripts/export_tbv1_vectors.py --out tmp/tbv1-vectors

For each case, <out>/<case>/ gets:
  trace.vgch                               the trace, decompressed (zstd -d)
  frames.txt                               vgacap-sample --sampler tb-v1 on trace.vgch
  frame_hashes.fnv1a64-tb2026-rgb888.txt   the same run's FNV file

and <out>/MANIFEST.txt lists their SHA-256s, this repository's commit and the
vgacap pin. A case is written only when tb-v1's results equal tb.cpp's own
(tests/sim/test_tbv1_matches_tb.py); a difference is kept in
tmp/tbv1-mismatch/<case>/ and the script fails. So does a trace over 1 MiB, or
a case that captures fewer than 2 frames (other than nosync, which captures none).
The work tree must be clean, so the commit in the manifest is what made the files.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
from compression import zstd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.sim import tbv1  # noqa: E402
from tests.sim.build import build_model  # noqa: E402
from ttvga import devtools  # noqa: E402

# Case -> --seconds. playground's moving pattern makes the largest trace: at
# 0.2 s it is 1.37 MB decompressed, so it runs for 0.1 s.
CASES = {
    "bars640": "0.2",
    "bars_cpp2": "0.2",
    "frac": "0.2",
    "glitch": "0.2",
    "nosync": "0.2",
    "playground": "0.1",
}
MAX_TRACE_BYTES = 1 << 20
FILES = ("trace.vgch", "frames.txt", tbv1.FNV)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def export_case(case: str, seconds: str, dev, work: Path, out: Path) -> None:
    model = build_model(case, dev, work / "models" / case)
    run_dir = work / "runs" / case
    if run_dir.exists():
        shutil.rmtree(run_dir)
    tj = tbv1.simulate(model, dev, run_dir, case, "--seconds", seconds)
    dest = out / case
    dest.mkdir(parents=True)
    trace = dest / "trace.vgch"
    trace.write_bytes(zstd.decompress((run_dir / "trace.vgch.zst").read_bytes()))
    size = trace.stat().st_size
    if size > MAX_TRACE_BYTES:
        raise SystemExit(f"{case}: trace.vgch is {size} bytes, over {MAX_TRACE_BYTES}: shorten its --seconds")
    tbv1_dir = tbv1.sample(dev, trace, run_dir / "sampled", case)
    diffs = tbv1.differences(dev, run_dir, tbv1_dir)
    if diffs:
        kept = tbv1.keep_mismatch(case, run_dir, diffs)
        raise SystemExit(f"{case}: tb-v1 differs from tb.cpp (kept in {kept}):\n" + "\n".join(diffs))
    frames = tj.get("frames", 0)
    problems = tbv1.expectation_problems(case, tj)
    if problems:
        raise SystemExit("\n".join(problems) + "\n(never shorten a case below 2 captured frames)")
    for name in FILES[1:]:
        shutil.copyfile(tbv1_dir / name, dest / name)
    log(f"{case}: --seconds {seconds}, status {tj['status']}, {frames} frames, trace.vgch {size} bytes")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=ROOT / "tmp" / "tbv1-export")
    args = ap.parse_args()
    out = args.out.resolve()

    # Untracked files are left out on purpose: tmp/ (these vectors, the logs, the
    # models) and other scratch files are untracked and cannot change what this
    # script runs, while an edit to any tracked file (code, designs, tools.toml)
    # could, and would make the manifest's commit a lie.
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise SystemExit(f"the work tree has uncommitted changes:\n{dirty}")
    commit = git("rev-parse", "HEAD").strip()
    dev = devtools.paths()
    dev.require("verilator", "ffmpeg_sink", "vgacap_sample")
    pin = tbv1.check_pin(dev)

    if out.exists():
        if any(out.iterdir()) and not (out / "MANIFEST.txt").exists():
            raise SystemExit(f"{out} exists and is not a vectors directory (no MANIFEST.txt)")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    start = time.monotonic()
    log(f"exporting {len(CASES)} cases to {out} (commit {commit}, vgacap {pin})")
    for i, (case, seconds) in enumerate(CASES.items(), 1):
        export_case(case, seconds, dev, args.work.resolve(), out)
        done = time.monotonic() - start
        left = done / i * (len(CASES) - i)
        eta = time.strftime("%H:%M:%S", time.localtime(time.time() + left))
        log(f"progress {i}/{len(CASES)}, {done:.0f} s so far, about {left:.0f} s left (ETA {eta})")

    lines = []
    for case in CASES:
        for name in FILES:
            digest = hashlib.sha256((out / case / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {case}/{name}")
    lines += [f"generator: tinytapeout-vga-videos {commit}", f"vgacap: {pin}"]
    (out / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    log(f"wrote {out / 'MANIFEST.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
