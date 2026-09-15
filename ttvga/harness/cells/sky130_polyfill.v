`default_nettype none

module polyfill__universal_flop(input CLK, D, DE, RESET_B, SET_B, SCD, SCE, output reg Q, output Q_N);
always @(posedge CLK, negedge RESET_B, negedge SET_B) begin
    if(~SET_B) Q <= 1'b1;
    else if(~RESET_B) Q <= 1'b0;
    else if(SCE) Q <= SCD;
    else if(DE) Q <= D;
end
assign Q_N = ~Q;
endmodule

module polyfill__universal_latch(input D, GATE, RESET_B, output reg Q, output Q_N);
always @(*) begin
    if(~RESET_B) Q = 1'b0;
    else if(GATE) Q = D;
end
assign Q_N = ~Q;
endmodule

module polyfill__clock_gate(input CLK, GATE, output reg GCLK);
always @(CLK) begin
    GCLK = CLK & GATE;
end
endmodule

module polyfill__conb(output HI, LO); assign {HI, LO} = 2'b10; endmodule
module polyfill__buf(input A, output X); assign X = A; endmodule
module polyfill__inv(input A, output Y); assign Y = ~A; endmodule
module polyfill__and2(input A, B, output X); assign X = A & B; endmodule
module polyfill__and2b(input A_N, B, output X); assign X = ~A_N & B; endmodule
module polyfill__and3(input A, B, C, output X); assign X = A & B & C; endmodule
module polyfill__and3b(input A_N, B, C, output X); assign X = ~A_N & B & C; endmodule
module polyfill__and4(input A, B, C, D, output X); assign X = A & B & C & D; endmodule
module polyfill__and4b(input A_N, B, C, D, output X); assign X = ~A_N & B & C & D; endmodule
module polyfill__and4bb(input A_N, B_N, C, D, output X); assign X = ~A_N & ~B_N & C & D; endmodule
module polyfill__nand2(input A, B, output Y); assign Y = ~(A & B); endmodule
module polyfill__nand2b(input A_N, B, output Y); assign Y = ~(~A_N & B); endmodule
module polyfill__nand3(input A, B, C, output Y); assign Y = ~(A & B & C); endmodule
module polyfill__nand3b(input A_N, B, C, output Y); assign Y = ~(~A_N & B & C); endmodule
module polyfill__nand4(input A, B, C, D, output Y); assign Y = ~(A & B & C & D); endmodule
module polyfill__nand4b(input A_N, B, C, D, output Y); assign Y = ~(~A_N & B & C & D); endmodule
module polyfill__nand4bb(input A_N, B_N, C, D, output Y); assign Y = ~(~A_N & ~B_N & C & D); endmodule
module polyfill__or2(input A, B, output X); assign X = A | B; endmodule
module polyfill__or2b(input A, B_N, output X); assign X = A | ~B_N; endmodule
module polyfill__or3(input A, B, C, output X); assign X = A | B | C; endmodule
module polyfill__or3b(input A, B, C_N, output X); assign X = A | B | ~C_N; endmodule
module polyfill__or4(input A, B, C, D, output X); assign X = A | B | C | D; endmodule
module polyfill__or4b(input A, B, C, D_N, output X); assign X = A | B | C | ~D_N; endmodule
module polyfill__or4bb(input A, B, C_N, D_N, output X); assign X = A | B | ~C_N | ~D_N; endmodule
module polyfill__nor2(input A, B, output Y); assign Y = ~(A | B); endmodule
module polyfill__nor2b(input A, B_N, output Y); assign Y = ~(A | ~B_N); endmodule
module polyfill__nor3(input A, B, C, output Y); assign Y = ~(A | B | C); endmodule
module polyfill__nor3b(input A, B, C_N, output Y); assign Y = ~(A | B | ~C_N); endmodule
module polyfill__nor4(input A, B, C, D, output Y); assign Y = ~(A | B | C | D); endmodule
module polyfill__nor4b(input A, B, C, D_N, output Y); assign Y = ~(A | B | C | ~D_N); endmodule
module polyfill__nor4bb(input A, B, C_N, D_N, output Y); assign Y = ~(A | B | ~C_N | ~D_N); endmodule
module polyfill__xor2(input A, B, output X); assign X = A ^ B; endmodule
module polyfill__xor3(input A, B, C, output X); assign X = A ^ B ^ C; endmodule
module polyfill__xnor2(input A, B, output Y); assign Y = ~(A ^ B); endmodule
module polyfill__xnor3(input A, B, C, output X); assign X = ~(A ^ B ^ C); endmodule
module polyfill__a2111o(input A1, A2, B1, C1, D1, output X); assign X = (A1 & A2) | B1 | C1 | D1; endmodule
module polyfill__a2111oi(input A1, A2, B1, C1, D1, output Y); assign Y = ~((A1 & A2) | B1 | C1 | D1); endmodule
module polyfill__a211o(input A1, A2, B1, C1, output X); assign X = (A1 & A2) | B1 | C1;  endmodule
module polyfill__a211oi(input A1, A2, B1, C1, output Y); assign Y = ~((A1 & A2) | B1 | C1); endmodule
module polyfill__a21bo(input A1, A2, B1_N, output X); assign X = (A1 & A2) | ~B1_N; endmodule
module polyfill__a21boi(input A1, A2, B1_N, output Y); assign Y = ~((A1 & A2) | ~B1_N); endmodule
module polyfill__a21o(input A1, A2, B1, output X); assign X = (A1 & A2) | B1; endmodule
module polyfill__a21oi(input A1, A2, B1, output Y); assign Y = ~((A1 & A2) | B1); endmodule
module polyfill__a221o(input A1, A2, B1, B2, C1, output X); assign X = (A1 & A2) | (B1 & B2) | C1; endmodule
module polyfill__a221oi(input A1, A2, B1, B2, C1, output Y); assign Y = ~((A1 & A2) | (B1 & B2) | C1); endmodule
module polyfill__a222oi(input A1, A2, B1, B2, C1, C2, output Y); assign Y = ~((A1 & A2) | (B1 & B2) | (C1 & C2)); endmodule
module polyfill__a22o(input A1, A2, B1, B2, output X); assign X = (A1 & A2) | (B1 & B2); endmodule
module polyfill__a22oi(input A1, A2, B1, B2, output Y); assign Y = ~((A1 & A2) | (B1 & B2)); endmodule
module polyfill__a2bb2o(input A1_N, A2_N, B1, B2, output X); assign X = (~A1_N & ~A2_N) | (B1 & B2); endmodule
module polyfill__a2bb2oi(input A1_N, A2_N, B1, B2, output Y); assign Y = ~((~A1_N & ~A2_N) | (B1 & B2)); endmodule
module polyfill__a311o(input A1, A2, A3, B1, C1, output X); assign X = (A1 & A2 & A3) | B1 | C1; endmodule
module polyfill__a311oi(input A1, A2, A3, B1, C1, output Y); assign Y = ~((A1 & A2 & A3) | B1 | C1); endmodule
module polyfill__a31o(input A1, A2, A3, B1, output X); assign X = (A1 & A2 & A3) | B1; endmodule
module polyfill__a31oi(input A1, A2, A3, B1, output Y); assign Y = ~((A1 & A2 & A3) | B1); endmodule
module polyfill__a32o(input A1, A2, A3, B1, B2, output X); assign X = (A1 & A2 & A3) | (B1 & B2); endmodule
module polyfill__a32oi(input A1, A2, A3, B1, B2, output Y); assign Y = ~((A1 & A2 & A3) | (B1 & B2)); endmodule
module polyfill__a41o(input A1, A2, A3, A4, B1, output X); assign X = (A1 & A2 & A3 & A4) | B1; endmodule
module polyfill__a41oi(input A1, A2, A3, A4, B1, output Y); assign Y = ~((A1 & A2 & A3 & A4) | B1); endmodule
module polyfill__o2111a(input A1, A2, B1, C1, D1, output X); assign X = (A1 | A2) & B1 & C1 & D1; endmodule
module polyfill__o2111ai(input A1, A2, B1, C1, D1, output Y); assign Y = ~((A1 | A2) & B1 & C1 & D1); endmodule
module polyfill__o211a(input A1, A2, B1, C1, output X); assign X = (A1 | A2) & B1 & C1; endmodule
module polyfill__o211ai(input A1, A2, B1, C1, output Y); assign Y = ~((A1 | A2) & B1 & C1); endmodule
module polyfill__o21a(input A1, A2, B1, output X); assign X = (A1 | A2) & B1; endmodule
module polyfill__o21ai(input A1, A2, B1, output Y); assign Y = ~((A1 | A2) & B1); endmodule
module polyfill__o21ba(input A1, A2, B1_N, output X); assign X = (A1 | A2) & ~B1_N; endmodule
module polyfill__o21bai(input A1, A2, B1_N, output Y); assign Y = ~((A1 | A2) & ~B1_N); endmodule
module polyfill__o221a(input A1, A2, B1, B2, C1, output X); assign X = (A1 | A2) & (B1 | B2) & C1; endmodule
module polyfill__o221ai(input A1, A2, B1, B2, C1, output Y); assign Y = ~((A1 | A2) & (B1 | B2) & C1); endmodule
module polyfill__o22a(input A1, A2, B1, B2, output X); assign X = (A1 | A2) & (B1 | B2); endmodule
module polyfill__o22ai(input A1, A2, B1, B2, output Y); assign Y = ~((A1 | A2) & (B1 | B2)); endmodule
module polyfill__o2bb2a(input A1_N, A2_N, B1, B2, output X); assign X = (~A1_N | ~A2_N) & (B1 | B2); endmodule
module polyfill__o2bb2ai(input A1_N, A2_N, B1, B2, output Y); assign Y = ~((~A1_N | ~A2_N) & (B1 | B2)); endmodule
module polyfill__o311a(input A1, A2, A3, B1, C1, output X); assign X = (A1 | A2 | A3) & B1 & C1; endmodule
module polyfill__o311ai(input A1, A2, A3, B1, C1, output Y); assign Y = ~((A1 | A2 | A3) & B1 & C1); endmodule
module polyfill__o31a(input A1, A2, A3, B1, output X); assign X = (A1 | A2 | A3) & B1; endmodule
module polyfill__o31ai(input A1, A2, A3, B1, output Y); assign Y = ~((A1 | A2 | A3) & B1); endmodule
module polyfill__o32a(input A1, A2, A3, B1, B2, output X); assign X = (A1 | A2 | A3) & (B1 | B2); endmodule
module polyfill__o32ai(input A1, A2, A3, B1, B2, output Y); assign Y = ~((A1 | A2 | A3) & (B1 | B2)); endmodule
module polyfill__o41a(input A1, A2, A3, A4, B1, output X); assign X = (A1 | A2 | A3 | A4) & B1; endmodule
module polyfill__o41ai(input A1, A2, A3, A4, B1, output Y); assign Y = ~((A1 | A2 | A3 | A4) & B1); endmodule
module polyfill__mux2(input A0, A1, S, output X); assign X = S ? A1 : A0; endmodule
module polyfill__mux2i(input A0, A1, S, output Y); assign Y = ~(S ? A1 : A0); endmodule
module polyfill__mux4(input A0, A1, A2, A3, S0, S1, output X); assign X = S1 ? (S0 ? A3 : A2) : (S0 ? A1 : A0); endmodule
module polyfill__maj3(input A, B, C, output X); assign X = {1'b0, A} + {1'b0, B} + {1'b0, C} >= 2'b10; endmodule
module polyfill__ha(input A, B, output COUT, SUM); assign {COUT, SUM} = {1'b0, A} + {1'b0, B}; endmodule
module polyfill__fa(input A, B, CIN, output COUT, SUM); assign {COUT, SUM} = {1'b0, A} + {1'b0, B} + {1'b0, CIN}; endmodule
module polyfill__fah(input A, B, CI, output COUT, SUM); assign {COUT, SUM} = {1'b0, A} + {1'b0, B} + {1'b0, CI}; endmodule
module polyfill__fahcin(input A, B, CIN, output COUT, SUM); assign {COUT, SUM} = {1'b0, A} + {1'b0, B} + {1'b0, ~CIN}; endmodule
module polyfill__fahcon(input A, B, CI, output COUT_N, SUM); assign {COUT_N, SUM} = {1'b0, A} + {1'b0, B} + {1'b1, CI}; endmodule
module polyfill__ebufn(input A, TE_B, output Z); assign Z = TE_B ? 1'bz : A; endmodule
module polyfill__einvn(input A, TE_B, output Z); assign Z = TE_B ? 1'bz : ~A; endmodule
module polyfill__einvp(input A, TE, output Z); assign Z = TE ? ~A : 1'bz;  endmodule

module polyfill__bufbuf(input A, output X); assign X = A; endmodule
module polyfill__bufinv(input A, output Y); assign Y = ~A; endmodule
module polyfill__clkbuf(input A, output X); assign X = A; endmodule
module polyfill__clkdlybuf4s15(input A, output X); assign X = A; endmodule
module polyfill__clkdlybuf4s18(input A, output X); assign X = A; endmodule
module polyfill__clkdlybuf4s25(input A, output X); assign X = A; endmodule
module polyfill__clkdlybuf4s50(input A, output X); assign X = A; endmodule
module polyfill__clkinv(input A, output Y); assign Y = ~A; endmodule
module polyfill__clkinvlp(input A, output Y); assign Y = ~A; endmodule
module polyfill__dlygate4sd1(input A, output X); assign X = A; endmodule
module polyfill__dlygate4sd2(input A, output X); assign X = A; endmodule
module polyfill__dlygate4sd3(input A, output X); assign X = A; endmodule
module polyfill__dlymetal6s2s(input A, output X); assign X = A; endmodule
module polyfill__dlymetal6s4s(input A, output X); assign X = A; endmodule
module polyfill__dlymetal6s6s(input A, output X); assign X = A; endmodule
module polyfill__lpflow_inputiso0n(input A, SLEEP_B, output X); assign X = A & SLEEP_B; endmodule
module polyfill__lpflow_inputiso0p(input A, SLEEP, output X); assign X = A & ~SLEEP; endmodule
module polyfill__lpflow_inputiso1n(input A, SLEEP_B, output X); assign X = A | ~SLEEP_B; endmodule
module polyfill__lpflow_inputiso1p(input A, SLEEP, output X); assign X = A | SLEEP; endmodule
module polyfill__lpflow_isobufsrc(input A, SLEEP, output X); assign X = A & ~SLEEP; endmodule

module polyfill__dfbbn(input CLK_N, D, RESET_B, SET_B, output Q, Q_N); polyfill__universal_flop uf(.CLK(~CLK_N), .D, .DE(1'b1), .RESET_B, .SET_B, .SCD(1'b0), .SCE(1'b0), .Q, .Q_N); endmodule 
module polyfill__dfbbp(input CLK, D, RESET_B, SET_B, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B, .SET_B, .SCD(1'b0), .SCE(1'b0), .Q, .Q_N); endmodule 
module polyfill__dfrbp(input CLK, D, RESET_B, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B, .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N); endmodule 
module polyfill__dfrtn(input CLK_N, D, RESET_B, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK(~CLK_N), .D, .DE(1'b1), .RESET_B, .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N(_Q_N)); endmodule
module polyfill__dfrtp(input CLK, D, RESET_B, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B, .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N(_Q_N)); endmodule
module polyfill__dfsbp(input CLK, D, SET_B, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B, .SCD(1'b0), .SCE(1'b0), .Q, .Q_N); endmodule
module polyfill__dfstp(input CLK, D, SET_B, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B, .SCD(1'b0), .SCE(1'b0), .Q, .Q_N(_Q_N)); endmodule
module polyfill__dfxbp(input CLK, D, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N); endmodule
module polyfill__dfxtp(input CLK, D, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N(_Q_N)); endmodule
module polyfill__edfxbp(input CLK, D, DE, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE, .RESET_B(1'b1), .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N); endmodule
module polyfill__edfxtp(input CLK, D, DE, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE, .RESET_B(1'b1), .SET_B(1'b1), .SCD(1'b0), .SCE(1'b0), .Q, .Q_N(_Q_N)); endmodule
module polyfill__sdfbbn(input CLK_N, D, RESET_B, SET_B, SCD, SCE, output Q, Q_N); polyfill__universal_flop uf(.CLK(~CLK_N), .D, .DE(1'b1), .RESET_B, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule 
module polyfill__sdfbbp(input CLK, D, RESET_B, SET_B, SCD, SCE, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule 
module polyfill__sdfrbp(input CLK, D, RESET_B, SCD, SCE, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B, .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N); endmodule 
module polyfill__sdfrtn(input CLK_N, D, RESET_B, SCD, SCE, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK(~CLK_N), .D, .DE(1'b1), .RESET_B, .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N(_Q_N)); endmodule
module polyfill__sdfrtp(input CLK, D, RESET_B, SCD, SCE, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B, .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N(_Q_N)); endmodule
module polyfill__sdfsbp(input CLK, D, SET_B, SCD, SCE, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module polyfill__sdfstp(input CLK, D, SET_B, SCD, SCE, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B, .SCD, .SCE, .Q, .Q_N(_Q_N)); endmodule
module polyfill__sdfxbp(input CLK, D, SCD, SCE, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N); endmodule
module polyfill__sdfxtp(input CLK, D, SCD, SCE, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE(1'b1), .RESET_B(1'b1), .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N(_Q_N)); endmodule
module polyfill__sedfxbp(input CLK, D, DE, SCD, SCE, output Q, Q_N); polyfill__universal_flop uf(.CLK, .D, .DE, .RESET_B(1'b1), .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N); endmodule
module polyfill__sedfxtp(input CLK, D, DE, SCD, SCE, output Q); wire _Q_N; polyfill__universal_flop uf(.CLK, .D, .DE, .RESET_B(1'b1), .SET_B(1'b1), .SCD, .SCE, .Q, .Q_N(_Q_N)); endmodule

module polyfill__dlrbn(input D, GATE_N, RESET_B, output Q, Q_N); polyfill__universal_latch ul(.D, .GATE(~GATE_N), .RESET_B, .Q, .Q_N); endmodule
module polyfill__dlrbp(input D, GATE, RESET_B, output Q, Q_N); polyfill__universal_latch ul(.D, .GATE, .RESET_B, .Q, .Q_N); endmodule
module polyfill__dlrtn(input D, GATE_N, RESET_B, output Q); wire _Q_N; polyfill__universal_latch ul(.D, .GATE(~GATE_N), .RESET_B, .Q, .Q_N(_Q_N)); endmodule
module polyfill__dlrtp(input D, GATE, RESET_B, output Q); wire _Q_N; polyfill__universal_latch ul(.D, .GATE, .RESET_B, .Q, .Q_N(_Q_N)); endmodule
module polyfill__dlxbn(input D, GATE_N, output Q, Q_N); polyfill__universal_latch ul(.D, .GATE(~GATE_N), .RESET_B(1'b1), .Q, .Q_N); endmodule
module polyfill__dlxbp(input D, GATE, output Q, Q_N); polyfill__universal_latch ul(.D, .GATE, .RESET_B(1'b1), .Q, .Q_N); endmodule
module polyfill__dlxtn(input D, GATE_N, output Q); wire _Q_N; polyfill__universal_latch ul(.D, .GATE(~GATE_N), .RESET_B(1'b1), .Q, .Q_N(_Q_N)); endmodule
module polyfill__dlxtp(input D, GATE, output Q); wire _Q_N; polyfill__universal_latch ul(.D, .GATE, .RESET_B(1'b1), .Q, .Q_N(_Q_N)); endmodule
module polyfill__lpflow_inputisolatch(input D, SLEEP_B, output Q); wire _Q_N; polyfill__universal_latch ul(.D, .GATE(SLEEP_B), .RESET_B(1'b1), .Q, .Q_N(_Q_N)); endmodule

module polyfill__dlclkp(input CLK, GATE, output GCLK); polyfill__clock_gate cg(.CLK, .GATE, .GCLK); endmodule
module polyfill__sdlclkp(input CLK, GATE, SCE, output GCLK); polyfill__clock_gate cg(.CLK, .GATE(GATE | SCE), .GCLK); endmodule

(* noblackbox *) module polyfill__fill(); endmodule
(* noblackbox *) module polyfill__decap(); endmodule
(* noblackbox *) module polyfill__diode(input DIODE); endmodule
(* noblackbox *) module polyfill__tap(); endmodule
(* noblackbox *) module polyfill__tapvgnd(); endmodule
(* noblackbox *) module polyfill__tapvgnd2(); endmodule
(* noblackbox *) module polyfill__tapvpwrvgnd(); endmodule

module sky130_fd_sc_hd__a2111o_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output X); polyfill__a2111o pf(.A1, .A2, .B1, .C1, .D1, .X); endmodule
module sky130_fd_sc_hd__a2111o_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output X); polyfill__a2111o pf(.A1, .A2, .B1, .C1, .D1, .X); endmodule
module sky130_fd_sc_hd__a2111o_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output X); polyfill__a2111o pf(.A1, .A2, .B1, .C1, .D1, .X); endmodule
module sky130_fd_sc_hd__a2111oi_0(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__a2111oi pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__a2111oi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__a2111oi pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__a2111oi_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__a2111oi pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__a2111oi_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__a2111oi pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__a211o_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output X); polyfill__a211o pf(.A1, .A2, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__a211o_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output X); polyfill__a211o pf(.A1, .A2, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__a211o_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output X); polyfill__a211o pf(.A1, .A2, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__a211oi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output Y); polyfill__a211oi pf(.A1, .A2, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__a211oi_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output Y); polyfill__a211oi pf(.A1, .A2, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__a211oi_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output Y); polyfill__a211oi pf(.A1, .A2, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__a21bo_1(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output X); polyfill__a21bo pf(.A1, .A2, .B1_N, .X); endmodule
module sky130_fd_sc_hd__a21bo_2(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output X); polyfill__a21bo pf(.A1, .A2, .B1_N, .X); endmodule
module sky130_fd_sc_hd__a21bo_4(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output X); polyfill__a21bo pf(.A1, .A2, .B1_N, .X); endmodule
module sky130_fd_sc_hd__a21boi_0(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__a21boi pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__a21boi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__a21boi pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__a21boi_2(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__a21boi pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__a21boi_4(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__a21boi pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__a21o_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, output X); polyfill__a21o pf(.A1, .A2, .B1, .X); endmodule
module sky130_fd_sc_hd__a21o_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, output X); polyfill__a21o pf(.A1, .A2, .B1, .X); endmodule
module sky130_fd_sc_hd__a21o_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, output X); polyfill__a21o pf(.A1, .A2, .B1, .X); endmodule
module sky130_fd_sc_hd__a21oi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__a21oi pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__a21oi_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__a21oi pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__a21oi_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__a21oi pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__a221o_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output X); polyfill__a221o pf(.A1, .A2, .B1, .B2, .C1, .X); endmodule
module sky130_fd_sc_hd__a221o_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output X); polyfill__a221o pf(.A1, .A2, .B1, .B2, .C1, .X); endmodule
module sky130_fd_sc_hd__a221o_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output X); polyfill__a221o pf(.A1, .A2, .B1, .B2, .C1, .X); endmodule
module sky130_fd_sc_hd__a221oi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output Y); polyfill__a221oi pf(.A1, .A2, .B1, .B2, .C1, .Y); endmodule
module sky130_fd_sc_hd__a221oi_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output Y); polyfill__a221oi pf(.A1, .A2, .B1, .B2, .C1, .Y); endmodule
module sky130_fd_sc_hd__a221oi_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output Y); polyfill__a221oi pf(.A1, .A2, .B1, .B2, .C1, .Y); endmodule
module sky130_fd_sc_hd__a222oi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, C2, output Y); polyfill__a222oi pf(.A1, .A2, .B1, .B2, .C1, .C2, .Y); endmodule
module sky130_fd_sc_hd__a22o_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output X); polyfill__a22o pf(.A1, .A2, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a22o_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output X); polyfill__a22o pf(.A1, .A2, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a22o_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output X); polyfill__a22o pf(.A1, .A2, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a22oi_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output Y); polyfill__a22oi pf(.A1, .A2, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a22oi_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output Y); polyfill__a22oi pf(.A1, .A2, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a22oi_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output Y); polyfill__a22oi pf(.A1, .A2, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a2bb2o_1(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output X); polyfill__a2bb2o pf(.A1_N, .A2_N, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a2bb2o_2(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output X); polyfill__a2bb2o pf(.A1_N, .A2_N, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a2bb2o_4(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output X); polyfill__a2bb2o pf(.A1_N, .A2_N, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a2bb2oi_1(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output Y); polyfill__a2bb2oi pf(.A1_N, .A2_N, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a2bb2oi_2(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output Y); polyfill__a2bb2oi pf(.A1_N, .A2_N, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a2bb2oi_4(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output Y); polyfill__a2bb2oi pf(.A1_N, .A2_N, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a311o_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output X); polyfill__a311o pf(.A1, .A2, .A3, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__a311o_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output X); polyfill__a311o pf(.A1, .A2, .A3, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__a311o_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output X); polyfill__a311o pf(.A1, .A2, .A3, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__a311oi_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__a311oi pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__a311oi_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__a311oi pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__a311oi_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__a311oi pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__a31o_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output X); polyfill__a31o pf(.A1, .A2, .A3, .B1, .X); endmodule
module sky130_fd_sc_hd__a31o_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output X); polyfill__a31o pf(.A1, .A2, .A3, .B1, .X); endmodule
module sky130_fd_sc_hd__a31o_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output X); polyfill__a31o pf(.A1, .A2, .A3, .B1, .X); endmodule
module sky130_fd_sc_hd__a31oi_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output Y); polyfill__a31oi pf(.A1, .A2, .A3, .B1, .Y); endmodule
module sky130_fd_sc_hd__a31oi_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output Y); polyfill__a31oi pf(.A1, .A2, .A3, .B1, .Y); endmodule
module sky130_fd_sc_hd__a31oi_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output Y); polyfill__a31oi pf(.A1, .A2, .A3, .B1, .Y); endmodule
module sky130_fd_sc_hd__a32o_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output X); polyfill__a32o pf(.A1, .A2, .A3, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a32o_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output X); polyfill__a32o pf(.A1, .A2, .A3, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a32o_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output X); polyfill__a32o pf(.A1, .A2, .A3, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__a32oi_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output Y); polyfill__a32oi pf(.A1, .A2, .A3, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a32oi_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output Y); polyfill__a32oi pf(.A1, .A2, .A3, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a32oi_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output Y); polyfill__a32oi pf(.A1, .A2, .A3, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__a41o_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output X); polyfill__a41o pf(.A1, .A2, .A3, .A4, .B1, .X); endmodule
module sky130_fd_sc_hd__a41o_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output X); polyfill__a41o pf(.A1, .A2, .A3, .A4, .B1, .X); endmodule
module sky130_fd_sc_hd__a41o_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output X); polyfill__a41o pf(.A1, .A2, .A3, .A4, .B1, .X); endmodule
module sky130_fd_sc_hd__a41oi_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output Y); polyfill__a41oi pf(.A1, .A2, .A3, .A4, .B1, .Y); endmodule
module sky130_fd_sc_hd__a41oi_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output Y); polyfill__a41oi pf(.A1, .A2, .A3, .A4, .B1, .Y); endmodule
module sky130_fd_sc_hd__a41oi_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output Y); polyfill__a41oi pf(.A1, .A2, .A3, .A4, .B1, .Y); endmodule
module sky130_fd_sc_hd__and2_0(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__and2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__and2_1(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__and2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__and2_2(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__and2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__and2_4(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__and2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__and2b_1(input VPWR, VGND, VPB, VNB, A_N, B, output X); polyfill__and2b pf(.A_N, .B, .X); endmodule
module sky130_fd_sc_hd__and2b_2(input VPWR, VGND, VPB, VNB, A_N, B, output X); polyfill__and2b pf(.A_N, .B, .X); endmodule
module sky130_fd_sc_hd__and2b_4(input VPWR, VGND, VPB, VNB, A_N, B, output X); polyfill__and2b pf(.A_N, .B, .X); endmodule
module sky130_fd_sc_hd__and3_1(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__and3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__and3_2(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__and3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__and3_4(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__and3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__and3b_1(input VPWR, VGND, VPB, VNB, A_N, B, C, output X); polyfill__and3b pf(.A_N, .B, .C, .X); endmodule
module sky130_fd_sc_hd__and3b_2(input VPWR, VGND, VPB, VNB, A_N, B, C, output X); polyfill__and3b pf(.A_N, .B, .C, .X); endmodule
module sky130_fd_sc_hd__and3b_4(input VPWR, VGND, VPB, VNB, A_N, B, C, output X); polyfill__and3b pf(.A_N, .B, .C, .X); endmodule
module sky130_fd_sc_hd__and4_1(input VPWR, VGND, VPB, VNB, A, B, C, D, output X); polyfill__and4 pf(.A, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4_2(input VPWR, VGND, VPB, VNB, A, B, C, D, output X); polyfill__and4 pf(.A, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4_4(input VPWR, VGND, VPB, VNB, A, B, C, D, output X); polyfill__and4 pf(.A, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4b_1(input VPWR, VGND, VPB, VNB, A_N, B, C, D, output X); polyfill__and4b pf(.A_N, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4b_2(input VPWR, VGND, VPB, VNB, A_N, B, C, D, output X); polyfill__and4b pf(.A_N, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4b_4(input VPWR, VGND, VPB, VNB, A_N, B, C, D, output X); polyfill__and4b pf(.A_N, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4bb_1(input VPWR, VGND, VPB, VNB, A_N, B_N, C, D, output X); polyfill__and4bb pf(.A_N, .B_N, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4bb_2(input VPWR, VGND, VPB, VNB, A_N, B_N, C, D, output X); polyfill__and4bb pf(.A_N, .B_N, .C, .D, .X); endmodule
module sky130_fd_sc_hd__and4bb_4(input VPWR, VGND, VPB, VNB, A_N, B_N, C, D, output X); polyfill__and4bb pf(.A_N, .B_N, .C, .D, .X); endmodule
module sky130_fd_sc_hd__buf_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__buf_2(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__buf_4(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__buf_6(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__buf_8(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__buf_12(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__buf_16(input VPWR, VGND, VPB, VNB, A, output X); polyfill__buf pf(.A, .X); endmodule
module sky130_fd_sc_hd__bufbuf_8(input VPWR, VGND, VPB, VNB, A, output X); polyfill__bufbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__bufbuf_16(input VPWR, VGND, VPB, VNB, A, output X); polyfill__bufbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__bufinv_8(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__bufinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__bufinv_16(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__bufinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkbuf_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkbuf_2(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkbuf_4(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkbuf_8(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkbuf_16(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkbuf pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s15_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s15 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s15_2(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s15 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s18_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s18 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s18_2(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s18 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s25_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s25 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s25_2(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s25 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s50_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s50 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkdlybuf4s50_2(input VPWR, VGND, VPB, VNB, A, output X); polyfill__clkdlybuf4s50 pf(.A, .X); endmodule
module sky130_fd_sc_hd__clkinv_1(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkinv_2(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkinv_4(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkinv_8(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkinv_16(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkinvlp_2(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinvlp pf(.A, .Y); endmodule
module sky130_fd_sc_hd__clkinvlp_4(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__clkinvlp pf(.A, .Y); endmodule
module sky130_fd_sc_hd__conb_1(input VPWR, VGND, VPB, VNB, output HI, LO); polyfill__conb pf(.HI, .LO); endmodule
module sky130_fd_sc_hd__decap_3(input VPWR, VGND, VPB, VNB); polyfill__decap pf(); endmodule
module sky130_fd_sc_hd__decap_4(input VPWR, VGND, VPB, VNB); polyfill__decap pf(); endmodule
module sky130_fd_sc_hd__decap_6(input VPWR, VGND, VPB, VNB); polyfill__decap pf(); endmodule
module sky130_fd_sc_hd__decap_8(input VPWR, VGND, VPB, VNB); polyfill__decap pf(); endmodule
module sky130_fd_sc_hd__decap_12(input VPWR, VGND, VPB, VNB); polyfill__decap pf(); endmodule
module sky130_ef_sc_hd__decap_12(input VPWR, VGND, VPB, VNB); polyfill__decap pf(); endmodule
module sky130_fd_sc_hd__dfbbn_1(input VPWR, VGND, VPB, VNB, CLK_N, D, RESET_B, SET_B, output Q, Q_N); polyfill__dfbbn pf(.CLK_N, .D, .RESET_B, .SET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfbbn_2(input VPWR, VGND, VPB, VNB, CLK_N, D, RESET_B, SET_B, output Q, Q_N); polyfill__dfbbn pf(.CLK_N, .D, .RESET_B, .SET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfbbp_1(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SET_B, output Q, Q_N); polyfill__dfbbp pf(.CLK, .D, .RESET_B, .SET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfrbp_1(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, output Q, Q_N); polyfill__dfrbp pf(.CLK, .D, .RESET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfrbp_2(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, output Q, Q_N); polyfill__dfrbp pf(.CLK, .D, .RESET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfrtn_1(input VPWR, VGND, VPB, VNB, CLK_N, D, RESET_B, output Q); polyfill__dfrtn pf(.CLK_N, .D, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dfrtp_1(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, output Q); polyfill__dfrtp pf(.CLK, .D, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dfrtp_2(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, output Q); polyfill__dfrtp pf(.CLK, .D, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dfrtp_4(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, output Q); polyfill__dfrtp pf(.CLK, .D, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dfsbp_1(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, output Q, Q_N); polyfill__dfsbp pf(.CLK, .D, .SET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfsbp_2(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, output Q, Q_N); polyfill__dfsbp pf(.CLK, .D, .SET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfstp_1(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, output Q); polyfill__dfstp pf(.CLK, .D, .SET_B, .Q); endmodule
module sky130_fd_sc_hd__dfstp_2(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, output Q); polyfill__dfstp pf(.CLK, .D, .SET_B, .Q); endmodule
module sky130_fd_sc_hd__dfstp_4(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, output Q); polyfill__dfstp pf(.CLK, .D, .SET_B, .Q); endmodule
module sky130_fd_sc_hd__dfxbp_1(input VPWR, VGND, VPB, VNB, CLK, D, output Q, Q_N); polyfill__dfxbp pf(.CLK, .D, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfxbp_2(input VPWR, VGND, VPB, VNB, CLK, D, output Q, Q_N); polyfill__dfxbp pf(.CLK, .D, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dfxtp_1(input VPWR, VGND, VPB, VNB, CLK, D, output Q); polyfill__dfxtp pf(.CLK, .D, .Q); endmodule
module sky130_fd_sc_hd__dfxtp_2(input VPWR, VGND, VPB, VNB, CLK, D, output Q); polyfill__dfxtp pf(.CLK, .D, .Q); endmodule
module sky130_fd_sc_hd__dfxtp_4(input VPWR, VGND, VPB, VNB, CLK, D, output Q); polyfill__dfxtp pf(.CLK, .D, .Q); endmodule
module sky130_fd_sc_hd__diode_2(input VPWR, VGND, VPB, VNB, DIODE); polyfill__diode pf(.DIODE); endmodule
module sky130_fd_sc_hd__dlclkp_1(input VPWR, VGND, VPB, VNB, CLK, GATE, output GCLK); polyfill__dlclkp pf(.CLK, .GATE, .GCLK); endmodule
module sky130_fd_sc_hd__dlclkp_2(input VPWR, VGND, VPB, VNB, CLK, GATE, output GCLK); polyfill__dlclkp pf(.CLK, .GATE, .GCLK); endmodule
module sky130_fd_sc_hd__dlclkp_4(input VPWR, VGND, VPB, VNB, CLK, GATE, output GCLK); polyfill__dlclkp pf(.CLK, .GATE, .GCLK); endmodule
module sky130_fd_sc_hd__dlrbn_1(input VPWR, VGND, VPB, VNB, D, GATE_N, RESET_B, output Q, Q_N); polyfill__dlrbn pf(.D, .GATE_N, .RESET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlrbn_2(input VPWR, VGND, VPB, VNB, D, GATE_N, RESET_B, output Q, Q_N); polyfill__dlrbn pf(.D, .GATE_N, .RESET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlrbp_1(input VPWR, VGND, VPB, VNB, D, GATE, RESET_B, output Q, Q_N); polyfill__dlrbp pf(.D, .GATE, .RESET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlrbp_2(input VPWR, VGND, VPB, VNB, D, GATE, RESET_B, output Q, Q_N); polyfill__dlrbp pf(.D, .GATE, .RESET_B, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlrtn_1(input VPWR, VGND, VPB, VNB, D, GATE_N, RESET_B, output Q); polyfill__dlrtn pf(.D, .GATE_N, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dlrtn_2(input VPWR, VGND, VPB, VNB, D, GATE_N, RESET_B, output Q); polyfill__dlrtn pf(.D, .GATE_N, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dlrtn_4(input VPWR, VGND, VPB, VNB, D, GATE_N, RESET_B, output Q); polyfill__dlrtn pf(.D, .GATE_N, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dlrtp_1(input VPWR, VGND, VPB, VNB, D, GATE, RESET_B, output Q); polyfill__dlrtp pf(.D, .GATE, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dlrtp_2(input VPWR, VGND, VPB, VNB, D, GATE, RESET_B, output Q); polyfill__dlrtp pf(.D, .GATE, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dlrtp_4(input VPWR, VGND, VPB, VNB, D, GATE, RESET_B, output Q); polyfill__dlrtp pf(.D, .GATE, .RESET_B, .Q); endmodule
module sky130_fd_sc_hd__dlxbn_1(input VPWR, VGND, VPB, VNB, D, GATE_N, output Q, Q_N); polyfill__dlxbn pf(.D, .GATE_N, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlxbn_2(input VPWR, VGND, VPB, VNB, D, GATE_N, output Q, Q_N); polyfill__dlxbn pf(.D, .GATE_N, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlxbp_1(input VPWR, VGND, VPB, VNB, D, GATE, output Q, Q_N); polyfill__dlxbp pf(.D, .GATE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__dlxtn_1(input VPWR, VGND, VPB, VNB, D, GATE_N, output Q); polyfill__dlxtn pf(.D, .GATE_N, .Q); endmodule
module sky130_fd_sc_hd__dlxtn_2(input VPWR, VGND, VPB, VNB, D, GATE_N, output Q); polyfill__dlxtn pf(.D, .GATE_N, .Q); endmodule
module sky130_fd_sc_hd__dlxtn_4(input VPWR, VGND, VPB, VNB, D, GATE_N, output Q); polyfill__dlxtn pf(.D, .GATE_N, .Q); endmodule
module sky130_fd_sc_hd__dlxtp_1(input VPWR, VGND, VPB, VNB, D, GATE, output Q); polyfill__dlxtp pf(.D, .GATE, .Q); endmodule
module sky130_fd_sc_hd__dlygate4sd1_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__dlygate4sd1 pf(.A, .X); endmodule
module sky130_fd_sc_hd__dlygate4sd2_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__dlygate4sd2 pf(.A, .X); endmodule
module sky130_fd_sc_hd__dlygate4sd3_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__dlygate4sd3 pf(.A, .X); endmodule
module sky130_fd_sc_hd__dlymetal6s2s_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__dlymetal6s2s pf(.A, .X); endmodule
module sky130_fd_sc_hd__dlymetal6s4s_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__dlymetal6s4s pf(.A, .X); endmodule
module sky130_fd_sc_hd__dlymetal6s6s_1(input VPWR, VGND, VPB, VNB, A, output X); polyfill__dlymetal6s6s pf(.A, .X); endmodule
module sky130_fd_sc_hd__ebufn_1(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__ebufn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__ebufn_2(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__ebufn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__ebufn_4(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__ebufn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__ebufn_8(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__ebufn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__edfxbp_1(input VPWR, VGND, VPB, VNB, CLK, D, DE, output Q, Q_N); polyfill__edfxbp pf(.CLK, .D, .DE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__edfxtp_1(input VPWR, VGND, VPB, VNB, CLK, D, DE, output Q); polyfill__edfxtp pf(.CLK, .D, .DE, .Q); endmodule
module sky130_fd_sc_hd__einvn_0(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__einvn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__einvn_1(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__einvn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__einvn_2(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__einvn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__einvn_4(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__einvn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__einvn_8(input VPWR, VGND, VPB, VNB, A, TE_B, output Z); polyfill__einvn pf(.A, .TE_B, .Z); endmodule
module sky130_fd_sc_hd__einvp_1(input VPWR, VGND, VPB, VNB, A, TE, output Z); polyfill__einvp pf(.A, .TE, .Z); endmodule
module sky130_fd_sc_hd__einvp_2(input VPWR, VGND, VPB, VNB, A, TE, output Z); polyfill__einvp pf(.A, .TE, .Z); endmodule
module sky130_fd_sc_hd__einvp_4(input VPWR, VGND, VPB, VNB, A, TE, output Z); polyfill__einvp pf(.A, .TE, .Z); endmodule
module sky130_fd_sc_hd__einvp_8(input VPWR, VGND, VPB, VNB, A, TE, output Z); polyfill__einvp pf(.A, .TE, .Z); endmodule
module sky130_fd_sc_hd__fa_1(input VPWR, VGND, VPB, VNB, A, B, CIN, output COUT, SUM); polyfill__fa pf(.A, .B, .CIN, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__fa_2(input VPWR, VGND, VPB, VNB, A, B, CIN, output COUT, SUM); polyfill__fa pf(.A, .B, .CIN, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__fa_4(input VPWR, VGND, VPB, VNB, A, B, CIN, output COUT, SUM); polyfill__fa pf(.A, .B, .CIN, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__fah_1(input VPWR, VGND, VPB, VNB, A, B, CI, output COUT, SUM); polyfill__fah pf(.A, .B, .CI, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__fahcin_1(input VPWR, VGND, VPB, VNB, A, B, CIN, output COUT, SUM); polyfill__fahcin pf(.A, .B, .CIN, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__fahcon_1(input VPWR, VGND, VPB, VNB, A, B, CI, output COUT_N, SUM); polyfill__fahcon pf(.A, .B, .CI, .COUT_N, .SUM); endmodule
module sky130_fd_sc_hd__fill_1(input VPWR, VGND, VPB, VNB); polyfill__fill pf(); endmodule
module sky130_fd_sc_hd__fill_2(input VPWR, VGND, VPB, VNB); polyfill__fill pf(); endmodule
module sky130_fd_sc_hd__fill_4(input VPWR, VGND, VPB, VNB); polyfill__fill pf(); endmodule
module sky130_fd_sc_hd__fill_8(input VPWR, VGND, VPB, VNB); polyfill__fill pf(); endmodule
module sky130_fd_sc_hd__ha_1(input VPWR, VGND, VPB, VNB, A, B, output COUT, SUM); polyfill__ha pf(.A, .B, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__ha_2(input VPWR, VGND, VPB, VNB, A, B, output COUT, SUM); polyfill__ha pf(.A, .B, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__ha_4(input VPWR, VGND, VPB, VNB, A, B, output COUT, SUM); polyfill__ha pf(.A, .B, .COUT, .SUM); endmodule
module sky130_fd_sc_hd__inv_1(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__inv_2(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__inv_4(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__inv_6(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__inv_8(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__inv_12(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__inv_16(input VPWR, VGND, VPB, VNB, A, output Y); polyfill__inv pf(.A, .Y); endmodule
module sky130_fd_sc_hd__lpflow_inputiso0n_1(input VPWR, VGND, VPB, VNB, A, SLEEP_B, output X); polyfill__lpflow_inputiso0n pf(.A, .SLEEP_B, .X); endmodule
module sky130_fd_sc_hd__lpflow_inputiso0p_1(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_inputiso0p pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__lpflow_inputiso1n_1(input VPWR, VGND, VPB, VNB, A, SLEEP_B, output X); polyfill__lpflow_inputiso1n pf(.A, .SLEEP_B, .X); endmodule
module sky130_fd_sc_hd__lpflow_inputiso1p_1(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_inputiso1p pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__lpflow_inputisolatch_1(input VPWR, VGND, VPB, VNB, D, SLEEP_B, output Q); polyfill__lpflow_inputisolatch pf(.D, .SLEEP_B, .Q); endmodule
module sky130_fd_sc_hd__lpflow_isobufsrc_1(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_isobufsrc pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__lpflow_isobufsrc_2(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_isobufsrc pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__lpflow_isobufsrc_4(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_isobufsrc pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__lpflow_isobufsrc_8(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_isobufsrc pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__lpflow_isobufsrc_16(input VPWR, VGND, VPB, VNB, A, SLEEP, output X); polyfill__lpflow_isobufsrc pf(.A, .SLEEP, .X); endmodule
module sky130_fd_sc_hd__maj3_1(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__maj3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__maj3_2(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__maj3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__maj3_4(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__maj3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__mux2_1(input VPWR, VGND, VPB, VNB, A0, A1, S, output X); polyfill__mux2 pf(.A0, .A1, .S, .X); endmodule
module sky130_fd_sc_hd__mux2_2(input VPWR, VGND, VPB, VNB, A0, A1, S, output X); polyfill__mux2 pf(.A0, .A1, .S, .X); endmodule
module sky130_fd_sc_hd__mux2_4(input VPWR, VGND, VPB, VNB, A0, A1, S, output X); polyfill__mux2 pf(.A0, .A1, .S, .X); endmodule
module sky130_fd_sc_hd__mux2_8(input VPWR, VGND, VPB, VNB, A0, A1, S, output X); polyfill__mux2 pf(.A0, .A1, .S, .X); endmodule
module sky130_fd_sc_hd__mux2i_1(input VPWR, VGND, VPB, VNB, A0, A1, S, output Y); polyfill__mux2i pf(.A0, .A1, .S, .Y); endmodule
module sky130_fd_sc_hd__mux2i_2(input VPWR, VGND, VPB, VNB, A0, A1, S, output Y); polyfill__mux2i pf(.A0, .A1, .S, .Y); endmodule
module sky130_fd_sc_hd__mux2i_4(input VPWR, VGND, VPB, VNB, A0, A1, S, output Y); polyfill__mux2i pf(.A0, .A1, .S, .Y); endmodule
module sky130_fd_sc_hd__mux4_1(input VPWR, VGND, VPB, VNB, A0, A1, A2, A3, S0, S1, output X); polyfill__mux4 pf(.A0, .A1, .A2, .A3, .S0, .S1, .X); endmodule
module sky130_fd_sc_hd__mux4_2(input VPWR, VGND, VPB, VNB, A0, A1, A2, A3, S0, S1, output X); polyfill__mux4 pf(.A0, .A1, .A2, .A3, .S0, .S1, .X); endmodule
module sky130_fd_sc_hd__mux4_4(input VPWR, VGND, VPB, VNB, A0, A1, A2, A3, S0, S1, output X); polyfill__mux4 pf(.A0, .A1, .A2, .A3, .S0, .S1, .X); endmodule
module sky130_fd_sc_hd__nand2_1(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nand2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nand2_2(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nand2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nand2_4(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nand2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nand2_8(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nand2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nand2b_1(input VPWR, VGND, VPB, VNB, A_N, B, output Y); polyfill__nand2b pf(.A_N, .B, .Y); endmodule
module sky130_fd_sc_hd__nand2b_2(input VPWR, VGND, VPB, VNB, A_N, B, output Y); polyfill__nand2b pf(.A_N, .B, .Y); endmodule
module sky130_fd_sc_hd__nand2b_4(input VPWR, VGND, VPB, VNB, A_N, B, output Y); polyfill__nand2b pf(.A_N, .B, .Y); endmodule
module sky130_fd_sc_hd__nand3_1(input VPWR, VGND, VPB, VNB, A, B, C, output Y); polyfill__nand3 pf(.A, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nand3_2(input VPWR, VGND, VPB, VNB, A, B, C, output Y); polyfill__nand3 pf(.A, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nand3_4(input VPWR, VGND, VPB, VNB, A, B, C, output Y); polyfill__nand3 pf(.A, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nand3b_1(input VPWR, VGND, VPB, VNB, A_N, B, C, output Y); polyfill__nand3b pf(.A_N, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nand3b_2(input VPWR, VGND, VPB, VNB, A_N, B, C, output Y); polyfill__nand3b pf(.A_N, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nand3b_4(input VPWR, VGND, VPB, VNB, A_N, B, C, output Y); polyfill__nand3b pf(.A_N, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nand4_1(input VPWR, VGND, VPB, VNB, A, B, C, D, output Y); polyfill__nand4 pf(.A, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4_2(input VPWR, VGND, VPB, VNB, A, B, C, D, output Y); polyfill__nand4 pf(.A, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4_4(input VPWR, VGND, VPB, VNB, A, B, C, D, output Y); polyfill__nand4 pf(.A, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4b_1(input VPWR, VGND, VPB, VNB, A_N, B, C, D, output Y); polyfill__nand4b pf(.A_N, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4b_2(input VPWR, VGND, VPB, VNB, A_N, B, C, D, output Y); polyfill__nand4b pf(.A_N, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4b_4(input VPWR, VGND, VPB, VNB, A_N, B, C, D, output Y); polyfill__nand4b pf(.A_N, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4bb_1(input VPWR, VGND, VPB, VNB, A_N, B_N, C, D, output Y); polyfill__nand4bb pf(.A_N, .B_N, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4bb_2(input VPWR, VGND, VPB, VNB, A_N, B_N, C, D, output Y); polyfill__nand4bb pf(.A_N, .B_N, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nand4bb_4(input VPWR, VGND, VPB, VNB, A_N, B_N, C, D, output Y); polyfill__nand4bb pf(.A_N, .B_N, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nor2_1(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nor2_2(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nor2_4(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nor2_8(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__nor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__nor2b_1(input VPWR, VGND, VPB, VNB, A, B_N, output Y); polyfill__nor2b pf(.A, .B_N, .Y); endmodule
module sky130_fd_sc_hd__nor2b_2(input VPWR, VGND, VPB, VNB, A, B_N, output Y); polyfill__nor2b pf(.A, .B_N, .Y); endmodule
module sky130_fd_sc_hd__nor2b_4(input VPWR, VGND, VPB, VNB, A, B_N, output Y); polyfill__nor2b pf(.A, .B_N, .Y); endmodule
module sky130_fd_sc_hd__nor3_1(input VPWR, VGND, VPB, VNB, A, B, C, output Y); polyfill__nor3 pf(.A, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nor3_2(input VPWR, VGND, VPB, VNB, A, B, C, output Y); polyfill__nor3 pf(.A, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nor3_4(input VPWR, VGND, VPB, VNB, A, B, C, output Y); polyfill__nor3 pf(.A, .B, .C, .Y); endmodule
module sky130_fd_sc_hd__nor3b_1(input VPWR, VGND, VPB, VNB, A, B, C_N, output Y); polyfill__nor3b pf(.A, .B, .C_N, .Y); endmodule
module sky130_fd_sc_hd__nor3b_2(input VPWR, VGND, VPB, VNB, A, B, C_N, output Y); polyfill__nor3b pf(.A, .B, .C_N, .Y); endmodule
module sky130_fd_sc_hd__nor3b_4(input VPWR, VGND, VPB, VNB, A, B, C_N, output Y); polyfill__nor3b pf(.A, .B, .C_N, .Y); endmodule
module sky130_fd_sc_hd__nor4_1(input VPWR, VGND, VPB, VNB, A, B, C, D, output Y); polyfill__nor4 pf(.A, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nor4_2(input VPWR, VGND, VPB, VNB, A, B, C, D, output Y); polyfill__nor4 pf(.A, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nor4_4(input VPWR, VGND, VPB, VNB, A, B, C, D, output Y); polyfill__nor4 pf(.A, .B, .C, .D, .Y); endmodule
module sky130_fd_sc_hd__nor4b_1(input VPWR, VGND, VPB, VNB, A, B, C, D_N, output Y); polyfill__nor4b pf(.A, .B, .C, .D_N, .Y); endmodule
module sky130_fd_sc_hd__nor4b_2(input VPWR, VGND, VPB, VNB, A, B, C, D_N, output Y); polyfill__nor4b pf(.A, .B, .C, .D_N, .Y); endmodule
module sky130_fd_sc_hd__nor4b_4(input VPWR, VGND, VPB, VNB, A, B, C, D_N, output Y); polyfill__nor4b pf(.A, .B, .C, .D_N, .Y); endmodule
module sky130_fd_sc_hd__nor4bb_1(input VPWR, VGND, VPB, VNB, A, B, C_N, D_N, output Y); polyfill__nor4bb pf(.A, .B, .C_N, .D_N, .Y); endmodule
module sky130_fd_sc_hd__nor4bb_2(input VPWR, VGND, VPB, VNB, A, B, C_N, D_N, output Y); polyfill__nor4bb pf(.A, .B, .C_N, .D_N, .Y); endmodule
module sky130_fd_sc_hd__nor4bb_4(input VPWR, VGND, VPB, VNB, A, B, C_N, D_N, output Y); polyfill__nor4bb pf(.A, .B, .C_N, .D_N, .Y); endmodule
module sky130_fd_sc_hd__o2111a_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output X); polyfill__o2111a pf(.A1, .A2, .B1, .C1, .D1, .X); endmodule
module sky130_fd_sc_hd__o2111a_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output X); polyfill__o2111a pf(.A1, .A2, .B1, .C1, .D1, .X); endmodule
module sky130_fd_sc_hd__o2111a_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output X); polyfill__o2111a pf(.A1, .A2, .B1, .C1, .D1, .X); endmodule
module sky130_fd_sc_hd__o2111ai_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__o2111ai pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__o2111ai_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__o2111ai pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__o2111ai_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, D1, output Y); polyfill__o2111ai pf(.A1, .A2, .B1, .C1, .D1, .Y); endmodule
module sky130_fd_sc_hd__o211a_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output X); polyfill__o211a pf(.A1, .A2, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__o211a_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output X); polyfill__o211a pf(.A1, .A2, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__o211a_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output X); polyfill__o211a pf(.A1, .A2, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__o211ai_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output Y); polyfill__o211ai pf(.A1, .A2, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o211ai_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output Y); polyfill__o211ai pf(.A1, .A2, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o211ai_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, C1, output Y); polyfill__o211ai pf(.A1, .A2, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o21a_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, output X); polyfill__o21a pf(.A1, .A2, .B1, .X); endmodule
module sky130_fd_sc_hd__o21a_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, output X); polyfill__o21a pf(.A1, .A2, .B1, .X); endmodule
module sky130_fd_sc_hd__o21a_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, output X); polyfill__o21a pf(.A1, .A2, .B1, .X); endmodule
module sky130_fd_sc_hd__o21ai_0(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__o21ai pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__o21ai_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__o21ai pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__o21ai_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__o21ai pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__o21ai_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, output Y); polyfill__o21ai pf(.A1, .A2, .B1, .Y); endmodule
module sky130_fd_sc_hd__o21ba_1(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output X); polyfill__o21ba pf(.A1, .A2, .B1_N, .X); endmodule
module sky130_fd_sc_hd__o21ba_2(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output X); polyfill__o21ba pf(.A1, .A2, .B1_N, .X); endmodule
module sky130_fd_sc_hd__o21ba_4(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output X); polyfill__o21ba pf(.A1, .A2, .B1_N, .X); endmodule
module sky130_fd_sc_hd__o21bai_1(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__o21bai pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__o21bai_2(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__o21bai pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__o21bai_4(input VPWR, VGND, VPB, VNB, A1, A2, B1_N, output Y); polyfill__o21bai pf(.A1, .A2, .B1_N, .Y); endmodule
module sky130_fd_sc_hd__o221a_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output X); polyfill__o221a pf(.A1, .A2, .B1, .B2, .C1, .X); endmodule
module sky130_fd_sc_hd__o221a_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output X); polyfill__o221a pf(.A1, .A2, .B1, .B2, .C1, .X); endmodule
module sky130_fd_sc_hd__o221a_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output X); polyfill__o221a pf(.A1, .A2, .B1, .B2, .C1, .X); endmodule
module sky130_fd_sc_hd__o221ai_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output Y); polyfill__o221ai pf(.A1, .A2, .B1, .B2, .C1, .Y); endmodule
module sky130_fd_sc_hd__o221ai_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output Y); polyfill__o221ai pf(.A1, .A2, .B1, .B2, .C1, .Y); endmodule
module sky130_fd_sc_hd__o221ai_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, C1, output Y); polyfill__o221ai pf(.A1, .A2, .B1, .B2, .C1, .Y); endmodule
module sky130_fd_sc_hd__o22a_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output X); polyfill__o22a pf(.A1, .A2, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o22a_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output X); polyfill__o22a pf(.A1, .A2, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o22a_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output X); polyfill__o22a pf(.A1, .A2, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o22ai_1(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output Y); polyfill__o22ai pf(.A1, .A2, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o22ai_2(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output Y); polyfill__o22ai pf(.A1, .A2, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o22ai_4(input VPWR, VGND, VPB, VNB, A1, A2, B1, B2, output Y); polyfill__o22ai pf(.A1, .A2, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o2bb2a_1(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output X); polyfill__o2bb2a pf(.A1_N, .A2_N, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o2bb2a_2(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output X); polyfill__o2bb2a pf(.A1_N, .A2_N, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o2bb2a_4(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output X); polyfill__o2bb2a pf(.A1_N, .A2_N, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o2bb2ai_1(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output Y); polyfill__o2bb2ai pf(.A1_N, .A2_N, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o2bb2ai_2(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output Y); polyfill__o2bb2ai pf(.A1_N, .A2_N, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o2bb2ai_4(input VPWR, VGND, VPB, VNB, A1_N, A2_N, B1, B2, output Y); polyfill__o2bb2ai pf(.A1_N, .A2_N, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o311a_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output X); polyfill__o311a pf(.A1, .A2, .A3, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__o311a_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output X); polyfill__o311a pf(.A1, .A2, .A3, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__o311a_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output X); polyfill__o311a pf(.A1, .A2, .A3, .B1, .C1, .X); endmodule
module sky130_fd_sc_hd__o311ai_0(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__o311ai pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o311ai_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__o311ai pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o311ai_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__o311ai pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o311ai_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, C1, output Y); polyfill__o311ai pf(.A1, .A2, .A3, .B1, .C1, .Y); endmodule
module sky130_fd_sc_hd__o31a_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output X); polyfill__o31a pf(.A1, .A2, .A3, .B1, .X); endmodule
module sky130_fd_sc_hd__o31a_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output X); polyfill__o31a pf(.A1, .A2, .A3, .B1, .X); endmodule
module sky130_fd_sc_hd__o31a_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output X); polyfill__o31a pf(.A1, .A2, .A3, .B1, .X); endmodule
module sky130_fd_sc_hd__o31ai_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output Y); polyfill__o31ai pf(.A1, .A2, .A3, .B1, .Y); endmodule
module sky130_fd_sc_hd__o31ai_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output Y); polyfill__o31ai pf(.A1, .A2, .A3, .B1, .Y); endmodule
module sky130_fd_sc_hd__o31ai_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, output Y); polyfill__o31ai pf(.A1, .A2, .A3, .B1, .Y); endmodule
module sky130_fd_sc_hd__o32a_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output X); polyfill__o32a pf(.A1, .A2, .A3, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o32a_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output X); polyfill__o32a pf(.A1, .A2, .A3, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o32a_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output X); polyfill__o32a pf(.A1, .A2, .A3, .B1, .B2, .X); endmodule
module sky130_fd_sc_hd__o32ai_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output Y); polyfill__o32ai pf(.A1, .A2, .A3, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o32ai_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output Y); polyfill__o32ai pf(.A1, .A2, .A3, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o32ai_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, B1, B2, output Y); polyfill__o32ai pf(.A1, .A2, .A3, .B1, .B2, .Y); endmodule
module sky130_fd_sc_hd__o41a_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output X); polyfill__o41a pf(.A1, .A2, .A3, .A4, .B1, .X); endmodule
module sky130_fd_sc_hd__o41a_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output X); polyfill__o41a pf(.A1, .A2, .A3, .A4, .B1, .X); endmodule
module sky130_fd_sc_hd__o41a_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output X); polyfill__o41a pf(.A1, .A2, .A3, .A4, .B1, .X); endmodule
module sky130_fd_sc_hd__o41ai_1(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output Y); polyfill__o41ai pf(.A1, .A2, .A3, .A4, .B1, .Y); endmodule
module sky130_fd_sc_hd__o41ai_2(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output Y); polyfill__o41ai pf(.A1, .A2, .A3, .A4, .B1, .Y); endmodule
module sky130_fd_sc_hd__o41ai_4(input VPWR, VGND, VPB, VNB, A1, A2, A3, A4, B1, output Y); polyfill__o41ai pf(.A1, .A2, .A3, .A4, .B1, .Y); endmodule
module sky130_fd_sc_hd__or2_0(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__or2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__or2_1(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__or2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__or2_2(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__or2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__or2_4(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__or2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__or2b_1(input VPWR, VGND, VPB, VNB, A, B_N, output X); polyfill__or2b pf(.A, .B_N, .X); endmodule
module sky130_fd_sc_hd__or2b_2(input VPWR, VGND, VPB, VNB, A, B_N, output X); polyfill__or2b pf(.A, .B_N, .X); endmodule
module sky130_fd_sc_hd__or2b_4(input VPWR, VGND, VPB, VNB, A, B_N, output X); polyfill__or2b pf(.A, .B_N, .X); endmodule
module sky130_fd_sc_hd__or3_1(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__or3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__or3_2(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__or3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__or3_4(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__or3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__or3b_1(input VPWR, VGND, VPB, VNB, A, B, C_N, output X); polyfill__or3b pf(.A, .B, .C_N, .X); endmodule
module sky130_fd_sc_hd__or3b_2(input VPWR, VGND, VPB, VNB, A, B, C_N, output X); polyfill__or3b pf(.A, .B, .C_N, .X); endmodule
module sky130_fd_sc_hd__or3b_4(input VPWR, VGND, VPB, VNB, A, B, C_N, output X); polyfill__or3b pf(.A, .B, .C_N, .X); endmodule
module sky130_fd_sc_hd__or4_1(input VPWR, VGND, VPB, VNB, A, B, C, D, output X); polyfill__or4 pf(.A, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__or4_2(input VPWR, VGND, VPB, VNB, A, B, C, D, output X); polyfill__or4 pf(.A, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__or4_4(input VPWR, VGND, VPB, VNB, A, B, C, D, output X); polyfill__or4 pf(.A, .B, .C, .D, .X); endmodule
module sky130_fd_sc_hd__or4b_1(input VPWR, VGND, VPB, VNB, A, B, C, D_N, output X); polyfill__or4b pf(.A, .B, .C, .D_N, .X); endmodule
module sky130_fd_sc_hd__or4b_2(input VPWR, VGND, VPB, VNB, A, B, C, D_N, output X); polyfill__or4b pf(.A, .B, .C, .D_N, .X); endmodule
module sky130_fd_sc_hd__or4b_4(input VPWR, VGND, VPB, VNB, A, B, C, D_N, output X); polyfill__or4b pf(.A, .B, .C, .D_N, .X); endmodule
module sky130_fd_sc_hd__or4bb_1(input VPWR, VGND, VPB, VNB, A, B, C_N, D_N, output X); polyfill__or4bb pf(.A, .B, .C_N, .D_N, .X); endmodule
module sky130_fd_sc_hd__or4bb_2(input VPWR, VGND, VPB, VNB, A, B, C_N, D_N, output X); polyfill__or4bb pf(.A, .B, .C_N, .D_N, .X); endmodule
module sky130_fd_sc_hd__or4bb_4(input VPWR, VGND, VPB, VNB, A, B, C_N, D_N, output X); polyfill__or4bb pf(.A, .B, .C_N, .D_N, .X); endmodule
module sky130_fd_sc_hd__sdfbbn_1(input VPWR, VGND, VPB, VNB, CLK_N, D, RESET_B, SET_B, SCD, SCE, output Q, Q_N); polyfill__sdfbbn pf(.CLK_N, .D, .RESET_B, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfbbn_2(input VPWR, VGND, VPB, VNB, CLK_N, D, RESET_B, SET_B, SCD, SCE, output Q, Q_N); polyfill__sdfbbn pf(.CLK_N, .D, .RESET_B, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfbbp_1(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SET_B, SCD, SCE, output Q, Q_N); polyfill__sdfbbp pf(.CLK, .D, .RESET_B, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfrbp_1(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SCD, SCE, output Q, Q_N); polyfill__sdfrbp pf(.CLK, .D, .RESET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfrbp_2(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SCD, SCE, output Q, Q_N); polyfill__sdfrbp pf(.CLK, .D, .RESET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfrtn_1(input VPWR, VGND, VPB, VNB, CLK_N, D, RESET_B, SCD, SCE, output Q); polyfill__sdfrtn pf(.CLK_N, .D, .RESET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfrtp_1(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SCD, SCE, output Q); polyfill__sdfrtp pf(.CLK, .D, .RESET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfrtp_2(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SCD, SCE, output Q); polyfill__sdfrtp pf(.CLK, .D, .RESET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfrtp_4(input VPWR, VGND, VPB, VNB, CLK, D, RESET_B, SCD, SCE, output Q); polyfill__sdfrtp pf(.CLK, .D, .RESET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfsbp_1(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, SCD, SCE, output Q, Q_N); polyfill__sdfsbp pf(.CLK, .D, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfsbp_2(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, SCD, SCE, output Q, Q_N); polyfill__sdfsbp pf(.CLK, .D, .SET_B, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfstp_1(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, SCD, SCE, output Q); polyfill__sdfstp pf(.CLK, .D, .SET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfstp_2(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, SCD, SCE, output Q); polyfill__sdfstp pf(.CLK, .D, .SET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfstp_4(input VPWR, VGND, VPB, VNB, CLK, D, SET_B, SCD, SCE, output Q); polyfill__sdfstp pf(.CLK, .D, .SET_B, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfxbp_1(input VPWR, VGND, VPB, VNB, CLK, D, SCD, SCE, output Q, Q_N); polyfill__sdfxbp pf(.CLK, .D, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfxbp_2(input VPWR, VGND, VPB, VNB, CLK, D, SCD, SCE, output Q, Q_N); polyfill__sdfxbp pf(.CLK, .D, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sdfxtp_1(input VPWR, VGND, VPB, VNB, CLK, D, SCD, SCE, output Q); polyfill__sdfxtp pf(.CLK, .D, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfxtp_2(input VPWR, VGND, VPB, VNB, CLK, D, SCD, SCE, output Q); polyfill__sdfxtp pf(.CLK, .D, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdfxtp_4(input VPWR, VGND, VPB, VNB, CLK, D, SCD, SCE, output Q); polyfill__sdfxtp pf(.CLK, .D, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sdlclkp_1(input VPWR, VGND, VPB, VNB, CLK, GATE, SCE, output GCLK); polyfill__sdlclkp pf(.CLK, .GATE, .SCE, .GCLK); endmodule
module sky130_fd_sc_hd__sdlclkp_2(input VPWR, VGND, VPB, VNB, CLK, GATE, SCE, output GCLK); polyfill__sdlclkp pf(.CLK, .GATE, .SCE, .GCLK); endmodule
module sky130_fd_sc_hd__sdlclkp_4(input VPWR, VGND, VPB, VNB, CLK, GATE, SCE, output GCLK); polyfill__sdlclkp pf(.CLK, .GATE, .SCE, .GCLK); endmodule
module sky130_fd_sc_hd__sedfxbp_1(input VPWR, VGND, VPB, VNB, CLK, D, DE, SCD, SCE, output Q, Q_N); polyfill__sedfxbp pf(.CLK, .D, .DE, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sedfxbp_2(input VPWR, VGND, VPB, VNB, CLK, D, DE, SCD, SCE, output Q, Q_N); polyfill__sedfxbp pf(.CLK, .D, .DE, .SCD, .SCE, .Q, .Q_N); endmodule
module sky130_fd_sc_hd__sedfxtp_1(input VPWR, VGND, VPB, VNB, CLK, D, DE, SCD, SCE, output Q); polyfill__sedfxtp pf(.CLK, .D, .DE, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sedfxtp_2(input VPWR, VGND, VPB, VNB, CLK, D, DE, SCD, SCE, output Q); polyfill__sedfxtp pf(.CLK, .D, .DE, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__sedfxtp_4(input VPWR, VGND, VPB, VNB, CLK, D, DE, SCD, SCE, output Q); polyfill__sedfxtp pf(.CLK, .D, .DE, .SCD, .SCE, .Q); endmodule
module sky130_fd_sc_hd__tap_1(input VPWR, VGND, VPB, VNB); polyfill__tap pf(); endmodule
module sky130_fd_sc_hd__tap_2(input VPWR, VGND, VPB, VNB); polyfill__tap pf(); endmodule
module sky130_fd_sc_hd__tapvgnd_1(input VPWR, VGND, VPB, VNB); polyfill__tapvgnd pf(); endmodule
module sky130_fd_sc_hd__tapvgnd2_1(input VPWR, VGND, VPB, VNB); polyfill__tapvgnd2 pf(); endmodule
module sky130_fd_sc_hd__tapvpwrvgnd_1(input VPWR, VGND, VPB, VNB); polyfill__tapvpwrvgnd pf(); endmodule
module sky130_fd_sc_hd__xnor2_1(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__xnor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__xnor2_2(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__xnor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__xnor2_4(input VPWR, VGND, VPB, VNB, A, B, output Y); polyfill__xnor2 pf(.A, .B, .Y); endmodule
module sky130_fd_sc_hd__xnor3_1(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__xnor3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__xnor3_2(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__xnor3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__xnor3_4(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__xnor3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__xor2_1(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__xor2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__xor2_2(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__xor2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__xor2_4(input VPWR, VGND, VPB, VNB, A, B, output X); polyfill__xor2 pf(.A, .B, .X); endmodule
module sky130_fd_sc_hd__xor3_1(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__xor3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__xor3_2(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__xor3 pf(.A, .B, .C, .X); endmodule
module sky130_fd_sc_hd__xor3_4(input VPWR, VGND, VPB, VNB, A, B, C, output X); polyfill__xor3 pf(.A, .B, .C, .X); endmodule

