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

  * `messageboard_audit_bench_continue` resumes one finished ReAct sample from
    its eval log: the stored conversation is the prefill, the report it wrote
    is put back in the sandbox, and a follow-up message asks for more.
      inspect eval messageboard_audit_bench/messageboard_audit_bench_continue \
        -T parent_log=logs/round4/react-kimi-k3/120m/<log>.eval -T parent_epoch=1

View any result with:  inspect view
"""

from __future__ import annotations

import json
import re

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import (
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    GenerateConfig,
)
from inspect_ai.util import (
    ComposeBuild,
    ComposeConfig,
    ComposeService,
    SandboxEnvironmentSpec,
)

from messageboard_audit_bench import runtime_policy
from messageboard_audit_bench import sandbox as _sandbox_policy  # noqa: F401
from messageboard_audit_bench.grading.core import variant_for_data
from messageboard_audit_bench.grading.scorer import sheet_scorer
from messageboard_audit_bench.native import inspect_native_agent
from messageboard_audit_bench.report_length import (
    acceptance_limits,
    limits,
    render_prompt,
)
from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.sandbox import IsolatedDockerSandbox  # noqa: F401
from messageboard_audit_bench.scorer import (
    process_metrics,
    report_length,
    rubric_scorer,
)
from messageboard_audit_bench.solver import replay, subscription_agent

EVAL_VERSION = "6-B"
_CONFIG_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CONFIGS = ("blind", "context", "blind-anthropic")
_SUPPORTED_AGENTS = {"claude", "codex", "react"}
_BACKENDS = {"inspect", "subscription"}
DEFAULT_TIME_LIMIT_MINUTES = 20
TIMEOUT_GRACE_MINUTES = 5


def _load_config(config_name: str) -> dict:
    """Load one of the repository's named benchmark configurations."""
    repo = repo_root()
    if not _CONFIG_NAME.fullmatch(config_name):
        raise ValueError(
            f"invalid config name {config_name!r}; use a name from {repo / 'configs'}"
        )
    if config_name not in _CONFIGS:
        raise ValueError(
            f"unknown config {config_name!r}; available configs: {', '.join(_CONFIGS)}"
        )
    path = repo / "configs" / f"{config_name}.toml"
    if not path.is_file():
        raise RuntimeError(f"config file is missing: {path}")

    import tomllib

    cfg = tomllib.loads(path.read_text())
    acceptance_limits(cfg)
    return cfg


def _time_limit(time_limit_minutes: int | None) -> int:
    value = (
        DEFAULT_TIME_LIMIT_MINUTES if time_limit_minutes is None else time_limit_minutes
    )
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("time_limit_minutes must be a positive integer")
    return value


def _min_runtime_fraction(min_runtime_fraction: float | None) -> float:
    """Validate the proportion of an agent budget that must be used.

    Zero is intentionally allowed as an explicit opt-out for ablations and
    backwards-compatible comparisons. A value of one would leave no time for a
    normal completion, so it is rejected.
    """
    value = (
        runtime_policy.DEFAULT_MIN_RUNTIME_FRACTION
        if min_runtime_fraction is None
        else min_runtime_fraction
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("min_runtime_fraction must be a finite number in [0, 1)")
    try:
        result = runtime_policy.fraction(value)
    except ValueError as exc:
        raise ValueError(
            "min_runtime_fraction must be a finite number in [0, 1)"
        ) from exc
    if result >= 1:
        raise ValueError("min_runtime_fraction must be a finite number in [0, 1)")
    return result


def _minimum_runtime_instruction(budget_seconds: int, fraction: float) -> str:
    """The shared, parameterized prompt contract for early completion."""
    return runtime_policy.instruction(fraction, budget_seconds / 60)


def _prompt_for(
    config_name: str,
    time_limit_minutes: int | None = None,
    min_runtime_fraction: float | None = None,
) -> str:
    cfg = _load_config(config_name)
    budget_minutes = _time_limit(time_limit_minutes)
    fraction = _min_runtime_fraction(min_runtime_fraction)
    text = (repo_root() / "sandbox" / "prompts" / f"{cfg['prompt']}.txt").read_text()
    return render_prompt(text, budget_minutes, *limits(cfg)) + (
        _minimum_runtime_instruction(budget_minutes * 60, fraction)
    )


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
    # A task worktree holds per-file symlinks to the primary checkout's data.
    # A bind mount cannot follow those, so mount the directory they resolve to.
    targets = {p.resolve().parent for p in data_dir.glob("*.jsonl") if p.is_symlink()}
    if len(targets) == 1:
        data_dir = targets.pop()
    elif targets:
        raise RuntimeError(f"data/{data_variant} symlinks point at several directories")
    return SandboxEnvironmentSpec(
        type="isolated-docker",
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
                    user="1000:1000",
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                    working_dir="/work",
                    volumes=[f"{data_dir}:/work/data:ro"],
                )
            }
        ),
    )


