"""Loss-aware conversion of subscription CLI events into Inspect messages.

Native ``inspect`` runs do not use this module: Inspect SWE emits their events
directly. The converter is for the opt-in ``subscription`` backend and replaying
historical runs. It deliberately preserves unfamiliar events as visible text
and records diagnostics instead of silently dropping trajectory information.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageTool,
    ChatMessageUser,
    ContentReasoning,
    ContentText,
)
from inspect_ai.tool import ToolCall, ToolCallError

from messageboard_audit_bench.usage import summarize


@dataclass
class Parsed:
    messages: list[ChatMessage] = field(default_factory=list)
    input_tokens: int = 0
    input_tokens_uncached: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    turns: int = 0
    tool_calls: int = 0
    cost_usd: float | None = None
    duration_ms: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Diagnostics:
    source_lines: int = 0
    blank_lines: int = 0
    malformed_json: int = 0
    non_object_events: int = 0
    unknown_events: Counter[str] = field(default_factory=Counter)
    unknown_items: Counter[str] = field(default_factory=Counter)
    auxiliary_events: Counter[str] = field(default_factory=Counter)
    duplicate_blocks: int = 0
    renamed_duplicate_tool_ids: int = 0
    synthetic_call_ids: int = 0
    orphan_tool_results: int = 0
    incomplete_tool_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_lines": self.source_lines,
            "blank_lines": self.blank_lines,
            "malformed_json": self.malformed_json,
            "non_object_events": self.non_object_events,
            "unknown_events": dict(sorted(self.unknown_events.items())),
            "unknown_items": dict(sorted(self.unknown_items.items())),
            "auxiliary_events": dict(sorted(self.auxiliary_events.items())),
            "duplicate_blocks": self.duplicate_blocks,
            "renamed_duplicate_tool_ids": self.renamed_duplicate_tool_ids,
            "synthetic_call_ids": self.synthetic_call_ids,
            "orphan_tool_results": self.orphan_tool_results,
            "incomplete_tool_calls": self.incomplete_tool_calls,
        }


def _lines(path: Path, diagnostics: _Diagnostics) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            diagnostics.source_lines += 1
            line = line.strip()
            if not line:
                diagnostics.blank_lines += 1
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.malformed_json += 1
                continue
            if not isinstance(event, dict):
                diagnostics.non_object_events += 1
                continue
            yield event


def _text(value: Any) -> str:
    """Render structured CLI output without Python repr noise."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(_text(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _visible_event(label: str, payload: Any) -> ChatMessageAssistant:
    body = _text(payload)
    return ChatMessageAssistant(
        content=[ContentText(text=f"[{label}]" + (f" {body}" if body else ""))]
    )


def _visible_user(label: str, payload: Any) -> ChatMessageUser:
    body = _text(payload)
    return ChatMessageUser(
        content=[ContentText(text=f"[{label}]" + (f" {body}" if body else ""))]
    )


def _finish_diagnostics(parsed: Parsed, diagnostics: _Diagnostics) -> None:
    calls = Counter()
    results = Counter()
    for message in parsed.messages:
        if isinstance(message, ChatMessageAssistant):
            calls.update(call.id for call in message.tool_calls or [])
        elif isinstance(message, ChatMessageTool) and message.tool_call_id:
            results[message.tool_call_id] += 1
    parsed.extra["transcript_diagnostics"] = {
        **diagnostics.as_dict(),
        "message_count": len(parsed.messages),
        "tool_call_ids": sum(calls.values()),
        "tool_result_ids": sum(results.values()),
        "unmatched_tool_calls": sorted((calls - results).elements()),
        "unmatched_tool_results": sorted((results - calls).elements()),
        "duplicate_tool_call_ids": sorted(k for k, v in calls.items() if v > 1),
        "duplicate_tool_result_ids": sorted(k for k, v in results.items() if v > 1),
    }


# ---------------------------------------------------------------- Claude Code

