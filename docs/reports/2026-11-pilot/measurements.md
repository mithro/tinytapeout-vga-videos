# Pilot measurements (plan Task 20, rollout step 2)

2026-11-27. 11 projects run at once on the host, each in its own queue-limited scope (MemoryMax 6G, CPUQuota 200%, TasksMax 64, OOMPolicy=continue), by [`scripts/pilot_measure.py`](../../../scripts/pilot_measure.py) at harness `0b581aeab69291a9` (commit f64607a). The raw records are in [`raw/`](raw/), one per project, and the ids in [`ids.txt`](ids.txt). Host paths in them are replaced by `<staging_dir>`, `<frames_root>` and `~`.

Per project, each under `/usr/bin/time -v`:
1. `job.py --tb-v1 --keep-build --timeout 10800 --grace 120 --seconds 60`, publishing to the frames subtree;
2. the kept `Vtop` 4 times, with the job's cwd and arguments: without `--trace`, with, without, with;
3. `vgacap-sample` alone on the published trace, with its default sampler and with both.

Host load during the run: 45 to 109 on 88 CPUs (0.5 to 1.24 a CPU), from the pilot's progress lines.

Two earlier starts failed and are not in these tables:

| attempt | started (UTC) | what failed | fix |
| --- | --- | --- | --- |
| 1 | 2026-11-27T01:16 | every model aborted: `std::system_error` EAGAIN | cb0f232 `ctx.threads(1)` |
| 2 | 2026-11-27T01:26 | the capture's MJPEG encoder did not open: EAGAIN | f64607a `-cpucount` |
| 3 | 2026-11-27T01:34 | none | - |

Attempt 1: Verilator's context starts 87 idle pool threads on this host. Attempt 2: ffmpeg sizes its encoder threads by the host's 88 CPUs. Both exceed the scope's TasksMax of 64. Attempt 2 was stopped by hand after 50 s.

## The upload's listing

> **The listing grows by about 0.14 ms a file. At 408 projects with tb-v1 it is projected at about 236 s, close to the 5-minute interval, and a run that also transfers new frames already took 247 s.**

From `/var/lib/data-upload/rsync.log` (host local time, ACDT): `Number of files:` and the time from `building file list` to `total size is`.

| run (ACDT) | files | duration (s) | frames in the upload |
| --- | ---: | ---: | --- |
| 2026-11-27T11:38:04 | 62,991 | 24 | none |
| 2026-11-27T12:13:04 | 62,993 | 24 | none |
| 2026-11-27T12:18:04 | 71,479 | 44 | first projects |
| 2026-11-27T12:28:03 | 91,899 | 146 | more projects |
| 2026-11-27T12:38:03 | 102,356 | 247 | more projects |
| 2026-11-27T13:13:03 | 102,579 | 31 | all 11 |
| 2026-11-27T15:03:03 | 102,579 | 31 | all 11 |

| quantity | value |
| --- | ---: |
| files added by 11 projects | 39,588 |
| files per project, both samplers | 3,599 |
| mean listing before | 25.0 s |
| mean listing after | 30.7 s |
| listing time added | 5.7 s |
| listing time per file | 0.14 ms |
| projected files, 408 projects, both samplers | 1.47 M |
| projected listing, 408 projects, both samplers | 236 s |
| projected files, 408 projects, centre-v1 only | 0.73 M |
| projected listing, 408 projects, centre-v1 only | 130 s |

The runs that transferred new frames (146 s, 247 s) are the ones that come close. During the step 4 re-run, with 24 jobs publishing, most runs will transfer.

## Recording

Target: `(wall with trace - wall without) / wall without` at most 5%. Mean of 2 runs each.

| project | wall without (s) | wall with (s) | overhead (%) | ns per clock | clocks | within 5% |
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

Max RSS from `time -v` (the largest single process), and the scope's MemoryPeak (all its processes and page cache), in MB.

