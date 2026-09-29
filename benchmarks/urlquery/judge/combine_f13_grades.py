"""Append independently judged F13 to the preserved 12-finding Astra grades."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import grade as common
import grade_openrouter
import render_sheet

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "reports/urlquery/graded/judge_gpt_6_astra_high_fairness_v2"
ADDED = ROOT / "reports/urlquery/graded/judge_gpt_6_astra_high_f13_only"
OUT = ROOT / "reports/urlquery/graded/judge_gpt_6_astra_high_fairness_v3"
F13_SOURCE = ROOT / "benchmarks/urlquery/claims/header_injection.json"
LAUNCH = ROOT / "runs/urlquery/final-20260927-agents-v6/launch.json"
OLD_HEADS = [f"F{i}" for i in range(1, 13)]
HEADS = [*OLD_HEADS, "F13"]


def combine(base: dict, added: dict, *, source_hash: str, combined_hash: str, report: str) -> dict:
    """Preserve old judgments and record both rubric versions explicitly."""
    for key in ("run", "agent", "model", "replicate", "condition", "judge", "effort",
                "prompt_sha256", "article_sha256", "report_sha256"):
        if base[key] != added[key]:
            raise ValueError(f"base and F13 grades disagree on {key}")
    if set(base["findings"]) != set(OLD_HEADS) or set(added["findings"]) != {"F13"}:
        raise ValueError("unexpected finding IDs in source grades")
    if any(item.get("status") != "ok" for item in [*base["findings"].values(), added["findings"]["F13"]]):
        raise ValueError("all source judgments must be successful")
    if base["report_sha256"] != common.sha(report):
        raise ValueError("report changed after judging")

    result = dict(base)
    result["findings"] = {**base["findings"], "F13": added["findings"]["F13"]}
    result["findings_sha256"] = combined_hash
    result["rubric_provenance"] = {
        "F1-F12_findings_sha256": base["findings_sha256"],
        "F13_findings_sha256": added["findings_sha256"],
        "F13_source_sha256": source_hash,
        "combined_findings_sha256": combined_hash,
    }
    result["n_findings"] = 13
    result["n_scored"] = 13
    result["unscored"] = []
    result["headline_weights"] = grade_openrouter.HEADLINE_WEIGHTS
    scores = {h: result["findings"][h]["score"] for h in HEADS}
    result["score_mean"], result["score_mean_unweighted"] = grade_openrouter.score_means(scores, HEADS)
    result["scan_coverage"] = render_sheet.coverage(report)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--f13", type=Path, default=ADDED)
    ap.add_argument("--output", type=Path, default=OUT)
    ap.add_argument("--launch", type=Path, default=LAUNCH)
    args = ap.parse_args()

    base_paths = {p.name: p for p in args.base.glob("*.json")}
    added_paths = {p.name: p for p in args.f13.glob("*.json")}
    if not base_paths or set(base_paths) != set(added_paths):
        raise SystemExit(f"grade file mismatch: {len(base_paths)} base, {len(added_paths)} F13")
    source_hash = common.sha(F13_SOURCE.read_bytes())
    combined_hash = common.sha(render_sheet.FINDINGS.read_bytes())
    report_dirs = {p.name: p for p in grade_openrouter.completed_reports(args.launch)}
    if set(report_dirs) != {Path(name).stem for name in base_paths}:
        raise SystemExit("source grades do not match completed reports in final launcher")
    args.output.mkdir(parents=True, exist_ok=True)
    for name in sorted(base_paths):
        base = json.loads(base_paths[name].read_text())
        added = json.loads(added_paths[name].read_text())
        report_path = report_dirs[base["run"]] / "report.md"
        if not report_path.is_file():
            raise SystemExit(f"missing report for {name}: {report_path}")
        result = combine(base, added, source_hash=source_hash, combined_hash=combined_hash,
                         report=report_path.read_text())
        dest = args.output / name
        tmp = args.output / f".{name}.tmp"
        tmp.write_text(json.dumps(result, indent=1, ensure_ascii=False))
        tmp.replace(dest)
    print(f"combined {len(base_paths)} reports with 13/13 successful findings in {args.output}")


if __name__ == "__main__":
    main()
