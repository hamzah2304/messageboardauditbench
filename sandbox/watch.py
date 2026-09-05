#!/usr/bin/env python3
"""Follow a run's transcript.jsonl and print what the agent is doing.

    sandbox/watch.py runs/<run_dir>          # follows until the run exits
    sandbox/watch.py runs/<run_dir> --no-follow

Handles both Claude Code (--output-format stream-json) and Codex (--json).
"""
import json
import sys
import time
from pathlib import Path

W = 160


def clip(s: str, n: int = W) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def show_claude(ev: dict) -> None:
    t = ev.get("type")
    if t == "assistant":
        for c in ev["message"].get("content", []):
            if c.get("type") == "text" and c["text"].strip():
                print(f"  💬 {clip(c['text'], 400)}")
            elif c.get("type") == "tool_use":
                inp = c.get("input", {})
                arg = inp.get("command") or inp.get("file_path") or inp.get("pattern") or json.dumps(inp)
                print(f"  ▶ {c['name']}: {clip(arg)}")
    elif t == "user":
        for c in ev["message"].get("content", []):
            if isinstance(c, dict) and c.get("type") == "tool_result":
                body = c.get("content")
                if isinstance(body, list):
                    body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                print(f"    ↳ {clip(body or '', 200)}")
    elif t == "result":
        print(f"■ done: {ev.get('subtype')} turns={ev.get('num_turns')} "
              f"{ev.get('duration_ms', 0) / 1000:.0f}s cost=${ev.get('total_cost_usd', 0):.2f}")


def show_codex(ev: dict) -> None:
    t = ev.get("type")
    if t == "item.completed":
        it = ev["item"]
        k = it.get("type")
        if k == "command_execution":
            print(f"  ▶ bash: {clip(it.get('command', ''))}")
            print(f"    ↳ {clip(it.get('aggregated_output', ''), 200)}")
        elif k == "agent_message":
            print(f"  💬 {clip(it.get('text', ''), 400)}")
        elif k == "reasoning":
            print(f"  🧠 {clip(it.get('text', ''), 200)}")
        elif k == "file_change":
            print(f"  ✎ {', '.join(c['path'].split('/')[-1] for c in it.get('changes', []))}")
    elif t == "turn.completed":
        u = ev.get("usage", {})
        print(f"■ turn done: in={u.get('input_tokens')} out={u.get('output_tokens')}")
    elif t == "error":
        print(f"  ✗ {clip(ev.get('message', ''))}")


def main() -> None:
    run = Path(sys.argv[1])
    follow = "--no-follow" not in sys.argv
    path = run / "transcript.jsonl"
    agent = "codex" if "_codex_" in run.name else "claude"  # react runs use the Claude dialect
    show = show_codex if agent == "codex" else show_claude
    with path.open() as f:
        while True:
            line = f.readline()
            if not line:
                if not follow or (run / "meta.json").exists() and "exit_code" in (run / "meta.json").read_text():
                    return
                time.sleep(1)
                continue
            try:
                show(json.loads(line))
            except json.JSONDecodeError:
                continue
            sys.stdout.flush()


if __name__ == "__main__":
    main()
