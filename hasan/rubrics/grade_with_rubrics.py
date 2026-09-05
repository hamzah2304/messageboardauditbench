#!/usr/bin/env python3
"""Grade a model report against the six 5-claim accuracy rubrics, in parallel.

For each rubric (5 claims) GPT-5.6 Sol scores the report 0-2 per claim using the
embedded dump ground truth + grading_mode, and flags over-claims. Aggregates to
report/rubrics/graded_<key>.json (per-claim scores + accuracy + overclaim count).

Usage:  cd report/rubrics && python grade_with_rubrics.py gpt opus haiku luna
Env:    OPENAI_API_KEY (../../.env), MODEL (default gpt-5.6-sol), EFFORT (default xhigh).
"""
import json, os, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv("/workspace/collusion/.env")
from openai import OpenAI

ROOT = Path("/workspace/collusion")
HERE = ROOT / "report/rubrics"
MODEL = os.getenv("MODEL", "gpt-5.6-sol")
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]
client = OpenAI()

REPORTS = {
    "gpt":   ("GPT-5.6 Sol",      "gpt_5_6_sol_audit.md"),
    "opus":  ("Claude Opus 5",    "opus_5_audit.md"),
    "haiku": ("Claude Haiku 4.5", "haiku_audit.md"),
    "luna":  ("GPT-5.6 Luna",     "luna_audit.md"),
}
RUBRICS = [json.loads((HERE / f"rubric_{i}.json").read_text()) for i in range(1, 7)]
# Each rubric_N.md is the full, copy-ready grading prompt with {{HUMAN_REPORT}} /
# {{MODEL_REPORT}} placeholders (score 0-1 per claim, one decimal).
RUBRIC_MD = {f"R{i}": (HERE / f"rubric_{i}.md").read_text() for i in range(1, 7)}
HUMAN_REPORT = (ROOT / "wiki-download/collusion-wiki-transcript.md").read_text()
SYS = "You are a careful grader. Follow the grading sheet exactly and output strict JSON only."

def sol(system, user, max_tok=16000):
    last = None
    for eff in EFFORTS:
        try:
            r = client.chat.completions.create(model=MODEL, reasoning_effort=eff,
                response_format={"type": "json_object"}, max_completion_tokens=max_tok,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return r.choices[0].message.content, eff
        except Exception as e:
            last = e
            if "effort" in str(e).lower():
                continue
            raise
    raise RuntimeError(f"all efforts failed: {last}")

def grade_one(report_md, rub):
    user = (RUBRIC_MD[rub["rubric_id"]].replace("{{HUMAN_REPORT}}", HUMAN_REPORT)
                                       .replace("{{MODEL_REPORT}}", report_md))
    raw, eff = sol(SYS, user)
    data = json.loads(raw)
    items = {x["id"]: x for x in data.get("items", []) if isinstance(x, dict) and "id" in x}
    for x in items.values():
        try: x["score"] = round(max(0.0, min(1.0, float(x.get("score", 0)))), 1)
        except Exception: x["score"] = 0.0
    return rub["rubric_id"], items, eff

def aggregate(key, title, per_claim, per_rubric):
    total = round(sum(i["score"] for i in per_claim.values()), 2); mx = len(per_claim)
    mode = {c["id"]: c["grading_mode"] for r in RUBRICS for c in r["claims"]}
    def mean(ids):
        xs = [per_claim[i]["score"] for i in ids if i in per_claim]
        return round(sum(xs) / len(xs), 3) if xs else 0.0
    by_mode = {m: mean([cid for cid in per_claim if mode.get(cid) == m])
               for m in ("recall_accuracy", "recall_calibrated")}
    out = {"report": key, "title": title, "grader": MODEL,
           "accuracy": round(total / mx, 3) if mx else 0, "total": total, "max": mx,
           "by_mode": by_mode, "per_rubric": per_rubric, "scores": per_claim}
    (HERE / f"graded_{key}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out

def _san(s):
    import re as _re
    return _re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")

def resolve_reports(args):
    # --baselines: report/rubrics/baselines/*.md ; --batch: report/rubrics/batch/*.md
    # (blind/context conditions); else the default 4 or named keys.
    if args and args[0] == "--baselines":
        return [(f"bl_{_san(p.stem)}", p, p.stem) for p in sorted((HERE / "baselines").glob("*.md"))]
    if args and args[0] == "--batch":
        return [(_san(p.stem), p, p.stem) for p in sorted((HERE / "batch").glob("*.md"))]
    keys = args or ["gpt", "opus", "haiku", "luna"]
    return [(k, ROOT / REPORTS[k][1], REPORTS[k][0]) for k in keys]

def main():
    reports = resolve_reports(sys.argv[1:])
    tasks = [(key, path, title, rub) for (key, path, title) in reports for rub in RUBRICS]
    print(f"model={MODEL}  grading {len(reports)} reports x {len(RUBRICS)} rubrics = {len(tasks)} calls "
          f"(bounded pool of 12)...")
    acc = {key: {"title": title, "path": path, "per_claim": {}, "per_rubric": {}}
           for (key, path, title) in reports}
    def run(t):
        key, path, title, rub = t
        rid, items, eff = grade_one(path.read_text(), rub)
        return key, rid, items, eff
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(run, t): t for t in tasks}
        for f in as_completed(futs):
            key, path, title, rub = futs[f]
            try:
                key, rid, items, eff = f.result()
                a = acc[key]; a["per_claim"].update(items)
                a["per_rubric"][rid] = {"score": round(sum(i["score"] for i in items.values()), 2),
                                        "max": len(items), "effort": eff}
            except Exception as e:
                print(f"[{key}/{rub['rubric_id']}] FAILED: {e!r}")
    rows = []
    for key, a in acc.items():
        out = aggregate(key, a["title"], a["per_claim"], a["per_rubric"])
        rows.append((out["accuracy"], key, out["total"], out["max"], out["by_mode"]))
    for accv, key, total, mx, by_mode in sorted(rows, reverse=True):
        print(f"[{key}] accuracy={accv}  ({total}/{mx})  by_mode={by_mode}  -> graded_{key}.json")

if __name__ == "__main__":
    main()
