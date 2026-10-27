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


def test_review_decisions_accept_qa_and_apply_overrides_once():
    mod = _script("apply_answer_key_review")
    f = _finding()
    f["detail"] = "old detail"
    f["fields"] = {"headline_status": "draft"}
    f["qa"] = {"outcome": "narrow", "reason": "r", "duplicate_of": "", "proposed_wording": "narrowed",
               "make_harder": "be specific", "how_to_find": ""}
    f["subfindings"].append({**f["subfindings"][0], "id": "N02", "qa": {"proposed_wording": "REMOVE", "duplicate_of": "N01",
                                                                       "reason": "same sentence"}})
    key = {"format": answer_key.FORMAT, "findings": [f], "excluded": []}
    review = {"default": "accept_qa", "overrides": {"N01": {"why": "x", "claim": "mine"}},
              "detail_edits": {"W01": [["old", "new"]]}}
    out = mod.apply(key, review, "r.json")
    w = out["findings"][0]
    assert (w["claim"], w["detail"], w["judge_notes"], w["fields"]["headline_status"]) == (
        "narrowed", "new detail", "be specific", "approved")
    assert [s["claim"] for s in w["subfindings"]] == ["mine"]
    assert out["excluded"][0]["id"] == "N02" and out["excluded"][0]["reason"].startswith("merged into N01")
    assert answer_key.validate(out) == []
    try:
        mod.apply(out, review, "r.json")
    except SystemExit:
        pass
    else:
        raise AssertionError("applied twice")


def _overlap_key():
    def sub(i):
        return {"id": i, "claim": f"claim {i}", "significance": "minor", "judge_notes": "", "evidence": [],
                "fields": {}, "qa": None}

    def finding(i, subs):
        return {**_finding(), "id": i, "claim": f"claim {i}", "detail": f"detail {i}", "subfindings": [sub(s) for s in subs]}

    return {"format": answer_key.FORMAT, "excluded": [],
            "findings": [finding("W01", ["N01", "N02"]), finding("W02", ["N03"]), finding("W03", ["N04"])]}


def test_overlap_edits_remove_rewrite_move_and_fold():
    mod = _script("apply_answer_key_review")
    key = _overlap_key()
    key["overlap"] = {"applied": "", "kept_separate": [], "overlaps": [
        {"id": "O1", "items": ["N01", "N02"], "sentence": "s", "reason": "N01 keeps it",
         "edits": [{"id": "N02", "action": "remove"}, {"id": "W01", "action": "rewrite", "field": "detail", "text": "new"}]},
        {"id": "O2", "items": ["N03", "W01"], "sentence": "s", "reason": "r", "edits": [{"id": "N03", "action": "move", "to": "W01"}]},
        {"id": "O3", "items": ["W03", "W02"], "sentence": "s", "reason": "r",
         "edits": [{"id": "W03", "action": "fold", "to": "W02", "claim": "folded", "judge_notes": "jn"}]},
        {"id": "O4", "items": ["W02"], "sentence": "s", "reason": "r", "edits": [{"id": "W02", "action": "remove"}]},
    ]}
    assert answer_key.validate(key) == []
    out = mod.apply_overlap(key, rejected=["O4"], date="2026-10-27")
    assert [f["id"] for f in out["findings"]] == ["W01", "W02"]
    w01, w02 = out["findings"]
    assert w01["detail"] == "new" and [s["id"] for s in w01["subfindings"]] == ["N01", "N03"]
    assert w01["subfindings"][1]["fields"]["moved_from"] == "W02"
    assert [(s["id"], s["claim"], s["judge_notes"]) for s in w02["subfindings"]] == [("W03", "folded", "jn")]
    assert {x["id"]: x["reason"].split(";")[0] for x in out["excluded"]} == {
        "N02": "overlap O1: N01 keeps it", "N04": "W03 folded into W02"}
    assert out["overlap"]["applied"] == "2026-10-27" and out["overlap"]["rejected"] == ["O4"]
    assert answer_key.validate(out) == []


def test_overlap_edits_refuse_conflicts_and_overridden_fields():
    mod = _script("apply_answer_key_review")

    def attempt(edits, **kw):
        key = _overlap_key()
        key["overlap"] = {"applied": "", "kept_separate": [], "overlaps": [
            {"id": f"O{i}", "items": [], "sentence": "", "reason": "", "edits": [e]} for i, e in enumerate(edits, 1)]}
        try:
            mod.apply_overlap(key, **kw)
        except SystemExit as exc:
            return str(exc)
        return ""

    assert "two overlap edits" in attempt([{"id": "N01", "action": "remove"}, {"id": "N01", "action": "move", "to": "W02"}])
    assert "removes or folds" in attempt([{"id": "W02", "action": "remove"}, {"id": "N01", "action": "move", "to": "W02"}])
    assert "unknown id" in attempt([{"id": "N99", "action": "remove"}])
    assert "has no detail" in attempt([{"id": "N01", "action": "rewrite", "field": "detail", "text": "x"}])
    assert "hand override" in attempt([{"id": "W01", "action": "rewrite", "field": "claim", "text": "x"}],
                                      protected={("W01", "claim")})


def test_overlap_prompt_fills_every_placeholder():
    ov = _script("run_answer_key_overlap")
    for ev in ("german-wiki", "aivillage", "transluce"):
        key = ov.post_qa_key(ev)
        text = ov.build_prompt(ev, key)
        assert "{{" not in text.replace("{{BUDGET_MIN}}", ""), ev
        assert "## The answer key" in text and "NOTE" in text and key["findings"][0]["id"] + " —" in text
        assert "REMOVE" not in "\n".join(s["claim"] for f in key["findings"] for s in f["subfindings"])


def test_review_applies_overlap_after_qa_unless_rejected():
    mod = _script("apply_answer_key_review")
    key = _overlap_key()
    key["findings"][0]["subfindings"][1]["qa"] = {"proposed_wording": "REMOVE (merge into N01)", "reason": "same"}
    key["overlap"] = {"applied": "", "kept_separate": [], "overlaps": [
        {"id": "O1", "items": ["N03", "N04"], "sentence": "", "reason": "r", "edits": [{"id": "N04", "action": "remove"}]},
        {"id": "O2", "items": ["W02"], "sentence": "", "reason": "r", "edits": [{"id": "W02", "action": "remove"}]}]}
    out = mod.apply(key, {"default": "accept_qa", "overlap_rejected": ["O2"], "date": "d"}, "r.json")
    assert [x["id"] for x in out["excluded"]] == ["N02", "N04"]
    assert out["overlap"]["applied"] == "d" and out["review"]["decisions"] == "r.json"
    assert answer_key.validate(out) == []
