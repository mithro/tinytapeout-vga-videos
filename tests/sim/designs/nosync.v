// SPDX-License-Identifier: Apache-2.0
//
// Test design: a constant uo_out, so there is never a sync signal.

`default_nettype none

module tt_um_test_nosync (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  assign uo_out  = 8'h88;
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;
  wire _unused = &{ena, clk, rst_n, ui_in, uio_in, 1'b0};
endmodule
