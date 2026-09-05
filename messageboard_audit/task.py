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
import subprocess, json as _json

def _prompt_for(config: str) -> str:
    cfg = _json.loads(subprocess.check_output(["python3", str(REPO / "scripts" / "read_config.py"), str(REPO / "configs" / f"{config}.toml"), "--json"]))
    text = (REPO / "sandbox" / "prompts" / f"{cfg['prompt']}.txt").read_text()
    return text.replace("{{BUDGET_MIN}}", str(cfg["budget_min"]))


@task
def messageboard_audit(
    agent: str = "claude",
    model: str = "claude-opus-5",
    config: str = "default",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    return Task(
        dataset=[Sample(input=_prompt_for(config), id=f"{agent}:{model}:{config}")],
        solver=cli_agent(agent=agent, model=model, config=config),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
    )


@task
def messageboard_audit_replay(
    runs_glob: str = "*",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    samples = []
    for d in sorted((REPO / "runs").glob(runs_glob)):
        if not (d / "transcript.jsonl").exists() or d.name.startswith("failed"):
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists() or _json.loads(meta_path.read_text()).get("exit_code") != 0:
            continue
        agent = next((a for a in ("codex", "react") if f"_{a}_" in d.name), "claude")
        samples.append(
            Sample(input=(d / "work" / "prompt.txt").read_text() if (d / "work" / "prompt.txt").exists() else "", id=d.name, metadata={"run_dir": str(d), "agent": agent})
        )
    if not samples:
        raise RuntimeError(f"no runs matched runs/{runs_glob}")
    return Task(
        dataset=samples,
        solver=replay(),
        scorer=[rubric_scorer(judge=judge), process_metrics()],
    )
