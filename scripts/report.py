"""
report.py  —  Enhanced report generator with structured error classification.

Produces both human-readable console output AND a machine-readable JSON
report at <out_dir>/feedback.json for the LLM feedback loop.
"""

import sys
import re
import os
import json


#  Lint log parser  —  Verilator -Wall output

_VERILATOR_TAG_MAP = {
    "WIDTHEXPAND":    "width_mismatch",
    "WIDTHTRUNC":     "width_mismatch",
    "WIDTHCONCAT":    "width_mismatch",
    "WIDTH":          "width_mismatch",
    "LATCH":          "inferred_latch",
    "COMBDLY":        "comb_loop",
    "UNDRIVEN":       "undriven_signal",
    "UNUSEDSIGNAL":   "unused_signal",
    "UNUSEDPARAM":    "unused_signal",
    "UNUSEDGENVAR":   "unused_signal",
    "IMPLICIT":       "implicit_wire",
    "PINMISSING":     "missing_module",
    "CASEX":          "general_lint",
    "CASEINCOMPLETE": "general_lint",
    "SYNCASYNCNET":   "general_lint",
    "BLKSEQ":         "general_lint",
    "MULTIDRIVEN":    "general_lint",
}


def parse_lint_log(log_path):
    """
    Parse Verilator lint output into structured warnings and errors.
    Returns (has_errors: bool, items: list[dict])
    """
    items = []
    if not os.path.exists(log_path):
        return False, items

    with open(log_path, "r") as f:
        content = f.read()

    # Verilator format:  %Warning-TAG: file:line:col: message
    #                    %Error: file:line:col: message
    pattern = re.compile(
        r"%(Warning|Error)(?:-(\w+))?:\s*([^:]+):(\d+):\d+:\s*(.*)"
    )

    has_errors = False
    for m in pattern.finditer(content):
        severity = m.group(1).lower()
        tag = m.group(2) or "GENERAL"
        filepath = m.group(3).strip()
        line_no = int(m.group(4))
        message = m.group(5).strip()

        if severity == "error":
            has_errors = True

        category = _VERILATOR_TAG_MAP.get(tag, "general_lint")

        items.append({
            "category": category,
            "tag": tag,
            "file": filepath,
            "line": line_no,
            "message": message,
            "severity": severity,
        })

    return has_errors, items


#  simulation log parser — iverilog / vvp output

def parse_sim_log(log_path):
    """
    Parse simulation log for pass/fail and mismatch details.
    Returns dict with keys: passed, mismatches, raw_snippet, error_type
    """
    result = {
        "passed": False,
        "mismatches": [],
        "raw_snippet": "",
        "error_type": None,
    }
    if not os.path.exists(log_path):
        result["error_type"] = "no_sim_log"
        return result

    with open(log_path, "r") as f:
        content = f.read()

    result["raw_snippet"] = content[-2000:]

    if "PASS" in content:
        result["passed"] = True
        return result

    # timeout
    if re.search(r"(?i)timeout|simulation did not finish", content):
        result["error_type"] = "timeout"
        return result

    # reset issues
    if re.search(r"(?i)reset.*mismatch|mismatch.*reset|time\s+0.*mismatch", content):
        result["error_type"] = "reset_issue"

    # per-signal mismatch hints
    mismatch_pat = re.compile(
        r"(?:Hint:\s*)?Output\s+'(\w+)'\s+has\s+(\d+)\s+mismatches?"
        r"(?:\.\s*First\s+mismatch\s+(?:occurred\s+)?at\s+time\s+(\d+))?"
    )
    for m in mismatch_pat.finditer(content):
        result["mismatches"].append({
            "signal": m.group(1),
            "count": int(m.group(2)),
            "first_time": int(m.group(3)) if m.group(3) else None,
        })

    # total mismatches
    total_match = re.search(
        r"Mismatches:\s+(\d+)\s+in\s+(\d+)\s+samples", content
    )
    if total_match:
        result["total_mismatches"] = int(total_match.group(1))
        result["total_samples"] = int(total_match.group(2))

    if not result["error_type"] and result["mismatches"]:
        result["error_type"] = "output_mismatch"
    elif not result["error_type"]:
        result["error_type"] = "general_runtime"

    return result


#  compilation error parser — iverilog stderr

