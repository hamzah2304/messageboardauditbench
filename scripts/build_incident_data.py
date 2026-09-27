#!/usr/bin/env python3
"""Run every registered incident-specific corpus builder."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from messageboard_audit_bench.incidents import incident, incidents  # noqa: E402
from messageboard_audit_bench.runtime import repo_root  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incident", nargs="*", help="incident IDs; default: every builder")
    args = parser.parse_args()
    selected = [incident(name) for name in args.incident] if args.incident else incidents().values()
    root = repo_root()
    ran = 0
    for item in selected:
        builder = item.corpus.get("builder")
        if not builder:
            continue
        path = root / builder
        print(f"[{item.id}] {builder}")
        subprocess.run([sys.executable, str(path)], cwd=root, check=True)
        ran += 1
    print(f"built {ran} registered incident {'corpus' if ran == 1 else 'corpora'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
