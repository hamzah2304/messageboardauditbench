#!/usr/bin/env python3
"""Apply the review decisions for an answer key (benchmarks/<eval>/answer-key-review.json) to its QA'd key.

    python3 scripts/apply_answer_key_review.py german-wiki [--check]
    python3 scripts/apply_answer_key_review.py german-wiki --overlap-only   # key reviewed before the overlap step
    python3 scripts/apply_answer_key_review.py transluce --source answer-key-qa.json   # QA'd key kept apart

The decisions file holds the default for every item ("accept_qa"), the items rewritten by hand
("overrides": id -> fields to set) and exact edits to finding details ("detail_edits": id -> [[old, new], ...]), and optionally significance levels
to set ("significance": id -> major/minor).
Accepting QA means: a narrowed proposal replaces the headline or subfinding claim, a REMOVE moves the
subfinding to `excluded`, make_harder is appended to the judge notes, and a drafted headline is marked
approved. The key records the decisions file in `review`; a key that already has one is not applied twice.

The overlap check's edits (key["overlap"], from scripts/run_answer_key_overlap.py) are accepted too,
after QA, except the overlaps the decisions file lists in "overlap_rejected" (["O2", ...]). An edit
that rewrites a field a hand override or detail edit also sets is refused: reject that overlap or put
the wording in the override. --overlap-only applies just the overlap edits, to a key whose QA review
was applied before the overlap step ran; the overlap is marked applied either way.
"""
import datetime
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# In the overlap sandbox this file sits next to a copy of answer_key.py (scripts/check_overlap_edits.py).
_ak = ROOT / "slopvestigator_bench/answer_key.py"
if not _ak.exists():
    _ak = Path(__file__).with_name("answer_key.py")
_spec = importlib.util.spec_from_file_location("answer_key", _ak)
answer_key = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_key)


def apply(key: dict, review: dict, review_path: str, overlap: bool = True) -> dict:
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
            elif (sqa.get("proposed_wording") or "").startswith("REMOVE"):  # some agents add "(merge ...)"
                why = f"merged into {sqa['duplicate_of']}: " if sqa.get("duplicate_of") else ""
                excluded.append({"id": s["id"], "kind": "subfinding", "claim": s["claim"], "reason": why + sqa.get("reason", "")})
                continue
            elif sqa.get("proposed_wording"):
                s["claim"] = sqa["proposed_wording"]
            subs.append(s)
        f["subfindings"] = subs
        findings.append(f)
    key["findings"], key["excluded"] = findings, excluded
    levels = review.get("significance", {})  # id -> level, for keys graded by their own weights (Transluce)
    for x in [x for f in findings for x in [f, *f["subfindings"]] if x["id"] in levels]:
        x["significance"] = levels[x["id"]]
    if overlap and key.get("overlap"):
        protected = {(i, k) for i, o in overrides.items() for k in o if k != "why"}
        protected |= {(i, "detail") for i in edits if not i.startswith("_")}
        apply_overlap(key, review.get("overlap_rejected", []), protected, review.get("date", ""))
    key["review"] = {"decisions": review_path, "date": review.get("date", ""), "decided_by": review.get("decided_by", "")}
    return key


