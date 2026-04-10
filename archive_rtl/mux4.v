// 4x1 multiplexer (combinational, no clock)

module mux4 (
    input [3:0] d, // d[0]~d[3]
    input [1:0] sel, // selection lines
    output y
);

    assign y = (sel == 2'b00) ? d[0] :
                (sel == 2'b01) ? d[1] :
                (sel == 2'b10) ? d[2] :
                d[3];

endmodule