`timescale 1ns/1ps
// testbench for the 4x1 multiplexers
module mux4_tb;
    reg [3:0] d;
    reg [1:0] sel;
    wire y;

    // DUT instantiation
    mux4 dut(.d(d), .sel(sel), .y(y));

    // back-annotation for GLS
    `ifdef SDF_ANNOTATE
        initial begin
            $sdf_annotate("out/mux4.sdf", dut);
        end
    `endif

    integer i, j, errors;
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, mux4_tb);

        errors = 0;
        for (i=0; i<4; i=i+1) begin
            for (j=0; j<4; j=j+1) begin
                d = 4'b0000;
                d[i] = 1'b1; // only one bit high at a time
                sel = j[1:0];
                #1;
                if (y !== d[sel]) begin
                    $display("FAIL: d=%b sel=%b -> y=%b (exp %b)", d, sel, y, d[sel]);
                    errors = errors + 1;
                end
            end
        end
        $display("TEST %s", (errors==0) ? "PASS" : "FAIL");
        $finish;
    end

endmodule