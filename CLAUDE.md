# Verilog RTL Generation Agent

## Goal
Generate functionally correct, synthesizable Verilog from a spec file. Verify it. Fix errors. Get PASS on `make all`.

## Project Layout
```
rtl/          ← write your Verilog here (ONLY writable directory)
tb/           ← testbenches (READ-ONLY — never modify)
out/          ← build logs + feedback.json
scripts/      ← build scripts (READ-ONLY)
Makefile      ← build system (READ-ONLY)
*.txt         ← spec files
```

## Commands
| Command | Purpose |
|---------|---------|
| `make clean && make check` | Fast check: lint + simulation |
| `make all` | Full flow: lint → sim → synth → STA → power |
| `python3 scripts/report.py out` | Classify errors → `out/feedback.json` |

## Workflow (follow this order)
1. **Read the spec** file carefully — understand ports, behaviour, reset, clock edge
2. **Read the testbench** in `tb/` — understand what signals are checked, when, and how (e.g. does it check outputs combinationally or after a clock edge? This determines whether your output should be registered or combinational)
3. **Write Verilog** to `rtl/<ModuleName>.v` — get it right the first time, don't write then immediately rewrite
4. **Run** `make clean && make lint sim`
5. **If FAIL**: run `python3 scripts/report.py out` then read `out/feedback.json` for classified errors. Fix based on the error categories, then go to step 4
6. **If PASS**: run `make all` for synthesis + timing + power results

## Verilog Rules
- All ports: `input logic` / `output logic`
- Sequential: `always @(posedge clk)`
- Combinational: `assign` or `always @(*)`
- State encoding: `localparam` (never `typedef enum`)
- End every file with `endmodule` + newline
- No testbench constructs in RTL (`$display`, `$finish`, `initial`)

## Common Pitfalls (read before writing)
- **Registered vs combinational output**: if the testbench checks outputs with `#1` after `@(posedge clk)`, your output likely needs to be a registered (flopped) signal, not a combinational `assign`
- **Overlapping FSM detection**: after detecting a full sequence, transition to the appropriate mid-sequence state (not IDLE) to catch overlapping matches
- **Width mismatches**: if comparing signals of different widths, explicitly size your constants (e.g. `3'd4` not just `4`)
- **Incomplete case**: always include a `default` branch in case statements
- **Inferred latches**: ensure all outputs are assigned in every branch of combinational `always @(*)` blocks

## Token Efficiency (IMPORTANT — save usage)
- **Pipe make output through tail**: use `make lint sim 2>&1 | tail -40` instead of raw `make` — full output wastes thousands of tokens on Verilator banners and synthesis logs
- **Use report.py instead of reading raw logs**: `python3 scripts/report.py out` produces a compact summary. Read `out/feedback.json` instead of `out/lint.log` or `out/sim.log` directly — it's shorter and structured
- **Don't re-read files you just wrote**: you already know the contents
- **Don't explain your reasoning at length**: just fix the code and run the test
- **One write, then test**: never write a file and immediately rewrite it before testing. Write once, test, then fix only if it fails
- **Skip make clean on retries**: only use `make clean` before the first run. Subsequent iterations can just run `make lint sim` directly
- **Limit make all to final pass**: only run `make all` once lint+sim passes. Don't run full synthesis on broken code
