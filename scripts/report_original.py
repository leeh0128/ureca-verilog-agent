import sys, re, os

def parse_metrics(out_dir):
    metrics = {
        "Status": "FAIL", 
        "Cell Count": "0", 
        "Area (um^2)": "0", 
        "Slack (ns)": "N/A", 
        "Power (W)": "N/A"
    }
    
    if os.path.exists(f"{out_dir}/sim.log"):
        with open(f"{out_dir}/sim.log") as f:
            if "PASS" in f.read(): metrics["Status"] = "PASS"

    try:
        with open(f"{out_dir}/yosys.log", 'r') as f:
            content = f.read()
            
            # Strategy A: Look for the specific Hierarchy Table line "256 6.32E+03 cells"
            # We look for lines ending in 'cells' and take the largest cell count found (the total)
            table_matches = re.findall(r'^\s+(\d+)\s+[\d\.E\+\-]+\s+cells', content, re.MULTILINE)
            if table_matches:
                # The last match in the hierarchy table is usually the total
                metrics["Cell Count"] = table_matches[-1]
            else:
                # Strategy B: Fallback to old format
                legacy_match = re.search(r'Number of cells:\s+(\d+)', content)
                if legacy_match: metrics["Cell Count"] = legacy_match.group(1)

            # Area Parsing: Handle "top module" and scientific notation
            area_match = re.search(r'Chip area for (?:top )?module.*:\s+([\d\.]+)', content)
            #area_match = re.search(r'Chip area for top module.*:\s+([\d\.]+)', content)
            if area_match: 
                metrics["Area (um^2)"] = area_match.group(1)
    except: pass

    try:
        with open(f"reports/timing/wns.rpt", 'r') as f:
            metrics["Slack (ns)"] = f.read().strip()
    except: pass

    try:
        with open(f"reports/power/power.rpt", 'r') as f:
            for line in f:
                # Matches: Total 1.23e-05 ... or Total      1.23 ...
                if line.strip().startswith("Total"):
                    vals = re.findall(r'([\d\.eE\+\-]+)', line)
                    if vals and len(vals) >= 2: 
                        metrics["Power (W)"] = vals[-2]
                        break
    except: pass

    return metrics

if __name__ == "__main__":
    m = parse_metrics(sys.argv[1])
    print("-" * 40)
    for k, v in m.items():
        print(f"{k:<20} | {v}")
    print("-" * 40)