def parse_claude(path: Path) -> Parsed:
    parsed = Parsed()
    diagnostics = _Diagnostics()
    current_id: str | None = None
    current: ChatMessageAssistant | None = None
    current_blocks: set[str] = set()
    tool_names: dict[str, str] = {}
    call_counts: Counter[str] = Counter()
    pending_call_ids: defaultdict[str, deque[str]] = defaultdict(deque)
    open_calls: set[str] = set()
    usage_by_message: dict[str, dict[str, Any]] = {}
    rate_limits: list[dict[str, Any]] = []
    synthetic = 0

    def new_id(prefix: str) -> str:
        nonlocal synthetic
        synthetic += 1
        diagnostics.synthetic_call_ids += 1
        return f"{prefix}_{synthetic}"

    def flush() -> None:
        nonlocal current, current_blocks
        if current is not None and (current.content or current.tool_calls):
            parsed.messages.append(current)
        current = None
        current_blocks = set()

    for event in _lines(path, diagnostics):
        event_type = str(event.get("type", "<missing>"))
        if event_type == "assistant":
            message = event.get("message")
            if not isinstance(message, dict):
                diagnostics.unknown_events["assistant_without_message"] += 1
                flush()
                parsed.messages.append(_visible_event("malformed Claude assistant event", event))
                continue
            message_id = str(message.get("id") or new_id("claude_message"))
            if current is None or message_id != current_id:
                flush()
                current_id = message_id
                current = ChatMessageAssistant(
                    id=message_id,
                    content=[],
                    tool_calls=[],
                    model=message.get("model"),
                    metadata={
                        "parent_tool_use_id": event.get("parent_tool_use_id")
                    } if event.get("parent_tool_use_id") else None,
                )
                parsed.turns += 1
            usage = message.get("usage")
            if isinstance(usage, dict):
                usage_by_message[message_id] = usage
            content = message.get("content", [])
            if not isinstance(content, list):
                content = [content]
            for block in content:
                if not isinstance(block, dict):
                    block = {"type": "unknown", "value": block}
                kind = str(block.get("type", "<missing>"))
                # Repeated tool blocks with the same id are verbose-stream
                # retransmissions. Identical text/reasoning blocks can be
                # intentional and must remain visible.
                fingerprint = json.dumps(block, ensure_ascii=False, sort_keys=True)
                if kind == "tool_use":
                    if fingerprint in current_blocks:
                        diagnostics.duplicate_blocks += 1
                        continue
                    current_blocks.add(fingerprint)
                if kind == "text" and block.get("text") is not None:
                    current.content.append(ContentText(text=_text(block.get("text"))))
                elif kind == "thinking":
                    current.content.append(
                        ContentReasoning(reasoning=_text(block.get("thinking")))
                    )
                elif kind == "redacted_thinking":
                    current.content.append(
                        ContentReasoning(
                            reasoning="[redacted reasoning]",
                            redacted=True,
                            signature=block.get("data"),
                        )
                    )
                elif kind == "tool_use":
                    source_call_id = str(block.get("id") or new_id("claude_tool"))
                    call_counts[source_call_id] += 1
                    occurrence = call_counts[source_call_id]
                    call_id = (
                        source_call_id
                        if occurrence == 1
                        else f"{source_call_id}__{occurrence}"
                    )
                    if occurrence > 1:
                        diagnostics.renamed_duplicate_tool_ids += 1
                    function = str(block.get("name") or "tool")
                    arguments = block.get("input")
                    if not isinstance(arguments, dict):
                        arguments = {"value": arguments}
                    tool_names[call_id] = function
                    pending_call_ids[source_call_id].append(call_id)
                    open_calls.add(call_id)
                    current.tool_calls.append(
                        ToolCall(id=call_id, function=function, arguments=arguments)
                    )
                    parsed.tool_calls += 1
                elif kind == "fallback":
                    fallback = {"from": block.get("from"), "to": block.get("to")}
                    parsed.extra.setdefault("model_fallbacks", []).append(fallback)
                    current.content.append(
                        ContentText(text=f"[Claude model fallback] {_text(fallback)}")
                    )
                else:
                    diagnostics.unknown_items[f"claude_content:{kind}"] += 1
                    current.content.append(
                        ContentText(text=f"[unmapped Claude content: {kind}] {_text(block)}")
                    )
        elif event_type == "user":
            flush()
            current_id = None
            message = event.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            if not isinstance(content, list):
                content = [content]
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    if _text(block):
                        parsed.messages.append(_visible_user("Claude user", block))
                    continue
                source_call_id = str(
                    block.get("tool_use_id") or new_id("claude_orphan")
                )
                call_id = (
                    pending_call_ids[source_call_id].popleft()
                    if pending_call_ids[source_call_id]
                    else source_call_id
                )
                if call_id not in tool_names:
                    diagnostics.orphan_tool_results += 1
                    tool_names[call_id] = "tool"
                    parsed.messages.append(
                        ChatMessageAssistant(
                            content=[],
                            tool_calls=[ToolCall(id=call_id, function="tool", arguments={})],
                        )
                    )
                    parsed.tool_calls += 1
                is_error = bool(block.get("is_error"))
                parsed.messages.append(
                    ChatMessageTool(
                        content=_text(block.get("content")),
                        tool_call_id=call_id,
                        function=tool_names[call_id],
                        error=ToolCallError(type="unknown", message="CLI tool error")
                        if is_error else None,
                    )
                )
                open_calls.discard(call_id)
        elif event_type == "system":
            subtype = str(event.get("subtype", "system"))
            # Init data is useful provenance but not a trajectory turn.
            if subtype == "init":
                parsed.extra["claude_init"] = {
                    key: event.get(key)
                    for key in ("claude_code_version", "model", "session_id", "tools")
                    if event.get(key) is not None
                }
            else:
                diagnostics.auxiliary_events[f"system:{subtype}"] += 1
                # Preserve important lifecycle failures visibly; high-volume
                # progress/telemetry remains available as a diagnostic count.
                if subtype in {
                    "api_retry",
                    "model_refusal_fallback",
                    "model_refusal_no_fallback",
                    "compact_boundary",
                }:
                    parsed.messages.append(_visible_event(f"Claude system {subtype}", event))
        elif event_type == "rate_limit_event":
            info = event.get("rate_limit_info")
            if isinstance(info, dict):
                rate_limits.append(info)
        elif event_type == "result":
            flush()
            parsed.cost_usd = event.get("total_cost_usd")
            parsed.duration_ms = event.get("duration_ms")
            parsed.extra["result_subtype"] = event.get("subtype")
            parsed.extra["num_turns_reported"] = event.get("num_turns")
            parsed.extra["result_is_error"] = event.get("is_error")
            if event.get("result"):
                parsed.extra["result_text"] = _text(event.get("result"))
            usage = event.get("usage") or {}
            if isinstance(usage, dict) and usage:
                parsed.input_tokens = int(usage.get("input_tokens", 0) or 0)
                parsed.output_tokens = int(usage.get("output_tokens", 0) or 0)
                parsed.cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
                parsed.cache_write_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
        elif event_type == "fallback":
            parsed.extra.setdefault("model_fallbacks", []).append(
                {"from": event.get("from"), "to": event.get("to")}
            )
            parsed.messages.append(_visible_event("Claude model fallback", event))
        elif event_type == "tool_progress":
            diagnostics.auxiliary_events[event_type] += 1
        elif event_type in {"error", "stream_event"}:
            # stream_event payloads are duplicated transport detail in --verbose
            # output; errors are retained visibly.
            if event_type == "error":
                parsed.messages.append(_visible_event("Claude error", event))
            else:
                diagnostics.auxiliary_events[event_type] += 1
        else:
            diagnostics.unknown_events[event_type] += 1
            parsed.messages.append(_visible_event(f"unmapped Claude event: {event_type}", event))

    flush()
    for call_id in sorted(open_calls):
        diagnostics.incomplete_tool_calls += 1
        parsed.messages.append(
            ChatMessageTool(
                content="Tool call did not complete before the transcript ended.",
                tool_call_id=call_id,
                function=tool_names.get(call_id, "tool"),
                error=ToolCallError(type="cancelled", message="transcript ended"),
            )
        )
    if not parsed.input_tokens:
        for usage in usage_by_message.values():
            parsed.input_tokens += int(usage.get("input_tokens", 0) or 0)
            parsed.output_tokens += int(usage.get("output_tokens", 0) or 0)
            parsed.cache_read_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
            parsed.cache_write_tokens += int(usage.get("cache_creation_input_tokens", 0) or 0)
    if rate_limits:
        parsed.extra["last_rate_limit"] = rate_limits[-1]
    _finish_diagnostics(parsed, diagnostics)
    return parsed


