# Status

Generated 2026-09-15 10:34 UTC by `tt-vga report`. Do not edit by hand.

- Targets: 440
- Attempted: 440
- Videos produced (ok + static + partial): 386
- Pending: 0

## Verdicts

| Verdict | Count |
| --- | ---: |
| ok | 294 |
| static | 68 |
| partial | 24 |
| blank | 15 |
| no-sync | 12 |
| bad-timing | 1 |
| unstable-sync | 2 |
| sim-timeout | 4 |
| build-failed | 10 |
| fetch-failed | 1 |
| skipped | 9 |

## Per shuttle

| Shuttle | Targets | ok | static | partial | blank | no-sync | bad-timing | unstable-sync | sim-timeout | build-failed | fetch-failed | skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tt05 | 6 | 4 | 2 |  |  |  |  |  |  |  |  |  |
| tt05of | 6 | 4 | 2 |  |  |  |  |  |  |  |  |  |
| tt06 | 6 | 3 |  | 1 |  |  |  |  |  |  | 1 | 1 |
| tt07 | 7 | 3 |  |  | 1 |  |  |  | 3 |  |  |  |
| ttihp0p1 | 5 | 3 | 1 |  |  |  |  |  |  | 1 |  |  |
| tt08 | 30 | 21 | 2 | 4 |  | 1 |  | 1 |  |  |  | 1 |
| ttihp0p2 | 24 | 16 | 3 | 3 | 1 | 1 |  |  |  |  |  |  |
| tt09 | 13 | 8 | 1 | 1 | 1 |  |  |  | 1 | 1 |  |  |
| ttihp25a | 46 | 31 | 6 | 4 | 3 | 1 |  |  |  | 1 |  |  |
| ttihp0p3 | 7 | 6 |  |  |  |  |  |  |  |  |  | 1 |
| ttcad25a | 40 | 29 | 4 | 4 | 1 | 1 |  |  |  |  |  | 1 |
| ttihp25b | 7 | 6 | 1 |  |  |  |  |  |  |  |  |  |
| ttsky25a | 27 | 16 | 5 | 1 | 1 | 1 | 1 |  |  | 1 |  | 1 |
| ttgf0p1 | 5 | 3 | 2 |  |  |  |  |  |  |  |  |  |
| ttsky25b | 15 | 9 | 3 |  | 1 |  |  | 1 |  |  |  | 1 |
| ttgf0p2 | 10 | 6 | 2 |  |  | 1 |  |  |  | 1 |  |  |
| ttihp26a | 31 | 22 | 5 | 1 | 1 | 1 |  |  |  | 1 |  |  |
| ttihp0p4 | 11 | 4 | 4 | 1 |  | 1 |  |  |  | 1 |  |  |
| ttsky26a | 57 | 43 | 6 | 3 | 2 | 1 |  |  |  | 1 |  | 1 |
| ttsky26b | 46 | 31 | 12 | 1 | 1 | 1 |  |  |  |  |  |  |
| ttgf26a | 10 | 7 | 1 |  |  | 1 |  |  |  | 1 |  |  |
| ttgf26b | 4 | 3 |  |  |  |  |  |  |  | 1 |  |  |
| ttgf0p3 | 6 | 4 | 1 |  |  |  |  |  |  |  |  | 1 |
| ttsky26c | 21 | 12 | 5 |  | 2 | 1 |  |  |  |  |  | 1 |

## Not yet producing a video

