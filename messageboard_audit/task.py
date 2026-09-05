"""Inspect task for MessageBoardAuditBench.

Two entry points:

  * `messageboard_audit` runs fresh trials through the sandbox CLI launcher.
      inspect eval messageboard_audit/task.py@messageboard_audit \
        -T agent=claude -T model=claude-opus-5 --epochs 3

  * `messageboard_audit_replay` imports runs already on disk under runs/,
    so `inspect view` can render past baseline runs with scoring.
      inspect eval messageboard_audit/task.py@messageboard_audit_replay

View any result with:  inspect view
"""
from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from messageboard_audit.scorer import process_metrics, rubric_scorer
from messageboard_audit.solver import cli_agent, replay

REPO = Path(__file__).resolve().parent.parent
PROMPT = (REPO / "sandbox" / "prompt.txt").read_text()


@task
def messageboard_audit(
    agent: str = "claude",
    model: str = "claude-opus-5",
    effort: str = "medium",
    timeout: str = "25m",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    return Task(
        dataset=[Sample(input=PROMPT, id=f"{agent}:{model}")],
        solver=cli_agent(agent=agent, model=model, effort=effort, timeout=timeout),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
    )


@task
def messageboard_audit_replay(
    runs_glob: str = "*_s*",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    samples = []
    for d in sorted((REPO / "runs").glob(runs_glob)):
        if not (d / "transcript.jsonl").exists() or d.name.startswith("failed"):
            continue
        agent = "codex" if "codex" in d.name else "claude"
        samples.append(
            Sample(input=PROMPT, id=d.name, metadata={"run_dir": str(d), "agent": agent})
        )
    if not samples:
        raise RuntimeError(f"no runs matched runs/{runs_glob}")
    return Task(
        dataset=samples,
        solver=replay(),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
    )
