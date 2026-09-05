#!/usr/bin/env python3
"""
Have GPT-5.6 Sol grade one or more model reports on all three axes, in parallel:
  recall     -> per-claim 0/1/2 vs the 68-claim rubric  -> ../reports/<key>.scores.json
  precision  -> 1-10 truthfulness + flagged errors       -> snippets/precision_<key>.json
  snippets   -> per-claim verbatim passage for the UI    -> snippets/<key>.json

Usage:  python benchmark/legacy_68claim/grade_reports.py haiku luna   (default: haiku luna)
NOTE: superseded by benchmark/rubrics/grade_with_rubrics.py. Also needs an external
collusion_eval/rubric_grader.py, which is not in this repo.
Env:    OPENAI_API_KEY (from ../../.env), MODEL (default gpt-5.6-sol), EFFORT (default xhigh).
"""
import json, os, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv(ENV_FILE)
from openai import OpenAI


sys.path.insert(0, os.environ.get("COLLUSION_EVAL_DIR", "collusion_eval"))  # external: rubric_grader.py + rubric.json
import rubric_grader as rg

import os, sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)


MODEL = os.getenv("MODEL", "gpt-5.6-sol")
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]
client = OpenAI()

REPORTS = {
    "gpt":   ("GPT-5.6 Sol",     "gpt_5_6_sol_audit.md"),
    "opus":  ("Claude Opus 5",   "opus_5_audit.md"),
    "haiku": ("Claude Haiku 4.5", "haiku_audit.md"),
    "luna":  ("GPT-5.6 Luna",    "luna_audit.md"),
}

claims = json.loads((CLAIMS / "claims.json").read_text())["claims"]
CLAIMS_BLOCK = "\n".join(f'{c["id"]}: {c["claim"]}  [reference: {c["dump_check"]}]' for c in claims)
FACTS = "\n".join(f'- {c["id"]}: {c["claim"]}  ({c["dump_check"]})' for c in claims)
HUMAN = (HUMAN_REPORT).read_text()


def split_prompt(md_text):
    body = re.sub(r"^# .*\n", "", md_text, count=1).strip()
    s, u = re.split(r"\nUSER:\n", body, maxsplit=1)
    return re.sub(r"^SYSTEM:\n", "", s).strip(), u.strip()


def sol(system, user, json_obj=True, max_tok=48000):
    last = None
    for eff in EFFORTS:
        try:
            kw = dict(model=MODEL, reasoning_effort=eff, max_completion_tokens=max_tok,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            if json_obj:
                kw["response_format"] = {"type": "json_object"}
            r = client.chat.completions.create(**kw)
            return r.choices[0].message.content, eff
        except Exception as e:
            last = e
            if "effort" in str(e).lower():
                continue
            raise
    raise RuntimeError(f"all efforts failed: {last}")


def grade_recall(key):
    title, fn = REPORTS[key]
    system, prompt = rg.build_messages((ROOT / fn).read_text())
    prompt += '\n\nReturn a JSON object {"items": [ ... ]} whose array is exactly the per-claim records above.'
    raw, eff = sol(system, prompt)
    data = json.loads(raw)
    arr = data.get("items") or data.get("claims") or (data if isinstance(data, list) else [])
    scored = {}
    for r in arr:
        if isinstance(r, dict) and "id" in r:
            try:
                r["score"] = max(0, min(2, int(r.get("score", 0))))
            except Exception:
                r["score"] = 0
            r["evidence_cited"] = bool(r.get("evidence_cited", False))
            scored[r["id"]] = r
    summary = rg.aggregate(scored)
    (ROOT / "reports" / f"{key}.scores.json").write_text(
        json.dumps({"report": key, "grader": MODEL, "effort": eff, "summary": summary, "scores": scored},
                   indent=1, ensure_ascii=False))
    return key, "recall", summary["recall"], eff


def grade_snippets(key):
    title, fn = REPORTS[key]
    md = (PROMPTS / "model_report_gpt.md").read_text().replace(
        "the GPT-5.6 Sol report under evaluation", f"the {title} report under evaluation")
    system, tmpl = split_prompt(md)
    user = tmpl.replace("{{CLAIMS}}", CLAIMS_BLOCK).replace("{{DOC}}", (ROOT / fn).read_text())
    raw, eff = sol(system, user)
    data = json.loads(raw)
    arr = data.get("claims", data if isinstance(data, list) else [])
    byid = {r["id"]: r for r in arr if isinstance(r, dict) and "id" in r}
    (SNIPPETS / f"{key}.json").write_text(
        json.dumps({"model": MODEL, "effort": eff, "doc": key, "claims": byid}, indent=1, ensure_ascii=False))
    return key, "snippets", sum(1 for r in byid.values() if r.get("present")), eff


def grade_precision(key):
    title, fn = REPORTS[key]
    system, tmpl = split_prompt((PROMPTS / "precision_grader.md").read_text())
    user = tmpl.replace("{{FACTS}}", FACTS).replace("{{HUMAN}}", HUMAN).replace("{{DOC}}", (ROOT / fn).read_text())
    raw, eff = sol(system, user, max_tok=32000)
    data = json.loads(raw)
    data.update({"_model": MODEL, "_effort": eff, "_report": key})
    (SNIPPETS / f"precision_{key}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return key, "precision", data.get("precision_score"), eff


def main():
    keys = sys.argv[1:] or ["haiku", "luna"]
    for k in keys:
        assert k in REPORTS, f"unknown report key {k}"
    (SNIPPETS).mkdir(exist_ok=True)
    (ROOT / "reports").mkdir(exist_ok=True)
    jobs = []
    for k in keys:
        jobs += [(grade_recall, k), (grade_snippets, k), (grade_precision, k)]
    print(f"model={MODEL} efforts={EFFORTS}  grading {keys} on 3 axes ({len(jobs)} calls in parallel)...")
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futs = {ex.submit(fn, k): (fn.__name__, k) for fn, k in jobs}
        for f in as_completed(futs):
            name, k = futs[f]
            try:
                key, axis, val, eff = f.result()
                print(f"[{key}/{axis}] ok: {val}  (effort={eff})")
            except Exception as e:
                print(f"[{k}/{name}] FAILED: {e!r}")
    print("done.")


if __name__ == "__main__":
    main()
