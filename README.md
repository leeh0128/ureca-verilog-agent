# Agentic LLM-Driven RTL Generation with Automated Verification Feedback

NTU EEE URECA Project (EEE25005)
**Author:** Lee Hyunseung;
**Supervisors:** Prof. Chang Chip Hong, Dr. Vivek Mohan, Dr. Viktor Schlegel

An autonomous AI agent that generates Verilog RTL from natural-language specifications, verifies it through a complete open-source EDA flow, and iteratively corrects errors based on classified feedback. The agent writes only the RTL; the verification testbench is manually provided and held read-only, so every candidate is scored against an identical, trusted reference.

> **Benchmark evaluation harness:** the VerilogEval v2 integration and the three-way
> comparison scripts used to produce the results below live in a companion repository:
> https://github.com/leeh0128/ureca-benchmark-eval

## Project Goal

Investigate whether an LLM agent equipped with standard open-source EDA tools and structured error feedback can iteratively generate functionally correct, synthesizable Verilog at zero cost. The work targets the gap between single-turn LLM generation (~63% pass@1 for GPT-4o in the literature) and heavyweight multi-agent systems like VerilogCoder (94.2%, but reliant on custom AST-based waveform-tracing tooling). The central question is whether adding Verilator lint as a *second* feedback channel alongside simulation meaningfully improves correctness and efficiency.

## Results

Three configurations were evaluated on the full 156-problem VerilogEval v2 spec-to-RTL benchmark using a single free-tier model (Gemini 2.5 Flash-Lite, temperature 0, 0-shot), so that differences reflect the feedback architecture rather than model capability.

| Configuration            | Pass rate | Passes  | Total tokens | Avg tok/prob | Wall time |
| ------------------------ | --------- | ------- | ------------ | ------------ | --------- |
| Single-shot baseline     | 44.9%     | 70/156  | 115K         | 740          | 40 min    |
| Agentic (simulation)     | 67.3%     | 105/156 | 1,629K       | 10,442       | 1h 45m    |
| Agentic (sim + lint)     | 68.6%     | 107/156 | 1,418K       | 9,090        | 1h 12m    |

Key findings:

- **Iterative simulation feedback is the dominant effect**, recovering 35 additional problems over the single-shot baseline (+22.4 pp), achieved by the feedback architecture alone with model and benchmark held constant.
- **Adding lint is primarily an efficiency win.** The pass-rate gain is modest (+1.3 pp, and not robust across runs), but the lint channel cuts token usage by 13% and wall time by 31% by helping the model converge faster on rule violations.
- **Lint specifically recovers structural failures** in the categories Verilator targets precisely (asynchronous reset usage, width mismatches, wire-vs-logic errors).

The reproduction scripts and the raw three-way comparison (`comparison.csv`) are in the
[benchmark evaluation repository](https://github.com/leeh0128/ureca-benchmark-eval).

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
├── CLAUDE.md           # Persistent system prompt / config for the agentic flows
├── Makefile            # Full EDA flow: lint → sim → synth → STA → power → gl_sim
├── scripts/
│   ├── agent.py        # Tool-calling agentic system (Gemini/OpenAI/Anthropic)
│   ├── llm_loop.py     # Fixed scripted feedback loop (no filesystem access)
│   ├── report.py       # Error classifier → out/feedback.json
│   └── manage_design.py # Auto-detects top module and clock signal
├── rtl/                # Generated Verilog (the only writable directory for the agent)
├── tb/                 # Testbenches (READ-ONLY — never modified by the agent)
├── synth/              # Synthesis scripts
├── constraints/        # SDC templates
├── spec_counter.txt    # Test spec: 4-bit up counter
└── spec_fsm.txt        # Test spec: 1011 overlapping sequence detector FSM
```

## LLM Integration Approaches

The pipeline supports three ways of driving an LLM, each with different trade-offs:

- **Fixed scripted loop (`llm_loop.py`)** — a Python orchestrator owns the whole
  generate–test–fix cycle; the model sees only text and never touches the filesystem
  or the testbench. Predictable token cost, but cannot inspect the testbench before
  writing code.
- **Tool-calling agent (`agent.py`)** — the model is given file/make/report tools and
  decides autonomously when to use them. Write access is restricted to `rtl/`, so the
  agent can modify only its own RTL candidate, never the testbench. This is the
  approach adapted for the benchmark sweep.
- **Claude Code** — Anthropic's CLI agent, using `CLAUDE.md` as its system prompt.
  Convenient for interactive use but unsuitable for batch evaluation at scale on a
  paid subscription.

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
**Expected results:** 17 cells, 561.97 µm², +3.83 ns slack @ 10 ns clock, 39.8 µW.

## Adding a New Test Case

1. Write a spec file in the project root, e.g. `spec_my_design.txt`
2. Write a testbench in `tb/TopModule_my_design_tb.v` (must include `PASS`/`FAIL` print statements)
3. Run the agent or call `make all` after writing RTL manually

## Future Work

Directions that follow directly from the benchmark findings:

- **Gate advisory lint feedback on sim-failed iterations** to eliminate the
  lint–simulation oscillation failure mode observed in two problems (where conflicting
  feedback channels prevented convergence).
- **Iteration-count ablation** (max-iters = 1, 2, 3, 5) to characterise the pass-rate
  vs. efficiency trade-off.
- **Stronger paid-model evaluation** to test whether the lint channel's value changes
  with model capability.
- **FPGA targets** — a parallel FPGA-targeted pipeline variant was prototyped during
  the project and is reserved for future work.
- **PPA-aware feedback** — feeding back area, timing slack, and switching activity from
  the synthesis/STA/power stages as additional structured signals.
- **Hardware security extensions** — logic locking and structural watermarking as
  generation constraints, the longer-term goal of the broader URECA programme.
- **Local LLM inference** via Ollama to remove API rate limits.

## References

1. M. Liu, N. Pinckney, B. Khailany, and H. Ren, "VerilogEval: Evaluating Large Language Models for Verilog Code Generation," in *Proc. IEEE/ACM Int. Conf. Comput.-Aided Des. (ICCAD)*, 2023.
2. N. Pinckney, C. Batten, M. Liu, H. Ren, and B. Khailany, "Revisiting VerilogEval: Newer LLMs, In-Context Learning, and Specification-to-RTL Tasks," arXiv:2408.11053, 2024.
3. C.-T. Ho, H. Ren, and B. Khailany, "VerilogCoder: Autonomous Verilog Coding Agents with Graph-based Planning and Abstract Syntax Tree (AST)-based Waveform Tracing Tool," in *Proc. AAAI*, 2025.
4. S. Thakur, B. Ahmad, H. Pearce, B. Tan, B. Dolan-Gavitt, R. Karri, and S. Garg, "VeriGen: A Large Language Model for Verilog Code Generation," *ACM Trans. Des. Autom. Electron. Syst.*, vol. 29, no. 3, 2024.

## Contact

For questions about this project or handover, contact Lee Hyunseung or the supervising team listed above.