// SPDX-License-Identifier: Apache-2.0
//
// Test design: bars640.v, but its syncs only toggle while ui_in is exactly 0x04,
// so it syncs only once the job's input probe has found that value. Otherwise
// hsync and vsync stay high (inactive) and there is no raster.

`default_nettype none

module tt_um_test_needs_ui2 (
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
  reg [6:0] bar_px;     // pixel within the current bar, 0..79
  reg [2:0] bar;        // colour of the current bar
  reg [2:0] frame;      // rotates the bars
  reg [7:0] out;

  wire mode   = ui_in == 8'h04;
  wire active = h < 640 && v < 480;
  wire hsync  = !(h >= 656 && h < 752);
  wire vsync  = !(v >= 490 && v < 492);

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
      // uo_out: {hsync, b0, g0, r0, vsync, b1, g1, r1}
      out <= {hsync | !mode, active ? bar : 3'b000, vsync | !mode, active ? bar : 3'b000};
    end
  end

  assign uo_out  = out;
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;
  wire _unused = &{ena, uio_in, 1'b0};
endmodule
