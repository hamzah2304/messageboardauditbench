#!/usr/bin/env python3
"""Precision grade (1-10): GPT-5.6 Sol compares each model report against the
human report and counts contradicted statements. Uses precision_prompt.md.

Usage:  python precision_grade.py --batch          (report/rubrics/batch/*.md)
        python precision_grade.py --baselines      (report/rubrics/baselines/*.md)
        python precision_grade.py gpt opus haiku luna
Writes report/rubrics/precision_<key>.json ; env OPENAI_API_KEY, MODEL, EFFORT.
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
PROMPT = (HERE / "precision_prompt.md").read_text()
HUMAN = (ROOT / "wiki-download/collusion-wiki-transcript.md").read_text()
SYS = "You are a careful fact-checker. Follow the instructions and output strict JSON only."
REPORTS = {"gpt": ("GPT-5.6 Sol", "gpt_5_6_sol_audit.md"), "opus": ("Claude Opus 5", "opus_5_audit.md"),
           "haiku": ("Claude Haiku 4.5", "haiku_audit.md"), "luna": ("GPT-5.6 Luna", "luna_audit.md")}

def _san(s): return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")

def resolve(args):
    if args and args[0] == "--batch":
        return [(_san(p.stem), p) for p in sorted((HERE / "batch").glob("*.md"))]
    if args and args[0] == "--baselines":
        return [(f"bl_{_san(p.stem)}", p) for p in sorted((HERE / "baselines").glob("*.md"))]
    return [(k, ROOT / REPORTS[k][1]) for k in (args or list(REPORTS))]

def sol(user, max_tok=48000):
    last = None
    for eff in EFFORTS:
        try:
            r = client.chat.completions.create(model=MODEL, reasoning_effort=eff,
                response_format={"type": "json_object"}, max_completion_tokens=max_tok,
                messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}])
            content = r.choices[0].message.content
            if content and content.strip():
                return content, eff
            last = RuntimeError(f"empty content at effort={eff} (finish={r.choices[0].finish_reason})")
            continue  # empty (reasoning exhausted the budget) -> retry at lower effort
        except Exception as e:
            last = e
            if "effort" in str(e).lower(): continue
            raise
    raise RuntimeError(f"all efforts failed: {last}")

def grade(key, path):
    user = PROMPT.replace("{{HUMAN_REPORT}}", HUMAN).replace("{{MODEL_REPORT}}", path.read_text())
    raw, eff = sol(user)
    d = json.loads(raw)
    try: d["precision"] = round(max(1.0, min(10.0, float(d.get("precision", 1)))), 1)
    except Exception: d["precision"] = 1.0
    d["n_contradictions"] = int(d.get("n_contradictions", len(d.get("contradictions", []))) or 0)
    d.update({"_report": key, "_grader": MODEL, "_effort": eff})
    (HERE / f"precision_{key}.json").write_text(json.dumps(d, indent=1, ensure_ascii=False))
    return key, d["precision"], d["n_contradictions"]

def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    reports = resolve(args)
    if "--force" not in sys.argv[1:]:  # skip reports already graded
        reports = [(k, p) for (k, p) in reports if not (HERE / f"precision_{k}.json").exists()]
    if not reports:
        print("nothing to do (all graded; pass --force to regrade)"); return
    print(f"model={MODEL}  precision-grading {len(reports)} reports in parallel...")
    with ThreadPoolExecutor(max_workers=min(12, len(reports))) as ex:
        futs = {ex.submit(grade, k, p): k for k, p in reports}
        rows = []
        for f in as_completed(futs):
            try: rows.append(f.result())
            except Exception as e: print(f"[{futs[f]}] FAILED: {e!r}")
    for key, prec, nc in sorted(rows, key=lambda r: -r[1]):
        print(f"[{key}] precision={prec}/10  contradictions={nc}  -> precision_{key}.json")

if __name__ == "__main__":
    main()
