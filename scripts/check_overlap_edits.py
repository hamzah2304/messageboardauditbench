#!/usr/bin/env python3
"""Check an overlap check's edits against the key, as the overlap agent's self-check.

    python3 check_overlap_edits.py [KEY] [OVERLAP]     # defaults: /work/answer-key.json /work/overlap.json

Copied into the overlap sandbox's /work by scripts/run_answer_key_overlap.py, next to answer_key.py and
apply_answer_key_review.py. It applies the edits to a copy of the key exactly as the review step will,
prints any problem that would stop them being applied, then shows each edited item before and after,
and flags judge notes that name items of other findings by id (the judge never sees those items).
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("apply_answer_key_review", HERE / "apply_answer_key_review.py")
review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review)


def items(key):
    out = {}
    for f in key["findings"]:
        out[f["id"]] = (f["id"], f)
        out.update({s["id"]: (f["id"], s) for s in f["subfindings"]})
    return out


def show(x):
    return "\n".join(f"    {k}: {x.get(k)}" for k in ("claim", "detail", "judge_notes") if x.get(k))


def main():
    key_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/work/answer-key.json")
    ov_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/work/overlap.json")
    key = json.loads(key_path.read_text())
    ov = json.loads(ov_path.read_text())
    key.pop("review", None)
    key["overlap"] = {"applied": "", "overlaps": [{"id": f"O{i}", **o} for i, o in enumerate(ov.get("overlaps", []), 1)],
                      "kept_separate": ov.get("kept_separate", [])}
    problems = review.answer_key.overlap_problems(key["overlap"], key)
    if problems:
        print("PROBLEMS (fix these):\n  " + "\n  ".join(problems))
        return 1
    before = items(key)
    after_key = copy.deepcopy(key)
    try:
        review.apply_overlap(after_key)
    except SystemExit as e:
        print(f"PROBLEM (fix this): {e}")
        return 1
    after = items(after_key)
    ids = sorted({e["id"] for o in ov["overlaps"] for e in o["edits"]} | {e.get("to") for o in ov["overlaps"]
                 for e in o["edits"] if e.get("to")})
    all_ids = set(before)
    for i in ids:
        print(f"== {i}")
        print("  before:\n" + show(before[i][1]))
        print("  after:\n" + (show(after[i][1]) if i in after else "    (removed or folded)"))
        if i in after and after[i][0] != before[i][0]:
            print(f"  now under {after[i][0]}")
    print()
    for i, (fid, x) in after.items():
        named = {m for m in re.findall(r"\b[A-Z]{1,2}\d+(?:\.\d+)?\b", x.get("judge_notes") or "")
                 if m in all_ids and after.get(m, before.get(m))[0] != fid}
        if named:
            print(f"WARNING {i}: judge notes name {sorted(named)} from other findings; the judge never sees "
                  "them, so describe the excluded fact in words")
    listed = [set(e.get("items", [])) for e in ov.get("overlaps", []) + ov.get("kept_separate", [])]
    covered = set().union(*listed) if listed else set()
    for f in key["findings"]:
        if not ({f["id"]} | {s["id"] for s in f["subfindings"]}) & covered:
            print(f"WARNING {f['id']}: neither it nor its subfindings appear in overlaps or kept_separate; "
                  "list the findings closest to it")
        subs_f = [s["id"] for s in f["subfindings"]]
        for i, a in enumerate(subs_f):
            for b in subs_f[i + 1:]:
                if not any({a, b} <= x for x in listed):
                    print(f"WARNING {a} and {b} (same finding): in neither overlaps nor kept_separate")
    print(f"ok: {len(ov['overlaps'])} overlaps, {len(after_key['findings'])} findings, "
          f"{sum(len(f['subfindings']) for f in after_key['findings'])} subfindings after the edits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
