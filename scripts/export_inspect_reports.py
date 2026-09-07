#!/usr/bin/env python3
"""Export report artifacts from native Inspect ``.eval`` logs.

Usage:
    uv run python scripts/export_inspect_reports.py --logs logs --out reports/native

The default only exports ``backend=inspect`` samples. Pass ``--backend all`` to
export imported subscription samples too. Reports are grouped by agent scaffold;
the backend remains in each index row for transport-level analysis.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Direct ``python scripts/...`` execution puts ``scripts/`` rather than the
# checkout root on sys.path. Keep the documented command usable without a
# prior editable installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from messageboard_audit_bench.log_export import export_logs
from messageboard_audit_bench.runtime import repo_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", default=str(repo_root() / "logs"))
    parser.add_argument("--out", default=str(repo_root() / "reports" / "native"))
    parser.add_argument(
        "--backend",
        choices=("inspect", "subscription", "all"),
        default="inspect",
        help="sample backend to export (default: inspect)",
    )
    parser.add_argument("--include-partial", action="store_true")
    args = parser.parse_args()
    backend = None if args.backend == "all" else args.backend
    rows = export_logs(
        Path(args.logs),
        Path(args.out),
        backend=backend,
        include_partial=args.include_partial,
    )
    print(f"{len(rows)} reports -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