def _scorers(judge: str, rubric: str | None, data_variant: str | None = None) -> list:
    """The always-on scorers, plus the rubric judge when a run asks for it.

    The sheet judge follows the data: a run on verbatim_anthropic is graded against the
    swapped sheets and answer key (core.variant_for_data)."""
    scorers = [rubric_scorer(judge=judge), process_metrics(), report_length()]
    if rubric:
        scorers.insert(
            0, sheet_scorer(rubric=rubric, judge=judge, variant=variant_for_data(data_variant))
        )
    return scorers


@task
def messageboard_audit_bench(
    agent: str = "claude",
    backend: str = "inspect",
    subscription_model: str | None = None,
    config: str = "blind",
    allow_networked_subscription: bool = True,
    time_limit_minutes: int | None = None,
    min_runtime_fraction: float = 0.75,
    judge: str = "anthropic/claude-sonnet-5",
    rubric: str | None = None,
) -> Task:
    """Run one sandboxed message-board audit.

    Args:
        agent: Agent harness to launch: ``claude``, ``codex``, or ``react``.
        backend: ``inspect`` for first-class Inspect execution (Inspect SWE for
            Claude Code/Codex), or ``subscription`` for the original CLI login.
        subscription_model: CLI model identifier for the subscription backend.
            Native runs select their model with Inspect's ``--model`` option.
        config: Named prompt/data/effort configuration from ``configs/``.
        time_limit_minutes: Trial budget in minutes. Overrides the named
            config's 20-minute default. Native runs have a separate
            five-minute outer guard for cleanup and log recovery.
        min_runtime_fraction: Fraction of the agent budget that must elapse
            before normal completion is accepted. Defaults to ``0.75``; set
            ``0`` to disable this continuation policy for an ablation.
        judge: Inspect model used to grade the report. A ``grader`` model role,
            when supplied to Inspect, takes precedence over this value.
        rubric: When set (``v2`` or ``tldrh``), also grade the report against
            that rubric's sheets inline. Off by default: it is eight judge
            calls per sample, and grading is normally a separate pass over
            staged reports (``grade_reports``), so a run does not silently pay
            for it.
    """
    cfg = _load_config(config)
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
    if backend == "subscription" and not allow_networked_subscription:
        raise ValueError(
            "subscription uses the restricted proxy with shell-accessible credentials; choose backend=inspect for offline tools"
        )
    budget_min = _time_limit(time_limit_minutes)
    runtime_fraction = _min_runtime_fraction(min_runtime_fraction)
    minimum_runtime_seconds = runtime_policy.minimum_runtime_seconds(
        budget_min * 60, runtime_fraction
    )
    cleanup_timeout_minutes = budget_min + TIMEOUT_GRACE_MINUTES
    sample_metadata = {
        "agent": agent,
        "scaffold": _scaffold(agent, backend),
        "backend": backend,
        "isolation": (
            "network_none" if backend == "inspect" else "provider_network_shared"
        ),
        "config": config,
        "budget_min": budget_min,
        "min_runtime_fraction": runtime_fraction,
        "minimum_runtime_seconds": minimum_runtime_seconds,
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
        input=_prompt_for(config, budget_min, runtime_fraction),
        id=f"{agent}:{backend}:{config}:{budget_min}m",
        metadata=sample_metadata,
    )
    if backend == "inspect":
        selected_solver = inspect_native_agent(
            agent=agent,
            time_limit_seconds=budget_min * 60,
            claude_disallowed_tools=cfg.get("claude_disallowed_tools", []),
            report_min_words=limits(cfg)[0],
            report_max_words=limits(cfg)[1],
            min_runtime_fraction=runtime_fraction,
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
            allow_networked_subscription=allow_networked_subscription,
            config=config,
            time_limit_minutes=budget_min,
            timeout_minutes=cleanup_timeout_minutes,
            prompt=cfg["prompt"],
            data_variant=cfg["data_variant"],
            effort=cfg["effort"],
            min_runtime_fraction=runtime_fraction,
        )
        selected_sandbox = None
        generate_config = GenerateConfig()
    return Task(
        dataset=[sample],
        solver=selected_solver,
        scorer=_scorers(judge, rubric, cfg["data_variant"]),
        config=generate_config,
        # Subscription calls occur outside Inspect's model provider. Supplying
        # the no-cost mock model keeps Inspect from requiring an unrelated
        # default; metadata records the actual CLI model.
        model="mockllm/model" if backend == "subscription" else None,
        sandbox=selected_sandbox,
        # Native execution gets a scoped budget plus this outer cleanup guard.
        # The subscription runner already owns its hard timeout; another equal
        # Inspect timeout can interrupt transcript folding and report recovery.
        time_limit=(cleanup_timeout_minutes * 60 if backend == "inspect" else None),
        version=EVAL_VERSION,
        metadata={
            "benchmark": "MessageBoardAuditBench",
            "backend": backend,
            "scaffold": _scaffold(agent, backend),
            "config": config,
            "time_limit_minutes": budget_min,
            "min_runtime_fraction": runtime_fraction,
            "minimum_runtime_seconds": minimum_runtime_seconds,
            "hard_time_limit_minutes": cleanup_timeout_minutes,
            "host_cleanup_guard_minutes": (
                cleanup_timeout_minutes + TIMEOUT_GRACE_MINUTES
                if backend == "subscription"
                else None
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
    include_failed: bool = True,
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Import local run artifacts into Inspect without rerunning agents."""
    samples = []
    for d in sorted((repo_root() / "runs").glob(runs_glob)):
        if not (d / "transcript.jsonl").exists():
            continue
        meta_path = d / "meta.json"
        # Nonzero exits can still contain a valuable partial trajectory. The
        # replay solver records the exit status and missing-report state.
        if not meta_path.exists() or (
            not include_failed
            and json.loads(meta_path.read_text()).get("exit_code") != 0
        ):
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


def _load_followup_config(config_name: str) -> dict:
    """Load a continuation config; these are not fresh-trial conditions."""
    repo = repo_root()
    if not _CONFIG_NAME.fullmatch(config_name):
        raise ValueError(f"invalid config name {config_name!r}")
    path = repo / "configs" / f"{config_name}.toml"
    if not path.is_file():
        raise RuntimeError(f"config file is missing: {path}")

    import tomllib

    cfg = tomllib.loads(path.read_text())
    acceptance_limits(cfg)
    return cfg


@task
def messageboard_audit_bench_continue(
    parent_log: str,
    parent_epochs: str = "all",
    config: str = "followup-5k",
    judge: str = "anthropic/claude-sonnet-5",
) -> Task:
    """Continue finished ReAct samples with a follow-up request.

    The parent sample's messages become the new sample's input, so the model
    sees exactly the conversation it had (Inspect's ReAct agent re-inserts the
    identical system message it prepended the first time, which is why the
    stored one is dropped). The parent's report is written back to
    ``/work/report.md`` before the agent starts. Other scratch files the agent
    made are not recoverable from the log; the follow-up prompt says so.

    Args:
        parent_log: Path to the round's ``.eval`` log holding the parent samples.
        parent_epochs: ``all`` or a comma-separated list of epochs to continue.
        config: Continuation config from ``configs/``; its ``budget_min`` is
            the extra time and its prompt is the follow-up message.
        judge: Inspect model used to grade the report.
    """
    cfg = _load_followup_config(config)
    log = read_eval_log(parent_log)
    if log.eval.task_args.get("agent") != "react" or (
        log.eval.task_args.get("backend") != "inspect"
    ):
        raise ValueError(
            "continuation supports react samples run on the inspect backend"
        )
    wanted = (
        None
        if parent_epochs == "all"
        else {int(value) for value in str(parent_epochs).split(",") if value.strip()}
    )
    parents = [s for s in log.samples or [] if wanted is None or s.epoch in wanted]
    if not parents:
        raise ValueError(f"no epochs {parent_epochs} in {parent_log}")
    budget_min = _time_limit(int(cfg["budget_min"]))
    runtime_fraction = _min_runtime_fraction(cfg.get("min_runtime_fraction", 0))
    minimum_runtime_seconds = runtime_policy.minimum_runtime_seconds(
        budget_min * 60, runtime_fraction
    )
    cleanup_timeout_minutes = budget_min + TIMEOUT_GRACE_MINUTES
    followup = render_prompt(
        (repo_root() / "sandbox" / "prompts" / f"{cfg['prompt']}.txt").read_text(),
        budget_min,
        *limits(cfg),
    ) + _minimum_runtime_instruction(budget_min * 60, runtime_fraction)
    samples = []
    reports: dict[int, str] = {}
    for parent in parents:
        report = parent.output.completion if parent.output else ""
        if not parent.metadata.get("report_written") or not report.strip():
            raise ValueError(
                f"parent epoch {parent.epoch} has no report to continue from"
            )
        reports[parent.epoch] = report
        history = _close_dangling_tool_calls(list(parent.messages))
        if history and isinstance(history[0], ChatMessageSystem):
            history = history[1:]
        messages = [*history, ChatMessageUser(content=followup)]
        samples.append(
            Sample(
                input=messages,
                id=(
                    f"react:inspect:{config}:{budget_min}m:"
                    f"from{parent.metadata.get('budget_min')}m:e{parent.epoch}"
                ),
                metadata=_continuation_sample_metadata(
                    cfg,
                    config,
                    budget_min,
                    runtime_fraction,
                    minimum_runtime_seconds,
                    parent,
                    parent_log,
                    log.eval.model,
                ),
            )
        )
    return Task(
        dataset=samples,
        solver=inspect_native_agent(
            agent="react",
            time_limit_seconds=budget_min * 60,
            claude_disallowed_tools=cfg.get("claude_disallowed_tools", []),
            report_min_words=limits(cfg)[0],
            report_max_words=limits(cfg)[1],
            min_runtime_fraction=runtime_fraction,
            seed_reports=reports,
        ),
        scorer=[rubric_scorer(judge=judge), process_metrics(), report_length()],
        config=GenerateConfig(cache_prompt=True, reasoning_effort=cfg["effort"]),
        model=log.eval.model,
        sandbox=_inspect_sandbox(cfg["data_variant"]),
        time_limit=cleanup_timeout_minutes * 60,
        version=EVAL_VERSION,
        metadata={
            "benchmark": "MessageBoardAuditBench",
            "mode": "continuation",
            "backend": "inspect",
            "scaffold": _scaffold("react", "inspect"),
            "config": config,
            "parent_log": str(parent_log),
            "parent_epochs": sorted(reports),
            "time_limit_minutes": budget_min,
            "min_runtime_fraction": runtime_fraction,
            "minimum_runtime_seconds": minimum_runtime_seconds,
            "hard_time_limit_minutes": cleanup_timeout_minutes,
            "data_variant": cfg["data_variant"],
            "report_min_words": limits(cfg)[0],
            "report_max_words": limits(cfg)[1],
            "report_accept_min_words": acceptance_limits(cfg)[0],
            "report_accept_max_words": acceptance_limits(cfg)[1],
        },
    )


UNANSWERED_TOOL_CALL = (
    "This tool call was not executed: the session was stopped at its time limit."
)


def _close_dangling_tool_calls(messages: list) -> list:
    """Answer tool calls the parent never got results for.

    A trial stopped at its time limit can end on an assistant turn whose tool
    calls were never run. OpenAI-style providers reject a conversation that
    continues past such a turn, so each unanswered call gets a tool result
    saying what happened, in the position its result would have taken.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ChatMessageTool)}
    closed: list = []
    for message in messages:
        closed.append(message)
        if isinstance(message, ChatMessageAssistant):
            for call in message.tool_calls or []:
                if call.id not in answered:
                    closed.append(
                        ChatMessageTool(
                            content=UNANSWERED_TOOL_CALL,
                            tool_call_id=call.id,
                            function=call.function,
                        )
                    )
    return closed


def _continuation_sample_metadata(
    cfg,
    config,
    budget_min,
    runtime_fraction,
    minimum_runtime_seconds,
    parent,
    parent_log,
    parent_model,
) -> dict:
    parent_meta = parent.metadata
    return {
        "agent": "react",
        "scaffold": _scaffold("react", "inspect"),
        "backend": "inspect",
        "isolation": "network_none",
        "mode": "continuation",
        "config": config,
        "budget_min": budget_min,
        "min_runtime_fraction": runtime_fraction,
        "minimum_runtime_seconds": minimum_runtime_seconds,
        "data_variant": cfg["data_variant"],
        "effort": cfg["effort"],
        "report_min_words": limits(cfg)[0],
        "report_max_words": limits(cfg)[1],
        "report_accept_min_words": acceptance_limits(cfg)[0],
        "report_accept_max_words": acceptance_limits(cfg)[1],
        "parent_log": str(parent_log),
        "parent_sample_id": parent.id,
        "parent_epoch": parent.epoch,
        "parent_config": parent_meta.get("config"),
        "parent_budget_min": parent_meta.get("budget_min"),
        "parent_report_words": parent_meta.get("report_words"),
        "parent_messages": len(parent.messages),
        "parent_model": parent_model,
    }
