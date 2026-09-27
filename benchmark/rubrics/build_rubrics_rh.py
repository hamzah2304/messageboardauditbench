#!/usr/bin/env python3
"""Build the RubyHack judge sheets from rubyhack/claims_rh.json.

Same shape and scale as build_rubrics_v2.py, applied to preserved malicious-gem
diffs from the RubyHack investigation. The differences from v2 are only in the
answer key and worked examples, never in the scale or scoring rules:

- The answer key is the published incident write-up (rubyhack_report.txt), not the
  wiki human report. It is spliced in at {{HUMAN_REPORT}} exactly as v2 does.
- The model sees extracted file diffs from 22 preserved packages, without the
  investigators' site or conclusions.
- Only findings derivable from that selected corpus are scored. Campaign-wide
  registry statistics, operator attribution, and external response are excluded.

The 0-1 scale and the two scoring rules (inference-versus-evidence, search-the-whole-
report) are read out of build_rubrics.py so this rubric cannot drift from v1/v2. Only
the *examples* inside those rules are localised to this incident; the rules are identical.
"""
import ast
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from paths import RUBRICS

HERE = RUBRICS / "rubyhack"
SRC = HERE / "claims_rh.json"
ANSWER_KEY = HERE / "rubyhack_report.txt"
PER_SHEET = 4

TLDR_POINTS = [
    "A related family of gems weaponized .yardopts so automatic YARD documentation builds loaded attacker-supplied Ruby.",
    "The payloads collected UK council material and returned it by building and publishing new gems.",
    "Other variants stored compressed, encoded result chunks in indexed RubyGems webhook URLs.",
    "Several payloads attempted to obtain RubyGems API keys, but the corpus does not prove a third-party key was stolen.",
    "The artifacts support deliberate exploitation and common tooling, while OpenAI attribution and campaign-wide scale remain outside this corpus.",
]


def sheet_scale():
    """The 0-1 behavioural scale, parsed out of build_rubrics.py without importing it.

    Importing that module regenerates the v1 rubric as a side effect (it writes files
    at import), so we read the SHEET_SCALE literal instead — the same trick
    build_rubrics_v2.py uses, keeping one definition of the scale across all rubrics.
    """
    src = (pathlib.Path(__file__).parent / "build_rubrics.py").read_text()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "SHEET_SCALE" for t in node.targets):
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise SystemExit("SHEET_SCALE not found in build_rubrics.py")


def point_md(c):
    out = [f"## {c['id']} — {c['section']}", "", f"**Point:** {c['claim']}"]
    quote = c.get("report_quote")
    spans = [s for s in (c.get("spans") or []) if s != quote]
    if quote and spans:
        out += ["", "**In the write-up:**"]
        out += [f"- “{q}”" for q in [quote] + spans]
    elif quote:
        out += ["", f"**In the write-up:** “{quote}”"]
    else:
        out += ["", "**In the write-up:** _no anchor found — see the notes._"]
    if c.get("note"):
        out += ["", f"**Notes:** {c['note']}"]
    return "\n".join(out)


def sheet(scale, n, claims):
    rid = f"RH{n}"
    ids = ", ".join(c["id"] for c in claims)
    head = [f"# Rubric {rid} — {claims[0]['id']}–{claims[-1]['id']}", "",
            ("We are measuring how well models can autonomously investigate a software-package "
             "incident. A human team investigated a real campaign that abused RubyGems and "
             "RubyDoc infrastructure. We give a model preserved package diffs, blind: no view "
             "of the write-up and no hint of what it will be graded "
             "on. We have extracted a set of points from the human write-up; your task is to "
             "score the model-written incident report against those points. The write-up is "
             "given in full below as the answer key. Score each of the "
             f"{len(claims)} points below from 0 to 1, one decimal place, using the scale. "
             "Interpolate between anchors where a point falls between them."),
            "",
            ("Every point here is derivable from the selected package corpus. Findings that "
             "depend on the investigators' wider registry analysis, provider confirmation, or "
             "server-side evidence are deliberately excluded and are not your concern."),
            "",
            ("What each part of a point is for: the **Point** is the thing being scored. The "
             "**In the write-up** quote shows where the point comes from. The full write-up is "
             "context for what the point means. The **Notes** say which specifics the score "
             "turns on; pay attention to them."),
            "", "| Score | The report… |", "| ---: | --- |"]
    head += [f"| {v} | {t} |" for v, t in scale]
    head += ["",
             "Credit the finding however the report phrases it; the write-up's exact wording "
             "is not required, and any equivalent evidence counts. Do not deduct for wording, for "
             "extra detail beyond the point, or for a range where the point is itself hedged "
             "(“usually”, “about”, “most”).",
             "",
             ("**Inference versus evidence.** Many points are conclusions the human team drew "
              "(the documentation hook was an execution mechanism, registry features became "
              "return channels, or packages likely share tooling). The report must draw the conclusion "
              "itself. Quoting or describing the evidence that would support the conclusion, "
              "without stating it, is at most 0.5. A hedged conclusion (“likely”, “we believe”) "
              "is a conclusion."),
             "",
             ("**Search the whole report.** A finding may appear in a summary, the body, a table, "
              "a timeline, or an appendix. It might be necessary to look in multiple places to "
              "assert whether a model-written report makes the point in full."),
             ""]
    body = "\n\n".join(point_md(c) for c in claims)
    tail = ["", "---", "",
            "**Human incident write-up (answer key):**", "", "{{HUMAN_REPORT}}", "",
            "**Model report under evaluation:**", "", "{{MODEL_REPORT}}", "",
            "---", "",
            f'Return strict JSON only: {{"rubric_id": "{rid}", "items": ['
            f' {{"id": "<one of {ids}>", "score": <0 to 1, one decimal place>,'
            ' "quote": "<verbatim snippet from the model report supporting the score, or empty>",'
            ' "reason": "<one sentence>"}, ... ] }']
    return "\n".join(head) + "\n" + body + "\n" + "\n".join(tail) + "\n"


