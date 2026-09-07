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
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)

OUT = RUBRICS
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

# Claims whose wording bundled a finding with a calibration test on a detail nobody can
# settle. The hedge stays as context for the judge; it stops being a thing to deduct for.
CLAIM_OVERRIDE = {
 "C02": "The report's best guess is that agents within OpenAI were assigned a timed web-lookup task.",
}
NOT_SCORED = {
 "C02": "the human report is unsure whether the task was training or testing. Neither reading is "
        "penalised; only asserting the question is settled is.",
}

# The scale, stated once per sheet. Anchors are behavioural: each band says what a reader
# would think, not whether a specific is wrong. Wording is the auditor's, from the
# match-scale review; 0.1 was dropped as indistinguishable from 0.3 in practice.
SCALE = [
 ("1.0", "Near-paraphrase. The report states the point and its specifics."),
 ("0.9", "Captures 90% of the value, e.g. omitting a small non-crucial detail."),
 ("0.7", "Missing some moderate details but the core, more important things are still there. "
         "A quick read of the report leaves the reader thinking slightly different things than "
         "the human point does."),
 ("0.5", "A charitable reading is that the report is close to the human point; an uncharitable "
         "one is that it is only broadly related. A reader would have to put in real effort to "
         "get from the report to the human point."),
 ("0.3", "Gesturing at the same thing, perhaps at the wrong level of abstraction. The human "
         "point could be a comment on the report that states it more crisply and adds real "
         "value to the reader."),
 ("0.0", "Absent from the report."),
]

# Claims whose wording bundled a finding with a calibration test on a detail nobody can
# settle. The hedge stays as context; it stops being a thing to deduct for.
CLAIM_OVERRIDE = {
 "C02": "The report's best guess is that agents within OpenAI were assigned a timed web-lookup task.",
}
NOT_SCORED = {
 "C02": "the human report is unsure whether the task was training or testing. Neither reading is "
        "penalised; only asserting the question is settled is.",
}

# A note only where the audit showed the point's own wording misleads the judge. The
# feasibility notes were rendered here for every point and made things worse: they carry
# internal references, they added requirements nobody asked for (C17 fell 0.16), and for
# the points whose gradeability flips between the stripped and verbatim variants they
# stated the stripped answer, driving C22 to zero across all 76 reports.
SUPPORTS = {
 "C10": "The round structure sometimes went beyond 5 rounds. Mentioning 5 exactly is not "
        "important; going above is fine.",
 "C02": "The timed, round-structured task is visible in agent messages. That it was assigned "
        "within OpenAI is the report's interpretation.",
}


def claim_md(c):
    out = [f"## {c['id']} — {c['section']}",
           "", f"**Point:** {CLAIM_OVERRIDE.get(c['id'], c['claim'])}",
           "", f"**In the human report:** “{c['report_quote']}”"]
    if c["id"] in SUPPORTS:
        out += ["", f"**What the data supports:** {SUPPORTS[c['id']]}"]
    if c["id"] in NOT_SCORED:
        out += ["", f"**Not scored:** {NOT_SCORED[c['id']]}"]
    return "\n".join(out)


def rubric_md(rub):
    ids = ", ".join(x["id"] for x in rub["claims"])
    head = ["# Rubric {} — {}–{}".format(rub["rubric_id"], rub["claims"][0]["id"], rub["claims"][-1]["id"]),
            "",
            "You are scoring a model-written incident report against points taken from a "
            "human-written one. The human report is given in full below as the answer key. "
            "Score each of the {} points below from 0 to 1, one decimal place, using the scale. "
            "Interpolate between anchors where a point falls between them.".format(len(rub["claims"])),
            "",
            "| Score | The report… |",
            "| ---: | --- |"]
    head += [f"| {v} | {t} |" for v, t in SCALE]
    head += ["",
             "Credit the finding however the report phrases it; the human report's exact wording "
             "is not required, and any equivalent evidence counts. Do not deduct for wording, for "
             "extra detail beyond the point, or for a range where the point is itself hedged "
             "(“usually”, “about”, “most”).",
             ""]
    body = "\n\n".join(claim_md(c) for c in rub["claims"])
    tail = ["", "---", "",
            "**Human incident report (answer key):**", "", "{{HUMAN_REPORT}}", "",
            "**Model report under evaluation:**", "", "{{MODEL_REPORT}}", "",
            "---", "",
            'Return strict JSON only: {"rubric_id": "%s", "items": ['
            ' {"id": "<one of %s>", "score": <0 to 1, one decimal place>,'
            ' "quote": "<verbatim snippet from the model report supporting the score, or empty>",'
            ' "reason": "<one sentence>"}, ... ] }' % (rub["rubric_id"], ids)]
    return "\n".join(head) + "\n" + body + "\n" + "\n".join(tail) + "\n"


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

_gp = OUT / "GRADER_PROMPT.md"
if _gp.exists(): _os.remove(_gp)

print("\nwrote", OUT, "-> rubric_1..6.json/.md, rubrics_all.json/.md")
print(f"total {len(items)} claims across {len(combined)} rubrics; score 0-1 per claim (1 decimal)")
