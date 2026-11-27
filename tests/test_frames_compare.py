# SPDX-License-Identifier: Apache-2.0
"""`tt-vga frames compare`: first mismatch, constant offset and start-clock deltas of two runs."""

from __future__ import annotations


import pytest
import xxhash
from compression import zstd

from ttvga import devtools, frames
from ttvga.cli import main
from ttvga.harness import vgacap_path

W, H = 4, 3
FC = 1000


@pytest.fixture(scope="module")
def framesfile():
    dev = devtools.paths()
    if not (dev.vgacap_src / "python").is_dir():
        pytest.fail(f"no vgacap clone at {dev.vgacap_src}; run `uv run tt-vga dev-tools` first")
    vgacap_path.add_src(dev.vgacap_src)
    from vgacap import framesfile

    return framesfile


def _pixels(label: int) -> bytes:
    return bytes((label * 7 + i) % 64 for i in range(W * H))


def _run(framesfile, directory, labels, starts=None, store=True, trace=False):
    """Write <directory>/<project>/centre-v1/frames.txt for `labels` (an int per frame, None for a gap)."""
    sampler_dir = directory / "centre-v1"
    sampler_dir.mkdir(parents=True)
    order = list(dict.fromkeys(x for x in labels if x is not None))
    pix = [_pixels(x) for x in order]
    data = b"".join(pix)
    name = "s_m_centre-v1_frames.rgb6.zst"
    if store:
        (sampler_dir / name).write_bytes(zstd.compress(data))
    if trace:
        (directory / "s_m_trace.vgch.zst").write_bytes(b"")
    if starts is None:
        starts = [FC * j for j in range(len(labels))]
    fr = [framesfile.Frame(-1) if x is None else framesfile.Frame(order.index(x), starts[j], 0)
          for j, x in enumerate(labels)]
    ff = framesfile.FramesFile(
        id="x", status="ok", sampler="centre-v1", sampler_status="ok", width=W, height=H, mode="test",
        clock_hz=25000000, clocks_per_pixel=1.0, capture_after_clock=0, store=name, store_length=len(data),
        store_xxh3_128=xxhash.xxh3_128_hexdigest(data), distinct=[xxhash.xxh3_128_hexdigest(p) for p in pix],
        frames=fr, centre=framesfile.Centre((0, 0), (0, 0), 0, (0, 0), 0, 0))
    framesfile.write_frames_txt(sampler_dir / "frames.txt", ff)
    return sampler_dir / "frames.txt", ff


def _hash_file(framesfile, path, ff, method="xxh3-128-rgb6"):
    if method == "xxh3-128-rgb6":
        per = list(ff.distinct)
    else:
        per = [f"{k:016x}" for k in range(len(ff.distinct))]
    framesfile.write_hash_file(path, framesfile.HashFile.from_frames(ff, method, per))
    return path


