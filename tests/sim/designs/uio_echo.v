// SPDX-License-Identifier: Apache-2.0
//
// Test design: uio_out follows ui_in and the upper four uio pins are
// outputs, so a trace shows the ports in known states.

`default_nettype none

module tt_um_test_uio_echo (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  assign uo_out  = 8'h00;
  assign uio_out = ui_in;
  assign uio_oe  = 8'hF0;
  wire _unused = &{ena, clk, rst_n, uio_in, 1'b0};
endmodule
