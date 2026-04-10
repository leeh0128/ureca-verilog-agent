"""
Instead of a rigid loop, the LLM receives tools and decides its own
course of action to generate correct Verilog from a specification.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import textwrap

#  config

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_STEPS = 30        # safety cap on total LLM calls
DEFAULT_TEMPERATURE = 0.0

#  tools  —  what the agent can do

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Use this to read specs, RTL source, testbenches, logs, or feedback.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read, relative to project root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Use this to create or overwrite Verilog RTL files in the rtl/ directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write, relative to project root. Usually rtl/<module_name>.v"
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete file content to write."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_make",
            "description": "Run a make target. Available targets: 'clean', 'lint', 'sim', 'lint sim', 'synth', 'all'. Use 'lint sim' for fast iteration. Use 'all' for full flow including synthesis, STA, and power.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "The make target(s) to run, e.g. 'clean', 'lint sim', 'all'."
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_report",
            "description": "Run the error classification report. This parses all logs in out/ and generates out/feedback.json with structured error categories. Always run this after run_make to get classified results.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory. Use this to see what RTL files, testbenches, or logs exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path relative to project root, e.g. 'rtl', 'tb', 'out'."
                    }
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that you are finished. Call this when the design passes all checks, or when you've exhausted your approaches and want to hand off to a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PASS", "FAIL", "NEEDS_HUMAN"],
                        "description": "Final status: PASS if all checks passed, FAIL if you couldn't fix it, NEEDS_HUMAN if it needs manual review."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of what you did and the final state."
                    }
                },
                "required": ["status", "summary"]
            }
        }
    },
]

#  tool calls  —  execute what the agent requests

def exec_read_file(path):
    # read a file and return its contents.
    if not os.path.exists(path):
        return f"[ERROR] File not found: {path}"
    try:
        with open(path, "r") as f:
            content = f.read()
        # truncate very large files to avoid blowing up context
        if len(content) > 8000:
            return content[:4000] + f"\n\n... [TRUNCATED — {len(content)} chars total] ...\n\n" + content[-2000:]
        return content
    except Exception as e:
        return f"[ERROR] Could not read {path}: {e}"


WRITABLE_DIRS = {"rtl"}  # only allow writes into these directories

def exec_write_file(path, content):
    # write content to a file. only allows writes inside rtl/.
    # resolve to absolute path and check for directory traversal
    abs_path = os.path.abspath(path)
    project_root = os.path.abspath(".")

    # ensure the resolved path is within the project root
    if not abs_path.startswith(project_root + os.sep):
        return f"[BLOCKED] Path escapes project root: {path}"

    # check the path starts with an allowed directory
    rel_path = os.path.relpath(abs_path, project_root)
    top_dir = rel_path.split(os.sep)[0]
    if top_dir not in WRITABLE_DIRS:
        return (
            f"[BLOCKED] Writes are only allowed in: {', '.join(sorted(WRITABLE_DIRS))}. "
            f"You tried to write to '{path}' (resolved top dir: '{top_dir}'). "
            f"Use a path like rtl/<module_name>.v instead."
        )

    try:
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)
        lines = content.count("\n") + 1
        return f"[OK] Wrote {len(content)} chars ({lines} lines) to {path}"
    except Exception as e:
        return f"[ERROR] Could not write {path}: {e}"


def exec_run_make(target):
    # run a make target and return stdout+stderr.
    # clean first if requested
    try:
        if "clean" in target:
            subprocess.run(["make", "clean"], capture_output=True, timeout=30)
            if target.strip() == "clean":
                return "[OK] make clean completed."
            # remove 'clean' from target for the next run
            target = target.replace("clean", "").strip()
            if not target:
                return "[OK] make clean completed."

        result = subprocess.run(
            ["make"] + target.split(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr

        # truncate if too long
        if len(output) > 6000:
            output = output[:3000] + "\n\n... [TRUNCATED] ...\n\n" + output[-2000:]

        status = "SUCCESS" if result.returncode == 0 else f"FAILED (exit code {result.returncode})"
        return f"[make {target}] {status}\n{output}"
    except subprocess.TimeoutExpired:
        return f"[make {target}] TIMEOUT after 300s"
    except Exception as e:
        return f"[make {target}] ERROR: {e}"


def exec_run_report():
    """Run report.py and return the contents of feedback.json."""
    try:
        result = subprocess.run(
            ["python3", "scripts/report.py", "out", "reports"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # read and return the feedback JSON
        feedback_path = "out/feedback.json"
        if os.path.exists(feedback_path):
            with open(feedback_path, "r") as f:
                feedback = json.load(f)
            # return a compact version
            return json.dumps(feedback, indent=2)
        else:
            return f"[WARN] report.py ran but no feedback.json found.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    except Exception as e:
        return f"[ERROR] Could not run report: {e}"


def exec_list_files(directory):
    """List files in a directory."""
    if not os.path.isdir(directory):
        return f"[ERROR] Directory not found: {directory}"
    try:
        entries = sorted(os.listdir(directory))
        if not entries:
            return f"[{directory}/] (empty)"
        return f"[{directory}/]\n" + "\n".join(f"  {e}" for e in entries)
    except Exception as e:
        return f"[ERROR] Could not list {directory}: {e}"


def execute_tool(name, arguments):
    """Dispatch a tool call to the appropriate implementation."""
    if name == "read_file":
        return exec_read_file(arguments["path"])
    elif name == "write_file":
        return exec_write_file(arguments["path"], arguments["content"])
    elif name == "run_make":
        return exec_run_make(arguments["target"])
    elif name == "run_report":
        return exec_run_report()
    elif name == "list_files":
        return exec_list_files(arguments["directory"])
    elif name == "done":
        return None  # Handled by the main loop
    else:
        return f"[ERROR] Unknown tool: {name}"


#  LLM client  —  Gemini via OpenAI-compatible API with tool calling

def call_llm_with_tools(messages, model, temperature=0.0):
    # call Gemini with tool definitions. Returns the raw response object so we can inspect tool_calls.
    
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
        tools=TOOLS_SCHEMA,
        temperature=temperature,
        max_tokens=8192,
    )
    return resp


#  system prompt  —  the agent's identity and instructions

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an autonomous Verilog RTL design agent. Your job is to generate
    functionally correct, synthesizable Verilog code from a natural language
    specification, and verify it using the provided EDA toolchain.

    You have full autonomy to decide your approach. You have access to tools
    for reading/writing files, running the build system, and analyzing results.

    ## Available Tools
    - read_file: Read any file (specs, RTL, testbenches, logs, feedback.json)
    - write_file: Create or overwrite files (put Verilog in rtl/*.v)
    - run_make: Run make targets (clean, lint, sim, synth, all, or combinations like "lint sim")
    - run_report: Generate out/feedback.json with classified error analysis
    - list_files: See what files exist in a directory
    - done: Signal completion with final status

    ## Project Structure
    - rtl/        : Your generated Verilog goes here
    - tb/         : Testbenches (read-only — do NOT modify)
    - out/        : Build artifacts and logs (lint.log, sim.log, yosys.log, feedback.json)
    - reports/    : Timing and power reports
    - scripts/    : Build scripts (read-only)
    - Makefile    : Build system

    ## Workflow Guidelines
    1. First, read the spec file to understand what needs to be built.
    2. Optionally, check tb/ to understand how your design will be tested.
    3. Write your Verilog to rtl/<ModuleName>.v
    4. Run "make clean" then "make lint sim" for fast verification.
    5. Run run_report to get structured error feedback in out/feedback.json.
    6. Read feedback.json to understand what went wrong.
    7. Fix the issues and repeat from step 4.
    8. When all checks pass, optionally run "make all" for full PPA analysis.
    9. Call done() with your final status.

    ## Verilog Coding Rules
    - Declare all ports as 'logic'
    - Use 'always @(posedge clk)' for sequential logic
    - Use 'assign' or 'always @(*)' for combinational logic
    - Always include 'endmodule' with a newline after it
    - Use 'localparam' for constants, not 'typedef enum'
    - Do NOT include testbench code, $display, or $finish in RTL

    ## Important
    - Do NOT modify files in tb/ — testbenches are fixed.
    - Read error messages carefully before making changes.
    - If lint warnings mention width mismatches or inferred latches, treat them seriously.
    - If simulation fails, check which output signals mismatch and at what time.
    - You have up to {max_steps} tool calls. Use them wisely.
""")

