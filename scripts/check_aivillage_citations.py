#!/usr/bin/env python3
"""Check the citations in AI Village reports: does each cited id exist, and does its quote appear in it?

    scripts/check_aivillage_citations.py DATA_DIR REPORT.md [REPORT.md ...] [--json]

Citations look like [turn:<id> "quote"]. Quotes are compared after normalising case,
whitespace and curly quotes. Grader-side only; agents never run this.
"""
import argparse
import warnings
import gzip
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

BRACKET = re.compile(r"\[([^\[\]]*)\]")
ONE = re.compile(r'(chat|turn|session|event|memory|claude_code|transcript):([^\s\]";,]+)(?:\s+["“](.*?)["”])?(?=\s*(?:[;,]|$))')


def norm(s):
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


def load(data, wanted):
    """Return {(kind, id): text} for the cited records only."""
    found = {}
    def scan(path, kind, key, opener=open):
        ids = {i for k, i in wanted if k == kind}
        if not ids or not path.exists():
            return
        with opener(path, "rt") as f:
            for line in f:
                r = json.loads(line)
                rid = str(r.get(key))
                if rid in ids:
                    found[(kind, rid)] = json.dumps(r, ensure_ascii=False) + " " + str(r.get("content", ""))
    scan(data / "chat_messages.jsonl", "chat", "id")
    scan(data / "events.jsonl", "event", "event_index")
    scan(data / "claude_code_messages.jsonl", "claude_code", "id")
    mem = data / "agent_memories.jsonl"
    scan(mem if mem.exists() else data / "agent_memories.jsonl.gz", "memory", "id", open if mem.exists() else gzip.open)
    db = sqlite3.connect(f"file:{data / 'village.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    for kind, table in (("turn", "computer_use_turns"), ("session", "computer_use_sessions")):
        for k, i in wanted:
            if k == kind:
                r = db.execute(f"SELECT * FROM {table} WHERE id = ?", (i,)).fetchone()
                if r:
                    found[(k, i)] = " ".join(str(v) for v in dict(r).values() if v is not None)
    stamps = {i for k, i in wanted if k == "transcript"}
    if stamps:
        t = json.load(open(data / "village-transcript.json"))
        for d in t["days"]:
            for e in d["events"]:
                if e.get("timestamp") in stamps:
                    found[("transcript", e["timestamp"])] = found.get(("transcript", e["timestamp"]), "") + json.dumps(e, ensure_ascii=False)
    return found


def check(data, report):
    cites = [(m.group(1), m.group(2), m.group(3))
             for b in BRACKET.finditer(Path(report).read_text())
             for m in ONE.finditer(b.group(1).strip())]
    found = load(Path(data), {(k, i) for k, i, _ in cites})
    result = Counter()
    failures = []
    for kind, rid, quote in cites:
        text = found.get((kind, rid))
        if text is None:
            status = "id_missing"
        elif not quote:
            status = "no_quote"
        else:
            # JSON escapes quotes and newlines; compare against both forms
            hay = norm(text) + " " + norm(text.encode().decode("unicode_escape", errors="ignore"))
            status = "ok" if norm(quote) in hay else "quote_missing"
        result[status] += 1
        result[f"{kind}:{status}"] += 1
        if status != "ok":
            failures.append({"kind": kind, "id": rid, "quote": quote, "status": status})
    return {"report": str(report), "citations": len(cites), "counts": dict(result), "failures": failures}


def main():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    p = argparse.ArgumentParser()
    p.add_argument("data")
    p.add_argument("reports", nargs="+")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    out = [check(a.data, r) for r in a.reports]
    if a.json:
        json.dump(out, sys.stdout, indent=1)
        return
    for r in out:
        c = r["counts"]
        print(f"{r['report']}: {r['citations']} citations; ok {c.get('ok', 0)}, id missing {c.get('id_missing', 0)}, "
              f"quote not found {c.get('quote_missing', 0)}, no quote {c.get('no_quote', 0)}")
        kinds = sorted({k.split(':')[0] for k in c if ':' in k})
        print("   by type:", ", ".join(f"{k} {c.get(k + ':ok', 0)}/{sum(v for kk, v in c.items() if kk.startswith(k + ':'))}" for k in kinds))
        for f in r["failures"][:8]:
            print(f"   {f['status']}: [{f['kind']}:{f['id'][:12]}…] \"{(f['quote'] or '')[:70]}\"")


if __name__ == "__main__":
    main()
