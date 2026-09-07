from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_inspect_matrix.sh"


def _dry_run(model: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(SCRIPT),
            "--backend",
            "inspect",
            "--agent",
            "claude",
            "--config",
            "blind",
            "--model",
            model,
            *extra,
            "--dry-run",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_muse_gets_explicit_two_connection_limit() -> None:
    result = _dry_run("anthropic/claude-muse-5")

    assert result.returncode == 0
    assert "--max-connections 2" in result.stdout


def test_subscription_muse_gets_same_explicit_limit() -> None:
    result = subprocess.run(
        [
            str(SCRIPT),
            "--backend",
            "subscription",
            "--agent",
            "claude",
            "--config",
            "blind",
            "--subscription-model",
            "claude-muse-5",
            "--dry-run",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--max-connections 2" in result.stdout


def test_muse_rejects_conflicting_connection_limit() -> None:
    result = _dry_run("anthropic/claude-muse-5", "--max-connections", "4")

    assert result.returncode == 2
    assert "Muse requires --max-connections 2" in result.stderr


def test_other_models_keep_four_connection_default() -> None:
    result = _dry_run("anthropic/claude-sonnet-5")

    assert result.returncode == 0
    assert "--max-connections 4" in result.stdout
