"""One eligibility rule for every benchmark: fail closed, never retry."""
import json

from slopvestigator_bench import eligibility

GOOD = {"model": "claude-opus-5", "report_exists": True, "report_words": 2800, "minimum_runtime_reached": True,
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
