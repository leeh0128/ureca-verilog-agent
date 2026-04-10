`timescale 1ns / 1ps

/*
    Group Members: Nikita Eisenhauer and Warren Seto
    Lab Name: Adder Design
    Design Description: Verilog test fixture to test the 64-bit ripple adder
*/

module ripple_adder_64_test;

  // Inputs
  reg [63:0] A;
  reg [63:0] B;

  // Outputs
  wire [63:0] SUM;
  wire CARRY;

  // Instantiate two counter variables for the test loop
  integer count;
  integer count2;
  reg error_found; // to track status of error

  // Instantiate the Unit Under Test (UUT)
  ripple_adder_64 uut
  (
    .A(A),
    .B(B),
    .SUM(SUM),
    .CARRY(CARRY)
  );

  initial begin

    // $monitor("%d + %d = %d and carry %d", A, B, SUM, CARRY);

    // Iterate through all possible combination of 0-32
    count = 0;
    count2 = 0;

    A = 0;
    B = 0;
    error_found = 0;

    // Loops over the possible combinations for the inputs A and B
    for (count = 0; count <= 32; count = count + 1) begin
      {A} = count;

      for (count2 = 0; count2 <= 32; count2 = count2 + 1) begin
        {B} = count2;
        #1;
        // check if the RTL output match the expected math
        if ({CARRY, SUM} !== (A+B)) begin
            $display("[ERROR] %d + %d = %d (Carry %d)", A, B, SUM, CARRY);
            error_found = 1;
      end
    end
  end

  // final check 
  if (error_found == 0) begin
    $display("TEST PASS");
  end else begin
    $display("TEST FAIL");
  end
  
  end 

  initial #4000 $finish; // The test will run for a total interval of 4000 nanoseconds
endmodule