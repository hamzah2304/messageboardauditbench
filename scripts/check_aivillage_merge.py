#!/usr/bin/env python3
"""Check a merged AI Village findings file against the merge input: nothing lost, nothing used twice.

    python3 check_merge.py MERGED_JSON [IDS_JSON]

IDS_JSON defaults to ids.json next to this script. Exit code 1 if any check fails.

Checks: every input finding is in exactly one merged finding's "sources" or in "dropped";
every subfinding of a kept finding is in exactly one merged subfinding's "from" or in
"dropped_subfindings" (a finding marked "unchanged" keeps all of its own); merged IDs are
unique; each drop has a reason; each merged finding names what went wrong ("failure").
"""
import json
import sys
from collections import Counter
from pathlib import Path


def check(merged, ids):
    problems = []
    all_subs = {s for subs in ids.values() for s in subs}
    used = Counter()
    for m in merged["merged"]:
        used.update(m["sources"])
    used.update(d["id"] for d in merged["dropped"])
    for fid in ids:
        if used[fid] != 1:
            problems.append(f"finding {fid} appears {used[fid]} times (must be exactly once in merged sources or dropped)")
    problems += [f"unknown finding ID {fid}" for fid in used if fid not in ids]
    problems += [f"dropped finding {d['id']} has no reason" for d in merged["dropped"] if not d.get("reason")]

    kept = {s for m in merged["merged"] for fid in m["sources"] for s in ids.get(fid, [])}
    sub_used = Counter()
    merged_ids = Counter()
    for m in merged["merged"]:
        merged_ids[m["id"]] += 1
        if not m.get("failure"):
            problems.append(f"{m['id']} does not say what went wrong (\"failure\")")
        own = {s for fid in m["sources"] for s in ids.get(fid, [])}
        if m.get("unchanged"):
            # One source finding kept exactly as extracted: all its subfindings come along.
            if len(m["sources"]) != 1 or m.get("subfindings"):
                problems.append(f"{m['id']} is marked unchanged, so it needs exactly one source and no subfindings")
            sub_used.update(own)
            continue
        if not m.get("subfindings"):
            problems.append(f"{m['id']} has no subfindings")
        for sf in m.get("subfindings", []):
            merged_ids[sf["id"]] += 1
            if not sf["from"]:
                problems.append(f"{sf['id']} names no source subfinding")
            sub_used.update(sf["from"])
            problems += [f"{sf['id']} uses {s}, which is not a subfinding of {m['id']}'s sources" for s in sf["from"] if s not in own]
    for d in merged.get("dropped_subfindings", []):
        sub_used[d["id"]] += 1
        if not d.get("reason"):
            problems.append(f"dropped subfinding {d['id']} has no reason")
    for s in sorted(kept):
        if sub_used[s] != 1:
            problems.append(f"subfinding {s} appears {sub_used[s]} times (must be exactly once in a merged subfinding or dropped_subfindings)")
    problems += [f"unknown subfinding ID {s}" for s in sub_used if s not in all_subs]
    problems += [f"subfinding {s} belongs to a dropped finding" for s in sub_used if s in all_subs and s not in kept]
    problems += [f"merged ID {i} is used {n} times" for i, n in merged_ids.items() if n > 1]
    return problems


def main():
    merged = json.loads(Path(sys.argv[1]).read_text())
    ids_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("ids.json")
    ids = json.loads(ids_path.read_text())
    problems = check(merged, ids)
    print(json.dumps({"input_findings": len(ids), "merged_findings": len(merged["merged"]),
                      "dropped_findings": len(merged["dropped"]),
                      "kept_unchanged": sum(bool(m.get("unchanged")) for m in merged["merged"]),
                      "merged_subfindings": sum(len(m.get("subfindings", [])) for m in merged["merged"]),
                      "dropped_subfindings": len(merged.get("dropped_subfindings", [])),
                      "problems": len(problems)}))
    for p in problems[:200]:
        print("PROBLEM:", p)
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
