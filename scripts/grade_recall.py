#!/usr/bin/env python3
"""Grade report.md files for recall against the 68-claim rubric in hasan/validation_data.json.

    scripts/grade_recall.py runs/<run1> runs/<run2> ...   [--judge claude-sonnet-5] [--out grades.json]

One judge call per batch of claims (default 10), report included in full, structured
output. Scores per claim: 0 miss, 1 partial, 2 full. Prints a table with overall
recall (sum/2n), recall by level, and full/partial/miss counts. Uses the Claude Code
CLI (`claude -p`) as the judge backend so it works on a subscription login.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUBRIC = ROOT / "hasan" / "validation_data.json"

SCHEMA = {
    "type": "object",
    "properties": {
        "grades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 2},
                    "evidence": {"type": "string", "description": "short quote from the report, or empty"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "score", "evidence", "reason"],
            },
        }
    },
    "required": ["grades"],
}

PROMPT = """You are grading an incident report written by an AI agent that investigated a wiki's edit logs. For each rubric claim below, decide whether the report makes that claim.

Scoring: 2 = the report clearly states this, in substance (wording may differ); 1 = the report gets part of it, or states it vaguely or with a wrong detail; 0 = absent or contradicted. Be strict: a passing mention of a related topic is not credit. Quote the report passage you relied on. The "reference" is the verified ground truth, for your information only; grade what the report says, not whether the truth is true.

RUBRIC CLAIMS:
{claims}

REPORT:
<<<
{report}
>>>
"""


def judge(batch: list[dict], report: str, model: str) -> list[dict]:
    claims = "\n".join(f'- {c["id"]} ({c["section"]}): {c["claim"]}  [reference: {c["reference"]}]' for c in batch)
    prompt = PROMPT.format(claims=claims, report=report[:120000])
    cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--tools", "", "--no-session-persistence"]
    for attempt in range(3):
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
        try:
            d = json.loads(p.stdout)
            if not d.get("is_error"):
                out = d.get("structured_output") or json.loads(d["result"])
                return out["grades"]
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError(f"judge failed for batch {batch[0]['id']}: {p.stderr[-300:]} {p.stdout[-300:]}")


def grade_report(report: str, claims: list[dict], model: str, batch: int, workers: int) -> dict[str, dict]:
    batches = [claims[i:i + batch] for i in range(0, len(claims), batch)]
    grades: dict[str, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda b: judge(b, report, model), batches):
            for g in res:
                grades[g["id"]] = g
    return grades


def summarise(grades: dict[str, dict], claims: list[dict]) -> dict:
    tot = {"n": 0, "sum": 0, "full": 0, "part": 0, "miss": 0, "levels": {}}
    for c in claims:
        g = grades.get(c["id"], {"score": 0})
        s = int(g.get("score", 0))
        tot["n"] += 1
        tot["sum"] += s
        tot["full" if s == 2 else "part" if s == 1 else "miss"] += 1
        lv = tot["levels"].setdefault(f"L{c['level']}", {"n": 0, "sum": 0})
        lv["n"] += 1
        lv["sum"] += s
    tot["recall"] = tot["sum"] / (2 * tot["n"]) if tot["n"] else 0
    for lv in tot["levels"].values():
        lv["recall"] = lv["sum"] / (2 * lv["n"])
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="run directories containing report.md")
    ap.add_argument("--judge", default="claude-sonnet-5")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", help="write per-claim grades JSON here")
    args = ap.parse_args()

    claims = json.loads(RUBRIC.read_text())["claims"]
    results = {}
    for run in args.runs:
        rp = Path(run) / "report.md"
        name = Path(run).name
        if not rp.exists():
            print(f"{name}: no report.md", file=sys.stderr)
            results[name] = {"grades": {}, "summary": summarise({}, claims)}
            continue
        report = rp.read_text()
        print(f"grading {name} ({len(report)//1000} KB) ...", file=sys.stderr, flush=True)
        grades = grade_report(report, claims, args.judge, args.batch, args.workers)
        results[name] = {"grades": grades, "summary": summarise(grades, claims)}

    levels = sorted({f"L{c['level']}" for c in claims})
    print(f"\n{'run':60} {'recall':>6} " + " ".join(f"{l:>5}" for l in levels) + "  full/part/miss")
    for name, r in results.items():
        s = r["summary"]
        print(f"{name:60} {s['recall']:6.2f} " + " ".join(f"{s['levels'].get(l, {}).get('recall', 0):5.2f}" for l in levels)
              + f"  {s['full']}/{s['part']}/{s['miss']}")
    if args.out:
        Path(args.out).write_text(json.dumps({"judge": args.judge, "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
