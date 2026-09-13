#!/usr/bin/env python3
"""The published headline score for a set of graded reports, including your own.

    scripts/score_reports.py benchmark/graded/judge_claude_fable_5_1
    scripts/score_reports.py --findings <dir> --summary <dir> --json

The headline is 70% finding coverage and 30% holistic summary quality:

    headline = 0.7 x mean(max(2s - 1, 0) over the 38 v2 findings) + 0.3 x tldrh

Two numbers are easy to confuse with that and neither is it. The raw mean of
per-finding credit is what `inspect eval` prints, and it runs well above the
strict coverage because it gives half credit to a report that only gestures at a
finding. The fraction of findings scoring above 0.5 is not it either. Both are
printed here beside the headline so the difference is visible rather than
discovered later.

The figure builders compute the same composite for the project's own rounds;
this works on any directory of grades, which is what an outside scaffold needs.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_performance import W_COV, W_TLDR, strict  # noqa: E402


def _grades(folder: Path) -> dict[str, dict]:
    """graded_<key>.json -> the parsed grade, keyed by the report it graded."""
    out: dict[str, dict] = {}
    for path in sorted(folder.glob("graded_*.json")):
        try:
            grade = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"skipping {path.name}: {exc}", file=sys.stderr)
            continue
        key = grade.get("report") or path.stem.removeprefix("graded_")
        out[key] = grade
    return out


def _coverage(grade: dict) -> tuple[float, float, float] | None:
    """Raw mean, strict mean, and the fraction above half credit."""
    scores = [s["score"] for s in grade.get("scores", {}).values() if "score" in s]
    if not scores:
        return None
    return (
        st.mean(scores),
        st.mean(strict(s) for s in scores),
        sum(1 for s in scores if s > 0.5) / len(scores),
    )


def combine(v2_dir: Path, tldrh_dir: Path) -> dict:
    """Pair the two sheets by report and compute the headline for each."""
    v2, tldrh = _grades(v2_dir), _grades(tldrh_dir)
    rows, warnings = [], []

    for key in sorted(set(v2) | set(tldrh)):
        cov = _coverage(v2[key]) if key in v2 else None
        holistic = tldrh[key].get("accuracy") if key in tldrh else None
        if cov is None or holistic is None:
            missing = v2_dir.name if cov is None else tldrh_dir.name
            warnings.append(f"{key}: no {missing} grade, excluded from the headline")
            continue
        raw, strict_cov, above_half = cov
        rows.append(
            {
                "report": key,
                "coverage_raw": round(raw, 4),
                "coverage_strict": round(strict_cov, 4),
                "fraction_above_half": round(above_half, 4),
                "tldrh": round(holistic, 4),
                "headline": round(W_COV * strict_cov + W_TLDR * holistic, 4),
                "judge_v2": v2[key].get("grader"),
                "judge_tldrh": tldrh[key].get("grader"),
            }
        )

    judges = {j for r in rows for j in (r["judge_v2"], r["judge_tldrh"]) if j}
    if len(judges) > 1:
        warnings.append(
            "grades come from more than one judge "
            f"({', '.join(sorted(judges))}); scores from different judges are not "
            "comparable and the mean below mixes them"
        )
    return {
        "weights": {"coverage": W_COV, "tldrh": W_TLDR},
        "judges": sorted(judges),
        "reports": rows,
        "mean_headline": round(st.mean(r["headline"] for r in rows), 4) if rows else None,
        "mean_coverage_strict": round(st.mean(r["coverage_strict"] for r in rows), 4)
        if rows
        else None,
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "judge_dir",
        nargs="?",
        help="a directory holding v2/tldrh or m5/m5tldrh grade subdirectories",
    )
    ap.add_argument(
        "--v2", "--findings", dest="findings", help="directory of finding grades"
    )
    ap.add_argument(
        "--tldrh", "--summary", dest="summary", help="directory of summary grades"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if args.findings and args.summary:
        v2_dir, tldrh_dir = Path(args.findings), Path(args.summary)
    elif args.judge_dir:
        root = Path(args.judge_dir)
        if (root / "m5").is_dir() or (root / "m5tldrh").is_dir():
            v2_dir, tldrh_dir = root / "m5", root / "m5tldrh"
        else:
            v2_dir, tldrh_dir = root / "v2", root / "tldrh"
    else:
        ap.error("give a judge directory, or both --findings and --summary")

    for label, folder in ((v2_dir.name, v2_dir), (tldrh_dir.name, tldrh_dir)):
        if not folder.is_dir():
            print(f"no {label} grades at {folder}", file=sys.stderr)
            print(
                "Grade a report set first:\n"
                "  uv run inspect eval messageboard_audit_bench/grade_reports \\\n"
                f"    -T dir=<your reports> -T rubric={label} "
                "--model-role grader=anthropic/claude-fable-5-1\n"
                "  uv run python scripts/export_grades.py logs/<the run>.eval",
                file=sys.stderr,
            )
            return 2

    result = combine(v2_dir, tldrh_dir)

    if args.json:
        print(json.dumps(result, indent=1))
        return 0

    rows = result["reports"]
    if not rows:
        print("no report was graded on both sheets", file=sys.stderr)
        for warning in result["warnings"]:
            print(f"  {warning}", file=sys.stderr)
        return 1

    width = max(len(r["report"]) for r in rows) + 2
    print(
        f"{len(rows)} reports, judge {', '.join(result['judges']) or 'unknown'}, "
        f"headline = {W_COV:g} x strict coverage + {W_TLDR:g} x tldrh\n"
    )
    print(
        f"{'report':<{width}}{'raw':>7}{'strict':>8}{'>0.5':>7}{'tldrh':>8}{'headline':>10}"
    )
    for r in sorted(rows, key=lambda r: -r["headline"]):
        print(
            f"{r['report']:<{width}}{r['coverage_raw']:>7.3f}{r['coverage_strict']:>8.3f}"
            f"{r['fraction_above_half']:>7.3f}{r['tldrh']:>8.3f}{r['headline']:>10.3f}"
        )
    print(
        f"\nmean headline {result['mean_headline']:.3f}"
        f"   mean strict coverage {result['mean_coverage_strict']:.3f}"
    )
    print(
        "\nraw is the mean of per-finding credit, what `inspect eval` reports; the\n"
        "headline uses strict coverage instead. >0.5 is the fraction of findings above\n"
        "half credit — a third number again, and not what the headline means."
    )
    for warning in result["warnings"]:
        print(f"\nwarning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
