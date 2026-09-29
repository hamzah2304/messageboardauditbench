"""Grade completed URLQuery reports with GPT-6 Astra via OpenRouter (the final-run judge).

    .venv/bin/python benchmarks/urlquery/judge/grade_openrouter.py \
      --launch runs/urlquery/final-20260927-agents-v6/launch.json --workers 32

A preset of grade.py: judge openrouter/openai/gpt-6-astra at high effort, the full
article, 32 workers, output reports/urlquery/graded/judge_gpt_6_astra_high/. Any grade.py
option overrides these.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402

from messageboard_audit_bench.grading.findings import (  # noqa: E402
    headline_weights,
    output_root,
    reports_from,
    score_means,
)

MODEL = "openrouter/openai/gpt-6-astra"
EFFORT = "high"
OUT = output_root() / "judge_gpt_6_astra_high"
HEADLINE_WEIGHTS = headline_weights()

__all__ = ["HEADLINE_WEIGHTS", "completed_reports", "score_means"]


def completed_reports(launch_path: Path) -> list[Path]:
    return reports_from(launch=launch_path)


if __name__ == "__main__":
    grade.main(defaults={"judge": MODEL, "effort": EFFORT, "output": OUT, "workers": 32})
