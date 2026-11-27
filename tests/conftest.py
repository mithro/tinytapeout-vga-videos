# SPDX-License-Identifier: Apache-2.0
import pytest

from ttvga import devtools
from ttvga.harness import vgacap_path


@pytest.fixture
def dev_tools() -> devtools.DevTools:
    """The dev-tools paths. Checks nothing: each sim test calls `require` with the tools it uses."""
    return devtools.paths()


@pytest.fixture(scope="module")
def framesfile():
    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    from vgacap import framesfile

    return framesfile
