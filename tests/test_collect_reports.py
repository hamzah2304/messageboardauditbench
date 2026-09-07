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
    report_words: int = 2,
    length_meta: dict | None = None,
    report_in_work: bool = False,
) -> None:
    run = runs / name
    work = run / "work"
    work.mkdir(parents=True)
    prompt = "Investigate the logs. Time budget: you have 20 minutes.\n"
    (work / "prompt.txt").write_text(prompt)
    report = "word " * report_words
    (work / "report.md" if report_in_work else run / "report.md").write_text(report)
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
    if length_meta:
        meta.update(length_meta)
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


def test_collect_reports_skips_rejected_reports_unless_requested(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    bounded = {
        "report_min_words": 2,
        "report_max_words": 3,
        "report_accept_min_words": 1,
        "report_accept_max_words": 4,
    }
    _trial(runs, "20260101T000000Z_codex_accepted", config="blind", include_condition=True,
           report_words=4, length_meta=bounded)
    _trial(runs, "20260102T000000Z_codex_rejected", config="blind", include_condition=True,
           report_words=5, length_meta=bounded)
    out = tmp_path / "reports"
    base = [sys.executable, str(repo_root() / "scripts" / "collect_reports.py"), "--runs", str(runs), "--out", str(out)]

    subprocess.run(base, check=True, capture_output=True, text=True)
    rows = [json.loads(line) for line in (out / "index.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["report_words"] == 4
    assert rows[0]["report_length_compliant"] is True
    assert rows[0]["report_rejected"] is False

    subprocess.run([*base, "--include-rejected"], check=True, capture_output=True, text=True)
    rows = [json.loads(line) for line in (out / "index.jsonl").read_text().splitlines()]
    rejected = next(row for row in rows if row["report_rejected"])
    assert rejected["report_words"] == 5
    assert rejected["report_length_compliant"] is False
    assert rejected["report_accept_max_words"] == 4


def test_collect_reports_preserves_disabled_legacy_limits_and_ignores_final_message(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    _trial(runs, "20260101T000000Z_codex_legacy", config="legacy", include_condition=False,
           report_words=1, length_meta={"report_min_words": 0, "report_max_words": 0}, report_in_work=True)
    final_only = runs / "20260102T000000Z_codex_final_only"
    final_only.mkdir()
    (final_only / "meta.json").write_text(json.dumps({"exit_code": 0, "agent": "codex", "model": "gpt-test"}))
    (final_only / "final_message.md").write_text("do not export")
    out = tmp_path / "reports"

    subprocess.run([sys.executable, str(repo_root() / "scripts" / "collect_reports.py"), "--runs", str(runs), "--out", str(out)],
                   check=True, capture_output=True, text=True)

    rows = [json.loads(line) for line in (out / "index.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["report_length_compliant"] is None
    assert rows[0]["report_rejected"] is False
