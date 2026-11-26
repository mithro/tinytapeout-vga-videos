// SPDX-License-Identifier: Apache-2.0
//
// Test design: 640x480@60 at one pixel per clock with active-low syncs, as
// bars640, but with pins that change on the clk-low half of a clock, which the
// trace samples separately. The fast-vs-fallback trace test needs them:
//   uo_out[0] (r1)  a register clocked on negedge clk, toggling every 37 clocks;
//   uo_out[1] (g1)  ~clk & m: m (a posedge register, toggling every 53 clocks)
//                   shows only while clk is low, so the clk-high samples of
//                   every clock agree and only the clk-low samples change.
// The other colour bits are eight vertical bars.

`default_nettype none

module tt_um_test_negedge (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  reg [9:0] h, v;
  reg [5:0] ncount, mcount;
  reg n, m;

  wire active = h < 640 && v < 480;
  wire hsync  = !(h >= 656 && h < 752);
  wire vsync  = !(v >= 490 && v < 492);
  wire [2:0] bar = active ? h[9:7] : 3'b000;

  always @(posedge clk) begin
    if (!rst_n) begin
      h <= 0; v <= 0; mcount <= 0; m <= 0;
    end else begin
      if (h == 799) begin
        h <= 0;
        v <= (v == 524) ? 10'd0 : v + 1;
      end else h <= h + 1;
      if (mcount == 52) begin mcount <= 0; m <= !m; end
      else mcount <= mcount + 1;
    end
  end

  always @(negedge clk) begin
    if (!rst_n) begin
      ncount <= 0; n <= 0;
    end else if (ncount == 36) begin
      ncount <= 0; n <= !n;
    end else ncount <= ncount + 1;
  end

  // uo_out: {hsync, b0, g0, r0, vsync, b1, g1, r1}
  assign uo_out  = {hsync, bar, vsync, bar[2], ~clk & m, n};
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;
  wire _unused = &{ena, ui_in, uio_in, 1'b0};
endmodule
