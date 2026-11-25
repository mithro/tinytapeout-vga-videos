# SPDX-License-Identifier: Apache-2.0
"""Build a test design of `tests/sim/designs/` with tb.cpp, the way the job builds a project."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ttvga import HARNESS_DIR
from ttvga.devtools import DevTools

sys.path.insert(0, str(HARNESS_DIR))

import job  # noqa: E402

DESIGNS = Path(__file__).resolve().parent / "designs"


def build_model(design: str, dev: DevTools, out: Path, test_hooks: bool = True) -> Path:
    """Verilate `designs/<design>.v` (top `tt_um_test_<design>`) into `out`; return the model.

    `test_hooks` compiles in tb.cpp's test-only hooks (`-DTTVGA_TEST_HOOKS`),
    as the tests need; a production model is built without them.
    Raises RuntimeError naming the build log if Verilator fails.
    """
    out = out.resolve()   # Verilator runs in designs/
    out.mkdir(parents=True, exist_ok=True)
    cmd = job.verilator_base(str(dev.verilator), f"tt_um_test_{design}", out, DESIGNS)
    cmd += job.vgacap_link_flags(dev.vgacap_src, dev.vgacap_build)
    if test_hooks:
        cmd += ["-CFLAGS", "-DTTVGA_TEST_HOOKS"]
    cmd += [str(job.TB_CPP), str(DESIGNS / f"{design}.v")]
    log = out / "build.log"
    with log.open("w") as f:
        f.write("$ " + " ".join(cmd) + "\n")
        f.flush()
        rc = subprocess.run(cmd, cwd=DESIGNS, stdout=f, stderr=subprocess.STDOUT).returncode
    model = out / "Vtop"
    if rc != 0 or not model.exists():
        raise RuntimeError(f"building {design} failed (exit {rc}); see {log}")
    return model
