#!/usr/bin/env python3
"""Apply the review decisions for an answer key (benchmarks/<eval>/answer-key-review.json) to its QA'd key.

    python3 scripts/apply_answer_key_review.py german-wiki [--check]

The decisions file holds the default for every item ("accept_qa"), the items rewritten by hand
("overrides": id -> fields to set) and exact edits to finding details ("detail_edits": id -> [[old, new], ...]).
Accepting QA means: a narrowed proposal replaces the headline or subfinding claim, a REMOVE moves the
subfinding to `excluded`, make_harder is appended to the judge notes, and a drafted headline is marked
approved. The key records the decisions file in `review`; a key that already has one is not applied twice.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("answer_key", ROOT / "slopvestigator_bench/answer_key.py")
answer_key = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_key)


def apply(key: dict, review: dict, review_path: str) -> dict:
    if key.get("review"):
        raise SystemExit(f"key already has review decisions applied ({key['review']['decisions']})")
    if review.get("default") != "accept_qa":
        raise SystemExit(f"unknown default {review.get('default')!r}")
    overrides, edits = review.get("overrides", {}), review.get("detail_edits", {})
    ids = {f["id"] for f in key["findings"]} | {s["id"] for f in key["findings"] for s in f["subfindings"]}
    unknown = (set(overrides) | {k for k in edits if not k.startswith("_")}) - ids
    if unknown:
        raise SystemExit(f"decisions name unknown ids: {sorted(unknown)}")

    findings, excluded = [], list(key.get("excluded", []))
    for f in key["findings"]:
        qa = f.get("qa") or {}
        if f["id"] in overrides:
            f.update({k: v for k, v in overrides[f["id"]].items() if k != "why"})
        elif qa.get("outcome") == "drop":
            excluded.append({"id": f["id"], "kind": "finding", "claim": f["claim"], "reason": qa.get("reason", "")})
            continue
        else:
            if qa.get("proposed_wording"):
                f["claim"] = qa["proposed_wording"]
            if qa.get("make_harder"):
                f["judge_notes"] = f"{f['judge_notes']} {qa['make_harder']}".strip()
        for old, new in edits.get(f["id"], []):
            if f["detail"].count(old) != 1:
                raise SystemExit(f"{f['id']}: detail edit does not match exactly once: {old[:60]!r}")
            f["detail"] = f["detail"].replace(old, new)
        if f.get("fields", {}).get("headline_status") == "draft":
            f["fields"]["headline_status"] = "approved"
        subs = []
        for s in f["subfindings"]:
            sqa = s.get("qa") or {}
            if s["id"] in overrides:
                s.update({k: v for k, v in overrides[s["id"]].items() if k != "why"})
            elif sqa.get("proposed_wording") == "REMOVE":
                why = f"merged into {sqa['duplicate_of']}: " if sqa.get("duplicate_of") else ""
                excluded.append({"id": s["id"], "kind": "subfinding", "claim": s["claim"], "reason": why + sqa.get("reason", "")})
                continue
            elif sqa.get("proposed_wording"):
                s["claim"] = sqa["proposed_wording"]
            subs.append(s)
        f["subfindings"] = subs
        findings.append(f)
    key["findings"], key["excluded"] = findings, excluded
    key["review"] = {"decisions": review_path, "date": review.get("date", ""), "decided_by": review.get("decided_by", "")}
    return key


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("eval")
    ap.add_argument("--check", action="store_true", help="validate and print a summary without writing")
    a = ap.parse_args()
    key_path = ROOT / "benchmarks" / a.eval / "answer-key.json"
    review_rel = f"benchmarks/{a.eval}/answer-key-review.json"
    key = apply(answer_key.load(key_path), json.loads((ROOT / review_rel).read_text()), review_rel)
    problems = answer_key.validate(key)
    if problems:
        sys.exit("invalid key:\n  " + "\n  ".join(problems))
    n_sub = sum(len(f["subfindings"]) for f in key["findings"])
    print(f"{a.eval}: {len(key['findings'])} findings, {n_sub} subfindings, {len(key['excluded'])} excluded")
    if not a.check:
        answer_key.dump(key, key_path)
        print(f"wrote {key_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
