#!/usr/bin/env python3
"""Draft one headline finding per German wiki section from the human report, for Oscar to approve.

    python3 scripts/draft_answer_key_headlines.py [--model MODEL] [--out FILE]

The 38 points of benchmarks/german-wiki/claims/claims_v2.json fall into 12 sections; each section becomes one
finding whose subfindings are its points. This asks a model, through the Claude Code CLI on the
subscription (no API key), for each section's headline claim and a two-to-three sentence detail,
written from the human report (benchmarks/german-wiki/human_report.txt) and following the finding description
module. Writes benchmarks/german-wiki/answer-key-headline-drafts.json with the prompt's hash and the
model, so the drafts can be traced. The headlines are drafts: the review page asks for approval of each.
"""
import argparse
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configured_model(helper: str) -> str:
    """The model configs/standard.toml [helpers] names for this script (its bare id); no fallback."""
    import tomllib

    entry = tomllib.loads((ROOT / "configs/standard.toml").read_text())["helpers"][helper]
    return entry["model"].split("/", 1)[1]
CLAIMS = ROOT / "benchmarks/german-wiki/claims/claims_v2.json"
REPORT = ROOT / "benchmarks/german-wiki/human_report.txt"
MODULES = ROOT / "benchmarks/qa/modules"
OUT = ROOT / "benchmarks/german-wiki/answer-key-headline-drafts.json"

PROMPT = """You are drafting headline findings for an answer key. Below are the human investigators' report on an
incident, a description of what a good finding is, and the report's points grouped into {n} sections.
Each section will become one headline finding, and its points will be the finding's subfindings.

For each section write:
- "claim": one sentence, the headline finding. It says what happened: who did what, and the result or
  the conclusion, in the report's own terms. It covers the section's points without listing them, and
  claims no more than they do: if a point is hedged ("likely"), the headline keeps the hedge. No
  numbers, names or dates that the points do not contain.
- "detail": two or three sentences that explain the finding for a grader who has not read the report:
  the mechanism, the key evidence the report gives, and why it matters.

{finding_description}

{addendum}

## The sections and their points

{sections}

## The human report

{report}

## Output

Reply with only a JSON object, no prose and no code fence:
{{"sections": [{{"section": "<section name exactly as given>", "claim": "...", "detail": "..."}}, ...]}}
with the sections in the order given.
"""


def sections(claims):
    order = []
    for c in claims:
        if c["section"] not in order:
            order.append(c["section"])
    return [(s, [c for c in claims if c["section"] == s]) for s in order]


def render_sections(groups):
    out = []
    for name, pts in groups:
        out.append(f"### {name}")
        for c in pts:
            note = f" (grader note: {c['note']})" if c.get("note") else ""
            out.append(f"- {c['id']}: {c['claim']}{note}")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=configured_model("draft_answer_key_headlines"),
                    help="Claude Code model (default: configs/standard.toml [helpers.draft_answer_key_headlines])")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    claims = json.loads(CLAIMS.read_text())["claims"]
    groups = sections(claims)
    prompt = PROMPT.format(
        n=len(groups),
        finding_description=(MODULES / "finding-description.txt").read_text().strip(),
        addendum=(MODULES / "finding-description-german-wiki.txt").read_text().strip(),
        sections=render_sections(groups),
        report=REPORT.read_text().strip(),
    )
    proc = subprocess.run(
        ["claude", "-p", "--model", a.model, "--output-format", "json", "--no-session-persistence",
         "--tools", "", "--setting-sources", ""],
        input=prompt, capture_output=True, text=True, check=True, cwd="/tmp",
    )
    text = json.loads(proc.stdout)["result"].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    drafted = json.loads(text)["sections"]
    names = [g[0] for g in groups]
    if [d["section"] for d in drafted] != names:
        raise SystemExit(f"sections came back as {[d['section'] for d in drafted]}, expected {names}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({
        "model": a.model, "drafted": datetime.date.today().isoformat(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "script": "scripts/draft_answer_key_headlines.py", "status": "draft, awaiting Oscar's approval",
        "sections": drafted}, ensure_ascii=False, indent=1) + "\n")
    for d in drafted:
        print(f"{d['section']}: {d['claim']}")


if __name__ == "__main__":
    main()
