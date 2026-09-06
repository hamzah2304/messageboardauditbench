from importlib.metadata import entry_points
from importlib.resources import files

import pytest
from inspect_ai._util.registry import registry_info

from messageboard_audit.task import EVAL_VERSION, _load_config, _prompt_for
from messageboard_audit.task import messageboard_audit as build_task


def test_task_has_stable_sample_and_version() -> None:
    task = build_task(agent="codex", model="gpt-test", config="blind-10")

    assert task.version == EVAL_VERSION == "1-A"
    assert len(task.dataset) == 1
    assert task.dataset[0].id == "codex:gpt-test:blind-10"
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


@pytest.mark.parametrize("name", ["../blind-10", "blind_10", "", "/tmp/config"])
def test_config_rejects_paths_and_invalid_names(name: str) -> None:
    with pytest.raises(ValueError, match="invalid config name"):
        _load_config(name)


def test_config_error_lists_available_names() -> None:
    with pytest.raises(ValueError, match="available configs:.*blind-20"):
        _load_config("does-not-exist")


def test_eval_metadata_file_is_packaged() -> None:
    assert files("messageboard_audit").joinpath("eval.yaml").is_file()


def test_inspect_entry_point_exposes_namespaced_task() -> None:
    entry_point = next(
        ep
        for ep in entry_points(group="inspect_ai")
        if ep.name == "messageboard_audit"
    )

    assert entry_point.value == "messageboard_audit"
    assert entry_point.load().__name__ == "messageboard_audit"
    assert registry_info(build_task).name == "messageboard_audit/messageboard_audit"