def parse_compile_errors(log_path):
    """
    Parse iverilog compilation output for errors.
    Returns (has_errors: bool, items: list[dict])
    """
    items = []
    if not os.path.exists(log_path):
        return False, items

    with open(log_path, "r") as f:
        content = f.read()

    has_errors = False

    err_pattern = re.compile(
        r"([^:\s]+):(\d+):\s*(error|syntax error)[:\s]*(.*)", re.IGNORECASE
    )
    for m in err_pattern.finditer(content):
        has_errors = True
        filepath = m.group(1).strip()
        line_no = int(m.group(2))
        err_type = m.group(3).lower()
        message = m.group(4).strip()

        # sub-classify
        category = "syntax_error"
        if re.search(r"Unable to bind wire/reg.*clk", message, re.IGNORECASE):
            category = "clock_bind"
        elif re.search(r"Unable to bind wire/reg", message, re.IGNORECASE):
            category = "missing_module"
        elif re.search(r"reg.*wire|wire.*reg|declared.*input.*reg", message, re.IGNORECASE):
            category = "reg_as_wire"
        elif re.search(r"not a valid l-value|target.*assign", message, re.IGNORECASE):
            category = "reg_as_wire"
        elif re.search(r"[Mm]odule.*not found|Unknown module", message, re.IGNORECASE):
            category = "missing_module"
        elif re.search(r"sensitivity", message, re.IGNORECASE):
            category = "sensitivity"

        items.append({
            "category": category,
            "file": filepath,
            "line": line_no,
            "message": f"{err_type}: {message}" if message else err_type,
            "severity": "error",
        })

    return has_errors, items


#  synthesis log parser  —  Yosys output

def parse_synth_log(log_path):
    """Parse Yosys synthesis log for errors and design metrics."""
    metrics = {"cell_count": "0", "area": "0"}
    errors = []

    if not os.path.exists(log_path):
        return metrics, errors

    with open(log_path, "r") as f:
        content = f.read()

    for m in re.finditer(r"ERROR:\s*(.*)", content):
        errors.append({"category": "general_synth", "message": m.group(1).strip()})

    table_matches = re.findall(
        r"^\s+(\d+)\s+[\d\.E\+\-]+\s+cells", content, re.MULTILINE
    )
    if table_matches:
        metrics["cell_count"] = table_matches[-1]
    else:
        legacy = re.search(r"Number of cells:\s+(\d+)", content)
        if legacy:
            metrics["cell_count"] = legacy.group(1)

    area_match = re.search(
        r"Chip area for (?:top )?module.*:\s+([\d\.]+)", content
    )
    if area_match:
        metrics["area"] = area_match.group(1)

    return metrics, errors


#  timing and power parsers

def parse_timing(rpt_dir):
    wns_path = os.path.join(rpt_dir, "timing", "wns.rpt")
    if not os.path.exists(wns_path):
        return "N/A"
    with open(wns_path, "r") as f:
        return f.read().strip() or "N/A"


def parse_power(rpt_dir):
    pwr_path = os.path.join(rpt_dir, "power", "power.rpt")
    if not os.path.exists(pwr_path):
        return "N/A"
    with open(pwr_path, "r") as f:
        for line in f:
            if line.strip().startswith("Total"):
                vals = re.findall(r"([\d\.eE\+\-]+)", line)
                if vals and len(vals) >= 2:
                    return vals[-2]
    return "N/A"


#  master report builder

def build_report(out_dir, rpt_dir="reports"):
    """
    Build the full structured report from all pipeline stage outputs.
    Returns a dict that is both printed and saved as JSON.
    """
    report = {
        "overall_status": "PASS",
        "failed_stage": None,
        "lint": {"passed": True, "errors": [], "warnings": []},
        "compile": {"passed": True, "errors": []},
        "simulation": {"passed": False, "details": {}},
        "synthesis": {"metrics": {}, "errors": []},
        "timing": {"slack": "N/A"},
        "power": {"total": "N/A"},
        "all_issues": [],
    }

    # lint
    lint_has_errors, lint_items = parse_lint_log(os.path.join(out_dir, "lint.log"))
    lint_warnings = [i for i in lint_items if i["severity"] == "warning"]
    lint_errors = [i for i in lint_items if i["severity"] == "error"]

    report["lint"]["warnings"] = lint_warnings
    report["lint"]["errors"] = lint_errors
    report["lint"]["passed"] = not lint_has_errors

    if lint_has_errors:
        report["overall_status"] = "FAIL"
        report["failed_stage"] = "lint"
        report["all_issues"].extend(lint_errors)
    # always include warnings for feedback even if lint passed
    report["all_issues"].extend(lint_warnings)

    # compilation
    compile_has_errors, compile_items = parse_compile_errors(
        os.path.join(out_dir, "sim.log")
    )
    report["compile"]["errors"] = compile_items
    report["compile"]["passed"] = not compile_has_errors

    if compile_has_errors:
        report["overall_status"] = "FAIL"
        if not report["failed_stage"]:
            report["failed_stage"] = "compile"
        report["all_issues"].extend(compile_items)

    # simulation
    sim_result = parse_sim_log(os.path.join(out_dir, "sim.log"))
    report["simulation"]["passed"] = sim_result["passed"]
    report["simulation"]["details"] = sim_result

    if not sim_result["passed"] and report["compile"]["passed"]:
        report["overall_status"] = "FAIL"
        if not report["failed_stage"]:
            report["failed_stage"] = "simulation"
        report["all_issues"].append({
            "category": sim_result.get("error_type", "general_runtime"),
            "message": _summarize_sim_failure(sim_result),
            "severity": "error",
        })

    # synthesis
    synth_metrics, synth_errors = parse_synth_log(os.path.join(out_dir, "yosys.log"))
    report["synthesis"]["metrics"] = synth_metrics
    report["synthesis"]["errors"] = synth_errors

    if synth_errors:
        report["overall_status"] = "FAIL"
        if not report["failed_stage"]:
            report["failed_stage"] = "synthesis"
        report["all_issues"].extend(synth_errors)

    # timing and power
    report["timing"]["slack"] = parse_timing(rpt_dir)
    report["power"]["total"] = parse_power(rpt_dir)

    return report


