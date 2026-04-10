module uart_tx_top(
  input clk,
  input rst,
  input baud_pulse,
  input parity_en,
  input tx_fifo_empty,
  input stop_bit_sel,
  input sticky_parity,
  input even_parity_sel,
  input set_break,
  input [7:0] data_in,
  input [1:0] word_len_sel,
  output reg pop,
  output reg shift_reg_empty,
  output reg tx
);
  reg [7:0] shift_reg;
  reg tx_bit;
  reg data_parity;
  reg [2:0] bit_counter = 0; // no of data bits
  reg [4:0] baud_counter = 5'd15;
  reg parity_bit;
  reg [7:0] data_in_reg;

  // FSM: 00 Idle, 01 Start Bit, 10 Transfer, 11 Parity
  reg [1:0] state = 2'b00;
  always @(posedge clk or posedge rst)
  begin
    if (rst)
    begin
      state <= 2'b00;
      baud_counter <= 5'd15;
      bit_counter <= 0;
      shift_reg <= 8'bxxxxxxxx;
      pop <= 1'b0;
      shift_reg_empty <= 1'b0;
      tx_bit <= 1'b1;
    end
    else if (baud_pulse)
    begin
      case (state)
        2'b00:
        begin
          if (tx_fifo_empty == 1'b0)
          begin
            if (baud_counter != 0) // make sure stop bit from previous transmission is sent
            begin
              baud_counter <= baud_counter - 1;
              state <= 2'b00;
            end
            else
            begin
              data_in_reg <= data_in;
              baud_counter <= 5'd15;
              state <= 2'b01;
              bit_counter <= {1'b1, word_len_sel}; // 5,6,7,8 data bits
              pop <= 1'b1;
              shift_reg <= data_in;
              shift_reg_empty <= 1'b0;
              tx_bit <= 1'b0; // start bit
            end
          end
        end

        2'b01:
        begin
          case (word_len_sel)
            2'b00: data_parity <= ^data_in_reg[4:0];
            2'b01: data_parity <= ^data_in_reg[5:0];
            2'b10: data_parity <= ^data_in_reg[6:0];
            2'b11: data_parity <= ^data_in_reg[7:0];
          endcase

          if (baud_counter != 0) // make sure start bit is sent for 16 clocks
          begin
            baud_counter <= baud_counter - 1;
            state <= 2'b01;
          end
          else
          begin
            baud_counter <= 5'd15;
            state <= 2'b10;
            tx_bit <= shift_reg[0]; // first data bit
            shift_reg <= shift_reg >> 1;
            pop <= 1'b0; // clear pop after one clock
          end
        end

        2'b10:
        begin
          case ({sticky_parity, even_parity_sel})
            2'b00: parity_bit <= ~data_parity; // odd parity
            2'b01: parity_bit <= data_parity; // even parity
            2'b10: parity_bit <= 1'b1; // sticky parity 1
            2'b11: parity_bit <= 1'b0; // sticky parity 0
          endcase

          if (bit_counter != 0) begin
            if (baud_counter != 0) // make sure data bit is sent for 16 clocks
            begin
              baud_counter <= baud_counter - 1;
              state <= 2'b10;
            end
            else
            begin
              baud_counter <= 5'd15;
              bit_counter <= bit_counter - 1;
              tx_bit <= shift_reg[0];
              shift_reg <= shift_reg >> 1;
              state <= 2'b10;
            end
          end
          else // when all data bits are sent
          begin
            if (baud_counter != 0) // make sure last data bit is sent for 16 clocks
            begin
              baud_counter <= baud_counter - 1;
              state <= 2'b10;
            end
            else
            begin
              baud_counter <= 5'd15;
              shift_reg_empty <= 1'b1;
              if (parity_en == 1'b1)
              begin
                state <= 2'b11;
                baud_counter <= 5'd15;
                tx_bit <= parity_bit;
              end
              else // no parity, go to stop bit
              begin
                tx_bit <= 1'b1;
                baud_counter <= (stop_bit_sel == 1'b0) ? 5'd15 : (word_len_sel == 2'b00) ? 5'd23 : 5'd31; // 1 or 2 stop bits
                state <= 2'b00;
              end
            end
          end
        end

        2'b11:
        begin
          if (baud_counter != 0) // make sure parity bit is sent for 16 clocks
          begin
            baud_counter <= baud_counter - 1;
            state <= 2'b11;
          end
          else
          begin
            tx_bit <= 1'b1;
            baud_counter <= (stop_bit_sel == 1'b0) ? 5'd15 : (word_len_sel == 2'b00) ? 5'd17 : 5'd31; // 1 or 2 stop bits
            state <= 2'b00;
          end
        end
      endcase
    end
  end

  always @(posedge clk, posedge rst)
  begin
    if (rst)
      tx <= 1'b1;
    else
      tx <= tx_bit & ~set_break;
  end

endmodule