## Step 1

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

## Step 2

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

Committed FNV files: 408, distinct FNV values summed per project: 543,730

## Step 3

| project | centre-v1 cpp | tb-v1 cpp | first mismatch | offset | start clock delta | differing pixels | diff |
| --- | ---: | ---: | --- | --- | --- | ---: | --- |
| tt08/tt_um_a1k0n_nyancat | 1 | 1 | none | 0 | -944 | - | - |
| tt08/tt_um_johshoff_metaballs | 1 | 1 | none | 0 | -5384 | - | - |
| ttihp25a/tt_um_rebeccargb_colorbars | 1 | 1 | none | 0 | -944 | - | - |
| ttihp25a/tt_um_rejunity_atari2600 | 1 | 1 | none | 0 | -944 | - | - |
| tt05/tt_um_tomkeddie_a | 1 | 1 | 0 | none | -942 | 1,122 | [0](frames/tt05__tt_um_tomkeddie_a/) |
| ttihp25a/tt_um_cfib_demo | 2 | 2 | 0 | none | -1888 | 14,235 | [0](frames/ttihp25a__tt_um_cfib_demo/) |
| ttihp25a/tt_um_a1k0n_vgadonut | 1.90625 | 1.90625 | 0 | none | -1799 | 65,089 | [0](frames/ttihp25a__tt_um_a1k0n_vgadonut/) |
| tt08/tt_um_nyan | 1 | 1.04 | 0 | none | -1008 | 28,371 | [0](frames/tt08__tt_um_nyan/) |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 0.952381 | none | 0 | -3184 | - | - |
| tt08/tt_um_MichaelBell_mandelbrot | 4 | 4.26667 | 0 | none | -35744 | 97,586 | [0](frames/tt08__tt_um_MichaelBell_mandelbrot/) |
| tt07/tt_um_tinytapeout_dvd_screensaver | 1 | 1 | none | 0 | -944 | - | - |

| project | cpp wanted | cpp | `colour_changes_off_grid` | `outside` | `suggested_offset` | `porches` | all as wanted |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| tt08/tt_um_nyan | 1 | 1 | 0 | 4,472 | 8 -1 | 72 33 | **no** |
| ttihp25a/tt_um_MichaelBell_rle_vga | 1 | 1 | 0 | 0 | 0 0 | 85 15 | yes |
| tt08/tt_um_MichaelBell_mandelbrot | 4 | 4 | 16,716,630 | 161,110 | -2 -2 | 169 8 | **no** |

cpp = 1 (centre-v1) projects where the samplers agree frame for frame:

- tt08/tt_um_a1k0n_nyancat
- tt08/tt_um_johshoff_metaballs
- ttihp25a/tt_um_rebeccargb_colorbars
- ttihp25a/tt_um_rejunity_atari2600
- ttihp25a/tt_um_MichaelBell_rle_vga
- tt07/tt_um_tinytapeout_dvd_screensaver