| project | job max RSS | model max RSS | sample default max RSS | sample both max RSS | scope MemoryPeak | scope peak tasks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 752 | 62 | 157 | 296 | 875 | 54 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 675 | 67 | 155 | 298 | 779 | 53 |
| tt08/tt_um_MichaelBell_mandelbrot | 741 | 64 | 75 | 115 | 1134 | 53 |
| tt08/tt_um_a1k0n_nyancat | 1803 | 99 | 572 | 712 | 3320 | 61 |
| tt08/tt_um_johshoff_metaballs | 1207 | 69 | 157 | 301 | 1349 | 61 |
| tt08/tt_um_nyan | 1770 | 73 | 75 | 95 | 2061 | 61 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 660 | 109 | 57 | 67 | 738 | 53 |
| ttihp25a/tt_um_a1k0n_vgadonut | 764 | 99 | 331 | 474 | 1932 | 53 |
| ttihp25a/tt_um_cfib_demo | 1818 | 70 | 180 | 317 | 2480 | 61 |
| ttihp25a/tt_um_rebeccargb_colorbars | 1792 | 75 | 28 | 37 | 1984 | 61 |
| ttihp25a/tt_um_rejunity_atari2600 | 1832 | 118 | 743 | 892 | 3999 | 61 |

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

## Sizes

The published directory (`du -b`, hard links once), in kB (1,000 bytes).

| project | trace | centre-v1 store | tb-v1 store | centre-v1 PNGs | tb-v1 PNGs | centre-v1 PNG files | tb-v1 PNG files | whole directory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 113 | 114 | 103 | 2,209 | 2,211 | 636 | 636 | 6,415 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 1,307 | 140 | 140 | 11,306 | 11,306 | 3568 | 3568 | 15,882 |
| tt08/tt_um_MichaelBell_mandelbrot | 14,719 | 560 | 598 | 1,047 | 1,160 | 103 | 103 | 18,995 |
| tt08/tt_um_a1k0n_nyancat | 416,434 | 4,539 | 4,539 | 23,179 | 23,179 | 3530 | 3530 | 451,663 |
| tt08/tt_um_johshoff_metaballs | 1,332 | 2,238 | 2,238 | 14,488 | 14,488 | 4325 | 4325 | 23,918 |
| tt08/tt_um_nyan | 51,779 | 1 | 1 | 10 | 11 | 2 | 2 | 52,359 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 18,389 | 0 | 0 | 2 | 2 | 1 | 1 | 18,926 |
| ttihp25a/tt_um_a1k0n_vgadonut | 167,330 | 27,660 | 27,724 | 79,348 | 79,014 | 3597 | 3597 | 384,087 |
| ttihp25a/tt_um_cfib_demo | 20,589 | 2,157 | 2,154 | 13,727 | 13,746 | 2320 | 2320 | 54,609 |
| ttihp25a/tt_um_rebeccargb_colorbars | 556 | 0 | 0 | 5 | 5 | 1 | 1 | 1,096 |
| ttihp25a/tt_um_rejunity_atari2600 | 596,591 | 313 | 313 | 11,552 | 11,552 | 1609 | 1609 | 610,840 |

## vgacap-sample alone

On the published trace, VGACAP_SAMPLE_DEBUG=1; and the job's derive from result.json.

| project | default wall (s) | default CPU (s) | both wall (s) | both CPU (s) | both debug | job derive wall (s) | job derive CPU (s) | frames | distinct frames |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| tt05/tt_um_tomkeddie_a | 15.1 | 15.1 | 34.7 | 34.7 | trace_passes=1 blocks_decoded=91 | 44.5 | 53.3 | 3736 | 636 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 23.1 | 23.1 | 51.9 | 50.8 | trace_passes=1 blocks_decoded=91 | 85.8 | 113.7 | 3596 | 3568 |
| tt08/tt_um_MichaelBell_mandelbrot | 14.5 | 14.5 | 30.9 | 30.9 | trace_passes=1 blocks_decoded=359 | 32.9 | 34.6 | 3355 | 103 |
| tt08/tt_um_a1k0n_nyancat | 54.8 | 52.7 | 85.8 | 85.7 | trace_passes=1 blocks_decoded=489 | 169.2 | 201.0 | 3596 | 3530 |
| tt08/tt_um_johshoff_metaballs | 38.9 | 38.8 | 86.2 | 86.2 | trace_passes=1 blocks_decoded=180 | 173.8 | 202.3 | 4331 | 4325 |
| tt08/tt_um_nyan | 5.5 | 5.5 | 11.5 | 11.5 | trace_passes=1 blocks_decoded=90 | 14.0 | 14.0 | 3434 | 2 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 51.2 | 51.2 | 64.1 | 64.0 | trace_passes=1 blocks_decoded=1208 | 139.1 | 139.0 | 3600 | 1 |
| ttihp25a/tt_um_a1k0n_vgadonut | 35.9 | 35.8 | 69.2 | 69.1 | trace_passes=1 blocks_decoded=195 | 117.1 | 179.8 | 3597 | 3597 |
| ttihp25a/tt_um_cfib_demo | 20.9 | 20.9 | 44.7 | 44.7 | trace_passes=1 blocks_decoded=180 | 76.5 | 109.8 | 3571 | 2320 |
| ttihp25a/tt_um_rebeccargb_colorbars | 4.8 | 4.8 | 9.8 | 9.8 | trace_passes=1 blocks_decoded=91 | 12.7 | 12.7 | 3596 | 1 |
| ttihp25a/tt_um_rejunity_atari2600 | 53.5 | 53.5 | 78.8 | 70.6 | trace_passes=1 blocks_decoded=569 | 140.2 | 153.0 | 3596 | 1609 |

