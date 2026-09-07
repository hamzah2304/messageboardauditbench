#!/usr/bin/env python3
"""Build the contradiction rubric — contra_1.md … contra_6.md, plus contra_all.md.

The recall rubric asks what a report found. This asks what it got wrong, over the same
30 points, on a scale from 0 to -1.0. The two are deliberately separate: a report that
finds little and says nothing false should not be confused with one that finds a lot and
misleads, and averaging the two into one number hides exactly that difference.

Silence is not contradiction. A point the report never touches scores 0, and so does a
claim the human report simply does not speak to — only a real conflict of fact counts.

Same shape as build_rubrics.py: the scale stated once per sheet, then five points
carrying only what is specific to them. Run it after build_rubrics.py so the point
wording and the auditor's notes stay in step.
"""
import json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from paths import RUBRICS

OUT = RUBRICS

# Anchored by what a reader of the report would come away believing, not by counting
# errors. The gap between -0.3 and -0.7 is the one that matters: a wrong detail beside a
# right story, against a story the point says did not happen.
SCALE = [
 ("0.0", "Nothing in the report conflicts with this point. A point the report never "
         "raises scores 0 — silence is not contradiction."),
 ("-0.3", "A detail differs — a number, a name, a date — but a reader would still come "
          "away with this point intact."),
 ("-0.5", "The report muddles the mechanism or the attribution. A reader would have to "
          "reconcile it against the point, and might not."),
 ("-0.7", "The report asserts something incompatible with this point on a matter that "
          "changes what happened."),
 ("-0.9", "The report denies this point, or asserts its opposite, and does so with "
          "confidence."),
 ("-1.0", "The report builds on the opposite of this point, so a reader who follows it "
          "is led somewhere false."),
]

INSTRUCTION = (
 "You are checking a model-written incident report for statements that **contradict** "
 "points taken from a human-written one. The human report is given in full below and is "
 "the reference. Score each of the {n} points below from 0 to -1.0, one decimal place, "
 "using the scale. This is not a recall check: you are not asking whether the report "
 "found the point, only whether it says something the point rules out.")

RULES = (
 "Count only clear conflicts of fact. Do **not** count a point the report is silent on, "
 "a claim the human report does not address (unverifiable is not contradicted), a "
 "difference of emphasis or wording, or a hedged statement offered as a possibility. A "
 "report that says less is not thereby more accurate — it simply scores 0 here, and its "
 "thinness shows up in the recall rubric instead. Where the report contradicts a point in "
 "one place and states it correctly in another, score the contradiction: a reader meets "
 "both.")


def load_points():
    pts = []
    for i in range(1, 7):
        rub = json.loads((OUT / f"rubric_{i}.json").read_text())
        pts.append((rub["rubric_id"], rub["claims"]))
    return pts


def point_md(c, sheet_text):
    """Reuse the recall sheet's own wording for the point, so the two rubrics cannot drift."""
    out = [f"## {c['id']} — {c['section']}", ""]
    block = sheet_text.split(f"## {c['id']} — ")[1].split("\n## ")[0]
    for line in block.split("\n"):
        if line.startswith("**Point:**") or line.startswith("**In the human report:**"):
            out.append(line); out.append("")
    return "\n".join(out).rstrip()


def sheet(rid, claims, recall_md):
    ids = ", ".join(c["id"] for c in claims)
    head = [f"# Contradiction {rid} — {claims[0]['id']}–{claims[-1]['id']}", "",
            INSTRUCTION.format(n=len(claims)), "",
            "| Score | The report… |", "| ---: | --- |"]
    head += [f"| {v} | {t} |" for v, t in SCALE]
    head += ["", RULES, ""]
    body = "\n\n".join(point_md(c, recall_md) for c in claims)
    tail = ["", "---", "",
            "**Human incident report (reference):**", "", "{{HUMAN_REPORT}}", "",
            "**Model report under evaluation:**", "", "{{MODEL_REPORT}}", "",
            "---", "",
            'Return strict JSON only: {"rubric_id": "%s", "items": ['
            ' {"id": "<one of %s>", "score": <0 to -1.0, one decimal place>,'
            ' "quote": "<verbatim snippet from the model report that contradicts, or empty>",'
            ' "reason": "<one sentence naming the conflict, or why there is none>"}, ... ] }' % (rid, ids)]
    return "\n".join(head) + "\n" + body + "\n" + "\n".join(tail) + "\n"


def main():
    mds = []
    for n, (rid, claims) in enumerate(load_points(), start=1):
        recall_md = (OUT / f"rubric_{n}.md").read_text()
        md = sheet(rid, claims, recall_md)
        (OUT / f"contra_{n}.md").write_text(md)
        mds.append(md)
    (OUT / "contra_all.md").write_text("\n\n\n".join(mds))
    json.dump({"scale": SCALE, "instruction": INSTRUCTION, "rules": RULES},
              open(OUT / "contra_scale.json", "w"), indent=1, ensure_ascii=False)
    print(f"wrote {OUT} -> contra_1..6.md, contra_all.md, contra_scale.json")
    print(f"30 points, scale 0 to -1.0 ({len(SCALE)} anchors)")


if __name__ == "__main__":
    main()
