import json, re, sys, os

def parse():
    top = sys.argv[1]
    out_dir = sys.argv[2]
    
    # define file paths
    wns_file = 'reports/timing/wns.rpt'
    pwr_file = 'reports/power/power.rpt'
    area_file = f'{out_dir}/area.rpt'
    
    try:
        wns_text = open(wns_file).read()
        pwr_text = open(pwr_file).read()
        area_text = open(area_file).read()
    except FileNotFoundError as e:
        print(json.dumps({"error": f"Missing report file: {e.filename}"}))
        return

    #1. regex for area (looks for the specific module's area)
    area_match = re.search(fr"Chip area for module '\\{top}':\s+([\d.]+)", area_text)
    area = area_match.group(1) if area_match else '0.0'

    #2. regex for worst timing slack
    wns_match = re.search(r'worst slack\s+([-+]?\d*\.\d+|\d+)', wns_text)
    wns = wns_match.group(1) if wns_match else '0.0'

    #3. logic behind power extraction
    #find the row that starts with 'Total' and has the watts unit pattern
    pwr_val = '0.0'
    for line in pwr_text.split('\n'):
        if line.strip().startswith('Total'):
            parts = line.split()
            if len(parts) >= 2:
                candidate = parts[-2]
                if 'NaN' not in candidate:
                    pwr_val = candidate
                    break

    #4. extracting cell count for LLM feedback
    cell_match = re.search(r'(\d+)\s+[\d.]+\s+cells', area_text)
    cell_count = cell_match.group(1) if cell_match else '0'

    data = {
        'top': top,
        'wns_ns': wns,
        'total_pwr_w': pwr_val,
        'area_um2': area,
        'cell_count': cell_count,
        'status': 'PASS' if float(wns) >= 0 else 'FAIL_TIMING'
    }
    
    output_path = f'{out_dir}/summary.json'
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=4)
    
    print(f"[SUCCESS] Metrics compiled for {top}")

if __name__ == "__main__":
    parse()
