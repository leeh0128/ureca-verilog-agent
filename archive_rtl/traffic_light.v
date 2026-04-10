module traffic_light (
    input  logic clk,
    input  logic rst_n,
    input  logic car_sensor,  // 1 if car is waiting
    output logic [1:0] light  // 00=RED, 01=YEL, 10=GRN
);

    // 1. SystemVerilog Enum (Tests if -sv flag works)
    typedef enum logic [1:0] {
        RED = 2'b00,
        YEL = 2'b01,
        GRN = 2'b10
    } state_t;

    state_t current_state, next_state;
    logic [3:0] timer;

    // 2. Sequential Logic (always_ff)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            current_state <= RED;
            timer <= 0;
        end else begin
            current_state <= next_state;
            if (current_state != next_state) timer <= 0;
            else timer <= timer + 1;
        end
    end

    // 3. Combinational Logic (always_comb + case)
    // This 'case' block tests if our regex accidentally thinks "case" is a module type.
    always_comb begin
        next_state = current_state;
        light = RED; // Default

        case (current_state)
            RED: begin
                light = RED;
                // Wait 10 cycles, or until car arrives
                if (timer > 10 || car_sensor) next_state = GRN;
            end
            
            GRN: begin
                light = GRN;
                // Stay green for 8 cycles
                if (timer > 8) next_state = YEL;
            end
            
            YEL: begin
                light = YEL;
                // Yellow for 3 cycles
                if (timer > 3) next_state = RED;
            end
        endcase
    end

endmodule