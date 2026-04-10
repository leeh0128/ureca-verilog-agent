module fsm (
    input clk, rst_n, in,
    output reg out
);
    // standard Moore Machine: 1->1 Sequence Detector
    parameter S0 = 2'b00, S1 = 2'b01, S2 = 2'b10;
    reg [1:0] state, next_state;

    // sequential Logic
    always @(posedge clk or negedge rst_n)
        if (!rst_n) state <= S0;
        else        state <= next_state;

    // combinational Logic
    always @(*) begin
        case (state)
            S0: next_state = in ? S1 : S0;
            S1: next_state = in ? S2 : S0;
            S2: next_state = in ? S2 : S0;
            default: next_state = S0;
        endcase
    end

    // output Logic
    always @(*) out = (state == S2);
endmodule