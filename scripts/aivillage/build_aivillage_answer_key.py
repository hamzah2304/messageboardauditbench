#!/usr/bin/env python3
"""Write the AI Village answer key in the answer-key-v1 format: benchmarks/aivillage/answer-key.json.

    python3 scripts/aivillage/build_aivillage_answer_key.py

Reads benchmarks/aivillage/findings/final-findings.json (the QA'd key: extraction, merge,
check against the records, adjudication, Oscar's reviews). Findings in groups keep and rewrite become
findings; drop and needs-screenshots go to `excluded` with their removal bucket. Within a kept finding,
dropped subfindings go to `excluded` too. The earlier QA maps onto the qa blocks: keep -> keep, rewrite
-> narrow (the wording is already the corrected one), the verifier's verdict onto each subfinding's
verdict, and its record citations onto evidence. Fields the earlier process never produced stay None
(overstated). Kept findings passed Oscar's significance cut, so they are major.

Then adds the open review items: citation failures from citation-check-remaining.json
(scripts/aivillage/check_aivillage_key_citations.py, the 84 findings whose citations were never checked), and any pair QA results passed with --qa-results (scripts/run_answer_key_qa.py aivillage ... --group).
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Loaded from its file, not via sys.path: the package folder also holds a benchmarks.py that would
# shadow the top-level benchmarks package for anything imported later.
_spec = importlib.util.spec_from_file_location("answer_key", ROOT / "slopvestigator_bench/answer_key.py")
answer_key = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_key)

DIR = ROOT / "benchmarks/aivillage/findings"
KINDS = answer_key.CITATION_KINDS["aivillage"]


def sub(s):
    v = s.get("verifier_verdict") or ""
    return {
        "id": s["id"], "claim": s["claim"], "significance": "major", "judge_notes": " ".join(s.get("notes") or []),
        "evidence": answer_key.evidence([s["records"]] if s.get("records") else [], KINDS),
        "fields": {"original_claim": s.get("original_claim", ""), "decided_by": s.get("decided_by", ""),
                   "checked_twice": s.get("checked_twice", False),
                   "needs_reasoning_traces": s.get("needs_reasoning_traces", False)},
        "qa": {"verdict": {"partly supported": "partly", "outside the records": "outside the data",
                           "not checked": "not found"}.get(v, v or "supported"),
               "overstated": None, "duplicate_of": "", "reason": s.get("reason", ""),
               "proposed_wording": ""},
    }


def build(findings, cite_remaining):
    out, excluded, queue = [], [], []
    for f in findings:
        if f["group"] not in ("keep", "rewrite"):
            excluded.append({"id": f["id"], "kind": "finding", "claim": f["headline"],
                             "reason": f"{f['group']}: {f.get('removal_bucket') or ''} {f.get('reason') or ''}".strip()})
            continue
        subs, dropped = [], []
        for s in f["subfindings"]:
            (subs if s["decision"] in ("keep", "rewrite") else dropped).append(s)
        excluded += [{"id": s["id"], "kind": "subfinding", "parent": f["id"], "claim": s["claim"],
                      "reason": f"{s['decision']}: {s.get('reason', '')}"} for s in dropped]
        out.append({
            "id": f["id"], "claim": f["headline"], "detail": f.get("summary_reconciled") or f["finding"],
            "significance": "major", "judge_notes": " ".join(f.get("notes") or []), "evidence": [],
            "fields": {"behavior_dates": f.get("behavior_dates", ""),
                       "sources": [{"id": s["id"], "type": s["source"].get("type", ""), "url": s["source"].get("url", ""),
                                    "date": s.get("source_date", "")} for s in f.get("sources", [])],
                       "original_claim": f.get("original_headline", ""), "decided_by": f.get("decided_by", "")},
            "qa": {"outcome": "narrow" if f["group"] == "rewrite" else "keep", "reason": f.get("reason", ""),
                   "duplicate_of": "", "proposed_wording": "", "make_harder": "",
                   "how_to_find": f.get("how_to_find", ""), "run": "earlier AI Village QA (verify + adjudicate)"},
            "subfindings": [sub(s) for s in subs],
        })
        failures = []
        for r in cite_remaining.get(f["id"], {}).get("subfindings", []):
            failures += [dict(x, subfinding=r["id"]) for x in r["failures"] if r["decision"] in ("keep", "rewrite")]
        if failures:
            queue.append({"id": f["id"], "why": "citation check: " + "; ".join(
                f"{x.get('subfinding', '')} {x['status']} {x['kind']}:{x['id'][:8]} \"{(x.get('quote') or '')[:60]}\"".strip()
                + (f" (quote is in {', '.join(i[:13] for i in x['quote_found_in'])})" if x.get("quote_found_in") else "")
                for x in failures)})
    return out, excluded, queue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa-results", type=Path, nargs="*", default=[], help="results/<id>.json from run_answer_key_qa.py")
    a = ap.parse_args()
    findings = json.loads((DIR / "final-findings.json").read_text())
    cr_path = DIR / "citation-check-remaining.json"
    cite_remaining = {r["id"]: r for r in json.loads(cr_path.read_text())["results"]} if cr_path.exists() else {}
    out, excluded, queue = build(findings, cite_remaining)
    key = {"format": answer_key.FORMAT, "eval": "aivillage",
           "source": "benchmarks/aivillage/findings/final-findings.json",
           "qa_process": {"earlier": "extraction, merge, check against the records, adjudication; see "
                                     "benchmarks/aivillage/findings/README.md"},
           "findings": out, "excluded": excluded, "review_queue": queue}
    by_id = {f["id"]: i for i, f in enumerate(out)}
    for p in a.qa_results:
        r = json.loads(p.read_text())
        i = by_id[r["id"]]
        key["findings"][i] = answer_key.apply_qa(out[i], r, KINDS, run=r.get("run_dir", ""))
        why = f"pair QA ({r.get('outcome')}): {r.get('reason', '')}"
        if r.get("duplicate_of"):
            why += f" Duplicate of {r['duplicate_of']}."
        key["review_queue"].append({"id": r["id"], "why": why})
    problems = answer_key.validate(key)
    if problems:
        raise SystemExit("\n".join(problems))
    answer_key.dump(key, ROOT / "benchmarks/aivillage/answer-key.json")
    print(f"{len(out)} findings, {len(excluded)} excluded, {len(key['review_queue'])} in the review queue")


if __name__ == "__main__":
    main()
