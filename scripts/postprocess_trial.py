#!/usr/bin/env python3
"""Finalize one subscription trial using only the Python standard library."""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "messageboard_audit_bench"))
from report_length import acceptance_limits, limits, measure  # noqa: E402


def _events(path: pathlib.Path) -> list[dict]:
    events = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _terminal_refusal(events: list[dict]) -> bool:
    """Recognize structured terminal refusal markers, never prose."""
    if not events:
        return False
    final = events[-1]
    if final.get("type") == "result" and final.get("stop_reason") in {
        "refusal",
        "content_filter",
    }:
        return True
    if any(event.get("subtype") == "model_refusal_no_fallback" for event in events):
        return True
    # The custom ReAct transcript ends with a synthetic result after the
    # provider response. Inspect the last assistant event before that result.
    assistants = [event for event in events if event.get("type") == "assistant"]
    if not assistants:
        return False
    return any(
        node.get("native_finish_reason") == "refusal"
        or node.get("finish_reason") == "content_filter"
        or node.get("stop_reason") in {"refusal", "content_filter"}
        for node in _walk(assistants[-1])
    )


def postprocess(run: pathlib.Path, returncode: int, wall_seconds: int) -> int:
    meta_path = run / "meta.json"
    meta = json.loads(meta_path.read_text())
    events = _events(run / "transcript.jsonl")
    report_path = run / "report.md"
    report_source = report_path if report_path.exists() else None
    report = report_source.read_text(errors="replace") if report_source else ""
    meta.update(
        exit_code=returncode,
        wall_seconds=wall_seconds,
        report_exists=report_path.exists(),
        report_source=str(report_source) if report_source else None,
    )
    meta.update(
        measure(
            report,
            *limits(meta),
            exists=bool(report),
            acceptance=acceptance_limits(meta),
        )
    )

    fallbacks = [
        event
        for event in events
        if event.get("type") == "system"
        and event.get("subtype") == "model_refusal_fallback"
    ]
    if fallbacks:
        meta["model_fallback"] = {
            "fallback_model": fallbacks[-1].get("fallback_model"),
            "trigger": fallbacks[0].get("trigger"),
            "category": fallbacks[0].get("api_refusal_category"),
            "events": len(fallbacks),
            "chain": [meta["model"]]
            + [event.get("fallback_model") for event in fallbacks],
        }
        meta["model_served"] = fallbacks[-1].get("fallback_model")

    if _terminal_refusal(events):
        meta["model_refusal"] = {"events": 1, "terminal": True}
        returncode = 5
        meta["exit_code"] = returncode

    usage_path = run / "usage.json"
    usage = json.loads(usage_path.read_text()) if usage_path.exists() else {}
    usage_keys = (
        "reasoning_tokens_source",
        "reasoning_tokens_estimated",
        "reasoning_items",
        "reasoning_encrypted_items",
        "reasoning_raw_chars",
        "reasoning_summary_chars",
        "usage_schema",
        "input_tokens",
        "input_tokens_uncached",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "cache_read_fraction",
        "reasoning_tokens",
        "cost_usd",
        "api_calls",
        "tool_calls",
        "api_retries",
        "api_errors",
        "peak_context_tokens",
        "terminal_reason",
        "is_error",
        "usage_source",
    )
    meta["usage"] = {key: usage.get(key) for key in usage_keys}
    meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta, indent=1))
    return returncode


if __name__ == "__main__":
    sys.exit(postprocess(pathlib.Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])))
