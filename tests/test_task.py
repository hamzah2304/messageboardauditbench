from importlib.metadata import entry_points

import pytest
from inspect_ai._util.registry import registry_info

import messageboard_audit_bench.task as task_module
from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.task import (
    _CONFIGS,
    EVAL_VERSION,
    _load_config,
    _prompt_for,
)
from messageboard_audit_bench.task import messageboard_audit_bench as build_task


def test_task_has_stable_sample_and_version() -> None:
    task = build_task(agent="codex", config="blind")

    assert task.version == EVAL_VERSION == "7-A"
    assert len(task.dataset) == 1
    assert task.dataset[0].id == "codex:inspect:blind:20m"
    assert task.dataset[0].metadata == {
        "agent": "codex",
        "scaffold": "codex-cli",
        "backend": "inspect",
        "isolation": "network_none",
        "config": "blind",
        "budget_min": 20,
        "min_runtime_fraction": 0.75,
        "minimum_runtime_seconds": 900,
        "data_variant": "verbatim",
        "effort": "xhigh",
        "report_min_words": 2500,
        "report_max_words": 3000,
        "report_accept_min_words": 0,
        "report_accept_max_words": 3200,
    }


def test_prompt_uses_named_config() -> None:
    prompt = _prompt_for("blind")

    assert "Time budget: you have 20 minutes" in prompt
    assert (
        "at least 75% of the 20-minute time budget has elapsed (about 15 minutes)"
        in prompt
    )
    assert "{{BUDGET_MIN}}" not in prompt
    assert "{{REPORT_MIN_WORDS}}" not in prompt
    assert "{{REPORT_MAX_WORDS}}" not in prompt
    assert "between 2,500 and 3,000 words" in prompt
    assert prompt.count("3,000 words is a strict upper limit") == 1
    assert "3,100" not in prompt


def test_command_time_limit_overrides_prompt_and_metadata() -> None:
    task = build_task(
        agent="react",
        config="blind",
        time_limit_minutes=37,
    )

    assert "Time budget: you have 37 minutes" in task.dataset[0].input
    assert task.dataset[0].metadata["budget_min"] == 37
    assert task.dataset[0].id.endswith(":37m")
    assert task.metadata["time_limit_minutes"] == 37
    assert task.metadata["hard_time_limit_minutes"] == 42
    assert task.metadata["min_runtime_fraction"] == 0.75
    assert task.metadata["minimum_runtime_seconds"] == int(37 * 60 * 0.75)


def test_minimum_runtime_policy_is_configurable_in_prompt_and_metadata() -> None:
    task = build_task(
        agent="react",
        config="blind",
        time_limit_minutes=37,
        min_runtime_fraction=0.6,
    )

    assert (
        "at least 60% of the 37-minute time budget has elapsed (about 22.2 minutes)"
        in (task.dataset[0].input)
    )
    assert task.dataset[0].metadata["min_runtime_fraction"] == 0.6
    assert task.dataset[0].metadata["minimum_runtime_seconds"] == 1332
    assert task.metadata["minimum_runtime_seconds"] == 1332


def test_zero_minimum_runtime_explicitly_disables_policy() -> None:
    task = build_task(min_runtime_fraction=0)

    assert "Minimum working period: disabled for this run." in task.dataset[0].input
    assert task.metadata["minimum_runtime_seconds"] == 0


def test_command_time_limit_reaches_solver(monkeypatch) -> None:
    captured = {}

    def capture_subscription_agent(**kwargs):
        captured.update(kwargs)
        return task_module.replay()

    monkeypatch.setattr(task_module, "subscription_agent", capture_subscription_agent)
    task_module.messageboard_audit_bench(
        agent="codex",
        backend="subscription",
        allow_networked_subscription=True,
        subscription_model="gpt-test",
        config="blind",
        time_limit_minutes=37,
    )

    assert captured["time_limit_minutes"] == 37
    assert captured["timeout_minutes"] == 42
    assert captured["prompt"] == "blind-v2"
    assert captured["data_variant"] == "verbatim"
    assert captured["effort"] == "xhigh"
    assert captured["min_runtime_fraction"] == 0.75