#  context management  —  keep conversation history from growing unbounded

# keep this many recent message exchanges in full detail.
# older tool results get compressed to a one-line summary.
CONTEXT_KEEP_RECENT = 8  # number of recent messages to keep verbatim


def compress_context(messages):
    """
    Compress older tool results to prevent context window bloat.

    Strategy: Keep the system prompt and user prompt intact. Keep the most
    recent CONTEXT_KEEP_RECENT messages in full. For older messages, replace
    long tool results with a short summary.
    """
    if len(messages) <= CONTEXT_KEEP_RECENT + 2:
        # +2 for system + initial user message — nothing to compress
        return messages

    # messages to always keep fully: system (index 0) and user (index 1)
    preserved_head = messages[:2]
    compressible = messages[2:-CONTEXT_KEEP_RECENT]
    recent_tail = messages[-CONTEXT_KEEP_RECENT:]

    compressed = []
    for msg in compressible:
        # compress tool result messages that are long
        if isinstance(msg, dict) and msg.get("role") == "tool":
            content = msg.get("content", "")
            if len(content) > 300:
                # keep first 150 chars as summary
                summary = content[:150].replace("\n", " ").strip()
                compressed.append({
                    "role": msg["role"],
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": f"[COMPRESSED] {summary}...",
                })
            else:
                compressed.append(msg)
        # compress assistant text messages that are long
        elif isinstance(msg, dict) and msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
            content = msg["content"]
            if len(content) > 300:
                compressed.append({
                    "role": "assistant",
                    "content": f"[Earlier reasoning compressed] {content[:150]}...",
                })
            else:
                compressed.append(msg)
        else:
            # keep assistant messages with tool_calls, etc. as-is
            compressed.append(msg)

    return preserved_head + compressed + recent_tail


