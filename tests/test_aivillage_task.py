"""The AI Village Inspect tasks on the shared harness, without Docker or model calls."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from inspect_ai.model import ChatMessageUser, ModelName, ModelOutput
from inspect_ai.scorer import Target
from inspect_ai.solver import TaskState

import slopvestigator_bench.task as task_module
from slopvestigator_bench import benchmarks
from slopvestigator_bench.configs import load_config
from slopvestigator_bench.grading import aivillage as av
from slopvestigator_bench.grading import answer_key_judge as akj
from slopvestigator_bench.grading import core, finding_scorer
from slopvestigator_bench.grading import task as grading_task

ROOT = Path(__file__).parents[1]
VARIANT = "aivillage/full-v2-reasoning"


@pytest.fixture
def primary(tmp_path, monkeypatch):
    """A primary checkout whose data/ holds a small AI Village build."""
    data = tmp_path / "data" / VARIANT
    data.mkdir(parents=True)
    (data / "chat_messages.jsonl").write_text('{"id": 1}\n')
    (data / "village_goals.jsonl").write_text("")
    with open(data / "village.db", "wb") as f:
        f.truncate(400_000_000)  # sparse: over a tenth of 3g, so the memory note names it
    monkeypatch.setattr(task_module, "primary_root", lambda: tmp_path)
    monkeypatch.setattr(benchmarks, "primary_root", lambda: tmp_path)
    return tmp_path


def test_registry_and_configs():
    assert benchmarks.SPECS["aivillage"].task == "aivillage_report"
    assert benchmarks.config_names("aivillage") == ("aivillage-v12-30", "aivillage-v12-30-subagents",
                                                    "aivillage-std-10", "aivillage-std-30")
    assert benchmarks.default_config("aivillage") == "aivillage-v12-30"
    for name in benchmarks.config_names("aivillage"):
        assert load_config(name, "aivillage")["data_variant"] == VARIANT
    with pytest.raises(ValueError, match="unknown aivillage config"):
        task_module.aivillage_report(config="blind")
    with pytest.raises(ValueError, match="unknown messageboard config"):
        load_config("aivillage-v12-30", "messageboard")


@pytest.mark.parametrize("subagents", [False, True])
def test_native_prompt_matches_the_subscription_runner(primary, subagents):
    """The runner's prompt.txt, built by the same CLIs run_trial.sh calls, is the native input."""
    cfg = load_config("aivillage-v12-30" + ("-subagents" if subagents else ""), "aivillage")
    py, data = sys.executable, primary / "data" / VARIANT
    run = lambda *args: subprocess.run([py, *map(str, args)], check=True, capture_output=True, text=True).stdout  # noqa: E731
    expected = (
        run(ROOT / "slopvestigator_bench/report_length.py", "--template", ROOT / "sandbox/prompts/aivillage-v12.txt",
            "--budget-min", 30, "--min-words", cfg["report_min_words"], "--max-words", cfg["report_max_words"],
            "--findings-count", 20, *(["--subagents"] if subagents else []), "--memory-limit", "3g")
        + run(ROOT / "slopvestigator_bench/runtime_policy.py", "--instruction", "--fraction", 0.9,
              "--budget-minutes", 30, "--notice", cfg["runtime_notice"])
        + run(ROOT / "slopvestigator_bench/report_length.py", "--memory-limit", "3g", "--memory-note", data)
    )
    task = task_module.aivillage_report(agent="codex", subagents=subagents)
    assert task.dataset[0].input == expected
    assert ("Subagents" in expected) == subagents
    assert "village.db is 0.4 GB" in expected


def test_native_task_applies_the_config(primary):
    task = task_module.aivillage_report(agent="codex")
    assert task.version == benchmarks.SPECS["aivillage"].eval_version
    sample = task.dataset[0]
    assert sample.id == "codex:inspect:aivillage-v12-30:30m"
    assert sample.metadata["benchmark_id"] == "aivillage" and sample.metadata["subagents"] is False
    assert sample.metadata["min_runtime_fraction"] == 0.9
    service = task.sandbox.config.services["default"]
    assert service.network_mode == "none" and service.mem_limit == "3g" == service.memswap_limit
    assert service.environment == {"MBAB_BENCHMARK_ID": "aivillage"}
    assert service.volumes == [f"{(primary / 'data' / VARIANT).resolve()}:/work/data:ro"]


