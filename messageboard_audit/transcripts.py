"""Convert a coding-agent CLI event stream into Inspect chat messages.

Two dialects:
  * Claude Code  `claude -p --output-format stream-json --verbose`
  * Codex        `codex exec --json`
  * ReAct        `sandbox/react_agent.py` (emits the Claude Code dialect)

The output is a list of ChatMessageAssistant / ChatMessageTool in the order the
agent produced them, plus a usage summary. Rendering them as ordinary messages
with tool calls is what makes `inspect view` show the run like any native
Inspect agent: text, tool call, tool result, repeat.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from inspect_ai.model import ChatMessage, ChatMessageAssistant, ChatMessageTool
from inspect_ai._util.content import ContentReasoning, ContentText
from inspect_ai.tool import ToolCall

from messageboard_audit.usage import summarize


@dataclass
class Parsed:
    messages: list[ChatMessage] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    turns: int = 0
    tool_calls: int = 0
    cost_usd: float | None = None
    duration_ms: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _lines(path: Path) -> Iterable[dict]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------- Claude Code

def parse_claude(path: Path) -> Parsed:
    p = Parsed()
    # Claude streams one `assistant` event per content block, all sharing the
    # API message id; merge blocks with the same id into one chat message.
    current_id: str | None = None
    current: ChatMessageAssistant | None = None
    tool_names: dict[str, str] = {}
    usage_by_msg: dict[str, dict] = {}
    rate_limits: list[dict] = []

    def flush() -> None:
        nonlocal current
        if current is not None and (current.content or current.tool_calls):
            p.messages.append(current)
        current = None

    for ev in _lines(path):
        t = ev.get("type")
        if t == "assistant":
            msg = ev["message"]
            if msg.get("id") != current_id:
                flush()
                current_id = msg.get("id")
                current = ChatMessageAssistant(content=[], tool_calls=[], model=msg.get("model"))
                p.turns += 1
            usage_by_msg[current_id] = msg.get("usage") or usage_by_msg.get(current_id, {})
            for c in msg.get("content", []):
                kind = c.get("type")
                if kind == "text" and c.get("text"):
                    current.content.append(ContentText(text=c["text"]))
                elif kind == "thinking" and c.get("thinking"):
                    current.content.append(ContentReasoning(reasoning=c["thinking"]))
                elif kind == "tool_use":
                    tool_names[c["id"]] = c["name"]
                    current.tool_calls.append(
                        ToolCall(id=c["id"], function=c["name"], arguments=c.get("input") or {})
                    )
                    p.tool_calls += 1
        elif t == "user":
            flush()
            current_id = None
            for c in ev["message"].get("content", []):
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    body = c.get("content")
                    if isinstance(body, list):
                        body = "\n".join(x.get("text", "") for x in body if isinstance(x, dict))
                    p.messages.append(
                        ChatMessageTool(
                            content=str(body or ""),
                            tool_call_id=c.get("tool_use_id"),
                            function=tool_names.get(c.get("tool_use_id"), "tool"),
                        )
                    )
        elif t == "rate_limit_event":
            rate_limits.append(ev.get("rate_limit_info", {}))
        elif t == "result":
            flush()
            p.cost_usd = ev.get("total_cost_usd")
            p.duration_ms = ev.get("duration_ms")
            p.extra["result_subtype"] = ev.get("subtype")
            p.extra["num_turns_reported"] = ev.get("num_turns")
            u = ev.get("usage") or {}
            if u:
                p.input_tokens = u.get("input_tokens", 0)
                p.output_tokens = u.get("output_tokens", 0)
                p.cache_read_tokens = u.get("cache_read_input_tokens", 0)
                p.cache_write_tokens = u.get("cache_creation_input_tokens", 0)
    flush()
    if not p.input_tokens:  # no result event (killed by timeout): sum per-message usage
        for u in usage_by_msg.values():
            p.input_tokens += u.get("input_tokens", 0)
            p.output_tokens += u.get("output_tokens", 0)
            p.cache_read_tokens += u.get("cache_read_input_tokens", 0)
            p.cache_write_tokens += u.get("cache_creation_input_tokens", 0)
    if rate_limits:
        p.extra["last_rate_limit"] = rate_limits[-1]
    return p


# --------------------------------------------------------------------- Codex

def parse_codex(path: Path) -> Parsed:
    p = Parsed()
    n = 0
    for ev in _lines(path):
        t = ev.get("type")
        if t == "item.completed":
            it = ev.get("item", {})
            k = it.get("type")
            n += 1
            if k == "command_execution":
                cid = it.get("id", f"item_{n}")
                p.messages.append(
                    ChatMessageAssistant(
                        content=[],
                        tool_calls=[ToolCall(id=cid, function="bash", arguments={"command": it.get("command", "")})],
                    )
                )
                out = it.get("aggregated_output", "") or ""
                if it.get("exit_code") not in (0, None):
                    out += f"\n[exit code {it.get('exit_code')}]"
                p.messages.append(ChatMessageTool(content=out, tool_call_id=cid, function="bash"))
                p.tool_calls += 1
                p.turns += 1
            elif k == "file_change":
                cid = it.get("id", f"item_{n}")
                changes = it.get("changes", [])
                p.messages.append(
                    ChatMessageAssistant(
                        content=[],
                        tool_calls=[ToolCall(id=cid, function="apply_patch", arguments={"changes": changes})],
                    )
                )
                p.messages.append(
                    ChatMessageTool(
                        content="\n".join(f"{c.get('kind')} {c.get('path')}" for c in changes),
                        tool_call_id=cid, function="apply_patch",
                    )
                )
                p.tool_calls += 1
                p.turns += 1
            elif k == "agent_message":
                p.messages.append(ChatMessageAssistant(content=[ContentText(text=it.get("text", ""))]))
                p.turns += 1
            elif k == "reasoning":
                # summary text with model_reasoning_summary=detailed; raw text when show_raw_agent_reasoning surfaces it
                p.messages.append(ChatMessageAssistant(content=[ContentReasoning(reasoning=it.get("text") or "")]))
        elif t == "turn.completed":
            u = ev.get("usage", {})
            p.input_tokens += u.get("input_tokens", 0)
            p.output_tokens += u.get("output_tokens", 0)
            p.cache_read_tokens += u.get("cached_input_tokens", 0)
            p.cache_write_tokens += u.get("cache_write_input_tokens", 0)
            p.reasoning_tokens += u.get("reasoning_output_tokens", 0)
        elif t == "error":
            p.messages.append(ChatMessageAssistant(content=[ContentText(text=f"[codex error] {ev.get('message')}")]))
    return p


def parse(agent: str, path: Path) -> Parsed:
    """Messages from the dialect parser; token/cost figures from messageboard_audit.usage, which is
    also what run_trial.sh writes to <run>/usage.json, so Inspect and meta.json always agree."""
    # react_agent.py deliberately writes the Claude Code dialect.
    p = parse_codex(path) if agent == "codex" else parse_claude(path)
    u = summarize(path.parent, agent)
    p.input_tokens, p.output_tokens = u["input_tokens"], u["output_tokens"]
    p.cache_read_tokens, p.cache_write_tokens = u["cache_read_tokens"], u["cache_write_tokens"]
    p.reasoning_tokens = u["reasoning_tokens"]
    p.cost_usd = u.get("cost_usd", p.cost_usd)
    p.duration_ms = u.get("duration_ms") or p.duration_ms
    for k in ("usage_source", "api_calls", "api_retries", "api_errors", "peak_context_tokens", "stop_reason",
              "terminal_reason", "is_error", "duration_api_ms", "ttft_ms", "thinking_blocks", "thinking_chars",
              "reasoning_tokens_estimated", "reasoning_items", "reasoning_summary_chars", "latency_ms_mean", "permission_denials"):
        if u.get(k) is not None:
            p.extra[k] = u[k]
    if u.get("last_rate_limit"):
        p.extra["last_rate_limit"] = u["last_rate_limit"]
    return p