def _summarize_sim_failure(sim_result):
    parts = []
    if sim_result.get("error_type") == "timeout":
        return "Simulation timed out — likely an infinite loop in sequential logic."
    if sim_result.get("error_type") == "reset_issue":
        parts.append("Possible reset issue (sync vs async mismatch).")
    for mm in sim_result.get("mismatches", []):
        s = f"Output '{mm['signal']}' has {mm['count']} mismatches"
        if mm.get("first_time") is not None:
            s += f" (first at time {mm['first_time']})"
        parts.append(s)
    total = sim_result.get("total_mismatches")
    samples = sim_result.get("total_samples")
    if total is not None and samples is not None:
        parts.append(f"Total: {total} mismatches in {samples} samples.")
    return " | ".join(parts) if parts else "Simulation failed — 'PASS' not found in output."


#  output console printing

def print_report(report):
    W = 60
    print("=" * W)
    status = report["overall_status"]
    tag = "\033[92mPASS\033[0m" if status == "PASS" else "\033[91mFAIL\033[0m"
    print(f"  Overall Status:  {tag}")
    if report["failed_stage"]:
        print(f"  First Failure:   {report['failed_stage']}")
    print("-" * W)

    # lint
    lw = report["lint"]["warnings"]
    le = report["lint"]["errors"]
    lint_tag = "\033[92mOK\033[0m" if report["lint"]["passed"] else "\033[91mFAIL\033[0m"
    print(f"  Lint:            {lint_tag}  ({len(le)} errors, {len(lw)} warnings)")
    for item in le[:5]:
        print(f"    \033[91m[E]\033[0m {item['file']}:{item['line']} — {item['message']}")
    for item in lw[:10]:
        print(f"    \033[93m[W]\033[0m {item['file']}:{item['line']} — {item['tag']}: {item['message']}")
    if len(lw) > 10:
        print(f"    ... and {len(lw) - 10} more warnings")

    # compilation
    ce = report["compile"]["errors"]
    comp_tag = "\033[92mOK\033[0m" if report["compile"]["passed"] else "\033[91mFAIL\033[0m"
    print(f"  Compile:         {comp_tag}  ({len(ce)} errors)")
    for item in ce[:5]:
        print(f"    \033[91m[E]\033[0m {item['file']}:{item['line']} — {item['message']}")

    # simulation
    sim = report["simulation"]
    if sim["passed"]:
        print(f"  Simulation:      \033[92mPASS\033[0m")
    elif report["compile"]["passed"]:
        print(f"  Simulation:      \033[91mFAIL\033[0m")
        for mm in sim["details"].get("mismatches", [])[:5]:
            print(f"    \033[91m[M]\033[0m Output '{mm['signal']}': {mm['count']} mismatches", end="")
            if mm.get("first_time") is not None:
                print(f" (first @ t={mm['first_time']})", end="")
            print()
    else:
        print(f"  Simulation:      \033[90mSKIPPED (compile failed)\033[0m")

    # synthesis metrics
    sm = report["synthesis"]["metrics"]
    print(f"  Cells:           {sm.get('cell_count', 'N/A')}")
    print(f"  Area (um²):      {sm.get('area', 'N/A')}")
    print(f"  Slack (ns):      {report['timing']['slack']}")
    print(f"  Power (W):       {report['power']['total']}")
    print("=" * W)



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 report.py <out_dir> [reports_dir]")
        sys.exit(1)

    out_dir = sys.argv[1]
    rpt_dir = sys.argv[2] if len(sys.argv) > 2 else "reports"

    report = build_report(out_dir, rpt_dir)
    print_report(report)

    # write LLM-friendly JSON for the feedback loop
    json_path = os.path.join(out_dir, "feedback.json")
    with open(json_path, "w") as f:
        export = json.loads(json.dumps(report))
        if "details" in export.get("simulation", {}):
            export["simulation"]["details"].pop("raw_snippet", None)
        json.dump(export, f, indent=2)
    print(f"\n[REPORT] Structured feedback written to {json_path}")
