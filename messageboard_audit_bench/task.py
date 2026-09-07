"""Inspect task for MessageBoardAuditBench.

Two entry points:

  * `messageboard_audit_bench` runs fresh trials. The default ``inspect``
    backend uses Inspect SWE and Inspect's own model, sandbox, limits, prompt
    caching, and live logs. The ``subscription`` backend preserves the original
    subscription-authenticated CLI runner.
      inspect eval messageboard_audit_bench/messageboard_audit_bench \
        -T agent=claude -T backend=inspect -T time_limit_minutes=30 \
        --model anthropic/claude-opus-4-1

  * `messageboard_audit_bench_replay` imports runs already on disk under runs/,
    so `inspect view` can render past or interrupted runs with scoring.
      inspect eval messageboard_audit_bench/messageboard_audit_bench_replay

View any result with:  inspect view
"""
from __future__ import annotations

import re

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig
from inspect_ai.util import (
    ComposeBuild,
    ComposeConfig,
    ComposeService,
    SandboxEnvironmentSpec,
)

from messageboard_audit_bench.native import inspect_native_agent
from messageboard_audit_bench.report_length import (
    acceptance_limits,
    instruction,
    limits,
)
from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.scorer import (
    process_metrics,
    report_length,
    rubric_scorer,
)
from messageboard_audit_bench.solver import replay, subscription_agent

EVAL_VERSION = "3-B"
_CONDITION_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CONDITIONS = ("blind", "context")
_SUPPORTED_AGENTS = {"claude", "codex", "react"}
_BACKENDS = {"inspect", "subscription"}
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

    cfg = tomllib.loads(path.read_text())
    acceptance_limits(cfg)
    return cfg


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
    return text.replace(
        "{{BUDGET_MIN}}", str(_time_limit(time_limit_minutes))
    ) + instruction(*limits(cfg))


def _scaffold(agent: str, backend: str) -> str:
    """Name the actual agent loop independently of its model transport."""
    if agent == "claude":
        return "claude-code"
    if agent == "codex":
        return "codex-cli"
    return "inspect-react" if backend == "inspect" else "legacy-react"


def _inspect_sandbox(data_variant: str) -> SandboxEnvironmentSpec:
    """Build the standard Inspect Docker sandbox with read-only benchmark data."""
    repo = repo_root().resolve()
    data_dir = (repo / "data" / data_variant).resolve()
    return SandboxEnvironmentSpec(
        type="docker",
        config=ComposeConfig(
            services={
                "default": ComposeService(
                    build=ComposeBuild(
                        context=str(repo),
                        dockerfile="sandbox/docker/Dockerfile",
                    ),
                    command="tail -f /dev/null",
                    init=True,
                    network_mode="none",
                    working_dir="/work",
                    volumes=[f"{data_dir}:/work/data:ro"],
                )
            }
        ),
    )


