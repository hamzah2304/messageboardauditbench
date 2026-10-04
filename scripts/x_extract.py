#!/usr/bin/env python3
"""Extract findings from screened AI Digest X posts with GPT-6.1 Sol.

Mirrors the Discord extraction run (runs/discord-extraction-concrete-20261004):
same model and effort, and the same JSON transport so the findings-review UI
can show the result. Each post's result is cached as <post id>.json in the run
directory; a raw response without a result stops the run for inspection.

    uv run python scripts/x_extract.py runs/x-extraction-sample-YYYYMMDD [--dry-run]

The run directory must hold sample-posts.json (rows from x_screen.py decisions).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "benchmark/incidents/aivillage/x-findings-prompt.md"
MODEL = "gpt-6.1-sol"
EFFORT = "high"
MAX_OUTPUT = 12000
# USD per token: input, cached input, output (https://developers.openai.com/api/docs/models/gpt-6.1-sol).
RATES = (2e-6, 0.1e-6, 10e-6)
PREFILTER_CONTEXT = (
    "AI Digest X export (446 posts). Posts with no text or dated before 2 April 2025 were dropped in code; "
    "GPT-6 Luna (low reasoning) then screened the rest with an earlier, more permissive version of this "
    "prompt that kept concrete behaviors, not only failures. It has not been rerun with the failure criteria. "
    "Screening rationales are not supplied as evidence."
)
TRANSPORT = """
Transport instruction: preserve the extraction criteria above, but serialize the
requested Markdown content as one JSON object so the existing review UI can display it.
Use this structure (include all fields; empty lists/strings when unnecessary):
{
 "source": {"title": "...", "url": "...", "source_type": "x", "coverage": "..."},
 "findings": [{"id": "F1", "headline": "...", "finding": "...", "notes": [],
  "subfindings": [{"id": "F1.1", "claim": "...", "notes": [],
   "source_support": [{"quote": "exact contiguous quote from the post text",
    "location": "author handle, post date and thread part (part 1, part 2, ...)",
    "url": "exact supplied post URL", "message_id": "exact supplied post ID",
    "source_kind": "organizer account|agent statement",
    "image_number": null, "image_url": null, "record_links": []}],
   "media_dependence": "...",
   "log_evidence": "not yet verified", "evidence_note": "..."}]}],
 "excluded_source_claims": [{"claim": "...", "reason": "..."}],
 "source_limits": []
}
Thread parts are separated by a line containing only ---; part 1 is the first.
Quotes must be verbatim contiguous substrings of the post text, within one part,
without invented ellipsis, spelling fixes or normalization. Preserve the URL and
ID exactly. No screenshot, video or linked-page contents have been supplied.
Frozen logs have not been provided: all log evidence stays not yet verified.
No external tools are available. Do not add a finding to meet a quota; an empty
findings list is allowed.
"""


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def body(post, prompt):
    instructions = prompt.replace("{{TASK_STAGE}}", "extract").replace("{{PREFILTER_CONTEXT}}", PREFILTER_CONTEXT)
    instructions = instructions.replace("{{SOURCE_TEXT}}", "Supplied as JSON in the user input.")
    source = {k: post[k] for k in ("id", "date", "url", "author", "text")}
    return {"model": MODEL, "reasoning": {"effort": EFFORT}, "instructions": instructions + TRANSPORT,
            "input": [{"role": "user", "content": "X post for JSON extraction:\n" + json.dumps(source, ensure_ascii=False)}],
            "text": {"format": {"type": "json_object"}}, "max_output_tokens": MAX_OUTPUT,
            "service_tier": "default", "store": False}


def validate(data, post):
    issues, ids = [], set()
    for f in data["findings"]:
        if f["id"] in ids:
            issues.append("Duplicate finding ID " + f["id"])
        ids.add(f["id"])
        for sf in f["subfindings"]:
            if sf["id"] in ids or not sf["id"].startswith(f["id"] + "."):
                issues.append("Invalid subfinding ID " + sf["id"])
            ids.add(sf["id"])
            if sf["log_evidence"] != "not yet verified":
                issues.append(sf["id"] + ": invented log verification")
            if not sf["source_support"]:
                issues.append(sf["id"] + ": missing source support")
            for s in sf["source_support"]:
                if s.get("message_id") != post["id"] or s.get("url") != post["url"]:
                    issues.append(sf["id"] + ": unknown post ID or URL")
                elif not s["quote"] or s["quote"] not in post["text"]:
                    issues.append(sf["id"] + ": quote is not verbatim")
                if s.get("image_number") is not None or s.get("image_url") is not None:
                    issues.append(sf["id"] + ": claims unseen image evidence")
    return issues


def extract(run, post, prompt):
    target = run / f"{post['id']}.json"
    if target.exists():
        return json.loads(target.read_text())
    request = body(post, prompt)
    dump(run / f"{post['id']}.request.json", request)
    raw = run / f"{post['id']}.response.json"
    if raw.exists():
        raise RuntimeError(f"Raw response exists for {post['id']}; inspect it before retrying")
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0, timeout=600)
    response = client.responses.create(**request)
    dump(raw, response.model_dump(mode="json"))
    if response.status != "completed":
        raise RuntimeError(f"Incomplete response for {post['id']}")
    data = json.loads(response.output_text)
    issues = validate(data, post)
    data["run"] = {"model": MODEL, "reasoning": {"effort": EFFORT},
                   "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "response_id": response.id,
                   "usage": response.usage.model_dump(mode="json"), "validation_issues": issues}
    dump(target, data)
    print(json.dumps({"post": post["id"], "findings": len(data["findings"]), "issues": issues}), flush=True)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run = ROOT / args.run
    prompt = PROMPT_PATH.read_text()
    (run / "extraction-prompt.md").write_text(prompt)
    (run / "transport-instruction.txt").write_text(TRANSPORT)
    posts = json.loads((run / "sample-posts.json").read_text())
    # Upper bound: UTF-8 bytes as tokens plus overhead, full output budget.
    upper = sum((len(json.dumps(body(p, prompt)).encode()) + 8192) * RATES[0] + MAX_OUTPUT * RATES[2] for p in posts)
    dump(run / "run-plan.json", {"model": MODEL, "effort": EFFORT, "calls": len(posts),
                                 "max_output_tokens_per_call": MAX_OUTPUT, "cost_upper_usd": round(upper, 3)})
    print(f"{len(posts)} calls; cost upper bound ${upper:.2f}")
    if args.dry_run:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: extract(run, p, prompt), posts))
    usage = [r["run"]["usage"] for r in results]
    inp = sum(u["input_tokens"] for u in usage)
    cached = sum((u.get("input_tokens_details") or {}).get("cached_tokens", 0) for u in usage)
    out = sum(u["output_tokens"] for u in usage)
    summary = {"model": MODEL, "reasoning_effort": EFFORT, "posts": len(posts),
               "findings": sum(len(r["findings"]) for r in results),
               "subfindings": sum(len(f["subfindings"]) for r in results for f in r["findings"]),
               "posts_without_findings": sum(not r["findings"] for r in results),
               "validation_issues": [i for r in results for i in r["run"]["validation_issues"]],
               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "cost_usd": round((inp - cached) * RATES[0] + cached * RATES[1] + out * RATES[2], 3)}
    dump(run / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
