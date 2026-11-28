# Step 5: where a hardware capture was looked for

Searched 2026-11-27, re-checked 2026-11-28, for the four projects ttihp25a/tt_um_cfib_demo, ttihp25a/tt_um_a1k0n_vgadonut, ttihp25a/tt_um_MichaelBell_rle_vga and tt08/tt_um_MichaelBell_mandelbrot (any shuttle). Paths are relative to the local workspace that holds the Tiny Tapeout repositories. The workspace's own `tmp/` is in no repository.

| place searched | repository | holds | match |
| --- | --- | --- | --- |
| `tt-harness-fpga-vga/work/run/<shuttle>/<macro>/outcome.json` | [tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) | the FPGA build status per design | no hardware stage |
| `tt-harness-fpga-vga/.superpowers/sdd/2026-11-23-plan-2-hardware-bringup/progress.md` | [tt-harness-fpga-vga](https://github.com/mithro/tt-harness-fpga-vga) | the FPGA session's hardware runs | none of the four |
| `tmp/hw1/` | none: the workspace's `tmp/` | the first hardware validation | none of the four |
| `tmp/hw2/<shuttle>__<macro>/` | none: the workspace's `tmp/` | the library batches (206 directories on 2026-11-28) | none of the four |
| `vgacap/tmp/*.vgacap` | [vgacap](https://github.com/mithro/vgacap) | the capture session's captures | none of the four |
| `tt-vga-capture/tmp/*.vgacap` | [tt-vga-capture](https://github.com/mithro/tt-vga-capture) | earlier capture work | none of the four |
| `tt-vga-capture/LOG.md` | [tt-vga-capture](https://github.com/mithro/tt-vga-capture) | earlier capture work | none of the four |
| `tt-vga-capture/TASKS.md` | [tt-vga-capture](https://github.com/mithro/tt-vga-capture) | earlier capture work | none of the four |
| file names on the whole volume | - | `cfib` or `vgadonut` or `rle_vga` or `MichaelBell_mandelbrot` | no capture |

- `tmp/hw2/` has 3 directories for `tt_um_gfg_development_tinymandelbrot`, a different design.
- The file-name search found only sources, builds, references and results.
