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
# The markdown judge sheet is the source of truth the grader actually reads (rubric_N.md).
RUBRIC_MD = {f"R{i}": (HERE / f"rubric_{i}.md").read_text() for i in range(1, 7)}
# The human incident report is given to the grader in-context as the answer key.
HUMAN_REPORT = (ROOT / "wiki-download/collusion-wiki-transcript.md").read_text()

def split_prompt(md):
    body = re.sub(r"^# .*\n", "", md, count=1).strip()
    s, u = re.split(r"\nUSER:\n", body, maxsplit=1)
    return re.sub(r"^SYSTEM:\n", "", s).strip(), u.strip()

SYS, USER_TMPL = split_prompt((HERE / "GRADER_PROMPT.md").read_text())

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
    user = (USER_TMPL.replace("{{HUMAN_REPORT}}", HUMAN_REPORT)
                     .replace("{{RUBRIC}}", RUBRIC_MD[rub["rubric_id"]])
                     .replace("{{REPORT}}", report_md))
    raw, eff = sol(SYS, user)
    data = json.loads(raw)
    items = {x["id"]: x for x in data.get("items", []) if isinstance(x, dict) and "id" in x}
    for x in items.values():
        try: x["score"] = max(0, min(2, int(x.get("score", 0))))
        except Exception: x["score"] = 0
    return rub["rubric_id"], items, eff

def grade_report(key):
    title, fn = REPORTS[key]
    report_md = (ROOT / fn).read_text()
    per_claim, per_rubric = {}, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(grade_one, report_md, r): r["rubric_id"] for r in RUBRICS}
        for f in as_completed(futs):
            rid, items, eff = f.result()
            per_claim.update(items)
            got = sum(i["score"] for i in items.values()); mx = 2 * len(items)
            per_rubric[rid] = {"score": got, "max": mx, "n_overclaims": sum(1 for i in items.values() if i.get("overclaimed")), "effort": eff}
    total = sum(i["score"] for i in per_claim.values()); mx = 2 * len(per_claim)
    # doc's headline metric: recall on derivable/partial claims - 0.5 * overclaim-rate on not-derivable ones
    mode = {c["id"]: c["grading_mode"] for r in RUBRICS for c in r["claims"]}
    deriv = [i for cid, i in per_claim.items() if mode.get(cid) in ("recall_accuracy", "recall_calibrated")]
    notd = [(cid, i) for cid, i in per_claim.items() if mode.get(cid) == "calibration"]
    recall = round(sum(i["score"] for i in deriv) / (2 * len(deriv)), 3) if deriv else 0.0
    oc_rate = round(sum(1 for _, i in notd if i.get("overclaimed")) / len(notd), 3) if notd else 0.0
    out = {"report": key, "title": title, "grader": MODEL,
           "accuracy": round(total / mx, 3) if mx else 0, "total": total, "max": mx,
           "recall_derivable": recall, "overclaim_rate": oc_rate,
           "headline": round(recall - 0.5 * oc_rate, 3),
           "n_overclaims": sum(1 for i in per_claim.values() if i.get("overclaimed")),
           "per_rubric": per_rubric, "scores": per_claim}
    (HERE / f"graded_{key}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return key, out["accuracy"], out["headline"], out["max"], out["n_overclaims"]

def main():
    keys = sys.argv[1:] or ["gpt", "opus", "haiku", "luna"]
    for k in keys: assert k in REPORTS, f"unknown report key {k}"
    print(f"model={MODEL}  grading {keys} against 6 rubrics x 5 claims each...")
    for k in keys:
        key, acc, headline, mx, oc = grade_report(k)
        print(f"[{key}] accuracy={acc}  headline(recall-0.5*oc)={headline}  overclaims={oc}  -> graded_{key}.json")

if __name__ == "__main__":
    main()