def test_subagents_switch_matches_the_runner():
    off, on = (load_config(n, "aivillage") for n in benchmarks.AIVILLAGE_CONFIGS)
    assert {"Task", "Agent"} <= set(task_module._claude_disallowed_tools(off))
    assert not {"Task", "Agent"} & set(task_module._claude_disallowed_tools(on))
    assert task_module._codex_settings(off, "aivillage") == (
        ("multi_agent", "multi_agent_v2"), {"tool_output_token_limit": "12500"})
    features_off, overrides = task_module._codex_settings(on, "aivillage")
    assert features_off == () and overrides["features.multi_agent"] == "true"
    assert task_module._agent_env(off, "claude")["BASH_MAX_OUTPUT_LENGTH"] == "50000"
    assert "BASH_MAX_OUTPUT_LENGTH" not in task_module._agent_env(off, "codex")
    # The other benchmarks' configs have no such keys, so nothing changes for them.
    blind = load_config("blind")
    assert task_module._claude_disallowed_tools(blind) == blind["claude_disallowed_tools"]
    assert task_module._codex_settings(blind, "messageboard") == ((), {})
    assert task_module._agent_env(blind, "claude") == {}


def test_subscription_task_hands_the_config_to_the_runner(primary):
    task = task_module.aivillage_report(agent="claude", backend="subscription",
                                        subscription_model="claude-opus-5", subagents=True)
    assert task.sandbox is None
    assert task.dataset[0].metadata["config"] == "aivillage-v12-30-subagents"
    with pytest.raises(ValueError, match="config or subagents"):
        task_module.aivillage_report(config="aivillage-v12-30", subagents=True)


def test_missing_data_fails_before_a_trial(tmp_path, monkeypatch):
    monkeypatch.setattr(task_module, "primary_root", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="build_aivillage_data"):
        task_module.aivillage_report()


class FakeJudge:
    """Scores every finding `value` and its sub-findings 1; raises on the finding `fail`."""

    def __init__(self, value=1.0, fail=None, name="openai/gpt-6.1-sol", returns="gpt-6.1-sol-2026-09-01"):
        self.value, self.fail, self.calls, self.name, self.returns = value, fail, [], name, returns
        self.findings = {f["id"]: f for f in akj.graded_findings(akj.load_key("aivillage"))}

    def __str__(self):
        return self.name

    async def generate(self, messages, config):
        prompt = "".join(part.text for part in messages[1].content)
        head = re.search(r"Finding ID: (M\d+)", prompt)[1]
        self.calls.append((prompt, config))
        if head == self.fail:
            raise RuntimeError("judge down")
        subs = [{"id": s["id"], "score": 1, "contradicted": False, "quote": "", "reason": "r"}
                for s in self.findings[head]["subfindings"]]
        return ModelOutput.from_content(model=self.returns, content=json.dumps(
            {"finding_id": head, "score": self.value, "contradicted": False, "quote": "", "reason": "r", "sub_findings": subs}))


def _state(report: str, variant: str = VARIANT) -> TaskState:
    return TaskState(model=ModelName("mockllm/model"), sample_id="r1", epoch=1, input="",
                     messages=[ChatMessageUser(content="")], output=ModelOutput.from_content("m", report),
                     metadata={"data_variant": variant, "run": "r1"})


async def test_scorer_judges_each_finding_on_its_own(monkeypatch):
    judge = FakeJudge(value=0.5)
    monkeypatch.setattr(finding_scorer, "get_model", lambda *a, **k: judge)
    score = await av.aivillage_scorer(effort="medium")(_state("A report."), Target(""))
    assert len(judge.calls) == len(judge.findings) == 96
    assert score.value == {"score": 0.5, "coverage": 0.5}
    prompt, config = judge.calls[0]
    assert "It also had reasoning traces" in prompt and "{{" not in prompt
    assert prompt.startswith("We are measuring") and "## The finding to score" in prompt
    assert config.reasoning_effort == "medium"
    grade = score.metadata["grade"]
    assert grade["rubric"] == "answer-key" and grade["top_k"] == av.TOP_K == akj.SPECS["aivillage"].top_k
    judge.calls.clear()
    await av.aivillage_scorer()(_state("A report.", "aivillage/full-v2-noreasoning"), Target(""))
    assert judge.calls[0][1].reasoning_effort == "high"   # configs/standard.toml judge_effort
    assert "It did not have reasoning traces" in judge.calls[0][0]


