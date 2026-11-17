#!/usr/bin/env python3
"""Build benchmarks/german-wiki/answer-key.json (answer-key-v1) from the v2 points, before QA.

    python3 scripts/build_german_wiki_answer_key.py [--out FILE]

One finding per section of benchmarks/german-wiki/claims/claims_v2.json (W01 to W12, in section order); the
section's points become its subfindings with their ids (N01 to N38) and grader notes kept. The
headline and detail of each finding come from the drafts in
benchmarks/german-wiki/answer-key-headline-drafts.json (scripts/draft_answer_key_headlines.py),
marked as drafts awaiting approval. Significance, evidence and the qa blocks stay empty until
scripts/run_answer_key_qa.py fills them. The v2 grading path is unchanged; it still reads claims_v2.json.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Loaded from its file, not via sys.path: the package folder also holds a benchmarks.py that would
# shadow the top-level benchmarks package for anything imported later.
_spec = importlib.util.spec_from_file_location("answer_key", ROOT / "slopvestigator_bench/answer_key.py")
answer_key = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_key)

CLAIMS = ROOT / "benchmarks/german-wiki/claims/claims_v2.json"
DRAFTS = ROOT / "benchmarks/german-wiki/answer-key-headline-drafts.json"
OUT = ROOT / "benchmarks/german-wiki/answer-key.json"

EXCLUDED = [
    {"id": "C15", "kind": "claim",
     "claim": "Starting June 21 the pages were visited by 13 new IPs registered to OpenAI headquarters in San "
              "Francisco showing human-like browsing patterns, plus 42 more IPs with very similar behaviour.",
     "reason": "Not derivable: it rests on access logs and IP ownership the data does not contain (both "
               "feasibility passes, benchmarks/german-wiki/feasibility/). Left out of the v2 points."},
    {"id": "C08", "kind": "claim",
     "claim": "Agents made backup pages whose names start with ZZZ so they would last longer before deletion.",
     "reason": "Merged into N16 when the v2 points were written."},
]


def build(claims, drafts):
    order = []
    for c in claims:
        if c["section"] not in order:
            order.append(c["section"])
    drafted = {d["section"]: d for d in drafts["sections"]}
    findings = []
    for i, section in enumerate(order, 1):
        d = drafted.get(section, {})
        subs = [{
            "id": c["id"], "claim": c["claim"], "significance": None, "judge_notes": c.get("note") or "",
            "evidence": [],
            "fields": {"descends_from": c.get("descends_from", ""), "report_quote": c.get("report_quote", ""),
                       "spans": c.get("spans", [])},
            "qa": None,
        } for c in claims if c["section"] == section]
        findings.append({
            "id": f"W{i:02d}", "claim": d.get("claim", ""), "detail": d.get("detail", ""), "significance": None,
            "judge_notes": "", "evidence": [],
            "fields": {"section": section, "headline_status": "draft",
                       "headline_source": f"drafted by {drafts.get('model', '?')} from benchmarks/german-wiki/human_report.txt"},
            "qa": None, "subfindings": subs,
        })
    return {
        "format": answer_key.FORMAT, "eval": "german-wiki",
        "source": "benchmarks/german-wiki/claims/claims_v2.json (38 points in 12 sections) and benchmarks/german-wiki/human_report.txt",
        "qa_process": {}, "findings": findings, "excluded": EXCLUDED, "review_queue": [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    key = build(json.loads(CLAIMS.read_text())["claims"], json.loads(DRAFTS.read_text()))
    problems = answer_key.validate(key)
    if problems:
        raise SystemExit("\n".join(problems))
    answer_key.dump(key, a.out)
    print(f"{a.out}: {len(key['findings'])} findings, {sum(len(f['subfindings']) for f in key['findings'])} subfindings")


if __name__ == "__main__":
    main()