# --------------------------------------------------------------------- Codex

_CODEX_TOOL_ITEMS = {
    "command_execution": "bash",
    "file_change": "apply_patch",
    "collab_tool_call": "collab_tool",
    "mcp_tool_call": "mcp_tool",
    "web_search": "web_search",
}


def _codex_tool(item: dict[str, Any], serial: int) -> tuple[ToolCall, ChatMessageTool]:
    kind = str(item.get("type"))
    call_id = str(item.get("id") or f"codex_item_{serial}")
    function = _CODEX_TOOL_ITEMS[kind]
    if kind == "command_execution":
        arguments = {"command": item.get("command", "")}
        output = _text(item.get("aggregated_output"))
        exit_code = item.get("exit_code")
        error = None
        if exit_code not in (0, None):
            output += f"\n[exit code {exit_code}]"
            error = ToolCallError(type="unknown", message=f"exit code {exit_code}")
    elif kind == "file_change":
        changes = item.get("changes") or []
        arguments = {"changes": changes}
        output = "\n".join(
            f"{change.get('kind', 'change')} {change.get('path', '')}"
            for change in changes if isinstance(change, dict)
        )
        error = None
    elif kind == "collab_tool_call":
        function = str(item.get("tool") or function)
        arguments = {
            key: item.get(key)
            for key in ("prompt", "receiver_thread_ids")
            if item.get(key) is not None
        }
        output = _text(item.get("agents_states") or item.get("status"))
        error = None
    elif kind == "mcp_tool_call":
        function = str(item.get("tool") or item.get("name") or function)
        arguments = item.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        output = _text(item.get("result") or item.get("output"))
        error = None
    else:
        arguments = {key: value for key, value in item.items() if key not in {"id", "type", "status"}}
        output = _text(item.get("result") or item.get("query") or item.get("status"))
        error = None
    if str(item.get("status", "")).lower() in {"failed", "error", "cancelled"} and error is None:
        status = str(item.get("status"))
        error = ToolCallError(
            type="cancelled" if status == "cancelled" else "unknown",
            message=status,
        )
    return (
        ToolCall(id=call_id, function=function, arguments=arguments),
        ChatMessageTool(
            content=output,
            tool_call_id=call_id,
            function=function,
            error=error,
        ),
    )


