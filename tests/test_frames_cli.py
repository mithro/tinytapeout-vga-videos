# SPDX-License-Identifier: Apache-2.0
"""`tt-vga frames`: to-png, from-png, diff and load_frame, over a small synthetic store."""

from __future__ import annotations

import random

import pytest
import xxhash
from compression import zstd

from ttvga import devtools, frames
from ttvga.cli import main
from ttvga.harness import pngio, vgacap_path

W, H = 8, 6


@pytest.fixture(scope="module")
def framesfile():
    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    from vgacap import framesfile

    return framesfile


@pytest.fixture
def sample(framesfile, tmp_path):
    """Three distinct frames; frames 0 and 3 share distinct 0, frame 2 is a gap. Returns (frames.txt, [rgb6])."""
    rng = random.Random(7)
    pix = [bytes(rng.randrange(64) for _ in range(W * H)) for _ in range(3)]
    store = b"".join(pix)
    d = tmp_path / "sampler"
    d.mkdir()
    (d / "x_frames.rgb6.zst").write_bytes(zstd.compress(store))
    fr = [framesfile.Frame(0, 100, 0), framesfile.Frame(1, 200, 0), framesfile.Frame(-1), framesfile.Frame(0, 400, 0),
          framesfile.Frame(2, 500, 0)]
    ff = framesfile.FramesFile(
        id="x", status="ok", sampler="tb-v1", sampler_status="ok", width=W, height=H, mode="test", clock_hz=25000000,
        clocks_per_pixel=1.0, capture_after_clock=0, store="x_frames.rgb6.zst", store_length=len(store),
        store_xxh3_128=xxhash.xxh3_128_hexdigest(store), distinct=[xxhash.xxh3_128_hexdigest(p) for p in pix],
        frames=fr)
    framesfile.write_frames_txt(d / "frames.txt", ff)
    return d / "frames.txt", pix


def test_to_png_from_png_round_trip(sample, tmp_path):
    txt, pix = sample
    png = tmp_path / "png"
    assert main(["frames", "to-png", str(txt), "--out", str(png)]) == 0
    assert [p.name for p in sorted(png.iterdir())] == ["000000.png", "000001.png", "000002.png"]
    assert pngio.read_rgb6(png / "000001.png") == (W, H, pix[1])
    store = tmp_path / "back.zst"
    assert main(["frames", "from-png", str(png), "--frames", str(txt), "--out", str(store)]) == 0
    assert zstd.decompress(store.read_bytes()) == b"".join(pix)


