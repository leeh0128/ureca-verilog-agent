import sys
import re
import os
import json

# defining constants
VERILOG_KEYWORDS = {
    'always', 'assign', 'case', 'casex', 'casez', 'else', 'end', 'endcase', 
    'endfunction', 'endgenerate', 'endmodule', 'endprimitive', 'endspecify', 
    'endtable', 'endtask', 'for', 'force', 'forever', 'fork', 'function', 
    'generate', 'if', 'initial', 'join', 'macromodule', 'module', 'primitive', 
    'repeat', 'specify', 'table', 'task', 'wait', 'while', 'wire', 'reg', 
    'logic', 'input', 'output', 'inout', 'parameter', 'localparam', 'begin'
}

PRIMITIVES = {
    'and', 'nand', 'or', 'nor', 'xor', 'xnor', 'buf', 'not', 'bufif0', 
    'bufif1', 'notif0', 'notif1', 'pulldown', 'pullup', 'nmos', 'rnmos', 
    'pmos', 'rpmos', 'cmos', 'rcmos', 'tran', 'rtran', 'tranif0', 
    'rtranif0', 'tranif1', 'rtranif1'
}

IGNORE_SET = VERILOG_KEYWORDS | PRIMITIVES

def strip_comments(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'): return " " 
        else: return s
    pattern = re.compile(
        r'//[^\n]*$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.MULTILINE | re.DOTALL
    )
    return re.sub(pattern, replacer, text)

# Regex-based analysis 

def analyze_rtl(rtl_files):
    defined_modules = {}
    instantiated_types = set()
    module_contents = {}

    for fpath in rtl_files:
        if not os.path.exists(fpath): continue
        with open(fpath, 'r') as f:
            raw = f.read()
            clean = strip_comments(raw)

        # 1. definitions 
        definitions = re.finditer(r'(?m)^\s*module\s+(\w+)', clean)
        for match in definitions:
            mname = match.group(1)
            defined_modules[mname] = fpath
            module_contents[mname] = clean

        # 2. instantiations
        # Constraint: Parameters #(...) must be on the same line to avoid runaway matching.
        candidates = re.finditer(r'(?m)^\s*(\w+)\s*(?:#\s*\([^;\n]*\)\s*)?(\w+)\s*\(', clean)
        
        for c in candidates:
            mtype = c.group(1)
            if mtype not in IGNORE_SET:
                instantiated_types.add(mtype)

    return defined_modules, instantiated_types, module_contents

def find_top(defined, instantiated):
    candidates = set(defined.keys()) - instantiated
    candidates = list(candidates)
    
    if not candidates: return "UNKNOWN_TOP"
    
    if len(candidates) > 1:
        # check if one is literally named "top" or "Top"
        explicit_tops = [c for c in candidates if c.lower() == 'top']
        if len(explicit_tops) == 1:
            return explicit_tops[0]
        
        # ERROR: Print exact file locations to help debug
        print(f"\n[ERR] Ambiguous Top Module. found {len(candidates)} candidates:")
        for c in candidates:
            # defined dictionary maps module_name -> file_path
            print(f"  - Module '{c}' found in: {defined[c]}")
        
        print("\n[TIP] You likely have an unused file in rtl/. Remove it or move it to a backup folder.\n")
        return "AMBIGUOUS_TOP"
    
    return candidates[0]

    
def get_clock_regex(content):
    
    # 1. Strip comments to prevent false matches
    clean_content = re.sub(r'//.*', '', content)
    clean_content = re.sub(r'/\*.*?\*/', '', clean_content, flags=re.DOTALL)

    # 2. priority Regex
    # explicit_match = re.search(
    #     r'^\s*input\s+(?:wire\s+|reg\s+|logic\s+)?(?:\[\s*\d+\s*:\s*\d+\s*\]\s*)?(\w*clk\w*|\w*clock\w*)', 
    #     clean_content, 
    #     re.MULTILINE | re.IGNORECASE
    # )
    explicit_match = re.search(
        r'^\s*input\s+(?:wire\s+|reg\s+|logic\s+)?'
        r'(?:\[\s*\d+\s*:\s*\d+\s*\]\s*)?'
        r'(\w*clk\w*|\w*clock\w*)',
        clean_content,
        re.MULTILINE | re.IGNORECASE
    )
    
    if explicit_match:
        return explicit_match.group(1)
    return "none"

def find_vcd_scope(vcd_path, dut_inst_name, sep="."):
    if not os.path.exists(vcd_path): return "none"
    
    current_scope = []
    found_path_parts = None 
    
    with open(vcd_path, 'r', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if line.startswith("$enddefinitions"): break
            
            if line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[2]
                    current_scope.append(name)
                    if name == dut_inst_name:
                        found_path_parts = list(current_scope) 

            elif line.startswith("$upscope"):
                if current_scope: current_scope.pop()
            
            elif line.startswith("$var") and found_path_parts:
                if len(current_scope) >= len(found_path_parts):
                    if current_scope[:len(found_path_parts)] == found_path_parts:
                        return sep.join(found_path_parts)

    return "none"

def get_dut_inst_name(tb_file, top_module):
    if not tb_file or not os.path.exists(tb_file): return "uut"
    with open(tb_file, 'r') as f: clean = strip_comments(f.read())
    match = re.search(r'(?m)^\s*' + re.escape(top_module) + r'\s+(\w+)\s*\(', clean)
    return match.group(1) if match else "uut"

# Verilator JSON parsing

def _walk_json_nodes(node, visitor):
    """
    Recursively walk every node in the Verilator JSON AST tree.
    Calls visitor(node) for each dict node that has a 'type' key.
    The tree structure uses a 'children' list under each node.
    """
    if not isinstance(node, dict):
        return
    if 'type' in node:
        visitor(node)
    for child in node.get('children', []):
        _walk_json_nodes(child, visitor)
        
def parse_verilator_json(json_path):
    """
    Parse the Verilator --json-only output (.tree.json) to extract:
      - top module name  (the elaborated top, not just any module)
      - clock signal name (1-bit input port whose name matches clk/clock patterns)

    Returns (top_module: str, clk: str)
    Both fall back to sentinel values if not found.
    """
    if not os.path.exists(json_path):
        return None, None

    try:
        with open(json_path, 'r') as f:
            ast = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None

    # Modules are in the top-level "modulesp" list
    modules = ast.get('modulesp', [])
    if not modules:
        return None, None
    # top_module = None
    # clk_signal = None
    
    # Top module: Verilator assigns level=2 to the elaborated design top.
    # level=1 is $root (internal wrapper), level=3+ are sub-modules.
    top_node = None
    for m in modules:
        if m.get('level') == 2:
            top_node = m
            break

    # fall back: first MODULE entry if level key is absent
    if top_node is None:
        top_node = modules[0]
    
    # # Collect all MODULE nodes
    # modules = []


    # def collect_modules(node):
    #     if node.get('type') == 'MODULE':
    #         modules.append(node)

    # _walk_json_nodes(ast, collect_modules)

    # if not modules:
    #     return None, None

    # # Identify the top module — prefer any node explicitly flagged isTop
    # top_node = None
    # for m in modules:
    #     if m.get('isTop'):
    #         top_node = m
    #         break

    # # Fallback: first MODULE node is typically the elaborated top
    # if top_node is None:
    #     top_node = modules[0]

    top_module = top_node.get('origName') or top_node.get('name')
    if not top_module:
        return None, None

    # Find clock: scan stmtsp for PORT nodes that are 1-bit inputs
    # matching common clock naming patterns
    clk_pattern = re.compile(r'\b(\w*clk\w*|\w*clock\w*)\b', re.IGNORECASE)
    clk_signal = None

    for stmt in top_node.get('stmtsp', []):
        if stmt.get('type') != 'VAR':
            continue
        if stmt.get('varType') != 'PORT':
            continue
        if stmt.get('direction', '').upper() != 'INPUT':
            continue
        name = stmt.get('origName') or stmt.get('name', '')
        if clk_pattern.fullmatch(name) or clk_pattern.search(name):
            clk_signal = name
            break
    # def find_clock_in_ports(node):
    #     nonlocal clk_signal
    #     if clk_signal:
    #         return
    #     if node.get('type') == 'PORT':
    #         direction = node.get('direction', '')
    #         name = node.get('name', '') or node.get('origName', '')
    #         width = node.get('width', None)
    #         left  = node.get('left',  None)
    #         right = node.get('right', None)
    #         is_scalar = (width == 1) or (left == 0 and right == 0)
    #         if direction == 'input' and is_scalar and clk_pattern.search(name):
    #             clk_signal = name

    #_walk_json_nodes(top_node, find_clock_in_ports)

    return top_module, clk_signal or 'none'


if __name__ == "__main__":
    mode = sys.argv[1]

    if mode == "config":
        out_mk, out_f = sys.argv[2], sys.argv[3]
        rtl_files, tb_file = [], None
        json_path = None
        
        it = iter(sys.argv[4:])
        for arg in it:
            if arg == "--tb": tb_file = next(it)
            elif arg == "--json": json_path = next(it)
            else: rtl_files.append(arg)

        #defined, instantiated, contents = analyze_rtl(rtl_files)
        
        # write the file list immediately so manual overrides work
        with open(out_f, 'w') as f:
            for p in rtl_files: f.write(f"{p}\n")

        #top = find_top(defined, instantiated)
        top=None
        clk=None
        
        # Path A: Verilator JSON (primary)
        if json_path and os.path.exists(json_path):
            print("[HIER] Using Verilator JSON for hierarchy analysis...")
            top, clk = parse_verilator_json(json_path)
            if top:
                print(f"[HIER] JSON resolved: top='{top}', clk='{clk}'")
            else:
                print("[HIER] JSON parse yielded no result — falling back to regex.")
                top = None
                
        # Path B: Regex fallback
        if not top:
            print("[HIER] Using regex for hierarchy analysis...")
            defined, instantiated, contents = analyze_rtl(rtl_files)
            top = find_top(defined, instantiated)
            if top not in ("UNKNOWN_TOP", "AMBIGUOUS_TOP"):
                clk = get_clock_regex(contents.get(top, ""))
            else:
                clk = 'none'       
        
        if top in ["UNKNOWN_TOP", "AMBIGUOUS_TOP"]:
            # write safety sentinel to .mk so Make fails fast
            with open(out_mk, 'w') as f:
                f.write(f"TOP := {top}\n")
            sys.exit(0) 

        #clk = get_clock(contents.get(top, ""), top)
        dut_inst = get_dut_inst_name(tb_file, top)

        with open(out_mk, 'w') as f:
            f.write(f"TOP := {top}\n")
            f.write(f"CLK := {clk}\n")
            f.write(f"DUT_INST := {dut_inst}\n") 
        
        print(f"[HIER] TOP={top}  CLK={clk}  DUT_INST={dut_inst}")
        # with open(out_f, 'w') as f:
        #     for p in rtl_files: f.write(f"{p}\n")

    elif mode == "scope":
        sep = sys.argv[4] if len(sys.argv) > 4 else "."
        print(find_vcd_scope(sys.argv[2], sys.argv[3], sep))