"""The URLQuery Inspect tasks on the shared harness, without Docker or model calls."""

from __future__ import annotations

import json
import re
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from inspect_ai._util.registry import registry_info
from inspect_ai.model import ChatMessageUser, ModelName, ModelOutput, get_model
from inspect_ai.scorer import Target
from inspect_ai.solver import TaskState

import messageboard_audit_bench.task as task_module
from messageboard_audit_bench import benchmarks
from messageboard_audit_bench.configs import load_config
from messageboard_audit_bench.grading import findings as fj
from messageboard_audit_bench.grading.finding_scorer import finding_scorer

ROOT = Path(__file__).parents[1]
MANIFEST = benchmarks.urlquery_manifest()


def test_manifest_owns_the_active_configs_and_every_one_matches_its_pins():
    assert benchmarks.config_names("urlquery") == ("urlquery-agents-v6-30", "urlquery-agents-v6-10")
    for name in benchmarks.config_names("urlquery"):
        cfg = load_config(name, "urlquery")
        assert cfg["dataset_sha256"] == MANIFEST["dataset"]["sha256"]
        assert cfg["data_variant"] == f"urlquery/{MANIFEST['dataset']['snapshot']}"
    batch = (ROOT / MANIFEST["runtime"]["batch"]).read_text()
    assert set(re.findall(r'configs/(urlquery-[a-z0-9-]+)\.toml', batch)) == set(benchmarks.config_names("urlquery"))


def test_each_task_accepts_only_its_own_configs():
    with pytest.raises(ValueError, match="unknown messageboard config"):
        task_module.messageboard_audit_bench(config="urlquery-agents-v6-30")
    with pytest.raises(ValueError, match="unknown urlquery config"):
        task_module.urlquery_audit_bench(config="blind")
    with pytest.raises(ValueError, match="belongs to 'messageboard'"):
        from messageboard_audit_bench.configs import validate_config
        validate_config({"name": "blind"}, "urlquery")


def test_native_task_mounts_the_pinned_snapshot_and_declares_it_to_preflight():
    task = task_module.urlquery_audit_bench(agent="codex")
    assert task.version == benchmarks.SPECS["urlquery"].eval_version == "1-A"
    assert task.version != task_module.EVAL_VERSION
    sample = task.dataset[0]
    assert sample.id == "codex:inspect:urlquery-agents-v6-30:30m"
    assert sample.metadata["benchmark_id"] == "urlquery" and "incident" not in sample.metadata
    assert sample.metadata["dataset_sha256"] == MANIFEST["dataset"]["sha256"]
    assert task.metadata["benchmark"] == "URLQuery agent-activity audit"
    service = task.sandbox.config.services["default"]
    assert service.network_mode == "none"
    assert service.environment == {"MBAB_BENCHMARK_ID": "urlquery",
                                   "MBAB_DATASET_SHA256": MANIFEST["dataset"]["sha256"]}
    assert service.volumes == [f"{benchmarks.urlquery_dataset_dir()}:/work/data:ro"]
    prompt = (ROOT / "sandbox/prompts/urlquery-agents-v6.txt").read_text()
    assert prompt.split("{{")[0].strip()[:200] in sample.input


def test_subscription_task_uses_the_shared_runner_with_the_config_pins(monkeypatch):
    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return task_module.replay()

    monkeypatch.setattr(task_module, "subscription_agent", capture)
    task = task_module.urlquery_audit_bench(
        agent="react", backend="subscription", subscription_model="moonshotai/kimi-k3",
        config="urlquery-agents-v6-10",
    )
    assert captured["config"] == "urlquery-agents-v6-10"
    assert captured["prompt"] == "urlquery-agents-v6"
    # run_trial.sh resolves the primary checkout's pinned snapshot from the config.
    assert captured["data_variant"] is None
    assert (captured["time_limit_minutes"], captured["effort"]) == (10, "medium")
    assert task.model.name == "model" and task.sandbox is None


def test_both_tasks_are_registered_under_the_package_entry_point():
    import messageboard_audit_bench as package

    entry_point = next(ep for ep in entry_points(group="inspect_ai") if ep.name == "messageboard_audit_bench")
    assert entry_point.value == "messageboard_audit_bench"
    for name in ("urlquery_audit_bench", "urlquery_grade_reports"):
        assert registry_info(getattr(package, name)).name == f"messageboard_audit_bench/{name}"


