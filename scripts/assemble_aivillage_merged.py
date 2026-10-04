#!/usr/bin/env python3
"""Attach the extracted evidence to a merged AI Village findings file.

    python3 scripts/assemble_aivillage_merged.py MERGE_INPUT_DIR MERGED_JSON OUT_JSON

The merge agent refers to extracted findings by ID only. This writes each merged finding in
full: its wording, and under every subfinding the source quotes, evidence notes and judge
notes of the extracted subfindings it was built from. Runs the coverage check first.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_aivillage_merge import check


def main():
    source_dir, merged_path, out_path = map(Path, sys.argv[1:4])
    merged = json.loads(merged_path.read_text())
    problems = check(merged, json.loads((source_dir / "ids.json").read_text()))
    if problems:
        raise SystemExit("merged file fails the coverage check:\n" + "\n".join(problems[:20]))
    extracted = {p.stem: json.loads(p.read_text()) for p in (source_dir / "findings").glob("*.json")}
    subs = {sf["id"]: sf for f in extracted.values() for sf in f["subfindings"]}

    def origin(fid):
        f = extracted[fid]
        return {"id": fid, "source": f["source"], "source_date": f["source_date"], "extracted_as": f["extracted_as"]}

    def evidence(sub_ids):
        return {"source_support": [{**s, "from": i} for i in sub_ids for s in subs[i]["source_support"]],
                "evidence_notes": [{"from": i, "note": subs[i]["evidence_note"]} for i in sub_ids if subs[i].get("evidence_note")],
                "log_evidence": "not yet verified"}

    out = []
    for m in merged["merged"]:
        if m.get("unchanged"):
            f = extracted[m["sources"][0]]
            full = {"id": m["id"], "headline": f["headline"], "finding": f["finding"], "notes": f["notes"], "unchanged": True,
                    "subfindings": [{"id": f"{m['id']}.{n}", "from": [sf["id"]], "claim": sf["claim"], "notes": sf.get("notes", []),
                                     **evidence([sf["id"]])} for n, sf in enumerate(f["subfindings"], 1)]}
        else:
            full = {"id": m["id"], "headline": m["headline"], "finding": m["finding"], "notes": m.get("notes", []),
                    "merge_note": m.get("merge_note", ""),
                    "subfindings": [{**sf, "notes": sf.get("notes", []), **evidence(sf["from"])} for sf in m["subfindings"]]}
        full["sources"] = [origin(fid) for fid in m["sources"]]
        out.append(full)
    result = {"merged": out,
              "dropped": [{**d, "finding": extracted[d["id"]]} for d in merged["dropped"]],
              "dropped_subfindings": [{**d, "subfinding": subs[d["id"]]} for d in merged.get("dropped_subfindings", [])]}
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    kinds = lambda m: {s["id"][0] for s in m["sources"]}  # noqa: E731
    print(json.dumps({"merged_findings": len(out), "subfindings": sum(len(m["subfindings"]) for m in out),
                      "from_several_extracted_findings": sum(len(m["sources"]) > 1 for m in out),
                      "from_several_source_types": sum(len(kinds(m)) > 1 for m in out),
                      "dropped": len(result["dropped"])}))


if __name__ == "__main__":
    main()