def parse_codex(path: Path) -> Parsed:
    parsed = Parsed()
    diagnostics = _Diagnostics()
    pending: dict[str, dict[str, Any]] = {}
    emitted: set[str] = set()
    serial = 0

    def emit(item: dict[str, Any], *, incomplete: bool = False) -> None:
        nonlocal serial
        serial += 1
        kind = str(item.get("type", "<missing>"))
        item_id = str(item.get("id") or f"codex_item_{serial}")
        if item_id in emitted:
            diagnostics.duplicate_blocks += 1
            return
        emitted.add(item_id)
        if kind in _CODEX_TOOL_ITEMS:
            call, result = _codex_tool(item, serial)
            if incomplete:
                diagnostics.incomplete_tool_calls += 1
                result.content = (_text(result.content) + "\n[tool call incomplete]").strip()
                result.error = ToolCallError(type="cancelled", message="transcript ended")
            parsed.messages.extend(
                [ChatMessageAssistant(content=[], tool_calls=[call]), result]
            )
            parsed.tool_calls += 1
            parsed.turns += 1
        elif kind == "agent_message":
            parsed.messages.append(
                ChatMessageAssistant(content=[ContentText(text=_text(item.get("text")))])
            )
            parsed.turns += 1
        elif kind == "reasoning":
            parsed.messages.append(
                ChatMessageAssistant(
                    content=[ContentReasoning(reasoning=_text(item.get("text")))]
                )
            )
        elif kind in {"todo_list", "plan_update"}:
            parsed.messages.append(_visible_event(f"Codex {kind}", item))
        elif kind == "error":
            parsed.messages.append(_visible_event("Codex error", item.get("message") or item))
        else:
            diagnostics.unknown_items[kind] += 1
            parsed.messages.append(_visible_event(f"unmapped Codex item: {kind}", item))

    for event in _lines(path, diagnostics):
        event_type = str(event.get("type", "<missing>"))
        if event_type in {"item.started", "item.updated"}:
            item = event.get("item")
            if isinstance(item, dict):
                item_id = str(item.get("id") or f"pending_{len(pending) + 1}")
                pending[item_id] = {**pending.get(item_id, {}), **item}
            else:
                diagnostics.unknown_events[f"{event_type}_without_item"] += 1
        elif event_type == "item.completed":
            item = event.get("item")
            if not isinstance(item, dict):
                diagnostics.unknown_events["item.completed_without_item"] += 1
                parsed.messages.append(_visible_event("malformed Codex completed item", event))
                continue
            item_id = str(item.get("id") or "")
            if item_id and item_id in pending:
                item = {**pending.pop(item_id), **item}
            emit(item)
        elif event_type == "turn.completed":
            usage = event.get("usage") or {}
            if isinstance(usage, dict):
                parsed.input_tokens += int(usage.get("input_tokens", 0) or 0)
                parsed.output_tokens += int(usage.get("output_tokens", 0) or 0)
                parsed.cache_read_tokens += int(usage.get("cached_input_tokens", 0) or 0)
                parsed.cache_write_tokens += int(usage.get("cache_write_input_tokens", 0) or 0)
                parsed.reasoning_tokens += int(usage.get("reasoning_output_tokens", 0) or 0)
        elif event_type in {"thread.started", "turn.started"}:
            if event_type == "thread.started" and event.get("thread_id"):
                parsed.extra["codex_thread_id"] = event["thread_id"]
        elif event_type in {"turn.failed", "error"}:
            parsed.messages.append(_visible_event(f"Codex {event_type}", event.get("error") or event.get("message") or event))
        else:
            diagnostics.unknown_events[event_type] += 1
            parsed.messages.append(_visible_event(f"unmapped Codex event: {event_type}", event))

    for item in pending.values():
        emit(item, incomplete=True)
    _finish_diagnostics(parsed, diagnostics)
    return parsed


