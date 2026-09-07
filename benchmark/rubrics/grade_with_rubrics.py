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
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)
from dotenv import load_dotenv
load_dotenv(ENV_FILE)
from openai import OpenAI


# Two rubrics over the same 30 points: what the report found (0..1) and what it got
# wrong (-1..0). They are graded separately and never blended — a thin report scores
# well on contradiction precisely because it says little, and averaging the two would
# hide that.
_R = os.getenv("RUBRIC", "contra" if "--contra" in sys.argv else "v2" if "--v2" in sys.argv else "recall")
MODE = {"contra": "contradiction", "v2": "v2", "recall": "recall"}[_R]
# sheet-file prefix, how many sheets, and the score range each rubric is scored on
SHEET, N_SHEETS = {"recall": ("rubric", 6), "contradiction": ("contra", 6), "v2": ("v2", 8)}[MODE]
LO, HI = {"recall": (0.0, 1.0), "contradiction": (-1.0, 0.0), "v2": (0.0, 1.0)}[MODE]

DEFAULT_MODEL = "gpt-5.6-sol"
MODEL = os.getenv("MODEL", DEFAULT_MODEL)
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]
IS_ANTHROPIC = MODEL.startswith("claude")


def _san(s):
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")


# The default judge keeps writing to benchmark/graded/ (where every committed grade
# lives); any other judge gets its own namespace so the two never collide.
OUT_DIR = GRADED if MODEL == DEFAULT_MODEL else GRADED / f"judge_{_san(MODEL)}"
if MODE != "recall":
    OUT_DIR = OUT_DIR / MODE
OUT_DIR.mkdir(parents=True, exist_ok=True)

if IS_ANTHROPIC:
    import anthropic
    _WS = os.getenv("ANTHROPIC_WORKSPACE_ID")
    client = anthropic.Anthropic(max_retries=8, timeout=1800.0,
                                 default_headers={"anthropic-workspace-id": _WS} if _WS else None)
else:
    client = OpenAI()

REPORTS = {
    "gpt":   ("GPT-5.6 Sol",      "gpt_5_6_sol_audit.md"),
    "opus":  ("Claude Opus 5",    "opus_5_audit.md"),
    "haiku": ("Claude Haiku 4.5", "haiku_audit.md"),
    "luna":  ("GPT-5.6 Luna",     "luna_audit.md"),
}
_SET = {"recall": "rubric", "contradiction": "rubric", "v2": "v2"}[MODE]
RUBRIC_SETS = [json.loads((RUBRICS / f"{_SET}_{i}.json").read_text()) for i in range(1, N_SHEETS + 1)]
# Each rubric_N.md is the full, copy-ready grading prompt with {{HUMAN_REPORT}} /
# {{MODEL_REPORT}} placeholders (score 0-1 per claim, one decimal).
_PFX = "V" if MODE == "v2" else "R"
RUBRIC_MD = {f"{_PFX}{i}": (RUBRICS / f"{SHEET}_{i}.md").read_text() for i in range(1, N_SHEETS + 1)}
HUMAN_REPORT = (HUMAN_REPORT).read_text()
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

JSON_ONLY = ("\n\nIMPORTANT: return ONLY the JSON object itself — no prose before or "
             "after it, and no markdown code fences.")


