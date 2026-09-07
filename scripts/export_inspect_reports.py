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
    parser.add_argument("--include-rejected", action="store_true")
    parser.add_argument(
        "--accept-max-words",
        type=int,
        help="re-judge report length under this acceptance ceiling instead of the "
        "one recorded with each run (e.g. 3200 for runs recorded at 3100)",
    )
    parser.add_argument(
        "--graded-inputs",
        metavar="ROUND",
        help="also copy the reports into benchmark/graded_inputs/<ROUND>_<condition><budget>/ "
        "(the layout grade_with_rubrics.py --dir reads)",
    )
    args = parser.parse_args()
    backend = None if args.backend == "all" else args.backend
    rows = export_logs(
        Path(args.logs),
        Path(args.out),
        backend=backend,
        include_partial=args.include_partial,
        include_rejected=args.include_rejected,
        accept_max_words=args.accept_max_words,
    )
    print(f"{len(rows)} reports -> {args.out}")
    if args.graded_inputs:
        from messageboard_audit_bench.log_export import export_graded_inputs

        written = export_graded_inputs(
            rows, Path(args.out), repo_root() / "benchmark" / "graded_inputs", args.graded_inputs
        )
        print(f"{len(written)} graded inputs -> benchmark/graded_inputs/{args.graded_inputs}_*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
