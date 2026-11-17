#!/usr/bin/env python3
"""Machine-check the verifier's record citations for AI Village findings whose citations were never checked.

    python3 scripts/aivillage/check_aivillage_key_citations.py DATA_DIR [--out FILE] [--all]

Reads benchmarks/aivillage/findings/final-findings.json and checks every citation in each
subfinding's `records` text (the verifier's evidence): the record exists and the quote appears in it.
By default only findings with no `citation_check` yet (84 of 190); --all checks every finding.
Uses the loader of scripts/check_aivillage_citations.py, once for all cited records, because each
load streams the multi-gigabyte files. Writes one entry per finding to --out
(default benchmarks/aivillage/findings/citation-check-remaining.json).
"""
import argparse
import importlib.util
import json
import warnings
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINDINGS = ROOT / "benchmarks/aivillage/findings/final-findings.json"
spec = importlib.util.spec_from_file_location("cac", ROOT / "scripts/aivillage/check_aivillage_citations.py")
cac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cac)


def citations(text):
    return [(m.group(1), m.group(2), m.group(3))
            for b in cac.BRACKET.finditer(text or "") for m in cac.ONE.finditer(b.group(1).strip())]


def status(found, kind, rid, quote):
    text = found.get((kind, rid))
    if text is None:
        return "id_missing"
    if not quote:
        return "no_quote"
    hay = cac.norm(text) + " " + cac.norm(text.encode().decode("unicode_escape", errors="ignore"))
    if cac.norm(quote) in hay:
        return "ok"
    # The verifier sometimes copied a JSON-escaped quote (\"seconds\": 45); compare it unescaped too.
    return "ok_unescaped" if "\\" in quote and cac.norm(quote.replace('\\"', '"')) in hay else "quote_missing"


def main():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--out", type=Path, default=FINDINGS.parent / "citation-check-remaining.json")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    findings = [f for f in json.loads(FINDINGS.read_text()) if a.all or f.get("citation_check") is None]
    wanted = {(k, i) for f in findings for s in f["subfindings"] for k, i, _ in citations(s.get("records"))}
    found = cac.load(a.data, wanted)
    out, total = [], Counter()
    for f in findings:
        subs = []
        for s in f["subfindings"]:
            cites = [{"kind": k, "id": i, "quote": q, "status": status(found, k, i, q)} for k, i, q in citations(s.get("records"))]
            total.update(c["status"] for c in cites)
            subs.append({"id": s["id"], "decision": s["decision"], "citations": len(cites),
                         "ok": sum(c["status"].startswith("ok") for c in cites),
                         "failures": [c for c in cites if not c["status"].startswith("ok")]})
        n = sum(s["citations"] for s in subs)
        ok = sum(s["ok"] for s in subs)
        out.append({"id": f["id"], "group": f["group"], "citations": n, "ok": ok, "subfindings": subs})
    # A chat citation whose id is missing may carry a real quote under a mistyped id: say where it is.
    lost = [c for r in out for s in r["subfindings"] for c in s["failures"]
            if c["kind"] == "chat" and c["status"] == "id_missing" and c["quote"]]
    if lost:
        with open(a.data / "chat_messages.jsonl") as fh:
            for line in fh:
                text = cac.norm(json.loads(line).get("content") or "")
                for c in lost:
                    if cac.norm(c["quote"]) in text:
                        c.setdefault("quote_found_in", []).append("chat:" + json.loads(line)["id"])
    a.out.write_text(json.dumps({"data": str(a.data), "findings": len(out), "counts": dict(total), "results": out},
                                ensure_ascii=False, indent=1) + "\n")
    failing = [r for r in out if r["ok"] < r["citations"]]
    print(json.dumps({"findings": len(out), "counts": dict(total), "findings_with_failures": len(failing),
                      "in_key_with_failures": [r["id"] for r in failing if r["group"] in ("keep", "rewrite")],
                      "no_citations": [r["id"] for r in out if r["citations"] == 0]}, indent=1))


if __name__ == "__main__":
    main()
