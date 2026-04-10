"""
llm_loop.py  —  LLM-based Verilog generation with negative feedback loop.

Orchestrates:  spec → decompose → generate → make all → classify → feedback → re-generate → ...

Usage:
    python3 scripts/llm_loop.py --spec spec.txt [options]

    Options:
        --spec          Path to specification file (required)
        --max-iter      Maximum feedback iterations (default: 5)
        --model         LLM model name (default: gpt-4o)
        --provider      API provider: openai | anthropic (default: openai)
        --temperature   Sampling temperature (default: 0.0)
        --skip-decomp   Skip spec decomposition step
        --make-target   Make target for fast iteration (default: "lint sim")
        --make-full     Run full "make all" on final pass
        --rtl-dir       Directory for generated RTL (default: rtl/)
        --out-dir       Pipeline output directory (default: out/)
        --verbose       Print LLM prompts and responses
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

#  config

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_PROVIDER = "gemini"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_ITER = 5
DEFAULT_MAKE_TARGET = "lint sim"

#  LLM client - Thin wrapper supporting Gemini, OpenAI, and Anthropic

def call_llm(messages, model, provider, temperature=0.0):
    """
    Call the LLM API.  Returns the assistant's reply as a string.

    `messages` is a list of dicts: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    if provider == "gemini":
        return _call_gemini(messages, model, temperature)
    elif provider == "openai":
        return _call_openai(messages, model, temperature)
    elif provider == "anthropic":
        return _call_anthropic(messages, model, temperature)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _call_gemini(messages, model, temperature):
    """Call Google Gemini via its OpenAI-compatible endpoint (free tier)."""
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[ERR] openai package not installed.  Run: pip install openai")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("[ERR] GEMINI_API_KEY not set. Get one free at https://aistudio.google.com")

    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=4096,
    )
    return resp.choices[0].message.content


def _call_openai(messages, model, temperature):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[ERR] openai package not installed.  Run: pip install openai")

    client = OpenAI()  # reads OPENAI_API_KEY from env
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=4096,
    )
    return resp.choices[0].message.content


def _call_anthropic(messages, model, temperature):
    try:
        import anthropic
    except ImportError:
        sys.exit("[ERR] anthropic package not installed.  Run: pip install anthropic")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    # Anthropic uses a separate 'system' param
    system_msg = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_msg = m["content"]
        else:
            user_messages.append(m)

    resp = client.messages.create(
        model=model,
        system=system_msg,
        messages=user_messages,
        temperature=temperature,
        max_tokens=4096,
    )
    return resp.content[0].text


#  stage 1: specification input

def load_spec(spec_path):
    """Load and validate the specification file."""
    if not os.path.exists(spec_path):
        sys.exit(f"[ERR] Spec file not found: {spec_path}")
    with open(spec_path, "r") as f:
        spec = f.read().strip()
    if not spec:
        sys.exit(f"[ERR] Spec file is empty: {spec_path}")
    return spec


#  stage 2: optional spec decomposition

DECOMPOSE_SYSTEM = """You are an expert digital hardware designer.
Given a module specification, extract a structured decomposition for implementation.

Return ONLY valid JSON with this schema:
{
  "module_name": "...",
  "ports": [{"name": "...", "direction": "input|output", "width": 1, "description": "..."}],
  "signals": [{"name": "...", "description": "..."}],
  "state_transitions": ["State A --input=1--> State B", ...],
  "subtasks": [
    {"id": 1, "description": "Define module interface with all ports", "signals": ["..."]},
    {"id": 2, "description": "Implement reset logic for ...", "signals": ["..."]},
    ...
  ]
}

Rules:
- Each subtask should focus on ONE signal or one logical unit.
- First subtask is always "Define module interface with all ports".
- Last subtask is always "Verify all outputs are assigned in all code paths".
- For FSMs: identify states first, then create one subtask per state transition signal.
- Include state_transitions only if the design is sequential/FSM.
- Do NOT include any text outside the JSON block.
"""


def decompose_spec(spec, model, provider, temperature):
    """
    Ask the LLM to decompose the spec into structured sub-tasks.
    Returns the decomposition dict, or None on failure.
    """
    messages = [
        {"role": "system", "content": DECOMPOSE_SYSTEM},
        {"role": "user", "content": f"Decompose this hardware specification:\n\n{spec}"},
    ]
    raw = call_llm(messages, model, provider, temperature)

    # extract JSON from response (handle markdown fences)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        # try parsing the whole response as JSON
        raw = raw.strip()

    try:
        decomp = json.loads(raw)
        return decomp
    except json.JSONDecodeError:
        print("[WARN] Spec decomposition returned invalid JSON — skipping.")
        return None


