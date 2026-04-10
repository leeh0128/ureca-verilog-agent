`timescale 1ns/1ps

module tb_traffic;

    logic clk, rst_n, car_sensor;
    wire [1:0] light;

    // Instance name is "uut" this time (Automator must find it)
    traffic_light uut (
        .clk(clk),
        .rst_n(rst_n),
        .car_sensor(car_sensor),
        .light(light)
    );

    // Clock gen
    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, tb_traffic);

        // Reset
        rst_n = 0; car_sensor = 0;
        #20 rst_n = 1;

        // Test Case 1: Wait for Red -> Green
        #50;
        
        // Test Case 2: Car arrives
        car_sensor = 1;
        #20 car_sensor = 0;
        
        // Run long enough to see cycles
        #300;
        
        // Simple sanity check: Logic should be valid (not X)
        if (light !== 2'bx) 
            $display("TEST PASS");
        else 
            $display("TEST FAIL");

        $finish;
    end

endmodule