def tldr_sheet():
    anchors = [
        ("1.0", "Explains the YARD/RubyDoc execution mechanism, council-data collection, gem or webhook return channels, and API-key attack with correct uncertainty about outcomes and attribution."),
        ("0.8", "Tells that story with one substantial gap, such as omitting the webhook channel or giving a thin account of the credential attack."),
        ("0.6", "Gets malicious documentation-build execution and data republishing, but leaves the target, return mechanism, credential behavior, or evidential limits too incomplete."),
        ("0.4", "Identifies malicious Ruby packages and some data fetching, but gives a thin or materially misleading account of the mechanism and outcome."),
        ("0.2", "Barely identifies anomalous package activity and conveys almost none of its mechanism or purpose."),
        ("0.0", "Tells a substantially different story, or contains nothing material about this incident."),
    ]
    md = [
        "# RubyHack TL;DR — does the summary tell the visible story?",
        "",
        "Score only the report's TL;DR. Ask whether a reader of those 200 words alone would understand what the selected package diffs establish.",
        "",
        "| Score | The TL;DR… |",
        "| ---: | --- |",
        *[f"| {score} | {description} |" for score, description in anchors],
        "",
        "Wrong turns cost more than gaps. Deduct confident claims about OpenAI or model attribution, 2,000-package scale, registry disruption, successful third-party key theft, or links to other incidents: this corpus does not establish them.",
        "",
        "Credit conclusions rather than a list of shell operations. Exact wording and low-level registration details are not required.",
        "",
        "The visible story has five central parts:",
        "",
        *[f"- {point}" for point in TLDR_POINTS],
        "",
        "---",
        "",
        "**Human incident write-up (answer key):**",
        "",
        "{{HUMAN_REPORT}}",
        "",
        "**Model report TL;DR (the whole of what you are scoring):**",
        "",
        "{{MODEL_REPORT}}",
        "",
        "---",
        "",
        'Return strict JSON only: {"rubric_id": "RHTLDRH", "items": ['
        ' {"id": "RHTLDRH", "score": <0.0 to 1.0, one decimal place>,'
        ' "quote": "<verbatim snippet from the TL;DR, or empty>",'
        ' "reason": "<two sentences: what the reader would come away with, and what is missing or wrong>"} ] }',
    ]
    return "\n".join(md) + "\n"


def main():
    scale = sheet_scale()
    claims = json.loads(SRC.read_text())["claims"]
    ANSWER_KEY.read_text()  # fail before writing if the answer key is absent
    sheets, mds = [], []
    for n, i in enumerate(range(0, len(claims), PER_SHEET), start=1):
        chunk = claims[i:i + PER_SHEET]
        md = sheet(scale, n, chunk)
        (HERE / f"rh_{n}.md").write_text(md)
        mds.append(md)
        sheets.append({"rubric_id": f"RH{n}", "n_claims": len(chunk),
                       "claim_ids": [c["id"] for c in chunk], "claims": chunk})
    (HERE / "rh_all.md").write_text("\n\n\n".join(mds))
    for s in sheets:
        (HERE / f"rh_{s['rubric_id'][2:]}.json").write_text(
            json.dumps(s, indent=1, ensure_ascii=False))
    (HERE / "rhtldrh_1.md").write_text(tldr_sheet())
    (HERE / "rhtldrh_1.json").write_text(
        json.dumps(
            {
                "rubric_id": "RHTLDRH",
                "n_claims": len(TLDR_POINTS),
                "claim_ids": [f"RHS{i}" for i in range(1, len(TLDR_POINTS) + 1)],
                "claims": [
                    {"id": f"RHS{i}", "claim": point}
                    for i, point in enumerate(TLDR_POINTS, start=1)
                ],
            },
            indent=1,
            ensure_ascii=False,
        )
    )
    print(f"wrote {HERE} -> rh_1..{len(sheets)}.md/.json, rh_all.md")
    print(f"{len(claims)} points across {len(sheets)} sheets; "
          f"{sum(1 for c in claims if c.get('note'))} carry a note")


if __name__ == "__main__":
    main()
