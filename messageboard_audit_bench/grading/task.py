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

from messageboard_audit_bench.benchmarks import reject_foreign_grading
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
      rubric: a key of `core.MODES`, such as "v2", "tldrh", "m5",
        "m5tldrh", "rh", or "rhtldrh".
      variant: explicit rubric variant for reports without an index; indexed
        reports otherwise select their variant from data_variant per sample.
      judge: Inspect model used to grade. As on the audit task, a ``grader``
        model role supplied to Inspect takes precedence over this value.
    """
    folder = staged_dir(dir)
    core.require_original_benchmark_folder(folder)
    rows = _index(folder)
    samples = []
    for path in sorted(folder.glob("*.md")):
        row = rows.get(path.name, {})
        reject_foreign_grading(row.get("benchmark_id", "messageboard"))
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


@task
def urlquery_grade_reports(
    runs: str | None = None,
    batch: str | None = None,
    launch: str | None = None,
    judge: str | None = None,
    judge_effort: str | None = None,
    article_context: str | None = None,
) -> Task:
    """Grade finished URLQuery run directories with the per-finding judge.

    The Inspect counterpart of benchmarks/urlquery/judge/grade.py: the same prompts and
    arithmetic, with the grade file for each report in ``Score.metadata["grade"]``.

    Args:
      runs: a glob under the primary checkout's runs/urlquery/ (e.g. ``2026092*_codex_*``).
      batch: a pilot plan directory whose ``*.result.json`` files name its run dirs.
      launch: a launch.json whose ``plans`` list plan files (the final-run launcher's).
      judge: Inspect model; defaults to ``anthropic/claude-opus-5-5``. Use
        ``openrouter/openai/gpt-6-astra`` for the final-run judge.
      judge_effort: ``xhigh`` for Anthropic judges, ``high`` otherwise, by default.
      article_context: ``omitted`` (default) or ``full``.
    """
    from messageboard_audit_bench.benchmarks import (
        SPECS,
        primary_root,
        urlquery_manifest,
    )
    from messageboard_audit_bench.grading import findings
    from messageboard_audit_bench.grading.finding_scorer import finding_scorer

    run_root = primary_root() / SPECS["urlquery"].run_root
    run_dirs = findings.reports_from(
        runs=sorted(run_root.glob(runs)) if runs else [],
        batches=[Path(batch)] if batch else [],
        launch=Path(launch) if launch else None,
    )
    samples = []
    for run_dir in run_dirs:
        meta = findings.run_meta(run_dir)
        run_meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").is_file() else {}
        reject_foreign_grading(run_meta.get("benchmark_id", "urlquery"), grader="urlquery")
        samples.append(
            Sample(
                input=(run_dir / "report.md").read_text(),
                id=run_dir.name,
                metadata={**meta, "run_dir": str(run_dir), "title": run_dir.name,
                          "data_variant": run_meta.get("data_variant"),
                          "dataset_sha256": run_meta.get("dataset_sha256")},
            )
        )
    if not samples:
        raise RuntimeError("no URLQuery run directories with a report.md matched")
    return Task(
        dataset=samples,
        solver=report_from_sample(),
        scorer=finding_scorer(judge=judge, effort=judge_effort, article_context=article_context),
        model="mockllm/model",
        metadata={
            "benchmark": SPECS["urlquery"].title,
            "benchmark_id": "urlquery",
            "mode": "grading",
            "rubric": urlquery_manifest()["grading"]["rubric"],
            "judge": judge,
        },
    )
