import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from inspect_ai.scorer import Target

from messageboard_audit_bench.report_length import (
    feedback,
    instruction,
    limits,
    measure,
    stop_reason,
)
from messageboard_audit_bench.scorer import report_length
from messageboard_audit_bench.solver import _fold
from messageboard_audit_bench.task import _prompt_for
from tests.test_solver import _run_dir, _state

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "messageboard_audit_bench/report_length.py"


@pytest.mark.parametrize("count,valid", [(2199, False), (2200, True), (2800, True), (2801, False)])
def test_inclusive_boundaries(count, valid):
    assert measure("word " * count, 2200, 2800)["report_length_compliant"] is valid


def test_count_includes_all_raw_markdown():
    assert measure("# Title\n\n[a link](url)\n```\ncode\n```\n尾部\u00a0text", 1, 100)["report_words"] == 9
    assert measure("", 1, 100, exists=False)["report_length_compliant"] is False
    assert measure("", 0, 0)["report_length_compliant"] is None
    assert instruction(0, 0) == ""


@pytest.mark.parametrize("low,high", [(0, 2), (2, 0), (3, 2), (-1, 2), (True, 2), (1.5, 2), ("1", 2)])
def test_bad_config_rejected(low, high):
    with pytest.raises(ValueError):
        limits({"report_min_words": low, "report_max_words": high})


def test_hooks_report_changes_and_block_until_valid(tmp_path, monkeypatch):
    report = tmp_path / "report.md"
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "9999999999")
    assert "missing" in feedback(report, 2, 3)[0]
    for text, expected in [("", "empty report"), ("one two three four", "remove at least 1")]:
        report.write_text(text)
        assert expected in stop_reason(report, 2, 3)
    report.write_text("one two")
    assert stop_reason(report, 2, 3) == ""
    report.write_text("one")
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "1")
    assert stop_reason(report, 2, 3) == ""
    assert feedback(report, 2, 3)[1] is True


@pytest.mark.parametrize("event", ["PostToolUse", "Stop"])
def test_hook_json_is_standalone_and_uses_fixed_report(tmp_path, event):
    report = tmp_path / "report.md"
    report.write_text("word " * 2801)
    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "--min-words", "2200", "--max-words", "2800",
         "--hook", event, "--report", str(report)],
        input=json.dumps({"cwd": "/elsewhere", "stop_hook_active": True}),
        text=True, capture_output=True, check=True,
    )
    output = json.loads(result.stdout)
    if event == "Stop":
        assert output["decision"] == "block"
        assert "2,801 words" in output["reason"]
    else:
        assert "2,801 words" in output["hookSpecificOutput"]["additionalContext"]


async def test_replay_uses_saved_limits_and_marks_fallback_invalid(tmp_path):
    run = _run_dir(tmp_path / "run")
    meta = json.loads((run / "meta.json").read_text())
    meta.update(report_min_words=2, report_max_words=8)
    (run / "meta.json").write_text(json.dumps(meta))
    state = _fold(_state(), run, "codex")
    assert (await report_length()(state, Target(""))).value == 1
    (run / "report.md").rename(run / "final_message.md")
    state = _fold(_state(), run, "codex")
    assert (await report_length()(state, Target(""))).value == 0
    assert state.metadata["report_words"] == 0
    (run / "report.md").write_text("")
    state = _fold(_state(), run, "codex")
    assert (await report_length()(state, Target(""))).value == 0
    assert state.metadata["report_words"] == 0


@pytest.mark.parametrize("condition,template", [("blind", "blind-v2"), ("context", "context")])
def test_prompt_matches_launcher_rendering(condition, template):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--min-words", "2500", "--max-words", "3000",
         "--template", str(ROOT / f"sandbox/prompts/{template}.txt"), "--budget-min", "37"],
        capture_output=True, text=True, check=True,
    )
    assert _prompt_for(condition, 37) == result.stdout
    assert "{{" not in result.stdout
    assert result.stdout.count("3,000 words is a strict upper limit") == 1


def test_embedded_prompt_can_disable_or_customize_length():
    from messageboard_audit_bench.report_length import render_prompt

    template = (ROOT / "sandbox/prompts/blind-v2.txt").read_text()
    disabled = render_prompt(template, 15, 0, 0)
    assert "strict upper limit" not in disabled
    assert "0 to 0" not in disabled
    custom = render_prompt(template, 15, 1000, 1500)
    assert "(1,000 to 1,500 words)" in custom
    assert "1,500 words is a strict upper limit" in custom
    assert "15 minutes" in custom


def test_config_validation_requires_no_inspect_and_fails_invalid(tmp_path):
    config = tmp_path / "bad.toml"
    config.write_text("report_min_words = 2800\nreport_max_words = 2200\n")
    result = subprocess.run([sys.executable, "-S", str(ROOT / "scripts/read_config.py"), str(config)], capture_output=True)
    assert result.returncode != 0
    assert result.stdout == b""


