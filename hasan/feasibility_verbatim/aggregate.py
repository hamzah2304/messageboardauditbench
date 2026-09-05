#!/usr/bin/env python3
"""Merge verbatim recheck batches into report/feasibility_verbatim.json and build
a raw-vs-verbatim comparison (report/feasibility_compare.json)."""
import json
from pathlib import Path
from collections import Counter
ROOT=Path("/workspace/collusion")
FV=ROOT/"report/feasibility_verbatim"
approved={c["id"]:c for c in json.loads((ROOT/"report/new_claims_approved.json").read_text())["approved"]}
raw={c["id"]:c for c in json.loads((ROOT/"report/feasibility.json").read_text())["claims"]}
res={}
for i in range(1,7):
    p=FV/f"result_batch_{i}.json"
    for r in json.loads(p.read_text()).get("results",[]):
        res[r["id"]]=r
merged=[]
for cid,c in sorted(approved.items(), key=lambda kv:kv[1]["report_order"]):
    r=res.get(cid,{})
    merged.append({**{k:c[k] for k in ("id","report_order","coverage","maps_to","proposed_id","level","section","claim","report_quote")},
        "verdict":r.get("verdict"),"changed":r.get("changed"),"change_reason":r.get("change_reason",""),
        "confidence":r.get("confidence"),"can_be_met":r.get("can_be_met"),
        "corrected_values":r.get("corrected_values",""),"fact_check":r.get("fact_check",[]),
        "evidence":r.get("evidence",[]),"feas_notes":r.get("notes","")})
vc=Counter(m["verdict"] for m in merged)
(ROOT/"report/feasibility_verbatim.json").write_text(json.dumps(
    {"variant":"verbatim","n":len(merged),"verdicts":dict(vc),
     "can_be_met":dict(Counter(m["can_be_met"] for m in merged)),"claims":merged}, indent=1, ensure_ascii=False))

# comparison
comp=[]
for m in merged:
    rv=raw[m["id"]]["verdict"]; vv=m["verdict"]
    comp.append({"id":m["id"],"report_order":m["report_order"],"section":m["section"],"level":m["level"],
        "claim":m["claim"],"raw_verdict":rv,"verbatim_verdict":vv,
        "flipped":rv!=vv,"change_reason":m.get("change_reason",""),
        "raw_corr":raw[m["id"]].get("corrected_values",""),"verbatim_corr":m.get("corrected_values","")})
flips=[c for c in comp if c["flipped"]]
(ROOT/"report/feasibility_compare.json").write_text(json.dumps(
    {"raw_verdicts":dict(Counter(c["raw_verdict"] for c in comp)),
     "verbatim_verdicts":dict(Counter(c["verbatim_verdict"] for c in comp)),
     "n_flipped":len(flips),"flips":[{k:c[k] for k in ("id","section","raw_verdict","verbatim_verdict","change_reason")} for c in flips],
     "claims":comp}, indent=1, ensure_ascii=False))
print("verbatim verdicts:",dict(vc))
print("raw     verdicts:",dict(Counter(c["raw_verdict"] for c in comp)))
print("flipped:",len(flips))
for c in flips: print(f"  {c['id']} {c['section']}: {c['raw_verdict']} -> {c['verbatim_verdict']}  ({c['change_reason'][:80]})")
