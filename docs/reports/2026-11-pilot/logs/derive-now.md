# derive at main 44a1baa, on the 11 published pilot traces

2026-11-28, 11:21 to 11:24 UTC, on the host.

| setting | value |
| --- | --- |
| this repository | [44a1baa](https://github.com/mithro/tinytapeout-vga-videos/commit/44a1baaf88523f23c373e087cc074ba4d002981a) |
| vgacap | [da9ea98](https://github.com/mithro/vgacap/commit/da9ea98b287740aa11b99263948bb3ca62d961c4) |
| tools | the dev tools' `vgacap-sample` and `tracetool` |
| [`tracetool.c`](../../../../ttvga/harness/tracetool.c) sha256 | `bc610e765faa9c4c7491b32cc6e232b82e20313e9e6dbdd1c1df1b7bdbfc660e` |
| traces | `<frames_root>/<id>/<stem>_trace.vgch.zst`, read only |
| script | [`derive_now.py`](../derive_now.py) |
| runs at once | 4 |
| scope | none |
| load at start | 40.91 |
| load at end | 26.15 |
| CPUs | 88 |

Each id ran twice, `both` (centre-v1 and tb-v1, as Task 23 runs) and `centre` (centre-v1 alone). Output: [`derive-now.jsonl`](derive-now.jsonl), one JSON line per run; every run exited 0 with `error` null.

`tracetool info` on nyancat's trace, the same tool (`/usr/bin/time -v`):

| quantity | value |
| --- | ---: |
| user (s) | 0.10 |
| system (s) | 0.00 |
| wall (s) | 0.11 |
| blocks | 489 |
| exit status | 0 |

So the dev tools' `tracetool` is the header-only one of [1d6930d](https://github.com/mithro/tinytapeout-vga-videos/commit/1d6930d).
