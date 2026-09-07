"""Guards for the operational fixes learned from the Sep 2026 rounds. They read the shell runner as text
because the behaviours live in bash; the point is that a later edit cannot silently drop them."""
from pathlib import Path

import messageboard_audit_bench.task as task_mod

ROOT = Path(__file__).resolve().parents[1]
RUN_TRIAL = (ROOT / "sandbox" / "docker" / "run_trial.sh").read_text()
REACT = (ROOT / "sandbox" / "react_agent.py").read_text()


def test_claude_long_lived_token_is_preferred_over_copied_credentials() -> None:
    # Copied credentials refresh inside every container; parallel refreshes rotate the shared refresh
    # token and all but the first trial fail to authenticate (2026-09-07). The setup-token file avoids it.
    token = RUN_TRIAL.index('runs/.claude-oauth-token')
    creds = RUN_TRIAL.index('cp "$ROOT/runs/.claude-home/.credentials.json"')
    assert token < creds
    assert "CLAUDE_CODE_OAUTH_TOKEN" in RUN_TRIAL


def test_codex_relaunches_when_the_model_is_at_capacity() -> None:
    assert "is at capacity" in RUN_TRIAL
    assert 'for attempt in 1 2 3' in RUN_TRIAL


def test_claude_model_switch_on_refusal_stays_enabled() -> None:
    # Decision 2026-09-06: let Claude Code switch model after a cyber-safeguard refusal and record
    # model_served, rather than ending the trial. Disabling it made opus/fable trials die in minutes.
    assert '"switchModelsOnFlag": false' not in RUN_TRIAL
    assert "model_served" in RUN_TRIAL


def test_refusal_ended_sessions_share_one_exit_code() -> None:
    # ReAct exits 0 and Claude Code exits 1 when a refusal ends the run; both must become exit 5 so a
    # caller can rerun refusals uniformly.
    assert "if rc in (0,1): rc=5" in RUN_TRIAL


def test_react_retries_truncated_responses() -> None:
    assert "http.client.HTTPException" in REACT
    assert "thought signature" in REACT


def test_subscription_kill_keeps_a_grace_period_after_the_budget() -> None:
    # The container is killed TIMEOUT_GRACE_MINUTES after the budget the agent is told about. A kill at
    # the budget itself produced empty reports whenever an agent was still writing (codex smoke, 2026-09-07).
    assert task_mod.TIMEOUT_GRACE_MINUTES >= 5
    src = (ROOT / "messageboard_audit_bench" / "task.py").read_text()
    assert "timeout_minutes = budget_min + TIMEOUT_GRACE_MINUTES" in src
    assert "timeout_minutes=timeout_minutes" in src
