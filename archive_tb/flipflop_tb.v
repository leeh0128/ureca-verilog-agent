`timescale 1ns/1ps

module flipflop_tb;
    reg clk;
    reg rst_n;
    reg d;
    wire q;

    // DUT instantiation
    flipflop dut(.clk(clk), .rst_n(rst_n), .d(d), .q(q));

    // Back-annotation for GLS
    `ifdef SDF_ANNOTATE
        initial begin
            $sdf_annotate("out/flipflop.sdf", dut);
        end
    `endif

    // Clock Generation (100MHz / 10ns period)
    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, flipflop_tb);

        // Reset Sequence
        rst_n = 0; d = 0;
        #12 rst_n = 1;

        // Test Data Toggles
        @(posedge clk); d <= 1;
        @(posedge clk); d <= 0;
        @(posedge clk); d <= 1;
        @(posedge clk); d <= 1;
        
        #20;
        $display("Sequential Test Finished");
        $finish;
    end

endmodule