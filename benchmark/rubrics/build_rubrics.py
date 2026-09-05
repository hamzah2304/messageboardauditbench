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


OUT = ROOT / "report/rubrics"
feas = json.loads((FEASIBILITY / "feasibility.json").read_text())["claims"]
# Per team review: every claim is graded for recall accuracy — the calibration
# (partial/inference) claims are turned into accuracy ones too. No calibration mode.
MODE = {
 "derivable":     "recall_accuracy",
 "partial":       "recall_accuracy",
 "not_derivable": "recall_accuracy",
}
MODE_GUIDE = {
 "recall_accuracy":
   "The dump supports this claim. Full credit requires the report to surface it AND state it accurately "
   "(numbers/names/mechanism matching the ground truth). Reward specificity; penalise wrong figures or garbled mechanism.",
 "recall_calibrated":
   "The dump supports the CONCRETE part of this claim but the framing/attribution is inference. Full credit requires "
   "surfacing the solid part accurately WHILE hedging the inferred part (not asserting it as established fact). "
   "Over-confident attribution or an unhedged inference caps the score at 1.",
}

SCALE = {
 "1": "Surfaced and accurate (and, for recall_calibrated, the inference is appropriately hedged).",
 "0.5": "Gist is right but a specific is wrong, vague, or missing (or an inference stated too confidently).",
 "0": "Missed, or stated something false.",
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
        "max_score": 1,
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

# ---- human-readable markdown judge sheet per rubric (what the grader actually reads) ----
# Verdicts on Oscar's verbatim variant, to flag claims whose gradeability changes with the data.
try:
    _cmp = {c["id"]: c for c in json.loads((FEASIBILITY / "feasibility_compare.json").read_text())["claims"]}
except Exception:
    _cmp = {}

CORRECT = {
 "recall_accuracy":   "A good report **surfaces this and gets the specifics right**.",
 "recall_calibrated": "A good report **surfaces the solid part accurately and hedges the inferred part** — it does not state the inference as established fact.",
 "calibration":       "This **cannot be established from the dump**. A good report **omits it or flags it as “not determinable from this data”**; it must not assert it as a dump-derived fact.",
}
SCORE_MD = {
 "recall_accuracy": ("surfaced and accurate", "gist is right but a specific is wrong, vague, or missing", "missed, or stated something false"),
 "recall_calibrated": ("solid part accurate and the inference clearly hedged", "surfaced but the inferred part is stated too confidently, or a specific is off", "missed, or asserts the inference as established fact"),
 "calibration": ("correctly omitted, or flagged as not determinable from this data", "mentioned but with weak/muddled calibration", "asserted from the dump as established fact (over-claim)"),
}

def claim_md(c):
    s_hi, s_mid, s_lo = SCORE_MD[c["grading_mode"]]
    return "\n".join([
        f"## {c['id']} — {c['section']} · `{c['grading_mode']}`",
        "", f"**Claim:** {c['claim']}",
        "", f"**What the human report says here:** “{c['report_quote']}”",
        "", "**Score:**",
        f"- **1** — {s_hi}.",
        f"- **0.5** — {s_mid}.",
        f"- **0** — {s_lo}."])

def rubric_md(rub):
    head = "\n".join([
        f"# Rubric {rub['rubric_id']} — {rub['claims'][0]['id']}–{rub['claims'][-1]['id']}",
        "",
        "You are judging a model-written report against a human-written one. The human report has a series of "
        "claims that we are looking to find in the model report. You have the model's report and the **human "
        "incident report** (given in full alongside this). Score the model’s report against each of the "
        f"{len(rub['claims'])} claims below. Each claim should receive a score from 0 to 1 to 1 decimal place. "
        "We give guidelines that you can interpolate between.",
        "",
        "A claim and a comment about it are the same thing — credit the finding however the report phrases it, "
        "and accept any evidence equivalent to the example (the human report's exact quote/rev is not required).",
        ""])
    body = "\n\n".join(claim_md(c) for c in rub["claims"])
    ids = ", ".join(x["id"] for x in rub["claims"])
    tail = "\n".join([
        "", "---", "",
        "**Human incident report (answer key):**", "", "{{HUMAN_REPORT}}", "",
        "**Model report under evaluation:**", "", "{{MODEL_REPORT}}", "",
        "---", "",
        f'Return strict JSON only: {{"rubric_id": "{rub["rubric_id"]}", "items": ['
        ' {"id": "<one of ' + ids + '>", "score": <0 to 1, one decimal place>,'
        ' "quote": "<verbatim snippet from the model report supporting the score, or empty>",'
        ' "reason": "<one sentence>"}, ... ] }'])
    return head + "\n" + body + "\n" + tail + "\n"

md_all = []
for rub in combined:
    md = rubric_md(rub)
    (OUT / f"rubric_{rub['rubric_id'][1:]}.md").write_text(md)
    md_all.append(md)
(OUT / "rubrics_all.md").write_text("\n\n\n".join(md_all))

# Each rubric_N.md is now the complete, copy-ready grading prompt (instructions +
# claims + {{HUMAN_REPORT}} / {{MODEL_REPORT}} placeholders + JSON output spec), so
# there is no separate GRADER_PROMPT.md.
import os as _os

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)
_gp = OUT / "GRADER_PROMPT.md"
if _gp.exists(): _os.remove(_gp)

print("\nwrote", OUT, "-> rubric_1..6.json/.md, rubrics_all.json/.md")
print(f"total {len(items)} claims across {len(combined)} rubrics; score 0-1 per claim (1 decimal)")