## Against the targets

| target | limit | projects within | projects over | worst |
| --- | --- | ---: | ---: | --- |
| recording | 5% of wall | 5 | 6 | nyancat 14.8% |
| post-simulation CPU | 5% of simulation CPU | 1 | 10 | nyancat 67% |
| memory | MemoryMax 6 GB | 11 | 0 | atari2600 4.0 GB |
| tasks | TasksMax 64 | 11 | 0 | 61, in the job's encode |
| root volume | `min_free_root_gb` | - | - | atari2600 1.98 GB |

- **Root volume:** the rule gives `min_free_root_gb = 100`, the value host.toml already had. It was written again (`min_free_root_gb = 100`).
- **Tasks:** six projects reach 61 of 64 tasks while job.py encodes (x264 and VP9 with `-cpucount 4`). That leaves 3 tasks of margin.
- **Memory:** the largest single process is x264 at 1.8 GB. MemoryPeak counts the scope's page cache too.
- **dvd_screensaver:** post-simulation CPU 131.3 s against its 17.8 s budget (5% of 356.9 s), with both samplers.

The pilot's wall times move with the host load: the same untraced model differed by up to 16% between its two runs (nyan 344.1 s and 295.9 s). Step 3 therefore runs its variants side by side, at the same moment, instead of one after another.

## Step 3: recording

### Side by side, colorbars

20 s runs, 4 at once, 3 rounds, in queue-sized scopes.

| run | round 1 wall (s) | round 2 wall (s) | round 3 wall (s) | median (s) |
| --- | ---: | ---: | ---: | ---: |
| without trace A | 101.8 | 99.3 | 99.5 | 99.5 |
| with trace A | 107.2 | 105.9 | 104.8 | 105.9 |
| without trace B | 101.2 | 96.1 | 96.7 | 96.7 |
| with trace B | 104.3 | 104.8 | 103.1 | 104.3 |

Median of all 6 without: 99.4 s. Median of all 6 with: 104.8 s. Overhead +5.5%.

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

No level beats 1, so tb.cpp keeps level 1 and nothing is committed. Compression is not where nyancat's time goes.

### The push is inline

`objdump -d -C` of colorbars' `Vtop` (logged on the host as `~/ttvga/work/pilot/diag/objdump-colorbars.txt`):

| callee | call sites |
| --- | ---: |
| `vgacap_trace_push` / `vgacap_trace_repeat2` (fast paths) | 0 |
| `vgacap_trace_slow` | 4 |
| `vgacap_trace_repeat2_slow` | 1 |
| `raw_slow` (tb.cpp) | 1 |
| `vgacap_trace_block_begin` | 4 |
| `vgacap_trace_block_end_runs` | 4 |

The fast paths are inlined. What remains is the slow path, taken on every pin change.

### Where the overhead comes from

`tracetool info` of each job's trace (both halves of each clock):

| project | samples | `uo_out` changes | `uio_out` changes | trace (bytes) | overhead in the pilot (%) | ns per clock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tomkeddie_a | 3,024,926,132 | 9,786,169 | 6,194,808 | 113,342 | 1.31 | 3.2 |
| colorbars | 3,024,787,222 | 15,887,545 | 37,809,840 | 556,030 | 7.33 | 16.5 |
| nyan | 3,004,255,510 | 13,384,881 | 23,288,802 | 51,778,941 | 8.81 | 18.8 |
| rle_vga | 2,883,211,220 | 3,611,225 | 2,883,206,512 | 18,388,738 | 10.59 | 31.8 |
| nyancat | 3,024,787,222 | 995,902,445 | 496,828,096 | 416,434,073 | 14.79 | 33.7 |

