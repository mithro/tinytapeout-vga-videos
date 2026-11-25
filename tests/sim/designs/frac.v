// SPDX-License-Identifier: Apache-2.0
//
// Test design: 640x480@60 timing with 1,525-clock lines, run at
// 48,000,000 Hz, so a pixel is 1.90625 clocks. A line is 183 clocks of
// hsync, 91 of back porch, 1,216 of bars (eight of 152 clocks) and 35 of
// black (the front porch, plus 4 clocks where the 640-pixel area, 1,220
// clocks, outlasts the bars).

`default_nettype none

module tt_um_test_frac (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  // h counts from the start of the hsync pulse.
  reg [10:0] h;
  reg [9:0]  v;
  reg [7:0]  bar_px;
  reg [2:0]  bar;
  reg [2:0]  frame;
  reg [7:0]  out;

  wire hsync  = !(h < 183);
  wire hact   = h >= 274 && h < 274 + 1216;
  wire vsync  = !(v >= 490 && v < 492);
  wire active = hact && v < 480;

  always @(posedge clk) begin
    if (!rst_n) begin
      h <= 0; v <= 0; bar_px <= 0; bar <= 0; frame <= 0; out <= 8'h88;
    end else begin
      if (h == 1524) begin
        h <= 0;
        if (v == 524) begin v <= 0; frame <= frame + 1; end
        else v <= v + 1;
      end else h <= h + 1;
      if (!hact) begin bar_px <= 0; bar <= frame; end
      else if (bar_px == 151) begin bar_px <= 0; bar <= bar + 1; end
      else bar_px <= bar_px + 1;
      out <= {hsync, active ? bar : 3'b000, vsync, active ? bar : 3'b000};
    end
  end

  assign uo_out  = out;
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;
  wire _unused = &{ena, ui_in, uio_in, 1'b0};
endmodule
