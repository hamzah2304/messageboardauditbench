#!/usr/bin/env python3
"""Minimal ReAct scaffold: an OpenAI-compatible tool-calling loop (OpenRouter by default).

Two tools: bash (run a command, capped output) and write_file. Runs inside the sandbox
container like the vendor CLIs. Emits a transcript on stdout in Claude Code's
stream-json dialect (assistant / user tool_result / result events) so the existing
transcript parser and `inspect view` work unchanged.

What is logged per model call (on the `assistant` event):
  * message.content: thinking (OpenRouter's `reasoning` text or the text/summary parts of
    `reasoning_details`), text, tool_use blocks
  * message.usage: input/output tokens, cache read/write, reasoning_tokens, cost (USD)
  * message.reasoning_details: OpenRouter's structured reasoning blocks, verbatim (also passed
    back on the next request so the model keeps its chain of thought across tool calls)
  * api: provider that served it, finish_reason, native_finish_reason, latency_ms, retries,
    upstream response id
The final `result` event carries the totals.

  react_agent.py --model moonshotai/kimi-k3 --prompt-file /work/prompt.txt --effort medium --budget-min 20
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.error

TOOLS = [
    {"type": "function", "function": {"name": "bash",
        "description": "Run a shell command in the working directory (bash, Python 3, jq, ripgrep, sqlite3 available). Output is truncated to 20000 characters.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "write_file",
        "description": "Write content to a file (overwrites). Use this to write report.md.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
]
MAX_OUT = 20000
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens")

def emit(ev):
    sys.stdout.write(json.dumps(ev) + "\n"); sys.stdout.flush()

def run_tool(name, args, cwd):
    if name == "bash":
        try:
            r = subprocess.run(args.get("command", ""), shell=True, cwd=cwd, capture_output=True, text=True,
                               errors="replace", timeout=300)
            out = r.stdout + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            if r.returncode: out += f"\n[exit code {r.returncode}]"
        except subprocess.TimeoutExpired:
            out = "[command timed out after 300s]"
    elif name == "write_file":
        try:
            path = os.path.join(cwd, args["path"])
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f: f.write(args["content"])
            out = f"wrote {len(args['content'])} chars to {args['path']}"
        except Exception as e:
            out = f"[error: {e}]"
    else:
        out = f"[unknown tool {name}]"
    if len(out) > MAX_OUT:
        out = out[:MAX_OUT // 2] + f"\n...[truncated {len(out) - MAX_OUT} chars]...\n" + out[-MAX_OUT // 2:]
    return out

def time_left_note():
    """Same message Claude Code gets from sandbox/time_left.sh: appended to every tool result when run_trial.sh set the deadline."""
    dl = os.environ.get("MBAB_DEADLINE_EPOCH")
    if not dl: return ""
    left = (int(dl) - int(time.time()) + 30) // 60
    budget = os.environ.get("MBAB_BUDGET_MIN", "?")
    if left > 0: return f"\n\n[Time budget: about {left} of {budget} minutes left.]"
    return f"\n\n[Time budget: exhausted (about {-left} minutes over). The session will be stopped any moment; make sure report.md is complete.]"

def chat(base, key, body):
    """POST /chat/completions with retries. Returns (response_json, retries, latency_ms of the successful attempt)."""
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/hamzah2304/messageboardauditbench", "X-Title": "messageboardauditbench"})
    for attempt in range(6):
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.load(r)
            err = resp.get("error") if isinstance(resp, dict) else None
            if err and "choices" not in resp:  # OpenRouter reports upstream 429/5xx in a 200 body
                code = err.get("code") if isinstance(err, dict) else None
                if code in (408, 409, 429, 500, 502, 503, 504) and attempt < 5:
                    emit({"type": "system", "subtype": "api_retry", "attempt": attempt + 1, "error_status": code, "error": str(err)[:200]})
                    time.sleep(2 ** attempt); continue
                raise RuntimeError(f"API error {code}: {json.dumps(err)[:500]}")
            return resp, attempt, int((time.time() - t) * 1000)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (408, 409, 429, 500, 502, 503, 504) and attempt < 5:
                emit({"type": "system", "subtype": "api_retry", "attempt": attempt + 1, "error_status": e.code, "error": msg[:200]})
                time.sleep(2 ** attempt); continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < 5:
                emit({"type": "system", "subtype": "api_retry", "attempt": attempt + 1, "error_status": None, "error": str(e)[:200]})
                time.sleep(2 ** attempt); continue
            raise

def usage_of(resp):
    """Normalize OpenRouter usage (OpenAI shape + cost) to the Claude-dialect keys the parser reads."""
    u = resp.get("usage") or {}
    pd = u.get("prompt_tokens_details") or {}
    cd = u.get("completion_tokens_details") or {}
    out = {"input_tokens": u.get("prompt_tokens", 0) or 0, "output_tokens": u.get("completion_tokens", 0) or 0,
           "cache_read_input_tokens": pd.get("cached_tokens", 0) or 0,
           "cache_creation_input_tokens": pd.get("cache_write_tokens", 0) or 0,
           "reasoning_tokens": cd.get("reasoning_tokens", 0) or 0, "cost": u.get("cost")}
    if u.get("cost_details"): out["cost_details"] = u["cost_details"]
    return out

def reasoning_text(m):
    """Plaintext reasoning for the transcript: `reasoning`, else the text/summary parts of `reasoning_details`."""
    if m.get("reasoning"): return m["reasoning"]
    parts = []
    for d in m.get("reasoning_details") or []:
        if not isinstance(d, dict): continue
        parts.append(d.get("text") or d.get("summary") or "")
    return "\n".join(p for p in parts if p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--effort", default="medium"); ap.add_argument("--budget-min", type=float, default=20)
    ap.add_argument("--max-turns", type=int, default=100000); ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"))
    a = ap.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY") or sys.exit("no API key in env")
    prompt = open(a.prompt_file).read()
    system = ("You are an autonomous agent working in a Linux shell. Use the bash tool to explore and "
              "write_file to write files. Keep working until the task is done.")
    # Prompt caching. OpenAI/Gemini 2.5+/Moonshot/DeepSeek/xAI cache automatically on OpenRouter.
    # Anthropic and Qwen need markers: the top-level cache_control lets OpenRouter place Anthropic
    # breakpoints automatically, and the per-block marker on the system prompt covers the rest.
    msgs = [{"role": "system", "content": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]},
            {"role": "user", "content": prompt}]
    t0 = time.time(); turns = 0; stop = "end_turn"; cost = 0.0; retries = 0; latencies = []; providers = {}
    usage = {k: 0 for k in USAGE_KEYS}
    emit({"type": "system", "subtype": "init", "cwd": a.cwd, "model": a.model, "effort": a.effort, "budget_min": a.budget_min,
          "tools": [t["function"]["name"] for t in TOOLS], "scaffold": "react_agent.py", "base_url": a.base_url})
    while turns < a.max_turns:
        elapsed = (time.time() - t0) / 60
        if elapsed > a.budget_min: stop = "budget"; break
        body = {"model": a.model, "messages": msgs, "tools": TOOLS,
                "cache_control": {"type": "ephemeral"}, "usage": {"include": True}}
        if a.effort: body["reasoning"] = {"effort": a.effort}
        try:
            resp, n_retry, latency_ms = chat(a.base_url, key, body)
            if "choices" not in resp:  # OpenRouter can return {"error": ...} with HTTP 200
                raise RuntimeError(f"no choices in response: {json.dumps(resp)[:600]}")
        except Exception as e:
            emit({"type": "error", "error": str(e)}); stop = "api_error"; break
        turns += 1; retries += n_retry; latencies.append(latency_ms)
        tu = usage_of(resp)
        for k in usage: usage[k] += tu.get(k) or 0
        cost += tu.get("cost") or 0
        choice = resp["choices"][0]; m = choice["message"]
        mid = resp.get("id") or f"msg_{turns}"
        provider = resp.get("provider"); providers[provider] = providers.get(provider, 0) + 1
        content = []
        rt = reasoning_text(m)
        if rt: content.append({"type": "thinking", "thinking": rt})
        if m.get("content"): content.append({"type": "text", "text": m["content"]})
        calls = m.get("tool_calls") or []
        for c in calls:
            try: args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError: args = {"_raw": c["function"].get("arguments")}
            c["_args"] = args
            content.append({"type": "tool_use", "id": c["id"], "name": c["function"]["name"], "input": args})
        message = {"id": mid, "model": resp.get("model") or a.model, "content": content, "usage": tu}
        if m.get("reasoning_details"): message["reasoning_details"] = m["reasoning_details"]
        emit({"type": "assistant", "message": message,
              "api": {"provider": provider, "finish_reason": choice.get("finish_reason"),
                      "native_finish_reason": choice.get("native_finish_reason"), "latency_ms": latency_ms,
                      "retries": n_retry, "response_id": resp.get("id"), "elapsed_s": round(time.time() - t0, 1)}})
        assistant = {"role": "assistant", "content": m.get("content") or ""}
        if calls: assistant["tool_calls"] = [{"id": c["id"], "type": "function", "function": c["function"]} for c in calls]
        # Pass reasoning back unmodified so reasoning models (Gemini 3, Anthropic, OpenAI) keep their
        # chain of thought across tool calls, as OpenRouter recommends.
        if m.get("reasoning_details"): assistant["reasoning_details"] = m["reasoning_details"]
        msgs.append(assistant)
        if not calls: break
        results = []
        for c in calls:
            args = c["_args"]
            out = ("[could not parse tool arguments as JSON]" if "_raw" in args else run_tool(c["function"]["name"], args, a.cwd))
            out += time_left_note()
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out})
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": out})
        emit({"type": "user", "message": {"content": results}})
    emit({"type": "result", "subtype": "success" if stop in ("end_turn", "budget") else "error", "is_error": stop == "api_error",
          "num_turns": turns, "duration_ms": int((time.time() - t0) * 1000), "stop_reason": stop, "terminal_reason": stop,
          "usage": usage, "total_cost_usd": round(cost, 6), "api_calls": turns, "api_retries": retries,
          "latency_ms_mean": round(sum(latencies) / len(latencies)) if latencies else None, "providers": providers})

if __name__ == "__main__":
    main()
