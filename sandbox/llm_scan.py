#!/usr/bin/env python3
"""llm_scan: read many log records with a language model, in parallel.

The data is too large for one context window. This tool splits selected rows
of a JSONL file into chunks, sends every chunk to a model with the same
instruction, and writes one JSONL line per finding. Use it to read for meaning
at scale; use grep/python for counting and filtering.

Examples
  llm_scan --input data/revisions.jsonl --text body --id rev_id \
      --prompt "List any technique for getting around a sandbox or network block" \
      --out scan_bypass.jsonl

  llm_scan --input data/revisions.jsonl --text body --id rev_id \
      --filter 'r["wiki"]=="dse" and r["body_len"]>2000' --rows-per-chunk 10 \
      --include time,label --prompt "What task are the writers trying to solve? Note anything odd." \
      --dry-run                       # shows chunk count and size, makes no calls

Output (default schema): one line per finding
  {"chunk":3,"source_id":"dse~Foo@2","category":"bypass","summary":"...","quote":"...","confidence":0.8}
plus one {"type":"note","chunk":3,"notes":"..."} line per chunk when the model
had something general to say. Results are also summarised on stderr.

Backends: the Claude Code CLI on this machine (default), or the Anthropic API if
ANTHROPIC_API_KEY is set. Reader model: --model haiku (default) or sonnet.
Calls are cached under ./.llm_scan/cache so re-running the same scan is free.
A per-session cap (LLM_SCAN_MAX_CALLS, default 400) stops runaway usage.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MODELS = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5"}
STATE = Path(".llm_scan")
CACHE = STATE / "cache"
USAGE = STATE / "usage.jsonl"
COUNTER = STATE / "calls.count"
MAX_CALLS = int(os.environ.get("LLM_SCAN_MAX_CALLS", "400"))

DEFAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "the id of the record this came from, copied exactly"},
                    "category": {"type": "string", "description": "short label; use 'other' for anything unusual not covered by the task"},
                    "summary": {"type": "string", "description": "one sentence"},
                    "quote": {"type": "string", "description": "short verbatim excerpt from the record"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["source_id", "category", "summary", "quote", "confidence"],
            },
        },
        "notes": {"type": "string", "description": "anything general about this batch, or empty"},
    },
    "required": ["findings", "notes"],
}

WRAPPER = """You are one of many readers helping an investigator go through a wiki's edit logs. You see one batch of records; other readers see the others. Read every record in the batch.

Investigator's instruction:
{prompt}

Rules: report only what is in the records below. For each finding give the record's id exactly as shown after '###', a short verbatim quote, a category, a one-sentence summary and a confidence between 0 and 1. Also report anything clearly unusual that the instruction did not ask about, under category "other". If nothing in the batch is relevant, return an empty findings list. Do not summarise records that contain nothing relevant.

Records:
{chunk}
"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_rows(path: str, flt: str | None, limit: int | None) -> list[dict]:
    rows = []
    fh = sys.stdin if path == "-" else open(path)
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if flt and not eval(flt, {}, {"r": r}):  # noqa: S307 - user-supplied filter on their own data
            continue
        rows.append(r)
        if limit and len(rows) >= limit:
            break
    return rows


def render_row(r: dict, id_field: str, text_fields: list[str], include: list[str], max_row_chars: int) -> str:
    rid = str(r.get(id_field, "?"))
    meta = " ".join(f"{k}={json.dumps(r.get(k), ensure_ascii=False)}" for k in include if k in r)
    parts = []
    for f in text_fields:
        v = r.get(f)
        if v is None:
            continue
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        parts.append(s if len(text_fields) == 1 else f"[{f}] {s}")
    body = "\n".join(parts)
    if len(body) > max_row_chars:
        body = body[:max_row_chars] + f"\n[... truncated, {len(body) - max_row_chars} more chars]"
    return f"### {rid}" + (f" | {meta}" if meta else "") + "\n" + body


