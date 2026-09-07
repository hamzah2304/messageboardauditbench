"""Inspect task for MessageBoardAuditBench.

Two entry points:

  * `messageboard_audit_bench` runs fresh trials through the sandbox CLI launcher.
      inspect eval messageboard_audit_bench/messageboard_audit_bench \
        -T agent=claude -T model=claude-opus-5 -T time_limit_minutes=30

  * `messageboard_audit_bench_replay` imports runs already on disk under runs/,
    so `inspect view` can render past baseline runs with scoring.
      inspect eval messageboard_audit_bench/messageboard_audit_bench_replay

View any result with:  inspect view
"""
from __future__ import annotations

import json
import re

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.scorer import process_metrics, rubric_scorer
from messageboard_audit_bench.solver import cli_agent, replay

EVAL_VERSION = "1-A"
_CONDITION_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CONDITIONS = ("blind", "context")
_SUPPORTED_AGENTS = {"claude", "codex", "react"}
DEFAULT_TIME_LIMIT_MINUTES = 20
TIMEOUT_GRACE_MINUTES = 5


def _load_condition(condition: str) -> dict:
    """Load one of the repository's named, time-neutral conditions."""
    repo = repo_root()
    if not _CONDITION_NAME.fullmatch(condition):
        raise ValueError(
            f"invalid condition name {condition!r}; use a name from {repo / 'configs'}"
        )
    if condition not in _CONDITIONS:
        raise ValueError(
            f"unknown condition {condition!r}; available conditions: "
            f"{', '.join(_CONDITIONS)}"
        )
    path = repo / "configs" / f"{condition}.toml"
    if not path.is_file():
        raise RuntimeError(f"condition file is missing: {path}")

    import tomllib

    return tomllib.loads(path.read_text())


def _time_limit(time_limit_minutes: int | None) -> int:
    value = (
        DEFAULT_TIME_LIMIT_MINUTES
        if time_limit_minutes is None
        else time_limit_minutes
    )
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("time_limit_minutes must be a positive integer")
    return value


def _prompt_for(condition: str, time_limit_minutes: int | None = None) -> str:
    cfg = _load_condition(condition)
    text = (
        repo_root() / "sandbox" / "prompts" / f"{cfg['prompt']}.txt"
    ).read_text()
    return text.replace("{{BUDGET_MIN}}", str(_time_limit(time_limit_minutes)))


@task
def messageboard_audit_bench(
    agent: str = "claude",
    model: str = "claude-opus-5",
    condition: str = "blind",
    time_limit_minutes: int | None = None,
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Run one sandboxed message-board audit.

    Args:
        agent: Agent harness to launch: ``claude``, ``codex``, or ``react``.
        model: Model identifier understood by that harness.
        condition: Time-neutral prompt/data/effort condition from ``configs/``.
        time_limit_minutes: Trial budget in minutes. Overrides the named
            condition's 20-minute default. The hard timeout adds five minutes.
        judge: Inspect model used to grade the report. A ``grader`` model role,
            when supplied to Inspect, takes precedence over this value.
    """
    cfg = _load_condition(condition)
    if agent not in _SUPPORTED_AGENTS:
        raise ValueError(
            f"unsupported agent {agent!r}; choose from: {', '.join(sorted(_SUPPORTED_AGENTS))}"
        )
    budget_min = _time_limit(time_limit_minutes)
    timeout_minutes = budget_min + TIMEOUT_GRACE_MINUTES
    return Task(
        dataset=[
            Sample(
                input=_prompt_for(condition, budget_min),
                id=f"{agent}:{model}:{condition}:{budget_min}m",
                metadata={
                    "agent": agent,
                    "model": model,
                    "condition": condition,
                    "budget_min": budget_min,
                    "data_variant": cfg["data_variant"],
                    "effort": cfg["effort"],
                },
            )
        ],
        solver=cli_agent(
            agent=agent,
            model=model,
            condition=condition,
            time_limit_minutes=budget_min,
            timeout_minutes=timeout_minutes,
            prompt=cfg["prompt"],
            data_variant=cfg["data_variant"],
            effort=cfg["effort"],
        ),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
        version=EVAL_VERSION,
        metadata={
            "benchmark": "MessageBoardAuditBench",
            "condition": condition,
            "time_limit_minutes": budget_min,
            "data_variant": cfg["data_variant"],
        },
    )


@task
def messageboard_audit_bench_replay(
    runs_glob: str = "*",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Import completed local runs into Inspect without rerunning agents."""
    samples = []
    for d in sorted((repo_root() / "runs").glob(runs_glob)):
        if not (d / "transcript.jsonl").exists() or d.name.startswith("failed"):
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists() or json.loads(meta_path.read_text()).get("exit_code") != 0:
            continue
        agent = next((a for a in ("codex", "react") if f"_{a}_" in d.name), "claude")
        samples.append(
            Sample(
                input=(d / "work" / "prompt.txt").read_text()
                if (d / "work" / "prompt.txt").exists()
                else "",
                id=d.name,
                metadata={"run_dir": str(d), "agent": agent},
            )
        )
    if not samples:
        raise RuntimeError(f"no runs matched runs/{runs_glob}")
    return Task(
        dataset=samples,
        solver=replay(),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
        version=EVAL_VERSION,
        metadata={"benchmark": "MessageBoardAuditBench", "mode": "replay"},
    )
