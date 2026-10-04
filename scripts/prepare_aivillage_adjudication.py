#!/usr/bin/env python3
"""Write adjudication batches for verified AI Village findings that have no batch yet.

    python3 scripts/prepare_aivillage_adjudication.py MERGED_FULL_JSON VERIFY_DIR DATA_DIR [BATCH_SIZE]

Each batch file (VERIFY_DIR/adjudication/batch-N.json) holds, per finding, its wording, the outside
quotes it was written from, the verifier's result and the machine check of the verifier's citations.
Findings already in a batch file are skipped, so this can be rerun as more results arrive.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewers"))
from build_aivillage_verified_review import check_citations

SUB_KEYS = ("verdict", "evidence", "wording", "confidence", "wording_problem", "proposed_claim", "searched", "needs_reasoning_traces")


def main():
    merged_path, verify_dir, data = map(Path, sys.argv[1:4])
    size = int(sys.argv[4]) if len(sys.argv) > 4 else 22
    adj = verify_dir / "adjudication"
    adj.mkdir(exist_ok=True)
    batches = sorted(adj.glob("batch-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    done = {f["id"] for p in batches for f in json.loads(p.read_text())}
    results = {p.stem: json.loads(p.read_text()) for p in (verify_dir / "results").glob("*.json") if p.stem not in done}
    if not results:
        return print("nothing new")
    cites = check_citations(results, data)
    all_cites = json.loads((adj / "citation-check.json").read_text()) if (adj / "citation-check.json").exists() else {}
    (adj / "citation-check.json").write_text(json.dumps({**all_cites, **cites}, indent=1))
    items = []
    for m in json.loads(merged_path.read_text())["merged"]:
        v = results.get(m["id"])
        if not v:
            continue
        by = {s.get("id"): s for s in v.get("subfindings", [])}
        c = cites.get(m["id"], {})
        items.append({"id": m["id"], "headline": m["headline"], "finding": m["finding"], "notes": m["notes"],
                      "sources": [f"{s['source']['type']}, published {s['source_date']}" for s in m["sources"]],
                      "verifier": {"verdict": v.get("verdict"), "proposed_headline": v.get("proposed_headline", ""),
                                   "proposed_finding": v.get("proposed_finding", ""), "behavior_dates": v.get("behavior_dates", ""),
                                   "notes": v.get("notes", []), "citations_checked": c.get("citations"),
                                   "citations_ok": c.get("ok"), "citation_failures": c.get("failures", [])},
                      "subfindings": [{"id": sf["id"], "claim": sf["claim"],
                                       "outside_quotes": [s["quote"][:400] for s in sf["source_support"]][:4],
                                       "verifier": {k: by.get(sf["id"], {}).get(k) for k in SUB_KEYS}} for sf in m["subfindings"]]})
    n = len(batches)
    for i in range(0, len(items), size):
        n += 1
        (adj / f"batch-{n}.json").write_text(json.dumps(items[i:i + size], ensure_ascii=False, indent=1))
        print(f"batch-{n}", len(items[i:i + size]), items[i]["id"], items[min(i + size, len(items)) - 1]["id"])


if __name__ == "__main__":
    main()
