"""Standard results: every run is a row, cells average eligible scored runs with an interval."""
import json

from slopvestigator_bench import results

GOOD = {"benchmark_id": "aivillage", "exit_code": 0, "report_exists": True, "report_words": 9000, "minimum_runtime_reached": True,
        "report_length_compliant": True, "data_manifest_status": "matches_manifest", "termination": "normal",
        "budget_min": 30}


def _run(root, name, **meta):
    run = root / "runs" / name
    run.mkdir(parents=True)
    (run / "meta.json").write_text(json.dumps({**GOOD, **meta}))
    (run / "usage.json").write_text(json.dumps({"cost_usd": 2.0}))
    return run


def test_rows_cells_and_intervals(tmp_path, monkeypatch):
    for rep in (1, 2, 3):
        _run(tmp_path, f"20261022T00000{rep}Z_codex_gpt-6-luna_r{rep}_aivillage-std-30_x", model="gpt-6-luna", replicate=rep)
    _run(tmp_path, "20261022T000004Z_claude_claude-opus-5_r1_aivillage-std-30_y", model="claude-opus-5", replicate=1,
         model_served="claude-opus-4-8", model_fallback={"fallback_model": "claude-opus-4-8"}, safety_flags=1)
    grades = {("aivillage", f"20261022T00000{rep}Z_codex_gpt-6-luna_r{rep}_aivillage-std-30_x"): {"score": s}
              for rep, s in ((1, 0.3), (2, 0.4), (3, 0.5))}
    monkeypatch.setattr(results, "grades_from_logs", lambda _: grades)
    table = results.rows(tmp_path, tmp_path)
    assert len(table) == 4 and sum(r.eligible for r in table) == 3
    by_model = {c["model"]: c for c in results.cells(table)}
    luna, opus = by_model["gpt-6-luna"], by_model["claude-opus-5"]
    assert abs(luna["score"] - 0.4) < 1e-9 and luna["ci_low"] <= 0.4 <= luna["ci_high"] and luna["cost_usd"] == 2.0
    assert opus["score"] is None and opus["runs"] == 1 and opus["eligible"] == 0 and opus["safety_flagged_runs"] == 1


def test_runs_of_an_older_config_version_are_left_out(tmp_path, monkeypatch):
    from slopvestigator_bench import standard

    _run(tmp_path, "20261022T000001Z_codex_gpt-6-luna_r1_aivillage-std-30_x", model="gpt-6-luna", replicate=1,
         config_sha256="0" * 64)
    _run(tmp_path, "20261022T000002Z_codex_gpt-6-luna_r2_aivillage-std-30_y", model="gpt-6-luna", replicate=2,
         config_sha256=standard.config_sha256("aivillage-std-30"))
    monkeypatch.setattr(results, "grades_from_logs", lambda _: {})
    assert [r.run for r in results.rows(tmp_path, tmp_path)] == ["20261022T000002Z_codex_gpt-6-luna_r2_aivillage-std-30_y"]


def test_german_wiki_headline_needs_both_rubrics():
    assert results.combine("messageboard", {"v2": 0.5}) is None
    assert abs(results.combine("messageboard", {"v2": 0.5, "tldrh": 1.0}) - 0.65) < 1e-9
    assert results.strict(0.4) == 0.0 and results.strict(0.75) == 0.5
