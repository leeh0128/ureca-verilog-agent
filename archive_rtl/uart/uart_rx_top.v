module uart_rx_top(
  input clk,
  input rst,
  input baud_pulse,
  input rx,
  input sticky_parity,
  input even_parity_sel,
  input parity_en,
  input [1:0] word_len_sel,
  output reg push,
  output reg parity_error,
  output reg framing_error,
  output reg break_interrupt,
  output reg [7:0] data_out
);

  // FSM: 000 Idle, 001 Start Bit, 010 Read, 011 Parity, 100 Stop Bit
  reg [2:0] state = 3'b000;

  reg rx_sync = 1'b1;
  wire rx_falling_edge;

  always @(posedge clk)
    rx_sync <= rx;

  assign rx_falling_edge = rx_sync;

  reg [2:0] bit_counter;
  reg [4:0] baud_counter = 0;
  reg parity_bit;

  always @(posedge clk or posedge rst)
  begin
    if (rst)
    begin
      state <= 3'b000;
      push <= 1'b0;
      parity_error <= 1'b0;
      framing_error <= 1'b0;
      break_interrupt <= 1'b0;
      bit_counter <= 3'h0;
    end
    else
    begin
      push <= 1'b0;

      if (baud_pulse)
      begin
        case (state)
          3'b000:
          begin
            if (!rx_falling_edge)
            begin
              state <= 3'b001;
              baud_counter <= 5'd15;
            end
            else
              state <= 3'b000;
          end

          3'b001:
          begin
            baud_counter <= baud_counter - 1;
            if (baud_counter == 5'd7)
            begin
              if (rx == 1'b1)
              begin
                state <= 3'b000;
                baud_counter <= 5'd15;
              end
              else
                state <= 3'b001;
            end
            else if (baud_counter == 0)
            begin
              state <= 3'b010;
              baud_counter <= 5'd15;
              bit_counter <= {1'b1, word_len_sel}; // 5,6,7,8 data bits
            end
          end

          3'b010:
          begin
            baud_counter <= baud_counter - 1;
            if (baud_counter == 5'd7)
            begin
              case (word_len_sel)
                2'b00: data_out <= {3'b000, rx, data_out[4:1]};
                2'b01: data_out <= {2'b00, rx, data_out[5:1]};
                2'b10: data_out <= {1'b0, rx, data_out[6:1]};
                2'b11: data_out <= {rx, data_out[7:1]};
              endcase
              state <= 3'b010;
            end
            else if (baud_counter == 0)
            begin
              if (bit_counter == 0)
              begin
                case ({sticky_parity, even_parity_sel})
                  2'b00: parity_bit <= ~^{rx, data_out}; // odd parity
                  2'b01: parity_bit <= ^{rx, data_out}; // even parity
                  2'b10: parity_bit <= ~rx; // sticky parity 1
                  2'b11: parity_bit <= rx; // sticky parity 0
                endcase

                if (parity_en == 1'b1)
                begin
                  state <= 3'b011;
                  baud_counter <= 5'd15;
                end
                else
                begin
                  state <= 3'b100;
                  baud_counter <= 5'd15;
                end
              end
              else
              begin
                bit_counter <= bit_counter - 1;
                state  <= 3'b010;
                baud_counter  <= 5'd15;
              end
            end
          end

          3'b011:
          begin
            baud_counter <= baud_counter - 1;
            if (baud_counter == 5'd7)
            begin
              parity_error <= parity_bit;
              state <= 3'b011;
            end
            else if (baud_counter == 0)
            begin
              state <= 3'b100;
              baud_counter <= 5'd15;
            end
          end

          3'b100:
          begin
            baud_counter <= baud_counter - 1;
            if (baud_counter == 5'd7)
            begin
              framing_error    <= ~rx;
              push  <= 1'b1;
              state <= 3'b100;
            end
            else if (baud_counter == 0)
            begin
              state <= 3'b000;
              baud_counter <= 5'd15;
            end
          end
        endcase
      end
    end
  end



endmodule