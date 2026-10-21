#!/usr/bin/env python3
"""Write the standard condition's per-eval configs from configs/standard.toml.

    uv run python scripts/standard_configs.py           # (re)write configs/<eval>-std-<budget>.toml
    uv run python scripts/standard_configs.py --check   # exit 1 if any generated file is stale

Each generated config is flat, like every other config, so both runners read it unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopvestigator_bench.standard import render_all  # noqa: E402


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for name, text in render_all().items():
        path = ROOT / "configs" / f"{name}.toml"
        if path.is_file() and path.read_text() == text:
            continue
        if check:
            stale.append(path.name)
        else:
            path.write_text(text)
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print(json.dumps({"stale": stale}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
