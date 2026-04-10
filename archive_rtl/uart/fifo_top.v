module fifo_top(
  input clk,
  input rst,
  input fifo_en,
  input push_en,
  input pop_en,
  input [7:0] data_in,
  output [7:0] data_out,
  output empty,
  output full,
  output overrun,
  output underrun,
  input [3:0] thresh_level,
  output thresh_reached
);
  reg [7:0] mem [0:15];

  reg [3:0] wptr = 0;
  reg [3:0] rptr = 0;
  reg [4:0] count = 0;

  wire push, pop;
  reg overrun_t, underrun_t;
  reg thresh_t;

  assign empty = (count == 0);
  assign full = (count == 16);
  assign data_out = empty ? 8'bxxxxxxxx : mem[rptr];
  assign push = fifo_en & push_en & ~full;
  assign pop = fifo_en & pop_en & ~empty;
  assign overrun = overrun_t;
  assign underrun = underrun_t;
  assign thresh_reached = thresh_t;

  // Count Flag
  always @(posedge clk or posedge rst)
  begin
    if (rst)
      count <= 0;
    else if (push && !pop)
      count <= count + 1;
    else if (!push && pop)
      count <= count - 1;
  end

  // Write Pointer
  always @(posedge clk, posedge rst)
  begin
    if (rst)
    begin
      wptr <= 4'h0;
    end
    else if (push)
    begin
      wptr <= (wptr + 1) & 4'hF;
    end
  end

  // Read Pointer
  always @(posedge clk, posedge rst)
  begin
    if (rst)
    begin
      rptr <= 4'h0;
    end
    else if (pop)
    begin
      rptr <= (rptr + 1) & 4'hF;
    end
  end

  // Memory write
  always @(posedge clk)
  begin
    if (push)
      mem[wptr] <= data_in;
  end

  // Overrun & Underrun Flag
  always @(posedge clk, posedge rst)
  begin
    if (rst)
    begin
      underrun_t <= 1'b0;
      overrun_t <= 1'b0;
    end
    else begin
      overrun_t <= fifo_en & push_en & full;
      underrun_t <= fifo_en & pop_en & empty;
    end
  end

  // Threshold Flag
  always @(posedge clk, posedge rst)
  begin
    if (rst)
      thresh_t <= 1'b0;
    else if (push ^ pop)
      thresh_t <= (count >= thresh_level);
  end
endmodule