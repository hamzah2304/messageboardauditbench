"""Regression guards for operational failures observed in prior runs."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_TRIAL = (ROOT / "sandbox" / "docker" / "run_trial.sh").read_text()
REACT = (ROOT / "sandbox" / "react_agent.py").read_text()
POSTPROCESS = (ROOT / "scripts" / "postprocess_trial.py").read_text()
NATIVE = (ROOT / "messageboard_audit_bench" / "native.py").read_text()
MATRIX = ROOT / "scripts" / "run_inspect_matrix.sh"


def test_claude_long_lived_token_is_preferred_over_copied_credentials() -> None:
    token = RUN_TRIAL.index("runs/.claude-oauth-token")
    credentials = RUN_TRIAL.index('cp "$ROOT/runs/.claude-home/.credentials.json"')

    assert token < credentials
    assert "CLAUDE_CODE_OAUTH_TOKEN" in RUN_TRIAL


def test_codex_relaunches_twice_when_model_is_at_capacity() -> None:
    assert "is at capacity" in RUN_TRIAL
    assert "for attempt in 1 2 3" in RUN_TRIAL
    assert '"turn.completed"' in RUN_TRIAL


def test_claude_model_switching_is_not_disabled() -> None:
    assert '"switchModelsOnFlag":false' not in RUN_TRIAL
    assert "switchModelsOnFlag" not in NATIVE
    assert 'meta["model_served"]' in POSTPROCESS


def test_react_retries_truncated_http_responses() -> None:
    assert "http.client.HTTPException" in REACT
    assert "thought signature" in REACT


def test_matrix_cli_uses_config_and_inspect_epochs() -> None:
    result = subprocess.run(
        [
            str(MATRIX),
            "--agent",
            "claude",
            "--config",
            "blind",
            "--model",
            "mockllm/model",
            "--epochs",
            "3",
            "--dry-run",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "config=blind" in result.stdout
    assert "--epochs 3" in result.stdout
    assert "condition" not in result.stdout


def test_subscription_solver_does_not_block_the_event_loop() -> None:
    # A blocking subprocess.run inside the async solver serialized every sample of an eval regardless of
    # --max-samples (audit 2026-09-07). The runner must be awaited.
    src = (ROOT / "messageboard_audit_bench" / "solver.py").read_text()
    solve_body = src[src.index("def subscription_agent"):src.index("def replay")]
    assert "subprocess.run(" not in solve_body
    assert "await _run_async(" in solve_body
