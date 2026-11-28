# Pilot measurements (plan Tasks 20 and 21, rollout step 2)

2026-11-27, all times UTC.

The [plan](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md)'s 11 projects ran at once on the host by [`scripts/pilot_measure.py`](../../../scripts/pilot_measure.py):
- harness `0b581aeab69291a9`, commit [f64607a](https://github.com/mithro/tinytapeout-vga-videos/commit/f64607a);
- vgacap at [c7176da](https://github.com/mithro/vgacap/tree/c7176da10e2171a76605734d4364de85bb549280);
- each project in its own queue-limited scope ([`runqueue.py`](../../../ttvga/harness/runqueue.py): MemoryMax 6G, CPUQuota 200%, TasksMax 64, OOMPolicy=continue).

The raw records are in [`raw/`](raw/), one per project, with the pilot's end in [`raw/DONE`](raw/DONE). The ids are in [`ids.txt`](ids.txt). Host names and paths in the records are replaced by `<host>`, `<staging_dir>`, `<frames_root>`, `<videos>` and `~`.

Per project, each under [GNU `time -v`](https://man7.org/linux/man-pages/man1/time.1.html):
1. [`job.py`](../../../ttvga/harness/job.py) `--tb-v1 --keep-build --timeout 10800 --grace 120 --seconds 60`, publishing to the frames subtree;
2. the kept `Vtop` 4 times, with the job's cwd and arguments: without `--trace`, with, without, with;
3. [`vgacap-sample`](https://github.com/mithro/vgacap/blob/c7176da10e2171a76605734d4364de85bb549280/src/tools/vgacap_sample.c) alone on the published trace, with its default sampler and with both.

Host load during the run: 45 to 109 on 88 CPUs (0.5 to 1.24 a CPU), from the pilot's progress lines.

## Rulings used here

| ruling | setting | value | from | date | source |
| --- | --- | --- | --- | --- | --- |
| W | default sampler set | centre-v1 | owner | 2026-11-25 | [spec, decision 3](../../superpowers/specs/2026-11-24-raw-frames-and-hash-methods-design.md#decisions-for-the-owner) |
| W | tb-v1 | on request (`--tb-v1`) | owner | 2026-11-25 | [spec, decision 3](../../superpowers/specs/2026-11-24-raw-frames-and-hash-methods-design.md#decisions-for-the-owner) |
| BK | upload split | none | owner | 2026-11-27 | [plan, Task 19](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-19-the-upload-split-decision-4-with-the-frames-upload-left-off) |
| BK | upload listing | measured | owner | 2026-11-27 | [plan, Task 19](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-19-the-upload-split-decision-4-with-the-frames-upload-left-off) |
| BK | plan Task 19 | reduced | owner | 2026-11-27 | [plan, Task 19](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-19-the-upload-split-decision-4-with-the-frames-upload-left-off) |
| BN | `FFMPEG_CPUS` | 2 | controller | 2026-11-27 | [3e52502](https://github.com/mithro/tinytapeout-vga-videos/commit/3e52502) |
| BN | TasksMax | 64 | controller | 2026-11-27 | [`runqueue.py`](../../../ttvga/harness/runqueue.py) |
| BU | trace formats in Task 21 Step 6 | the trace-format study | controller | 2026-11-27 | [trace-format study](https://github.com/mithro/vgacap/blob/847a17f4a5e87a5b509f1722f0237de5d99ceb6a/docs/design/2026-11-27-trace-format-study.md) |

## Starts that failed

Two earlier starts failed and are not in these tables:

| attempt | started | failed in | error | threads from | threads | stopped |
| --- | --- | --- | --- | --- | ---: | --- |
| 1 | 01:16 | every model | `std::system_error` EAGAIN | Verilator context pool | 87 | itself |
| 2 | 01:26 | capture's MJPEG encoder | EAGAIN | ffmpeg, by host CPUs | 88 | by hand, 50 s |
| 3 | 01:34 | - | - | - | - | - |

| attempt | fix commit | change | file |
| --- | --- | --- | --- |
| 1 | [cb0f232](https://github.com/mithro/tinytapeout-vga-videos/commit/cb0f232) | `ctx.threads(1)` | [`tb.cpp`](../../../ttvga/harness/tb.cpp) |
| 2 | [f64607a](https://github.com/mithro/tinytapeout-vga-videos/commit/f64607a) | `-cpucount` | [`tb.cpp`](../../../ttvga/harness/tb.cpp) |
| 2 | [f64607a](https://github.com/mithro/tinytapeout-vga-videos/commit/f64607a) | `-cpucount` | [`encode.py`](../../../ttvga/harness/encode.py) |

Both thread counts exceed the scope's TasksMax of 64.

## The upload's listing (Ruling BK)

> **At all 408 projects with both samplers (the step 4 re-run) the steady listing is projected at about 189 s (161 to 216 s) of the 5-minute interval, and runs that also transfer new frames already took up to 247 s during the pilot.**
>
> The projection extrapolates linearly from 63,000 to 103,000 files measured to 1.09 million, about 10 times the largest count measured: the listing's real cost at that size is not measured.

From the upload's `/var/lib/data-upload/rsync.log` on the host, read-only:
- files: `Number of files:`;
- duration: the time from `building file list` to `total size is`, in whole seconds;
- projects published: the pilot's projects published before the run started.

| run | files | duration (s) | projects published |
| --- | ---: | ---: | ---: |
| 2026-11-27T01:08:04 | 62,991 | 24 | 0 |
| 2026-11-27T01:43:04 | 62,993 | 24 | 0 |
| 2026-11-27T01:48:04 | 71,479 | 44 | 4 |
| 2026-11-27T01:53:03 | 71,498 | 30 | 5 |
| 2026-11-27T01:58:03 | 91,899 | 146 | 8 |
| 2026-11-27T02:03:03 | 91,910 | 30 | 8 |
| 2026-11-27T02:08:03 | 102,356 | 247 | 10 |
| 2026-11-27T02:23:04 | 102,579 | 32 | 11 |
| 2026-11-27T02:43:03 | 102,579 | 31 | 11 |
| 2026-11-27T04:33:03 | 102,579 | 31 | 11 |

### The per-file cost

| quantity | value |
| --- | ---: |
| runs before the pilot's frames | 38 |
| their mean duration | 25.05 s |
| runs with all 11 projects | 35 |
| their mean duration | 30.97 s |
| files added | 39,588 |
| cost per file | 0.150 ms |
| cost per file, delta 1 s lower | 0.124 ms |
| cost per file, delta 1 s higher | 0.175 ms |

The cost per file comes from one delta, between two means of whole-second durations. ±1 s on that delta is the range carried below. The listing is assumed linear in files.

### Projected to the committed results

From the committed [`data/results/*/*/result.json`](../../../data/results/):
- 440 results;
- 421 simulated, so published (a no-picture run publishes `frames: 0`);
- 408 with frames: `distinct_frames` sums to 543,730, mean 1,333, median 256.

Entries per project, counted in the pilot's frames tree: 9 with centre-v1 alone, 17 with both samplers. On top of those come one PNG per distinct frame per sampler, 24 shuttle directories and the root. Generator: [`upload_projection.py`](upload_projection.py).

| samplers | files | listing (s) | listing, low (s) | listing, high (s) | share of 300 s |
| --- | ---: | ---: | ---: | ---: | ---: |
| both (step 4 re-run) | 1,094,642 | 189 | 161 | 216 | 63% |
| centre-v1 only (default) | 547,544 | 107 | 93 | 121 | 36% |

The runs that also transferred new frames (146 s and 247 s) come closest. During the step 4 re-run, with 24 jobs publishing, most runs will transfer.

## Recording, from the pilot's own runs (indicative)

Target: `(wall with trace - wall without) / wall without` at most 5%. Mean of 2 runs each, one after another, so the verdicts here are indicative only: see the side-by-side bench under Step 3.

| project | wall without (s) | wall with (s) | overhead (%) | ns per clock | clocks | within 5% (indicative) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| tt05/tt_um_tomkeddie_a | 368.2 | 373.0 | 1.31 | 3.2 | 1,512,463,066 | yes |
| tt07/tt_um_tinytapeout_dvd_screensaver | 342.6 | 355.8 | 3.86 | 8.7 | 1,512,393,611 | yes |
| tt08/tt_um_MichaelBell_mandelbrot | 1849.8 | 1892.4 | 2.30 | 7.1 | 6,007,335,947 | yes |
| tt08/tt_um_a1k0n_nyancat | 344.4 | 395.3 | 14.79 | 33.7 | 1,512,393,611 | **no** |
| tt08/tt_um_johshoff_metaballs | 633.3 | 667.2 | 5.36 | 11.3 | 3,003,263,130 | **no** |
| tt08/tt_um_nyan | 320.0 | 348.2 | 8.81 | 18.8 | 1,502,127,755 | **no** |
| ttihp25a/tt_um_MichaelBell_rle_vga | 433.2 | 479.1 | 10.59 | 31.8 | 1,441,605,610 | **no** |
| ttihp25a/tt_um_a1k0n_vgadonut | 706.2 | 740.5 | 4.86 | 11.9 | 2,883,800,936 | yes |
| ttihp25a/tt_um_cfib_demo | 583.3 | 630.1 | 8.02 | 15.6 | 3,003,787,210 | **no** |
| ttihp25a/tt_um_rebeccargb_colorbars | 339.6 | 364.5 | 7.33 | 16.5 | 1,512,393,611 | **no** |
| ttihp25a/tt_um_rejunity_atari2600 | 655.6 | 680.5 | 3.80 | 16.5 | 1,512,001,611 | yes |

## Post-simulation CPU

Target: (compressor CPU + `derive_cpu_seconds`) / simulation CPU without the trace, at most 5%.

| project | CPU without (s) | CPU with (s) | compressor (s) | derive (s) | post (s) | budget (s) | post (%) | within 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| tt05/tt_um_tomkeddie_a | 385.1 | 394.2 | 9.1 | 53.3 | 62.4 | 19.3 | 16.20 | **no** |
| tt07/tt_um_tinytapeout_dvd_screensaver | 356.9 | 374.5 | 17.6 | 113.7 | 131.3 | 17.8 | 36.79 | **no** |
| tt08/tt_um_MichaelBell_mandelbrot | 1886.8 | 1930.1 | 43.3 | 34.6 | 77.9 | 94.3 | 4.13 | yes |
| tt08/tt_um_a1k0n_nyancat | 405.7 | 477.2 | 71.6 | 201.0 | 272.6 | 20.3 | 67.19 | **no** |
| tt08/tt_um_johshoff_metaballs | 672.3 | 707.4 | 35.1 | 202.3 | 237.4 | 33.6 | 35.32 | **no** |
| tt08/tt_um_nyan | 336.7 | 369.2 | 32.5 | 14.0 | 46.5 | 16.8 | 13.82 | **no** |
| ttihp25a/tt_um_MichaelBell_rle_vga | 453.0 | 504.5 | 51.4 | 139.0 | 190.5 | 22.7 | 42.05 | **no** |
| ttihp25a/tt_um_a1k0n_vgadonut | 759.9 | 800.6 | 40.7 | 179.8 | 220.5 | 38.0 | 29.01 | **no** |
| ttihp25a/tt_um_cfib_demo | 623.5 | 672.1 | 48.6 | 109.8 | 158.4 | 31.2 | 25.40 | **no** |
| ttihp25a/tt_um_rebeccargb_colorbars | 356.1 | 383.2 | 27.2 | 12.7 | 39.8 | 17.8 | 11.18 | **no** |
| ttihp25a/tt_um_rejunity_atari2600 | 733.2 | 784.4 | 51.2 | 153.0 | 204.2 | 36.7 | 27.85 | **no** |

## Memory per job

Max RSS from `time -v` (the largest single process), and the scope's MemoryPeak (all its processes and page cache), in MiB. `time -v` reports KiB.

| project | job max RSS | model max RSS | sample default max RSS | sample both max RSS | scope MemoryPeak | scope peak tasks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 734 | 61 | 153 | 289 | 834 | 54 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 659 | 65 | 152 | 291 | 743 | 53 |
| tt08/tt_um_MichaelBell_mandelbrot | 723 | 63 | 74 | 112 | 1,081 | 53 |
| tt08/tt_um_a1k0n_nyancat | 1,761 | 96 | 559 | 695 | 3,167 | 61 |
| tt08/tt_um_johshoff_metaballs | 1,178 | 67 | 154 | 294 | 1,286 | 61 |
| tt08/tt_um_nyan | 1,728 | 71 | 73 | 93 | 1,965 | 61 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 645 | 107 | 56 | 65 | 704 | 53 |
| ttihp25a/tt_um_a1k0n_vgadonut | 746 | 97 | 323 | 463 | 1,843 | 53 |
| ttihp25a/tt_um_cfib_demo | 1,776 | 68 | 175 | 310 | 2,365 | 61 |
| ttihp25a/tt_um_rebeccargb_colorbars | 1,750 | 73 | 27 | 37 | 1,892 | 61 |
| ttihp25a/tt_um_rejunity_atari2600 | 1,789 | 115 | 725 | 871 | 3,814 | 61 |

## Root-volume peak per job

Peak `du -sb` of the project's work directory while job.py ran, polled every 5 s, in GB.

| project | work directory peak | scratch peak | pilot re-run directory peak |
| --- | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 0.07 | 0.01 | 0.05 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 0.05 | 0.02 | 0.03 |
| tt08/tt_um_MichaelBell_mandelbrot | 0.34 | 0.02 | 0.30 |
| tt08/tt_um_a1k0n_nyancat | 1.36 | 0.45 | 1.26 |
| tt08/tt_um_johshoff_metaballs | 0.06 | 0.02 | 0.04 |
| tt08/tt_um_nyan | 0.21 | 0.05 | 0.16 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 0.04 | 0.02 | 0.03 |
| ttihp25a/tt_um_a1k0n_vgadonut | 0.97 | 0.38 | 0.75 |
| ttihp25a/tt_um_cfib_demo | 0.55 | 0.05 | 0.46 |
| ttihp25a/tt_um_rebeccargb_colorbars | 0.12 | 0.00 | 0.07 |
| ttihp25a/tt_um_rejunity_atari2600 | 1.98 | 0.61 | 1.72 |

Largest peak 1.98 GB: 24 x 1.98 x 2 = 94.9 GB, rounded up to 10: `min_free_root_gb = 100`.

Root volume free, lowest seen by the 5 s polls during the pilot: 772 GB.

## Sizes

The published directory (`du -b`, hard links once), in kB (1,000 bytes).

| project | trace | centre-v1 store | tb-v1 store | centre-v1 PNGs | tb-v1 PNGs | centre-v1 PNG files | tb-v1 PNG files | whole directory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 113 | 114 | 103 | 2,209 | 2,211 | 636 | 636 | 6,415 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 1,307 | 140 | 140 | 11,306 | 11,306 | 3,568 | 3,568 | 15,882 |
| tt08/tt_um_MichaelBell_mandelbrot | 14,719 | 560 | 598 | 1,047 | 1,160 | 103 | 103 | 18,995 |
| tt08/tt_um_a1k0n_nyancat | 416,434 | 4,539 | 4,539 | 23,179 | 23,179 | 3,530 | 3,530 | 451,663 |
| tt08/tt_um_johshoff_metaballs | 1,332 | 2,238 | 2,238 | 14,488 | 14,488 | 4,325 | 4,325 | 23,918 |
| tt08/tt_um_nyan | 51,779 | 1 | 1 | 10 | 11 | 2 | 2 | 52,359 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 18,389 | 0 | 0 | 2 | 2 | 1 | 1 | 18,926 |
| ttihp25a/tt_um_a1k0n_vgadonut | 167,330 | 27,660 | 27,724 | 79,348 | 79,014 | 3,597 | 3,597 | 384,087 |
| ttihp25a/tt_um_cfib_demo | 20,589 | 2,157 | 2,154 | 13,727 | 13,746 | 2,320 | 2,320 | 54,609 |
| ttihp25a/tt_um_rebeccargb_colorbars | 556 | 0 | 0 | 5 | 5 | 1 | 1 | 1,096 |
| ttihp25a/tt_um_rejunity_atari2600 | 596,591 | 313 | 313 | 11,552 | 11,552 | 1,609 | 1,609 | 610,840 |

## vgacap-sample alone

On the published trace, VGACAP_SAMPLE_DEBUG=1; and the job's derive from result.json.

| project | default wall (s) | default CPU (s) | both wall (s) | both CPU (s) | both debug | job derive wall (s) | job derive CPU (s) | frames | distinct frames |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 15.1 | 15.1 | 34.7 | 34.7 | trace_passes=1 blocks_decoded=91 | 44.5 | 53.3 | 3,736 | 636 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 23.1 | 23.1 | 51.9 | 50.8 | trace_passes=1 blocks_decoded=91 | 85.8 | 113.7 | 3,596 | 3,568 |
| tt08/tt_um_MichaelBell_mandelbrot | 14.5 | 14.5 | 30.9 | 30.9 | trace_passes=1 blocks_decoded=359 | 32.9 | 34.6 | 3,355 | 103 |
| tt08/tt_um_a1k0n_nyancat | 54.8 | 52.7 | 85.8 | 85.7 | trace_passes=1 blocks_decoded=489 | 169.2 | 201.0 | 3,596 | 3,530 |
| tt08/tt_um_johshoff_metaballs | 38.9 | 38.8 | 86.2 | 86.2 | trace_passes=1 blocks_decoded=180 | 173.8 | 202.3 | 4,331 | 4,325 |
| tt08/tt_um_nyan | 5.5 | 5.5 | 11.5 | 11.5 | trace_passes=1 blocks_decoded=90 | 14.0 | 14.0 | 3,434 | 2 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 51.2 | 51.2 | 64.1 | 64.0 | trace_passes=1 blocks_decoded=1208 | 139.1 | 139.0 | 3,600 | 1 |
| ttihp25a/tt_um_a1k0n_vgadonut | 35.9 | 35.8 | 69.2 | 69.1 | trace_passes=1 blocks_decoded=195 | 117.1 | 179.8 | 3,597 | 3,597 |
| ttihp25a/tt_um_cfib_demo | 20.9 | 20.9 | 44.7 | 44.7 | trace_passes=1 blocks_decoded=180 | 76.5 | 109.8 | 3,571 | 2,320 |
| ttihp25a/tt_um_rebeccargb_colorbars | 4.8 | 4.8 | 9.8 | 9.8 | trace_passes=1 blocks_decoded=91 | 12.7 | 12.7 | 3,596 | 1 |
| ttihp25a/tt_um_rejunity_atari2600 | 53.5 | 53.5 | 78.8 | 70.6 | trace_passes=1 blocks_decoded=569 | 140.2 | 153.0 | 3,596 | 1,609 |

## Against the targets

| target | limit | within | over | inconclusive | worst project | worst value |
| --- | --- | ---: | ---: | ---: | --- | --- |
| recording, side by side | 5% of wall | 0 | 3 | 5 | rle_vga | +20.7% |
| recording, pilot runs only (indicative) | 5% of wall | 3 | 0 | 0 | dvd_screensaver | +3.9% |
| post-simulation CPU | 5% of simulation CPU | 1 | 10 | 0 | nyancat | 67% |
| memory | MemoryMax 6 GiB | 11 | 0 | 0 | atari2600 | 3,814 MiB |
| tasks, `FFMPEG_CPUS` 4 | TasksMax 64 | 11 | 0 | 0 | six projects | 61 |
| tasks, `FFMPEG_CPUS` 2 | TasksMax 64 | 1 | 0 | 0 | atari2600 | 53 |
| root volume | `min_free_root_gb` | - | - | - | atari2600 | 1.98 GB |

- **Recording:** the verdicts come from the side-by-side bench below: over for nyancat, rle_vga and vgadonut; inconclusive (pairs span 5%) for colorbars, nyan, cfib_demo, metaballs and tomkeddie_a. dvd_screensaver, mandelbrot and atari2600 have only the pilot's runs. The pilot's own runs, one after another, are indicative only: the same untraced model differed by up to 26.6% between its two runs (rle_vga: 484.1 s and 382.4 s; dvd_screensaver 18.7%).
- **Root volume:**
  - the rule gives `min_free_root_gb = 100`, the value host.toml already had; it was written again;
  - the lowest free space on the root volume during the pilot was 772 GB.
- **Tasks (Ruling BN):** with `FFMPEG_CPUS = 4` six projects reached 61 of 64 tasks while job.py encoded. Commit [3e52502](https://github.com/mithro/tinytapeout-vga-videos/commit/3e52502) sets it to 2. One encode-heavy project, atari2600 (945 s of encode in the pilot), was run again with it: the peak was 53 tasks, during derive; encode peaked at 46.
  - The cost of Ruling BN: atari2600's encode took 1,352 s against 945 s in the pilot, +43%.
  - Measured on one project only; the other five that reached 61 tasks were not re-run.
  - The re-run ran alone, under different host load from the pilot's, so the +43% is one sample, not a measured rate.
- **Memory:** the largest single process is x264 at 1,789 MiB. MemoryPeak counts the scope's page cache too.
- **dvd_screensaver:** post-simulation CPU 131.3 s against its 17.8 s budget (5% of 356.9 s), with both samplers.

## Step 3: recording

### Side by side

The logs are in [`bench/`](bench/), summarised by [`bench_summary.py`](bench_summary.py), whose output the two tables below are. 20 s of simulated time per model, in queue-sized scopes. A pair is one without and one with, started together.

| project | bench | models at once | pairs a round | rounds | log |
| --- | --- | --- | ---: | ---: | --- |
| colorbars | 2 + 2 | not recorded | 2 | 3 | [`colorbars.log`](bench/colorbars.log) |
| rle_vga | 2 + 2 | 24 | 2 | 3 | [`six.log`](bench/six.log) |
| nyan | 2 + 2 | 24 | 2 | 3 | [`six.log`](bench/six.log) |
| cfib_demo | 2 + 2 | 24 | 2 | 3 | [`six.log`](bench/six.log) |
| metaballs | 2 + 2 | 24 | 2 | 3 | [`six.log`](bench/six.log) |
| tomkeddie_a | 2 + 2 | 24 | 2 | 3 | [`six.log`](bench/six.log) |
| vgadonut | 2 + 2 | 24 | 2 | 3 | [`six.log`](bench/six.log) |
| nyancat | level bench | 5 | 1 | 3 | [`levels-nyancat.log`](bench/levels-nyancat.log) |

- No bench log has start times, so none shows how many models ran at once. The 24 and the 5 are the benches' design (6 projects of 4 models, and 5 variants), and their logs list the runs in that shape. colorbars' log holds only its own 4 runs a round, so its count is not recorded.

| project | bench | round | pair | without (s) | with (s) | overhead (%) |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| colorbars | 2 + 2 | 1 | A | 101.8 | 107.2 | +5.3 |
| colorbars | 2 + 2 | 1 | B | 101.2 | 104.3 | +3.0 |
| colorbars | 2 + 2 | 2 | A | 99.2 | 105.9 | +6.7 |
| colorbars | 2 + 2 | 2 | B | 96.1 | 104.8 | +9.0 |
| colorbars | 2 + 2 | 3 | A | 99.5 | 104.8 | +5.3 |
| colorbars | 2 + 2 | 3 | B | 96.7 | 103.1 | +6.6 |
| rle_vga | 2 + 2 | 1 | A | 140.3 | 175.7 | +25.2 |
| rle_vga | 2 + 2 | 1 | B | 140.0 | 162.8 | +16.3 |
| rle_vga | 2 + 2 | 2 | A | 161.6 | 175.9 | +8.8 |
| rle_vga | 2 + 2 | 2 | B | 157.7 | 178.2 | +13.0 |
| rle_vga | 2 + 2 | 3 | A | 144.3 | 191.4 | +32.7 |
| rle_vga | 2 + 2 | 3 | B | 148.6 | 190.8 | +28.4 |
| nyan | 2 + 2 | 1 | A | 102.8 | 111.7 | +8.7 |
| nyan | 2 + 2 | 1 | B | 108.6 | 110.7 | +1.9 |
| nyan | 2 + 2 | 2 | A | 110.7 | 110.9 | +0.1 |
| nyan | 2 + 2 | 2 | B | 111.5 | 111.7 | +0.2 |
| nyan | 2 + 2 | 3 | A | 115.7 | 123.6 | +6.8 |
| nyan | 2 + 2 | 3 | B | 115.0 | 124.6 | +8.3 |
| cfib_demo | 2 + 2 | 1 | A | 215.3 | 253.7 | +17.8 |
| cfib_demo | 2 + 2 | 1 | B | 221.9 | 252.0 | +13.5 |
| cfib_demo | 2 + 2 | 2 | A | 226.6 | 233.0 | +2.9 |
| cfib_demo | 2 + 2 | 2 | B | 217.6 | 240.2 | +10.4 |
| cfib_demo | 2 + 2 | 3 | A | 215.0 | 233.6 | +8.7 |
| cfib_demo | 2 + 2 | 3 | B | 213.8 | 232.6 | +8.8 |
| metaballs | 2 + 2 | 1 | A | 247.3 | 272.0 | +10.0 |
| metaballs | 2 + 2 | 1 | B | 257.2 | 269.0 | +4.6 |
| metaballs | 2 + 2 | 2 | A | 227.3 | 253.8 | +11.7 |
| metaballs | 2 + 2 | 2 | B | 238.8 | 257.8 | +7.9 |
| metaballs | 2 + 2 | 3 | A | 219.0 | 235.7 | +7.6 |
| metaballs | 2 + 2 | 3 | B | 224.3 | 234.0 | +4.3 |
| tomkeddie_a | 2 + 2 | 1 | A | 120.8 | 128.8 | +6.6 |
| tomkeddie_a | 2 + 2 | 1 | B | 121.0 | 129.8 | +7.3 |
| tomkeddie_a | 2 + 2 | 2 | A | 132.9 | 130.7 | -1.7 |
| tomkeddie_a | 2 + 2 | 2 | B | 135.2 | 131.8 | -2.6 |
| tomkeddie_a | 2 + 2 | 3 | A | 116.8 | 126.4 | +8.2 |
| tomkeddie_a | 2 + 2 | 3 | B | 115.1 | 125.8 | +9.2 |
| vgadonut | 2 + 2 | 1 | A | 273.0 | 288.6 | +5.7 |
| vgadonut | 2 + 2 | 1 | B | 284.2 | 305.1 | +7.4 |
| vgadonut | 2 + 2 | 2 | A | 282.3 | 304.3 | +7.8 |
| vgadonut | 2 + 2 | 2 | B | 284.1 | 302.5 | +6.5 |
| vgadonut | 2 + 2 | 3 | A | 246.8 | 270.2 | +9.5 |
| vgadonut | 2 + 2 | 3 | B | 249.2 | 266.9 | +7.1 |
| nyancat | level bench | 1 | - | 112.0 | 137.2 | +22.5 |
| nyancat | level bench | 2 | - | 113.9 | 127.4 | +11.8 |
| nyancat | level bench | 3 | - | 114.7 | 134.9 | +17.6 |

| project | bench | pairs | median overhead (%) | lowest (%) | highest (%) | pairs span 5% | verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| colorbars | 2 + 2 | 6 | +6.0 | +3.0 | +9.0 | yes | inconclusive |
| rle_vga | 2 + 2 | 6 | +20.7 | +8.8 | +32.7 | no | over |
| nyan | 2 + 2 | 6 | +4.4 | +0.1 | +8.7 | yes | inconclusive |
| cfib_demo | 2 + 2 | 6 | +9.6 | +2.9 | +17.8 | yes | inconclusive |
| metaballs | 2 + 2 | 6 | +7.8 | +4.3 | +11.7 | yes | inconclusive |
| tomkeddie_a | 2 + 2 | 6 | +6.9 | -2.6 | +9.2 | yes | inconclusive |
| vgadonut | 2 + 2 | 6 | +7.2 | +5.7 | +9.5 | no | over |
| nyancat | level bench | 3 | +17.6 | +11.8 | +22.5 | no | over |

- **Verdict:** inconclusive when the pairs span 5% (lowest at or below 5%, highest above), however the median falls.
- **Over:** rle_vga, vgadonut (lowest pair +5.7%) and nyancat.
- **Inconclusive:** colorbars, nyan, cfib_demo, metaballs, tomkeddie_a. Pairs in the same round differ by up to 8.9 points (rle_vga round 1: +25.2% and +16.3%; nyan round 1: +8.7% and +1.9%). colorbars' level 1 against no trace in the level bench below is +1.6%, against its +6.0% median here.
- **nyancat** (bench "level bench") comes from a different shape: 5 models at once, one without the trace and four at different levels, so one pair a round.

### kTraceZstdLevel

The same harness, rebuilt through `job.build` with only the level changed. 20 s runs, all 5 at once, 3 rounds.

| project | variant | round 1 wall (s) | round 2 wall (s) | round 3 wall (s) | median (s) | against no trace (%) | trace (bytes) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| colorbars | no trace | 99.0 | 96.4 | 97.7 | 97.7 | 0.0 | - |
| colorbars | level 1 | 98.1 | 99.3 | 105.1 | 99.3 | +1.6 | 180,815 |
| colorbars | level -1 | 98.5 | 102.9 | 105.9 | 102.9 | +5.2 | 285,809 |
| colorbars | level -3 | 102.5 | 107.2 | 104.0 | 104.0 | +6.4 | 166,808 |
| colorbars | level -5 | 106.3 | 107.1 | 105.1 | 106.3 | +8.8 | 210,785 |
| nyancat | no trace | 112.0 | 113.9 | 114.7 | 113.9 | 0.0 | - |
| nyancat | level 1 | 137.2 | 127.4 | 134.9 | 134.9 | +18.4 | 139,329,744 |
| nyancat | level -1 | 136.9 | 128.0 | 133.8 | 133.8 | +17.5 | 198,514,689 |
| nyancat | level -3 | 136.7 | 128.5 | 134.3 | 134.3 | +17.9 | 178,290,033 |
| nyancat | level -5 | 134.3 | 130.7 | 134.2 | 134.2 | +17.8 | 223,866,179 |

No level beats 1, so [`tb.cpp`](../../../ttvga/harness/tb.cpp) keeps level 1 and nothing is committed. Compression is not where nyancat's time goes.

### The push is inline

[`objdump`](https://sourceware.org/binutils/docs/binutils/objdump.html) `-d -C` of colorbars' `Vtop`, its trace call sites in [`bench/objdump-colorbars-trace-calls.txt`](bench/objdump-colorbars-trace-calls.txt):

| callee | call sites |
| --- | ---: |
| `vgacap_trace_push` / `vgacap_trace_repeat2` (fast paths) | 0 |
| `vgacap_trace_slow` | 4 |
| `vgacap_trace_repeat2_slow` | 1 |
| `raw_slow` (tb.cpp) | 1 |
| `vgacap_trace_block_begin` | 4 |
| `vgacap_trace_block_end_runs` | 4 |

The fast paths are inlined. What remains is the slow path, taken on every pin change.

### Pin changes against the overhead

`tracetool info` of each job's trace (both halves of each clock), against the side-by-side median:

| project | samples | `uo_out` changes | `uio_out` changes | trace (bytes) | side-by-side overhead (%) |
| --- | ---: | ---: | ---: | ---: | ---: |
| tomkeddie_a | 3,024,926,132 | 9,786,169 | 6,194,808 | 113,342 | +6.9 |
| metaballs | 6,006,526,260 | 7,065,081 | 0 | 1,332,139 | +7.8 |
| colorbars | 3,024,787,222 | 15,887,545 | 37,809,840 | 556,030 | +6.0 |
| nyan | 3,004,255,510 | 13,384,881 | 23,288,802 | 51,778,941 | +4.4 |
| cfib_demo | 6,007,574,420 | 59,159,422 | 11,746,027 | 20,589,332 | +9.6 |
| vgadonut | 5,767,601,872 | 457,046,574 | 0 | 167,330,036 | +7.2 |
| nyancat | 3,024,787,222 | 995,902,445 | 496,828,096 | 416,434,073 | +17.6 |
| rle_vga | 2,883,211,220 | 3,611,225 | 2,883,206,512 | 18,388,738 | +20.7 |

- nyancat changes `uo_out` on a third of its samples. It is over, and the slow path is where its time goes (no zstd level helps).
- rle_vga's QSPI clock changes `uio_out` on every sample, yet side by side it is the worst at +20.7% (+8.8 to +32.7%): the slow path on every sample. The pilot's indicative +10.6% understated it.
- vgadonut, over with every pair above 5% (+5.7 to +9.5%), changes `uo_out` on 7.9% of its samples.
- The quiet designs are inconclusive: metaballs (+7.8% median, a change on 0.1% of samples) and tomkeddie_a (+6.9%) have pairs on both sides of 5%. Their medians, under this load (24 models at once on a host already at about 0.6 a CPU), sit above the 1.5-2.6% the trace-speed work measured on a quieter host.
- The scope's CPUQuota of 200% is shared by the simulation thread, the trace compressor thread and the capture's ffmpeg. On a busy design the compressor's CPU therefore also shows up as wall time.
- The next fix in the plan is the [format note](https://github.com/mithro/vgacap/blob/m10-format-note/docs/design/2026-11-25-format-v2-runs.md)'s planar alternative: `uo_out` as plain bytes per sample, the other pins as 64-bit change events. That is vgacap work, and goes to the controller with this profile.

## Step 3: post-simulation CPU

### 1. A lower store level

`vgacap-sample` alone on dvd_screensaver's trace (3,568 of 3,596 frames distinct, ratio 0.99), centre-v1, queue-sized scope, interleaved, 3 rounds:

| `--store-level` | round 1 CPU (s) | round 2 CPU (s) | round 3 CPU (s) | median CPU (s) | store (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 (default) | 22.62 | 23.11 | 22.50 | 22.62 | 139,780 |
| 1 | 21.75 | 22.03 | 22.38 | 22.03 | 144,947 |
| -1 | 22.08 | 21.83 | 22.66 | 22.08 | 143,923 |

Saving: 0.6 s of dvd's 131.3 s post-simulation CPU. It is not committed as a derive rule, because it does not change the result against the budget.

### Where derive's CPU goes

[gprof](https://sourceware.org/binutils/docs/gprof/) of a `-pg` copy of `vgacap-sample` (built aside from the pinned c7176da) on dvd_screensaver's trace; flat profiles in [`bench/gprof-default.txt`](bench/gprof-default.txt) and [`bench/gprof-both.txt`](bench/gprof-both.txt):

| function | default sampler: self (s) | default: share (%) | both samplers: self (s) | both: share (%) |
| --- | ---: | ---: | ---: | ---: |
| `sha256_transform` | 12.09 | 53.9 | 22.49 | 46.9 |
| `sha256_update` | 4.07 | 18.2 | 7.92 | 16.5 |
| `on_raw` | 3.62 | 16.2 | 3.24 | 6.8 |
| `ZSTD_ldm_generateSequences` (the store) | 1.91 | 8.5 | 3.98 | 8.3 |
| `vgahash_fnv1a64_tb2026_rgb888` | - | - | 4.54 | 9.5 |
| `tbv1_push_runs` | - | - | 4.07 | 8.5 |
| total | 22.4 | 100 | 47.9 | 100 |

- One sampler makes 34,390,797 transform calls of 64 bytes, which is 2.2 GB for 1.1 GB of frames: each 307,200-byte frame is hashed twice, at about 136 MB/s.
- `-pg` adds a counting call to every function call, so the sha256 functions (34 million calls) carry most of that overhead and their share is overstated. The `-pg` build took 23.7 s CPU against the release build's 22.6 s.

derive's own Python, dvd_screensaver, both samplers, after the pngio fix below:

| part | CPU (s) |
| --- | ---: |
| derive total | 77.1 |
| children: vgacap-sample, tracetool | 52.6 |
| Python: the PNG pipe reader | 23.8 |
| of which `pngio.write_rgb6` | 9.1 |
| Python: everything else | 0.7 |

The rest of the reader (14.7 s) reads 2.2 GB from the pipe and takes a SHA-256 of each record, so PNGs can be shared between samplers.

### pngio: translate instead of max()

Commit [5c4f797](https://github.com/mithro/tinytapeout-vga-videos/commit/5c4f797), [`pngio.py`](../../../ttvga/harness/pngio.py). `max()` over a frame's bytes walked Python ints: 5.3 ms of `write_rgb6`'s 6.1 ms per 640x480 frame. derive in a queue-sized scope, interleaved, 3 rounds:

| project | samplers | harness | round 1 CPU (s) | round 2 CPU (s) | round 3 CPU (s) | median CPU (s) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| dvd_screensaver | both | before | 99.04 | 113.03 | 99.53 | 99.53 |
| dvd_screensaver | both | after | 81.26 | 84.68 | 85.77 | 84.68 |

One run each, centre-v1 only (the default after the re-run):

| project | budget (s) | before CPU (s) | after CPU (s) |
| --- | ---: | ---: | ---: |
| dvd_screensaver | 17.8 | 61.3 | 38.9 |
| nyancat | 20.3 | 113.8 | 103.6 |
| metaballs | 33.6 | 98.4 | 74.5 |
| vgadonut | 38.0 | 82.7 | 71.4 |

### 3. The second sampler only on request

This is already the default (Ruling W): without `--tb-v1` a job runs centre-v1 alone. The pilot ran `--tb-v1`, as step 4 will.

### Still missed

The post-simulation target is still missed on every project but mandelbrot, with centre-v1 alone too.

On dvd_screensaver, centre-v1 alone:

| part | CPU (s) |
| --- | ---: |
| derive now | 38.9 |
| of which vgacap-sample's SHA-256 | 16.2 |
| SHA-256 once, at 400 MB/s (about hashlib's speed on this host) | 2.8 |
| derive after the vgacap fix | 25.5 |
| budget | 17.8 |

SHA-256 is about 41% of it. Even after the vgacap fix dvd stays over its budget.

Left for the controller, largest first:
1. vgacap: hash each frame once, with a faster SHA-256 (gprof above);
2. vgacap: the planar trace layout for busy designs (recording, above), which also cuts the compressor's CPU;
3. this repo: the PNG pipe reader (14.7 s on dvd), for example no SHA-256 per record when only one sampler runs;
4. this repo: `tracetool uohash` and the trace SHA-256 on busy traces (rle_vga: derive 139 s against 64 s for both samplers alone).

# Plan Task 21: correctness, formats, viewers

2026-11-27, all times UTC. [Plan Task 21](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-21-pilot-rollout-step-2-correctness-formats-viewers).

The 11 projects' published frames were re-derived on the host earlier today in the XXH3-128 format:
- this repository at [26b1004](https://github.com/mithro/tinytapeout-vga-videos/commit/26b1004);
- vgacap at [4a3c670](https://github.com/mithro/vgacap/commit/4a3c6701638c67956b54d5dee8f589e89e869b32) ([`tools.toml`](../../../ttvga/tools.toml));
- the published files read in place, under host.toml's `frames_root` (written `<frames_root>` below).

## Step 1: tb-v1's FNV against git

[`correctness.py`](correctness.py) reads each project's published `<frames_root>/<id>/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt` and the committed [`data/results/<id>/frames/tb-v1/`](../../../data/results/) file with vgacap's [`framesfile.read_hash_file`](https://github.com/mithro/vgacap/blob/4a3c6701638c67956b54d5dee8f589e89e869b32/python/vgacap/framesfile.py).

| project | frames | hash lines equal | file bytes equal |
| --- | ---: | --- | --- |
| tt08/tt_um_a1k0n_nyancat | 3,596 | yes | yes |
| tt08/tt_um_johshoff_metaballs | 4,331 | yes | yes |
| ttihp25a/tt_um_rebeccargb_colorbars | 3,596 | yes | yes |
| ttihp25a/tt_um_rejunity_atari2600 | 3,596 | yes | yes |
| tt05/tt_um_tomkeddie_a | 3,736 | yes | yes |
| ttihp25a/tt_um_cfib_demo | 3,571 | yes | yes |
| ttihp25a/tt_um_a1k0n_vgadonut | 3,597 | yes | yes |
| tt08/tt_um_nyan | 3,434 | yes | yes |
| ttihp25a/tt_um_MichaelBell_rle_vga | 3,600 | yes | yes |
| tt08/tt_um_MichaelBell_mandelbrot | 3,355 | yes | yes |
| tt07/tt_um_tinytapeout_dvd_screensaver | 3,596 | yes | yes |

No difference: all 11 files are byte-identical to git. Output: [`logs/correctness.md`](logs/correctness.md), Step 1.

## Step 2: distinct counts

From the published `frames.txt` (`distinct:` lines) and the published FNV file (distinct non-gap values).

| project | tb-v1 distinct XXH3-128 | centre-v1 distinct XXH3-128 | distinct FNV | XXH3-128 minus FNV |
| --- | ---: | ---: | ---: | ---: |
| tt08/tt_um_a1k0n_nyancat | 3,530 | 3,530 | 3,530 | 0 |
| tt08/tt_um_johshoff_metaballs | 4,325 | 4,325 | 4,325 | 0 |
| ttihp25a/tt_um_rebeccargb_colorbars | 1 | 1 | 1 | 0 |
| ttihp25a/tt_um_rejunity_atari2600 | 1,609 | 1,609 | 1,609 | 0 |
| tt05/tt_um_tomkeddie_a | 636 | 636 | 636 | 0 |
| ttihp25a/tt_um_cfib_demo | 2,320 | 2,320 | 2,320 | 0 |
| ttihp25a/tt_um_a1k0n_vgadonut | 3,597 | 3,597 | 3,597 | 0 |
| tt08/tt_um_nyan | 2 | 2 | 2 | 0 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 1 | 1 | 0 |
| tt08/tt_um_MichaelBell_mandelbrot | 103 | 103 | 103 | 0 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 3,568 | 3,568 | 3,568 | 0 |

| quantity | value |
| --- | ---: |
| committed FNV files | 408 |
| distinct FNV values, summed per project | 543,730 |

Output: [`logs/correctness.md`](logs/correctness.md), Step 2.

## Step 3: tb-v1 against centre-v1

[`correctness.py`](correctness.py) runs [`tt-vga frames compare`](../../../ttvga/frames.py) with tb-v1 as A and centre-v1 as B, and [`tt-vga frames diff`](../../../ttvga/frames.py) on frame `first_mismatch` of both. The output and the PNGs (`a.png` tb-v1, `b.png` centre-v1, `mask.png`) are in [`frames/`](frames/), one directory per project. Output: [`logs/correctness.md`](logs/correctness.md), Step 3, and [`logs/compare-all.log`](logs/compare-all.log), the same compares run by hand first.

| project | centre-v1 cpp | tb-v1 cpp | first mismatch | offset | start clock delta | differing pixels | diff |
| --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| tt08/tt_um_a1k0n_nyancat | 1 | 1 | none | 0 | -944 | - | [compare](frames/tt08__tt_um_a1k0n_nyancat/compare.txt) |
| tt08/tt_um_johshoff_metaballs | 1 | 1 | none | 0 | -5384 | - | [compare](frames/tt08__tt_um_johshoff_metaballs/compare.txt) |
| ttihp25a/tt_um_rebeccargb_colorbars | 1 | 1 | none | 0 | -944 | - | [compare](frames/ttihp25a__tt_um_rebeccargb_colorbars/compare.txt) |
| ttihp25a/tt_um_rejunity_atari2600 | 1 | 1 | none | 0 | -944 | - | [compare](frames/ttihp25a__tt_um_rejunity_atari2600/compare.txt) |
| tt05/tt_um_tomkeddie_a | 1 | 1 | 0 | none | -942 | 1,122 | [frame 0](frames/tt05__tt_um_tomkeddie_a/) |
| ttihp25a/tt_um_cfib_demo | 2 | 2 | 0 | none | -1888 | 14,235 | [frame 0](frames/ttihp25a__tt_um_cfib_demo/) |
| ttihp25a/tt_um_a1k0n_vgadonut | 1.90625 | 1.90625 | 0 | none | -1799 | 65,089 | [frame 0](frames/ttihp25a__tt_um_a1k0n_vgadonut/) |
| tt08/tt_um_nyan | 1 | 1.04 | 0 | none | -1008 | 28,371 | [frame 0](frames/tt08__tt_um_nyan/) |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 0.952381 | none | 0 | -3184 | - | [compare](frames/ttihp25a__tt_um_MichaelBell_rle_vga/compare.txt) |
| tt08/tt_um_MichaelBell_mandelbrot | 4 | 4.26667 | 0 | none | -35744 | 97,586 | [frame 0](frames/tt08__tt_um_MichaelBell_mandelbrot/) |
| tt07/tt_um_tinytapeout_dvd_screensaver | 1 | 1 | none | 0 | -944 | - | [compare](frames/tt07__tt_um_tinytapeout_dvd_screensaver/compare.txt) |

- Every project has the same number of frames in both samplers and no gaps. Where they differ, they differ from frame 0 and no offset up to ±120 lines them up: the crop differs, not the frame cut.
- The start clock delta is the same for every frame of a project (one value per [`compare.txt`](frames/)): centre-v1 starts each frame at the hsync edge of the first vsync line, tb-v1 at the end of the vsync pulse.
- **tomkeddie_a:** both samplers capture 640x504, not the mode's 640x480 (`height: 504`, `mode: 640x480@60`), which is why centre-v1's `porches` are 47 and 0.
  - In tb-v1's `a.png` column 639 is black on every row; in centre-v1's `b.png` it is blue like the rest of the playfield.
  - So tb-v1's window starts one pixel late and takes in a blanking pixel; centre-v1's 640 columns are all active. The mask is the one-pixel shift of every vertical edge.
- **nyan:** the design's line is 832 clocks, not the mode's 800: `frame_clocks` is 436,800 = 832 x 525.
  - tb-v1's cpp of 1.04 is 832/800: it stretches the mode's 800-clock line over the design's 832. centre-v1's cpp of 1 is the design's real pixel clock.
  - In the committed PNGs the grey cat is 238 pixels wide in tb-v1 (x 167 to 405) and 247 in centre-v1 (x 152 to 399): tb-v1's is about 3.6% narrower, about 1/1.04.
  - The black band on the left is 29 pixels in tb-v1 and 8 in centre-v1 (`suggested_offset` 8).
- **mandelbrot:** see the check table below. tb-v1's last non-black row is 469; centre-v1's is 477, with rows 478 and 479 black.

The three projects the plan names, from centre-v1's `frames.txt`:

| project | cpp wanted | cpp | `colour_changes_off_grid` | `outside` | `suggested_offset` x | `suggested_offset` y | `porches` x | `porches` y | as wanted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| tt08/tt_um_nyan | 1 | 1 | 0 | 4,472 | 8 | -1 | 72 | 33 | **no** |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 1 | 0 | 0 | 0 | 0 | 85 | 15 | yes |
| tt08/tt_um_MichaelBell_mandelbrot | 4 | 4 | 16,716,630 | 161,110 | -2 | -2 | 169 | 8 | **no** |

- nyan: cpp and `colour_changes_off_grid` as wanted; `outside` is 4,472, suggested offset (8, -1).
- mandelbrot: cpp as wanted, but **every** colour change is off centre-v1's 4-clock grid: `colour_changes_off_grid` 16,716,630 of `colour_changes` 16,716,630, 100%.
  - `outside` is 161,110 and the suggested offset (-2, -2). Rows 478 and 479 of centre-v1's frame are black, as the -2 rows suggest.
  - 100% off grid is a systematic phase or period error, not noise. It is recorded as a **candidate centre-v1 grid-phase bug** for the vgacap session (reported via the controller), on the same terms as Step 4's rule.
- No override was set for either.

cpp = 1 projects (centre-v1) where the two samplers agree frame for frame:
- tt08/tt_um_a1k0n_nyancat
- tt08/tt_um_johshoff_metaballs
- ttihp25a/tt_um_rebeccargb_colorbars
- ttihp25a/tt_um_rejunity_atari2600
- ttihp25a/tt_um_MichaelBell_rle_vga (tb-v1's cpp is 0.95; one distinct frame)
- tt07/tt_um_tinytapeout_dvd_screensaver

The cpp = 1 projects that do not agree: tomkeddie_a and nyan.

## Step 4: calibration designs

[`tt-vga queue start`](../../../ttvga/remote.py) `--only testpatterns --timeout 10800` ran the 10 calibration jobs from 08:51 to 08:58 (the queue's status and log: [`logs/testpatterns-queue-status.log`](logs/testpatterns-queue-status.log); 10 done, 0 with errors, `published=False`). Each job keeps its trace and centre-v1 output in its work directory's `kept/`.

[`calibration.py`](calibration.py), run under [tt-vga-testpatterns](https://github.com/mithro/tt-vga-testpatterns/tree/1ff01b15eb0a9f624b45d38c01c7e010e5bbdd8d)' own environment (`uv run --project`), compares each distinct frame, written as PNG by [`tt-vga frames to-png`](../../../ttvga/frames.py), with [`tools/render.py`](https://github.com/mithro/tt-vga-testpatterns/blob/1ff01b15eb0a9f624b45d38c01c7e010e5bbdd8d/tools/render.py) for that design and `ui_in` ([`overrides/testpatterns/`](../../../overrides/testpatterns/)). For counter and prbs it decodes the frame counter from the frame, as [`tools/check.py`](https://github.com/mithro/tt-vga-testpatterns/blob/1ff01b15eb0a9f624b45d38c01c7e010e5bbdd8d/tools/check.py) does, and checks that it steps by 1 from each captured frame to the next.

| design | `ui_in` | mode | expected mode | width | height | frames | gaps | distinct | equal to render | counter steps by 1 | result |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| tt_um_vgacal_bars | 0 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_grid | 0 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_counter | 0 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 256 | 256 | yes | pixel-exact |
| tt_um_vgacal_prbs | 0 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 256 | 256 | yes | pixel-exact |
| tt_um_vgacal_modes_m0 | 0 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m1 | 1 | 800x600@60 | 800x600@60 | 800 | 600 | 2,278 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m2 | 2 | 720x400@70 | 720x400@70 | 720 | 400 | 3,738 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m0_hneg | 4 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m0_vneg | 8 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m0_hvneg | 12 | 640x480@60 | 640x480@60 | 640 | 480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |

- All 10 are pixel-exact, including 720x400 and the three polarity cases. No centre-v1 bug. Output: [`logs/calibration.md`](logs/calibration.md).
- Each centre-v1 `frames.txt` has `outside` 0 and `colour_changes_off_grid` 0.
- The check fails when it should: with bars' frame put in grid's place it reports 302,400 differing pixels, and with one prbs frame swapped for another the counter step fails ([`logs/calibration-negative-control.md`](logs/calibration-negative-control.md)).

## Step 5: hardware

Searched for a [vgacap](https://github.com/mithro/vgacap) capture of each of the four; the paths searched are in [`logs/hardware-search.md`](logs/hardware-search.md):
- the captures of the [tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) hardware runs (the first validation and the library batches, on the FPGA harness's board);
- tt-harness-fpga-vga's `work/run/<id>/outcome.json` and its results;
- vgacap's and [tt-vga-capture](https://github.com/mithro/tt-vga-capture)'s capture files.

| project | FPGA build | capture | rgb6 XXH3-128 compared |
| --- | --- | --- | --- |
| ttihp25a/tt_um_cfib_demo | timing-fail | none | - |
| ttihp25a/tt_um_a1k0n_vgadonut | timing-fail | none | - |
| ttihp25a/tt_um_MichaelBell_rle_vga | ok | none | - |
| tt08/tt_um_MichaelBell_mandelbrot | timing-fail | none | - |

- The FPGA hardware batches ran only designs with a clean build; three of the four fail timing, and none of the four is among the designs run.
- No board was claimed, flashed or power-cycled for this step.
- A future comparison must count clocks or frames, not wall time: real boards run 25.175 MHz designs at 25.25 MHz, the SDK's nearest clock.

## Step 6: formats

**The trace formats** (VGCH, FST, sigrok and others) are not measured here (Ruling BU). The [trace-format study](https://github.com/mithro/vgacap/blob/847a17f4a5e87a5b509f1722f0237de5d99ceb6a/docs/design/2026-11-27-trace-format-study.md) (vgacap branch `trace-format-study`, [847a17f](https://github.com/mithro/vgacap/commit/847a17f4a5e87a5b509f1722f0237de5d99ceb6a)) covers them.

**The frames store.** [`scripts/pilot_formats.py`](../../../scripts/pilot_formats.py) reads each published centre-v1 store (one zstd stream with long-distance matching, as vgacap-sample writes it) and recompresses it as one zstd frame per distinct image (level 3, no long-distance matching), adding 8 bytes per image for an offset index. The read time is for the middle distinct frame, median of 5, one thread, wall time, on the host at a load of about 1.4 a CPU. The stream is decompressed from its start up to that frame. Output: [`logs/formats.md`](logs/formats.md) (run again on 2026-11-28 for the busy-project median; sizes unchanged, times up to 23% from the first run's).

| project | distinct frames | uncompressed (bytes) | stream (bytes) | one frame per image (bytes) | size ratio | stream: read middle (ms) | one frame per image: read middle (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt08/tt_um_a1k0n_nyancat | 3,530 | 1,084,416,000 | 4,539,138 | 13,568,241 | 2.99 | 1250.5 | 0.09 |
| tt08/tt_um_johshoff_metaballs | 4,325 | 2,076,000,000 | 2,237,504 | 1,917,974 | 0.86 | 2468.5 | 0.15 |
| ttihp25a/tt_um_rebeccargb_colorbars | 1 | 307,200 | 134 | 191 | 1.43 | 0.2 | 0.04 |
| ttihp25a/tt_um_rejunity_atari2600 | 1,609 | 494,284,800 | 312,552 | 5,278,004 | 16.89 | 652.5 | 0.10 |
| tt05/tt_um_tomkeddie_a | 636 | 205,148,160 | 113,758 | 274,165 | 2.41 | 313.4 | 0.08 |
| ttihp25a/tt_um_cfib_demo | 2,320 | 712,704,000 | 2,156,619 | 5,348,618 | 2.48 | 962.7 | 0.07 |
| ttihp25a/tt_um_a1k0n_vgadonut | 3,597 | 1,104,998,400 | 27,660,224 | 47,486,237 | 1.72 | 1763.9 | 0.33 |
| tt08/tt_um_nyan | 2 | 614,400 | 1,164 | 5,551 | 4.77 | 0.5 | 0.15 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 307,200 | 29 | 38 | 1.31 | 0.3 | 0.06 |
| tt08/tt_um_MichaelBell_mandelbrot | 103 | 31,641,600 | 560,261 | 685,438 | 1.22 | 23.1 | 0.11 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 3,568 | 1,096,089,600 | 139,780 | 3,400,570 | 24.33 | 1262.8 | 0.08 |

Projected to the 408 projects with frames, one sampler, from the pilot's bytes per distinct frame and the committed 543,730 distinct frames:

| quantity | stream | one frame per image |
| --- | ---: | ---: |
| pilot bytes | 37,721,163 | 77,965,027 |
| pilot distinct frames | 19,692 | 19,692 |
| bytes per distinct frame | 1,916 | 3,959 |
| 408 projects (GB) | 1.04 | 2.15 |
| read cost per frame decompressed (ms, median of 8 projects over 100 distinct) | 0.820 | - |
| read one image (ms, median of the same 8) | - | 0.094 |
| read the middle frame, mean project of 1,333 distinct (s) | 0.55 | 0.0001 |
| read the middle frame, largest project of 4,325 distinct (s) | 1.77 | 0.0001 |

- Per frame, the stream is about half the size: 2.1 times smaller over the pilot, and up to 24 times on designs whose frames differ only a little (dvd_screensaver, atari2600). On metaballs (800x600) it is larger.
- One frame per image reads any frame in under 0.4 ms; the stream needs time proportional to the frame's position, up to 2.5 s in the pilot.
- The projection assumes the pilot's bytes per distinct frame hold for all 408. The pilot was chosen for busy designs, so it likely overstates both sizes.
- The 408-project read times assume 640x480 frames; metaballs' 800x600 frames took 2.47 s, not the 1.77 s projected.
- The per-frame medians leave out the three projects with 1 or 2 distinct frames, whose times are fixed overhead.

## Step 7: viewers

Frame 100 of nyancat and of cfib_demo, exported by [`tt-vga trace export`](../../../ttvga/traces.py) (`--from` the frame's start clock, `--to` one `frame_clocks` later, `--sampler-frames` centre-v1's `frames.txt`), as FST and as VCD, from the published VGCH v2 traces.

| project | clocks | FST (bytes) | VCD (bytes) | value changes | fst2vcd equal to VCD |
| --- | ---: | ---: | ---: | ---: | --- |
| tt08/tt_um_a1k0n_nyancat | 420,000 | 50,784 | 25,354,745 | 1,946,638 | yes |
| ttihp25a/tt_um_cfib_demo | 840,000 | 19,731 | 30,719,333 | 1,731,441 | yes |

- [`fst2vcd`](https://gtkwave.github.io/gtkwave/) (from the pinned [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-14)) of each FST against the VCD, by [`viewers/vcd_equal.py`](viewers/vcd_equal.py): the same set of (time, signal, value) changes ([nyancat](viewers/tt08_tt_um_a1k0n_nyancat/vcd_equal.txt), [cfib_demo](viewers/ttihp25a_tt_um_cfib_demo/vcd_equal.txt); first run: [`logs/vcd-equal.log`](logs/vcd-equal.log)).
- Screenshots by [`viewers/screenshot.sh`](viewers/screenshot.sh) under [`xvfb-run`](https://manpages.debian.org/trixie/xvfb/xvfb-run.1.en.html) on the host, loading the `.gtkw` and `.sucl` [vgacap-export](https://github.com/mithro/vgacap/blob/4a3c6701638c67956b54d5dee8f589e89e869b32/src/tools/vgacap_export.c) wrote beside the FST.
- In [`viewers/`](viewers/): the FSTs, `.gtkw`, `.sucl` and screenshots. The VCDs are over 5 MB and are not committed. The save files' absolute paths are cut to the file name: open them from their directory.

| project | [GTKWave](https://gtkwave.github.io/gtkwave/) 3.3.121 | [Surfer](https://gitlab.com/surfer-project/surfer) 0.7.0 |
| --- | --- | --- |
| tt08/tt_um_a1k0n_nyancat | [screenshot](viewers/tt08_tt_um_a1k0n_nyancat/tt08_tt_um_a1k0n_nyancat_f100_gtkwave.png) | [screenshot](viewers/tt08_tt_um_a1k0n_nyancat/tt08_tt_um_a1k0n_nyancat_f100_surfer.png) |
| ttihp25a/tt_um_cfib_demo | [screenshot](viewers/ttihp25a_tt_um_cfib_demo/ttihp25a_tt_um_cfib_demo_f100_gtkwave.png) | [screenshot](viewers/ttihp25a_tt_um_cfib_demo/ttihp25a_tt_um_cfib_demo_f100_surfer.png) |

- GTKWave: both groups (`ports`, `decoded`) and all signals, zoomed to the frame.
- Surfer: both groups and all signals load, but the view spans from time 0 to the frame's end, so the frame (from 1.75 s) is a sliver at the right edge. The `.sucl` has no zoom command. Appending `zoom_fit` changes nothing; `zoom_to_fit` is refused (`InvalidParameter`). For vgacap: a `.sucl` for a slice that does not start at 0 needs a way to show only the slice.
- This check ran against the VGCH v2 traces. A planar trace layout is under decision ([the trace-format study](https://github.com/mithro/vgacap/blob/847a17f4a5e87a5b509f1722f0237de5d99ceb6a/docs/design/2026-11-27-trace-format-study.md)); if it is adopted, Step 7 must be repeated.

## Step 8: upload listing

Done in plan Task 20: see [The upload's listing (Ruling BK)](#the-uploads-listing-ruling-bk) above (about 189 s of the 5-minute interval for both samplers at 408 projects, 107 s for centre-v1 alone). Not measured again.

## Sampler window flags

2026-11-28. [`window_flags.py`](window_flags.py) reads both samplers' published `<frames_root>/<id>/<sampler>/frames.txt`, read only, and computes each one's `window` with [`derive.windows`](../../../ttvga/harness/derive.py), the code that writes it into `result.json` ([consumers.md](../../consumers.md#sampler-windows)). The files are the ones Steps 1-3 read (vgacap [4a3c670](https://github.com/mithro/vgacap/commit/4a3c6701638c67956b54d5dee8f589e89e869b32)); the modes are vgacap's tables at the pin, [da9ea98](https://github.com/mithro/vgacap/commit/da9ea98b287740aa11b99263948bb3ca62d961c4).

| project | mode | centre-v1 cpp | tb-v1 cpp | frame_clocks | centre-v1 mode_frame_clocks | `outside` | `suggested_offset` | tb-v1 line_clocks | tb-v1 lines | mode_line_clocks | mode_lines | centre-v1 exact | tb-v1 exact |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| tt08/tt_um_a1k0n_nyancat | 640x480@60 | 1 | 1 | 420,000 | 420,000 | 640 | (0, -1) | 800 | 525 | 800 | 525 | **no** | yes |
| tt08/tt_um_johshoff_metaballs | 800x600@72 | 1 | 1 | 692,640 | 692,640 | 0 | (0, 0) | 1,040 | 666 | 1,040 | 666 | yes | yes |
| ttihp25a/tt_um_rebeccargb_colorbars | 640x480@60 | 1 | 1 | 420,000 | 420,000 | 1,119 | (-1, -1) | 800 | 525 | 800 | 525 | **no** | yes |
| ttihp25a/tt_um_rejunity_atari2600 | 640x480@60 | 1 | 1 | 420,000 | 420,000 | 22,968 | (0, -33) | 800 | 525 | 800 | 525 | **no** | yes |
| tt05/tt_um_tomkeddie_a | 640x480@60 | 1 | 1 | 404,294 | 420,000 | 0 | (0, 0) | - | - | 800 | 525 | yes | **no** |
| ttihp25a/tt_um_cfib_demo | 640x480@60 | 2 | 2 | 840,000 | 840,000 | 0 | (0, 0) | 1,600 | 525 | 1,600 | 525 | yes | yes |
| ttihp25a/tt_um_a1k0n_vgadonut | 640x480@60 | 1.90625 | 1.90625 | 800,625 | 800,625 | 1,220 | (0, -1) | 1,525 | 525 | 1,600 | 525 | **no** | **no** |
| tt08/tt_um_nyan | 640x480@60 | 1 | 1.04 | 436,800 | 420,000 | 4,472 | (8, -1) | 832 | 525 | 800 | 525 | **no** | **no** |
| ttihp25a/tt_um_MichaelBell_rle_vga | 640x480@75 | 1 | 0.952381 | 400,000 | 420,000 | 0 | (0, 0) | 800 | 500 | 840 | 500 | yes | **no** |
| tt08/tt_um_MichaelBell_mandelbrot | 640x480@75 | 4 | 4.26667 | 1,788,416 | 1,680,000 | 161,110 | (-2, -2) | 3,584 | 499 | 3,360 | 500 | **no** | **no** |
| tt07/tt_um_tinytapeout_dvd_screensaver | 640x480@60 | 1 | 1 | 420,000 | 420,000 | 0 | (0, 0) | 800 | 525 | 800 | 525 | yes | yes |

- centre-v1 is not exact on the six projects with `outside` > 0: nyancat, colorbars, atari2600, vgadonut, nyan and mandelbrot.
- Off-mode timing, `outside` 0: tomkeddie_a and rle_vga. centre-v1 is exact on them, because its `exact` is `outside` alone (ruling CA). Their `frame_clocks` is not `mode_frame_clocks`, so the owner can decide later whether to widen the flag.
- tb-v1 is not exact on tomkeddie_a, vgadonut, nyan, rle_vga and mandelbrot.
  - nyan: `line_clocks` 832 against the mode's 800, 525 lines.
  - rle_vga: 800 against 840, 500 lines.
  - mandelbrot: 3,584 against 3,360, and 499 lines against 500.
  - vgadonut: 1,525 against 1,600. Its cpp of 1.90625 is not a whole number, even after tb-v1's rounding of a cpp within 0.01 of one.
    - This changed in review fix 1. Earlier versions of this table said tb-v1 exact "yes" for vgadonut, when tb-v1 was checked at centre-v1's cpp. That value is no longer current.
  - tomkeddie_a: the line is not measured. tb-v1 rounded 799/800 to cpp 1, and 404,294 is not a whole number of 800-clock lines (it is 799 x 506).