#  stage 3: LLM code generation

GENERATE_SYSTEM = """You are a Verilog RTL designer that writes correct, synthesizable SystemVerilog code.

Rules:
- Declare all ports as 'logic'. Use 'logic' for internal signals too.
- For combinational logic, use 'assign' or 'always @(*)' (never explicit sensitivity lists).
- For sequential logic, use 'always @(posedge clk)'.
- Always include 'endmodule' at the end.
- Do NOT use 'typedef enum' — use 'localparam' for state encoding.
- Do NOT include testbench code, $display, or $finish.
- Do NOT include any explanation — output ONLY the Verilog code.
- Enclose your code with [BEGIN] and [DONE] markers.
"""

ICL_EXAMPLE = """
Example — a combinational incrementer:

Question:
Implement a hardware module named TopModule with the following interface.
- input in_ (8 bits)
- output out (8 bits)
The module should increment the input by one.

Answer:
[BEGIN]
module TopModule (
    input  logic [7:0] in_,
    output logic [7:0] out
);
    assign out = in_ + 1;
endmodule
[DONE]
"""


def generate_code(spec, decomposition, model, provider, temperature):
    """
    Generate Verilog code from the spec and optional decomposition.
    Returns the extracted Verilog code string.
    """
    user_content = "Implement the following hardware module.\n\n"
    user_content += f"Specification:\n{spec}\n"

    if decomposition:
        # attach decomposition context if needed
        subtasks = decomposition.get("subtasks", [])
        if subtasks:
            user_content += "\nImplementation plan (follow this order):\n"
            for st in subtasks:
                user_content += f"  {st['id']}. {st['description']}\n"
                sigs = st.get("signals", [])
                if sigs:
                    user_content += f"     Related signals: {', '.join(sigs)}\n"

        transitions = decomposition.get("state_transitions", [])
        if transitions:
            user_content += "\nState transitions:\n"
            for t in transitions:
                user_content += f"  {t}\n"

    user_content += "\nEnclose your code with [BEGIN] and [DONE]. Only output the code."

    messages = [
        {"role": "system", "content": GENERATE_SYSTEM},
        {"role": "user", "content": ICL_EXAMPLE + "\nNow solve this:\n\n" + user_content},
    ]

    raw = call_llm(messages, model, provider, temperature)
    return _extract_verilog(raw)


def _extract_verilog(response):
    """Extract Verilog code from LLM response, handling various formats."""
    # try [BEGIN]...[DONE] markers first
    m = re.search(r"\[BEGIN\]\s*(.*?)\s*\[DONE\]", response, re.DOTALL)
    if m:
        code = m.group(1).strip()
        if code:
            return _ensure_endmodule(code)

    # try ```verilog ... ``` fences
    m = re.search(r"```(?:verilog|systemverilog|sv)?\s*(.*?)```", response, re.DOTALL)
    if m:
        code = m.group(1).strip()
        if code:
            return _ensure_endmodule(code)

    # try to find module...endmodule block
    m = re.search(r"(module\s+\w+[\s\S]*?endmodule)", response)
    if m:
        return m.group(1).strip()

    # last resort: return everything (will likely fail lint/compile)
    return response.strip()


def _ensure_endmodule(code):
    """Append endmodule if missing."""
    if not re.search(r"\bendmodule\b", code):
        code += "\nendmodule"
    return code


#  stage 4: run make pipeline

def run_make(target="lint sim", out_dir="out"):
    """
    Run the make pipeline.  Returns (success: bool, return_code: int).
    We run 'make clean' first, then the target, capturing all output.
    """
    # clean previous artifacts
    subprocess.run(["make", "clean"], capture_output=True)

    # run the requested targets
    result = subprocess.run(
        ["make"] + target.split(),
        capture_output=True,
        text=True,
        timeout=300,  # 5 min timeout
    )

    # print make output for visibility
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode == 0, result.returncode


#  stage 5 and 6: error classification and feedback construction

