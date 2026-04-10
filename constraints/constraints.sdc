create_clock -name clk      -period 10.000   [get_ports clk     ]
set_input_delay 2.0 -clock clk      [get_ports -filter "direction==input && name!=clk     " *]
set_output_delay 2.0 -clock clk      [all_outputs]
set_load 0.02     [all_outputs]
