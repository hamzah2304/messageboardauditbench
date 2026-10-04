#!/usr/bin/env python3
"""Screen AI Digest X posts for findings leads with GPT-6 Luna.

Drops empty and pre-Village posts in code, then asks Luna for keep/drop on the
rest using the screening stage of the X findings prompt. Responses are cached
per batch under the run directory, so a rerun only pays for missing batches.

    uv run python scripts/x_screen.py [--run runs/x-screen-YYYYMMDD] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# data/ is shared from the primary checkout, which worktrees do not fully link.
PRIMARY = Path(subprocess.check_output(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                       cwd=ROOT, text=True).strip()).parent
CSV = PRIMARY / "data/aivillage/aidigest-posts-with-x-stats.csv"
PROMPT = ROOT / "benchmark/incidents/aivillage/x-findings-prompt.md"
MODEL = "gpt-6-luna"
REASONING = "low"
INPUT_RATE, OUTPUT_RATE = 0.10 / 1e6, 0.50 / 1e6
BATCH = 15
VILLAGE_START, VILLAGE_END = "2025-04-02", "2026-09-21"
PREFILTER_CONTEXT = (
    "Every post from the AI Digest export, minus posts with no text and posts dated before "
    "the Village launched (2 April 2025). No earlier model screening."
)


def load_posts():
    rows = list(csv.DictReader(CSV.open(newline="")))
    posts, skipped = [], []
    for r in rows:
        pid = r["x_url"].rsplit("/", 1)[-1] if r["x_url"] else f"typefully-{r['typefully_id']}"
        post = {"id": pid, "date": r["published_at"][:10], "url": r["x_url"],
                "author": r["x_url"].split("/")[3] if r["x_url"] else "unknown", "text": r["x_text"]}
        if not r["x_text"].strip():
            skipped.append({**post, "decision": "drop", "behavior": "no text", "stage": "code"})
        elif r["published_at"] < VILLAGE_START:
            skipped.append({**post, "decision": "drop", "behavior": "before the Village launched", "stage": "code"})
        else:
            posts.append(post)
    posts.sort(key=lambda p: p["date"])
    return posts, skipped


def system_prompt():
    text = PROMPT.read_text()
    text = text.replace("{{TASK_STAGE}}", "screen").replace("{{PREFILTER_CONTEXT}}", PREFILTER_CONTEXT)
    text = text.replace("{{SOURCE_TEXT}}", "Supplied in the user message as JSON: a list of posts.")
    return text + (
        "\n\nReturn only JSON matching the schema, with exactly one decision for every supplied post, "
        "in order, using the supplied post IDs. Posts are separate; do not combine their evidence."
    )


def request(posts):
    item = {"type": "object", "additionalProperties": False,
            "required": ["id", "decision", "behavior", "agents"],
            "properties": {"id": {"type": "string"}, "decision": {"type": "string", "enum": ["keep", "drop"]},
                           "behavior": {"type": "string"}, "agents": {"type": "array", "items": {"type": "string"}}}}
    schema = {"type": "object", "additionalProperties": False, "required": ["decisions"],
              "properties": {"decisions": {"type": "array", "items": item}}}
    user = [{k: p[k] for k in ("id", "date", "author", "text")} for p in posts]
    return {"model": MODEL, "reasoning_effort": REASONING, "max_completion_tokens": 6000,
            "messages": [{"role": "system", "content": system_prompt()},
                         {"role": "user", "content": json.dumps({"posts": user}, ensure_ascii=False)}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "x_screen", "strict": True, "schema": schema}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=f"runs/x-screen-{date.today():%Y%m%d}")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run = ROOT / args.run
    (run / "responses").mkdir(parents=True, exist_ok=True)
    (run / "system-prompt.md").write_text(system_prompt())

    posts, skipped = load_posts()
    batches = [posts[i:i + BATCH] for i in range(0, len(posts), BATCH)]
    bodies = [request(b) for b in batches]
    est = sum(len(json.dumps(b)) for b in bodies) / 3.5 * INPUT_RATE + len(posts) * 60 * OUTPUT_RATE
    print(f"{len(posts)} posts to screen in {len(batches)} calls; {len(skipped)} dropped in code; ~${est:.3f}")
    if args.dry_run:
        return

    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=180)
    decisions, cost = [], 0.0
    for batch, body in zip(batches, bodies):
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
        cache = run / "responses" / f"{key}.json"
        if not cache.exists():
            resp = client.chat.completions.create(**body)
            cache.write_text(resp.model_dump_json(indent=1))
        resp = json.loads(cache.read_text())
        cost += resp["usage"]["prompt_tokens"] * INPUT_RATE + resp["usage"]["completion_tokens"] * OUTPUT_RATE
        got = {d["id"]: d for d in json.loads(resp["choices"][0]["message"]["content"])["decisions"]}
        for p in batch:
            d = got.get(p["id"], {"decision": "keep", "behavior": "MISSING FROM RESPONSE, kept for review", "agents": []})
            decisions.append({**p, **{k: d[k] for k in ("decision", "behavior", "agents")}, "stage": "luna"})

    out = decisions + skipped
    with (run / "decisions.jsonl").open("w") as f:
        f.writelines(json.dumps(d, ensure_ascii=False) + "\n" for d in out)
    kept = [d for d in decisions if d["decision"] == "keep"]
    summary = {"model": MODEL, "reasoning_effort": REASONING, "csv": str(CSV.relative_to(PRIMARY)),
               "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
               "rows": len(out), "dropped_in_code": len(skipped), "screened": len(decisions),
               "kept": len(kept), "cost_usd": round(cost, 4)}
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