def test_diff_counts_and_bbox(tmp_path, capsys):
    a = bytes(W * H)
    b = bytearray(a)
    b[1 * W + 2] = 0b010011        # r1 g0 b3 at (2, 1)
    b[3 * W + 5] = 0b100000        # r2 at (5, 3)
    b[3 * W + 6] = 0b100000        # r2 at (6, 3)
    pa, pb = tmp_path / "a.png", tmp_path / "b.png"
    pngio.write_rgb6(pa, W, H, a)
    pngio.write_rgb6(pb, W, H, bytes(b))
    out = tmp_path / "out"
    assert main(["frames", "diff", str(pa), str(pb), "--out", str(out)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "differing_pixels: 3" in lines
    assert "bbox: 2 1 7 4" in lines
    assert "per_channel: r 3 g 0 b 1" in lines
    pairs = [ln for ln in lines if " -> " in ln]
    assert pairs == ["0,0,0 -> 2,0,0: 2", "0,0,0 -> 1,0,3: 1"]
    assert pngio.read_rgb6(out / "a.png") == (W, H, a)
    assert pngio.read_rgb6(out / "b.png") == (W, H, bytes(b))
    mask = pngio.read_rgb6(out / "mask.png")[2]
    assert [i for i, v in enumerate(mask) if v] == [1 * W + 2, 3 * W + 5, 3 * W + 6]


def test_diff_shape_mismatch(tmp_path, capsys):
    pa, pb = tmp_path / "a.png", tmp_path / "b.png"
    pngio.write_rgb6(pa, W, H, bytes(W * H))
    pngio.write_rgb6(pb, W + 1, H, bytes((W + 1) * H))
    assert main(["frames", "diff", str(pa), str(pb), "--out", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out" / "mask.png").exists()
    assert "8x6" in capsys.readouterr().err


def test_load_frame_captured_vs_distinct(sample, tmp_path):
    txt, pix = sample
    store = txt.parent / "x_frames.rgb6.zst"
    assert frames.load_frame(f"{store}:1") == (W, H, pix[1])
    # STORE@F is a captured frame number: frame 3 shows distinct frame 0, frame 4 distinct frame 2.
    assert frames.load_frame(f"{store}@3") == (W, H, pix[0])
    assert frames.load_frame(f"{store}@4") == (W, H, pix[2])
    with pytest.raises(ValueError, match="gap"):
        frames.load_frame(f"{store}@2")
    with pytest.raises(ValueError, match="out of range"):
        frames.load_frame(f"{store}:3")
    with pytest.raises(ValueError, match="out of range"):
        frames.load_frame(f"{store}@5")
    png = tmp_path / "f.png"
    pngio.write_rgb6(png, W, H, pix[2])
    assert frames.load_frame(str(png)) == (W, H, pix[2])


@pytest.mark.parametrize("damage", ["truncated", "other-bytes", "not-zstd"])
def test_corrupt_store_is_refused(sample, tmp_path, capsys, damage):
    txt, pix = sample
    store = txt.parent / "x_frames.rgb6.zst"
    if damage == "truncated":        # one byte short: store_length differs
        store.write_bytes(zstd.compress(b"".join(pix)[:-1]))
    elif damage == "other-bytes":    # the right length, other bytes: XXH3-128 differs
        store.write_bytes(zstd.compress(bytes(len(b"".join(pix)))))
    else:
        store.write_bytes(b"not a zstd frame")
    assert main(["frames", "to-png", str(txt), "--out", str(tmp_path / "png")]) == 1
    err = capsys.readouterr().err
    assert str(store) in err
    assert {"truncated": "store_length", "other-bytes": "XXH3-128", "not-zstd": "tt-vga: "}[damage] in err
    assert not (tmp_path / "png").exists()
    with pytest.raises(ValueError, match="x_frames.rgb6.zst"):
        frames.load_frame(f"{store}:0")


def test_diff_lists_at_most_10_pairs(tmp_path, capsys):
    # 12 distinct (a, b) value pairs, pair k on k + 1 pixels: the 10 most frequent are listed, most first.
    w, h = 13, 12
    a, b = bytearray(w * h), bytearray(w * h)
    for k in range(12):
        for x in range(k + 1):
            b[k * w + x] = k + 1
    pa, pb = tmp_path / "a.png", tmp_path / "b.png"
    pngio.write_rgb6(pa, w, h, bytes(a))
    pngio.write_rgb6(pb, w, h, bytes(b))
    assert main(["frames", "diff", str(pa), str(pb), "--out", str(tmp_path / "out")]) == 0
    pairs = [ln for ln in capsys.readouterr().out.splitlines() if " -> " in ln]
    assert len(pairs) == 10
    assert pairs[0] == f"0,0,0 -> {frames._channels(12)}: 12"
    assert pairs[-1] == f"0,0,0 -> {frames._channels(3)}: 3"


def test_unreadable_png_is_a_message_not_a_traceback(sample, tmp_path, capsys):
    pa = tmp_path / "a.png"
    pngio.write_rgb6(pa, W, H, bytes(W * H))
    missing = tmp_path / "missing.png"
    assert main(["frames", "diff", str(pa), str(missing), "--out", str(tmp_path / "out")]) == 1
    assert f"tt-vga: {missing}: No such file or directory" in capsys.readouterr().err
    # from-png: a file named like a frame that is not an rgb6 PNG.
    txt, _ = sample
    png = tmp_path / "png"
    assert main(["frames", "to-png", str(txt), "--out", str(png)]) == 0
    (png / "000001.png").write_bytes(b"not a png")
    assert main(["frames", "from-png", str(png), "--frames", str(txt), "--out", str(tmp_path / "s.zst")]) == 1
    assert "000001.png: not an rgb6 PNG" in capsys.readouterr().err
