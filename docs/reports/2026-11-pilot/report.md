# Raw traces pipeline: the owner report

2026-11-28. [Plan Task 22](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-22-the-owner-report-rollout-step-3), rollout step 3. This repository at `main` [44a1baa](https://github.com/mithro/tinytapeout-vga-videos/commit/44a1baaf88523f23c373e087cc074ba4d002981a), vgacap pinned at [da9ea98](https://github.com/mithro/vgacap/commit/da9ea98b287740aa11b99263948bb3ca62d961c4) ([`tools.toml`](../../../ttvga/tools.toml)).

The pilot ran 11 projects ([`ids.txt`](ids.txt)) on 2026-11-27; its tables are in [measurements.md](measurements.md). This report projects them to all 408 projects with frames and records the rulings. Under the plan's I12 ruling the re-run (Task 23) does not wait for an answer: an objection is applied afterwards by re-deriving, or for the stored format by re-encoding.

Where the numbers come from:

| source | what | kind |
| --- | --- | --- |
| [measurements.md](measurements.md) | the pilot (Tasks 20 and 21) | measured |
| [`raw/`](raw/) | the pilot's records | measured |
| [`logs/derive-now.jsonl`](logs/derive-now.jsonl) | derive at 44a1baa on the 11 published traces on 2026-11-28 ([setup](logs/derive-now.md)) | measured |
| [`logs/upload-listing-2026-11-28.md`](logs/upload-listing-2026-11-28.md) | the upload's last 12 runs | measured |
| [`logs/report-projection.md`](logs/report-projection.md) | the output of [`report_projection.py`](report_projection.py) | projected |
| [trace-format study](https://github.com/mithro/vgacap/blob/00037fa417057afe7b3df19d4bb2eeb3ffcc1d2f/docs/superpowers/2026-11-27-trace-format-study.md) | trace formats; vgacap branch `trace-format-study` at [00037fa](https://github.com/mithro/vgacap/commit/00037fa417057afe7b3df19d4bb2eeb3ffcc1d2f) | measured |
| [vgacap issue 100](https://github.com/mithro/vgacap/issues/100) | the centre-v1 window investigation | measured |
| [`data/results/*/*/result.json`](../../../data/results/) | the reference run's clocks and distinct frames and timings | committed |

Every projection is linear in one pilot quantity, named where it is used. The pilot was chosen for busy designs, so a projection from its bytes per clock or per distinct frame likely overstates.

## Summary

- **Stored format:** VGCH v2 stays for the re-run. Planar is 0.087 of its size over the pilot and is the owner's open question.
- **Reference sampler:** tb-v1 stays the reference. centre-v1 is pixel-exact on all 10 calibration designs but shows a shifted and cropped part of the picture on mandelbrot (cpp 4). Both samplers are published, each with a `window` flag.
- **Upload:** one upload, as now. The listing is 30 to 31 s today and projected at 189 s of the 300 s interval after the re-run.
- **Re-run:** 24 jobs, `min_free_root_gb = 100`, projected at 5.4 to 5.7 hours of wall time.
- **Budgets:** recording is over 5% on nyancat, rle_vga and vgadonut, with no fix. Post-simulation CPU is now within 5% on 2 of 11 (it was 1), and the trace's own compressor exceeds the whole budget on 8 of 11.
- **Correctness:** tb-v1 reproduces all 11 committed FNV files byte for byte.

## Rulings

Each in the plan's form: "Ruling: <decision> - <reason from the numbers> - <cost if wrong>".

1. **Decision 2, the stored format.** Ruling: VGCH v2 with runs stays the stored format for the Task 23 re-run, and planar is decided later (owner, 2026-11-27: "Re-run now, decide later") - over the 11 pilot traces FST (zlib) is 0.41 of VGCH v2's size (531.92 MB against 1,289.14 MB), which passes the plan's "at most half" test, but FST written on the simulation thread costs 4.1 to 5.1 times VGCH v2 on the busy designs and a cut-short FST gave no samples or crashed libfst's reader, so it fails two of the study's must requirements (R1 recording cost, R6 truncation); sigrok-like is 1.59 times VGCH v2; planar is 0.087 times but is a new format version that is not specified yet - if wrong, the published traces are re-encoded losslessly from VGCH v2, which the study puts at 18 to 86 s a trace, 2 to 10 CPU-hours for 408, with no re-simulation.
2. **Decision 3, the reference sampler.** Ruling: tb-v1 stays the reference sampler; centre-v1 is published beside it, and each sampler's `samplers.<sampler>.window.exact` in `result.json` says whether its window fits the design (owner, 2026-11-28: "Publish both, flag affected"; [consumers.md, Sampler windows](../../consumers.md#sampler-windows)) - the condition fails: centre-v1 is pixel-exact on 10 of 10 calibration designs, but on mandelbrot (CVT 720x480@56, cpp 4) it shows the design's pixel (p+81, y+2) at (p, y), so the left 81 columns and top 2 rows are never shown (vgacap issue 100), and no hardware capture exists for any of the cpp != 1 pilot projects; tb-v1 is not exact either on 5 of the 11 (it stretches the mode's line over the design's: 832 clocks against 800 on nyan) - if wrong, consumers who compare only where `window.exact` is `true` lose nothing; the flagged projects are re-derived from their traces with centre-v2 when it lands, with no re-simulation.
3. **Decision 4, the upload.** Ruling: one upload of the whole archive, the frames subtree included, with its listing time logged at each re-run interval and brought back to the owner if it nears 4 minutes (owner Rulings BK and BO) - today the listing takes 30 to 31 s for 102,579 files (12 runs on 2026-11-28); at 1,094,642 files after a re-run with both samplers it is projected at 189 s (161 to 216 s), 63% of the 300 s interval, and pilot runs that also transferred frames took up to 247 s - if wrong, intervals run long during the re-run and the clips' 5-minute latency stretches; the split upload drafted in Task 19 is on branch [`t19-upload`](https://github.com/mithro/tinytapeout-vga-videos/tree/t19-upload) ([f42a98d](https://github.com/mithro/tinytapeout-vga-videos/commit/f42a98dbf2c5a4fe33ce6500379ae9bf3cd8a661)), unmerged.
4. **The re-run's job count and `min_free_root_gb`.** Ruling: `--jobs 24` and `min_free_root_gb = 100` (already in `host.toml`) - memory: the largest scope peak was 3,814 MiB (atari2600), 24 of them 89.4 GiB, against 418 GiB available on 2026-11-28 (`free -g`); root volume: the largest work-directory peak was 1.98 GB, and the plan's rule 24 x 1.98 x 2 = 94.9 GB rounds up to 100, against 772 GB free at the pilot's lowest and 683 GB on 2026-11-28 (`df -B1 /`); CPU: 24 scopes at CPUQuota 200% use at most 48 of 88 CPUs - if wrong, a job waits at the queue's free-space check, or a scope over MemoryMax 6 GiB loses one job (OOMPolicy=continue, Ruling BE); fewer jobs lengthen the 5.4 to 5.7 hour projection.

## Left for the owner

| # | question | where |
| --- | --- | --- |
| 1 | planar: adopt it and when | [Planar](#planar) |
| 2 | recording over 5% on busy designs with no fix | [Recording](#recording) |
| 3 | post-simulation CPU over 5% on 9 of 11 | [Post-simulation CPU](#post-simulation-cpu) |
| 4 | centre-v2 spec section 10 | [centre-v2](#centre-v2) |
| 5 | centre-v2 owner review question 12 | [centre-v2](#centre-v2) |
| 6 | centre-v1's flag and off-mode timing | [centre-v1's flag](#centre-v1s-flag) |
| 7 | a durable home for the study's raw results | [The study's raw results](#the-studys-raw-results) |
| 8 | a CI link check for vgacap's `docs/superpowers/*.md` | [Link check](#link-check) |
| 9 | the daemon PR #27 rollout timing | [Daemon PR 27](#daemon-pr-27) |

### Planar

From the [study](https://github.com/mithro/vgacap/blob/00037fa417057afe7b3df19d4bb2eeb3ffcc1d2f/docs/superpowers/2026-11-27-trace-format-study.md#recommendation), "Summary" and "Recommendation", items 5 to 7:

| measure | plan | nyancat | rle_vga | atari2600 |
| --- | --- | ---: | ---: | ---: |
| size (MB) | VGCH v2 | 416.43 | 18.39 | 596.59 |
| size (MB) | planar | 53.76 | 0.62 | 9.02 |
| trace share of R2 with header-only info (%) | VGCH v2 | 10.1 | 11.1 | 5.9 |
| trace share of R2 with header-only info (%) | planar on the simulation thread | 3.5 | 1.0 | 0.8 |
| R1 (%) | VGCH v2 | 16.7 | 19.9 | 8.1 |
| R1 (%) | planar on the simulation thread | 13.0 | 10.3 | 6.0 |
| R1 (%) | changelog stored as planar | 7.8 | 5.4 | 3.1 |

- R1 is the recording cost in the Verilator loop, as % of the untraced simulation, in the study's background set. R2 is the trace's share of everything after the simulation. Both budgets are 5%.
- No measured plan keeps R1 within 5% on all three busy designs. Planar cuts size and the post-simulation read; it does not fix recording.
- The study's conditions for adopting it:
  - a new header version, not a variant of VGCH v2;
  - every published trace re-encoded and checked by canonical-run hashes (18 to 86 s a trace);
  - one stored layout in `trace_read.c`, with no dual readers;
  - every reader and writer updated in the same change;
  - the container (one zstd frame a block, or seven) measured before the spec is written;
  - whether planar gets a plain uncompressed form.
- Header-only `tracetool info`, which needed no format change, is merged: [1d6930d](https://github.com/mithro/tinytapeout-vga-videos/commit/1d6930d), nyancat 27.3 to 0.14 s, rle_vga 68.8 to 0.25 s.

### centre-v2

centre-v2 is a corrected sampler for [vgacap issue 100](https://github.com/mithro/vgacap/issues/100): it fits the window to the lit picture and measures the colour phase. Its spec, `tmp/centrev2/2026-11-28-centre-v2-spec.md` in the local workspace (in no repository), is clean from this repository's side after four consumer checks. It waits on the owner:
- section 10, "Open questions for Tim": 12 questions, each with a recommendation; question 10 is the clip rule for a fit over 4,096;
- the owner review's question 12: one stray off-grid colour change makes mandelbrot 2880x480 at cpp 1; keep the exact rule (recommended: yes, no threshold).

When it lands, the projects whose `window.exact` is `false` are re-derived with it from their traces.

### centre-v1's flag

centre-v1's `exact` is `outside == 0` alone (Ruling CA). Two pilot projects have `outside` 0 with off-mode timing ([measurements.md, Sampler window flags](measurements.md#sampler-window-flags)):

| project | `frame_clocks` | `mode_frame_clocks` | `outside` | centre-v1 exact |
| --- | ---: | ---: | ---: | --- |
| tt05/tt_um_tomkeddie_a | 404,294 | 420,000 | 0 | yes |
| ttihp25a/tt_um_MichaelBell_rle_vga | 400,000 | 420,000 | 0 | yes |

Should centre-v1's flag also require `frame_clocks == mode_frame_clocks`? Both keys are in `result.json` either way, so a change would re-derive the flags only, not the frames.

### The study's raw results

The study's result CSVs, about 102 MB (18 GB with the traces), are in the study's vgacap worktree, under `tmp/format-study/`, and go when the worktree goes. They need a durable home. The place beside the traces is the public archive, so it is not that. Neither size is in a committed file: they come from the capture session's report.

### Link check

vgacap's Sphinx build (`-W`) excludes `docs/superpowers/`, so nothing checks the study document's links in CI. Add a check?

### Daemon PR 27

When to roll out daemon PR #27. The sources this report reads do not name its repository, so it is not linked.

## Trace size per format

The study's "Total bytes, MB" table (whole traces, projected by the study where it sampled), summed over the 11 pilot traces. The 408-project figure scales each total by clocks: the 408 projects with frames simulated 707,406,858,038 clocks in the reference run, the pilot's 11 projects 25,403,566,098 (3.59%).

| format | pilot (MB) | over VGCH v2 | 408 projects projected (GB) |
| --- | ---: | ---: | ---: |
| VGCH v2 (zstd 1) | 1,289.14 | 1.000 | 35.9 |
| planar (zstd 1) | 112.53 | 0.087 | 3.1 |
| sigrok-like (deflate 6) | 2,045.37 | 1.587 | 57.0 |
| FST (LZ4) | 734.18 | 0.570 | 20.4 |
| FST (zlib) | 531.92 | 0.413 | 14.8 |
| FST with clk (LZ4) | 726.82 | 0.564 | 20.2 |
| VCD (zstd 1) | 11,233.93 | 8.714 | 312.8 |
| LXT2 | 30,083.45 | 23.336 | 837.7 |

- atari2600 (596.59 MB) and nyancat (416.43 MB) are 79% of the pilot's VGCH v2 bytes. Most projects are quieter, so the 35.9 GB likely overstates.
- Viewers read FST exported by [`vgacap-export`](https://github.com/mithro/vgacap/blob/da9ea98b287740aa11b99263948bb3ca62d961c4/src/tools/vgacap_export.c): the pilot's FST checked equal to its VCD, and loads in [GTKWave](https://gtkwave.github.io/gtkwave/) and [Surfer](https://gitlab.com/surfer-project/surfer) ([measurements.md, Step 7](measurements.md#step-7-viewers)).

## Stores and PNGs

Per distinct frame from the pilot ([`raw/`](raw/) sizes), times the reference run's 543,730 distinct frames over 408 projects:

| quantity | pilot | per distinct frame | 408 projects projected |
| --- | ---: | ---: | ---: |
| centre-v1 store (bytes) | 37,721,163 | 1,916 | 1.04 GB |
| tb-v1 store (bytes) | 37,810,100 | 1,920 | 1.04 GB |
| centre-v1 PNGs (bytes) | 156,872,929 | 7,966 | 4.33 GB |
| tb-v1 PNGs added after sharing (bytes) | 96,141,612 | 4,882 | 2.65 GB |
| centre-v1 PNG files | 19,692 | 1.000 | 543,730 |
| tb-v1 PNG files added after sharing | 6,658 | 0.338 | 183,839 |

- **Sharing.** derive writes one PNG per distinct image and hard-links a sampler's PNG to the other's when the frame is the same. In [`derive-now.jsonl`](logs/derive-now.jsonl) tb-v1 adds no PNG on the 6 projects where the samplers agree (nyancat, metaballs, colorbars, atari2600, rle_vga, dvd_screensaver), and one PNG per distinct frame on the other 5.
- The tb-v1 bytes added are each project's tb-v1 PNG bytes times its added share, which is 0 or 1 on every pilot project.
- With the traces, the frames subtree is projected at about 45 GB after the re-run: 35.9 + 1.04 + 1.04 + 4.33 + 2.65.

## Run time and root volume per job

**Run time.** The pilot's job time (fetch, build, simulate, derive, encode, publish) against the same project's reference-run job time (fetch, build, simulate, encode):

| project | reference run (s) | pilot job (s) | pilot derive (s) | derive at 44a1baa (s) | pilot over reference |
| --- | ---: | ---: | ---: | ---: | ---: |
| tt08/tt_um_a1k0n_nyancat | 758.3 | 1,236.8 | 169.2 | 64.8 | 1.63 |
| tt08/tt_um_johshoff_metaballs | 1,174.9 | 1,271.4 | 173.8 | 29.8 | 1.08 |
| ttihp25a/tt_um_rebeccargb_colorbars | 598.0 | 543.5 | 12.7 | 3.1 | 0.91 |
| ttihp25a/tt_um_rejunity_atari2600 | 1,515.6 | 1,920.8 | 140.2 | 60.7 | 1.27 |
| tt05/tt_um_tomkeddie_a | 581.1 | 613.5 | 44.5 | 5.3 | 1.06 |
| ttihp25a/tt_um_cfib_demo | 1,267.0 | 1,376.5 | 76.5 | 15.9 | 1.09 |
| ttihp25a/tt_um_a1k0n_vgadonut | 1,672.3 | 1,889.6 | 117.1 | 43.5 | 1.13 |
| tt08/tt_um_nyan | 472.7 | 562.6 | 14.0 | 3.8 | 1.19 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 729.8 | 871.8 | 139.1 | 60.7 | 1.19 |
| tt08/tt_um_MichaelBell_mandelbrot | 3,801.2 | 2,864.2 | 32.9 | 6.0 | 0.75 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 501.1 | 650.4 | 85.8 | 14.3 | 1.30 |
| all 11 | 13,072.0 | 13,801.1 | - | - | 1.06 |

Projected to the 431 committed results with timings (the queue's whole set, `testpatterns` included), by the pilot's factor:

| quantity | as the pilot ran | with derive at 44a1baa |
| --- | ---: | ---: |
| factor over the reference run | 1.056 | 1.002 |
| job time (h) | 136.0 | 129.1 |
| wall time at 24 jobs (h) | 5.7 | 5.4 |

- Wall time is job time over 24. The last jobs add a tail of up to one longest job: 6,943 s in the reference run, about 2 hours.
- The reference run and the pilot ran under different host load: mandelbrot's pilot job was faster than its reference run.
- "With derive at 44a1baa" swaps each pilot derive for the wall time of [`derive_now.py`](derive_now.py), both samplers, run 4 at once outside a scope.

**Root volume** ([measurements.md](measurements.md#root-volume-peak-per-job)):

| quantity | value |
| --- | ---: |
| largest work-directory peak (atari2600) | 1.98 GB |
| largest scratch peak (atari2600) | 0.61 GB |
| `min_free_root_gb` by the plan's rule | 100 |
| lowest free during the pilot | 772 GB |
| free on 2026-11-28 | 683 GB |

## The upload listing

| state | runs | statistic | files | listing (s) | share of 300 s | kind |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| before the pilot | 38 | mean | 62,991 | 25.05 | 8% | measured |
| 11 pilot projects | 35 | mean | 102,579 | 30.97 | 10% | measured |
| 11 pilot projects on 2026-11-28 | 12 | longest | 102,579 | 31 | 10% | measured |
| a pilot run that also transferred frames | 1 | longest | 102,356 | 247 | 82% | measured |
| 408 projects with centre-v1 only | - | - | 547,544 | 107 | 36% | projected |
| 408 projects with both samplers | - | - | 1,094,642 | 189 | 63% | projected |

- The projection is 0.150 ms a file (0.124 to 0.175), from one measured delta, extrapolated linearly about 10 times past the largest count measured ([measurements.md, The upload's listing](measurements.md#the-uploads-listing-ruling-bk)).
- During the re-run, with 24 jobs publishing, most runs will also transfer.
- The frames subtree's file count did not change when the 11 were re-derived in the XXH3-128 format ([`upload-listing-2026-11-28.md`](logs/upload-listing-2026-11-28.md)).

## Against the budget

| target | limit | pilot within | pilot over | pilot inconclusive | now within | now over | worst now | worst value |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| recording side by side | 5% of wall | 0 | 3 | 5 | 0 | 3 | rle_vga | +20.7% |
| post-simulation CPU with both samplers | 5% of simulation CPU | 1 | 10 | 0 | 2 | 9 | nyancat | 35.9% |
| post-simulation CPU with centre-v1 alone | 5% of simulation CPU | - | - | - | 2 | 9 | nyancat | 29.9% |
| memory | MemoryMax 6 GiB | 11 | 0 | 0 | 11 | 0 | atari2600 | 3,814 MiB |
| tasks with `FFMPEG_CPUS` 2 | TasksMax 64 | 1 | 0 | 0 | 1 | 0 | atari2600 | 53 |
| root volume | `min_free_root_gb` 100 | 11 | 0 | 0 | 11 | 0 | atari2600 | 1.98 GB |

- "Now" is main at 44a1baa. The recording code has not changed since the pilot, so its verdicts stand, and so do memory, tasks and root volume.
- The pilot ran both samplers only; centre-v1 alone was not in it.

### Recording

- **Over:** nyancat (+17.6% median), rle_vga (+20.7%), vgadonut (+7.2%). Inconclusive, with pairs on both sides of 5%: colorbars, nyan, cfib_demo, metaballs, tomkeddie_a ([measurements.md, Step 3](measurements.md#step-3-recording)).
- **Profile:** the writer's slow path, on every pin change. nyancat changes `uo_out` on a third of its samples; rle_vga's QSPI clock changes `uio_out` on every sample; vgadonut changes `uo_out` on 7.9%. The fast paths are inlined.
- **Fixes tried:** zstd levels 1, -1, -3 and -5; none beats 1.
- **Fixes left, none adopted:**
  - the lean writer, byte-identical output, 0.91 of VGCH v2 on rle_vga and within the noise on nyancat and atari2600 in the study's loop ([vgacap issue 98](https://github.com/mithro/vgacap/issues/98), open);
  - a change-driven writer stored as planar, 0.26 to 0.51 of VGCH v2 on the busy designs, still over 5% on nyancat and rle_vga (study).
- **For the owner:** no measured plan meets 5% on nyancat. This target is missed with no fix in hand.

### Post-simulation CPU

(compressor CPU + derive CPU) over the untraced simulation's CPU. The compressor CPU is the pilot's (CPU with the trace minus without): the writer has not changed. derive now is [`derive-now.jsonl`](logs/derive-now.jsonl).

| project | budget (s) | compressor (s) | derive in the pilot (s) | post in the pilot (%) | derive now with both (s) | post now with both (%) | derive now with centre-v1 (s) | post now with centre-v1 (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt08/tt_um_a1k0n_nyancat | 20.3 | 71.6 | 201.0 | 67.2 | 74.1 | 35.9 | 49.7 | 29.9 |
| tt08/tt_um_johshoff_metaballs | 33.6 | 35.1 | 202.3 | 35.3 | 44.7 | 11.9 | 17.1 | 7.8 |
| ttihp25a/tt_um_rebeccargb_colorbars | 17.8 | 27.2 | 12.7 | 11.2 | 3.1 | 8.5 | 2.1 | 8.2 |
| ttihp25a/tt_um_rejunity_atari2600 | 36.7 | 51.2 | 153.0 | 27.8 | 64.7 | 15.8 | 45.6 | 13.2 |
| tt05/tt_um_tomkeddie_a | 19.3 | 9.1 | 53.3 | 16.2 | 7.2 | 4.2 | 2.9 | 3.1 |
| ttihp25a/tt_um_cfib_demo | 31.2 | 48.6 | 109.8 | 25.4 | 24.8 | 11.8 | 11.9 | 9.7 |
| ttihp25a/tt_um_a1k0n_vgadonut | 38.0 | 40.7 | 179.8 | 29.0 | 67.6 | 14.2 | 36.4 | 10.1 |
| tt08/tt_um_nyan | 16.8 | 32.5 | 14.0 | 13.8 | 3.8 | 10.8 | 2.5 | 10.4 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 22.7 | 51.4 | 139.0 | 42.0 | 60.7 | 24.8 | 46.6 | 21.6 |
| tt08/tt_um_MichaelBell_mandelbrot | 94.3 | 43.3 | 34.6 | 4.1 | 6.5 | 2.6 | 5.4 | 2.6 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 17.8 | 17.6 | 113.7 | 36.8 | 22.9 | 11.4 | 10.6 | 7.9 |

Fixes applied since the pilot:

| fix | change | project | step | samplers | before | after | unit |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| PNG check with `translate` | [5c4f797](https://github.com/mithro/tinytapeout-vga-videos/commit/5c4f797) | dvd_screensaver | derive | both | 99.5 | 84.7 | s CPU |
| XXH3-128 with one hash per distinct frame | [vgacap PR 62](https://github.com/mithro/vgacap/pull/62) | dvd_screensaver | derive | centre-v1 | 38.1 | 13.0 | s wall |
| vectorised centre-v1 | [vgacap PR 74](https://github.com/mithro/vgacap/pull/74) | mandelbrot | sampling | both | 22.3 | 5.9 | s user |
| tb-v1 run fill | [vgacap PR 68](https://github.com/mithro/vgacap/pull/68) | nyan | sampling | both | 11.2 | 3.3 | s user |
| header-only `tracetool info` | [1d6930d](https://github.com/mithro/tinytapeout-vga-videos/commit/1d6930d) | nyancat | `tracetool info` | - | 27.3 | 0.14 | s |

The XXH3-128 figure is in merge [26b1004](https://github.com/mithro/tinytapeout-vga-videos/commit/26b1004)'s message, and PRs 74 and 68 together in merge [e71f3a6](https://github.com/mithro/tinytapeout-vga-videos/commit/e71f3a6)'s.

- **Profile now:** the compressor alone exceeds the whole budget on 8 of 11 projects (all but tomkeddie_a, mandelbrot and dvd_screensaver), so no derive fix can meet the target there. The compressor figure also holds the simulation thread's slowdown, since both share the scope's CPUQuota.
- On rle_vga derive still takes 46.6 s for one distinct frame. The sampler's pass over the trace takes 33.0 s in the study; the rest is `tracetool uohash` and the trace's SHA-256, not broken down.
- **Fixes left:** planar cuts the compressor (background CPU: nyancat 19.62 to 3.83 s, rle_vga 6.83 to 2.39 s in the study) and the sampler's pass (rle_vga 33.0 to 0.04 s, nyancat 18.3 to 10.1 s). That is question 1.
- **For the owner:** with planar on the simulation thread the study still puts nyancat's trace share at 3.5%, so 5% for everything after the simulation stays tight on busy designs.
- derive now ran 4 at once, outside a scope, on the host at a load of 26 to 41 on 88 CPUs. The pilot's derive ran 11 at once inside scopes.

## Correctness

| check | result | where |
| --- | --- | --- |
| tb-v1's FNV hashes against git | 11 of 11 byte-identical | [Step 1](measurements.md#step-1-tb-v1s-fnv-against-git) |
| distinct XXH3-128 against distinct FNV | equal on 11 of 11 | [Step 2](measurements.md#step-2-distinct-counts) |
| tb-v1 equal to centre-v1 frame for frame | 6 of 11 | [Step 3](measurements.md#step-3-tb-v1-against-centre-v1) |
| calibration designs pixel-exact | 10 of 10 | [Step 4](measurements.md#step-4-calibration-designs) |
| hardware captures found | 0 of 4 | [Step 5](measurements.md#step-5-hardware) |
| FST equal to VCD | 2 of 2 | [Step 7](measurements.md#step-7-viewers) |
| centre-v1 window exact | 5 of 11 | [Sampler window flags](measurements.md#sampler-window-flags) |
| tb-v1 window exact | 6 of 11 | [Sampler window flags](measurements.md#sampler-window-flags) |

- The re-run's own check (Task 23 Step 4) compares all 408 FNV files with git.
- The 5 projects whose samplers differ all differ from frame 0, with no frame offset: the crop differs, not the frame cut.
- centre-v1 on the two designs vgacap issue 100 investigated:

  | project | real timing | matched mode | cpp | shown at x | shown at y | `outside` | wrong pixels |
  | --- | --- | --- | ---: | --- | --- | ---: | ---: |
  | tt08/tt_um_MichaelBell_mandelbrot | CVT 720x480@56 | 640x480@75 | 4 | p+81 | y+2 | 161,110 | 0 |
  | tt08/tt_um_nyan | 832-clock lines | 640x480@60 | 1 | p-8 | y+1 | 4,472 | 0 |

  - Every pixel centre-v1 shows is the design's; it shows the wrong part of the picture.
  - mandelbrot's 100% `colour_changes_off_grid` is an artefact: its colour changes one clock before its sync, so every change is at clock 3 mod 4.
- **Archive-wide:** 41 of 404 projects have a line length or line count off their matched mode's totals in the reference run's `timing` (vgacap issue 100). Porch shifts alone do not show there; in the pilot 3 of the 8 projects with standard totals still have `outside` > 0. The exact count comes with the re-run's `window` flags.

## Host changes

Made with `tim`'s sudo, from the controller's logs `tmp/t18-host.log` and `tmp/t19.log` in the main checkout (not committed). Host paths are written as host.toml's keys.

| date (UTC) | task | change | as | etckeeper commit |
| --- | --- | --- | --- | --- |
| 2026-11-26 | Task 18 Step 3 | `install -d -o ttvga -g ttvga -m 755 <staging_dir>` | root | none recorded |
| 2026-11-26 | Task 18 Step 3 | `loginctl enable-linger ttvga` | root | none recorded |
| 2026-11-26 | Task 18 Step 3 | `~/ttvga/host.toml` with `frames_root` and `staging_dir` and `min_free_root_gb = 100` | ttvga | none recorded |
| 2026-11-27 | Task 19 Step 2 | `install -d -o ttvga -g ttvga -m 755 <frames_root>` | root | none recorded |
| 2026-11-27 | Task 19 Step 2 | `touch <frames_root>/.ttvga-frames-root` | ttvga | none recorded |

- No etckeeper commit SHA is recorded in those logs, the Task 18 and Task 19 reports, or the ledger. None of the recorded commands writes under `/etc`, which is all etckeeper tracks.
- The upload-split changes that would have had etckeeper commits ([plan Task 19](../../superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-19-the-upload-split-decision-4-with-the-frames-upload-left-off) Steps 1, 3 and 4) were not made: the owner chose one upload (Ruling BK).
- Checked read-only on 2026-11-28: `Linger=yes`; `<staging_dir>` and the frames marker exist, owned by `ttvga`; the only upload timer is the main one.

## Carried minors folded in

| item | from | change |
| --- | --- | --- |
| [`hardware-search.md`](logs/hardware-search.md) rows without a repository | Task 21 re-review | a repository column |
| a host-named nginx file in [`publishing.md`](../../publishing.md) | Ruling BY | a `SITE.conf` placeholder |
| colorbars' bench shape in [measurements.md](measurements.md#side-by-side) | Task 20 re-review 2 | `not recorded` and one row per project |
| the BK rows' source in [measurements.md](measurements.md#rulings-used-here) | Task 20 re-review 2 | already plan Task 19 in [fd31b98](https://github.com/mithro/tinytapeout-vga-videos/commit/fd31b98) |
