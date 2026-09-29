"""scripts/run_eval.py: choosing a benchmark version, without creating worktrees or runs."""

import importlib.util
from pathlib import Path

import pytest

from messageboard_audit_bench.benchmarks import SPECS, normalize_version, version_tag

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("run_eval", ROOT / "scripts/run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


@pytest.mark.parametrize(("given", "expected"), [
    ("10", "10.0"), ("10.0", "10.0"), ("v10.0", "10.0"), ("10-A", "10.0"), ("6-B", "6.1"), ("1.2", "1.2"),
])
def test_versions_normalize_including_the_old_letter_labels(given, expected):
    assert normalize_version(given) == expected


def test_tags_are_named_after_the_public_benchmark_names():
    assert version_tag("messageboard", "9-A") == "german-wiki-report-v9.0"
    assert version_tag("urlquery", "1") == "transluce-report-v1.0"


def test_current_version_runs_in_place_with_the_version_guard(capsys):
    assert run_eval.main(["german-wiki-report", "--dry-run", "--", "-T", "agent=codex"]) == 0
    out = capsys.readouterr().out
    assert "(this checkout)" in out
    assert f"messageboard_audit_bench/german_wiki_report -T version={SPECS['messageboard'].eval_version} -T agent=codex" in out


def test_grading_role_has_no_version_option(capsys):
    run_eval.main(["transluce-report", "--task", "grade", "--dry-run"])
    out = capsys.readouterr().out
    assert "messageboard_audit_bench/transluce_report_grade" in out and "version=" not in out


def test_unknown_version_lists_what_is_tagged(monkeypatch):
    monkeypatch.setattr(run_eval, "tags_for", lambda name: [f"{name}-v9.0"])
    with pytest.raises(SystemExit, match="german-wiki-report-v9.0"):
        run_eval.plan("german-wiki-report", "3.0", "run")


def test_older_versions_use_the_task_name_they_had(monkeypatch):
    sources = {"old": "def messageboard_audit_bench(", "new": 'x = task(name="german_wiki_report")'}
    monkeypatch.setattr(run_eval, "source_at", lambda ref, path: sources[ref] if "task.py" in path else "")
    assert run_eval.task_name("old", "german_wiki_report") == "messageboard_audit_bench"
    assert run_eval.task_name("old", "transluce_report_grade") == "urlquery_grade_reports"
    assert run_eval.task_name("new", "german_wiki_report") == "german_wiki_report"
    assert not run_eval.has_version_guard("old")


def test_a_tagged_version_gets_its_own_reusable_checkout(monkeypatch, tmp_path):
    monkeypatch.setattr(run_eval, "tags_for", lambda name: [f"{name}-v9.0"])
    monkeypatch.setattr(run_eval, "primary_root", lambda: tmp_path)
    plan = run_eval.plan("german-wiki-report", "9-A", "run")
    assert plan["tag"] == "german-wiki-report-v9.0" and plan["create"]
    assert plan["checkout"] == tmp_path / ".worktrees/version-german-wiki-report-v9.0"


def test_shared_state_is_linked_not_copied(tmp_path):
    primary, worktree = tmp_path / "primary", tmp_path / "wt"
    (primary / "data/verbatim").mkdir(parents=True)
    (primary / "data/verbatim/events.jsonl").write_text("{}\n")
    (primary / "data/transluce").mkdir()
    (primary / "runs").mkdir()
    (worktree / "data/verbatim").mkdir(parents=True)  # tracked placeholder
    run_eval.link_shared(primary, worktree)
    assert (worktree / "runs").is_symlink() and (worktree / "data/transluce").is_symlink()
    assert (worktree / "data/verbatim/events.jsonl").is_symlink()
    assert not (worktree / "data/verbatim").is_symlink()
