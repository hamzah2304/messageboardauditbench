"""Claude safeguard flags (an intermittent API error) are retried a limited number of times per run."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from slopvestigator_bench import runtime_policy

ROOT = Path(__file__).resolve().parents[1]
FLAG_TEXT = ("API Error: claude-sonnet-5-5's safeguards flagged this message. Our intentionally broad "
             "safeguards allow us to deliver more capabilities faster, but can sometimes flag legitimate "
             "cybersecurity work.\n\nDetails: `[cyber]`\n\nRequest ID: req_x")
FLAG_EVENT = {"type": "system", "subtype": "model_refusal_no_fallback", "api_refusal_category": "cyber"}
FLAG_RESULT = {"type": "result", "subtype": "success", "is_error": True, "stop_reason": "refusal", "result": FLAG_TEXT}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MBAB_SAFEGUARD_RETRY_LIMIT", "3")
    monkeypatch.setenv("MBAB_SAFEGUARD_RETRY_MESSAGE", "Continue the same investigation.")
    monkeypatch.delenv("MBAB_SAFEGUARD_RETRIES_USED", raising=False)
    monkeypatch.delenv("MBAB_EARLIEST_FINISH_EPOCH", raising=False)


def test_flag_text_is_recognised_but_a_models_own_refusal_is_not():
    assert runtime_policy.safeguard_flagged({"result": FLAG_TEXT})
    assert runtime_policy.safeguard_flagged({"last_assistant_message": FLAG_TEXT})
    assert not runtime_policy.safeguard_flagged({"last_assistant_message": "I can't help with this request."})
    # A report that discusses cyber content is not an API error.
    assert not runtime_policy.safeguard_flagged({"last_assistant_message": "The [cyber] tag marks the XSS probes."})


def test_hook_continues_a_flagged_turn_until_the_per_run_limit(tmp_path):
    state = tmp_path / "state.json"
    reasons = [runtime_policy.safeguard_retry_reason({"result": FLAG_TEXT, "is_error": True}, state_file=state)
               for _ in range(4)]
    assert reasons[:3] == ["Continue the same investigation."] * 3
    assert reasons[3] == ""   # the fourth flag ends the run
    saved = json.loads(state.read_text())
    assert saved == {"safeguard_flags": 4, "safeguard_retries": 3, "safeguard_retries_exhausted": True}


def test_runner_resumes_count_against_the_same_limit(tmp_path):
    state = tmp_path / "state.json"
    assert runtime_policy.safeguard_retry_reason({"result": FLAG_TEXT}, used_elsewhere=2, state_file=state)
    assert runtime_policy.safeguard_retry_reason({"result": FLAG_TEXT}, used_elsewhere=2, state_file=state) == ""


def test_stop_hook_retries_the_flag_but_keeps_other_terminal_statuses_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_policy, "_STATE_FILE", tmp_path / "state.json")
    report = tmp_path / "report.md"
    report.write_text("x")
    monkeypatch.setenv("MBAB_REPORT_MIN_WORDS", "0")
    monkeypatch.setenv("MBAB_REPORT_MAX_WORDS", "0")
    sys.path.insert(0, str(ROOT / "slopvestigator_bench"))
    flagged = {"is_error": True, "error": "api_error", "last_assistant_message": FLAG_TEXT}
    original = runtime_policy.safeguard_retry_reason
    monkeypatch.setattr(runtime_policy, "safeguard_retry_reason",
                        lambda event: original(event, state_file=tmp_path / "state.json"))
    assert runtime_policy.stop_reason(flagged, report=report) == "Continue the same investigation."
    assert runtime_policy.stop_reason({"is_error": True, "error": "overloaded"}, report=report) == ""
    assert runtime_policy.stop_reason({"stop_reason": "refusal", "last_assistant_message": "I won't."}, report=report) == ""


def test_limit_zero_leaves_the_old_stop_logic_exactly_as_it_was(tmp_path, monkeypatch):
    monkeypatch.setenv("MBAB_SAFEGUARD_RETRY_LIMIT", "0")
    state = tmp_path / "s.json"
    assert runtime_policy.safeguard_retry_reason({"result": FLAG_TEXT}, state_file=state) is None
    assert not state.exists()   # nothing recorded
    monkeypatch.delenv("MBAB_SAFEGUARD_RETRY_LIMIT")
    assert runtime_policy.safeguard_retry_reason({"result": FLAG_TEXT}, state_file=state) is None
    # A flagged Stop event that is not terminal by the old rules is held by the early-stop policy,
    # as before the retry existed.
    import time
    monkeypatch.setenv("MBAB_EARLIEST_FINISH_EPOCH", str(int(time.time()) + 600))
    monkeypatch.setattr(runtime_policy, "_STATE_FILE", state)
    report = tmp_path / "report.md"
    report.write_text("x")
    monkeypatch.setenv("MBAB_REPORT_MIN_WORDS", "0")
    monkeypatch.setenv("MBAB_REPORT_MAX_WORDS", "0")
    import sys
    sys.path.insert(0, str(ROOT / "slopvestigator_bench"))
    reason = runtime_policy.stop_reason({"last_assistant_message": FLAG_TEXT}, report=report)
    assert "early-completion reminder" in reason


def test_transcript_summary_counts_flags_and_whether_the_stream_ended_on_one(tmp_path):
    survived = [FLAG_EVENT, {"type": "user"}, FLAG_EVENT, {"type": "result", "is_error": False, "subtype": "success"}]
    ended = [FLAG_EVENT, FLAG_RESULT]
    assert runtime_policy.count_safeguard_flags(survived) == 2 and not runtime_policy.final_safeguard_flag(survived)
    assert runtime_policy.count_safeguard_flags(ended) == 1 and runtime_policy.final_safeguard_flag(ended)
    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in ended))
    out = subprocess.run(["python3", str(ROOT / "slopvestigator_bench/runtime_policy.py"), "--safeguard", str(path)],
                         capture_output=True, text=True, check=True).stdout
    assert out.split() == ["1", "1"]


def _postprocess(tmp_path, transcript, rc):
    run = tmp_path / "run"
    run.mkdir()
    (run / "meta.json").write_text(json.dumps({"agent": "claude", "model": "m", "run_id": "r", "report_min_words": 0,
                                               "report_max_words": 0}))
    (run / "transcript.jsonl").write_text("".join(json.dumps(e) + "\n" for e in transcript))
    (run / "report.md").write_text("x")
    result = subprocess.run([sys.executable, "-S", str(ROOT / "scripts/postprocess_trial.py"), str(run), str(rc), "5"],
                            capture_output=True, text=True)
    return result.returncode, json.loads((run / "meta.json").read_text())


def test_a_retried_flag_is_not_a_terminal_refusal(tmp_path):
    resumed = [{"type": "system", "subtype": "init"}, FLAG_EVENT,
               {"type": "assistant", "message": {"model": "<synthetic>", "stop_reason": "refusal"}}, FLAG_RESULT,
               {"type": "system", "subtype": "init"},
               {"type": "assistant", "message": {"model": "claude-sonnet-5-5"}}, {"type": "user"}]
    rc, meta = _postprocess(tmp_path, resumed, 124)   # then the time limit ended it
    assert rc == 124 and "model_refusal" not in meta


def test_a_flag_that_ends_the_run_is_still_a_terminal_refusal(tmp_path):
    rc, meta = _postprocess(tmp_path, [FLAG_EVENT, FLAG_RESULT], 1)
    assert rc == 5 and meta["model_refusal"]["terminal"] is True


def test_runner_resumes_flagged_sessions_and_records_them():
    runner = (ROOT / "sandbox/docker/run_trial.sh").read_text()
    assert 'for attempt in $(seq 1 $((2 + SAFEGUARD_RETRY_LIMIT)))' in runner
    assert 'claude_prompt="$CFG_SAFEGUARD_RETRY_MESSAGE"' in runner
    for key in ("safeguard_retries", "safeguard_retry_limit", "safeguard_retries_exhausted"):
        assert f"{key}: ${key}" in runner


def test_standard_configs_turn_retries_on_and_inspect_passes_them():
    import slopvestigator_bench.task as task_module
    from slopvestigator_bench import standard
    from slopvestigator_bench.configs import load_config

    for bench in standard.benchmark_ids():
        cfg = load_config(standard.config_name(bench, 10), bench)
        assert cfg["safeguard_retry_limit"] == 3 and cfg["safeguard_retry_message"]
        env = task_module._agent_env(cfg, "claude")
        assert env["MBAB_SAFEGUARD_RETRY_LIMIT"] == "3"
        assert env["MBAB_SAFEGUARD_RETRY_MESSAGE"] == cfg["safeguard_retry_message"]