def chunk_rows(rendered: list[str], rows_per_chunk: int, max_chars: int) -> list[list[int]]:
    chunks, cur, size = [], [], 0
    for i, txt in enumerate(rendered):
        if cur and (len(cur) >= rows_per_chunk or size + len(txt) > max_chars):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(txt)
    if cur:
        chunks.append(cur)
    return chunks


def bump_counter(n: int) -> int:
    STATE.mkdir(exist_ok=True)
    cur = int(COUNTER.read_text()) if COUNTER.exists() else 0
    COUNTER.write_text(str(cur + n))
    return cur + n


def call_cli(prompt: str, model: str, schema: dict, timeout: int) -> dict:
    cmd = [
        "claude", "-p", "--model", model, "--output-format", "json",
        "--json-schema", json.dumps(schema), "--tools", "", "--no-session-persistence",
    ]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode != 0 and not p.stdout.strip():
        raise RuntimeError(f"claude exited {p.returncode}: {p.stderr[-400:]}")
    d = json.loads(p.stdout)
    if d.get("is_error"):
        raise RuntimeError(f"model error: {str(d.get('result'))[:300]}")
    out = d.get("structured_output")
    if out is None:
        out = json.loads(d.get("result") or "{}")
    return {"result": out, "usage": d.get("usage", {}), "cost_usd": d.get("total_cost_usd"), "ms": d.get("duration_ms")}