def parse(agent: str, path: Path) -> Parsed:
    """Parse a subscription transcript and apply the benchmark's canonical usage totals."""
    # react_agent.py deliberately writes the Claude Code dialect.
    parsed = parse_codex(path) if agent == "codex" else parse_claude(path)
    usage = summarize(path.parent, agent)
    parsed.input_tokens = usage["input_tokens"]
    parsed.input_tokens_uncached = usage["input_tokens_uncached"]
    parsed.output_tokens = usage["output_tokens"]
    parsed.cache_read_tokens = usage["cache_read_tokens"]
    parsed.cache_write_tokens = usage["cache_write_tokens"]
    parsed.reasoning_tokens = usage["reasoning_tokens"]
    parsed.cost_usd = usage.get("cost_usd", parsed.cost_usd)
    parsed.duration_ms = usage.get("duration_ms") or parsed.duration_ms
    for key in (
        "usage_schema", "usage_source", "api_calls", "api_retries", "api_errors",
        "peak_context_tokens", "cache_read_fraction", "stop_reason", "terminal_reason",
        "is_error", "duration_api_ms", "ttft_ms", "thinking_blocks", "thinking_chars",
        "reasoning_tokens_estimated", "reasoning_items", "reasoning_summary_chars",
        "latency_ms_mean", "permission_denials",
    ):
        if usage.get(key) is not None:
            parsed.extra[key] = usage[key]
    if usage.get("last_rate_limit"):
        parsed.extra["last_rate_limit"] = usage["last_rate_limit"]
    return parsed
