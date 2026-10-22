import importlib.util
import json
from pathlib import Path

from slopvestigator_bench import answer_key

ROOT = Path(__file__).resolve().parents[1]

KINDS = answer_key.CITATION_KINDS["german-wiki"]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _finding():
    return {"id": "W01", "claim": "c", "detail": "", "significance": None, "judge_notes": "", "evidence": [],
            "fields": {}, "qa": None,
            "subfindings": [{"id": "N01", "claim": "s", "significance": None, "judge_notes": "", "evidence": [],
                             "fields": {}, "qa": None}]}


def test_parse_citations_handles_quotes_and_bare_ids():
    text = 'They said so [rev:dse~Page@3 "exact words"; event:request:dse:0 "x"] and [label:OpenAIResearcher].'
    refs = [(c["ref"], c["quote"]) for c in answer_key.parse_citations(text, KINDS)]
    assert refs == [("rev:dse~Page@3", "exact words"), ("event:request:dse:0", "x"), ("label:OpenAIResearcher", "")]


def test_apply_qa_merges_and_validates():
    result = {"id": "W01", "outcome": "Narrow", "reason": "r", "significance": "major", "duplicate_of": "",
              "proposed_claim": "p", "make_harder": "", "how_to_find": "h", "evidence": ['[page:dse/X]'],
              "subfindings": [{"id": "N01", "verdict": "partly supported", "overstated": True, "significance": "minor",
                               "reason": "why", "proposed_claim": "REMOVE", "evidence": ['[rev:a@1 "q"]']}]}
    assert answer_key.qa_problems(result, _finding()) == []
    f = answer_key.apply_qa(_finding(), result, KINDS, run="runs/x")
    assert f["qa"]["outcome"] == "narrow" and f["qa"]["proposed_wording"] == "p"
    s = f["subfindings"][0]
    assert s["qa"]["verdict"] == "partly" and s["qa"]["overstated"] == "yes" and s["significance"] == "minor"
    assert s["evidence"][0]["citations"][0] == {"ref": "rev:a@1", "quote": "q", "check": "unchecked"}
    key = {"format": answer_key.FORMAT, "findings": [f], "excluded": []}
    assert answer_key.validate(key) == []


def test_qa_problems_catches_missing_subfindings_and_bad_values():
    bad = {"id": "W01", "outcome": "maybe", "significance": "huge", "subfindings": []}
    problems = answer_key.qa_problems(bad, _finding())
    assert any("outcome" in p for p in problems) and any("subfindings" in p for p in problems)


def test_german_wiki_key_builds_from_v2_points():
    build = _script("build_german_wiki_answer_key")
    claims = json.loads((ROOT / "benchmarks/german-wiki/claims/claims_v2.json").read_text())["claims"]
    key = build.build(claims, {"model": "m", "sections": []})
    assert answer_key.validate(key) == []
    assert len(key["findings"]) == 12
    assert [s["id"] for f in key["findings"] for s in f["subfindings"]] == [c["id"] for c in claims]


def test_committed_answer_keys_are_valid():
    paths = sorted((ROOT / "benchmarks").glob("*/answer-key.json"))
    assert {p.parent.name for p in paths} >= {"german-wiki", "aivillage"}
    for path in paths:
        assert answer_key.validate(json.loads(path.read_text())) == [], path


def test_qa_prompt_fills_every_placeholder():
    qa = _script("run_answer_key_qa")
    key = answer_key.load(ROOT / "benchmarks/german-wiki/answer-key.json")
    text = qa.build_prompt("german-wiki", key, [key["findings"][1]], "")
    assert "{{" not in text.replace("{{BUDGET_MIN}}", "")
    assert "DERIVABILITY" in text and "DATA NOTE: GERMAN WIKI" in text and "W02 —" in text
