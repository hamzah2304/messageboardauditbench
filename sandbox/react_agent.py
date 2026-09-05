#!/usr/bin/env python3
"""Minimal ReAct scaffold: an OpenAI-compatible tool-calling loop (OpenRouter by default).

Two tools: bash (run a command, capped output) and write_file. Runs inside the sandbox
container like the vendor CLIs. Emits a transcript on stdout in Claude Code's
stream-json dialect (assistant / user tool_result / result events) so the existing
transcript parser and `inspect view` work unchanged.

  react_agent.py --model moonshotai/kimi-k3 --prompt-file /work/prompt.txt --effort medium --budget-min 20
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.error, uuid

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

def chat(base, key, body):
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/hamzah2304/messageboardauditbench", "X-Title": "messageboardauditbench"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (408, 409, 429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(2 ** attempt); continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < 5: time.sleep(2 ** attempt); continue
            raise

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
    t0 = time.time(); turns = 0; stop = "end_turn"; cost = 0.0
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    emit({"type": "system", "subtype": "init", "cwd": a.cwd, "model": a.model, "tools": [t["function"]["name"] for t in TOOLS],
          "scaffold": "react_agent.py", "base_url": a.base_url})
    while turns < a.max_turns:
        elapsed = (time.time() - t0) / 60
        if elapsed > a.budget_min: stop = "budget"; break
        body = {"model": a.model, "messages": msgs, "tools": TOOLS,
                "cache_control": {"type": "ephemeral"}, "usage": {"include": True}}
        if a.effort: body["reasoning"] = {"effort": a.effort}
        try:
            resp = chat(a.base_url, key, body)
        except Exception as e:
            emit({"type": "error", "error": str(e)}); stop = "api_error"; break
        turns += 1
        u = resp.get("usage") or {}
        det = u.get("prompt_tokens_details") or {}
        tu = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0),
              "cache_read_input_tokens": det.get("cached_tokens", 0) or 0,
              "cache_creation_input_tokens": det.get("cache_write_tokens", 0) or 0, "cost": u.get("cost")}
        for k in usage: usage[k] += tu[k]
        cost += u.get("cost") or 0
        m = resp["choices"][0]["message"]
        mid = resp.get("id") or f"msg_{turns}"
        content = []
        if m.get("reasoning"): content.append({"type": "thinking", "thinking": m["reasoning"]})
        if m.get("content"): content.append({"type": "text", "text": m["content"]})
        calls = m.get("tool_calls") or []
        for c in calls:
            try: args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError: args = {"_raw": c["function"].get("arguments")}
            c["_args"] = args
            content.append({"type": "tool_use", "id": c["id"], "name": c["function"]["name"], "input": args})
        emit({"type": "assistant", "message": {"id": mid, "model": a.model, "content": content,
              "usage": tu}})
        assistant = {"role": "assistant", "content": m.get("content") or ""}
        if calls: assistant["tool_calls"] = [{"id": c["id"], "type": "function", "function": c["function"]} for c in calls]
        msgs.append(assistant)
        if not calls: break
        results = []
        for c in calls:
            args = c["_args"]
            out = ("[could not parse tool arguments as JSON]" if "_raw" in args else run_tool(c["function"]["name"], args, a.cwd))
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out})
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": out})
        emit({"type": "user", "message": {"content": results}})
    emit({"type": "result", "subtype": "success", "num_turns": turns, "duration_ms": int((time.time() - t0) * 1000),
          "stop_reason": stop, "usage": usage, "total_cost_usd": round(cost, 6)})

if __name__ == "__main__":
    main()