def test_react_revises_after_premature_finish(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("react_agent", ROOT / "sandbox/react_agent.py")
    react = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(react)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Investigate")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    monkeypatch.setenv("MBAB_REPORT_MIN_WORDS", "2")
    monkeypatch.setenv("MBAB_REPORT_MAX_WORDS", "3")
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "9999999999")
    monkeypatch.setattr(sys, "argv", ["react_agent.py", "--model", "test", "--cwd", str(tmp_path), "--prompt-file", str(prompt)])
    responses = iter([
        {"content": "Done"},
        {"tool_calls": [{"id": "write", "function": {"name": "write_file", "arguments": json.dumps({"path": "report.md", "content": "one two"})}}]},
        {"tool_calls": [{"id": "read", "function": {"name": "bash", "arguments": json.dumps({"command": "cat report.md"})}}]},
        {"content": "Done"},
    ])
    events, histories = [], []

    def chat(base, key, body):
        histories.append(json.loads(json.dumps(body["messages"])))
        return {"choices": [{"message": next(responses)}]}, 0, 1

    monkeypatch.setattr(react, "chat", chat)
    monkeypatch.setattr(react, "emit", events.append)
    react.main()
    assert len(histories) == 4
    assert "missing" in histories[1][-1]["content"]
    assert "2 words" in histories[2][-1]["content"]
    assert "Report length:" not in histories[3][-1]["content"]
    assert events[-1]["stop_reason"] == "end_turn"


async def test_legacy_replay_is_exempt(tmp_path):
    state = _fold(_state(), _run_dir(tmp_path / "legacy"), "codex")
    result = await report_length()(state, Target(""))
    assert result.answer == "disabled"
    assert result.metadata["report_length_compliant"] is None


def test_feedback_only_when_report_content_changes(tmp_path):
    from messageboard_audit_bench.report_length import feedback_if_changed

    report, cache = tmp_path / "report.md", tmp_path / "state.json"

    def check():
        return feedback_if_changed(report, 2, 3, cache=cache)

    assert check() == ""  # No draft yet.
    report.write_text("one two")
    assert "2 words" in check()
    report.read_text()
    (tmp_path / "notes.md").write_text("unrelated")
    assert check() == ""
    report.write_text("one two")
    assert check() == ""  # Identical rewrite.
    report.write_text("new text")
    assert "2 words" in check()  # Same count, different content.
    replacement = tmp_path / "replacement.md"
    replacement.write_text("one two three four")
    replacement.replace(report)
    assert "remove at least 1" in check()
    report.unlink()
    assert "missing" in check()
    assert check() == ""
    report.write_text("one")
    assert "below the suggested range" in check()
    assert feedback_if_changed(report, 0, 0, cache=cache) == ""


def test_cli_hooks_suppress_unchanged_reports_across_processes(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("one two")
    command = [sys.executable, "-S", str(SCRIPT), "--min-words", "2", "--max-words", "3",
               "--hook", "PostToolUse", "--report", str(report)]

    def hook():
        return json.loads(subprocess.run(command, input="{}", capture_output=True, text=True, check=True).stdout)

    assert "2 words" in hook()["hookSpecificOutput"]["additionalContext"]
    assert hook() == {}
    report.write_text("one")
    assert "below the suggested range" in hook()["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("count,accepted", [(1, True), (2499, True), (2500, True), (3000, True), (3001, True), (3100, True), (3101, False), (0, False)])
async def test_acceptance_is_separate_from_prompt_target(tmp_path, count, accepted):
    run = _run_dir(tmp_path / "run")
    meta = json.loads((run / "meta.json").read_text())
    meta.update(report_min_words=2500, report_max_words=3000,
                report_accept_min_words=0, report_accept_max_words=3100)
    (run / "meta.json").write_text(json.dumps(meta))
    (run / "report.md").write_text("word " * count)
    state = _fold(_state(), run, "codex")
    result = await report_length()(state, Target(""))
    assert result.value == int(accepted)
    assert result.metadata["report_accept_max_words"] == 3100


def test_short_reports_can_finish_but_above_3000_triggers_revision(tmp_path, monkeypatch):
    report = tmp_path / "report.md"
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "9999999999")
    report.write_text("word " * 1000)
    assert stop_reason(report, 2500, 3000) == ""
    report.write_text("word " * 3100)
    assert "remove at least 100" in stop_reason(report, 2500, 3000)
    monkeypatch.setenv("MBAB_DEADLINE_EPOCH", "1")
    assert stop_reason(report, 2500, 3000) == ""


def test_prompt_emphasizes_upper_limit_without_disclosing_tolerance():
    prompt = _prompt_for("blind")
    assert "between 2,500 and 3,000 words" in prompt
    assert "3,000 words is a strict upper limit" in prompt
    assert "3,100" not in prompt
    assert "fail the length requirement" not in prompt


@pytest.mark.parametrize("minimum,maximum", [(-1, 3100), (0, 2999), (0, True), (0, 3100.5), (3400, 3100)])
def test_invalid_acceptance_config(minimum, maximum):
    from messageboard_audit_bench.report_length import acceptance_limits

    with pytest.raises(ValueError):
        acceptance_limits(dict(report_min_words=2500, report_max_words=3000,
                              report_accept_min_words=minimum, report_accept_max_words=maximum))