def apply_overlap(key: dict, rejected=(), protected=frozenset(), date: str = "") -> dict:
    """Apply the accepted overlap edits in place: rewrites, then moves, folds and removals."""
    ov = key["overlap"]
    if ov.get("applied"):
        raise SystemExit(f"overlap edits already applied ({ov['applied']})")
    unknown = set(rejected) - {o["id"] for o in ov["overlaps"]}
    if unknown:
        raise SystemExit(f"overlap_rejected names unknown overlaps: {sorted(unknown)}")
    accepted = [o for o in ov["overlaps"] if o["id"] not in set(rejected)]
    problems = answer_key.overlap_problems({"overlaps": accepted}, key)
    if problems:
        raise SystemExit("overlap edits do not fit the key:\n  " + "\n  ".join(problems))
    edits = [(o, e) for o in accepted for e in o["edits"]]
    structural = {}
    for o, e in edits:
        if e["action"] == "rewrite":
            if (e["id"], e["field"]) in protected:
                raise SystemExit(f"{o['id']} rewrites {e['id']}.{e['field']}, which a hand override sets; "
                                 "add it to overlap_rejected or put the wording in the override")
            continue
        if e["id"] in structural:
            raise SystemExit(f"{e['id']} has two overlap edits ({structural[e['id']]} and {o['id']} {e['action']})")
        structural[e["id"]] = f"{o['id']} {e['action']}"
    gone = {e["id"] for _, e in edits if e["action"] in ("remove", "fold")}
    for o, e in edits:
        if e["action"] == "rewrite" and e["id"] in gone:
            raise SystemExit(f"{o['id']} rewrites {e['id']}, which another edit removes or folds")
        if e["action"] in ("move", "fold") and e["to"] in gone:
            raise SystemExit(f"{o['id']} sends {e['id']} to {e['to']}, which another edit removes or folds")

    fmap = {f["id"]: f for f in key["findings"]}
    parent = {s["id"]: f for f in key["findings"] for s in f["subfindings"]}
    item = lambda i: fmap.get(i) or next(s for s in parent[i]["subfindings"] if s["id"] == i)  # noqa: E731
    why = lambda o: f"overlap {o['id']}: {o.get('reason', '')}".strip()  # noqa: E731
    excluded = key.setdefault("excluded", [])
    for o, e in edits:
        if e["action"] == "rewrite":
            item(e["id"])[e["field"]] = e["text"]
    for o, e in edits:
        if e["action"] == "move":
            s = item(e["id"])
            parent[e["id"]]["subfindings"].remove(s)
            s.setdefault("fields", {})["moved_from"] = parent[e["id"]]["id"]
            fmap[e["to"]]["subfindings"].append(s)
            parent[e["id"]] = fmap[e["to"]]
    for o, e in edits:
        if e["action"] == "fold":
            f = fmap[e["id"]]
            fmap[e["to"]]["subfindings"].append({
                "id": f["id"], "claim": e["claim"], "significance": f.get("significance"),
                "judge_notes": e.get("judge_notes", ""), "evidence": f.get("evidence", []),
                "fields": {"folded_from": f["claim"]}, "qa": None})
            for s in f["subfindings"]:
                excluded.append({"id": s["id"], "kind": "subfinding", "claim": s["claim"],
                                 "reason": f"{f['id']} folded into {e['to']}; {why(o)}"})
            key["findings"].remove(f)
    for o, e in edits:
        if e["action"] == "remove":
            if e["id"] in fmap:
                f = fmap[e["id"]]
                excluded.append({"id": f["id"], "kind": "finding", "claim": f["claim"], "reason": why(o)})
                excluded += [{"id": s["id"], "kind": "subfinding", "claim": s["claim"],
                              "reason": f"its finding {f['id']} was removed; {why(o)}"} for s in f["subfindings"]]
                key["findings"].remove(f)
            else:
                s = item(e["id"])
                parent[e["id"]]["subfindings"].remove(s)
                excluded.append({"id": s["id"], "kind": "subfinding", "claim": s["claim"], "reason": why(o)})
    ov["applied"] = date or datetime.date.today().isoformat()
    if rejected:
        ov["rejected"] = sorted(rejected)
    return key


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("eval")
    ap.add_argument("--check", action="store_true", help="validate and print a summary without writing")
    ap.add_argument("--source", default="answer-key.json",
                    help="the QA'd key in benchmarks/<eval>/ to apply the decisions to (written to answer-key.json)")
    ap.add_argument("--overlap-only", action="store_true",
                    help="apply only the overlap edits, to a key whose QA review is already applied")
    a = ap.parse_args()
    key_path = ROOT / "benchmarks" / a.eval / "answer-key.json"
    review_rel = f"benchmarks/{a.eval}/answer-key-review.json"
    review = json.loads((ROOT / review_rel).read_text())
    key = answer_key.load(key_path.with_name(a.source))
    if a.overlap_only:
        if not key.get("review") or not key.get("overlap"):
            sys.exit("--overlap-only needs a key with its review applied and an overlap result")
        key = apply_overlap(key, review.get("overlap_rejected", []), date=review.get("overlap_date", ""))
    else:
        key = apply(key, review, review_rel)
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