def call_api(prompt: str, model: str, schema: dict, timeout: int) -> dict:
    import anthropic  # only needed on this path

    client = anthropic.Anthropic(timeout=timeout)
    t0 = time.time()
    msg = client.messages.create(
        model=model, max_tokens=4000,
        tools=[{"name": "report", "description": "Report findings", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "report"},
        messages=[{"role": "user", "content": prompt}],
    )
    out = next(b.input for b in msg.content if b.type == "tool_use")
    u = msg.usage
    return {"result": out, "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
            "cost_usd": None, "ms": int((time.time() - t0) * 1000)}


def scan_chunk(idx: int, text: str, args, schema: dict, backend) -> tuple[int, dict, bool]:
    prompt = WRAPPER.format(prompt=args.prompt, chunk=text)
    key = hashlib.sha256(f"{args.model}\n{json.dumps(schema, sort_keys=True)}\n{prompt}".encode()).hexdigest()
    cpath = CACHE / f"{key}.json"
    if cpath.exists():
        return idx, json.loads(cpath.read_text()), True
    last = None
    for attempt in range(3):
        try:
            res = backend(prompt, args.model, schema, args.timeout)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    else:
        return idx, {"error": str(last)}, False
    CACHE.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(res))
    with USAGE.open("a") as fh:
        fh.write(json.dumps({"t": time.time(), "chunk": idx, "model": args.model, "chars": len(prompt),
                             "usage": res.get("usage"), "cost_usd": res.get("cost_usd"), "ms": res.get("ms")}) + "\n")
    return idx, res, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="JSONL file, or - for stdin")
    ap.add_argument("--prompt", help="what to look for; or use --prompt-file")
    ap.add_argument("--prompt-file")
    ap.add_argument("--text", default="body", help="comma-separated field(s) holding the text to read (default body)")
    ap.add_argument("--id", default="rev_id", help="field used as the record id (default rev_id)")
    ap.add_argument("--include", default="", help="comma-separated extra fields to show as record metadata, e.g. time,label")
    ap.add_argument("--filter", help='python expression over row r, e.g. \'r["wiki"]=="dse"\'')
    ap.add_argument("--limit", type=int, help="stop after this many matching rows")
    ap.add_argument("--rows-per-chunk", type=int, default=20)
    ap.add_argument("--max-chars", type=int, default=60000, help="max characters of records per chunk")
    ap.add_argument("--max-row-chars", type=int, default=8000, help="truncate a single record's text beyond this")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--model", default="haiku", help="haiku (default) or sonnet")
    ap.add_argument("--schema", help="JSON schema file replacing the default findings schema; output is then one line per chunk")
    ap.add_argument("--out", help="write results here (default: stdout)")
    ap.add_argument("--timeout", type=int, default=240, help="seconds per model call")
    ap.add_argument("--dry-run", action="store_true", help="show chunking and estimated size, make no calls")
    args = ap.parse_args()

    if args.prompt_file:
        args.prompt = Path(args.prompt_file).read_text()
    if not args.prompt:
        ap.error("--prompt or --prompt-file required")
    args.model = MODELS.get(args.model, args.model)
    schema = json.loads(Path(args.schema).read_text()) if args.schema else DEFAULT_SCHEMA
    custom = args.schema is not None

    rows = load_rows(args.input, args.filter, args.limit)
    text_fields = [f for f in args.text.split(",") if f]
    include = [f for f in args.include.split(",") if f]
    rendered = [render_row(r, args.id, text_fields, include, args.max_row_chars) for r in rows]
    chunks = chunk_rows(rendered, args.rows_per_chunk, args.max_chars)
    total_chars = sum(len(t) for t in rendered)
    log(f"llm_scan: {len(rows)} rows -> {len(chunks)} chunks, {total_chars/1000:.0f}k chars (~{total_chars//4//1000}k tokens), model {args.model}")
    if not rows:
        return 0
    if args.dry_run:
        for i, c in enumerate(chunks[:5]):
            log(f"  chunk {i}: {len(c)} rows, {sum(len(rendered[j]) for j in c)} chars, ids {rows[c[0]].get(args.id)} .. {rows[c[-1]].get(args.id)}")
        if len(chunks) > 5:
            log(f"  ... {len(chunks) - 5} more")
        return 0

    used = int(COUNTER.read_text()) if COUNTER.exists() else 0
    if used + len(chunks) > MAX_CALLS:
        log(f"llm_scan: refusing: this scan needs {len(chunks)} calls, {used} already used, cap is {MAX_CALLS}. Narrow with --filter/--limit or raise --rows-per-chunk.")
        return 2
    bump_counter(len(chunks))

    backend = call_api if os.environ.get("ANTHROPIC_API_KEY") else call_cli
    out = open(args.out, "w") if args.out else sys.stdout
    t0 = time.time()
    n_find, n_err, n_cached, cats = 0, 0, 0, {}
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(scan_chunk, i, "\n\n".join(rendered[j] for j in c), args, schema, backend) for i, c in enumerate(chunks)]
        done = 0
        for fut in cf.as_completed(futs):
            idx, res, cached = fut.result()
            done += 1
            n_cached += cached
            ids = [str(rows[j].get(args.id)) for j in chunks[idx]]
            if "error" in res:
                n_err += 1
                out.write(json.dumps({"type": "error", "chunk": idx, "source_ids": ids, "error": res["error"]}) + "\n")
            elif custom:
                out.write(json.dumps({"chunk": idx, "source_ids": ids, "result": res["result"]}, ensure_ascii=False) + "\n")
            else:
                r = res["result"] or {}
                for f in r.get("findings", []) or []:
                    f = dict(f)
                    f["chunk"] = idx
                    if f.get("source_id") not in ids:
                        f["source_id_unverified"] = True
                    out.write(json.dumps(f, ensure_ascii=False) + "\n")
                    n_find += 1
                    cats[f.get("category", "?")] = cats.get(f.get("category", "?"), 0) + 1
                if (r.get("notes") or "").strip():
                    out.write(json.dumps({"type": "note", "chunk": idx, "source_ids": ids, "notes": r["notes"]}, ensure_ascii=False) + "\n")
            out.flush()
            if done % 10 == 0 or done == len(chunks):
                log(f"  {done}/{len(chunks)} chunks, {n_find} findings, {n_err} errors, {time.time()-t0:.0f}s")
    if args.out:
        out.close()
    top = ", ".join(f"{k}={v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1])[:8])
    log(f"llm_scan: done in {time.time()-t0:.0f}s. {n_find} findings ({top}); {n_err} chunk errors; {n_cached} from cache; calls used this session {used + len(chunks) - n_cached}/{MAX_CALLS}")
    if args.out:
        log(f"results in {args.out}. Records flagged source_id_unverified had an id the reader did not see; check them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
