#!/usr/bin/env python3
"""Summarise an AI Village grading plan into one row per report and one row per model and condition.

    scripts/summarize_aivillage_grades.py runs/aivillage-grading-medium/plans/<plan>/grades.json \
        benchmarks/aivillage/results/

Score is the mean of the report's 20 best finding scores (the judge's 0-1 score for how fully the
report states each key finding), matching the 20 findings a report writes. Coverage is the
grader's `mean_coverage`, the same scores averaged over every key finding. "Findings at 0.5+"
counts key findings the judge scored 0.5 or higher. Contradiction penalties are not applied (pending human review).
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

TOP_K = 20
RUN = re.compile(r"^\d{8}T\d{6}Z_(claude|codex|react)_(.+)_r(\d+)_(aivillage-v12-30(?:-subagents)?)_[0-9a-f]+$")


def main(grades_path: str, out_dir: str) -> None:
    grades = json.loads(Path(grades_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows, groups = [], defaultdict(list)
    for r in grades["reports"]:
        m = RUN.match(r["report_id"])
        if not m or not r["complete"]:
            sys.exit(f"unexpected or incomplete report: {r['report_id']}")
        harness, model, rep, config = m.groups()
        model = model.replace("_", "/") if harness == "react" else model
        subagents = "yes" if config.endswith("-subagents") else "no"
        scores = sorted((f["score"] for f in r["scores"].values()), reverse=True)
        top = sum(scores[:TOP_K]) / TOP_K
        row = (harness, model, subagents, rep, top, sum(s >= 0.5 for s in scores), len(scores), r["report_id"], r["mean_coverage"])
        rows.append(row)
        groups[(harness, model, subagents)].append(row)
    rows.sort(key=lambda x: (-x[4], x[7]))
    with open(out / "scores-by-report.tsv", "w") as f:
        f.write("harness\tmodel\tsubagents\treplicate\tscore_top20\tcoverage\tfindings_at_0.5_plus\tkey_findings\treport_id\n")
        for h, mo, s, rep, top, hi, n, rid, cov in rows:
            f.write(f"{h}\t{mo}\t{s}\t{rep}\t{top:.3f}\t{cov:.3f}\t{hi}\t{n}\t{rid}\n")
    summary = sorted(groups.items(), key=lambda kv: -sum(x[4] for x in kv[1]) / len(kv[1]))
    with open(out / "scores-by-model.tsv", "w") as f:
        f.write("harness\tmodel\tsubagents\treports\tmean_score_top20\tscore_per_report\tmean_coverage\tmean_findings_at_0.5_plus\n")
        for (h, mo, s), rs in summary:
            tops = sorted(x[4] for x in rs)
            f.write(f"{h}\t{mo}\t{s}\t{len(rs)}\t{sum(tops) / len(tops):.3f}\t{', '.join(f'{c:.3f}' for c in tops)}\t"
                    f"{sum(x[8] for x in rs) / len(rs):.3f}\t{sum(x[5] for x in rs) / len(rs):.1f}\n")
    print(f"{len(rows)} reports, mean score {sum(x[4] for x in rows) / len(rows):.3f}, mean coverage {sum(x[8] for x in rows) / len(rows):.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
