from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from messageboard_audit_bench.benchmarks import (
    benchmark_spec,
    check_resume,
    require_scoring_ready,
)
from messageboard_audit_bench.grading.core import variant_for_data

ROOT = Path(__file__).parents[1]


def test_namespaces_and_fail_closed_grading():
    original, new = benchmark_spec("messageboard"), benchmark_spec("urlquery")
    assert original.evaluator_root == "benchmark" and new.evaluator_root == "benchmarks/urlquery"
    assert new.run_root == "runs/urlquery" and new.report_root == "reports/urlquery"
    with pytest.raises(ValueError, match="unknown benchmark"):
        benchmark_spec("typo")
    with pytest.raises(ValueError, match="approved rubric"):
        require_scoring_ready("urlquery")
    with pytest.raises(ValueError, match="grading is forbidden"):
        variant_for_data("urlquery/2026-09-26-v1")
    assert variant_for_data("verbatim") is None
    assert variant_for_data("verbatim_anthropic") == "anthropic"


def test_resume_never_crosses_benchmarks():
    check_resume({}, "messageboard", None)
    with pytest.raises(ValueError, match="cross-benchmark"):
        check_resume({"benchmark_id": "urlquery"}, "messageboard", None)
    with pytest.raises(ValueError, match="dataset mismatch"):
        check_resume({"benchmark_id": "urlquery", "dataset_sha256": "a"}, "urlquery", "b")


def ui_module():
    spec = importlib.util.spec_from_file_location("urlquery_ui", ROOT / "viewers/build_urlquery_findings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_original_ui_reuse_with_inert_source_and_scoped_imports(tmp_path):
    module = ui_module()
    source = tmp_path / "article.html"
    source.write_text('<article><h1>Report</h1><script>alert(1)</script><p onclick="evil()">' + "Evidence. " * 150 + '</p><img onerror="bad()" src="remote"><code>&lt;script&gt;not executed&lt;/script&gt;</code></article>')
    out = tmp_path / "preview.html"
    scope = module.build(source, out, [])
    page = out.read_text()
    assert "alert(1)" not in page and "onclick=\"evil()" not in page and 'src="remote"' not in page
    assert "coverage_urlquery_" in page and "urlquery_cov_author" in page
    assert 'report:"human collusion.wiki report"' not in page
    review = tmp_path / "review.json"
    review.write_text(json.dumps({**scope, "comments": []}))
    assert module.build(source, out, [review]) == scope
    review.write_text(json.dumps({**scope, "benchmark_id": "messageboard", "comments": []}))
    with pytest.raises(ValueError, match="wrong benchmark"):
        module.build(source, out, [review])


def test_trial_prompt_is_neutral_and_length_config_is_approved():
    import tomllib

    from messageboard_audit_bench.report_length import render_prompt
    cfg = tomllib.loads((ROOT / "configs/urlquery-10.toml").read_text())
    prompt = render_prompt((ROOT / "sandbox/prompts/urlquery-blind.txt").read_text(), 10, 3000, 3500)
    assert "{{" not in prompt and "3,500" in prompt
    assert cfg["effort"] == "medium" and cfg["report_accept_max_words"] == 3600
    for hint in ("Transluce", "ONCB", "AIHW", "OpenAI", "Anthropic", "collusion.wiki"):
        assert hint not in prompt


def test_collector_separates_nested_urlquery_reports(tmp_path):
    runs, out = tmp_path / "runs", tmp_path / "reports"
    run = runs / "urlquery" / "20260926T120000Z_example"
    (run / "work").mkdir(parents=True)
    (run / "report.md").write_text("A report with an observed finding.")
    (run / "work/prompt.txt").write_text("offline investigation")
    meta = {"benchmark_id": "urlquery", "dataset_sha256": "a" * 64, "run_id": "b" * 32,
            "agent": "codex", "model": "example", "config": "urlquery-10", "budget_min": 10,
            "data_variant": "urlquery/v1", "effort": "medium", "exit_code": 124,
            "stopped_at_active_limit": True, "report_finalization": "not_confirmed",
            "report_min_words": 3000, "report_max_words": 3500,
            "report_accept_min_words": 0, "report_accept_max_words": 3600}
    (run / "meta.json").write_text(json.dumps(meta))
    command = [sys.executable, str(ROOT / "scripts/collect_reports.py"), "--runs", str(runs), "--out", str(out)]
    subprocess.run(command, check=True, capture_output=True)
    assert not (out / "index.jsonl").read_text().strip()
    subprocess.run(command + ["--benchmark", "urlquery"], check=True, capture_output=True)
    row = json.loads((out / "urlquery/index.jsonl").read_text())
    assert row["benchmark_id"] == "urlquery" and row["dataset_sha256"] == "a" * 64
    assert not row["partial"] and row["report_finalization"] == "not_confirmed"
    assert (out / "urlquery" / row["report"]).read_text() == (run / "report.md").read_text()
    from messageboard_audit_bench.grading.task import grade_reports
    with pytest.raises(ValueError, match="cross-benchmark grading"):
        grade_reports(dir=str((out / "urlquery" / row["report"]).parent))
    meta.pop("dataset_sha256")
    (run / "meta.json").write_text(json.dumps(meta))
    result = subprocess.run(command + ["--benchmark", "urlquery"], capture_output=True, text=True)
    assert result.returncode and "missing dataset identity" in result.stderr


def test_original_stager_rejects_urlquery_metadata(tmp_path):
    (tmp_path / "index.jsonl").write_text(json.dumps({"benchmark_id": "urlquery", "config": "urlquery-10"}) + "\n")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/stage_graded_inputs.py"), str(tmp_path),
                             "urlquery-10=should-not-exist:test"], capture_output=True, text=True)
    assert result.returncode and "different benchmark" in result.stderr


