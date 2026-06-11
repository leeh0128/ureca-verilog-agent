#!/usr/bin/env python3
# Batch evaluation harness for VerilogEval v2
import argparse, json, os, shutil, subprocess, time
from pathlib import Path

VEVAL = Path("/foss/designs/URECA/verilog-eval/dataset_spec-to-rtl")
WORK  = Path("/foss/designs/URECA/ureca_designs")
RESULTS = WORK / "batch_results"

def run_one_problem(prob_dir, model, max_iters):
    name = prob_dir.name
    # 1. Reset workspace
    shutil.rmtree(WORK / "rtl", ignore_errors=True)
    shutil.rmtree(WORK / "tb", ignore_errors=True)
    (WORK / "rtl").mkdir()
    (WORK / "tb").mkdir()
    
    # 2. Copy spec + testbench from VerilogEval
    spec_file = prob_dir / f"{name}_prompt.txt"
    tb_file   = prob_dir / f"{name}_test.sv"
    if not spec_file.exists() or not tb_file.exists():
        return {"name": name, "status": "SKIP", "reason": "missing files"}
    
    shutil.copy(spec_file, WORK / "spec.txt")
    shutil.copy(tb_file, WORK / "tb" / "TopModule_tb.sv")
    
    # 3. Run agent with timeout
    t0 = time.time()
    try:
        result = subprocess.run(
            ["python3", "scripts/agent.py", "spec.txt",
             "--model", model, "--max-iters", str(max_iters)],
            cwd=WORK, capture_output=True, text=True, timeout=600
        )
        elapsed = time.time() - t0
        
        # 4. Check if make all passed
        passed = subprocess.run(
            ["make", "check"], cwd=WORK,
            capture_output=True, text=True, timeout=120
        ).returncode == 0
        
        return {
            "name": name, "model": model,
            "status": "PASS" if passed else "FAIL",
            "time": elapsed,
            "iterations": result.stdout.count("Iteration"),
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "TIMEOUT", "time": 600}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--max-iters", type=int, default=5)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=156)
    args = ap.parse_args()
    
    RESULTS.mkdir(exist_ok=True)
    out_file = RESULTS / f"results_{args.model.replace('/','_')}.jsonl"
    
    problems = sorted(VEVAL.iterdir())[args.start:args.end]
    for i, prob in enumerate(problems):
        print(f"[{i+1}/{len(problems)}] {prob.name}")
        result = run_one_problem(prob, args.model, args.max_iters)
        with open(out_file, "a") as f:
            f.write(json.dumps(result) + "\n")
        print(f"  → {result['status']}")

if __name__ == "__main__":
    main()