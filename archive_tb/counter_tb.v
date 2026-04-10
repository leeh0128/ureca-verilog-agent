`timescale 1ns/1ps

module TopModule_tb;

    reg clk;
    reg reset;
    wire [3:0] out;

    // Instantiate DUT
    TopModule dut (
        .clk(clk),
        .reset(reset),
        .out(out)
    );

    // Clock generation: 10ns period
    initial clk = 0;
    always #5 clk = ~clk;

    // Dump waveforms
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, TopModule_tb);
    end

    // Test sequence
    integer errors;
    reg [3:0] expected;

    initial begin
        errors = 0;
        expected = 4'd0;

        // Apply reset
        reset = 1;
        @(posedge clk); #1;
        @(posedge clk); #1;

        // Check reset value
        if (out !== 4'd0) begin
            $display("FAIL: After reset, out=%0d, expected 0", out);
            errors = errors + 1;
        end

        // Release reset
        reset = 0;

        // Count from 0 to 15, verify each step
        repeat (20) begin
            @(posedge clk); #1;
            if (reset)
                expected = 4'd0;
            else
                expected = expected + 1;

            if (out !== expected) begin
                $display("FAIL: out=%0d, expected=%0d at time %0t", out, expected, $time);
                errors = errors + 1;
            end
        end

        // Test reset mid-count
        reset = 1;
        @(posedge clk); #1;
        expected = 4'd0;
        if (out !== 4'd0) begin
            $display("FAIL: Reset mid-count, out=%0d, expected 0", out);
            errors = errors + 1;
        end

        reset = 0;
        repeat (5) begin
            @(posedge clk); #1;
            expected = expected + 1;
            if (out !== expected) begin
                $display("FAIL: After re-release, out=%0d, expected=%0d", out, expected);
                errors = errors + 1;
            end
        end

        // Summary
        if (errors == 0)
            $display("PASS: All tests passed.");
        else
            $display("FAIL: %0d errors found.", errors);

        $finish;
    end

endmodule