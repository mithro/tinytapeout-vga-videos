# SPDX-License-Identifier: Apache-2.0
"""The frames format's XXH3-128 digests, and the refusal of the SHA-256 format they replaced."""

from __future__ import annotations

import pytest
import xxhash

from ttvga import devtools
from ttvga.cli import main
from ttvga.harness import vgacap_path

FIXTURE = devtools.ROOT / "tests" / "fixtures" / "frames" / "bars640" / "frames.txt"

# rgb6 frames and their XXH3-128 (seed 0, canonical big-endian: `xxhsum -H2`). The same vectors are
# in vgacap's python/tests/test_hashes.py and tests/test_hashes.c, where upstream xxhsum confirms them.
VECTORS = [
    (bytes(range(8)), "e1e4432a62217fe4cfd50c61c8bb98c1"),
    (bytes(640 * 480), "f356f76a71c18f05221f2123042fb5ce"),
    (bytes(i % 64 for i in range(640 * 480)), "e1ca6fb5c48a9634f4c39e84aaa74f6a"),
]


@pytest.fixture(scope="module")
def vgacap():
    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    from vgacap import framesfile, hashes

    return framesfile, hashes


@pytest.mark.parametrize("rgb6,digest", VECTORS)
def test_known_answer_rgb6_frame(vgacap, rgb6, digest):
    _, hashes = vgacap
    assert xxhash.xxh3_128_hexdigest(rgb6) == digest        # what derive.py and `frames` compute
    assert hashes.xxh3_128_rgb6(rgb6) == digest             # vgacap's Python reference
    assert len(digest) == 32


def test_the_committed_fixture_digests_are_32_hex(vgacap):
    framesfile, _ = vgacap
    ff = framesfile.read_frames_txt(FIXTURE)
    assert len(ff.store_xxh3_128) == 32 and all(len(d) == 32 for d in ff.distinct)


def test_frames_txt_with_the_sha256_key_is_refused(vgacap, tmp_path, capsys):
    old = tmp_path / "frames.txt"
    old.write_text(FIXTURE.read_text().replace("store_xxh3_128: ", "store_sha256: ", 1))
    assert main(["frames", "compare", str(old), str(FIXTURE)]) != 0
    err = capsys.readouterr().err
    assert "store_sha256" in err and "store_xxh3_128" in err, err


def test_a_hash_file_with_the_sha256_method_is_refused(vgacap, tmp_path, capsys):
    old = tmp_path / "frame_hashes.sha256-rgb6.txt"
    old.write_text("hash_method: sha256-rgb6\n# SHA-256 of the frame as rgb6\n")
    assert main(["frames", "compare", str(old), str(FIXTURE)]) != 0
    assert "unknown hash method 'sha256-rgb6'" in capsys.readouterr().err


def test_frames_hash_no_longer_offers_the_sha256_method(capsys):
    with pytest.raises(SystemExit) as e:
        main(["frames", "hash", str(FIXTURE), "--method", "sha256-rgb6", "--out", "x"])
    assert e.value.code == 2
    assert "xxh3-128-rgb6" in capsys.readouterr().err
