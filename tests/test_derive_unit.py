# SPDX-License-Identifier: Apache-2.0
"""derive, without a simulator: the checks made before vgacap-sample runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from ttvga.harness import derive


def stub(path: Path, body: str) -> Path:
    path.write_text("#!/bin/bash\n" + body)   # bash: dash cannot redirect to a descriptor above 9
    path.chmod(0o755)
    return path


def test_derive_refuses_a_slice(tmp_path):
    called = tmp_path / "sample-called"
    tools = derive.Tools(
        vgacap_sample=stub(tmp_path / "vgacap-sample", f"touch {called}\nexit 0\n"),
        tracetool=stub(tmp_path / "tracetool", "printf 'version: 2\\nopen.project: test/x\\n"
                                                "open.slice_from_clock: 1000\\nopen.slice_to_clock: 2000\\n'\n"),
    )
    trace = tmp_path / "slice.vgch.zst"
    trace.write_bytes(b"not read")
    with pytest.raises(derive.DeriveError, match="slice"):
        derive.derive(trace, tmp_path / "out", "s_m", tb_v1=False, centre_window=None, store_level=None,
                      tools=tools, log=tmp_path / "derive.log", tb_hashes=None)
    assert not called.exists()
    assert not (tmp_path / "out").exists()


def test_derive_refuses_when_info_fails(tmp_path):
    tools = derive.Tools(vgacap_sample=tmp_path / "unused",
                         tracetool=stub(tmp_path / "tracetool", "echo 'tracetool: bad trace' >&2\nexit 1\n"))
    trace = tmp_path / "t.vgch.zst"
    trace.write_bytes(b"x")
    with pytest.raises(derive.DeriveError, match="bad trace"):
        derive.derive(trace, tmp_path / "out", "s_m", tb_v1=False, centre_window=None, store_level=None,
                      tools=tools, log=tmp_path / "derive.log", tb_hashes=None)


def test_derive_a_bad_png_record_is_raised(tmp_path):
    """A record out of order stops the PNG reader; derive raises instead of writing a short png/."""
    from ttvga import devtools
    from ttvga.harness import vgacap_path

    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    # The last argument is the --png-fd number: distinct frame 5 arrives first.
    sample = stub(tmp_path / "vgacap-sample", "for a; do fd=$a; done\n"
                                              "printf 'centre-v1 5 2 2\\nabcd' >&$fd\nexit 1\n")
    tools = derive.Tools(vgacap_sample=sample,
                         tracetool=stub(tmp_path / "tracetool", "printf 'version: 2\\n'\n"))
    trace = tmp_path / "t.vgch.zst"
    trace.write_bytes(b"x")
    with pytest.raises(derive.DeriveError, match="distinct frame 5, expected 0"):
        derive.derive(trace, tmp_path / "out", "s_m", tb_v1=False, centre_window=None, store_level=None,
                      tools=tools, log=tmp_path / "derive.log", tb_hashes=None)
