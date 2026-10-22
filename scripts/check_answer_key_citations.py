#!/usr/bin/env python3
"""Check every citation in an answer-key-v1 file: the record exists and the quote appears in it.

    python3 scripts/check_answer_key_citations.py german-wiki [--data DIR]
    python3 scripts/check_answer_key_citations.py aivillage [--data DIR]

Sets each citation's `check` to ok, id_missing, quote_missing or no_quote (the record exists; there is
no quote to compare) in benchmarks/<eval>/answer-key.json, and adds a review_queue entry for each
finding with a failure (replacing earlier citation entries). Quotes are compared after normalising
case, whitespace, curly quotes and JSON escapes.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = Path(subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute",
                                        "--git-common-dir"], text=True).strip()).parent
# Loaded from its file, not via sys.path: the package folder also holds a benchmarks.py that would
# shadow the top-level benchmarks package for anything imported later.
_spec = importlib.util.spec_from_file_location("answer_key", ROOT / "slopvestigator_bench/answer_key.py")
answer_key = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_key)

DATA = {"german-wiki": PRIMARY / "data/verbatim", "aivillage": PRIMARY / "data/aivillage/full-v2-reasoning"}
WIKI_FILES = {"rev": ("revisions.jsonl", "rev_id"), "event": ("events.jsonl", "event_id"),
              "page": ("pages.jsonl", "page_id"), "label": ("labels.jsonl", "label")}


def norm(s):
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace('\\"', '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def load_wiki(data, wanted):
    found = {}
    for kind, (name, field) in WIKI_FILES.items():
        ids = {i for k, i in wanted if k == kind}
        if not ids:
            continue
        with open(data / name) as fh:
            for line in fh:
                r = json.loads(line)
                if str(r.get(field)) in ids:
                    found[(kind, str(r.get(field)))] = " ".join(str(v) for v in r.values()) + " " + line
    return found


def load_village(data, wanted):
    spec = importlib.util.spec_from_file_location("cac", ROOT / "scripts/aivillage/check_aivillage_citations.py")
    cac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cac)
    return cac.load(data, wanted)


def main():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument("eval", choices=sorted(DATA))
    ap.add_argument("--data", type=Path)
    a = ap.parse_args()
    path = ROOT / "benchmarks" / a.eval / "answer-key.json"
    key = answer_key.load(path)
    cites = list(answer_key.iter_citations(key))
    wanted = {tuple(c["ref"].split(":", 1)) for _, c in cites}
    data = a.data or DATA[a.eval]
    found = (load_wiki if a.eval == "german-wiki" else load_village)(data, wanted)
    failures = {}
    for owner, c in cites:
        text = found.get(tuple(c["ref"].split(":", 1)))
        if text is None:
            c["check"] = "id_missing"
        elif not c["quote"]:
            c["check"] = "no_quote"
        else:
            hay = norm(text) + " " + norm(text.encode().decode("unicode_escape", errors="ignore"))
            c["check"] = "ok" if norm(c["quote"]) in hay else "quote_missing"
        if c["check"] in ("id_missing", "quote_missing"):
            failures.setdefault(owner, []).append(c)
    parent = {s["id"]: f["id"] for f in key["findings"] for s in f["subfindings"]}
    by_finding = {}
    for owner, cs in failures.items():
        by_finding.setdefault(parent.get(owner, owner), []).extend((owner, c) for c in cs)
    key["review_queue"] = [q for q in key.get("review_queue", []) if not q["why"].startswith("citation check")]
    for fid, cs in sorted(by_finding.items()):
        key["review_queue"].append({"id": fid, "why": "citation check: " + "; ".join(
            f"{o} {c['check']} {c['ref'][:40]} \"{c['quote'][:60]}\"" for o, c in cs)})
    answer_key.dump(key, path)
    counts = {}
    for _, c in cites:
        counts[c["check"]] = counts.get(c["check"], 0) + 1
    print(json.dumps({"citations": len(cites), "counts": counts, "findings_with_failures": sorted(by_finding)}, indent=1))


if __name__ == "__main__":
    main()
