# Agentic LLM-Driven RTL Generation with Automated Verification Feedback

NTU EEE URECA Project (EEE25005)
**Author:** Lee Hyunseung;
**Supervisors:** Prof. Chang Chip Hong, Dr. Vivek Mohan, Dr. Viktor Schlegel

An autonomous AI agent that generates Verilog RTL from natural-language specifications, verifies it through a complete open-source EDA flow, and iteratively corrects errors based on classified feedback — without requiring golden testbenches at generation time.

## Project Goal

Investigate whether an LLM agent equipped with standard EDA tools and structured error feedback can iteratively generate functionally correct, synthesizable Verilog that meets PPA constraints. The pipeline targets the gap between single-turn LLM generation (~63% pass rate) and heavyweight multi-agent systems like VerilogCoder (94%, but requires AST tooling and golden testbenches).

## Environment Setup

This project runs entirely inside the [IIC-OSIC-TOOLS](https://github.com/iic-jku/iic-osic-tools) Docker container, which provides Verilator, Icarus Verilog, Yosys, OpenSTA, and the GF180MCU PDK out of the box.

### 1. Start the container

```bash
~/foss/iic-osic-tools/start_vnc.sh
docker exec -it iic-osic-tools_xvnc_uid_1012 bash
```

### 2. Clone this repo into the mounted designs folder

```bash
cd /foss/designs
git clone https://github.com/leeh0128/ureca-verilog-agent.git URECA/ureca_designs
cd URECA/ureca_designs
```

### 3. (Optional) Install Claude Code for the agentic flow

```bash
# Run as root inside the container
exit
docker exec -it -u root iic-osic-tools_xvnc_uid_1012 bash
apt update && apt install -y nodejs npm
npm install -g @anthropic-ai/claude-code
```

## Project Layout

```
ureca_designs/
├── CLAUDE.md           # System prompt / config for Claude Code agent
├── Makefile            # Full EDA flow: lint → sim → synth → STA → power → gl_sim
├── scripts/
│   ├── agent.py        # Standalone Python agentic system (Gemini/OpenAI/Anthropic)
│   ├── llm_loop.py     # Scripted feedback loop (non-agentic baseline)
│   ├── report.py       # Error classifier → out/feedback.json
│   └── manage_design.py # Auto-detects top module and clock signal
├── rtl/                # Generated Verilog (the only writable directory for the agent)
├── tb/                 # Testbenches (READ-ONLY)
├── synth/              # Synthesis scripts
├── constraints/        # SDC templates
├── spec_counter.txt    # Test spec: 4-bit up counter
└── spec_fsm.txt        # Test spec: 1011 overlapping sequence detector FSM
```

## How to Run

### Manual flow (no agent)

```bash
# Drop a Verilog file in rtl/, then run the full EDA flow
make all                # lint + sim + synth + STA + power + gate-level sim
make clean              # Wipe build artifacts
```

Individual stages:
```bash
make lint               # Verilator linting
make sim                # RTL simulation with Icarus Verilog
make synth              # Yosys synthesis to GF180MCU
make sta                # OpenSTA static timing analysis
make power              # Power analysis with VCD activity
make gl_sim             # Gate-level simulation of the post-synthesis netlist
```

Token-efficient targets for use by LLM agents:
```bash
make quick              # lint + sim, output filtered to last 30 lines
make check              # Same as quick + auto-runs report.py → feedback.json
```

### Agentic flow with Claude Code

```bash
cd /foss/designs/URECA/ureca_designs
claude
# Then in the Claude Code prompt:
> Generate Verilog for the spec in spec_fsm.txt. Verify it passes make check. Fix any errors. When it passes, run make all.
```

The `CLAUDE.md` file in the project root acts as a persistent system prompt — it tells the agent the project layout, available commands, Verilog coding rules, common pitfalls, and token-efficiency instructions.

### Agentic flow with the standalone Python agent

For environments without Claude Code (or to use Gemini/OpenAI):

```bash
export GEMINI_API_KEY="your-key-here"
python3 scripts/agent.py spec_fsm.txt --model gemini-2.5-flash
```

## Pipeline Stages

1. **Specification** — Natural-language Verilog spec in a `.txt` file
2. **LLM Generation** — Agent writes Verilog to `rtl/<ModuleName>.v`
3. **EDA Verification** — `make all` runs the full toolchain
4. **Error Classification** — `scripts/report.py` parses logs, classifies errors into a taxonomy (compile, simulation, lint, synthesis), and writes `out/feedback.json`
5. **Agent Decision** — Agent reads feedback and decides: fix code, re-read spec, inspect testbench, or signal completion
6. **Re-generation** — Agent corrects code and loops back to step 3

## Test Cases

### `spec_counter.txt` — 4-bit up counter
Simple sequential design. Both Sonnet 4.6 and Haiku 4.5 pass on the first attempt.
**Expected results:** 13 cells, 412.7 µm², −0.43 ns slack @ 10 ns clock, 31.7 µW.

### `spec_fsm.txt` — 1011 overlapping sequence detector
Moore FSM with overlapping detection, tested against 8 verification cases.
**Expected results:** 17 cells, 561.97 µm², 3.83 ns slack @ 10 ns clock, 39.8 µW.

## Adding a New Test Case

1. Write a spec file in the project root, e.g. `spec_my_design.txt`
2. Write a testbench in `tb/TopModule_my_design_tb.v` (must include `PASS`/`FAIL` print statements)
3. Run the agent or call `make all` after writing RTL manually

## Future Work

- Batch evaluation on the [VerilogEval v2](https://github.com/NVlabs/verilog-eval) benchmark (156 problems)
- Statistical comparison: single-turn vs. agentic pass rates
- Local LLM inference via Ollama (no API rate limits)
- Multi-agent specialisation (separate design and debug agents)

## References

1. Liu et al., "VerilogEval: Evaluating LLMs for Verilog Code Generation," ICCAD 2023.
2. Pinckney et al., "Revisiting VerilogEval: Newer LLMs, ICL, and Spec-to-RTL," arXiv:2408.11053, 2025.
3. Ho et al., "VerilogCoder: Autonomous Verilog Coding Agents with AST-Based Waveform Tracing," AAAI 2025.
4. Thakur et al., "Benchmarking LLMs for Automated Verilog RTL Code Generation," ACM TODAES 2024.

## Contact

For questions about this project or handover, contact Lee Hyunseung or the supervising team listed above.
