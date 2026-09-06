"""Inspect task for MessageBoardAuditBench.

Two entry points:

  * `messageboard_audit` runs fresh trials through the sandbox CLI launcher.
      inspect eval messageboard_audit/messageboard_audit \
        -T agent=claude -T model=claude-opus-5 --epochs 3

  * `messageboard_audit_replay` imports runs already on disk under runs/,
    so `inspect view` can render past baseline runs with scoring.
      inspect eval messageboard_audit/messageboard_audit_replay

View any result with:  inspect view
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from messageboard_audit.scorer import process_metrics, rubric_scorer
from messageboard_audit.solver import cli_agent, replay

REPO = Path(__file__).resolve().parent.parent
EVAL_VERSION = "1-A"
_CONFIG_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _load_config(config: str) -> dict:
    """Load one of the repository's named trial configurations."""
    if not _CONFIG_NAME.fullmatch(config):
        raise ValueError(
            f"invalid config name {config!r}; use a name from {REPO / 'configs'}"
        )
    path = REPO / "configs" / f"{config}.toml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in path.parent.glob("*.toml")))
        raise ValueError(f"unknown config {config!r}; available configs: {available}")

    import tomllib

    return tomllib.loads(path.read_text())


def _prompt_for(config: str) -> str:
    cfg = _load_config(config)
    text = (REPO / "sandbox" / "prompts" / f"{cfg['prompt']}.txt").read_text()
    return text.replace("{{BUDGET_MIN}}", str(cfg["budget_min"]))


@task
def messageboard_audit(
    agent: str = "claude",
    model: str = "claude-opus-5",
    config: str = "default",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Run one sandboxed message-board audit.

    Args:
        agent: Agent harness to launch: ``claude``, ``codex``, or ``react``.
        model: Model identifier understood by that harness.
        config: Named configuration from ``configs/``.
        judge: Inspect model used to grade the report. A ``grader`` model role,
            when supplied to Inspect, takes precedence over this value.
    """
    cfg = _load_config(config)
    return Task(
        dataset=[
            Sample(
                input=_prompt_for(config),
                id=f"{agent}:{model}:{config}",
                metadata={
                    "agent": agent,
                    "model": model,
                    "config": config,
                    "budget_min": cfg["budget_min"],
                    "data_variant": cfg["data_variant"],
                    "effort": cfg["effort"],
                },
            )
        ],
        solver=cli_agent(agent=agent, model=model, config=config),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
        version=EVAL_VERSION,
        metadata={
            "benchmark": "MessageBoardAuditBench",
            "config": config,
            "data_variant": cfg["data_variant"],
        },
    )


@task
def messageboard_audit_replay(
    runs_glob: str = "*",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Import completed local runs into Inspect without rerunning agents."""
    samples = []
    for d in sorted((REPO / "runs").glob(runs_glob)):
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
