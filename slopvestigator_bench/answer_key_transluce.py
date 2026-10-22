"""The Transluce answer key in answer-key-v1 (slopvestigator_bench/answer_key.py) and back.

benchmarks/transluce/answer-key.json is converted from the reviewed findings file
benchmarks/transluce/claims/findings_reviewed.json (the transluce-report-v1.0 rubric): headlines
become findings and their children subfindings, scans become `scan:<id>` citations, headline F3
(weight 0.5 in v1.0) and the "low-weight" children are minor. The grader reads the key and
rebuilds the reviewed file with `to_transluce`, byte for byte (tests check it), so the judge sees
the same prompts and earlier grades still match their findings hash.
"""
from __future__ import annotations

from slopvestigator_bench import answer_key

SOURCE = "benchmarks/transluce/claims/findings_reviewed.json"
# The two key orders the reviewed file uses (findings added from a model report differ).
_ORDER = ("id", "parent", "text", "kind", "derivable", "tags", "episode", "note", "judge_notes",
          "scan_note", "evidence_scans", "quotes", "revised_from")
_ORDER_SOURCED = ("id", "parent", "text", "kind", "derivable", "tags", "episode", "quotes",
                  "evidence_scans", "source", "note", "judge_notes", "scan_note")
_FIELDS = ("kind", "derivable", "tags", "episode", "note", "scan_note", "quotes", "revised_from", "source")


def _item(f: dict, minor: set[str]) -> dict:
    scans = f["evidence_scans"]
    return {
        "id": f["id"],
        "claim": f["text"],
        "significance": "minor" if "low-weight" in f["tags"] or f["id"] in minor else "major",
        "judge_notes": f["judge_notes"],
        "evidence": [{"text": "", "citations": [{"ref": f"scan:{s}", "quote": "", "check": "unchecked"}
                                                for s in scans]}] if scans else [],
        "fields": {k: f[k] for k in _FIELDS if k in f},
        "qa": None,
    }


def from_transluce(doc: dict, headline_weights: dict[str, float]) -> dict:
    """findings_reviewed.json -> answer-key-v1."""
    if set(headline_weights.values()) - {0.5}:
        raise ValueError("Transluce headline weights other than 0.5 have no significance level")
    minor = set(headline_weights)
    findings: list[dict] = []
    heads: dict[str, dict] = {}
    for f in doc["findings"]:
        item = _item(f, minor)
        if f["parent"] is None:
            item = {**item, "detail": "", "subfindings": []}
            findings.append(item)
            heads[f["id"]] = item
        else:
            heads[f["parent"]]["subfindings"].append(item)
    excluded = [{"id": f"X{i:02d}", "kind": "article_quote", "claim": e["quote"], "reason": e["reason"]}
                for i, e in enumerate(doc["excluded"], 1)]
    excluded += [{"id": r["v1_id"], "kind": "removed_finding", "claim": r["text"], "reason": r["reason"]}
                 for r in doc["removed"]]
    header = {k: doc[k] for k in doc if k not in ("findings", "excluded", "removed")}
    return {"format": answer_key.FORMAT, "eval": "transluce", "source": SOURCE, "source_header": header,
            "qa_process": None, "findings": findings, "excluded": excluded, "review_queue": []}


def to_transluce(key: dict) -> dict:
    """answer-key-v1 -> the findings_reviewed.json structure the Transluce grader renders from."""
    def flat(item: dict, parent: str | None) -> dict:
        values = {**item["fields"], "id": item["id"], "parent": parent, "text": item["claim"],
                  "judge_notes": item["judge_notes"],
                  "evidence_scans": [c["ref"].removeprefix("scan:") for e in item["evidence"] for c in e["citations"]]}
        order = _ORDER_SOURCED if "source" in item["fields"] else _ORDER
        return {k: values[k] for k in order if k in values}

    findings = []
    for finding in key["findings"]:
        findings.append(flat(finding, None))
        findings += [flat(sub, finding["id"]) for sub in finding["subfindings"]]
    return {**key["source_header"], "findings": findings,
            "excluded": [{"quote": e["claim"], "reason": e["reason"]} for e in key["excluded"] if e["kind"] == "article_quote"],
            "removed": [{"v1_id": e["id"], "text": e["claim"], "reason": e["reason"]}
                        for e in key["excluded"] if e["kind"] == "removed_finding"]}
