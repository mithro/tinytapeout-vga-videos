# Step 5: where a hardware capture was looked for

Searched 2026-11-27, re-checked 2026-11-28, for the four projects ttihp25a/tt_um_cfib_demo, ttihp25a/tt_um_a1k0n_vgadonut, ttihp25a/tt_um_MichaelBell_rle_vga and tt08/tt_um_MichaelBell_mandelbrot (any shuttle). Paths are relative to the local workspace of the Tiny Tapeout repositories.

| place searched | holds | match |
| --- | --- | --- |
| `tt-harness-fpga-vga/work/run/<shuttle>/<macro>/outcome.json` | the FPGA build status per design | no hardware stage |
| `tt-harness-fpga-vga/.superpowers/sdd/2026-11-23-plan-2-hardware-bringup/progress.md` | the FPGA session's hardware runs | none of the four |
| `tmp/hw1/` | the first hardware validation | none of the four |
| `tmp/hw2/<shuttle>__<macro>/` | the library batches (206 directories on 2026-11-28) | none of the four |
| `vgacap/tmp/*.vgacap` | the capture session's captures | none of the four |
| `tt-vga-capture/tmp/*.vgacap` | earlier capture work | none of the four |
| `tt-vga-capture/LOG.md` | earlier capture work | none of the four |
| `tt-vga-capture/TASKS.md` | earlier capture work | none of the four |
| file names on the whole volume | `cfib` or `vgadonut` or `rle_vga` or `MichaelBell_mandelbrot` | no capture |

- `tmp/hw2/` has 3 directories for `tt_um_gfg_development_tinymandelbrot`, a different design.
- The file-name search found only sources, builds, references and results.
