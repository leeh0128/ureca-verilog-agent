`timescale 1ns / 1ps

module moore_ol_tb;

   reg         in;
   reg         clk;
   reg         reset;
   wire        out;
   
   // Golden Model Parameters (Moore Machine needs 5 states for 4 bits)
   parameter   S0 = 0, S1 = 1, S2 = 2, S3 = 3, S4 = 4;
   reg         new_out;
   reg   [2:0] ps, ns;

   // Automation Variables
   reg error_found;

   // Instantiation of the design under test
   moore_ol dut (
      .in    (in),
      .clk   (clk),
      .reset (reset),
      .out   (out)
   );
    
   // Clock Generation
   initial begin
      clk = 0;
      reset = 1;
      #20 reset = 0;
      forever #5 clk = ~clk;
   end
   
   // Test Logic
   initial begin
      // 1. Enable VCD (Required for Power Analysis)
      $dumpfile("waves.vcd");
      $dumpvars(0, moore_ol_tb);

      error_found = 0;
      
      // Wait for reset to finish
      wait(reset == 0);

      repeat(20) begin
         stimulus(); // call task
         
         // Compare DUT output vs Golden Model
         if (out == new_out) begin
            $display("Time %t: Input=%b Output=%b Expected=%b [OK]", $time, in, out, new_out);
            
            if (out == 1 && new_out == 1)
               $display("  -> Sequence 1101 Detected!");
         end else begin
            $display("Time %t: Input=%b Output=%b Expected=%b [FAIL]", $time, in, out, new_out);
            error_found = 1;
         end
      end

      // 2. Final Status Check (The Automation Contract)
      if (error_found == 0) begin
         $display("TEST PASS");
      end else begin
         $display("TEST FAIL");
      end

      $finish;
   end
   
   // Input Task
   task stimulus;
      begin
         in = $random;
         @(posedge clk);
         #1; // Critical: Small delay to allow logic to settle before checking
      end
   endtask

   // ==========================================
   // Golden Model (Reference Logic for Moore)
   // ==========================================

   always@(posedge clk or posedge reset) begin
      if(reset) ps <= S0;
      else      ps <= ns;
   end

   always@(ps or in) begin      
      // Moore Output Logic: Output depends ONLY on current state
      case(ps)
          S4: new_out = 1;
          default: new_out = 0;
      endcase

      // Next State Logic
      case(ps)    
         S0 : ns = in ? S1 : S0;
         S1 : ns = in ? S2 : S0;
         S2 : ns = in ? S2 : S3;
         S3 : ns = in ? S4 : S0;
         S4 : ns = in ? S2 : S0; // Overlapping behavior (1101101 -> two detections)
         default: ns = S0;
      endcase
   end
         
endmodule