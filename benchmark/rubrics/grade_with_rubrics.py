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
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2] / "scripts"))
from extract_tldr import extract as extract_tldr  # noqa: F401  (used via core)
from messageboard_audit_bench.grading import core
from dotenv import load_dotenv
load_dotenv(ENV_FILE)
from openai import OpenAI


# Two rubrics over the same 30 points: what the report found (0..1) and what it got
# wrong (-1..0). They are graded separately and never blended — a thin report scores
# well on contradiction precisely because it says little, and averaging the two would
# hide that.
#
# The mode table, the prompt, the parsing, the arithmetic and the output path all live in
# messageboard_audit_bench.grading.core, which the Inspect scorer imports too. This script
# keeps its CLI, its thread pool and its provider clients; it no longer keeps its own
# definition of what a grade is, so the two paths cannot drift.
_R = os.getenv("RUBRIC", "contra" if "--contra" in sys.argv else "v2" if "--v2" in sys.argv
                else "tldrh" if "--tldrh" in sys.argv else "recall")
MODE = {"contra": "contradiction", "v2": "v2", "recall": "recall",
        "tldr": "tldr", "tldrh": "tldrh"}[_R]
SPEC = core.MODES[MODE]
LO, HI = SPEC.lo, SPEC.hi
# --variant anthropic (or RUBRIC_VARIANT=anthropic): grade reports written against the
# verbatim_anthropic data with the swapped sheets and answer key (see
# build_rubrics_anthropic.py). Grades land under a variant_<name>/ subdirectory.
def _variant_arg():
    if "--variant" in sys.argv:
        return sys.argv[sys.argv.index("--variant") + 1]
    return os.getenv("RUBRIC_VARIANT") or None
VARIANT = _variant_arg()

DEFAULT_MODEL = core.DEFAULT_JUDGE
MODEL = os.getenv("MODEL", DEFAULT_MODEL)
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]
WORKERS = int(os.getenv("WORKERS", "12"))   # sheet calls in flight at once
IS_ANTHROPIC = MODEL.startswith("claude")


_san = core.sanitise

OUT_DIR = core.out_dir(MODEL, MODE, VARIANT)
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
# Each sheet's .md is the full, copy-ready grading prompt with {{HUMAN_REPORT}} /
# {{MODEL_REPORT}} placeholders (score 0-1 per claim, one decimal); the .json is the
# machine-readable claim set.
RUBRIC_SETS, RUBRIC_MD = core.load_sheets(MODE, VARIANT)
SYS = core.SYSTEM

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

JSON_ONLY = core.JSON_ONLY
_extract_json = core.extract_json


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
    """One sheet against one report. `core.build_prompt` decides what the judge sees.

    The Anthropic path sends the prefix and suffix as two blocks so the sheet carries the
    cache breakpoint; the OpenAI path concatenates them into one message. Either way the
    bytes are the same, which is what tests/test_grading_prompt_parity.py pins down.
    """
    system, prefix, suffix = core.build_prompt(MODE, rub["rubric_id"], report_md, RUBRIC_MD, VARIANT)
    if IS_ANTHROPIC:
        raw, eff = claude(system, prefix, suffix)
        data = _extract_json(raw)
        if data is None:  # one retry, telling it to drop the wrapper
            raw, eff = claude(system, prefix, suffix + JSON_ONLY)
            data = _extract_json(raw)
        if data is None:
            raise ValueError(f"unparseable JSON from {MODEL}: {raw[:200]!r}")
    else:
        raw, eff = sol(system, prefix + suffix)
        data = json.loads(raw)
    return rub["rubric_id"], core.parse_items(data, LO, HI), eff

def aggregate(key, title, per_claim, per_rubric):
    out = core.aggregate(key, title, MODEL, MODE, per_claim, per_rubric, RUBRIC_SETS)
    if out["max"] == 0:
        # Every call for this report failed (an auth or billing error hits all of them at
        # once). Writing the file anyway records a total of 0 that is indistinguishable
        # from a report that genuinely scored nothing, and the resume path then skips it
        # forever.
        print(f"[{key}] no claims came back — not writing a grade file", flush=True)
        return out
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
    args = [a for a in sys.argv[1:] if a not in ("--force", "--contra", "--v2", "--tldrh")]
    if "--variant" in args:
        i = args.index("--variant"); del args[i:i + 2]
    reports = resolve_reports(args)
    if "--force" not in sys.argv[1:]:  # skip reports already graded (fill gaps only)
        reports = [r for r in reports if not (OUT_DIR / f"graded_{r[0]}.json").exists()]
    if not reports:
        print("nothing to do (all graded; pass --force to regrade)"); return
    tasks = [(key, path, title, rub) for (key, path, title) in reports for rub in RUBRIC_SETS]
    print(f"model={MODEL}  rubric={MODE}  variant={VARIANT}  grading {len(reports)} reports x {len(RUBRIC_SETS)} rubrics = {len(tasks)} calls "
          f"(bounded pool of {WORKERS}) -> {OUT_DIR}", flush=True)
    acc = {key: {"title": title, "path": path, "per_claim": {}, "per_rubric": {}}
           for (key, path, title) in reports}
    def run(t):
        key, path, title, rub = t
        rid, items, eff = grade_one(path.read_text(), rub)
        return key, rid, items, eff
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
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
        if out["max"] == 0:      # nothing came back; there is no row to print or sort
            continue
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