DEBUG_SYSTEM = """You are a Verilog RTL designer fixing errors in generated code.

You will receive:
1. The original specification
2. The current (broken) Verilog code
3. Classified error feedback from the toolchain

Rules:
- Fix ONLY the issues described in the error feedback.
- Do NOT change the module interface unless the error specifically requires it.
- Declare all ports as 'logic'.
- For combinational logic, use 'assign' or 'always @(*)'.
- For sequential logic, use 'always @(posedge clk)'.
- Always include 'endmodule'.
- Do NOT use 'typedef enum' — use 'localparam' for state encoding.
- Do NOT include testbench code, $display, or $finish.
- Output ONLY the complete corrected Verilog module enclosed with [BEGIN] and [DONE].
"""


def build_feedback_prompt(spec, current_code, feedback_json):
    """
    Build a targeted correction prompt from the feedback JSON.
    Returns the user message string for the debug prompt.
    """
    parts = []
    parts.append("=== ORIGINAL SPECIFICATION ===")
    parts.append(spec)
    parts.append("")
    parts.append("=== CURRENT VERILOG CODE (has errors) ===")
    parts.append(current_code)
    parts.append("")
    parts.append("=== ERROR FEEDBACK FROM TOOLCHAIN ===")
    parts.append(f"Status: {feedback_json['overall_status']}")
    parts.append(f"Failed at stage: {feedback_json.get('failed_stage', 'unknown')}")
    parts.append("")

    issues = feedback_json.get("all_issues", [])
    if not issues:
        parts.append("No specific issues extracted — simulation did not produce PASS.")
    else:
        # group by category for clarity
        by_category = {}
        for issue in issues:
            cat = issue.get("category", "unknown")
            by_category.setdefault(cat, []).append(issue)

        for cat, cat_issues in by_category.items():
            parts.append(f"[{cat.upper()}] — {len(cat_issues)} issue(s):")
            for iss in cat_issues:
                loc = ""
                if "file" in iss and "line" in iss:
                    loc = f" at {iss['file']}:{iss['line']}"
                parts.append(f"  • {iss.get('message', 'No details')}{loc}")
            parts.append("")

    parts.append("=== INSTRUCTIONS ===")

    # tailor instructions based on failure stage
    stage = feedback_json.get("failed_stage")
    if stage == "lint":
        parts.append(
            "Fix all lint errors listed above. Also address warnings if possible — "
            "they often indicate real bugs (width mismatches, inferred latches)."
        )
    elif stage == "compile":
        parts.append(
            "Fix the compilation errors listed above. Common causes: "
            "missing endmodule, using undeclared signals, reg/wire type confusion."
        )
    elif stage == "simulation":
        parts.append(
            "The code compiles but produces wrong outputs. "
            "Check the mismatched signals listed above. Common causes: "
            "wrong boolean logic, off-by-one in counters, sync vs async reset confusion, "
            "missing state transitions in FSMs."
        )
    elif stage == "synthesis":
        parts.append(
            "The code simulates but fails synthesis. Check for non-synthesizable constructs."
        )
    else:
        parts.append("Fix the issues listed above and re-generate the complete module.")

    parts.append("")
    parts.append("Output the COMPLETE corrected module enclosed with [BEGIN] and [DONE].")

    return "\n".join(parts)


