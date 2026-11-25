// SPDX-License-Identifier: Apache-2.0
//
// Test design: the timing of the VGA Playground's hvsync_generator
// (640x480; hsync and vsync registered from the counters, so they lag the
// colour, which is computed from the counters combinationally, by one
// clock), with a pattern that moves one pixel a frame.

`default_nettype none

module tt_um_test_playground (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  localparam H_DISPLAY = 640, H_BACK = 48, H_FRONT = 16, H_SYNC = 96;
  localparam V_DISPLAY = 480, V_TOP = 33, V_BOTTOM = 10, V_SYNC = 2;
  localparam H_SYNC_START = H_DISPLAY + H_FRONT;
  localparam H_SYNC_END   = H_DISPLAY + H_FRONT + H_SYNC - 1;
  localparam H_MAX        = H_DISPLAY + H_BACK + H_FRONT + H_SYNC - 1;
  localparam V_SYNC_START = V_DISPLAY + V_BOTTOM;
  localparam V_SYNC_END   = V_DISPLAY + V_BOTTOM + V_SYNC - 1;
  localparam V_MAX        = V_DISPLAY + V_TOP + V_BOTTOM + V_SYNC - 1;

  reg [9:0] hpos, vpos;
  reg       hsync, vsync;
  reg [9:0] counter;    // frames
  wire hmaxxed = hpos == H_MAX;
  wire vmaxxed = vpos == V_MAX;
  wire display_on = hpos < H_DISPLAY && vpos < V_DISPLAY;

  always @(posedge clk) begin
    if (!rst_n) begin
      hpos <= 0; hsync <= 1;
    end else begin
      hsync <= ~(hpos >= H_SYNC_START && hpos <= H_SYNC_END);
      hpos  <= hmaxxed ? 10'd0 : hpos + 1;
    end
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      vpos <= 0; vsync <= 1; counter <= 0;
    end else begin
      vsync <= ~(vpos >= V_SYNC_START && vpos <= V_SYNC_END);
      if (hmaxxed) begin
        vpos <= vmaxxed ? 10'd0 : vpos + 1;
        if (vmaxxed) counter <= counter + 1;
      end
    end
  end

  wire [9:0] x = hpos + counter;
  wire [1:0] R = display_on ? x[6:5] : 2'b00;
  wire [1:0] G = display_on ? vpos[6:5] : 2'b00;
  wire [1:0] B = display_on ? x[7:6] ^ vpos[7:6] : 2'b00;

  assign uo_out  = {hsync, B[0], G[0], R[0], vsync, B[1], G[1], R[1]};
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;
  wire _unused = &{ena, ui_in, uio_in, 1'b0};
endmodule
