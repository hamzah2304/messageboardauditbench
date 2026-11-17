"""One eligibility rule for every benchmark: fail closed, never retry."""
import json

from slopvestigator_bench import eligibility

GOOD = {"exit_code": 0, "model": "claude-opus-5", "report_exists": True, "report_words": 2800, "minimum_runtime_reached": True,
        "report_length_compliant": True, "data_manifest_status": "matches_manifest", "termination": "normal"}


def test_a_clean_run_counts():
    v = eligibility.check_meta(GOOD)
    assert v.eligible and v.reasons == () and v.served_model == "claude-opus-5"


def test_each_failure_is_named():
    cases = {
        "model_switched": {"model_fallback": {"fallback_model": "claude-opus-4-8"}, "model_served": "claude-opus-4-8"},
        "refused": {"model_refusal": {"terminal": True}},
        "no_report": {"report_exists": False},
        "below_minimum_runtime": {"minimum_runtime_reached": False},
        "report_length": {"report_length_compliant": False},
        "data_unverified": {"data_manifest_status": "no_manifest_entry"},
        "ended_error": {"termination": "error"},
    }
    for reason, change in cases.items():
        v = eligibility.check_meta({**GOOD, **change})
        assert not v.eligible and reason in v.reasons, reason


def test_missing_fields_count_against_the_run(tmp_path):
    assert eligibility.check(tmp_path).reasons == ("no_meta",)
    (tmp_path / "meta.json").write_text(json.dumps({"model": "gpt-6-luna"}))
    v = eligibility.check(tmp_path)
    assert not v.eligible and {"no_report", "below_minimum_runtime", "data_unverified"} <= set(v.reasons)


def test_same_model_accepts_snapshots_not_other_versions():
    from slopvestigator_bench.model_ids import same_model
    assert same_model("openai/gpt-6.1-sol", "gpt-6.1-sol-2026-09-29")
    assert same_model("claude-opus-5", "claude-opus-5-20260724")
    assert same_model("deepseek/deepseek-v4.1-flash-1017", "deepseek/deepseek-v4.1-flash")
    assert not same_model("claude-opus-5", "claude-opus-5-5")
    assert not same_model("claude-opus-5", "claude-opus-4-8")
    assert not same_model("gpt-6-luna", "gpt-6-luna-pro")


def test_same_model_checks_the_owner_and_unfinished_runs_do_not_count():
    from slopvestigator_bench.model_ids import same_model
    assert same_model("openrouter/openai/gpt-6.1-sol", "openai/gpt-6.1-sol")
    assert same_model("openai/gpt-6.1-sol", "gpt-6.1-sol")
    assert not same_model("openrouter/openai/gpt-6.1-sol", "other/gpt-6.1-sol")
    v = eligibility.check_meta({k: v for k, v in GOOD.items() if k != "exit_code"})
    assert not v.eligible and "unfinished" in v.reasons


def test_a_run_that_survived_safety_flags_through_retries_counts_and_keeps_the_count():
    v = eligibility.check_meta({**GOOD, "safety_flags": 2, "safeguard_retries": 2, "safeguard_retry_limit": 3})
    assert v.eligible and v.safety_flags == 2
    exhausted = eligibility.check_meta({**GOOD, "safety_flags": 4, "safeguard_retries_exhausted": True,
                                        "model_refusal": {"terminal": True}})
    assert not exhausted.eligible and "refused" in exhausted.reasons
