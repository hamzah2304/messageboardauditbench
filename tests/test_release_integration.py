"""Public Inspect construction, continuation, and inline grading contracts."""
import json
from types import SimpleNamespace

import pytest
from inspect_ai import eval
from inspect_ai.model import ChatMessageUser, ModelOutput

import messageboard_audit_bench.task as tasks
from messageboard_audit_bench.grading.task import grade_reports, report_from_sample
from tests.test_grading_scorer import judge, sheet_reply


def parent_log(variant="verbatim", epochs=(1,)):
    return SimpleNamespace(
        eval=SimpleNamespace(task_args={"agent": "react"}, model="mockllm/model"),
        samples=[SimpleNamespace(
            epoch=e, id="parent", metadata={"report_written": True,
                "data_variant": variant, "budget_min": 30},
            output=ModelOutput.from_content("mockllm/model", "A report"),
            messages=[ChatMessageUser(content="Investigate")],
        ) for e in epochs],
    )


def test_followup_inherits_variant_and_accepts_default_backend(monkeypatch):
    monkeypatch.setattr(tasks, "read_eval_log", lambda _: parent_log("verbatim_anthropic"))
    task = tasks.messageboard_audit_bench_continue("parent.eval", config="followup-5k-min5")
    assert task.dataset[0].metadata["data_variant"] == "verbatim_anthropic"
    assert task.metadata["minimum_runtime_seconds"] == 300
    assert len(task.scorer) == 4
    assert "verbatim_anthropic" in task.sandbox.config.services["default"].volumes[0]


@pytest.mark.parametrize("epochs,wanted,match", [
    ((1,), "1,2", "missing"), ((1,1), "all", "one parent sample"),
])
def test_followup_rejects_ambiguous_or_missing_parents(monkeypatch, epochs, wanted, match):
    monkeypatch.setattr(tasks, "read_eval_log", lambda _: parent_log(epochs=epochs))
    with pytest.raises(ValueError, match=match):
        tasks.messageboard_audit_bench_continue("parent.eval", parent_epochs=wanted)


def test_followup_rejects_fresh_config():
    with pytest.raises(ValueError, match="not a continuation config"):
        tasks.messageboard_audit_bench_continue("unused.eval", config="blind")


@pytest.mark.parametrize("variant", ["verbatim", "verbatim_anthropic"])
def test_default_eval_runs_both_benchmark_graders(tmp_path, monkeypatch, variant):
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(tmp_path / "trace.log"))
    # Only replace execution: exercise the actual public task and its scorers
    # through Inspect, with canned judge replies instead of paid provider calls.
    task = tasks.messageboard_audit_bench(agent="react", data_variant=variant)
    task.sandbox = None
    task.solver = report_from_sample()
    replies = [sheet_reply("v2", i, 1) for i in range(8)] + [sheet_reply("tldrh", 0, 1)]
    model = judge(replies)
    [log] = eval(task, model="mockllm/model", model_roles={"grader": model},
        display="none", log_realtime=False, log_dir=str(tmp_path / "logs"))
    assert log.status == "success", log.error
    grades = [s.metadata["grade"] for s in log.samples[0].scores.values()
              if s.metadata and "grade" in s.metadata]
    assert {g["rubric"] for g in grades} == {"v2", "tldrh"}
    assert all(g["accuracy"] == 1 for g in grades)
    assert all(g.get("rubric_variant") == ("anthropic" if variant.endswith("anthropic") else None)
               for g in grades)


def test_staged_grading_preserves_variant_and_needs_no_agent_model(tmp_path):
    (tmp_path / "report.md").write_text("A report")
    (tmp_path / "_index.jsonl").write_text(json.dumps({
        "graded_input": "report.md", "data_variant": "verbatim_anthropic"}) + "\n")
    task = grade_reports(dir=str(tmp_path))
    assert task.dataset[0].metadata["data_variant"] == "verbatim_anthropic"
    assert str(task.model) == "mockllm/model"


def test_inline_grade_export_separates_epochs_and_reruns():
    from messageboard_audit_bench.grading.export import grades_in

    def log(eval_id):
        return SimpleNamespace(eval=SimpleNamespace(eval_id=eval_id), samples=[
            SimpleNamespace(epoch=e, metadata={}, scores={"sheet": SimpleNamespace(
                metadata={"grade": {"report": "react:inspect:blind:20m", "max": 38}}
            )}) for e in (1, 2)
        ])
    keys = [g["report"] for run in ("run-a", "run-b") for g in grades_in(log(run))]
    assert len(set(keys)) == 4
    assert all(":" not in key for key in keys)


def test_mixed_rubrics_export_without_overwriting(tmp_path):
    from messageboard_audit_bench.grading.export import export

    log = SimpleNamespace(samples=[SimpleNamespace(scores={
        mode: SimpleNamespace(metadata={"grade": {
            "report": "same_report", "max": 1, "grader": "test", "rubric": mode,
        }}) for mode in ("v2", "tldrh")
    })])
    paths = export(log, out_dir=tmp_path)
    assert len(paths) == len(set(paths)) == 2
    assert {json.loads(p.read_text())["rubric"] for p in paths} == {"v2", "tldrh"}


def test_followup_staging_keeps_parent_epochs(tmp_path):
    from messageboard_audit_bench.log_export import export_graded_inputs

    rows = []
    for epoch in (1, 2):
        name = f"report{epoch}.md"
        (tmp_path / name).write_text(f"Report {epoch}")
        rows.append(dict(report=name, config="followup-5k-min5", budget_min=10,
            agent="react", model="test", replicate=1, parent_budget_min=30,
            parent_epoch=epoch))
    paths = export_graded_inputs(rows, tmp_path, tmp_path / "staged", "test")
    assert len(set(paths)) == 2
    assert {p.read_text() for p in paths} == {"Report 1", "Report 2"}
    (tmp_path / rows[0]["report"]).write_text("Different report")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        export_graded_inputs(rows, tmp_path, tmp_path / "staged", "test")
