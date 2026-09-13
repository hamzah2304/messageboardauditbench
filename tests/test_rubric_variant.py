"""The anthropic rubric variant: swapped sheets and answer key, default path untouched."""

import re

import pytest

from messageboard_audit_bench.grading import core

MAKER = re.compile(r"openai|chatgpt|\bgpt\b|\boai\b|codex", re.I)


def test_variant_for_data():
    assert core.variant_for_data("verbatim_anthropic") == "anthropic"
    assert core.variant_for_data("verbatim") is None
    assert core.variant_for_data(None) is None


def test_unknown_variant_rejected():
    with pytest.raises(ValueError):
        core.load_sheets("v2", "gemini")


def test_mythos_modes_use_their_own_sheets_and_answer_key():
    sets, templates = core.load_sheets("m5")
    assert len(sets) == 3
    assert sum(len(sheet["claims"]) for sheet in sets) == 13
    assert set(templates) == {"M1", "M2", "M3"}
    assert "{{HUMAN_REPORT}}" in templates["M1"]
    assert "Claude Mythos 5" in core.human_report(mode="m5")

    summary_sets, _ = core.load_sheets("m5tldrh")
    assert [sheet["rubric_id"] for sheet in summary_sets] == ["M5TLDRH"]


def test_mythos_mode_rejects_provider_swap_variant():
    with pytest.raises((ValueError, FileNotFoundError)):
        core.load_sheets("m5", "anthropic")


def test_rubyhack_modes_use_their_own_sheets_and_answer_key():
    sets, templates = core.load_sheets("rh")
    assert len(sets) == 3
    assert sum(len(sheet["claims"]) for sheet in sets) == 12
    assert set(templates) == {"RH1", "RH2", "RH3"}
    assert "RubyHack package-corpus answer key" in core.human_report(mode="rh")

    summary_sets, _ = core.load_sheets("rhtldrh")
    assert [sheet["rubric_id"] for sheet in summary_sets] == ["RHTLDRH"]


@pytest.mark.parametrize("mode", ["v2", "tldrh", "recall", "contradiction", "tldr"])
def test_variant_sheets_name_the_swapped_maker(mode):
    sets, templates = core.load_sheets(mode, "anthropic")
    base_sets, base_templates = core.load_sheets(mode)
    # same claim ids and grading modes, only the wording differs
    assert [c["id"] for s in sets for c in s["claims"]] == [
        c["id"] for s in base_sets for c in s["claims"]
    ]
    for rid, text in templates.items():
        assert not MAKER.search(text), f"{mode}/{rid} still names the original maker"
        assert "{{HUMAN_REPORT}}" in text and "{{MODEL_REPORT}}" in text
        assert base_templates[rid] != text or not MAKER.search(base_templates[rid])


def test_answer_key_is_swapped_and_default_is_not():
    swapped, original = core.human_report("anthropic"), core.human_report()
    assert "OpenAI" in original and "OpenAI" not in swapped
    assert "Anthropic" in swapped
    # Azure -> AWS; the report's real AWS mentions stay; only the victim's "Azure B2C" survives
    assert not re.search(r"\bAzure\b(?! B2C)", swapped)
    assert "traced to AWS, DigitalOcean, and Tor" in swapped
    assert "Azure B2C" in swapped and "20.223.25.152" in swapped
    # no lineage to an earlier incident
    assert not re.search(r"hugging ?face|artifactory|exploitgym|\bMETR\b|another example|distinct swarm", swapped, re.I)
    assert len(swapped.splitlines()) < len(original.splitlines()) - 80


def test_build_prompt_uses_variant_answer_key():
    sets, templates = core.load_sheets("v2", "anthropic")
    _, prefix, _ = core.build_prompt("v2", sets[0]["rubric_id"], "# TL;DR\nx", templates, "anthropic")
    assert "OpenAI" not in prefix and "Anthropic" in prefix
    _, base_prefix, _ = core.build_prompt("v2", sets[0]["rubric_id"], "# TL;DR\nx")
    assert "OpenAI" in base_prefix


def test_out_dir_separates_variants():
    assert core.out_dir("gpt-5.6-sol", "v2", "anthropic").name == "variant_anthropic"
    assert core.out_dir("gpt-5.6-sol", "v2").name == "v2"


def test_variant_version_and_aggregate_stamp():
    assert core.variant_version(None) is None
    assert core.variant_version("anthropic") not in (None, "unversioned")
    per = {"N07": {"id": "N07", "score": 1.0}}
    out = core.aggregate("k", "t", "gpt-5.6-sol", "v2", per, {"V2": {"score": 1.0, "max": 1}}, None, "anthropic")
    assert out["rubric_variant"] == "anthropic"
    assert out["rubric_variant_version"] == core.variant_version("anthropic")
    plain = core.aggregate("k", "t", "gpt-5.6-sol", "v2", per, {"V2": {"score": 1.0, "max": 1}})
    assert "rubric_variant" not in plain
