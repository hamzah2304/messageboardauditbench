"""Grade reports that already exist on disk.

`german_wiki_report_grade` is the Inspect replacement for `grade_with_rubrics.py --dir <name>`. Its
dataset is a staged report folder — `benchmarks/german-wiki/graded_inputs/<dir>/`, produced either by
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

from slopvestigator_bench.benchmarks import reject_foreign_grading
from slopvestigator_bench.grading import core
from slopvestigator_bench.grading.scorer import sheet_scorer
from slopvestigator_bench.runtime import repo_root


def staged_dir(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else repo_root() / "benchmarks" / "german-wiki" / "graded_inputs" / name


def _index(folder: Path) -> dict[str, dict]:
    """graded_input filename -> the run's index row, when the folder carries one."""
    idx = folder / "_index.jsonl"
    if not idx.exists():
        return {}
    rows = [json.loads(line) for line in idx.read_text().splitlines() if line.strip()]
    return {r["graded_input"]: r for r in rows if r.get("graded_input")}


def run_samples(benchmark_id: str, pattern: str) -> list[Sample]:
    """One sample per run directory matching `pattern` under the benchmark's run root.

    Shared by the grade tasks: the report is the input, and the run record's model, budget,
    replicate and eligibility (slopvestigator_bench/eligibility.py) ride along as metadata.
    Runs without a report are skipped here; the results table counts them as failures.
    """
    from slopvestigator_bench import eligibility
    from slopvestigator_bench.benchmarks import SPECS, primary_root

    samples = []
    for run_dir in sorted((primary_root() / SPECS[benchmark_id].run_root).glob(pattern)):
        if not (run_dir / "report.md").is_file():
            continue
        meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").is_file() else {}
        if meta.get("benchmark_id"):  # older AI Village runs predate the field
            reject_foreign_grading(meta["benchmark_id"], benchmark_id)
        verdict = eligibility.check_meta(meta)
        samples.append(Sample(
            input=(run_dir / "report.md").read_text(), id=core.sanitise(run_dir.name),
            metadata={"run": run_dir.name, "title": run_dir.name, "run_dir": str(run_dir),
                      "data_variant": meta.get("data_variant"), "model": meta.get("model"),
                      "model_served": meta.get("model_served"), "agent": meta.get("agent"),
                      "config": meta.get("config"), "budget_min": meta.get("budget_min"),
                      "replicate": meta.get("replicate"), "eligible": verdict.eligible,
                      "ineligible_reasons": list(verdict.reasons)}))
    return samples


