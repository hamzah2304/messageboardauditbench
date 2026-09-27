import json
import shutil
import subprocess

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model

from report_eval_harness import prompts
from report_eval_harness.corpus import Corpus, list_corpora
from report_eval_harness.feedback import Feedback, report_counts
from report_eval_harness.scorer import parse_grades, strict
from report_eval_harness.task import investigation


def test_corpora_have_ids_and_claims():
    for name in list_corpora():
        corpus = Corpus(name)
        assert corpus.ids(), name
        ids = [c["id"] for c in corpus.claims()]
        assert len(ids) == len(set(ids)), f"duplicate claim ids in {name}"
        for claim in corpus.claims():
            assert {"id", "claim", "grading_mode", "note"} <= claim.keys()


def test_strict_transform():
    assert strict(1.0) == 1.0
    assert strict(0.5) == 0.0
    assert strict(0.2) == 0.0
    assert strict(0.8) == pytest.approx(0.6)


def test_parse_grades_tolerates_prose_and_missing_claims():
    reply = 'Here you go:\n{"A": {"score": 0.7, "reason": "ok"}, "B": {"score": 1.4}}'
    grades = parse_grades(reply, ["A", "B", "C"])
    assert grades["A"]["score"] == 0.7
    assert grades["B"]["score"] == 1.0  # clamped
    assert grades["C"] is None


def prompt_values() -> dict[str, object]:
    return prompts.values(n_records=3, budget_min=30, report_min_words=2500, report_max_words=3000)


def test_render_fills_values_and_sections():
    values = prompt_values()
    text = (
        "report.md{{#REPORT_LENGTH}} ({{REPORT_MIN_WORDS}} to {{REPORT_MAX_WORDS}})"
        "{{/REPORT_LENGTH}}"
    )
    assert prompts.render(text, values) == "report.md (2,500 to 3,000)\n"
    no_limit = {**values, "REPORT_LENGTH": False}
    assert prompts.render(text + "\n\n\n\n{{BUDGET_MIN}} min", no_limit) == "report.md\n\n30 min\n"
    assert prompts.render("{literal} braces", values) == "{literal} braces\n"
    for bad in ["{{TYPO}}", "{{#REPORT_LENGTH}}unclosed"]:
        with pytest.raises(ValueError):
            prompts.render(bad, values)


def test_every_prompt_renders():
    values = prompt_values()
    for name in [*prompts.list_prompts(), "analyst.txt"]:
        for length in (True, False):
            text = prompts.render(prompts.load(name), {**values, "REPORT_LENGTH": length})
            assert "{{" not in text, name


def test_report_counts_follow_the_prompt():
    report = (
        "# TL;DR\n\nOne two [scan](https://urlquery.net/report/a), [[1]](https://x/y) three.\n\n"
        "## Incidents\n\n| a | b |\n\n```\n# code, not a heading\n```\n"
    )
    counts = report_counts(report)
    assert counts.tldr_words == 4  # "One two , three." -- links excluded, heading not counted
    assert counts.words == 2 + 4 + 2 + 5 + 1 + 5 + 1  # headings, tables and code still count
    assert report_counts("**TL;DR:** a b c\n\n# Next\nd").tldr_words == 3
    assert report_counts("no summary").tldr_words is None


