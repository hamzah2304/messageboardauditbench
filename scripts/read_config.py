#!/usr/bin/env python3
"""Read a trial config (configs/<name>.toml) and print it as shell assignments or JSON.

    scripts/read_config.py configs/blind-20.toml          # CFG_NAME=... lines for `eval`
    scripts/read_config.py configs/blind-20.toml --json

The configs are flat TOML: strings, integers, and arrays of strings. Parsed here
without tomllib so the launcher works on any python3.
"""
import json, re, sys
from pathlib import Path

def load(path: str) -> dict:
    cfg = {}
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip() if not line.strip().startswith('"') else line
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$', line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        v = re.sub(r'\s+#.*$', '', v).strip()
        if v.startswith("["):
            cfg[k] = re.findall(r'"([^"]*)"', v)
        elif v.startswith('"'):
            cfg[k] = v.strip('"')
        elif re.fullmatch(r'-?\d+', v):
            cfg[k] = int(v)
        elif v in ("true", "false"):
            cfg[k] = v == "true"
        else:
            cfg[k] = v
    return cfg

if __name__ == "__main__":
    cfg = load(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(cfg))
    else:
        for k, v in cfg.items():
            if isinstance(v, list):
                v = " ".join(v)
            print(f"CFG_{k.upper()}={json.dumps(str(v))}")
