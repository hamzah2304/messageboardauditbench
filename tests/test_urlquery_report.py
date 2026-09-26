import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture
def report_fixture(tmp_path, monkeypatch):
    script = Path(__file__).parents[1] / "docs/assessments/transluce/summarize_pilot.py"
    summarize = runpy.run_path(str(script))["summarize"]
    monkeypatch.setitem(summarize.__globals__, "primary_root", lambda: tmp_path)
    root = tmp_path / "runs/urlquery"
    experiment, run = root / "pilot-test", root / "trial-test"
    experiment.mkdir(parents=True)
    run.mkdir()
    digest = "d" * 64
    (experiment / "plan.json").write_text(json.dumps({
        "benchmark_id": "urlquery", "status": "finished", "dataset_sha256": digest,
        "experiment_id": "pilot-test", "matrix": []}))
    (run / "meta.json").write_text(json.dumps({"benchmark_id": "urlquery", "dataset_sha256": digest,
                                             "run_id": "a" * 32, "report_words": 2}))
    (run / "report.md").write_text("# Report\n")
    (run / "cli.version.txt").write_text("codex-cli 0.156.1\n")
    (run / "audit.json").write_text(json.dumps({"served_model": {"requested": "gpt-6-astra", "served": None}}))
    attempts = [{"agent": "codex", "requested_model": "gpt-6-astra", "replicate": 1,
                 "run_dir": str(run), "termination": "normal", "report_exists": True},
                {"agent": "claude", "requested_model": "claude-opus-5-5", "replicate": 1,
                 "run_dir": None, "termination": "error", "report_exists": False}]
    (experiment / "results.json").write_text(json.dumps(attempts))
    reports = tmp_path / "reports/urlquery"
    (reports / "group").mkdir(parents=True)
    (reports / "group/report.md").write_text("# Report\n")
    (reports / "index.jsonl").write_text(json.dumps({"run_dir": run.name, "report": "group/report.md",
                                                    "benchmark_id": "urlquery", "dataset_sha256": digest}) + "\n")
    return summarize, experiment, run, reports


def test_summary_keeps_failures_and_unknown_served_identity(report_fixture):
    summarize, experiment, _, reports = report_fixture
    data = summarize([experiment], reports)
    assert len(data["attempts"]) == 2 and data["report_count"] == 1
    assert data["attempts"][0]["provider_served_model"]["served"] is None
    assert data["attempts"][0]["cli_version"] == "codex-cli 0.156.1"
    assert data["attempts"][0]["report_url"].startswith("http://localhost:8792/urlquery_")
    assert data["attempts"][1]["metadata_available"] is False
    assert "report_path" not in data["attempts"][1]
    assert data["grading"] == "none"


def test_summary_rejects_changed_export(report_fixture):
    summarize, experiment, _, reports = report_fixture
    (reports / "group/report.md").write_text("changed")
    with pytest.raises(ValueError, match="export differs"):
        summarize([experiment], reports)


def test_summary_labels_mixed_models_not_legacy_first_model(report_fixture):
    summarize, experiment, run, reports = report_fixture
    meta = json.loads((run / "meta.json").read_text())
    meta["model_fallback"] = {"chain": ["claude-opus-5-5", "claude-opus-4-8"], "trigger": "refusal"}
    (run / "meta.json").write_text(json.dumps(meta))
    (run / "audit.json").write_text(json.dumps({"served_model": {
        "served": "claude-opus-5-5", "observed_served_models": [
            {"model": "claude-opus-5-5"}, {"model": "claude-opus-4-8"}, {"model": "<synthetic>"}]}}))
    row = summarize([experiment], reports)["attempts"][0]
    assert row["model_identity"]["mixed_model"] is True
    assert row["model_identity"]["single_served_model"] is None
    assert "claude-opus-4-8 (fallback)" in row["report_label"]


def test_summary_rejects_duplicate_and_cross_benchmark_runs(report_fixture):
    summarize, experiment, run, reports = report_fixture
    with pytest.raises(ValueError, match="duplicate attempt"):
        summarize([experiment, experiment], reports)
    meta = json.loads((run / "meta.json").read_text())
    meta["benchmark_id"] = "messageboard"
    (run / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="cross-benchmark"):
        summarize([experiment], reports)


def test_selected_checks_distinguish_request_and_response_content(tmp_path, monkeypatch):
    script = Path(__file__).parents[1] / "docs/assessments/transluce/check_pilot_examples.py"
    check = runpy.run_path(str(script))["check"]
    monkeypatch.setitem(check.__globals__, "validate_dataset", lambda _: {"dataset_sha256": "d" * 64})
    http = {"scan_id": "not-selected", "transaction_index": 0,
            "url": {"addr": "host/base64/text"}, "response": {"status_code": "200"}}
    (tmp_path / "http.jsonl").write_text(json.dumps(http) + "\n")
    resources = [{"source_field": field, "availability": "embedded"} for field in
                 ["http[0].request.post_data", "http[0].response.data", "final.dom"]]
    (tmp_path / "resources.jsonl").write_text("\n".join(map(json.dumps, resources)) + "\n")
    result = check(tmp_path)
    assert result["embedded_content_by_source"] == {"request_body": 1, "response_body": 1, "final.dom": 1}
    assert result["opus1_status_sample"]["wrong_status_field"] == {"None": 1}
    assert result["opus1_status_sample"]["correct_status_code_field"] == {"200": 1}


def test_summary_rejects_unfinished_plan(report_fixture):
    summarize, experiment, _, reports = report_fixture
    plan = json.loads((experiment / "plan.json").read_text())
    plan["status"] = "running"
    (experiment / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="finished"):
        summarize([experiment], reports)