- On nyancat a third of the samples change `uo_out`. On rle_vga `uio_out` (its QSPI clock) changes on every sample. Both take the slow path that often.
- The scope's CPUQuota of 200% is shared by the simulation thread, the trace compressor thread and the capture's ffmpeg. On a busy design the compressor's CPU therefore also shows up as wall time.
- The next fix in the plan is the format note's planar alternative (`uo_out` as plain bytes per sample, the other pins as 64-bit change events). That is vgacap work and goes to the controller with this profile.

## Step 3: post-simulation CPU

### 1. A lower store level

`vgacap-sample` alone on dvd_screensaver's trace (3,568 of 3,596 frames distinct, ratio 0.99), centre-v1, queue-sized scope, interleaved, 3 rounds:

| `--store-level` | round 1 CPU (s) | round 2 CPU (s) | round 3 CPU (s) | median CPU (s) | store (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 (default) | 22.62 | 23.11 | 22.50 | 22.62 | 139,780 |
| 1 | 21.75 | 22.03 | 22.38 | 22.03 | 144,947 |
| -1 | 22.08 | 21.83 | 22.66 | 22.08 | 143,923 |

Saving: 0.6 s of dvd's 131.3 s post-simulation CPU. Not committed as a derive rule: it does not change the result against the budget.

### Where derive's CPU goes

gprof of a `-pg` copy of `vgacap-sample` (built aside in `~/ttvga/work/pilot/diag/vgacap-pg`, the pinned c7176da) on dvd_screensaver's trace:

| function | default sampler: self (s) | default: share (%) | both samplers: self (s) | both: share (%) |
| --- | ---: | ---: | ---: | ---: |
| `sha256_transform` | 12.09 | 53.9 | 22.49 | 46.9 |
| `sha256_update` | 4.07 | 18.2 | 7.92 | 16.5 |
| `on_raw` | 3.62 | 16.2 | 3.24 | 6.8 |
| `ZSTD_ldm_generateSequences` (the store) | 1.91 | 8.5 | 3.98 | 8.3 |
| `vgahash_fnv1a64_tb2026_rgb888` | - | - | 4.54 | 9.5 |
| `tbv1_push_runs` | - | - | 4.07 | 8.5 |
| total | 22.4 | 100 | 47.9 | 100 |

- 34,390,797 transform calls of 64 bytes for one sampler is 2.2 GB: each 307,200-byte frame is hashed twice, at about 136 MB/s.
- Hashing each frame once, with a faster SHA-256, would take dvd's centre-v1 from about 22 s to about 9 s (at 400 MB/s, about what hashlib reaches on this host). That is vgacap work (step 2 of the spec's order) and goes to the controller.

derive's own Python, dvd_screensaver, both samplers, after the pngio fix below:

| part | CPU (s) |
| --- | ---: |
| derive total | 77.1 |
| children: vgacap-sample, tracetool | 52.6 |
| Python: the PNG pipe reader | 23.8 |
| of which `pngio.write_rgb6` | 9.1 |
| Python: everything else | 0.7 |

The rest of the reader (14.7 s) reads 2.2 GB from the pipe and takes a SHA-256 of each record, to share PNGs between samplers.

### pngio: translate instead of max() (commit 5c4f797)

`max()` over a frame's bytes walked Python ints: 5.3 ms of `write_rgb6`'s 6.1 ms a 640x480 frame. derive in a queue-sized scope, interleaved, 3 rounds:

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

Already the default (Ruling W): without `--tb-v1` a job runs centre-v1 alone. The pilot ran `--tb-v1`, as step 4 will.

### Still missed

The post-simulation target is still missed on every project but mandelbrot, with centre-v1 alone too. Left for the controller, largest first:
1. vgacap: each frame hashed once, and a faster SHA-256 (gprof above);
2. vgacap: the planar trace layout for busy designs (recording, above), which also cuts the compressor's CPU;
3. this repo: the PNG pipe reader (14.7 s on dvd), for example no SHA-256 per record when only one sampler runs;
4. this repo: `tracetool uohash` and the trace SHA-256 on busy traces (rle_vga: derive 139 s against 64 s for both samplers alone).