#  agent loop  —  the core autonomous execution engine

def run_agent(spec_path, model, temperature, max_steps, verbose):
    # run the autonomous agent. The agent decides all actions. Returns (status, summary, step_count).
    # build the initial message
    system = SYSTEM_PROMPT.replace("{max_steps}", str(max_steps))

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"Generate correct Verilog RTL for the specification in '{spec_path}'. "
            f"Verify it passes lint and simulation using the Makefile toolchain. "
            f"Fix any errors autonomously. When everything passes, run the full "
            f"'make all' for synthesis and timing analysis, then call done()."
        )},
    ]

    # tracking
    step = 0
    history = []  # list of {step, tool, args_summary, result_summary}
    _last_call_time = 0.0  # for rate limit throttling

    print(f"\n{'═' * 60}")
    print(f"  AGENT STARTED  |  Model: {model}  |  Max steps: {max_steps}")
    print(f"{'═' * 60}\n")

    while step < max_steps:
        step += 1
        t0 = time.time()

        if verbose:
            print(f"\n{'─' * 60}")
            print(f"  STEP {step}/{max_steps}  —  Calling LLM...")
            print(f"{'─' * 60}")

        # compress old context to stay within token limits
        messages = compress_context(messages)

        # rate limit throttle: Gemini free tier = 5 req/min
        # ensure at least 13s between calls (safe for 5/min limit)
        if step > 1:
            elapsed_since_last = time.time() - _last_call_time
            min_gap = 13.0  # seconds between calls (5 req/min = 12s, +1s buffer)
            if elapsed_since_last < min_gap:
                wait = min_gap - elapsed_since_last
                print(f"  [RATE] Waiting {wait:.0f}s (free tier throttle)...")
                time.sleep(wait)

        # call the LLM with retry on rate limit errors
        response = None
        for attempt in range(3):
            try:
                response = call_llm_with_tools(messages, model, temperature)
                _last_call_time = time.time()
                break
            except Exception as e:
                err_str = str(e)
                # extract retryDelay from error if present
                delay_match = re.search(r'retryDelay.*?(\d+)', err_str)
                if '429' in err_str and delay_match:
                    wait_secs = int(delay_match.group(1)) + 5  # add buffer
                    print(f"  [RATE] Rate limited. Waiting {wait_secs}s (attempt {attempt+1}/3)...")
                    time.sleep(wait_secs)
                elif '429' in err_str:
                    wait_secs = 30 * (attempt + 1)
                    print(f"  [RATE] Rate limited. Waiting {wait_secs}s (attempt {attempt+1}/3)...")
                    time.sleep(wait_secs)
                else:
                    print(f"  [ERR] LLM call failed: {e}")
                    if attempt == 2:
                        return "FAIL", f"LLM API error: {e}", step
                    time.sleep(5)

        if response is None:
            return "FAIL", "LLM API failed after 3 retries.", step

        elapsed = time.time() - t0
        choice = response.choices[0]
        msg = choice.message

        # case 1: the LLM wants to call tool(s)
        if msg.tool_calls:
            # add the assistant message (with tool calls) to history
            messages.append(msg)

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError as je:
                    # feed the error back to the LLM so it can fix its syntax
                    error_msg = (
                        f"[TOOL CALL ERROR] Your tool call '{tool_name}' had invalid JSON arguments.\n"
                        f"Raw arguments: {tc.function.arguments[:500]}\n"
                        f"JSON error: {je}\n"
                        f"Please retry the tool call with valid JSON."
                    )
                    print(f"  [{step}] ⚠️  Bad JSON for {tool_name}: {je}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": error_msg,
                    })
                    history.append({
                        "step": step,
                        "tool": f"{tool_name}_JSON_ERROR",
                        "args": str(je),
                        "result_len": len(error_msg),
                    })
                    continue  # skip to next tool call or next LLM turn

                # pretty print
                args_display = _summarize_args(tool_name, tool_args)
                print(f"  [{step}] 🔧 {tool_name}({args_display})  [{elapsed:.1f}s]")

                # check for done() call
                if tool_name == "done":
                    status = tool_args.get("status", "PASS")
                    summary = tool_args.get("summary", "Agent finished.")
                    print(f"\n  [{step}] ✅ Agent called done(status={status})")
                    print(f"  Summary: {summary}")
                    _save_history(history, step, status, summary)
                    return status, summary, step

                # execute the tool
                result = execute_tool(tool_name, tool_args)

                if verbose and result:
                    # print truncated result
                    display = result[:500] + "..." if len(result) > 500 else result
                    print(f"  Result: {display}")

                # track
                history.append({
                    "step": step,
                    "tool": tool_name,
                    "args": args_display,
                    "result_len": len(result) if result else 0,
                })

                # add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result or "",
                })

        # case 2: the LLM just sent text (thinking out loud)
        elif msg.content:
            messages.append({"role": "assistant", "content": msg.content})
            if verbose:
                display = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
                print(f"  [{step}] 💭 Agent thinking: {display}")

        # case 3: empty response (shouldn't happen but handle gracefully)
        else:
            print(f"  [{step}] ⚠️  Empty response from LLM")
            messages.append({"role": "assistant", "content": "I need to continue working."})

    # max steps reached
    print(f"\n  ⚠️  Max steps ({max_steps}) reached without done() call.")
    _save_history(history, step, "MAX_STEPS", "Agent did not complete within step limit.")
    return "MAX_STEPS", "Reached maximum step limit.", step


