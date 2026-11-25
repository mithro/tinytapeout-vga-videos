// SPDX-License-Identifier: Apache-2.0
//
// Test design: bars640.v with a one-clock glitch inside the vsync pulse of
// every fourth frame: in the pulse's first line, at h == 400, vsync is
// inactive for one clock.

`default_nettype none

module tt_um_test_glitch (
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
  reg [6:0] bar_px;
  reg [2:0] bar;
  reg [2:0] frame;
  reg [7:0] out;

  wire active = h < 640 && v < 480;
  wire hsync  = !(h >= 656 && h < 752);
  wire glitch = frame[1:0] == 2'd0 && v == 490 && h == 400;   // frames 0, 4, 8, ...
  wire vsync  = !(v >= 490 && v < 492) || glitch;

  always @(posedge clk) begin
    if (!rst_n) begin
      h <= 0; v <= 0; bar_px <= 0; bar <= 0; frame <= 0; out <= 8'h88;
    end else begin
      if (h == 799) begin
        h <= 0;
        if (v == 524) begin v <= 0; frame <= frame + 1; end
        else v <= v + 1;
      end else h <= h + 1;
      if (h == 799) begin bar_px <= 0; bar <= frame + ((v == 524) ? 3'd1 : 3'd0); end
      else if (bar_px == 79) begin bar_px <= 0; bar <= bar + 1; end
      else bar_px <= bar_px + 1;
      out <= {hsync, active ? bar : 3'b000, vsync, active ? bar : 3'b000};
    end
  end

  assign uo_out  = out;
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;
  wire _unused = &{ena, ui_in, uio_in, 1'b0};
endmodule
