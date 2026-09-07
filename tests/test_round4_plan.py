from __future__ import annotations

import subprocess
import sys

from scripts.run_round4 import ROOT, command, expand_jobs, load_manifest, summary


def test_round4_has_full_base_grid_and_one_astra_react_sample() -> None:
    manifest = load_manifest()
    jobs = expand_jobs(manifest)
    exploratory = [job for job in jobs if job.system_id.endswith("exploratory")]
    base = [job for job in jobs if job not in exploratory]
    expected_systems = {
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "codex-gpt-5-6-sol",
        "codex-gpt-5-6-terra",
        "codex-gpt-5-6-luna",
        "codex-gpt-6-astra",
        "react-gpt-5-6-sol",
        "react-gemini-3-8-flash",
        "react-muse-spark-1-3",
        "react-kimi-k3",
        "react-glm-5-3",
    }

    assert {job.system_id for job in base} == expected_systems
    assert all(job.epochs == 3 for job in base)
    assert all(
        {job.budget_minutes for job in base if job.system_id == system_id}
        == {10, 30, 120}
        for system_id in {job.system_id for job in base}
    )
    assert len(exploratory) == 1
    assert exploratory[0].model == "openrouter/openai/gpt-6-astra"
    assert exploratory[0].budget_minutes == 120
    assert exploratory[0].epochs == 1
    assert summary(jobs) == "40 jobs, 118 samples, 106 nominal agent-hours"


def test_backends_and_muse_limit_are_explicit() -> None:
    manifest = load_manifest()
    jobs = expand_jobs(manifest)

    assert all(
        job.backend == "subscription"
        for job in jobs
        if job.agent in {"claude", "codex"}
    )
    assert all(job.backend == "inspect" for job in jobs if job.agent == "react")
    muse = next(job for job in jobs if "muse" in job.model)
    muse_command = command(manifest, muse)
    assert muse.max_connections == 2
    assert muse_command[muse_command.index("--max-connections") + 1] == "2"
    assert muse_command[muse_command.index("--model") + 1].startswith("openrouter/")


def test_generation_is_unscored_and_default_cli_cannot_launch() -> None:
    manifest = load_manifest()
    job = expand_jobs(manifest)[0]
    assert command(manifest, job)[-2:] == ["--", "--no-score"]

    result = subprocess.run(
        [sys.executable, "scripts/run_round4.py", "--system", job.system_id],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DRY RUN: nothing launched" in result.stdout
    assert "--subscription-model claude-opus-5" in result.stdout