def test_grade_task_reads_finished_run_dirs(tmp_path, monkeypatch):
    from messageboard_audit_bench.grading import task as grading_task

    runs = tmp_path / "runs/urlquery"
    good = runs / "20260927T211426Z_codex_gpt-6-astra_r1_urlquery-agents-v6-30_10188a321353"
    good.mkdir(parents=True)
    (good / "report.md").write_text("# Report\n")
    (good / "meta.json").write_text(json.dumps({"benchmark_id": "urlquery", "data_variant": "urlquery/x"}))
    (runs / "20260927T211426Z_codex_gpt-6-sol_r1_urlquery-agents-v6-30_aaaaaaaaaaaa").mkdir()  # no report
    monkeypatch.setattr(benchmarks, "primary_root", lambda: tmp_path)
    task = grading_task.urlquery_grade_reports(runs="2026*")
    assert [s.id for s in task.dataset] == [good.name]
    assert task.dataset[0].metadata["model"] == "gpt-6-astra"
    assert task.dataset[0].input == "# Report\n"

    (good / "meta.json").write_text(json.dumps({"benchmark_id": "messageboard"}))
    with pytest.raises(ValueError, match="cross-benchmark grading rejected"):
        grading_task.urlquery_grade_reports(runs="2026*")


def _state(report: str) -> TaskState:
    st = TaskState(model=ModelName("mockllm/model"), sample_id="r", epoch=1, input=report,
                   messages=[ChatMessageUser(content=report)], metadata={"run": "r"}, target=Target(""))
    st.output = ModelOutput.from_content(model="staged-report", content=report)
    return st


def _judge(score_for: dict[str, float], refuse: set[str] = frozenset()):
    """Answer each headline call with the given score and a matching sub-finding list."""
    calls: list[str] = []

    def reply(messages, *_args, **_kwargs) -> ModelOutput:
        text = "".join(part.text for part in messages[-1].content)
        headline = re.search(r"### Finding (F\d+)", text).group(1)
        calls.append(headline)
        if headline in refuse:
            return ModelOutput.from_content("mockllm/model", "I can't help with that.", stop_reason="content_filter")
        subs = [{"id": s, "score": 0.5, "contradicted": False, "quote": "", "reason": "x"}
                for s in fj.sub_ids(headline)]
        body = {"score": score_for.get(headline, 0.0), "contradicted": False, "quote": "", "reason": "x",
                "sub_findings": subs}
        return ModelOutput.from_content("mockllm/model", json.dumps(body))

    return get_model("mockllm/model", custom_outputs=reply), calls


async def test_scorer_grades_every_headline_with_the_manifest_weights():
    heads = fj.headlines()
    model, calls = _judge({h: 1.0 for h in heads} | {"F3": 0.0})
    score = await finding_scorer(judge=model)(_state("REPORT"), Target(""))
    grade = score.metadata["grade"]
    assert sorted(calls) == sorted(heads)
    assert grade["n_scored"] == len(heads) and grade["unscored"] == []
    assert grade["headline_weights"] == {"F3": 0.5}
    expected = fj.score_means({h: 1.0 for h in heads} | {"F3": 0.0}, heads)
    assert (score.value, grade["score_mean_unweighted"]) == expected
    assert grade["article_context"] == "omitted"
    assert grade["prompt_sha256"] == fj.sha(fj.template_path().read_bytes())


async def test_scorer_never_turns_a_refusal_into_zero():
    model, calls = _judge({}, refuse={fj.headlines()[0]})
    score = await finding_scorer(judge=model)(_state("REPORT"), Target(""))
    assert score.value != 0 and score.answer == "ungraded"
    assert calls == [fj.headlines()[0]], "a first-headline refusal skips the rest"
    assert score.metadata["grade"]["findings"][fj.headlines()[0]]["status"] == "refused"


def test_preflight_takes_its_benchmark_from_the_native_sandbox_env(monkeypatch, tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("preflight", ROOT / "sandbox/isolation_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = {}
    monkeypatch.setattr(module, "preflight", lambda work, **kw: seen.update(kw) or {"ok": True})
    monkeypatch.setenv("MBAB_BENCHMARK_ID", "urlquery")
    monkeypatch.setenv("MBAB_DATASET_SHA256", "a" * 64)
    monkeypatch.setattr("sys.argv", ["preflight", "--work", str(tmp_path)])
    assert module.main() == 0
    assert (seen["benchmark_id"], seen["expected_sha256"]) == ("urlquery", "a" * 64)
