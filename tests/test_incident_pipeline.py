"""The incident registry is the complete executable integration contract."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from messageboard_audit_bench.incidents import (
    config_names,
    data_variants,
    incident_for_variant,
    incidents,
)
from messageboard_audit_bench.task import incident_task

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import incident_pipeline as pipeline  # noqa: E402
from incident_pipeline import validate  # noqa: E402


def test_registry_describes_all_three_incidents() -> None:
    assert tuple(incidents()) == ("wiki", "mythos5", "rubyhack")
    assert set(config_names()) == {"blind", "context", "blind-anthropic", "mythos5", "rubyhack"}
    assert data_variants() == {
        "raw_stripped",
        "verbatim",
        "verbatim_anthropic",
        "mythos5",
        "rubyhack",
    }
    assert incident_for_variant("verbatim_anthropic").id == "wiki"


def test_every_registered_incident_passes_the_offline_pipeline() -> None:
    failures = {}
    for item in incidents().values():
        if problems := validate(item).problems:
            failures[item.id] = problems
    assert failures == {}


def test_incident_config_defaults_reach_the_actual_task() -> None:
    expected = {"wiki": 20, "mythos5": 20, "rubyhack": 10}
    for incident_id, minutes in expected.items():
        item = incidents()[incident_id]
        task = incident_task(item.runtime["default_config"])
        assert task.dataset[0].metadata["budget_min"] == minutes
        assert task.dataset[0].metadata["data_variant"] == item.corpus["primary_variant"]
        assert len(task.scorer) == 4


def test_new_command_creates_the_complete_candidate_scaffold(tmp_path, monkeypatch) -> None:
    for directory in ("benchmark/incidents", "benchmark/rubrics", "configs", "scripts"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".gitignore").write_text("")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    result = pipeline.cmd_new(
        SimpleNamespace(
            id="example",
            title="Example incident",
            investigation_url="https://example.org/investigation",
            data_file="records.jsonl",
            prefix="EX",
            minutes=10,
        )
    )

    manifest = (tmp_path / "benchmark/incidents/example.json").read_text()
    assert result == 0
    assert '"finding_mode": "example"' in manifest
    assert (tmp_path / "configs/example.toml").is_file()
    assert (tmp_path / "scripts/build_example_data.py").is_file()
    assert (tmp_path / "benchmark/rubrics/build_rubrics_example.py").is_file()
    assert (tmp_path / "benchmark/rubrics/example/claims_example.json").is_file()
    assert "/data/example" in (tmp_path / ".gitignore").read_text()
