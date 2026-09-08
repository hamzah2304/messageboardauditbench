"""Grade reports that already exist on disk.

`grade_reports` is the Inspect replacement for `grade_with_rubrics.py --dir <name>`. Its
dataset is a staged report folder — `benchmark/graded_inputs/<dir>/`, produced either by
`scripts/stage_graded_inputs.py` or by `log_export.export_graded_inputs()` — and its sample
ids are the same sanitised stems the grade filenames have always used, so a run of this
task exports over the existing corpus rather than beside it.

This task also supports a separate grading pass over exported historical reports.
"""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, TaskState, solver

from messageboard_audit_bench.grading import core
from messageboard_audit_bench.grading.scorer import sheet_scorer
from messageboard_audit_bench.runtime import repo_root


def staged_dir(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else repo_root() / "benchmark" / "graded_inputs" / name


def _index(folder: Path) -> dict[str, dict]:
    """graded_input filename -> the run's index row, when the folder carries one."""
    idx = folder / "_index.jsonl"
    if not idx.exists():
        return {}
    rows = [json.loads(line) for line in idx.read_text().splitlines() if line.strip()]
    return {r["graded_input"]: r for r in rows if r.get("graded_input")}


@solver
def report_from_sample():
    """The report is the input; there is no agent to run."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.output = ModelOutput.from_content(
            model="staged-report", content=state.input_text
        )
        return state

    return solve


@task
def grade_reports(
    dir: str = "round4_blind120",  # noqa: A002 — the Inspect task parameter is named `dir`
    rubric: str = "v2",
    judge: str = "openai/gpt-5.6-sol",
    variant: str | None = None,
) -> Task:
    """Grade every staged report in `dir` against `rubric`.

    Args:
      dir: a folder under benchmark/graded_inputs/, or an absolute path.
      rubric: a key of `core.MODES`, such as "v2" or "tldrh".
      variant: explicit rubric variant for reports without an index; indexed
        reports otherwise select their variant from data_variant per sample.
      judge: Inspect model used to grade. As on the audit task, a ``grader``
        model role supplied to Inspect takes precedence over this value.
    """
    folder = staged_dir(dir)
    rows = _index(folder)
    samples = []
    for path in sorted(folder.glob("*.md")):
        row = rows.get(path.name, {})
        samples.append(
            Sample(
                input=path.read_text(),
                id=core.sanitise(path.stem),
                metadata={
                    "title": path.stem,
                    "staged_input": path.name,
                    "staged_dir": folder.name,
                    "budget_min": row.get("budget_min"),
                    "model": row.get("model"),
                    "model_served": row.get("model_served"),
                    "agent": row.get("agent"),
                    "scaffold": row.get("scaffold"),
                    "replicate": row.get("replicate"),
                    "data_variant": row.get("data_variant"),
                },
            )
        )
    if not samples:
        raise RuntimeError(f"no reports in {folder}")
    return Task(
        dataset=samples,
        solver=report_from_sample(),
        scorer=sheet_scorer(rubric=rubric, judge=judge, variant=variant),
        model="mockllm/model",
        metadata={
            "benchmark": "MessageBoardAuditBench",
            "mode": "grading",
            "rubric": rubric,
            "judge": judge,
            "staged_dir": folder.name,
        },
    )
