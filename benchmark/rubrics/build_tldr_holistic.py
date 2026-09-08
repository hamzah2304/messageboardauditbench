#!/usr/bin/env python3
"""Build the holistic TL;DR rubric — tldrh_1.md — one score for the whole summary.

The tldr rubric asks five separate questions and adds them up. That is a good measure of
coverage and a poor one of whether the summary reads as an account of what happened: a
TL;DR can name four points flatly and leave the reader holding nothing, and a checklist
cannot see the difference. This sheet asks the judge the question a human grader is
actually asked — would a reader of these 200 words alone come away with the story? — as a
single number from 0.0 to 1.0, so model judges and human graders can be put on one axis
and correlated.

Everything the judge reads comes from tldr_holistic.json: the intro, the scale anchors,
the guidance and the five points it names. The human grading UI reads the same file, so
the words in front of a person and the words in front of the judge are the same words and
cannot drift apart. Point wording, human-report quotes and notes still come from
claims_v2.json, as in build_tldr_rubric.py, for the same reason.
"""
import json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from paths import CLAIMS, RUBRICS

SPEC = pathlib.Path(__file__).parent / "tldr_holistic.json"


def point_bullet(c):
    """One point, compactly: the claim, the human report's words, then the note."""
    out = f"- {c['claim']}"
    if c.get("report_quote"):
        out += f" “{c['report_quote']}”"
    if c.get("note"):
        out += f" {c['note']}"
    return out


def main():
    spec = json.loads(SPEC.read_text())
    ids = spec["point_ids"]
    by = {c["id"]: c for c in json.loads((CLAIMS / "claims_v2.json").read_text())["claims"]}
    claims = [by[i] for i in ids]

    md = [f"# {spec['title']}", ""]
    for p in spec["intro"]:
        md += [p, ""]
    md += ["| Score | The TL;DR… |", "| ---: | --- |"]
    md += [f"| {v} | {t} |" for v, t in spec["scale"]]
    md += [""]
    for g in spec["guidance"]:
        md += [g, ""]
    md += [spec["points_intro"], ""]
    md += [point_bullet(c) for c in claims]
    md += ["", "---", "",
           "**Human incident report (answer key):**", "", "{{HUMAN_REPORT}}", "",
           "**Model report TL;DR (the whole of what you are scoring):**", "", "{{MODEL_REPORT}}", "",
           "---", "",
           'Return strict JSON only: {"rubric_id": "%s", "items": ['
           ' {"id": "%s", "score": <0.0 to 1.0, one decimal place>,'
           ' "quote": "<verbatim snippet from the TL;DR, or empty>",'
           ' "reason": "<two sentences: what the reader would come away with, and what is'
           ' missing or wrong>"} ] }' % (spec["rubric_id"], spec["rubric_id"])]

    (RUBRICS / "tldrh_1.md").write_text("\n".join(md) + "\n")
    (RUBRICS / "tldrh_1.json").write_text(json.dumps(
        {"rubric_id": spec["rubric_id"], "n_claims": len(claims), "claim_ids": ids, "claims": claims},
        indent=1, ensure_ascii=False))
    print(f"wrote {RUBRICS}/tldrh_1.md and tldrh_1.json — one holistic score over: {', '.join(ids)}")


if __name__ == "__main__":
    main()
