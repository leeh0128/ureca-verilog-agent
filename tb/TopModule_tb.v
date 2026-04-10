`timescale 1ns/1ps

module TopModule_tb;

    reg clk;
    reg reset;
    reg in_bit;
    wire detected;

    // Instantiate DUT
    TopModule dut (
        .clk(clk),
        .reset(reset),
        .in_bit(in_bit),
        .detected(detected)
    );

    // Clock generation: 10ns period
    initial clk = 0;
    always #5 clk = ~clk;

    // Dump waveforms
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, TopModule_tb);
    end

    // Helper task: drive one bit and check expected output
    integer errors;

    task drive_and_check;
        input d_in;
        input exp_detected;
        input integer cycle_num;
        begin
            in_bit = d_in;
            @(posedge clk); #1;
            if (detected !== exp_detected) begin
                $display("FAIL: cycle %0d, in_bit=%0b, detected=%0b, expected=%0b (time=%0t)",
                         cycle_num, d_in, detected, exp_detected, $time);
                errors = errors + 1;
            end
        end
    endtask

    integer cycle;

    initial begin
        errors = 0;
        in_bit = 0;
        cycle = 0;

        // TEST 1: Reset behavior
        reset = 1;
        @(posedge clk); #1;
        @(posedge clk); #1;
        if (detected !== 1'b0) begin
            $display("FAIL: detected should be 0 during reset");
            errors = errors + 1;
        end
        reset = 0;

        // TEST 2: Basic sequence "1011" → detected goes high
        //
        //   Cycle:  1    2    3    4    5
        //   in_bit: 1    0    1    1    0
        //   detect: 0    0    0    0    1
        //
        //   detected goes high one cycle AFTER the full "1011"
        //   is clocked in (Moore FSM: output depends on state,
        //   state updates on clock edge, so detected=1 appears
        //   on the cycle after the last '1' is sampled).
        cycle = 1;
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 1
        drive_and_check(0, 0, cycle); cycle = cycle + 1;  // seen: 10
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 101
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 1011 → enter detected state
        drive_and_check(0, 1, cycle); cycle = cycle + 1;  // output=1 (Moore: in detected state)

        // TEST 3: Reset mid-sequence clears state
        // Start a sequence
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 1 (after overlap from detected→10)
        drive_and_check(0, 0, cycle); cycle = cycle + 1;  // seen: 10

        // Reset
        reset = 1;
        in_bit = 0;
        @(posedge clk); #1;
        if (detected !== 1'b0) begin
            $display("FAIL: detected should be 0 after mid-sequence reset (time=%0t)", $time);
            errors = errors + 1;
        end
        reset = 0;
        cycle = cycle + 1;

        // After reset, need full "1011" again
        drive_and_check(1, 0, cycle); cycle = cycle + 1;
        drive_and_check(0, 0, cycle); cycle = cycle + 1;
        drive_and_check(1, 0, cycle); cycle = cycle + 1;
        drive_and_check(1, 0, cycle); cycle = cycle + 1;
        drive_and_check(0, 1, cycle); cycle = cycle + 1;  // detected!

        // TEST 4: Overlapping detection — "10111011"
        //   Input stream: 1 0 1 1 1 0 1 1
        //   The first "1011" is at positions 1-4.
        //   After detection, because of overlap, the "1" at
        //   position 4 starts a new potential match:
        //   positions 4-7 give "1011" again.
        //
        //   Expected detected pulses at cycle after pos 4 and
        //   cycle after pos 8.
        // Reset first
        reset = 1;
        @(posedge clk); #1;
        reset = 0;
        cycle = 100;  // renumber for clarity

        // First "1011"
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // 1
        drive_and_check(0, 0, cycle); cycle = cycle + 1;  // 10
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // 101
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // 1011 → enter detected
        drive_and_check(1, 1, cycle); cycle = cycle + 1;  // output=1, new input=1 → start overlap (seen: 1)

        // Continue into second "1011" (overlapping)
        drive_and_check(0, 0, cycle); cycle = cycle + 1;  // seen: 10
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 101
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 1011 → enter detected again
        drive_and_check(0, 1, cycle); cycle = cycle + 1;  // output=1, second detection!

        // TEST 5: No false positives — "1010100"
        reset = 1;
        @(posedge clk); #1;
        reset = 0;
        cycle = 200;

        drive_and_check(1, 0, cycle); cycle = cycle + 1;
        drive_and_check(0, 0, cycle); cycle = cycle + 1;
        drive_and_check(1, 0, cycle); cycle = cycle + 1;
        drive_and_check(0, 0, cycle); cycle = cycle + 1;
        drive_and_check(1, 0, cycle); cycle = cycle + 1;
        drive_and_check(0, 0, cycle); cycle = cycle + 1;
        drive_and_check(0, 0, cycle); cycle = cycle + 1;

        // TEST 6: All zeros — should never detect
        reset = 1;
        @(posedge clk); #1;
        reset = 0;
        cycle = 300;

        repeat (10) begin
            drive_and_check(0, 0, cycle);
            cycle = cycle + 1;
        end

        // TEST 7: All ones — should never detect (no '0' in pattern)
        reset = 1;
        @(posedge clk); #1;
        reset = 0;
        cycle = 400;

        repeat (10) begin
            drive_and_check(1, 0, cycle);
            cycle = cycle + 1;
        end

        // TEST 8: Back-to-back sequences "101101011"
        //   1 0 1 1 0 1 0 1 1
        //   First 1011 at pos 1-4, second 1011 at pos 6-9
        //   (non-overlapping, with gap)
        reset = 1;
        @(posedge clk); #1;
        reset = 0;
        cycle = 500;

        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // 1
        drive_and_check(0, 0, cycle); cycle = cycle + 1;  // 10
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // 101
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // 1011 → detected state
        drive_and_check(0, 1, cycle); cycle = cycle + 1;  // output=1, in=0 → seen: 10 (overlap from detected)
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 101
        drive_and_check(0, 0, cycle); cycle = cycle + 1;  // seen: 10 (broke sequence)
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 101
        drive_and_check(1, 0, cycle); cycle = cycle + 1;  // seen: 1011 → detected state
        drive_and_check(0, 1, cycle); cycle = cycle + 1;  // output=1, second detection

        // SUMMARY
        if (errors == 0)
            $display("PASS: All tests passed.");
        else
            $display("FAIL: %0d errors found.", errors);

        $finish;
    end

endmodule