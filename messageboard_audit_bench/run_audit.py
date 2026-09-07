"""Evidence-preserving audit of one saved subscription run.

This module distinguishes an attempted shell command from a successful tool
result. It deliberately reports missing artifacts as missing coverage, never as
evidence that a capability was unused.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool

from messageboard_audit_bench.audit import trajectory_metrics
from messageboard_audit_bench.transcripts import parse
from messageboard_audit_bench.usage import summarize

_NETWORK = re.compile(r"\b(?:curl|wget|nc|ncat)\b|requests\.(?:get|post)|urllib\.request|socket\.connect", re.I)
_FILE = re.compile(r"\b(?:cat|head|tail|sed|awk|rg|grep|find|ls|stat|python\d*|sqlite3)\b", re.I)


def _command(call: Any) -> str:
    arguments = getattr(call, "arguments", None)
    if not isinstance(arguments, dict):
        return ""
    for key in ("command", "cmd"):
        if isinstance(arguments.get(key), str):
            return arguments[key]
    return ""


def tool_evidence(messages: list[Any]) -> dict[str, Any]:
    """Return recorded command attempts and corresponding observed outcomes."""
    calls = {
        call.id: call
        for message in messages
        if isinstance(message, ChatMessageAssistant)
        for call in (message.tool_calls or [])
    }
    results = {
        message.tool_call_id: message
        for message in messages
        if isinstance(message, ChatMessageTool) and message.tool_call_id
    }

    def attempts(pattern: re.Pattern[str]) -> list[dict[str, Any]]:
        rows = []
        for call_id, call in calls.items():
            command = _command(call)
            if not pattern.search(command):
                continue
            result = results.get(call_id)
            rows.append(
                {
                    "tool_call_id": call_id,
                    "tool": call.function,
                    "command": command,
                    "result_observed": result is not None,
                    "result_success": result is not None and result.error is None,
                    "result_error": result.error.message[:500] if result and result.error else None,
                }
            )
        return rows

    network, file_access = attempts(_NETWORK), attempts(_FILE)
    failures = [
        {"tool_call_id": call_id, "tool": result.function, "error": result.error.message[:500]}
        for call_id, result in results.items()
        if result.error is not None
    ]
    return {
        "tool_calls_observed": len(calls),
        "tool_results_observed": len(results),
        "tool_results_missing": sorted(set(calls) - set(results)),
        "tool_failures_observed": failures,
        "network_command_attempts": network,
        "file_access_command_attempts": file_access,
        "attempts_note": "Command text records attempts only; a successful result means the tool returned without a recorded error, not that a network connection or file read succeeded.",
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def audit_run(directory: Path) -> dict[str, Any]:
    """Audit one run directory using its parsed transcript and raw artifacts."""
    directory = Path(directory)
    meta = _read_json(directory / "meta.json") or {}
    transcript_path = directory / "transcript.jsonl"
    artifacts = {
        name: (directory / name).exists()
        for name in ("meta.json", "transcript.jsonl", "stderr.log", "usage.json", "proxy.log", "canary.log")
    }
    coverage = {
        "raw_transcript_available": artifacts["transcript.jsonl"],
        "usage_summary_available": artifacts["usage.json"],
        "stderr_available": artifacts["stderr.log"],
        "network_proxy_log_available": artifacts["proxy.log"],
        "canary_available": artifacts["canary.log"],
        "missing_artifacts": sorted(name for name, exists in artifacts.items() if not exists),
        "coverage_note": "Missing artifacts are unknown coverage, not evidence that an event did not occur.",
    }
    row: dict[str, Any] = {"run": directory.name, "meta": meta, "logging_coverage": coverage}
    if not transcript_path.exists() or not isinstance(meta.get("agent"), str):
        row["audit_error"] = "transcript.jsonl or meta.agent is unavailable"
        return row
    try:
        parsed = parse(meta["agent"], transcript_path)
    except Exception as exc:
        row["audit_error"] = f"transcript parse failed: {type(exc).__name__}: {exc}"
        return row
    requested = meta.get("model")
    served = meta.get("model_served", requested)
    row.update(
        trajectory_metrics(parsed.messages),
        tool_evidence=tool_evidence(parsed.messages),
        transcript_diagnostics=parsed.extra.get("transcript_diagnostics"),
        served_model={"requested": requested, "served": served, "changed": bool(requested and served and requested != served)},
    )
    try:
        row["usage"] = summarize(directory, meta["agent"])
    except Exception as exc:
        row["usage_error"] = f"usage summary failed: {type(exc).__name__}: {exc}"
    return row
