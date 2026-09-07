from importlib.metadata import entry_points
from importlib.resources import files

import pytest
from inspect_ai._util.registry import registry_info

import messageboard_audit_bench.task as task_module
from messageboard_audit_bench.task import EVAL_VERSION, _load_config, _prompt_for
from messageboard_audit_bench.task import messageboard_audit_bench as build_task


def test_task_has_stable_sample_and_version() -> None:
    task = build_task(agent="codex", model="gpt-test", config="blind-10")

    assert task.version == EVAL_VERSION == "1-A"
    assert len(task.dataset) == 1
    assert task.dataset[0].id == "codex:gpt-test:blind-10:10m"
    assert task.dataset[0].metadata == {
        "agent": "codex",
        "model": "gpt-test",
        "config": "blind-10",
        "budget_min": 10,
        "data_variant": "verbatim",
        "effort": "xhigh",
    }


def test_prompt_uses_named_config() -> None:
    prompt = _prompt_for("blind-10")

    assert "Time budget: you have 10 minutes" in prompt
    assert "{{BUDGET_MIN}}" not in prompt


def test_command_time_limit_overrides_prompt_and_metadata() -> None:
    task = build_task(
        agent="react",
        model="openai/gpt-test",
        config="blind-10",
        time_limit_minutes=37,
    )

    assert "Time budget: you have 37 minutes" in task.dataset[0].input
    assert task.dataset[0].metadata["budget_min"] == 37
    assert task.dataset[0].id.endswith(":37m")
    assert task.metadata["time_limit_minutes"] == 37


def test_command_time_limit_reaches_solver(monkeypatch) -> None:
    captured = {}

    def capture_cli_agent(**kwargs):
        captured.update(kwargs)
        return task_module.replay()

    monkeypatch.setattr(task_module, "cli_agent", capture_cli_agent)
    task_module.messageboard_audit_bench(
        agent="codex",
        model="gpt-test",
        config="blind-10",
        time_limit_minutes=37,
    )

    assert captured["time_limit_minutes"] == 37
    assert captured["timeout_minutes"] == 42


def test_default_time_limit_preserves_config_timeout(monkeypatch) -> None:
    captured = {}

    def capture_cli_agent(**kwargs):
        captured.update(kwargs)
        return task_module.replay()

    monkeypatch.setattr(task_module, "cli_agent", capture_cli_agent)
    task_module.messageboard_audit_bench(config="blind-10")

    assert captured["time_limit_minutes"] == 10
    assert captured["timeout_minutes"] == 15


@pytest.mark.parametrize("value", [0, -1, True])
def test_time_limit_must_be_positive_integer(value) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_task(time_limit_minutes=value)


def test_agent_must_be_supported() -> None:
    with pytest.raises(ValueError, match="unsupported agent"):
        build_task(agent="unknown")


@pytest.mark.parametrize("name", ["../blind-10", "blind_10", "", "/tmp/config"])
def test_config_rejects_paths_and_invalid_names(name: str) -> None:
    with pytest.raises(ValueError, match="invalid config name"):
        _load_config(name)


def test_config_error_lists_available_names() -> None:
    with pytest.raises(ValueError, match="available configs:.*blind-20"):
        _load_config("does-not-exist")


def test_eval_metadata_file_is_packaged() -> None:
    assert files("messageboard_audit_bench").joinpath("eval.yaml").is_file()


def test_inspect_entry_point_exposes_namespaced_task() -> None:
    entry_point = next(
        ep
        for ep in entry_points(group="inspect_ai")
        if ep.name == "messageboard_audit_bench"
    )

    assert entry_point.value == "messageboard_audit_bench"
    assert entry_point.load().__name__ == "messageboard_audit_bench"
    assert registry_info(build_task).name == "messageboard_audit_bench/messageboard_audit_bench"