def load_feedback(out_dir):
    """Load the feedback.json produced by report.py."""
    path = os.path.join(out_dir, "feedback.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


#  file I/O helpers

def write_rtl(code, rtl_dir="rtl", filename=None):
    """Write generated Verilog code to the rtl/ directory."""
    os.makedirs(rtl_dir, exist_ok=True)

    if not filename:
        # extract module name for filename
        m = re.search(r"module\s+(\w+)", code)
        name = m.group(1) if m else "generated"
        filename = f"{name}.v"

    path = os.path.join(rtl_dir, filename)
    with open(path, "w") as f:
        f.write(code)
    print(f"[GEN] Wrote {len(code)} chars to {path}")
    return path


def read_current_rtl(rtl_dir="rtl"):
    """Read all .v files in rtl/ and concatenate them."""
    code_parts = []
    for fname in sorted(os.listdir(rtl_dir)):
        if fname.endswith(".v"):
            with open(os.path.join(rtl_dir, fname), "r") as f:
                code_parts.append(f.read())
    return "\n".join(code_parts)


#  main loop

def main():
    parser = argparse.ArgumentParser(
        description="LLM Verilog generation with negative feedback loop"
    )
    parser.add_argument("--spec", required=True, help="Path to specification file")
    parser.add_argument("--max-iter", type=int, default=DEFAULT_MAX_ITER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["gemini", "openai", "anthropic"])
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--skip-decomp", action="store_true", help="Skip spec decomposition")
    parser.add_argument("--make-target", default=DEFAULT_MAKE_TARGET, help="Make targets for iteration")
    parser.add_argument("--make-full", action="store_true", help="Run full 'make all' on final pass")
    parser.add_argument("--rtl-dir", default="rtl")
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  LLM Verilog Generation — Negative Feedback Loop")
    print(f"  Model: {args.model}  |  Provider: {args.provider}")
    print(f"  Max iterations: {args.max_iter}  |  Temperature: {args.temperature}")
    print("=" * 60)

    # stage 1: load spec
    spec = load_spec(args.spec)
    print(f"\n[SPEC] Loaded specification ({len(spec)} chars)")

    # stage 2: spec decomposition (optional)
    decomposition = None
    if not args.skip_decomp:
        print("[DECOMP] Decomposing specification...")
        decomposition = decompose_spec(spec, args.model, args.provider, args.temperature)
        if decomposition:
            n_tasks = len(decomposition.get("subtasks", []))
            n_signals = len(decomposition.get("signals", []))
            print(f"[DECOMP] Extracted {n_tasks} subtasks, {n_signals} signals")
            if args.verbose:
                print(json.dumps(decomposition, indent=2))
        else:
            print("[DECOMP] Skipped (decomposition failed)")

    # stage 3: initial code generation
    print("\n[GEN] Generating initial Verilog code...")
    code = generate_code(spec, decomposition, args.model, args.provider, args.temperature)
    if args.verbose:
        print("--- Generated Code ---")
        print(code)
        print("--- End Code ---")

    rtl_path = write_rtl(code, args.rtl_dir)

    # stages 4-7: feedback loop
    for iteration in range(1, args.max_iter + 1):
        print(f"\n{'─' * 60}")
        print(f"  ITERATION {iteration}/{args.max_iter}")
        print(f"{'─' * 60}")

        # stage 4: run make pipeline
        print(f"[MAKE] Running: make {args.make_target}")
        t0 = time.time()
        success, rc = run_make(args.make_target, args.out_dir)
        elapsed = time.time() - t0
        print(f"[MAKE] Completed in {elapsed:.1f}s  (exit code {rc})")

        # run report to generate feedback.json
        subprocess.run(
            ["python3", "scripts/report.py", args.out_dir],
            capture_output=not args.verbose,
        )

        # stage 5: load and check feedback
        feedback = load_feedback(args.out_dir)
        if feedback is None:
            print("[WARN] No feedback.json found — assuming failure")
            feedback = {"overall_status": "FAIL", "failed_stage": "unknown", "all_issues": []}

        if feedback["overall_status"] == "PASS":
            print(f"\n\033[92m[SUCCESS] All checks passed on iteration {iteration}!\033[0m")

            # optionally run full make all for timing/power
            if args.make_full and args.make_target != "all":
                print("[MAKE] Running full pipeline for timing/power analysis...")
                run_make("all", args.out_dir)
                subprocess.run(["python3", "scripts/report.py", args.out_dir])

            _save_history(args.out_dir, iteration, "PASS", code)
            return 0

        # stage 6: build feedback prompt
        current_code = read_current_rtl(args.rtl_dir)
        prompt = build_feedback_prompt(spec, current_code, feedback)
        if args.verbose:
            print("--- Feedback Prompt ---")
            print(prompt[:2000])
            print("--- End Prompt ---")

        # stage 7: regenerate code
        print(f"[FIX] Requesting correction from {args.model}...")
        messages = [
            {"role": "system", "content": DEBUG_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        raw_response = call_llm(messages, args.model, args.provider, args.temperature)
        code = _extract_verilog(raw_response)

        if args.verbose:
            print("--- Corrected Code ---")
            print(code)
            print("--- End Code ---")

        rtl_path = write_rtl(code, args.rtl_dir)

    # max iterations reached
    print(f"\n\033[93m[MAX ITER] Reached {args.max_iter} iterations without passing.\033[0m")
    print(f"[MAX ITER] Best attempt is in {args.rtl_dir}/")
    print(f"[MAX ITER] Error log at {args.out_dir}/feedback.json")
    _save_history(args.out_dir, args.max_iter, "MAX_ITER", code)
    return 1


def _save_history(out_dir, iteration, outcome, final_code):
    """Save a summary of the loop run for later analysis."""
    history_path = os.path.join(out_dir, "loop_history.json")
    history = {
        "iterations": iteration,
        "outcome": outcome,
        "final_code_length": len(final_code),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"[HISTORY] Saved to {history_path}")


if __name__ == "__main__":
    sys.exit(main())