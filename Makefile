SHELL := /bin/bash

# directories
ROOT  := $(CURDIR)
OUT   := $(ROOT)/out
RPT   := $(ROOT)/reports

# open-source tools from iioc
IVERILOG ?= iverilog
VVP      ?= vvp
YOSYS    ?= yosys
OPENSTA  ?= sta
VERILATOR ?= verilator

# configuration of lib and pdk
PDK_ROOT ?= /foss/pdks
LIB := $(PDK_ROOT)/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_1v80.lib

# Gate-level simulation cell models (functional Verilog of GF180 standard cells)
GL_CELL_MODELS := \
    $(PDK_ROOT)/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v \
    $(PDK_ROOT)/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog/gf180mcu_fd_sc_mcu7t5v0.v

VCD_SEP := .

# configurable clock period in ns (can override ex: make CLK_PERIOD = 20.0)
CLK_PERIOD ?= 10.0

# input candidates
_RTL_CANDIDATES := $(wildcard rtl/*.v rtl/*.sv rtl/includes/*.v rtl/includes/*.sv)
_TB_CANDIDATES  := $(firstword $(wildcard tb/*.v))

# auto-configuration
$(OUT)/design.mk: $(_RTL_CANDIDATES) $(_TB_CANDIDATES) scripts/manage_design.py
	@mkdir -p $(OUT)
	@echo "[FLOW] Analyzing design hierarchy..."
	@python3 scripts/manage_design.py config $(OUT)/design.mk $(OUT)/rtl.f $(_RTL_CANDIDATES) --tb $(_TB_CANDIDATES) --json $(out)/design.json

-include $(OUT)/design.mk

# targets
.PHONY: all clean report dirs check lint sim synth sdc sta power gl_sim quick

all: dirs lint sim synth sdc sta power gl_sim report

dirs:
	@mkdir -p $(OUT) $(RPT)/timing $(RPT)/power

# 0. linting using Verilator
lint: $(OUT)/design.mk
	@if [ -z "$(_RTL_CANDIDATES)" ]; then echo "[ERR] No RTL files found in rtl/"; exit 1; fi
	@echo "[FLOW] Linting $(TOP) with Verilator..."
	@$(VERILATOR) --lint-only -Wall -Wno-fatal $(_RTL_CANDIDATES) --top-module $(TOP) 2>&1 | tee $(OUT)/lint.log
	@$(VERILATOR) --json-only $(_RTL_CANDIDATES) --top-module $(TOP) --json-only-output $(OUT)/design.json 2>/dev/null || true
	@if grep -qiE "^%Error" $(OUT)/lint.log; then echo "[LINT] FAILED: errors found - see $(OUT)/lint.log"; exit 1; fi
	
	@echo "[LINT] PASSED"


# 1. simulation (RTL-level)
sim: $(OUT)/design.mk
	@if [ -z "$(_TB_CANDIDATES)" ]; then echo "[ERR] No Testbench found in tb/"; exit 1; fi
	@if [ "$(TOP)" = "UNKNOWN_TOP" ]; then echo "[ERR] No Top Module Found"; exit 1; fi
	@if [ "$(TOP)" = "AMBIGUOUS_TOP" ]; then echo "[ERR] Multiple uninstantiated modules found. Please check hierarchy."; exit 1; fi
	@echo "[FLOW] Simulating $(TOP)..."
	$(IVERILOG) -g2012 -o $(OUT)/sim.vvp -f $(OUT)/rtl.f $(_TB_CANDIDATES)
	$(VVP) $(OUT)/sim.vvp | tee $(OUT)/sim.log
	@[ -f waves.vcd ] && mv waves.vcd $(OUT)/waves.vcd || true
	@grep "PASS" $(OUT)/sim.log > /dev/null || (echo "[SIM] FAILED: 'PASS' not found" && exit 1)
	@echo "[SIM] PASSED"

# 2. synthesis
synth: $(OUT)/design.mk
	@echo "[FLOW] Synthesizing $(TOP)..."
	@rm -f $(OUT)/synth.ys
	@while read -r file; do echo "read_verilog -sv $$file" >> $(OUT)/synth.ys; done < $(OUT)/rtl.f
	@# Add the rest of the synthesis commands
	@echo "hierarchy -check -top $(TOP)"          >> $(OUT)/synth.ys
	@echo "synth -top $(TOP)"            >> $(OUT)/synth.ys
	@echo "dfflibmap -liberty $(LIB)"             >> $(OUT)/synth.ys
	@echo "abc -liberty $(LIB)"                   >> $(OUT)/synth.ys
	@echo "clean"                                 >> $(OUT)/synth.ys
	@echo "rename -enumerate"                     >> $(OUT)/synth.ys
	@echo "write_verilog -noattr $(OUT)/netlist.v">> $(OUT)/synth.ys
	@echo "stat -liberty $(LIB)"                  >> $(OUT)/synth.ys
	@$(YOSYS) -Q -s $(OUT)/synth.ys | tee $(OUT)/yosys.log

# 3. SDC
sdc: $(OUT)/design.mk
	@echo "[FLOW] Generating Constraints (CLK_PERIOD=$(CLK_PERIOD) ns)..."
	@{ \
	  if [ "$(CLK)" = "none" ]; then \
	     echo "set_max_delay $(CLK_PERIOD) -from [all_inputs] -to [all_outputs]"; \
	  else \
	     echo "create_clock -name core_clk -period $(CLK_PERIOD) [get_ports {$(CLK)}]"; \
	     echo "set_input_delay 2.0 -clock core_clk [all_inputs]"; \
	     echo "set_output_delay 2.0 -clock core_clk [all_outputs]"; \
	     echo "set_input_transition 0.5 [all_inputs]"; \
	     echo "set_load 0.05 [all_outputs]"; \
	  fi; \
	} > $(OUT)/constraints.sdc
	
# 4. STA
sta: synth sdc
	@echo "[FLOW] Running STA..."
	@{ \
	  echo "read_liberty $(LIB)"; \
	  echo "read_verilog $(OUT)/netlist.v"; \
	  echo "link_design $(TOP)"; \
	  echo "read_sdc $(OUT)/constraints.sdc"; \
	  echo "report_checks -path_delay min_max > $(RPT)/timing/checks.rpt"; \
	  echo "report_worst_slack > $(RPT)/timing/wns.rpt"; \
	} > $(OUT)/sta.tcl
	@$(OPENSTA) -no_init -exit $(OUT)/sta.tcl 

# 5. Power (depends on Sim + Synth + SDC)
power: sim synth sdc
	@echo "[FLOW] Running Power Analysis..."
	@{\
	  echo "read_liberty $(LIB)"; \
	  echo "read_verilog $(OUT)/netlist.v"; \
	  echo "link_design $(TOP)"; \
	  echo "read_sdc $(OUT)/constraints.sdc"; \
	  if [ -f "$(OUT)/waves.vcd" ]; then \
	      SCOPE=$$(python3 scripts/manage_design.py scope $(OUT)/waves.vcd $(DUT_INST) "$(VCD_SEP)"); \
	      if [ "$$SCOPE" = "none" ]; then \
	          echo "puts { [WARN] DUT instance '$(DUT_INST)' not found/active in VCD. }"; \
	          echo "report_power > $(RPT)/power/power.rpt"; \
	      else \
	          echo "read_vcd -scope {$$SCOPE} $(OUT)/waves.vcd"; \
	          echo "report_power > $(RPT)/power/power.rpt"; \
	      fi; \
	  else \
	      echo "puts { [WARN] No VCD found. }"; \
	      echo "report_power > $(RPT)/power/power.rpt"; \
	  fi; \
	} > $(OUT)/power.tcl
	@$(OPENSTA) -no_init -exit $(OUT)/power.tcl 

# 6. Gate-Level Simulation (depends on synth)
# Simulates the post-synthesis netlist against the same testbench using the GF180 cell functional models. Validates that synthesis preserved the RTL behaviour. If RTL sim PASSes but gl_sim FAILs, synthesis introduced a behavioural change.
gl_sim: synth
	@if [ -z "$(_TB_CANDIDATES)" ]; then echo "[ERR] No testbench found in tb/"; exit 1; fi
	@echo "[FLOW] Gate-Level Simulating $(TOP)..."
	@if [ ! -f "$(OUT)/netlist.v" ]; then echo "[ERR] No netlist found. Run 'make synth' first."; exit 1; fi
	@for f in $(GL_CELL_MODELS); do \
	    if [ ! -f "$$f" ]; then \
	        echo "[ERR] GF180 cell model not found: $$f"; \
	        echo "[HINT] Check PDK_ROOT or list available libs with: ls $(PDK_ROOT)/gf180mcuD/libs.ref/*/verilog/"; \
	        exit 1; \
	    fi; \
	done
	$(IVERILOG) -g2012 \
	    -o $(OUT)/gl_sim.vvp \
	    -DFUNCTIONAL -DUNIT_DELAY=#1 \
	    $(GL_CELL_MODELS) \
	    $(OUT)/netlist.v \
	    $(_TB_CANDIDATES) 2>&1 | tee $(OUT)/gl_sim_compile.log
	$(VVP) $(OUT)/gl_sim.vvp | tee $(OUT)/gl_sim.log
	@[ -f waves.vcd ] && mv waves.vcd $(OUT)/gl_waves.vcd || true
	@grep "PASS" $(OUT)/gl_sim.log > /dev/null || (echo "[GL_SIM] FAILED: 'PASS' not found in gate-level simulation" && exit 1)
	@echo "[GL_SIM] PASSED"

#  TOKEN-EFFICIENT TARGETS (for use by LLM agents)
# Wrap existing targets with output filtering to minimise log volume sent back to the agent. Use these instead of raw targets when running the agentic pipeline.

# Quick check: lint + sim, output filtered to last 30 lines
quick: $(OUT)/design.mk
	@$(MAKE) lint sim 2>&1 | tail -30

# Full check: lint + sim with filtered output, then auto-run report.py
check: $(OUT)/design.mk
	@$(MAKE) lint sim 2>&1 | tail -30
	@python3 scripts/report.py $(OUT) 2>/dev/null || true
	@echo ""
	@echo "[CHECK] Read $(OUT)/feedback.json for classified errors"

report:
	@python3 scripts/report.py $(OUT)

clean:
	rm -rf $(OUT) $(RPT) waves.vcd