| Project | Verdict | Reason |
| --- | --- | --- |
| tt07/tt_um_vga_snake | blank | 4320/4369 frames are one colour (640x480@72) |
| tt09/tt_um_toivoh_pio_ram_emu_example | blank | 3600/3600 frames are black (640x480@60) |
| ttcad25a/tt_um_gfg_development_tinymandelbrot | blank | 2278/2278 frames are black (800x600@60) |
| ttihp0p2/tt_um_MichaelBell_rle_vga | blank | 3596/3596 frames are black (640x480@60) |
| ttihp25a/tt_um_MichaelBell_rle_vga | blank | 3600/3600 frames are black (640x480@75) |
| ttihp25a/tt_um_gfg_development_tinymandelbrot | blank | 2278/2278 frames are black (800x600@60) |
| ttihp25a/tt_um_toivoh_pio_ram_emu_example | blank | 3600/3600 frames are black (640x480@60) |
| ttihp26a/tt_um_michaelstambach_vogal | blank | 3596/3596 frames are one colour (640x480@60) |
| ttsky25a/tt_um_MichaelBell_rle_vga | blank | 3600/3600 frames are black (640x480@75) |
| ttsky25b/tt_um_pongsagon_tinygpu_v2 | blank | 3596/3596 frames are black (640x480@60) |
| ttsky26a/tt_um_TinyGPU_v3 | blank | 3596/3596 frames are black (640x480@60) |
| ttsky26a/tt_um_madech_8bit_processor_vga | blank | 3596/3596 frames are black (640x480@60) |
| ttsky26b/tt_um_sandsim_Alden_G878 | blank | 3587/3587 frames are one colour (640x480@60) |
| ttsky26c/tt_um_nobleg30_uart_vga_scroller | blank | 3596/3596 frames are black (640x480@60) |
| ttsky26c/tt_um_vga_ca | blank | 3583/3596 frames are one colour (640x480@60) |
| tt08/tt_um_crispy_vga | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttcad25a/tt_um_crispy_vga | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttgf0p2/tt_um_htfab_vga_tester | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttgf26a/tt_um_htfab_vga_tester | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttihp0p2/tt_um_crispy_vga | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttihp0p4/tt_um_MichaelBell_photo_frame | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttihp25a/tt_um_crispy_vga | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttihp26a/tt_um_MichaelBell_photo_frame | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttsky25a/tt_um_spacewar | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttsky26a/tt_um_rebelmike_asic_odyssey | no-sync | line 0 clocks, ? lines, hsync transitions 1 |
| ttsky26b/tt_um_enjimneering_spi_mem | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttsky26c/tt_um_htfab_vga_tester | no-sync | line 0 clocks, ? lines, hsync transitions 0 |
| ttsky25a/tt_um_nitelich_conway | bad-timing | line 420000 clocks, ? lines, hsync transitions 8 |
| tt08/tt_um_gfg_development_tinymandelbrot | unstable-sync | line 1056 clocks, 628 lines, hsync transitions ? |
| ttsky25b/tt_um_enjimneering_tts_top | unstable-sync | line 800 clocks, 525 lines, hsync transitions ? |
| tt07/tt_um_MichaelBell_rle_vga | sim-timeout | line None clocks, ? lines, hsync transitions ? |
| tt07/tt_um_algofoogle_raybox_zero | sim-timeout | line None clocks, ? lines, hsync transitions ? |
| tt07/tt_um_emern_top | sim-timeout | line None clocks, ? lines, hsync transitions ? |
| tt09/tt_um_MichaelBell_rle_vga | sim-timeout | line None clocks, ? lines, hsync transitions ? |
| tt09/tt_um_rejunity_atari2600 | build-failed | verilator failed |
| ttgf0p2/tt_um_algofoogle_vgaringosc | build-failed | verilator failed |
| ttgf26a/tt_um_pixel_processor | build-failed | verilator failed |
| ttgf26b/tt_um_LukeSilva_cartrip | build-failed | verilator failed |
| ttihp0p1/tt_um_algofoogle_raybox_zero | build-failed | missing sources: raybox-zero/src/rtl/fixed_point_params.v, raybox-zero/src/rtl/helpers.v, raybox-zero/src/rtl/rbzero.v, raybox-zero/src/rtl/spi_registers.v, raybox-zero/src/rtl/debug_overlay.v, raybox-zero/src/rtl/map_overlay.v, raybox-zero/src/rtl/map_rom.v, raybox-zero/src/rtl/pov.v, raybox-zero/src/rtl/lzc.v, raybox-zero/src/rtl/reciprocal.v, raybox-zero/src/rtl/wall_tracer.v, raybox-zero/src/rtl/row_render.v, raybox-zero/src/rtl/vga_mux.v, raybox-zero/src/rtl/vga_sync.v, raybox-zero/src/rtl/top_raybox_zero_fsm.v |
| ttihp0p4/tt_um_algofoogle_vgaringosc | build-failed | verilator failed |
| ttihp25a/tt_um_toivoh_demo_tt08 | build-failed | verilator failed |
| ttihp26a/tt_um_lkhanh_vga_trng | build-failed | verilator failed |
| ttsky25a/tt_um_rejunity_atari2600 | build-failed | verilator failed |
| ttsky26a/tt_um_prime_quine | build-failed | verilator failed |
| tt06/tt_um_alexsegura_pong | fetch-failed | fetch failed |