def test_scoped_review_artifacts_require_source_and_dataset_hashes():
    from messageboard_audit_bench.review_scope import validate_review_scope
    with pytest.raises(ValueError, match="wrong benchmark"):
        validate_review_scope({"meta": {"benchmark_id": "messageboard"}}, "urlquery")
    with pytest.raises(ValueError, match="report_sha256"):
        validate_review_scope({"meta": {"benchmark_id": "urlquery"}}, "urlquery")
    meta = {"benchmark_id": "urlquery", "report_sha256": "a" * 64, "dataset_sha256": "b" * 64}
    assert validate_review_scope({"meta": meta}, "urlquery") == meta


@pytest.mark.parametrize(("rc", "seconds", "refusal", "capacity", "termination"), [
    (124, 600, False, False, "active_time_limit"),
    (137, 601, False, False, "active_time_limit"),
    (124, 20, False, False, "error"),
    (0, 470, False, False, "normal"),
    (0, 20, True, False, "refusal"),
    (124, 600, True, False, "refusal"),
    (124, 600, False, True, "capacity_exhausted"),
])
def test_urlquery_termination_precedence(tmp_path, rc, seconds, refusal, capacity, termination):
    meta = {"benchmark_id": "urlquery", "active_time_limit_seconds": 600,
            "agent": "codex", "model": "test", "report_min_words": 3000, "report_max_words": 3500,
            "report_accept_min_words": 0, "report_accept_max_words": 3600}
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    (tmp_path / "report.md").write_text("evidence")
    (tmp_path / "transcript.jsonl").write_text(json.dumps({"type": "result", "stop_reason": "refusal" if refusal else "end_turn"}) + "\n")
    if capacity:
        (tmp_path / "runner-events.jsonl").write_text('{"event":"capacity_exhausted"}\n')
    subprocess.run([sys.executable, str(ROOT / "scripts/postprocess_trial.py"), str(tmp_path), str(rc), str(seconds)], capture_output=True)
    result = json.loads((tmp_path / "meta.json").read_text())
    assert result["termination"] == termination
    assert result["stopped_at_active_limit"] == (termination == "active_time_limit")


def test_runner_rejects_unpinned_config_before_docker():
    import os
    result = subprocess.run(["bash", str(ROOT / "sandbox/docker/run_trial.sh"), "codex", "test", "1"],
                            cwd=ROOT, env={**os.environ, "CONFIG": "urlquery-10"}, capture_output=True, text=True)
    assert result.returncode == 2 and "requires dataset_sha256" in result.stderr


