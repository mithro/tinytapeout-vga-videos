// SPDX-License-Identifier: Apache-2.0
//
// Test design: bars640.v plus a free-running xorshift32 on uio_out, so a
// trace of it barely compresses and fills the trace writer's file buffer
// (1 MiB) within a block or two. For tests that kill the model and need
// whole blocks already on disk.

`default_nettype none

module tt_um_test_noisy (
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
  reg [31:0] x;

  wire active = h < 640 && v < 480;
  wire hsync  = !(h >= 656 && h < 752);
  wire vsync  = !(v >= 490 && v < 492);
  wire [31:0] x1 = x ^ (x << 13);
  wire [31:0] x2 = x1 ^ (x1 >> 17);
  wire [31:0] x3 = x2 ^ (x2 << 5);

  always @(posedge clk) begin
    if (!rst_n) begin
      h <= 0; v <= 0; bar_px <= 0; bar <= 0; frame <= 0; out <= 8'h88; x <= 32'h2545F491;
    end else begin
      x <= x3;
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
  assign uio_out = x[15:8];
  assign uio_oe  = 8'hFF;
  wire _unused = &{ena, ui_in, uio_in, 1'b0};
endmodule
