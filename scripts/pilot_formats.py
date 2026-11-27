"""Pilot Task 21 Step 6, the frames store: one long-distance zstd stream against one zstd frame per image.

    uv run scripts/pilot_formats.py FRAMES_ROOT ID... > tmp/formats.md

FRAMES_ROOT is host.toml's frames_root. For each id it reads the published centre-v1 store (one zstd
stream of the distinct frames' rgb6 bytes, as vgacap-sample writes it, with long-distance matching)
and measures, against a layout of one zstd frame per distinct image (level 3, no long-distance
matching, plus an 8-byte offset per image so any one can be found):

- size in bytes;
- the time to read the middle distinct frame (index n // 2): for the stream, decompressing from the
  start until that frame is out; for one frame per image, decompressing that image's frame alone.
  Median of 5 reads, wall time (time.perf_counter), one thread.

The trace formats (VGCH, FST, sigrok) are not measured here: the trace-format study covers them.
"""
import statistics
import sys
import time
from pathlib import Path

from compression import zstd

from ttvga import devtools
from ttvga.harness import vgacap_path

vgacap_path.add_src(devtools.paths().vgacap_src)
from vgacap import framesfile  # noqa: E402

LEVEL = 3
READS = 5
OPTIONS = {zstd.CompressionParameter.compression_level: LEVEL,
           zstd.CompressionParameter.enable_long_distance_matching: 0}


def timed(fn) -> float:
    runs = []
    for _ in range(READS):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs)


def measure(sampler_dir: Path) -> dict:
    ff = framesfile.read_frames_txt(sampler_dir / "frames.txt")
    blob = (sampler_dir / ff.store).read_bytes()
    n = ff.width * ff.height
    raw = zstd.decompress(blob)
    count = len(ff.distinct)
    images = [zstd.compress(raw[k * n:(k + 1) * n], options=OPTIONS) for k in range(count)]
    mid = count // 2

    def stream_read() -> bytes:
        out = zstd.ZstdDecompressor().decompress(blob, max_length=(mid + 1) * n)
        assert len(out) == (mid + 1) * n
        return out[mid * n:]

    def image_read() -> bytes:
        return zstd.decompress(images[mid])

    assert stream_read() == image_read() == raw[mid * n:(mid + 1) * n]
    return {"count": count, "raw": len(raw), "stream": len(blob),
            "images": sum(len(i) for i in images) + 8 * count,
            "stream_s": timed(stream_read), "image_s": timed(image_read)}


def main() -> int:
    root, ids = Path(sys.argv[1]), sys.argv[2:]
    print("| project | distinct frames | uncompressed (bytes) | stream (bytes) | one frame per image (bytes) "
          "| size ratio | stream: read middle (ms) | one frame per image: read middle (ms) |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    rows = []
    for id_ in ids:
        r = measure(root / id_ / "centre-v1")
        rows.append(r)
        print(f"| {id_} | {r['count']:,} | {r['raw']:,} | {r['stream']:,} | {r['images']:,} | "
              f"{r['images'] / r['stream']:.2f} | {r['stream_s'] * 1e3:.1f} | {r['image_s'] * 1e3:.2f} |")
    frames = sum(r["count"] for r in rows)
    stream, images = sum(r["stream"] for r in rows), sum(r["images"] for r in rows)
    # The stream's middle read decompresses about half the store: its cost per decompressed frame.
    per_frame = statistics.median(r["stream_s"] / (r["count"] // 2 + 1) for r in rows)
    per_image = statistics.median(r["image_s"] for r in rows)
    print(f"\npilot: {frames:,} distinct frames; stream {stream:,} bytes; one frame per image {images:,} bytes")
    print(f"stream bytes per distinct frame {stream / frames:,.0f}; one frame per image {images / frames:,.0f}")
    print(f"stream read cost per frame decompressed (median) {per_frame * 1e3:.3f} ms; "
          f"one image read (median) {per_image * 1e3:.3f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