def _summarize_args(tool_name, args):
    # create a short display string for tool arguments.
    if tool_name == "read_file":
        return args.get("path", "?")
    elif tool_name == "write_file":
        path = args.get("path", "?")
        content = args.get("content", "")
        return f"{path}, {len(content)} chars"
    elif tool_name == "run_make":
        return args.get("target", "?")
    elif tool_name == "list_files":
        return args.get("directory", "?")
    elif tool_name == "done":
        return f"status={args.get('status', '?')}"
    else:
        return str(args)[:80]


def _save_history(history, total_steps, status, summary):
    # save the agent's action history for analysis.
    record = {
        "total_steps": total_steps,
        "status": status,
        "summary": summary,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "actions": history,
    }
    path = "out/agent_history.json"
    os.makedirs("out", exist_ok=True)
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    print(f"  [HISTORY] Saved to {path}")


#  entry point

def main():
    parser = argparse.ArgumentParser(
        description="Agentic Verilog generation — the LLM decides the workflow"
    )
    parser.add_argument("--spec", required=True, help="Path to specification file")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS,
                        help=f"Max tool calls before stopping (default: {DEFAULT_MAX_STEPS})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"LLM model (default: {DEFAULT_MODEL})")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--verbose", action="store_true",
                        help="Print all tool results and agent reasoning")
    args = parser.parse_args()

    # validate
    if not os.path.exists(args.spec):
        sys.exit(f"[ERR] Spec file not found: {args.spec}")
    if not os.path.exists("Makefile"):
        sys.exit("[ERR] No Makefile found. Run this from your project root.")

    status, summary, steps = run_agent(
        spec_path=args.spec,
        model=args.model,
        temperature=args.temperature,
        max_steps=args.max_steps,
        verbose=args.verbose,
    )

    # final output
    print(f"\n{'═' * 60}")
    if status == "PASS":
        print(f"  \033[92m✅ AGENT FINISHED: {status}\033[0m  ({steps} steps)")
    else:
        print(f"  \033[93m⚠️  AGENT FINISHED: {status}\033[0m  ({steps} steps)")
    print(f"  {summary}")
    print(f"{'═' * 60}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())