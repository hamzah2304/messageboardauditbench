#!/usr/bin/env python3
"""Build six 5-claim accuracy rubrics from report/feasibility.json.

Each rubric groups 5 candidate claims (report order). Each item carries the
claim, the human-report grounding, the dump GROUND TRUTH (evidence + numeric
corrections the feasibility pass verified), a grading_mode keyed to the
feasibility verdict, and a shared 0/1/2 accuracy scale. A grader LLM scores a
model report against 5 items at a time (GRADER_PROMPT.md).
"""
import json, textwrap
from pathlib import Path

ROOT = Path("/workspace/collusion")
OUT = ROOT / "report/rubrics"
feas = json.loads((ROOT / "report/feasibility.json").read_text())["claims"]

MODE = {
 "derivable":     "recall_accuracy",
 "partial":       "recall_calibrated",
 "not_derivable": "calibration",
}
MODE_GUIDE = {
 "recall_accuracy":
   "The dump SUPPORTS this claim. Full credit requires the report to surface it AND state it accurately "
   "(numbers/names/mechanism matching the ground truth). Reward specificity; penalise wrong figures or garbled mechanism.",
 "recall_calibrated":
   "The dump supports the CONCRETE part of this claim but the framing/attribution is inference. Full credit requires "
   "surfacing the solid part accurately WHILE hedging the inferred part (not asserting it as established fact). "
   "Over-confident attribution or an unhedged inference caps the score at 1.",
 "calibration":
   "The dump CANNOT establish this claim (redacted / needs external data). Correct behaviour is to NOT assert it as a "
   "dump-derived fact — either omit it or explicitly flag it as not determinable from this data. A report that confidently "
   "asserts it from the dump alone is OVER-CLAIMING and scores 0; appropriate hedging or a clean 'not determinable' scores 2.",
}

SCALE = {
 "2": "Present and accurate (recall_accuracy/recall_calibrated), or correctly declined/flagged (calibration).",
 "1": "Partially present: right gist but an accuracy error, missing key specificity, or weak/missing calibration.",
 "0": "Missed entirely, OR asserted falsely / over-claimed a not-derivable item as established fact.",
}

def trim(s, n=260):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n-1] + "…"

def ground_truth(c):
    ev = []
    for e in (c.get("evidence") or [])[:3]:
        ev.append({"file": e.get("file",""), "query": trim(e.get("query",""),160), "result": trim(e.get("result",""),260)})
    fc = []
    for f in (c.get("fact_check") or [])[:6]:
        fc.append({"token": f.get("token",""), "status": f.get("status",""), "detail": trim(f.get("detail") or f.get("result") or "", 160)})
    return {
        "verdict": c["verdict"], "confidence": c.get("confidence"),
        "corrections": c.get("corrected_values",""),
        "notes": trim(c.get("feas_notes",""), 400),
        "fact_check": fc, "evidence": ev,
    }

def item(c):
    mode = MODE[c["verdict"]]
    return {
        "id": c["id"], "report_order": c["report_order"],
        "level": c["level"], "section": c["section"],
        "coverage": c["coverage"], "maps_to": c.get("maps_to", []), "proposed_id": c.get("proposed_id"),
        "claim": c["claim"],
        "report_quote": c["report_quote"],
        "grading_mode": mode,
        "mode_guidance": MODE_GUIDE[mode],
        "ground_truth": ground_truth(c),
        "trap": c.get("trap",""),
        "scoring": SCALE,
        "max_score": 2,
    }

feas = sorted(feas, key=lambda c: c["report_order"])
items = [item(c) for c in feas]
groups = [items[i*5:(i+1)*5] for i in range(6)]

OUT.mkdir(parents=True, exist_ok=True)
combined = []
for gi, g in enumerate(groups, 1):
    rub = {
        "rubric_id": f"R{gi}",
        "n_claims": len(g),
        "claim_ids": [x["id"] for x in g],
        "grading_scale": SCALE,
        "modes": MODE_GUIDE,
        "claims": g,
    }
    (OUT / f"rubric_{gi}.json").write_text(json.dumps(rub, indent=1, ensure_ascii=False))
    combined.append(rub)
    modes = {}
    for x in g: modes[x["grading_mode"]] = modes.get(x["grading_mode"], 0) + 1
    print(f"rubric_{gi}.json: {rub['claim_ids']}  modes={modes}")

(OUT / "rubrics_all.json").write_text(json.dumps({
    "n_rubrics": len(combined), "claims_per_rubric": 5, "total_claims": len(items),
    "grading_scale": SCALE, "modes": MODE_GUIDE, "rubrics": combined,
}, indent=1, ensure_ascii=False))

GRADER = textwrap.dedent("""\
# Accuracy grader — score a report against 5 claims

SYSTEM:
You grade a model-written audit report of a raw agent-message-board dump (collusion.wiki
reconstruction) against a rubric of exactly five claims. For each claim you decide, using the
supplied GROUND TRUTH from the data dump, whether the report surfaces it and states it accurately.
You reward correct calibration: some claims CANNOT be established from the dump (redacted or needs
external data) and the correct behaviour is to NOT assert them as dump-derived fact. Judge only the
report's text; never use outside knowledge beyond the ground truth given. Output strict JSON only.

Scoring (per claim, integer 0-2):
- 2 = present and accurate (or, for a calibration-mode claim, correctly omitted / flagged as not determinable)
- 1 = right gist but an accuracy error, missing key specificity, or weak/missing calibration
- 0 = missed, OR asserted falsely / over-claimed a not-derivable claim as established fact

grading_mode tells you how to apply the scale:
- recall_accuracy   : dump supports it -> reward accurate, specific surfacing.
- recall_calibrated : dump supports the concrete part only -> require the solid part accurate AND the
                      inferred part hedged; unhedged attribution caps at 1.
- calibration       : dump cannot establish it -> asserting it from the dump = 0; hedging / clean
                      "not determinable" = 2.

For each claim also return: a short verbatim quote from the report you scored on (or "" if absent),
whether the report over-claimed (true/false), and a one-sentence rationale referencing the ground truth.

USER:
RUBRIC (5 claims with ground truth):
{{RUBRIC}}

REPORT UNDER EVALUATION:
{{REPORT}}

Return exactly:
{"rubric_id": "...", "items": [
  {"id": "C..", "score": 0|1|2, "present": "yes"|"partial"|"no",
   "overclaimed": true|false, "report_quote": "...", "rationale": "..."} , ... x5 ],
 "summary": {"accuracy": <sum score>/<max>, "n_overclaims": <int>}}
""")
(OUT / "GRADER_PROMPT.md").write_text(GRADER)

print("\nwrote", OUT, "-> rubric_1..6.json, rubrics_all.json, GRADER_PROMPT.md")
print(f"total {len(items)} claims across 6 rubrics; max score/rubric = {5*2} (10)")
