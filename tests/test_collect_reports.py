import hashlib
import json
import subprocess
import sys
from pathlib import Path

from messageboard_audit_bench.runtime import repo_root


def _trial(
    runs: Path,
    name: str,
    *,
    config: str,
    include_condition: bool,
    timeout: str = "25m",
) -> None:
    run = runs / name
    work = run / "work"
    work.mkdir(parents=True)
    prompt = "Investigate the logs. Time budget: you have 20 minutes.\n"
    (work / "prompt.txt").write_text(prompt)
    (run / "report.md").write_text("# Report\n")
    meta = {
        "exit_code": 0,
        "agent": "codex",
        "model": "gpt-test",
        "replicate": 1,
        "config": config,
        "prompt": "blind",
        "budget_min": 20,
        "timeout": timeout,
        "data_variant": "verbatim",
        "effort": "xhigh",
    }
    if include_condition:
        meta["condition"] = "blind"
    (run / "meta.json").write_text(json.dumps(meta))


def test_collect_reports_normalizes_legacy_and_new_condition_names(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    _trial(
        runs,
        "20260101T000000Z_codex_old",
        config="blind-20",
        include_condition=False,
    )
    _trial(
        runs,
        "20260102T000000Z_codex_new",
        config="blind",
        include_condition=True,
        timeout="30m",
    )
    out = tmp_path / "reports"

    subprocess.run(
        [
            sys.executable,
            str(repo_root() / "scripts" / "collect_reports.py"),
            "--runs",
            str(runs),
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    prompt = "Investigate the logs. Time budget: you have 20 minutes.\n"
    prompt_id = hashlib.sha256(prompt.encode()).hexdigest()[:8]
    group = out / f"blind_verbatim_xhigh_p{prompt_id}"
    assert len(list(group.glob("*.md"))) == 2
    rows = [json.loads(line) for line in (out / "index.jsonl").read_text().splitlines()]
    assert {row["condition"] for row in rows} == {"blind"}
    assert {row["config"] for row in rows} == {"blind", "blind-20"}
    conditions = json.loads((group / "CONDITIONS.json").read_text())
    assert "timeout" not in conditions
