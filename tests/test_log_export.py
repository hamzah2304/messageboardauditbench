from pathlib import Path
from types import SimpleNamespace

from messageboard_audit_bench.log_export import export_records, records_from_log


def _log(*, backend: str = "inspect", report: str = "# Report", exit_code: int = 0):
    sample = SimpleNamespace(
        id="claude:inspect:blind:20m",
        epoch=2,
        input="Investigate this.\n",
        output=SimpleNamespace(completion=report),
        metadata={
            "backend": backend,
            "agent": "claude",
            "scaffold": "claude-code",
            "model": "anthropic/claude-test",
            "config": "blind",
            "budget_min": 20,
            "data_variant": "verbatim",
            "effort": "xhigh",
            "cache_read_tokens": 10,
            "usage_source": "inspect",
            "exit_code": exit_code,
        },
        error=None,
    )
    return SimpleNamespace(samples=[sample])


def test_records_only_select_requested_backend_and_real_reports() -> None:
    assert len(records_from_log(_log(), "native.eval", backend="inspect")) == 1
    assert not records_from_log(
        _log(backend="subscription"), "old.eval", backend="inspect"
    )
    assert not records_from_log(
        _log(report="(no report written)"), "empty.eval", backend="inspect"
    )


def test_export_groups_by_scaffold_and_keeps_backend_in_index(tmp_path: Path) -> None:
    records = records_from_log(_log(), "native.eval", backend="inspect")
    rows = export_records(records, tmp_path)

    assert len(rows) == 1
    assert rows[0]["backend"] == "inspect"
    assert rows[0]["scaffold"] == "claude-code"
    assert rows[0]["source"] == "inspect_eval_log"
    assert (tmp_path / rows[0]["report"]).is_file()
    group = next(
        path
        for path in tmp_path.iterdir()
        if path.is_dir() and path.name.startswith("claude-code_blind_")
    )
    assert (group / "CONFIG.json").is_file()


def test_same_scaffold_can_pool_transports(tmp_path: Path) -> None:
    native = records_from_log(_log(), "native.eval", backend=None)
    subscription = records_from_log(
        _log(backend="subscription"), "subscription.eval", backend=None
    )

    rows = export_records([*native, *subscription], tmp_path)

    assert {row["backend"] for row in rows} == {"inspect", "subscription"}
    assert (
        len(
            [
                path
                for path in tmp_path.iterdir()
                if path.is_dir() and path.name != "prompts"
            ]
        )
        == 1
    )


def test_records_fall_back_to_inspect_model_when_task_metadata_omits_it() -> None:
    log = _log()
    del log.samples[0].metadata["model"]
    log.samples[0].output.model = "openai/gpt-test"

    [record] = records_from_log(log, "native.eval", backend="inspect")

    assert record.metadata["model"] == "openai/gpt-test"


def test_nonzero_exit_is_exported_only_when_partial_runs_are_requested(
    tmp_path: Path,
) -> None:
    records = records_from_log(_log(exit_code=124), "timeout.eval", backend="inspect")

    assert records[0].partial is True
    assert export_records(records, tmp_path / "default") == []
    rows = export_records(records, tmp_path / "included", include_partial=True)
    assert rows[0]["partial"] is True
