import subprocess

import pytest

from messageboard_audit_bench.runtime import repo_root


def _resolve(
    config_budget: int,
    config_timeout: int,
    budget: str = "",
    timeout: str = "",
) -> str:
    helper = repo_root() / "sandbox" / "docker" / "resolve_timeout.sh"
    script = (
        'CFG_BUDGET_MIN="$1"; CFG_TIMEOUT_MIN="$2"; '
        'BUDGET_MIN="$3"; TIMEOUT="$4"; . "$5"; '
        'resolve_trial_time; printf "%s|%s" "$BUDGET_MIN" "$TIMEOUT"'
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            script,
            "resolve-timeout",
            str(config_budget),
            str(config_timeout),
            budget,
            timeout,
            str(helper),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@pytest.mark.parametrize(
    ("config_budget", "config_timeout", "budget", "timeout", "expected"),
    [
        (20, 25, "", "", "20|25m"),
        (20, 25, "30", "", "30|35m"),
        (20, 25, "30", "50m", "30|50m"),
        (120, 125, "30", "", "30|35m"),
    ],
)
def test_resolve_trial_time(
    config_budget: int,
    config_timeout: int,
    budget: str,
    timeout: str,
    expected: str,
) -> None:
    assert _resolve(config_budget, config_timeout, budget, timeout) == expected
