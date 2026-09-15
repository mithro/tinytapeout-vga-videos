# Behavioural cell models for simulation

`sky130_polyfill.v` is the polyfill Tiny Tapeout uses to re-harden sky130
projects on IHP: behavioural Verilog for 410 `sky130_fd_sc_hd__*` cells.
Copied from https://github.com/TinyTapeout/tt09-ttihp25a-reharden
(`hdl/tt_um_toivoh_demo/src/sky130_polyfill.v`), Apache-2.0, Tiny Tapeout LTD.

Verilator picks modules up from this directory with `-y`, so projects that
instantiate sky130 latches, clock gates or buffers directly in their RTL
build without the PDK. Projects on IHP or GF that instantiate their PDK's
cells (so far only ring oscillators) are not covered.
