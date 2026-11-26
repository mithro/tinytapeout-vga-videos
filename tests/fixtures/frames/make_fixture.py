# SPDX-License-Identifier: Apache-2.0
"""Write tests/fixtures/frames/<name>/frames.txt: vgacap-sample's centre-v1 output on a test design's trace.

Run: TTVGA_DEV_TOOLS=<dev-tools> uv run tests/fixtures/frames/make_fixture.py
`tests/sim/test_fixtures_current.py` regenerates them and compares.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.sim import framesfix  # noqa: E402
from tests.sim.build import build_model  # noqa: E402
from ttvga import devtools  # noqa: E402


def main() -> int:
    dev = devtools.paths()
    dev.require("verilator", "ffmpeg_sink", "vgacap_sample")
    work = ROOT / "tmp" / "frames-fixture"
    shutil.rmtree(work, ignore_errors=True)
    for name, (design, _seconds) in framesfix.CASES.items():
        model = build_model(design, dev, work / "models" / design)
        txt = framesfix.centre_frames_txt(dev, model, design, work / name)
        dest = Path(__file__).resolve().parent / name
        dest.mkdir(exist_ok=True)
        shutil.copyfile(txt, dest / "frames.txt")
        print(f"wrote {dest / 'frames.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
