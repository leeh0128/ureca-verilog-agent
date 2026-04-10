`timescale 1ns / 1ps

module mealy_ol_tb;

   reg         in;
   reg         clk;
   reg         reset;
   wire        out;
   
   // Golden Model Parameters
   parameter   S0 = 0, S1 = 1, S2 = 2, S3 = 3;
   reg         new_out;
   reg   [1:0] ps, ns;

   // Automation Variables
   reg error_found;

   // Instantiation of the design under test
   mealy_ol dut (
      .in(in),
      .clk(clk),
      .reset(reset),
      .out(out)
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
      $dumpvars(0, mealy_ol_tb);

      error_found = 0;
      
      // Wait for reset to finish
      wait(reset == 0);

      repeat(20) begin
         stimulus(); // call task
         
         // Compare DUT output vs Golden Model
         if (out == new_out) begin
            // We use [OK] instead of "Pass" here to avoid confusing the Makefile regex
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
   // Golden Model (Reference Logic)
   // ==========================================

   always@(posedge clk or posedge reset) begin
      if(reset) ps <= S0;
      else      ps <= ns;
   end

   always@(ps or in) begin      
      case(ps)    
         S0 : begin 
            new_out = 0;
            ns = in ? S1 : S0;
         end
         S1 : begin 
            new_out = 0;
            ns = in ? S2 : S0;
         end
         S2 : begin 
            new_out = 0;
            ns = in ? S2 : S3;              
         end 
         S3 : begin 
            new_out = in ?  1 : 0;
            ns = in ? S1 : S0;
         end
         default: ns = S0;
      endcase
   end
         
endmodule