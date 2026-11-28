projects with frames: 408; their clocks: 707,406,858,038; distinct frames: 543,730
pilot: clocks 25,403,566,098; distinct frames 19,692; clocks share 0.0359

## Trace size per format

| format | pilot total (MB) | over vgch2 | 408 projects, projected (GB) |
| --- | ---: | ---: | ---: |
| vgch2 (zstd 1) | 1,289.14 | 1.000 | 35.9 |
| planar (zstd 1) | 112.53 | 0.087 | 3.1 |
| sigrok-like (deflate 6) | 2,045.37 | 1.587 | 57.0 |
| FST (LZ4) | 734.18 | 0.570 | 20.4 |
| FST (zlib) | 531.92 | 0.413 | 14.8 |
| FST with clk (LZ4) | 726.82 | 0.564 | 20.2 |
| VCD (zstd 1) | 11,233.93 | 8.714 | 312.8 |
| LXT2 | 30,083.45 | 23.336 | 837.7 |

## A full-pin export to FST, projected

| exporter | 3 busy traces (CPU s) | their clocks | 408 projects, projected (CPU h) |
| --- | ---: | ---: | ---: |
| the study's export from VGCH v2 | 1,721.6 | 4,466,000,832 | 75.7 |
| vgacap-export on VGCH v2 | 1,801.2 | 4,466,000,832 | 79.3 |

## Stores and PNGs, pilot

| project | distinct frames | centre-v1 store (bytes) | tb-v1 store (bytes) | centre-v1 PNGs (bytes) | centre-v1 PNG files | PNGs written, both samplers | tb-v1 PNG files added | tb-v1 PNG bytes added |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt08/tt_um_a1k0n_nyancat | 3,530 | 4,539,138 | 4,539,138 | 23,178,533 | 3,530 | 3,530 | 0 | 0 |
| tt08/tt_um_johshoff_metaballs | 4,325 | 2,237,504 | 2,237,504 | 14,488,348 | 4,325 | 4,325 | 0 | 0 |
| ttihp25a/tt_um_rebeccargb_colorbars | 1 | 134 | 134 | 4,592 | 1 | 1 | 0 | 0 |
| ttihp25a/tt_um_rejunity_atari2600 | 1,609 | 312,552 | 312,552 | 11,552,411 | 1,609 | 1,609 | 0 | 0 |
| tt05/tt_um_tomkeddie_a | 636 | 113,758 | 103,104 | 2,208,646 | 636 | 1,272 | 636 | 2,211,266 |
| ttihp25a/tt_um_cfib_demo | 2,320 | 2,156,619 | 2,153,885 | 13,727,333 | 2,320 | 4,640 | 2,320 | 13,745,510 |
| ttihp25a/tt_um_a1k0n_vgadonut | 3,597 | 27,660,224 | 27,724,460 | 79,348,194 | 3,597 | 7,194 | 3,597 | 79,014,288 |
| tt08/tt_um_nyan | 2 | 1,164 | 1,110 | 10,355 | 2 | 4 | 2 | 10,826 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 29 | 29 | 1,626 | 1 | 1 | 0 | 0 |
| tt08/tt_um_MichaelBell_mandelbrot | 103 | 560,261 | 598,404 | 1,047,300 | 103 | 206 | 103 | 1,159,722 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 3,568 | 139,780 | 139,780 | 11,305,591 | 3,568 | 3,568 | 0 | 0 |

## Stores and PNGs, projected by distinct frames

| quantity | pilot | per distinct frame | 408 projects, projected |
| --- | ---: | ---: | ---: |
| centre-v1 store (GB) | 37,721,163 | 1,915.558 | 1.04 |
| tb-v1 store (GB) | 37,810,100 | 1,920.074 | 1.04 |
| centre-v1 PNGs (GB) | 156,872,929 | 7,966.328 | 4.33 |
| tb-v1 PNG bytes added (GB) | 96,141,612 | 4,882.268 | 2.65 |
| centre-v1 PNG files | 19,692 | 1.000 | 543,730 |
| tb-v1 PNG files added | 6,658 | 0.338 | 183,839 |

## Run time per job

| project | reference run (s) | pilot job (s) | pilot derive (s) | derive now, both (s) | ratio |
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

| quantity | value |
| --- | ---: |
| results with timings | 431 |
| their reference-run job time (h) | 128.8 |
| longest reference-run job (s) | 6,943.1 |
| pilot factor, as run | 1.056 |
| pilot factor, derive at this commit | 1.002 |
| projected job time, as run (h) | 136.0 |
| projected wall at 24 jobs, as run (h) | 5.7 |
| projected job time, derive at this commit (h) | 129.1 |
| projected wall at 24 jobs, derive at this commit (h) | 5.4 |

## Post-simulation CPU, then and now

| project | CPU without (s) | compressor (s) | budget (s) | pilot derive (s) | post, pilot (%) | derive now, both (s) | post now, both (%) | derive now, centre-v1 (s) | post now, centre-v1 (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt08/tt_um_a1k0n_nyancat | 405.7 | 71.6 | 20.3 | 201.0 | 67.2 | 74.1 | 35.9 | 49.7 | 29.9 |
| tt08/tt_um_johshoff_metaballs | 672.3 | 35.1 | 33.6 | 202.3 | 35.3 | 44.7 | 11.9 | 17.1 | 7.8 |
| ttihp25a/tt_um_rebeccargb_colorbars | 356.1 | 27.2 | 17.8 | 12.7 | 11.2 | 3.1 | 8.5 | 2.1 | 8.2 |
| ttihp25a/tt_um_rejunity_atari2600 | 733.2 | 51.2 | 36.7 | 153.0 | 27.8 | 64.7 | 15.8 | 45.6 | 13.2 |
| tt05/tt_um_tomkeddie_a | 385.1 | 9.1 | 19.3 | 53.3 | 16.2 | 7.2 | 4.2 | 2.9 | 3.1 |
| ttihp25a/tt_um_cfib_demo | 623.5 | 48.6 | 31.2 | 109.8 | 25.4 | 24.8 | 11.8 | 11.9 | 9.7 |
| ttihp25a/tt_um_a1k0n_vgadonut | 759.9 | 40.7 | 38.0 | 179.8 | 29.0 | 67.6 | 14.2 | 36.4 | 10.1 |
| tt08/tt_um_nyan | 336.7 | 32.5 | 16.8 | 14.0 | 13.8 | 3.8 | 10.8 | 2.5 | 10.4 |
| ttihp25a/tt_um_MichaelBell_rle_vga | 453.0 | 51.4 | 22.7 | 139.0 | 42.0 | 60.7 | 24.8 | 46.6 | 21.6 |
| tt08/tt_um_MichaelBell_mandelbrot | 1,886.8 | 43.3 | 94.3 | 34.6 | 4.1 | 6.5 | 2.6 | 5.4 | 2.6 |
| tt07/tt_um_tinytapeout_dvd_screensaver | 356.9 | 17.6 | 17.8 | 113.7 | 36.8 | 22.9 | 11.4 | 10.6 | 7.9 |