def test_replay_rejects_cross_benchmark_metadata(tmp_path, monkeypatch):
    # Import explicitly; the package also exposes registered task callables.
    import importlib

    module = importlib.import_module("messageboard_audit_bench.task")
    run = tmp_path / "runs" / "foreign"
    run.mkdir(parents=True)
    (run / "transcript.jsonl").write_text("")
    (run / "meta.json").write_text('{"benchmark_id":"urlquery","exit_code":0}')
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    with pytest.raises(ValueError, match="cross-benchmark replay"):
        module.messageboard_audit_bench_replay()


def test_pilot_plan_pins_input_and_keeps_subscription_lanes(tmp_path, monkeypatch):
    import tomllib

    from messageboard_audit_bench import urlquery_pilot as pilot
    dataset = tmp_path / "data/urlquery/test-v1"
    dataset.mkdir(parents=True)
    monkeypatch.setattr(pilot, "primary_root", lambda: tmp_path)
    monkeypatch.setattr(pilot, "validate_trial_data", lambda *_: {
        "benchmark_id": "urlquery", "dataset_sha256": "a" * 64, "dataset_version": "test-v1"})
    directory, payload = pilot.plan(dataset)
    assert directory.parent == tmp_path / "runs/urlquery"
    cfg = tomllib.loads(Path(payload["config"]).read_text())
    assert cfg["dataset_sha256"] == "a" * 64 and cfg["data_variant"] == "urlquery/test-v1"
    assert cfg["budget_min"] == 10 and cfg["effort"] == "medium"
    assert payload["status"] == "planned" and len(payload["matrix"]) == 4
    assert [r["agent"] for r in payload["matrix"]].count("claude") == 2
    assert not list(directory.glob("*.log"))


@pytest.mark.parametrize(("scenario", "rc", "expected_runs"), [("capacity_exhausted", 124, 2), ("refusal", 5, 4), ("error", 1, 2), ("outer_timeout", -15, 2)])
def test_pilot_lanes_and_scoped_cleanup_without_docker(tmp_path, monkeypatch, scenario, rc, expected_runs):
    import uuid

    from messageboard_audit_bench import urlquery_pilot as pilot
    directory = tmp_path / "runs/urlquery/pilot-test"
    directory.mkdir(parents=True)
    payload = {"config": str(directory / "pilot-config.toml"), "dataset_path": str(tmp_path / "data"),
               "dataset_sha256": "a" * 64, "outer_guard_seconds": 900, "status": "planned"}
    calls, launches = [], []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    class Process:
        def __init__(self, command, *, stdout, **kwargs):
            self.command = command
            self.stopped = False
            assert "BUDGET_MIN" not in kwargs["env"]
            run_id = uuid.uuid4().hex
            run = directory.parent / ("20260926_trial_" + run_id[:12])
            run.mkdir()
            (run / ".secrets").mkdir()
            (run / ".secrets/auth-copy").write_text("fixture")
            metadata = {"benchmark_id": "urlquery", "dataset_sha256": "a" * 64,
                        "run_id": run_id, "termination": scenario, "model_refusal": scenario == "refusal",
                        "report_exists": True}
            (run / "meta.json").write_text(json.dumps(metadata))
            stdout.write("run: " + str(run) + "\n")
            launches.append((run, run_id))

        def wait(self, timeout=None):
            if scenario == "outer_timeout" and not self.stopped:
                raise subprocess.TimeoutExpired(self.command, timeout)
            return rc

        def terminate(self):
            self.stopped = True

        def kill(self):
            self.stopped = True

    monkeypatch.setenv("BUDGET_MIN", "123")
    monkeypatch.setattr(pilot.subprocess, "run", fake_run)
    monkeypatch.setattr(pilot.subprocess, "Popen", Process)
    results = pilot.launch(directory, payload)
    assert len(results) == len(launches) == expected_runs
    assert payload["status"] == ("finished" if expected_runs == 4 else "stopped_with_unlaunched_trials")
    if scenario == "outer_timeout":
        for run, run_id in launches:
            assert ["docker", "rm", "-f", f"mbab-agent-{run_id}", f"mbab-proxy-{run_id}"] in calls
            assert ["docker", "network", "rm", f"mbab-inner-{run_id}"] in calls
            assert not (run / ".secrets").exists() and (run / "meta.json").exists()
