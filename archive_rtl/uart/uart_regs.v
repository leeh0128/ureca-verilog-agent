module uart_regs(
  input clk,
  input rst,
  input wr_i,
  input rd_i,
  input rx_fifo_empty_i,
  input rx_overrun_err,
  input rx_parity_err,
  input rx_framing_err,
  input rx_break_int,
  input [2:0] addr_i,
  input [7:0] din_i,
  input [7:0] rx_fifo_data_in,
  output tx_fifo_push,
  output rx_fifo_pop,
  output baud_pulse_out,
  output tx_fifo_reset,
  output rx_fifo_reset,
  output [3:0] rx_fifo_threshold,
  output reg [7:0] data_out,

  output [7:0] fcr_out,
  output [7:0] lcr_out,
  output [7:0] lsr_out,
  output [7:0] scr_out,
  output [7:0] baud_div_lsb_out,
  output [7:0] baud_div_msb_out
);
  // FCR
  reg [1:0] fcr_rx_trigger_level;
  reg [1:0] fcr_reserved_bits;
  reg fcr_dma_enable;
  reg fcr_tx_reset;
  reg fcr_rx_reset;
  reg fcr_fifo_enable;

  // LCR
  reg lcr_divisor_latch_access;
  reg lcr_break_control;
  reg lcr_stick_parity;
  reg lcr_even_parity_select;
  reg lcr_parity_enable;
  reg lcr_stop_bits;
  reg [1:0] lcr_word_length_select;

  // LSR
  reg lsr_rx_fifo_error;
  reg lsr_transmitter_empty;
  reg lsr_transmitter_holding_empty;
  reg lsr_break_interrupt;
  reg lsr_framing_error;
  reg lsr_parity_error;
  reg lsr_overrun_error;
  reg lsr_data_ready;

  // SCR
  reg [7:0] scratch_reg;

  // Baud Rate Divider
  reg [7:0] baud_div_msb;
  reg [7:0] baud_div_lsb;

  // Baud Generation
  always @(posedge clk)
    if (wr_i && addr_i == 3'b000 && lcr_divisor_latch_access == 1'b1)
      baud_div_lsb <= din_i;

  always @(posedge clk)
    if (wr_i && addr_i == 3'b001 && lcr_divisor_latch_access == 1'b1)
      baud_div_msb <= din_i;

  reg baud_update;
  reg [15:0] baud_counter = 0;
  reg baud_pulse = 0;
  always @(posedge clk)
    baud_update <= wr_i & (lcr_divisor_latch_access == 1'b1) & ((addr_i == 3'b000) | (addr_i == 3'b001));

  always @(posedge clk, posedge rst)
    if (rst)
      baud_counter <= 16'h0;
    else if (baud_update || baud_counter == 16'h0000)
      baud_counter <= {baud_div_msb, baud_div_lsb};
    else
      baud_counter <= baud_counter - 1;

  always @(posedge clk)
    baud_pulse <= (|{baud_div_msb, baud_div_lsb}) & ~|baud_counter;

  assign baud_pulse_out = baud_pulse;

  // FCR Logic
  wire tx_fifo_write;
  assign tx_fifo_write = wr_i & (addr_i == 3'b000) & (lcr_divisor_latch_access == 1'b0);
  assign tx_fifo_push = tx_fifo_write;

  wire rx_fifo_read;
  assign rx_fifo_read = rd_i & (addr_i == 3'b000) & (lcr_divisor_latch_access == 1'b0);
  assign rx_fifo_pop = rx_fifo_read;

  reg [7:0] rx_data;
  always @(posedge clk)
    if (rx_fifo_pop)
      rx_data <= rx_fifo_data_in;

  always @(posedge clk, posedge rst)
    if (rst)
    begin
      fcr_rx_trigger_level <= 2'b00;
      fcr_reserved_bits <= 2'b00;
      fcr_dma_enable <= 1'b0;
      fcr_tx_reset <= 1'b0;
      fcr_rx_reset <= 1'b0;
      fcr_fifo_enable <= 1'b0;
    end
    else if (wr_i == 1'b1 && addr_i == 3'h2)
    begin
      fcr_rx_trigger_level <= din_i[7:6];
      fcr_dma_enable <= din_i[3];
      fcr_tx_reset <= din_i[2];
      fcr_rx_reset <= din_i[1];
      fcr_fifo_enable <= din_i[0];
    end
    else
    begin
      fcr_tx_reset <= 1'b0;
      fcr_rx_reset <= 1'b0;
    end

  assign tx_fifo_reset = fcr_tx_reset;
  assign rx_fifo_reset = fcr_rx_reset;

  reg [3:0] rx_fifo_threshold_count = 0;
  always @*
  begin
    if (fcr_fifo_enable == 1'b0)
      rx_fifo_threshold_count = 4'd0;
    else
      case (fcr_rx_trigger_level)
        2'b00: rx_fifo_threshold_count = 4'd1;
        2'b01: rx_fifo_threshold_count = 4'd4;
        2'b10: rx_fifo_threshold_count = 4'd8;
        2'b11: rx_fifo_threshold_count = 4'd14;
      endcase
  end

  assign rx_fifo_threshold = rx_fifo_threshold_count;

  // LCR Logic
  reg [7:0] lcr_reg_temp;
  always @(posedge clk, posedge rst)
    if (rst)
    begin
      lcr_divisor_latch_access <= 1'b0;
      lcr_break_control <= 1'b0;
      lcr_stick_parity <= 1'b0;
      lcr_even_parity_select <= 1'b0;
      lcr_parity_enable <= 1'b0;
      lcr_stop_bits <= 1'b0;
      lcr_word_length_select <= 2'b00;
    end
    else if (wr_i == 1'b1 && addr_i == 3'h3)
    begin
      lcr_divisor_latch_access <= din_i[7];
      lcr_break_control <= din_i[6];
      lcr_stick_parity <= din_i[5];
      lcr_even_parity_select <= din_i[4];
      lcr_parity_enable <= din_i[3];
      lcr_stop_bits <= din_i[2];
      lcr_word_length_select <= din_i[1:0];
    end

  wire lcr_read;
  assign lcr_read = ((rd_i == 1) && (addr_i == 3'h3));
  always @(posedge clk)
    if (lcr_read)
      lcr_reg_temp <= {lcr_divisor_latch_access, lcr_break_control, lcr_stick_parity, lcr_even_parity_select, lcr_parity_enable, lcr_stop_bits, lcr_word_length_select};

  // LSR Logic
  reg [7:0] lsr_reg_temp;
  always @(posedge clk, posedge rst)
    if (rst)
    begin
      lsr_rx_fifo_error <= 1'b0;
      lsr_transmitter_empty <= 1'b1;
      lsr_transmitter_holding_empty <= 1'b1;
      lsr_break_interrupt <= 1'b0;
      lsr_framing_error <= 1'b0;
      lsr_parity_error <= 1'b0;
      lsr_overrun_error <= 1'b0;
      lsr_data_ready <= 1'b0;
    end
    else
    begin
      lsr_data_ready <= ~rx_fifo_empty_i;
      lsr_overrun_error <= rx_overrun_err;
      lsr_parity_error <= rx_parity_err;
      lsr_framing_error <= rx_framing_err;
      lsr_break_interrupt <= rx_break_int;
    end

  reg [7:0] lsr_temp;
  wire lsr_read;
  assign lsr_read = (rd_i == 1) & (addr_i == 3'h5);
  always @(posedge clk)
    if (lsr_read)
      lsr_temp <= {lsr_rx_fifo_error, lsr_transmitter_empty, lsr_transmitter_holding_empty, lsr_break_interrupt, lsr_framing_error, lsr_parity_error, lsr_overrun_error, lsr_data_ready};

  // SCR Logic
  always @(posedge clk, posedge rst)
    if (rst)
      scratch_reg <= 8'h00;
    else if (wr_i == 1'b1 && addr_i == 3'h7)
      scratch_reg <= din_i;

  reg [7:0] scratch_reg_temp;
  wire scratch_reg_read;
  assign scratch_reg_read = (rd_i == 1) & (addr_i == 3'h7);
  always @(posedge clk)
    if (scratch_reg_read)
      scratch_reg_temp <= scratch_reg;

  always @(posedge clk)
    case (addr_i)
      0: data_out <= lcr_divisor_latch_access ? baud_div_lsb : rx_data;
      1: data_out <= lcr_divisor_latch_access ? baud_div_msb : 8'h00;
      2: data_out <= 8'h00;
      3: data_out <= lcr_reg_temp;
      4: data_out <= 8'h00;
      5: data_out <= lsr_temp;
      6: data_out <= 8'h00;
      7: data_out <= scratch_reg_temp;
    endcase

  assign fcr_out = {fcr_rx_trigger_level, fcr_reserved_bits, fcr_dma_enable, fcr_tx_reset, fcr_rx_reset, fcr_fifo_enable};
  assign lcr_out = {lcr_divisor_latch_access, lcr_break_control, lcr_stick_parity, lcr_even_parity_select, lcr_parity_enable, lcr_stop_bits, lcr_word_length_select};
  assign lsr_out = {lsr_rx_fifo_error, lsr_transmitter_empty, lsr_transmitter_holding_empty, lsr_break_interrupt, lsr_framing_error, lsr_parity_error, lsr_overrun_error, lsr_data_ready};
  assign scr_out = scratch_reg;
  assign baud_div_lsb_out = baud_div_lsb;
  assign baud_div_msb_out = baud_div_msb;
endmodule