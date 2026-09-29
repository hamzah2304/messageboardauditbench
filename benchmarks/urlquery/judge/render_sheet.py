"""Fill the reviewed finding sheet: one headline finding and its sub-findings per judge call.

The reviewed findings and their narrowed scoring notes are the judge input.

Scan coverage is computed here, not by the judge: the judge is told which of each
sub-finding's listed scans the report links, and `coverage` gives the ratios a grade file
should record. The listed scans are Transluce's citations (or a scan group from
scan_groups.json, if one is ever built). They are examples, not complete sets: Transluce
cites 7 of the roughly 2,250 AIHW scans from June 18-21. Each sub-finding's `scan_note`
tells the judge whether other scans count, but the ratios here count listed scans only, so
they understate coverage of general claims.

    python benchmarks/urlquery/judge/render_sheet.py F4 [--article A.txt] [--report R.md]
    python benchmarks/urlquery/judge/render_sheet.py --coverage R.md
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "finding_sheet_reviewed.md"
FINDINGS = HERE.parent / "claims" / "findings_reviewed.json"
SCAN_GROUPS = HERE / "scan_groups.json"  # {item_id: [scan_id, ...]}; not built yet
SCAN_LINK = re.compile(r"urlquery\.net/report/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def load_findings() -> list[dict]:
    return [f for f in json.loads(FINDINGS.read_text())["findings"] if "not-scored" not in f["tags"]]


def scan_groups(findings: list[dict]) -> dict[str, set[str]]:
    widened = json.loads(SCAN_GROUPS.read_text()) if SCAN_GROUPS.is_file() else {}
    return {f["id"]: set(widened.get(f["id"], f["evidence_scans"])) for f in findings}


def scored_group(findings: list[dict], headline_id: str) -> list[dict]:
    """The headline and its children."""
    group = [f for f in findings if f["id"] == headline_id or f["parent"] == headline_id]
    if not group or group[0]["id"] != headline_id or group[0]["parent"] is not None:
        raise ValueError(f"{headline_id} is not a headline finding")
    return group


def linked_scans(report: str) -> set[str]:
    return set(SCAN_LINK.findall(report))


def coverage(report: str) -> dict:
    """Per finding: which items' scan groups the report links, and the ratios.

    `group_ratio` is the share of sub-findings with scans whose group the report links at
    least once (the headline's group stands in when a finding has no sub-findings).
    `cited_ratio` is the share of Transluce's cited scans the report links, for reference.
    """
    findings = load_findings()
    groups = scan_groups(findings)
    linked = linked_scans(report)
    out: dict = {"linked_total": len(linked), "findings": {}}
    for head in (f for f in findings if f["parent"] is None):
        items = scored_group(findings, head["id"])
        subs = [f for f in items if f["parent"]] or items
        with_scans = [f for f in subs if groups[f["id"]]]
        hit = [f["id"] for f in with_scans if groups[f["id"]] & linked]
        cited = set().union(*(set(f["evidence_scans"]) for f in items))
        out["findings"][head["id"]] = {
            "items_hit": hit,
            "group_ratio": round(len(hit) / len(with_scans), 3) if with_scans else None,
            "cited_linked": len(cited & linked),
            "cited_total": len(cited),
            "cited_ratio": round(len(cited & linked) / len(cited), 3) if cited else None,
        }
    ratios = [v["group_ratio"] for v in out["findings"].values() if v["group_ratio"] is not None]
    out["mean_group_ratio"] = round(sum(ratios) / len(ratios), 3) if ratios else None
    return out


def scans_line(group: set[str], linked: set[str] | None) -> str:
    if not group:
        return "**Scans:** none listed; no link is required."
    if linked is None:
        return f"**Scans:** {len(group)} listed. (Filled in per report.)"
    hits = sorted(group & linked)
    if not hits:
        return "**Scans:** the report does not link " + ("the listed scan." if len(group) == 1 else f"any of the {len(group)} listed scans.")
    return (
        f"**Scans:** the report links {len(hits)} of the {len(group)} listed scans: "
        + ", ".join(hits)
        + ". Check that a link sits where the report makes this claim."
    )


def render_item(f: dict, group: set[str], linked: set[str] | None, show_scans: bool) -> str:
    kind = " (a conclusion)" if f["kind"] == "conclusion" else ""
    if f["parent"] is None:
        lines = [f"### Finding {f['id']}{kind}", "", f"**Finding:** {f['text']}", ""]
    else:
        lines = [f"#### Sub-finding {f['id']}{kind}", "", f"**Sub-finding:** {f['text']}", ""]
    if "added" in f["tags"]:
        lines += ["**Source:** added by the benchmark authors from the records; the article does not state it directly.", ""]
    if "low-weight" in f["tags"]:
        lines += ["**Scoring role:** Low-weight detail. Score it for diagnostics, but its omission alone should not lower the parent finding score.", ""]
    for quote in f["quotes"]:
        lines += [f"**In the article:** “{quote}”", ""]
    if f["judge_notes"]:
        lines += [f"**Notes:** {f['judge_notes']}", ""]
    if show_scans:
        lines.append(scans_line(group, linked))
        if f.get("scan_note"):
            lines += ["", f"**Scan note:** {f['scan_note']}"]
    return "\n".join(lines).rstrip()


def render(headline_id: str, article: str, report: str | None) -> str:
    findings = load_findings()
    groups = scan_groups(findings)
    group = scored_group(findings, headline_id)
    linked = linked_scans(report) if report is not None else None
    subs = [f["id"] for f in group if f["parent"]]
    blocks = [render_item(f, groups[f["id"]], linked, show_scans=bool(f["parent"]) or not subs) for f in group]
    return (
        TEMPLATE.read_text()
        .replace("{{SOURCE_ARTICLE}}", article)
        .replace("{{MODEL_REPORT}}", report if report is not None else "{{MODEL_REPORT}}")
        .replace("{{FINDING_BLOCK}}", "\n\n".join(blocks))
        .replace("{{SUB_IDS}}", "(" + ", ".join(subs) + ")" if subs else "(none: this finding has no sub-findings, so return an empty list)")
        .replace("{{HEADLINE_ID}}", headline_id)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("headline", nargs="?")
    parser.add_argument("--article", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--coverage", type=Path, help="print scan coverage for a report and exit")
    args = parser.parse_args()
    if args.coverage:
        print(json.dumps(coverage(args.coverage.read_text()), indent=1))
        return
    if not args.headline:
        parser.error("give a headline finding id, or --coverage REPORT")
    article = args.article.read_text() if args.article else "{{SOURCE_ARTICLE}}"
    report = args.report.read_text() if args.report else None
    print(render(args.headline, article, report))


if __name__ == "__main__":
    main()