@solver
def report_from_sample():
    """The report is the input; there is no agent to run."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.output = ModelOutput.from_content(
            model="staged-report", content=state.input_text
        )
        return state

    return solve


def _german_wiki_report_grade(
    dir: str = "round4_blind120",  # noqa: A002 — the Inspect task parameter is named `dir`
    rubric: str = "v2",
    judge: str = "openai/gpt-5.6-sol",
    variant: str | None = None,
    runs: str | None = None,
    judge_effort: str | None = None,
) -> Task:
    """Grade every staged report in `dir` (or every run matching `runs`) against `rubric`.

    Args:
      dir: a folder under benchmarks/german-wiki/graded_inputs/, or an absolute path.
      runs: instead of `dir`, a glob of run directories under the primary checkout's runs/
        (e.g. ``*_wiki-std-30_*``); each run's own data variant picks its rubric variant.
      judge_effort: one reasoning effort for every sheet; unset, xhigh then high then medium.
      rubric: a key of `core.MODES`, such as "v2", "tldrh", "m5",
        "m5tldrh", "rh", or "rhtldrh".
      variant: explicit rubric variant for reports without an index; indexed
        reports otherwise select their variant from data_variant per sample.
      judge: Inspect model used to grade. As on the audit task, a ``grader``
        model role supplied to Inspect takes precedence over this value.
    """
    if runs:
        samples = run_samples("messageboard", runs)
        if not samples:
            raise RuntimeError(f"no German wiki runs with a report match {runs!r}")
        return _german_wiki_grade_task(samples, rubric, judge, variant, judge_effort, {"runs": runs})
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
    return _german_wiki_grade_task(samples, rubric, judge, variant, judge_effort, {"staged_dir": folder.name})


def _german_wiki_grade_task(samples, rubric, judge, variant, effort, source: dict) -> Task:
    return Task(
        dataset=samples,
        solver=report_from_sample(),
        scorer=sheet_scorer(rubric=rubric, judge=judge, variant=variant, effort=effort),
        model="mockllm/model",
        metadata={
            "benchmark": "German wiki report",
            "benchmark_id": "messageboard",
            "mode": "grading",
            "rubric": rubric,
            "judge": judge,
            "judge_effort": effort,
            **source,
        },
    )


german_wiki_report_grade = task(name="german_wiki_report_grade")(_german_wiki_report_grade)


def _transluce_report_grade(
    runs: str | None = None,
    batch: str | None = None,
    launch: str | None = None,
    judge: str | None = None,
    judge_effort: str | None = None,
    article_context: str | None = None,
) -> Task:
    """Grade finished Transluce report run directories with the per-finding judge.

    The Inspect counterpart of benchmarks/transluce/judge/grade.py: the same prompts and
    arithmetic, with the grade file for each report in ``Score.metadata["grade"]``.

    Args:
      runs: a glob under the primary checkout's runs/urlquery/ (e.g. ``2026092*_codex_*``).
      batch: a pilot plan directory whose ``*.result.json`` files name its run dirs.
      launch: a launch.json whose ``plans`` list plan files (the final-run launcher's).
      judge: Inspect model; defaults to ``anthropic/claude-opus-5-5``. Use
        ``openrouter/openai/gpt-6-astra`` for the final-run judge.
      judge_effort: ``xhigh`` for Anthropic judges, ``high`` otherwise, by default.
      article_context: ``omitted`` or ``full``; defaults to ``omitted`` for Anthropic
        judges and ``full`` otherwise.
    """
    from slopvestigator_bench.benchmarks import (
        SPECS,
        primary_root,
        urlquery_manifest,
    )
    from slopvestigator_bench.grading import findings
    from slopvestigator_bench.grading.finding_scorer import finding_scorer

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


transluce_report_grade = task(name="transluce_report_grade")(_transluce_report_grade)


@task
def aivillage_report_grade(
    runs: str | None = None,
    dir: str | None = None,  # noqa: A002 — named like german_wiki_report_grade's
    judge: str | None = None,
    data_variant: str = "aivillage/full-v2-reasoning",
    judge_effort: str | None = None,
) -> Task:
    """Grade finished AI Village reports against the 96 rubric findings.

    The Inspect counterpart of scripts/aivillage/grade_aivillage.py: the same judge requests, with
    each report's per-finding grades in ``Score.metadata["grade"]``.

    Args:
      runs: a glob of run directories under the primary checkout's runs/
        (e.g. ``*_aivillage-v12-30*``); each needs a report.md.
      dir: or a folder of ``.md`` reports, one per run (absolute, or relative to the repo).
      judge: Inspect model; defaults to ``openai/gpt-6.1-sol``. A ``grader`` role wins.
      data_variant: the data the reports were written from, for ``dir`` reports; run
        directories record their own. It sets the goal periods and whether the judge is
        told the investigator saw reasoning traces.
      judge_effort: the judge's reasoning effort; ``medium`` as published, ``high`` in the standard condition.
    """
    from slopvestigator_bench.benchmarks import SPECS
    from slopvestigator_bench.grading.aivillage import EFFORT, aivillage_scorer

    if bool(runs) == bool(dir):
        raise ValueError("pass exactly one of runs or dir")
    samples = []
    if runs:
        samples = run_samples("aivillage", runs)
        for sample in samples:
            sample.metadata["data_variant"] = sample.metadata["data_variant"] or data_variant
    else:
        folder = Path(dir) if Path(dir).is_absolute() else repo_root() / dir
        for path in sorted(folder.glob("*.md")):
            samples.append(Sample(input=path.read_text(), id=core.sanitise(path.stem),
                                  metadata={"run": path.stem, "title": path.stem, "data_variant": data_variant}))
    if not samples:
        raise RuntimeError("no AI Village reports matched")
    return Task(
        dataset=samples,
        solver=report_from_sample(),
        scorer=aivillage_scorer(judge=judge, effort=judge_effort or EFFORT),
        model="mockllm/model",
        metadata={"benchmark": SPECS["aivillage"].title, "benchmark_id": "aivillage", "mode": "grading",
                  "judge": judge, "judge_effort": judge_effort or EFFORT},
    )
