#!/usr/bin/env python3
"""Merge the 6 feasibility result batches into report/feasibility.json:
each approved candidate claim + its verdict / can_be_met / fact_check / evidence."""
import json, glob
from pathlib import Path

ROOT = Path("/workspace/collusion")
FEAS = ROOT / "report/feasibility"
approved = json.loads((ROOT / "report/new_claims_approved.json").read_text())["approved"]
by_id = {c["id"]: c for c in approved}

res = {}
missing_files = []
for i in range(1, 7):
    p = FEAS / f"result_batch_{i}.json"
    if not p.exists():
        missing_files.append(p.name); continue
    for r in json.loads(p.read_text()).get("results", []):
        res[r["id"]] = r

merged = []
for c in sorted(approved, key=lambda x: x["report_order"]):
    r = res.get(c["id"], {})
    merged.append({**c,
        "verdict": r.get("verdict"), "confidence": r.get("confidence"),
        "can_be_met": r.get("can_be_met"), "corrected_values": r.get("corrected_values", ""),
        "fact_check": r.get("fact_check", []), "evidence": r.get("evidence", []),
        "feas_notes": r.get("notes", "")})

from collections import Counter
vc = Counter(m["verdict"] for m in merged)
mc = Counter(m["can_be_met"] for m in merged)
out = {"n": len(merged), "verdicts": dict(vc), "can_be_met": dict(mc),
       "missing_batches": missing_files, "claims": merged}
(ROOT / "report/feasibility.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print("verdicts:", dict(vc))
print("can_be_met:", dict(mc))
print("no result for:", [m["id"] for m in merged if m["verdict"] is None] or "none")
if missing_files: print("MISSING batch files:", missing_files)