async def test_scorer_pins_the_openrouter_route(monkeypatch):
    judge = FakeJudge(name="openrouter/openai/gpt-6.1-sol")
    monkeypatch.setattr(finding_scorer, "get_model", lambda *a, **k: judge)
    await av.aivillage_scorer()(_state("A report."), Target(""))
    config = judge.calls[0][1]
    assert config.extra_body["provider"] == {"allow_fallbacks": False, "require_parameters": True}
    assert config.extra_body["response_format"] == {"type": "json_object"}


async def test_scorer_refuses_a_grade_from_another_model(monkeypatch):
    judge = FakeJudge(name="openrouter/openai/gpt-6.1-sol", returns="openai/gpt-6-luna")
    monkeypatch.setattr(finding_scorer, "get_model", lambda *a, **k: judge)
    score = await av.aivillage_scorer()(_state("A report."), Target(""))
    assert score.answer == "ungraded"
    first = score.metadata["grade"]["findings"][score.metadata["grade"]["unscored"][0]]
    assert first["status"] == "api_error" and "differs" in first["error"]


async def test_scorer_tops_twenty_and_leaves_failures_unscored(monkeypatch):
    heads = list(FakeJudge().findings)
    body = {"findings": {h: {"status": "ok", "score": 1.0 if i < 20 else 0.0} for i, h in enumerate(heads)}}
    akj.summarize("aivillage", body, heads, {}, "")
    assert body["score"] == body["score_top_k"] == 1.0 and body["score_mean"] == round(20 / 96, 3)
    judge = FakeJudge(fail=heads[1])
    monkeypatch.setattr(finding_scorer, "get_model", lambda *a, **k: judge)
    score = await av.aivillage_scorer()(_state("A report."), Target(""))
    assert score.answer == "ungraded"
    assert score.metadata["grade"]["findings"][heads[1]]["error"].startswith("RuntimeError")


def test_grade_task_reads_run_directories(primary):
    run = primary / "runs" / "20261004T000000Z_codex_gpt-6-luna_r1_aivillage-v12-30_abc"
    run.mkdir(parents=True)
    (run / "report.md").write_text("A report.")
    (run / "meta.json").write_text(json.dumps({"data_variant": VARIANT, "model": "gpt-6-luna", "agent": "codex"}))
    task = grading_task.aivillage_report_grade(runs="*_aivillage-v12-30_*")
    assert [s.id for s in task.dataset] == [core.sanitise(run.name)]
    assert task.dataset[0].metadata["run"] == run.name
    assert task.dataset[0].metadata["data_variant"] == VARIANT
    with pytest.raises(ValueError, match="exactly one"):
        grading_task.aivillage_report_grade()


def test_german_wiki_grades_run_directories_with_eligibility(primary):
    run = primary / "runs" / "20261022T000000Z_claude_claude-opus-5_r1_wiki-std-30_abc"
    run.mkdir(parents=True)
    (run / "report.md").write_text("A report.")
    (run / "meta.json").write_text(json.dumps({"benchmark_id": "messageboard", "model": "claude-opus-5",
                                               "data_variant": "verbatim", "model_served": "claude-opus-4-8",
                                               "model_fallback": {"fallback_model": "claude-opus-4-8"}}))
    task = grading_task.german_wiki_report_grade(runs="*_wiki-std-30_*", judge_effort="high")
    meta = task.dataset[0].metadata
    assert meta["eligible"] is False and "model_switched" in meta["ineligible_reasons"]
    assert task.metadata["judge_effort"] == "high" and task.metadata["runs"] == "*_wiki-std-30_*"


def test_the_graded_findings_leave_out_what_the_qa_did_not_find():
    key = akj.load_key("aivillage")
    graded = akj.graded_findings(key)
    assert len(graded) == 96 and sum(len(f["subfindings"]) for f in graded) == 248
    assert sum(len(f["subfindings"]) for f in key["findings"]) == 252
