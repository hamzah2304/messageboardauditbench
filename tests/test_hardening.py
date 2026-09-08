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


def test_subscription_proxy_is_scoped_to_the_selected_agent() -> None:
    assert '--agent "$AGENT"' in RUN_TRIAL


def test_subscription_never_mounts_two_cli_credential_directories() -> None:
    # The canary deliberately has no credentials; a real agent gets only the
    # one directory selected by AGENT_SECRET_MOUNTS.
    assert 'CANARY_ARGS=("${DOCKER_BASE[@]}" "$IMAGE")' in RUN_TRIAL
    assert 'AGENT_SECRET_MOUNTS=(-v "$SECRETS/claude:/home/agent/.claude")' in RUN_TRIAL
    assert 'AGENT_SECRET_MOUNTS=(-v "$SECRETS/codex:/home/agent/.codex")' in RUN_TRIAL
    assert '-v "$SECRETS/claude:/home/agent/.claude" -v "$SECRETS/codex:/home/agent/.codex"' not in RUN_TRIAL


def test_codex_capacity_retries_preserve_attempts_and_one_deadline() -> None:
    assert 'HARD_DEADLINE="$((START + $(timeout_seconds "$TIMEOUT")))"' in RUN_TRIAL
    assert '"${remaining}s" codex "${CODEX_CMD[@]}"' in RUN_TRIAL
    assert 'CODEX_CMD=(exec resume "$PARENT_THREAD_ID")' in RUN_TRIAL
    assert 'CODEX_CMD=(exec -C /work)' in RUN_TRIAL
    assert '"$RUN/transcript.attempt$attempt.jsonl"' in RUN_TRIAL
    assert '"$RUN/stderr.attempt$attempt.log"' in RUN_TRIAL
    assert 'sleep_seconds=$((remaining < 30 ? remaining : 30))' in RUN_TRIAL


def test_future_subscription_runs_capture_reproducible_provenance() -> None:
    for artifact in (
        "config.source.toml",
        "config.rendered.json",
        "git.commit",
        "git.dirty.patch",
        "code_snapshot.tar.gz",
        "image.inspect.json",
        "cli.version.txt",
    ):
        assert artifact in RUN_TRIAL
    assert "subscription_allowlisted_provider_proxy" in RUN_TRIAL
    assert "accepted_isolation_tradeoff" in RUN_TRIAL
    assert "config_rendered_sha256" in RUN_TRIAL
    assert "code_snapshot_sha256" in RUN_TRIAL


def test_subscription_artifact_collection_rejects_agent_created_symlinks() -> None:
    assert '[ -L "$source" ]' in RUN_TRIAL
    assert "symlink_rejected" in RUN_TRIAL
    assert '"launch_status":"preparing"' in RUN_TRIAL



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
