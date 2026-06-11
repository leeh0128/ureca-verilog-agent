module TopModule (
    input clk,
    input reset,
    input data,
    output reg [3:0] count,
    output reg counting,
    output reg done,
    input ack
);

    localparam S_SEARCH = 4'd0;
    localparam S_GOT1   = 4'd1;
    localparam S_GOT11  = 4'd2;
    localparam S_GOT110 = 4'd3;
    localparam S_SHIFT0 = 4'd4;
    localparam S_SHIFT1 = 4'd5;
    localparam S_SHIFT2 = 4'd6;
    localparam S_SHIFT3 = 4'd7;
    localparam S_COUNT  = 4'd8;
    localparam S_DONE   = 4'd9;

    reg [3:0] state;
    reg [3:0] delay;      // stores the 4-bit delay value
    reg [3:0] delay_count; // current countdown
    reg [9:0] cycle_count; // 0..999

    always @(posedge clk) begin
        if (reset) begin
            state <= S_SEARCH;
            delay <= 4'd0;
            delay_count <= 4'd0;
            cycle_count <= 10'd0;
            counting <= 1'b0;
            done <= 1'b0;
            count <= 4'd0;
        end else begin
            case (state)
                S_SEARCH: begin
                    counting <= 1'b0;
                    done <= 1'b0;
                    if (data == 1'b1)
                        state <= S_GOT1;
                    else
                        state <= S_SEARCH;
                end
                
                S_GOT1: begin
                    if (data == 1'b1)
                        state <= S_GOT11;
                    else
                        state <= S_SEARCH;
                end
                
                S_GOT11: begin
                    if (data == 1'b0)
                        state <= S_GOT110;
                    else
                        state <= S_GOT11; // stay, got another 1
                end
                
                S_GOT110: begin
                    if (data == 1'b1)
                        state <= S_SHIFT0;
                    else
                        state <= S_SEARCH;
                end
                
                // Shift in 4 bits MSB first: delay[3], delay[2], delay[1], delay[0]
                S_SHIFT0: begin
                    delay[3] <= data;
                    state <= S_SHIFT1;
                end
                
                S_SHIFT1: begin
                    delay[2] <= data;
                    state <= S_SHIFT2;
                end
                
                S_SHIFT2: begin
                    delay[1] <= data;
                    state <= S_SHIFT3;
                end
                
                S_SHIFT3: begin
                    delay[0] <= data;
                    // Initialize counters - delay[3:1] already stored, delay[0]=data
                    delay_count <= {delay[3], delay[2], delay[1], data};
                    cycle_count <= 10'd0;
                    count <= {delay[3], delay[2], delay[1], data};
                    counting <= 1'b1;
                    state <= S_COUNT;
                end
                
                S_COUNT: begin
                    counting <= 1'b1;
                    if (cycle_count == 10'd999) begin
                        cycle_count <= 10'd0;
                        if (delay_count == 4'd0) begin
                            // Done
                            state <= S_DONE;
                            counting <= 1'b0;
                            done <= 1'b1;
                        end else begin
                            delay_count <= delay_count - 4'd1;
                            count <= delay_count - 4'd1;
                        end
                    end else begin
                        cycle_count <= cycle_count + 10'd1;
                        count <= delay_count;
                    end
                end
                
                S_DONE: begin
                    counting <= 1'b0;
                    done <= 1'b1;
                    if (ack) begin
                        done <= 1'b0;
                        state <= S_SEARCH;
                    end
                end
                
                default: state <= S_SEARCH;
            endcase
        end
    end

endmodule