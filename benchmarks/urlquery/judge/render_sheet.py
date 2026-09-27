"""Fill the v1 finding sheet: one headline finding and its sub-findings per judge call.

Draft only. Nothing grades with this yet; see finding_sheet_v1.md for the prompt itself.

    python benchmarks/urlquery/judge/render_sheet.py F4 [--article A.txt] [--report R.md]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "finding_sheet_v1.md"
FINDINGS = HERE.parent / "claims" / "findings_v1.json"


def scored_group(findings: list[dict], headline_id: str) -> list[dict]:
    """The headline and its children, minus background items tagged not-scored."""
    group = [f for f in findings if f["id"] == headline_id or f["parent"] == headline_id]
    if not group or group[0]["id"] != headline_id or group[0]["parent"] is not None:
        raise ValueError(f"{headline_id} is not a headline finding")
    return [f for f in group if "not-scored" not in f["tags"]]


def render_item(f: dict) -> str:
    role = "headline" if f["parent"] is None else "sub-finding"
    derivable = "derivable" if f["derivable"] == "yes" else "partly derivable"
    lines = [f"### {f['id']} ({role}; {f['kind']}; {derivable})", "", f"**Item:** {f['text']}", ""]
    if "added" in f["tags"]:
        lines += ["**Source:** added by the benchmark authors from the records; the article does not state it directly.", ""]
    for quote in f["quotes"]:
        lines += [f"**In Transluce's article:** “{quote}”", ""]
    if f["judge_notes"]:
        lines += [f"**Notes:** {f['judge_notes']}", ""]
    if f["evidence_scans"]:
        lines += ["**Evidence scans:** " + ", ".join(f["evidence_scans"]), ""]
    return "\n".join(lines).rstrip()


def render(headline_id: str, article: str, report: str) -> str:
    findings = json.loads(FINDINGS.read_text())["findings"]
    group = scored_group(findings, headline_id)
    ids = [f["id"] for f in group]
    return (
        TEMPLATE.read_text()
        .replace("{{SOURCE_ARTICLE}}", article)
        .replace("{{MODEL_REPORT}}", report)
        .replace("{{FINDING_BLOCK}}", "\n\n".join(render_item(f) for f in group))
        .replace("{{ITEM_IDS}}", ", ".join(ids))
        .replace("{{HEADLINE_ID}}", headline_id)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("headline")
    parser.add_argument("--article", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    article = args.article.read_text() if args.article else "{{SOURCE_ARTICLE}}"
    report = args.report.read_text() if args.report else "{{MODEL_REPORT}}"
    print(render(args.headline, article, report))


if __name__ == "__main__":
    main()
