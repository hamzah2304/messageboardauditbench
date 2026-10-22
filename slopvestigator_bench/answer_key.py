"""The answer-key-v1 format: one JSON file per eval, benchmarks/<eval>/answer-key.json.

QA output, the review page and the grader all read this one definition. A file looks like

    {"format": "answer-key-v1", "eval": "german-wiki", "source": "...", "qa_process": {...},
     "findings": [<finding>, ...], "excluded": [<excluded>, ...], "review_queue": [...]}

A finding:

    {"id", "claim", "detail", "significance": "major"|"minor"|None, "judge_notes",
     "evidence": [{"text", "citations": [{"ref", "quote", "check"}]}],
     "fields": {...eval-specific...},
     "qa": {"outcome": "keep"|"narrow"|"drop", "reason", "duplicate_of", "proposed_wording",
            "make_harder", "how_to_find", "run"} | None,
     "subfindings": [<subfinding>, ...]}

A subfinding:

    {"id", "claim", "significance", "judge_notes", "evidence", "fields",
     "qa": {"verdict": "supported"|"partly"|"contradicted"|"not found"|"outside the data",
            "overstated": "yes"|"no"|None, "duplicate_of", "reason", "proposed_wording"} | None}

`significance` and `qa` are None until QA has run. Ids are stable across QA, review and grading.
`excluded` lists what was decided out before this file (id, kind, claim, reason); `review_queue`
lists items that need a person's look beyond the normal review (id, why).

Only the standard library is used, so scripts and the sandbox can import it without the package.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FORMAT = "answer-key-v1"
OUTCOMES = ("keep", "narrow", "drop")
VERDICTS = ("supported", "partly", "contradicted", "not found", "outside the data")
SIGNIFICANCE = ("major", "minor")
OVERSTATED = ("yes", "no")
CITATION_KINDS = {
    "german-wiki": ("rev", "event", "page", "label"),
    "aivillage": ("chat", "turn", "session", "event", "memory", "claude_code", "transcript"),
}
_BRACKET = re.compile(r"\[([^\[\]]*)\]")


def parse_citations(text: str, kinds) -> list[dict]:
    """Citations like [rev:<id> "quote"] or [page:<id>] in `text`, several per bracket allowed."""
    one = re.compile(
        r"(" + "|".join(map(re.escape, kinds)) + r'):([^\s\]";,]+)(?:\s+["“]((?:\\.|[^"”\\])*)["”])?(?=\s*(?:[;,]|$))'
    )
    out = []
    for b in _BRACKET.finditer(text or ""):
        for m in one.finditer(b.group(1).strip()):
            out.append({"ref": f"{m.group(1)}:{m.group(2)}", "quote": m.group(3) or "", "check": "unchecked"})
    return out


def evidence(items, kinds) -> list[dict]:
    """Evidence entries from a list of texts with inline citations."""
    if isinstance(items, str):
        items = [items]
    return [{"text": t, "citations": parse_citations(t, kinds)} for t in items or [] if str(t).strip()]


def load(path) -> dict:
    return json.loads(Path(path).read_text())


def dump(key: dict, path) -> None:
    Path(path).write_text(json.dumps(key, ensure_ascii=False, indent=1) + "\n")


def _check_evidence(where, ev, problems):
    if not isinstance(ev, list):
        problems.append(f"{where}: evidence is not a list")
        return
    for e in ev:
        if not isinstance(e, dict) or "text" not in e or not isinstance(e.get("citations"), list):
            problems.append(f"{where}: evidence entry needs text and citations")


def validate(key: dict) -> list[str]:
    """Problems that make a file unusable; empty when it is valid."""
    problems = []
    if key.get("format") != FORMAT:
        problems.append(f"format is {key.get('format')!r}, not {FORMAT}")
    seen = set()
    for f in key.get("findings", []):
        fid = f.get("id")
        if not fid or fid in seen:
            problems.append(f"finding id missing or repeated: {fid!r}")
        seen.add(fid)
        for k in ("claim", "detail", "judge_notes", "evidence", "fields", "subfindings"):
            if k not in f:
                problems.append(f"{fid}: missing {k}")
        if f.get("significance") not in (*SIGNIFICANCE, None):
            problems.append(f"{fid}: significance {f.get('significance')!r}")
        _check_evidence(fid, f.get("evidence", []), problems)
        qa = f.get("qa")
        if qa is not None:
            if qa.get("outcome") not in OUTCOMES:
                problems.append(f"{fid}: outcome {qa.get('outcome')!r}")
            for k in ("reason", "duplicate_of", "proposed_wording", "make_harder", "how_to_find"):
                if not isinstance(qa.get(k, None), str):
                    problems.append(f"{fid}: qa.{k} must be a string")
        for s in f.get("subfindings", []):
            sid = s.get("id")
            if not sid or sid in seen:
                problems.append(f"subfinding id missing or repeated: {sid!r}")
            seen.add(sid)
            for k in ("claim", "judge_notes", "evidence"):
                if k not in s:
                    problems.append(f"{sid}: missing {k}")
            if s.get("significance") not in (*SIGNIFICANCE, None):
                problems.append(f"{sid}: significance {s.get('significance')!r}")
            _check_evidence(sid, s.get("evidence", []), problems)
            sqa = s.get("qa")
            if sqa is not None:
                if sqa.get("verdict") not in VERDICTS:
                    problems.append(f"{sid}: verdict {sqa.get('verdict')!r}")
                if sqa.get("overstated") not in (*OVERSTATED, None):
                    problems.append(f"{sid}: overstated {sqa.get('overstated')!r}")
    for x in key.get("excluded", []):
        if not x.get("id") or not x.get("reason"):
            problems.append(f"excluded entry needs id and reason: {x}")
    return problems


def _norm_verdict(v: str) -> str:
    v = (v or "").strip().lower()
    return {"partly supported": "partly", "outside the records": "outside the data"}.get(v, v)


def _yes_no(v) -> str | None:
    if isinstance(v, bool):
        return "yes" if v else "no"
    v = str(v or "").strip().lower()
    return v if v in OVERSTATED else None


def qa_problems(result: dict, finding: dict) -> list[str]:
    """Why a QA agent's output cannot be merged as is; empty when it can."""
    out = []
    if result.get("id") != finding["id"]:
        out.append(f"id {result.get('id')!r} is not {finding['id']}")
    if str(result.get("outcome", "")).lower() not in OUTCOMES:
        out.append(f"unknown outcome {result.get('outcome')!r}")
    if str(result.get("significance", "")).lower() not in SIGNIFICANCE:
        out.append(f"unknown significance {result.get('significance')!r}")
    want = [s["id"] for s in finding["subfindings"]]
    got = [s.get("id") for s in result.get("subfindings", [])]
    if sorted(want) != sorted(got):
        out.append(f"subfindings {got} do not match {want}")
    for s in result.get("subfindings", []):
        if _norm_verdict(s.get("verdict")) not in VERDICTS:
            out.append(f"{s.get('id')}: unknown verdict {s.get('verdict')!r}")
        if _yes_no(s.get("overstated")) is None:
            out.append(f"{s.get('id')}: overstated must be yes or no")
        if str(s.get("significance", "")).lower() not in SIGNIFICANCE:
            out.append(f"{s.get('id')}: unknown significance {s.get('significance')!r}")
    return out