def test_feedback_report_note():
    note = Feedback(2500, 3000)._report("## TL;DR\n" + "w " * 201)
    assert "203 words (target 2,500-3,000)" in note and "TL;DR 201 words (max 200; 1 over)" in note


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.docker
@pytest.mark.skipif(not docker_available(), reason="no Docker daemon")
def test_end_to_end_with_scripted_model(tmp_path):
    """Lead -> analyst subagent -> report -> judge, with scripted (free) model outputs."""
    corpus = Corpus("puchoiswater")
    if not corpus.records():
        pytest.skip("run `report-eval-harness fetch puchoiswater` first")

    m = "mockllm/model"
    bash = "bash"
    agent_outputs = [
        # lead: look at the data (relative to /work), and prove the sandbox is locked down
        ModelOutput.for_tool_call(m, bash, {"command": "wc -l < data/scans.jsonl; ls data"}),
        ModelOutput.for_tool_call(m, bash, {"command": "touch /work/data/x 2>&1; echo rc=$?"}),
        ModelOutput.for_tool_call(
            m,
            bash,
            {
                "command": 'python3 -c "import urllib.request as u; '
                "u.urlopen('http://1.1.1.1', timeout=3)\" 2>&1 | tail -1"
            },
        ),
        # lead delegates to the analyst subagent (same scripted model)
        ModelOutput.for_tool_call(m, "analyst", {"input": "How many records are there?"}),
        ModelOutput.for_tool_call(m, bash, {"command": "wc -l < /work/data/scans.jsonl"}),
        ModelOutput.for_tool_call(m, "submit", {"answer": "There are 22 records."}),
        # lead writes the report and submits
        ModelOutput.for_tool_call(
            m, bash, {"command": "printf '# TL;DR\\nMicrosoft 365 phishing.\\n' > /work/report.md"}
        ),
        ModelOutput.for_tool_call(m, "submit", {"answer": "Report written."}),
    ]
    claim_ids = [c["id"] for c in corpus.claims()]
    judge_reply = json.dumps({cid: {"score": 0.8, "reason": "scripted"} for cid in claim_ids})
    judge = get_model(m, custom_outputs=[ModelOutput.from_content(m, judge_reply)])

    [log] = inspect_eval(
        investigation(corpus="puchoiswater", time_limit_minutes=5),
        model=get_model(m, custom_outputs=agent_outputs),
        model_roles={"grader": judge},
        log_dir=str(tmp_path),
        display="none",
    )

    assert log.status == "success", log.error
    [sample] = log.samples
    tool_outputs = [msg.text for msg in sample.messages if msg.role == "tool"]
    assert tool_outputs[0].split()[:3] == ["22", "README.txt", "scans.jsonl"]
    assert "Read-only file system" in tool_outputs[1]
    assert "Error" in tool_outputs[2] or "unreachable" in tool_outputs[2]
    assert "22 records" in tool_outputs[3]  # analyst's answer came back to the lead
    # every lead tool result carries the time; the report counts only once it changes
    assert all("[harness] Time remaining: " in out for out in tool_outputs)
    assert not any("report.md" in out for out in tool_outputs[:4])
    assert "report.md changed: 5 words (target 2,500-3,000); TL;DR 3 words" in tool_outputs[4]
    score = sample.scores["claim_judge"]
    assert score.value["raw"] == pytest.approx(0.8)
    assert score.value["strict"] == pytest.approx(0.6)
    assert score.metadata["tldr_words"] == 3


@pytest.mark.docker
@pytest.mark.skipif(not docker_available(), reason="no Docker daemon")
def test_claude_code_sandbox_is_locked_down(tmp_path):
    """Claude Code gets only the bridged tools, which run in the locked-down data container."""
    if not Corpus("puchoiswater").records():
        pytest.skip("run `report-eval-harness fetch puchoiswater` first")

    m = "mockllm/model"

    def bash(cmd: str) -> ModelOutput:
        return ModelOutput.for_tool_call(m, "mcp__sandbox__bash", {"command": cmd})

    outputs = [
        bash(
            "pwd; env | grep -c '^ANTHROPIC_'; grep NoNewPrivs /proc/self/status; "
            "touch /usr/x 2>&1; touch data/x 2>&1; "
            "python3 -c \"import urllib.request as u;u.urlopen('https://example.com',timeout=3)\" "
            "2>&1 | tail -1"
        ),
        bash("command -v claude || echo no-claude"),
        bash("printf '## TL;DR\\nOne two three.\\n' > report.md"),
        # text_editor takes no sandbox name; it must still land in the data container
        ModelOutput.for_tool_call(
            m, "mcp__sandbox__text_editor", {"command": "view", "path": "/etc/hostname"}
        ),
        ModelOutput.from_content(m, "Probe finished."),
    ]
    [log] = inspect_eval(
        investigation(corpus="puchoiswater", agent="claude_code", time_limit_minutes=5),
        model=get_model(m, custom_outputs=outputs),
        score=False,
        log_dir=str(tmp_path),
        display="none",
    )

    assert log.status == "success", log.error
    [sample] = read_eval_log(log.location, resolve_attachments=True).samples
    calls = [e for e in sample.events if e.event == "model"]
    tools = {t.name for t in calls[0].tools}
    assert {"mcp__sandbox__bash", "mcp__sandbox__text_editor"} <= tools
    assert not tools & {"Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "Task"}
    assert len(calls) == len(outputs)
    results = [msg.text for msg in calls[-1].input if msg.role == "tool"]
    probe = results[0].splitlines()
    assert probe[:2] == ["/work", "0"]  # shell in /work; no bridge env in the data container
    assert "NoNewPrivs:\t1" in results[0]
    assert results[0].count("Read-only file system") == 2
    assert "Error" in results[0]
    assert "no-claude" in results[1]
    assert all("[harness] Time remaining: " in r for r in results)
    assert "report.md changed: 5 words (target 2,500-3,000); TL;DR 3 words" in results[2]
    assert "default" in results[3] and "claude" not in results[3]