def test_subscription_time_limit_has_shutdown_and_host_grace(monkeypatch) -> None:
    captured = {}

    def capture_subscription_agent(**kwargs):
        captured.update(kwargs)
        return task_module.replay()

    monkeypatch.setattr(task_module, "subscription_agent", capture_subscription_agent)
    task = task_module.messageboard_audit_bench(
        backend="subscription",
        allow_networked_subscription=True,
        subscription_model="claude-test",
        config="blind",
    )

    assert captured["time_limit_minutes"] == 20
    assert captured["timeout_minutes"] == 25
    assert task.metadata["hard_time_limit_minutes"] == 25
    assert task.metadata["host_cleanup_guard_minutes"] == 30


@pytest.mark.parametrize("value", [0, -1, True])
def test_time_limit_must_be_positive_integer(value) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_task(time_limit_minutes=value)


@pytest.mark.parametrize("value", [-0.01, 1, float("inf"), True, "0.75"])
def test_min_runtime_fraction_requires_finite_proportion_below_one(value) -> None:
    with pytest.raises(ValueError, match="finite number in \\[0, 1\\)"):
        build_task(min_runtime_fraction=value)


def test_agent_must_be_supported() -> None:
    with pytest.raises(ValueError, match="unsupported agent"):
        build_task(agent="unknown")


def test_backend_must_be_supported() -> None:
    with pytest.raises(ValueError, match="unsupported backend"):
        build_task(backend="unknown")


def test_native_model_uses_inspect_cli() -> None:
    with pytest.raises(ValueError, match="use Inspect's --model"):
        build_task(subscription_model="claude-test")


def test_subscription_requires_explicit_cli_model() -> None:
    with pytest.raises(ValueError, match="requires -T subscription_model"):
        build_task(backend="subscription")


def test_subscription_does_not_require_an_unrelated_inspect_model() -> None:
    task = build_task(
        backend="subscription",
        allow_networked_subscription=True,
        subscription_model="claude-opus-5",
    )

    assert str(task.model) == "mockllm/model"
    assert task.time_limit is None
    assert task.dataset[0].metadata["subscription_model"] == "claude-opus-5"


def test_native_configures_inspect_cache_limit_and_sandbox() -> None:
    task = build_task(agent="claude", time_limit_minutes=9)
    service = task.sandbox.config.services["default"]

    assert task.config.cache_prompt is True
    assert task.config.reasoning_effort == "xhigh"
    assert task.time_limit == 14 * 60
    assert service.network_mode == "none"
    assert service.working_dir == "/work"
    assert service.volumes[0].endswith("/data/verbatim:/work/data:ro")
    assert service.build.dockerfile == "sandbox/docker/Dockerfile"


def test_native_threads_config_tools_to_agent_solver(monkeypatch) -> None:
    captured = {}

    def capture_native_agent(**kwargs):
        captured.update(kwargs)
        return task_module.replay()

    monkeypatch.setattr(task_module, "inspect_native_agent", capture_native_agent)
    task_module.messageboard_audit_bench(agent="claude", config="blind")

    assert captured["agent"] == "claude"
    assert captured["time_limit_seconds"] == 20 * 60
    assert "WebSearch" in captured["claude_disallowed_tools"]
    assert captured["report_min_words"] == 2500
    assert captured["report_max_words"] == 3000
    assert captured["min_runtime_fraction"] == 0.75


@pytest.mark.parametrize("name", ["../blind", "blind_mode", "", "/tmp/config"])
def test_config_rejects_paths_and_invalid_names(name: str) -> None:
    with pytest.raises(ValueError, match="invalid config name"):
        _load_config(name)


def test_config_error_lists_names() -> None:
    with pytest.raises(ValueError, match="available configs: blind, context"):
        _load_config("blind-20")


@pytest.mark.parametrize("config_name", _CONFIGS)
def test_all_public_configs_build(config_name: str) -> None:
    cfg = _load_config(config_name)

    assert cfg["prompt"] == ("blind-v2" if config_name == "blind" else config_name)
    assert (repo_root() / "sandbox" / "prompts" / f"{cfg['prompt']}.txt").is_file()
    assert cfg["data_variant"] in {"raw_stripped", "verbatim"}
    assert build_task(config=config_name).dataset[0].id.endswith(f":{config_name}:20m")


def test_inspect_entry_point_exposes_namespaced_task() -> None:
    entry_point = next(
        ep
        for ep in entry_points(group="inspect_ai")
        if ep.name == "messageboard_audit_bench"
    )

    assert entry_point.value == "messageboard_audit_bench"
    assert entry_point.load().__name__ == "messageboard_audit_bench"
    assert (
        registry_info(build_task).name
        == "messageboard_audit_bench/messageboard_audit_bench"
    )