def apply_qa(finding: dict, result: dict, kinds, run: str = "") -> dict:
    """Merge one QA agent's output into a finding (a copy is returned). Ids come from the finding."""
    f = json.loads(json.dumps(finding))
    f["significance"] = str(result.get("significance", "")).lower() or None
    f["evidence"] = evidence(result.get("evidence"), kinds)
    f["qa"] = {
        "outcome": str(result.get("outcome", "")).lower(),
        "reason": result.get("reason", "") or "",
        "duplicate_of": result.get("duplicate_of", "") or "",
        "proposed_wording": result.get("proposed_claim", "") or "",
        "make_harder": result.get("make_harder", "") or "",
        "how_to_find": result.get("how_to_find", "") or "",
        "run": run,
    }
    by_id = {s.get("id"): s for s in result.get("subfindings", [])}
    for s in f["subfindings"]:
        r = by_id.get(s["id"])
        if r is None:
            continue
        s["significance"] = str(r.get("significance", "")).lower() or None
        s["evidence"] = evidence(r.get("evidence"), kinds)
        s["qa"] = {
            "verdict": _norm_verdict(r.get("verdict")),
            "overstated": _yes_no(r.get("overstated")),
            "duplicate_of": r.get("duplicate_of", "") or "",
            "reason": r.get("reason", "") or "",
            "proposed_wording": r.get("proposed_claim", "") or "",
        }
    return f


def iter_citations(key: dict):
    """Every citation in the file, with the id of the finding or subfinding it sits under."""
    for f in key.get("findings", []):
        for e in f.get("evidence", []):
            for c in e["citations"]:
                yield f["id"], c
        for s in f.get("subfindings", []):
            for e in s.get("evidence", []):
                for c in e["citations"]:
                    yield s["id"], c
