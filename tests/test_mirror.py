# SPDX-License-Identifier: Apache-2.0
"""tt-vga mirror: the rsync script never deletes and never touches the FPGA session's files or frames/."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ttvga import remote
from ttvga.harness import verify


def put(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def run(script: str, log: Path) -> subprocess.CompletedProcess:
    p = subprocess.run(["bash", "-s"], input=script, text=True, capture_output=True)
    log.write_text(f"exit {p.returncode}\n--- stdout\n{p.stdout}--- stderr\n{p.stderr}")
    return p


def test_mirror_excludes_foreign_and_never_deletes(tmp_path):
    src, dest = tmp_path / "public_html", tmp_path / "archive"
    put(src / "tt05" / "tt_um_x" / "tt05_tt_um_x_60s.mp4", b"new clip")
    put(src / "tt05" / "tt_um_x" / "tt05_tt_um_x-000000000000.bin", b"not ours")
    put(src / "fpga-library.json", b"not ours either")
    put(src / "frames" / "tt05" / "tt_um_x" / "centre-v1" / "frames.txt", b"never mirrored")
    put(src / "index.html", b"index")
    bitstream = put(dest / "tt05" / "tt_um_x" / "tt05_x-dc03d0ecd3a2.bin", b"fpga session")
    library = put(dest / "fpga-library.json", b"{}")
    old = put(dest / "tt05" / "tt_um_gone" / "tt05_tt_um_gone_60s.mp4", b"old clip")

    script = remote.mirror_script(f"{src}/", str(dest), dry_run=False)
    assert "--delete" not in script
    for pattern in verify.FOREIGN_PATTERNS:
        assert f"--exclude {'/' + pattern}" in script.replace("'", "")
    assert "--exclude /frames/" in script.replace("'", "")
    p = run(script, tmp_path / "mirror.log")
    assert p.returncode == 0, p.stderr
    assert (dest / "tt05" / "tt_um_x" / "tt05_tt_um_x_60s.mp4").read_bytes() == b"new clip"
    assert (dest / "index.html").read_bytes() == b"index"
    assert bitstream.read_bytes() == b"fpga session" and library.read_bytes() == b"{}"
    assert old.read_bytes() == b"old clip"
    assert not (dest / "tt05" / "tt_um_x" / "tt05_tt_um_x-000000000000.bin").exists()
    assert not (dest / "frames").exists()

    # A dry run copies nothing.
    put(src / "tt05" / "tt_um_y" / "tt05_tt_um_y_60s.mp4", b"later")
    p = run(remote.mirror_script(f"{src}/", str(dest), dry_run=True), tmp_path / "dry.log")
    assert p.returncode == 0, p.stderr
    assert not (dest / "tt05" / "tt_um_y").exists()


def test_mirror_refuses_frames_root_dest(tmp_path):
    src, dest = tmp_path / "public_html", tmp_path / "archive" / "frames"
    put(src / "tt05" / "tt_um_x" / "tt05_tt_um_x_60s.mp4", b"clip")
    put(dest / ".ttvga-frames-root", b"")
    p = run(remote.mirror_script(f"{src}/", str(dest), dry_run=False), tmp_path / "mirror.log")
    assert p.returncode != 0
    assert ".ttvga-frames-root" in p.stdout + p.stderr
    assert sorted(x.name for x in dest.iterdir()) == [".ttvga-frames-root"]


def test_fpga_ids_from_untrusted_paths(tmp_path):
    dest = tmp_path / "archive"
    put(dest / "tt05of" / "tt_um_dinogame" / "tt05of_dinogame-dc03d0ecd3a2.bin", b"b")
    put(dest / "tt05of" / "tt_um_dinogame" / "second-000000000000.bin", b"b")
    put(dest / "ttsky25a" / "tt_um_vga_example" / "x-111111111111.bin", b"b")
    put(dest / "ttsky25a" / "not_tt_um" / "x-111111111111.bin", b"b")
    put(dest / "TTSKY" / "tt_um_upper_shuttle" / "x.bin", b"b")
    put(dest / "tt06" / "tt_um_a\nb" / "x.bin", b"b")
    put(dest / "tt06" / "tt_um_ok" / "x\n.bin", b"b")
    put(dest / "tt06" / "tt_um_nonutf8" / b"\xff.bin".decode("utf-8", "surrogateescape"), b"b")
    put(dest / "tt06" / "tt_um_deep" / "sub" / "x.bin", b"b")
    put(dest / "tt06" / "tt_um_txt" / "x.txt", b"b")
    p = subprocess.run(["bash", "-s"], input=remote.fpga_ids_script(str(dest)).encode(), capture_output=True)
    assert p.returncode == 0, p.stderr
    ids, dropped = remote.parse_fpga_ids(p.stdout)
    assert ids == ["tt05of/tt_um_dinogame", "tt06/tt_um_nonutf8", "tt06/tt_um_ok", "ttsky25a/tt_um_vga_example"]
    assert len(dropped) == 3
    assert all(isinstance(d, str) for d in dropped)
