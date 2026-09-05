#!/usr/bin/env python3
"""Summarize what a trial cost: tokens (incl. reasoning), cache hits, cost, API calls, retries, how it ended.

    python3 -m messageboard_audit.usage runs/<run_dir>      # writes <run>/usage.json, prints it

Stdlib only, so run_trial.sh can call it on any python3 and transcripts.py can import it.
One dialect per agent:

  * claude  Claude Code `--output-format stream-json`. Totals come from the final `result`
            event (`usage.output_tokens_details.thinking_tokens` is the reasoning count); if the
            run was killed before it, per-message `usage` is summed and thinking tokens fall
            back to Claude Code's own `system/thinking_tokens` estimates.
  * react   sandbox/react_agent.py emits the Claude dialect plus OpenRouter's reasoning token
            count, cost, provider and latency per call.
  * codex   `codex exec --json` only reports usage once, in `turn.completed`, and nothing if
            killed. The session rollout Codex writes (copied to <run>/codex_sessions/) has a
            `token_count` event per API call and the reasoning items, so it is preferred when present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable

KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens")


def _lines(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open(errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict):
                yield ev


def _blank() -> dict[str, Any]:
    return {**{k: 0 for k in KEYS}, "cost_usd": None, "api_calls": 0, "turns": 0, "tool_calls": 0,
            "thinking_blocks": 0, "thinking_chars": 0, "api_retries": 0, "api_errors": 0,
            "peak_context_tokens": 0, "stop_reason": None, "terminal_reason": None, "is_error": None,
            "duration_ms": None, "usage_source": None}


def agent_of(run_dir: Path) -> str:
    meta = run_dir / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text())["agent"]
        except (json.JSONDecodeError, KeyError):
            pass
    return next((a for a in ("codex", "react") if f"_{a}_" in run_dir.name), "claude")


# ------------------------------------------------------------ Claude Code dialect (claude, react)

def summarize_claude_stream(path: Path) -> dict[str, Any]:
    s = _blank()
    per_msg: dict[str, dict] = {}
    seen_ids: set[str] = set()
    est_thinking = 0
    rate_limits: list[dict] = []
    result: dict | None = None
    latencies: list[int] = []
    providers: set[str] = set()
    finish_reasons: dict[str, int] = {}
    for ev in _lines(path):
        t = ev.get("type")
        if t == "assistant":
            msg = ev.get("message") or {}
            mid = msg.get("id") or f"anon{len(seen_ids)}"
            if mid not in seen_ids:
                seen_ids.add(mid)
                s["turns"] += 1
            if msg.get("usage"):
                per_msg[mid] = msg["usage"]
            for c in msg.get("content") or []:
                k = c.get("type")
                if k == "tool_use":
                    s["tool_calls"] += 1
                elif k == "thinking":
                    s["thinking_blocks"] += 1
                    s["thinking_chars"] += len(c.get("thinking") or "")
            api = ev.get("api") or {}   # react_agent.py only
            if api.get("latency_ms") is not None:
                latencies.append(api["latency_ms"])
            if api.get("provider"):
                providers.add(api["provider"])
            if api.get("finish_reason"):
                finish_reasons[api["finish_reason"]] = finish_reasons.get(api["finish_reason"], 0) + 1
            s["api_retries"] += api.get("retries") or 0
        elif t == "system":
            sub = ev.get("subtype")
            if sub == "thinking_tokens":
                est_thinking += ev.get("estimated_tokens_delta") or 0
            elif sub == "api_retry":
                s["api_retries"] += 1
        elif t == "rate_limit_event":
            rate_limits.append(ev.get("rate_limit_info") or {})
        elif t == "error":
            s["api_errors"] += 1
        elif t == "result":
            result = ev
    s["api_calls"] = len(per_msg) or s["turns"]
    for u in per_msg.values():
        ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
        s["peak_context_tokens"] = max(s["peak_context_tokens"], ctx)

    def take(u: dict) -> None:
        s["input_tokens"] = u.get("input_tokens") or 0
        s["output_tokens"] = u.get("output_tokens") or 0
        s["cache_read_tokens"] = u.get("cache_read_input_tokens") or 0
        s["cache_write_tokens"] = u.get("cache_creation_input_tokens") or 0
        s["reasoning_tokens"] = ((u.get("output_tokens_details") or {}).get("thinking_tokens")
                                 or u.get("reasoning_tokens") or 0)

    if result and result.get("usage"):
        take(result["usage"])
        s["usage_source"] = "result"
    else:
        agg: dict[str, int] = {}
        for u in per_msg.values():
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens"):
                agg[k] = agg.get(k, 0) + (u.get(k) or 0)
            agg["reasoning_tokens"] = agg.get("reasoning_tokens", 0) + ((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
        take(agg)
        s["usage_source"] = "per_message_sum" if per_msg else "none"
        if not s["reasoning_tokens"] and est_thinking:
            s["reasoning_tokens"] = est_thinking
            s["reasoning_tokens_estimated"] = True
    if result:
        s["cost_usd"] = result.get("total_cost_usd")
        s["duration_ms"] = result.get("duration_ms")
        s["stop_reason"] = result.get("stop_reason")
        s["terminal_reason"] = result.get("terminal_reason") or result.get("subtype")
        s["is_error"] = result.get("is_error")
        for k in ("duration_api_ms", "ttft_ms", "api_error_status", "session_id", "num_turns"):
            if result.get(k) is not None:
                s[k] = result[k]
        if result.get("permission_denials"):
            s["permission_denials"] = len(result["permission_denials"])
        if result.get("modelUsage"):
            s["per_model"] = result["modelUsage"]
    elif per_msg:
        s["cost_usd"] = sum((u.get("cost") or 0) for u in per_msg.values()) or None
        s["terminal_reason"] = "no_result_event"
    if est_thinking:
        s["thinking_tokens_estimated_by_cli"] = est_thinking
    if rate_limits:
        s["last_rate_limit"] = rate_limits[-1]
    if latencies:
        s["latency_ms_mean"] = round(sum(latencies) / len(latencies))
        s["latency_ms_max"] = max(latencies)
    if providers:
        s["providers"] = sorted(providers)
    if finish_reasons:
        s["finish_reasons"] = finish_reasons
    return s


# --------------------------------------------------------------------------------------- Codex

def _codex_rollouts(run_dir: Path) -> list[Path]:
    return sorted((run_dir / "codex_sessions").rglob("rollout-*.jsonl"))


def summarize_codex(run_dir: Path) -> dict[str, Any]:
    s = _blank()
    turn_usage: dict | None = None
    for ev in _lines(run_dir / "transcript.jsonl"):
        t = ev.get("type")
        if t == "item.completed":
            k = (ev.get("item") or {}).get("type")
            if k in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
                s["tool_calls"] += 1
            elif k == "reasoning":
                s["thinking_blocks"] += 1
                s["thinking_chars"] += len((ev["item"].get("text") or ""))
        elif t == "turn.completed":
            turn_usage = ev.get("usage") or {}
            s["turns"] += 1
        elif t == "error":
            s["api_errors"] += 1
            if "Reconnecting" in str(ev.get("message", "")):
                s["api_retries"] += 1
    s["turns"] = s["tool_calls"]  # codex's own "turn" is the whole exec; count tool round-trips like the others

    def take(u: dict) -> None:
        s["input_tokens"] = u.get("input_tokens") or 0
        s["output_tokens"] = u.get("output_tokens") or 0
        s["cache_read_tokens"] = u.get("cached_input_tokens") or 0
        s["cache_write_tokens"] = u.get("cache_write_input_tokens") or 0
        s["reasoning_tokens"] = u.get("reasoning_output_tokens") or 0

    rollouts = _codex_rollouts(run_dir)
    if rollouts:
        last_total: dict | None = None
        calls = 0; r_items = 0; r_summary_chars = 0; r_raw_chars = 0; encrypted = 0; peak = 0
        for ro in rollouts:
            for ev in _lines(ro):
                p = ev.get("payload") or {}
                if ev.get("type") == "event_msg" and p.get("type") == "token_count":
                    info = p.get("info") or {}
                    if info.get("total_token_usage"):
                        last_total = info["total_token_usage"]
                    last = info.get("last_token_usage") or {}
                    if last:
                        calls += 1
                        peak = max(peak, last.get("input_tokens") or 0)
                elif ev.get("type") == "response_item" and p.get("type") == "reasoning":
                    r_items += 1
                    r_summary_chars += sum(len(x.get("text") or "") for x in (p.get("summary") or []) if isinstance(x, dict))
                    r_raw_chars += sum(len(x.get("text") or "") for x in (p.get("content") or []) if isinstance(x, dict))
                    encrypted += bool(p.get("encrypted_content"))
                elif ev.get("type") == "turn_context":
                    for k in ("model", "effort", "summary"):
                        if p.get(k) is not None:
                            s[f"codex_{k}"] = p[k]
        s["api_calls"] = calls
        s["peak_context_tokens"] = peak
        s["reasoning_items"] = r_items
        s["reasoning_summary_chars"] = r_summary_chars
        s["reasoning_raw_chars"] = r_raw_chars
        s["reasoning_items_encrypted"] = encrypted
        if last_total:
            take(last_total)
            s["usage_source"] = "codex_rollout"
    if s["usage_source"] is None and turn_usage is not None:
        take(turn_usage)
        s["usage_source"] = "turn_completed"
    if s["usage_source"] is None:
        s["usage_source"] = "none"
    s["terminal_reason"] = "turn_completed" if turn_usage is not None else "no_turn_completed"
    s["is_error"] = turn_usage is None
    return s


# --------------------------------------------------------------------------------------- entry

def summarize(run_dir: Path, agent: str | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    agent = agent or agent_of(run_dir)
    s = summarize_codex(run_dir) if agent == "codex" else summarize_claude_stream(run_dir / "transcript.jsonl")
    s["agent"] = agent
    s["total_tokens"] = s["input_tokens"] + s["output_tokens"] + s["cache_read_tokens"] + s["cache_write_tokens"]
    return s


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__); return 2
    run_dir = Path(argv[1])
    s = summarize(run_dir)
    (run_dir / "usage.json").write_text(json.dumps(s, indent=1) + "\n")
    if "--quiet" not in argv:
        print(json.dumps({k: s[k] for k in ("agent", "usage_source", *KEYS, "cost_usd", "api_calls", "tool_calls",
                                             "api_retries", "peak_context_tokens", "terminal_reason")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
