from pathlib import Path
from types import SimpleNamespace

from messageboard_audit_bench.log_export import export_records, records_from_log


def _log(*, backend: str = "inspect", report: str = "# Report", exit_code: int = 0,
         length_meta: dict | None = None):
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
    if length_meta:
        sample.metadata.update(length_meta)
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


def test_rejected_native_reports_skip_by_default_and_keep_flags_when_requested(tmp_path: Path) -> None:
    bounds = {
        "report_min_words": 2,
        "report_max_words": 3,
        "report_accept_min_words": 1,
        "report_accept_max_words": 4,
    }
    records = records_from_log(
        _log(report="word " * 5, length_meta=bounds), "native.eval", backend="inspect"
    )

    assert export_records(records, tmp_path / "default") == []
    [row] = export_records(records, tmp_path / "included", include_rejected=True)
    assert row["report_rejected"] is True
    assert row["report_words"] == 5
    assert row["report_length_compliant"] is False
    assert row["report_accept_max_words"] == 4


def test_disabled_native_length_bounds_are_not_rejected(tmp_path: Path) -> None:
    records = records_from_log(
        _log(report="word", length_meta={"report_min_words": 0, "report_max_words": 0}),
        "native.eval", backend="inspect",
    )

    [row] = export_records(records, tmp_path)
    assert row["report_rejected"] is False
    assert row["report_length_compliant"] is None


def test_index_carries_outcome_fields_and_served_model_tag(tmp_path: Path) -> None:
    from messageboard_audit_bench.log_export import export_graded_inputs

    log = _log(report="# Report\n\nfour words here now")
    log.samples[0].metadata.update(
        model="claude-opus-5",
        model_served="claude-opus-4-8",
        model_fallback={"chain": ["claude-opus-5", "claude-opus-4-8"]},
            terminal_refusal=False,
            wall_seconds=1234,
            report_min_words=2,
            report_max_words=3,
            report_accept_min_words=1,
            report_accept_max_words=5,
        )
    rows = export_records(
        records_from_log(log, "native.eval", backend="inspect"), tmp_path,
        include_rejected=True,
    )
    row = rows[0]
    assert row["model"] == "claude-opus-5"
    assert row["model_served"] == "claude-opus-4-8"
    assert row["model_fallback"]["chain"][-1] == "claude-opus-4-8"
    assert row["terminal_refusal"] is False
    assert row["wall_seconds"] == 1234
    assert row["report_words"] == 6
    assert row["report_length_compliant"] is False
    assert "_served-claude-opus-4-8" in row["report"]

    graded = tmp_path / "graded_inputs"
    written = export_graded_inputs(rows, tmp_path, graded, "round4")
    assert written == [graded / "round4_blind20" / "b20__claude__claude-opus-5__rep2_served-claude-opus-4-8.md"]
    assert written[0].read_text() == "# Report\n\nfour words here now"
    index = (graded / "round4_blind20" / "_index.jsonl").read_text().splitlines()
    assert len(index) == 1 and '"graded_input"' in index[0]
