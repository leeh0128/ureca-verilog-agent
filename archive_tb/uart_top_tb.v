`timescale 1us/1ns

module uart_top_tb;
  reg clk, rst, wr_i, rd_i;
  reg [2:0] addr_i;
  reg [7:0] din_i;

  wire tx;
  wire rx;
  wire [7:0] data_out;

  assign rx = (tx === 1'b0) ? 1'b0 : 1'b1;

  uart_top dut(clk, rst, wr_i, rd_i, rx, addr_i, din_i, tx, data_out);

  // VCD generation 
  initial begin
    $dumpfile("waves.vcd");
    $dumpvars(0, uart_top_tb);
  end

  initial
  begin
    rst = 0;
    clk = 0;
    wr_i = 0;
    rd_i = 0;
    addr_i = 0;
    din_i = 0;
    // rx = 1;
  end

  always #5 clk = ~clk;

  initial
  begin
    rst = 1'b1;
    repeat(5) @(posedge clk);
    rst = 0;

    // dlab = 1;
    @(negedge clk);
    wr_i   = 1;
    addr_i = 3'h3;
    din_i  = 8'b1000_0000;

    // Set Divisor = 2 (Extremely fast baud rate for simulation)
    @(negedge clk); addr_i = 3'h0; din_i = 8'b0000_0010; // LSB = 2
  
    @(negedge clk); addr_i = 3'h1; din_i = 8'b0000_0000; // MSB = 0

    // DLAB = 0, 8-bit words, 1 stop bit, no parity
    @(negedge clk); addr_i = 3'h3; din_i = 8'b0000_0011;

    // push 0xF4 into FIFO (thr, dlab = 0)
    @(negedge clk); addr_i = 3'h0; din_i = 8'hF4;

    @(negedge clk); wr_i = 0;

    // wait for the UART to transmit the frame and the receiver to decode it
    // #10000;

    begin : poll_lsr
      integer timeout;
      timeout = 0;
      rd_i = 1;
      addr_i = 3'h5;  // LSR address
      @(negedge clk);
      while (data_out[0] !== 1'b1 && timeout < 10000) begin
        @(negedge clk);
        timeout = timeout + 1;
      end
      rd_i = 0;
      if (timeout == 10000) begin
        $display("FAIL: Timeout - RX data never became ready");
        $finish;
      end
    end

    @(negedge clk);
    rd_i=1;
    addr_i=3'h0;

    @(negedge clk);
    @(negedge clk);

    if (data_out == 8'hF4) begin
      $display("PASS: Loopback successful. 0xF4 transmitted and received.");
    end else begin
      $display("FAIL: Expected 0xF4, but got 0x%h", data_out);
    end
    // safely drop the read signal
    rd_i=0;
    // small delay to ensure the VCD waveform captures the final state
    #10;
    $finish;
  end
endmodule

//   initial begin
//     @(negedge rst);
//     #400000;
//     $display("PASS: Simulation Finished Successfully");
//     $finish;
//   end