def _extract_json(raw):
    """Anthropic gives no response_format guarantee; strip fences/prose around the object."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"```\s*$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(s[i:j + 1])
        except Exception:
            return None
    return None


def claude(system, prefix, suffix, max_tok=32000):
    """Anthropic judge. `prefix` (sheet + answer key) is identical for every report on
    a rubric, so it carries the cache breakpoint; the report goes in `suffix`."""
    eff = EFFORTS[0] if EFFORTS[0] in ("low", "medium", "high", "xhigh", "max") else "xhigh"
    with client.messages.stream(
            model=MODEL, max_tokens=max_tok,
            system=[{"type": "text", "text": system}],
            thinking={"type": "adaptive"},
            output_config={"effort": eff},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": suffix}]}]) as st:
        msg = st.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text"), eff


def grade_one(report_md, rub):
    tmpl = RUBRIC_MD[rub["rubric_id"]].replace("{{HUMAN_REPORT}}", HUMAN_REPORT)
    if IS_ANTHROPIC:
        pre, _, post = tmpl.partition("{{MODEL_REPORT}}")
        raw, eff = claude(SYS, pre, report_md + post)
        data = _extract_json(raw)
        if data is None:  # one retry, telling it to drop the wrapper
            raw, eff = claude(SYS, pre, report_md + post + JSON_ONLY)
            data = _extract_json(raw)
        if data is None:
            raise ValueError(f"unparseable JSON from {MODEL}: {raw[:200]!r}")
    else:
        raw, eff = sol(SYS, tmpl.replace("{{MODEL_REPORT}}", report_md))
        data = json.loads(raw)
    items = {x["id"]: x for x in data.get("items", []) if isinstance(x, dict) and "id" in x}
    for x in items.values():
        try: x["score"] = round(max(LO, min(HI, float(x.get("score", 0)))), 1)
        except Exception: x["score"] = 0.0
    return rub["rubric_id"], items, eff

def aggregate(key, title, per_claim, per_rubric):
    total = round(sum(i["score"] for i in per_claim.values()), 2); mx = len(per_claim)
    out = {"report": key, "title": title, "grader": MODEL, "rubric": MODE,
           "total": total, "max": mx, "per_rubric": per_rubric, "scores": per_claim}
    if MODE == "contradiction":
        hit = [i for i in per_claim.values() if i["score"] < 0]
        out["contradiction"] = round(total / mx, 3) if mx else 0
        out["n_contradicted"] = len(hit)
        out["worst"] = round(min([i["score"] for i in per_claim.values()] or [0]), 1)
    else:
        mode = {c["id"]: c.get("grading_mode", "recall_accuracy")
                for r in RUBRIC_SETS for c in r["claims"]}
        def mean(ids):
            xs = [per_claim[i]["score"] for i in ids if i in per_claim]
            return round(sum(xs) / len(xs), 3) if xs else 0.0
        out["accuracy"] = round(total / mx, 3) if mx else 0
        out["by_mode"] = {m: mean([cid for cid in per_claim if mode.get(cid) == m])
                          for m in ("recall_accuracy", "recall_calibrated")}
    (OUT_DIR / f"graded_{key}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out

def resolve_reports(args):
    # --dir <path>: grade every *.md in <path> (key = sanitized stem);
    # --baselines: benchmark/graded_inputs/seed_baselines/*.md
    # --batch:     benchmark/graded_inputs/blind_context/*.md
    # --dir NAME:  benchmark/graded_inputs/NAME/*.md   (e.g. --dir round2)
    # (blind/context conditions); else the default 4 or named keys.
    if args and args[0] == "--dir":
        d = Path(args[1]) if Path(args[1]).is_absolute() else (GRADED_INPUTS / args[1])
        return [(_san(p.stem), p, p.stem) for p in sorted(d.glob("*.md"))]
    if args and args[0] == "--baselines":
        return [(f"bl_{_san(p.stem)}", p, p.stem) for p in sorted((GRADED_INPUTS / "seed_baselines").glob("*.md"))]
    if args and args[0] == "--batch":
        return [(_san(p.stem), p, p.stem) for p in sorted((GRADED_INPUTS / "blind_context").glob("*.md"))]
    keys = args or ["gpt", "opus", "haiku", "luna"]
    return [(k, ROOT / REPORTS[k][1], REPORTS[k][0]) for k in keys]

def main():
    args = [a for a in sys.argv[1:] if a not in ("--force", "--contra", "--v2")]
    reports = resolve_reports(args)
    if "--force" not in sys.argv[1:]:  # skip reports already graded (fill gaps only)
        reports = [r for r in reports if not (OUT_DIR / f"graded_{r[0]}.json").exists()]
    if not reports:
        print("nothing to do (all graded; pass --force to regrade)"); return
    tasks = [(key, path, title, rub) for (key, path, title) in reports for rub in RUBRIC_SETS]
    print(f"model={MODEL}  rubric={MODE}  grading {len(reports)} reports x {len(RUBRIC_SETS)} rubrics = {len(tasks)} calls "
          f"(bounded pool of 12) -> {OUT_DIR}", flush=True)
    acc = {key: {"title": title, "path": path, "per_claim": {}, "per_rubric": {}}
           for (key, path, title) in reports}
    def run(t):
        key, path, title, rub = t
        rid, items, eff = grade_one(path.read_text(), rub)
        return key, rid, items, eff
    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(run, t): t for t in tasks}
        for f in as_completed(futs):
            key, path, title, rub = futs[f]
            done += 1
            try:
                key, rid, items, eff = f.result()
                a = acc[key]; a["per_claim"].update(items)
                a["per_rubric"][rid] = {"score": round(sum(i["score"] for i in items.values()), 2),
                                        "max": len(items), "effort": eff}
                print(f"  .. {done}/{len(tasks)} {key}/{rid} ok ({len(items)} claims)", flush=True)
            except Exception as e:
                print(f"[{key}/{rub['rubric_id']}] FAILED: {e!r}", flush=True)
    rows = []
    for key, a in acc.items():
        out = aggregate(key, a["title"], a["per_claim"], a["per_rubric"])
        rows.append((out.get("accuracy", out.get("contradiction")), key,
                     out["total"], out["max"], out.get("by_mode"), out.get("n_contradicted")))
    for v, key, total, mx, by_mode, nc in sorted(rows, reverse=True):
        if MODE == "contradiction":
            print(f"[{key}] contradiction={v}  total {total} over {mx} points, {nc} contradicted"
                  f"  -> graded_{key}.json", flush=True)
        else:
            print(f"[{key}] accuracy={v}  ({total}/{mx})  by_mode={by_mode}  -> graded_{key}.json", flush=True)

if __name__ == "__main__":
    main()
