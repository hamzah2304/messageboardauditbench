#!/usr/bin/env python3
"""Write graded_<key>.json out of an Inspect eval log.

    uv run python scripts/export_grades.py logs/2026-09-08T…_grade-reports_….eval

Everything downstream of grading — scripts/report_performance.py, the headline and combined
figures, the audit viewers, scripts/tldr_judge_vs_human.py — reads
benchmark/graded/[judge_<model>/]<rubric>/graded_<key>.json. This puts the Inspect path's
grades there, unchanged, so none of them has to learn what an eval log is.

The grades are copied out of the score metadata rather than recomputed. A second
computation here could disagree with the one the scorer already did, and then two files
claiming to be the same grade would differ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inspect_ai.log import read_eval_log  # noqa: E402

from messageboard_audit_bench.grading import core, export  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", help="path to the .eval log")
    ap.add_argument("--out-dir", help="write here instead of benchmark/graded/…")
    ap.add_argument("--force", action="store_true", help="overwrite existing grade files")
    ap.add_argument("--dry-run", action="store_true", help="say what would be written")
    args = ap.parse_args()

    log = read_eval_log(args.log)
    grades = export.grades_in(log)
    if not grades:
        raise SystemExit(f"{args.log}: no graded samples — was sheet_scorer attached?")

    judges = {g["grader"] for g in grades}
    rubrics = {g["rubric"] for g in grades}
    out = Path(args.out_dir) if args.out_dir else None
    dest = out or core.out_dir(sorted(judges)[0], sorted(rubrics)[0])
    print(f"{len(grades)} graded samples · judge {', '.join(sorted(judges))} · "
          f"rubric {', '.join(sorted(rubrics))} -> {dest}")
    if len(judges) > 1 or len(rubrics) > 1:
        print("  (mixed judges or rubrics: each grade is filed under its own)")

    if args.dry_run:
        for g in sorted(grades, key=lambda g: g["report"]):
            print(f"  would write graded_{g['report']}.json  "
                  f"{g['total']}/{g['max']}  accuracy={g.get('accuracy')}")
        return

    written = export.export(log, out_dir=out, force=args.force)
    skipped = len(grades) - len(written)
    print(f"wrote {len(written)} file{'' if len(written) == 1 else 's'}"
          + (f", skipped {skipped} that already existed (--force to overwrite)" if skipped else ""))


if __name__ == "__main__":
    main()