@task
def messageboard_audit_bench(
    agent: str = "claude",
    backend: str = "inspect",
    subscription_model: str | None = None,
    condition: str = "blind",
    time_limit_minutes: int | None = None,
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Run one sandboxed message-board audit.

    Args:
        agent: Agent harness to launch: ``claude``, ``codex``, or ``react``.
        backend: ``inspect`` for first-class Inspect execution (Inspect SWE for
            Claude Code/Codex), or ``subscription`` for the original CLI login.
        subscription_model: CLI model identifier for the subscription backend.
            Native runs select their model with Inspect's ``--model`` option.
        condition: Time-neutral prompt/data/effort condition from ``configs/``.
        time_limit_minutes: Trial budget in minutes. Overrides the named
            condition's 20-minute default. Native runs have a separate
            five-minute outer guard for cleanup and log recovery.
        judge: Inspect model used to grade the report. A ``grader`` model role,
            when supplied to Inspect, takes precedence over this value.
    """
    cfg = _load_condition(condition)
    if agent not in _SUPPORTED_AGENTS:
        raise ValueError(
            f"unsupported agent {agent!r}; choose from: {', '.join(sorted(_SUPPORTED_AGENTS))}"
        )
    if backend not in _BACKENDS:
        raise ValueError(
            f"unsupported backend {backend!r}; choose from: "
            f"{', '.join(sorted(_BACKENDS))}"
        )
    if backend == "inspect" and subscription_model is not None:
        raise ValueError(
            "subscription_model only applies to backend='subscription'; "
            "use Inspect's --model option for backend='inspect'"
        )
    if backend == "subscription" and not subscription_model:
        raise ValueError(
            "backend='subscription' requires -T subscription_model=<cli-model>"
        )
    budget_min = _time_limit(time_limit_minutes)
    cleanup_timeout_minutes = budget_min + TIMEOUT_GRACE_MINUTES
    sample_metadata = {
        "agent": agent,
        "scaffold": _scaffold(agent, backend),
        "backend": backend,
        "condition": condition,
        "budget_min": budget_min,
        "data_variant": cfg["data_variant"],
        "effort": cfg["effort"],
        "report_min_words": limits(cfg)[0],
        "report_max_words": limits(cfg)[1],
        "report_accept_min_words": acceptance_limits(cfg)[0],
        "report_accept_max_words": acceptance_limits(cfg)[1],
    }
    if subscription_model is not None:
        sample_metadata["subscription_model"] = subscription_model
    sample = Sample(
        input=_prompt_for(condition, budget_min),
        id=f"{agent}:{backend}:{condition}:{budget_min}m",
        metadata=sample_metadata,
    )
    if backend == "inspect":
        selected_solver = inspect_native_agent(
            agent=agent,
            time_limit_seconds=budget_min * 60,
            claude_disallowed_tools=cfg.get("claude_disallowed_tools", []),
            report_min_words=limits(cfg)[0],
            report_max_words=limits(cfg)[1],
        )
        selected_sandbox = _inspect_sandbox(cfg["data_variant"])
        generate_config = GenerateConfig(
            cache_prompt=True,
            reasoning_effort=cfg["effort"],
        )
    else:
        assert subscription_model is not None
        selected_solver = subscription_agent(
            agent=agent,
            model=subscription_model,
            condition=condition,
            time_limit_minutes=budget_min,
            timeout_minutes=budget_min,
            prompt=cfg["prompt"],
            data_variant=cfg["data_variant"],
            effort=cfg["effort"],
        )
        selected_sandbox = None
        generate_config = GenerateConfig()
    return Task(
        dataset=[sample],
        solver=selected_solver,
        scorer=[rubric_scorer(judge=judge), process_metrics(), report_length()],
        config=generate_config,
        # Subscription calls occur outside Inspect's model provider. Supplying
        # the no-cost mock model keeps Inspect from requiring an unrelated
        # default; metadata records the actual CLI model.
        model="mockllm/model" if backend == "subscription" else None,
        sandbox=selected_sandbox,
        # Native execution gets a scoped budget plus this outer cleanup guard.
        # The subscription runner already owns its hard timeout; another equal
        # Inspect timeout can interrupt transcript folding and report recovery.
        time_limit=(
            cleanup_timeout_minutes * 60 if backend == "inspect" else None
        ),
        version=EVAL_VERSION,
        metadata={
            "benchmark": "MessageBoardAuditBench",
            "backend": backend,
            "scaffold": _scaffold(agent, backend),
            "condition": condition,
            "time_limit_minutes": budget_min,
            "hard_time_limit_minutes": budget_min,
            "cleanup_time_limit_minutes": (
                cleanup_timeout_minutes if backend == "inspect" else None
            ),
            "data_variant": cfg["data_variant"],
            "report_min_words": limits(cfg)[0],
            "report_max_words": limits(cfg)[1],
            "report_accept_min_words": acceptance_limits(cfg)[0],
            "report_accept_max_words": acceptance_limits(cfg)[1],
        },
    )


@task
def messageboard_audit_bench_replay(
    runs_glob: str = "*",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Import local run artifacts into Inspect without rerunning agents."""
    samples = []
    for d in sorted((repo_root() / "runs").glob(runs_glob)):
        if not (d / "transcript.jsonl").exists() or d.name.startswith("failed"):
            continue
        meta_path = d / "meta.json"
        # Nonzero exits can still contain a valuable partial trajectory. The
        # replay solver records the exit status and missing-report state.
        if not meta_path.exists():
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
        scorer=[rubric_scorer(judge=judge), process_metrics(), report_length()],
        version=EVAL_VERSION,
        metadata={"benchmark": "MessageBoardAuditBench", "mode": "replay"},
    )