def test_identical(framesfile, tmp_path, capsys):
    labels = list(range(30))
    a, ffa = _run(framesfile, tmp_path / "a", labels)
    b, _ = _run(framesfile, tmp_path / "b", labels)
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (None, 0)
    assert (c.frames_a, c.frames_b, c.gaps_a, c.gaps_b) == (30, 30, 0, 0)
    assert c.start_clock_deltas == {0: 30}
    # A frames.txt against the xxh3-128-rgb6 hash file of the same frames.
    h = _hash_file(framesfile, tmp_path / "frame_hashes.xxh3-128-rgb6.txt", ffa)
    c = frames.compare(a, h)
    assert (c.first_mismatch, c.offset, c.start_clock_deltas) == (None, 0, None)
    assert main(["frames", "compare", str(a), str(b)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "first_mismatch: none" in out
    assert "offset: 0" in out
    assert "start_clock_delta: 0 x30" in out
    # Fewer than 10 comparable pairs: nothing to stand an offset on.
    a5, _ = _run(framesfile, tmp_path / "a5", list(range(9)))
    b5, _ = _run(framesfile, tmp_path / "b5", list(range(9)))
    assert (frames.compare(a5, b5).first_mismatch, frames.compare(a5, b5).offset) == (None, None)


def test_shift_by_3(framesfile, tmp_path, capsys):
    # B shows three extra frames after frame 5, then the same frames as A: b[j + 3] == a[j] for j >= 5.
    a_labels = list(range(30))
    b_labels = list(range(5)) + [100, 101, 102] + list(range(5, 30))
    a, _ = _run(framesfile, tmp_path / "a", a_labels, trace=True)
    b, _ = _run(framesfile, tmp_path / "b", b_labels, trace=True)
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (5, 3)
    assert (c.frames_a, c.frames_b) == (30, 33)
    # Frames 0-4 pair at offset 0, frames 5-29 at offset 3 (3 frames, 3000 clocks, later in B).
    assert c.start_clock_deltas == {0: 5, 3 * FC: 25}
    diff_out = tmp_path / "diff"
    assert main(["frames", "compare", str(a), str(b), "--out", str(diff_out)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "first_mismatch: 5" in out
    assert "offset: 3" in out
    assert out.index(f"start_clock_delta: {3 * FC} x25") < out.index("start_clock_delta: 0 x5")
    # The stores are there: frames diff of a@5 and b@5.
    assert f"differing_pixels: {sum(x != y for x, y in zip(_pixels(5), _pixels(100)))}" in out
    assert (diff_out / "mask.png").is_file()
    # The traces are there: the clock range of frame 5 in each.
    assert f"trace_range_a: --from {5 * FC} --to {6 * FC}" in out
    assert f"trace_range_b: --from {5 * FC} --to {6 * FC}" in out


def test_shift_negative(framesfile, tmp_path):
    # A starts three frames early: a[j] == b[j - 3]; a[0..2] have no partner in B, which is no data.
    a_labels = [100, 101, 102] + list(range(30))
    b_labels = list(range(30))
    a, _ = _run(framesfile, tmp_path / "a", a_labels)
    b, _ = _run(framesfile, tmp_path / "b", b_labels)
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (0, -3)
    # Frames 0-2 of A pair with nothing at offset -3, so 30 deltas of 3 frames earlier in B.
    assert c.start_clock_deltas == {-3 * FC: 30}
    # Both -1 and +1 fit an alternating pattern; the negative one is taken.
    a, _ = _run(framesfile, tmp_path / "alt_a", [j % 2 for j in range(30)])
    b, _ = _run(framesfile, tmp_path / "alt_b", [(j + 1) % 2 for j in range(30)])
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (0, -1)


def test_real_difference_no_offset(framesfile, tmp_path, capsys):
    a_labels = list(range(30))
    b_labels = list(range(30))
    b_labels[10] = 99
    a, _ = _run(framesfile, tmp_path / "a", a_labels)
    b, _ = _run(framesfile, tmp_path / "b", b_labels)
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (10, None)
    assert main(["frames", "compare", str(a), str(b)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "first_mismatch: 10" in out
    assert "offset: none" in out
    # A shift that agrees over only 9 pairs is not an offset.
    a, _ = _run(framesfile, tmp_path / "short_a", list(range(12)))
    b, _ = _run(framesfile, tmp_path / "short_b", [100, 101, 102] + list(range(12)))
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (0, 3)
    a, _ = _run(framesfile, tmp_path / "short9_a", list(range(9)) + [200, 201, 202])
    b, _ = _run(framesfile, tmp_path / "short9_b", [100, 101, 102] + list(range(9)))
    assert frames.compare(a, b).offset is None


def test_gaps_are_not_mismatches(framesfile, tmp_path):
    a_labels = list(range(30))
    b_labels = list(range(30))
    for j in (2, 3, 17):
        a_labels[j] = None
    b_labels[8] = None
    a, _ = _run(framesfile, tmp_path / "a", a_labels)
    b, _ = _run(framesfile, tmp_path / "b", b_labels)
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (None, 0)
    assert (c.frames_a, c.frames_b, c.gaps_a, c.gaps_b) == (30, 30, 3, 1)
    assert c.start_clock_deltas == {0: 26}
    # A shift over gaps: the gaps neither break the offset nor count as pairs.
    b_labels = [100, 101, 102] + list(range(30))
    b_labels[3 + 20] = None
    b, _ = _run(framesfile, tmp_path / "b2", b_labels)
    c = frames.compare(a, b)
    assert (c.first_mismatch, c.offset) == (0, 3)


def test_start_clock_deltas(framesfile, tmp_path, capsys):
    labels = list(range(40))
    extra = [7] * 20 + [8] * 8 + [9] * 5 + [10] * 4 + [11] * 2 + [12] * 1
    a, _ = _run(framesfile, tmp_path / "a", labels)
    b, _ = _run(framesfile, tmp_path / "b", labels, starts=[FC * j + extra[j] for j in range(40)])
    c = frames.compare(a, b)
    assert c.start_clock_deltas == {7: 20, 8: 8, 9: 5, 10: 4, 11: 2, 12: 1}
    assert main(["frames", "compare", str(a), str(b)]) == 0
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("start_clock_delta:")]
    assert out == ["start_clock_delta: 7 x20", "start_clock_delta: 8 x8", "start_clock_delta: 9 x5",
                   "start_clock_delta: 10 x4", "start_clock_delta: 11 x2"]


def test_methods_must_match(framesfile, tmp_path, capsys):
    a, ffa = _run(framesfile, tmp_path / "a", list(range(20)))
    sha = _hash_file(framesfile, tmp_path / "frame_hashes.xxh3-128-rgb6.txt", ffa)
    fnv = _hash_file(framesfile, tmp_path / "frame_hashes.fnv1a64-tb2026-rgb888.txt", ffa,
                     "fnv1a64-tb2026-rgb888")
    fnv2 = _hash_file(framesfile, tmp_path / "fnv2.txt", ffa, "fnv1a64-tb2026-rgb888")
    assert frames.compare(fnv, fnv2).first_mismatch is None
    for x, y in ((sha, fnv), (a, fnv), (fnv, a)):
        with pytest.raises(frames.CompareError):
            frames.compare(x, y)
        assert main(["frames", "compare", str(x), str(y)]) == 2
        assert "fnv1a64-tb2026-rgb888" in capsys.readouterr().err
