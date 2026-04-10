module TopModule (
    input logic clk,
    input logic reset,
    input logic in_bit,
    output logic detected
);

    // State encoding
    localparam IDLE   = 3'd0;
    localparam S1     = 3'd1;
    localparam S10    = 3'd2;
    localparam S101   = 3'd3;
    localparam S1011  = 3'd4;

    logic [2:0] state, next_state;
    logic detected_r;

    // Sequential logic: state transitions and registered output
    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            detected_r <= 1'b0;
        end else begin
            state <= next_state;
            detected_r <= (state == S1011) ? 1'b1 : 1'b0;
        end
    end

    // Combinational logic: next state
    always @(*) begin
        case (state)
            IDLE: begin
                if (in_bit == 1'b1)
                    next_state = S1;
                else
                    next_state = IDLE;
            end
            S1: begin
                if (in_bit == 1'b1)
                    next_state = S1;
                else
                    next_state = S10;
            end
            S10: begin
                if (in_bit == 1'b1)
                    next_state = S101;
                else
                    next_state = IDLE;
            end
            S101: begin
                if (in_bit == 1'b1)
                    next_state = S1011;
                else
                    next_state = S10;
            end
            S1011: begin
                if (in_bit == 1'b1)
                    next_state = S1;
                else
                    next_state = S10;
            end
            default:
                next_state = IDLE;
        endcase
    end

    // Output: registered, so detected is high one cycle after being in S1011
    assign detected = detected_r;

endmodule
