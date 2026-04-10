`timescale 1ns/1ps

module fsm_tb;

    // declare signals
    reg clk;
    reg rst_n;
    reg in;
    wire out;

    // instantiate the FSM (Unit Under Test)
    fsm dut (
        .clk(clk),
        .rst_n(rst_n),
        .in(in),
        .out(out)
    );

    // generate clock (10ns period -> 100 MHz)
    initial clk = 0;
    always #5 clk = ~clk;

    // test sequence
    initial begin
        // dump waves for Power Analysis and Debugging
        $dumpfile("waves.vcd"); // Make sure this matches your Makefile's expectation
        $dumpvars(0, fsm_tb);

        // initialize
        rst_n = 0; in = 0;
        #12 rst_n = 1; // Release reset a little after the first edge

        // test case: Detect "11"
        // sequence: 0 -> 1 -> 1 (Detect!) -> 0 -> 1
        
        @(posedge clk) in <= 0; // State: S0
        @(posedge clk) in <= 1; // State: S0 -> S1
        @(posedge clk) in <= 1; // State: S1 -> S2 (Output should go HIGH)
        @(posedge clk) in <= 0; // State: S2 -> S0 (Output should go LOW)
        @(posedge clk) in <= 1; // State: S0 -> S1
        
        #20;
        $finish;
    end

    // optional: Monitor output in terminal
    initial begin
        $monitor("Time=%0t | rst=%b in=%b state=%b out=%b", 
                 $time, rst_n, in, dut.state, out);
    end

endmodule