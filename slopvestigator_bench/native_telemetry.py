"""Coverage checks for future native Inspect event logs.

Inspect's event stream is the authoritative trajectory: this module does not
reconstruct missing provider data. It reports whether a decoded sample retained
the raw model calls and the timing/correlation fields needed to audit it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any


def _value(event: object, name: str) -> Any:
    if isinstance(event, Mapping):
        return event.get(name)
    return getattr(event, name, None)


def _event_dict(event: object) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return dict(event) if isinstance(event, Mapping) else {}


def _maximum_overlap(intervals: list[tuple[str, str]]) -> int:
    """Return overlap of wall-clock event intervals; it is not a concurrency claim."""
    points: list[tuple[datetime, int]] = []
    for start, end in intervals:
        try:
            points.extend(
                ((datetime.fromisoformat(start), 1), (datetime.fromisoformat(end), -1))
            )
        except (TypeError, ValueError):
            continue
    active = maximum = 0
    # Ends sort before starts at a shared timestamp, avoiding a false overlap.
    for _, delta in sorted(points, key=lambda point: (point[0], point[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def _has_reasoning_content(output: Mapping[str, Any]) -> bool:
    for choice in output.get("choices") or []:
        message = choice.get("message") if isinstance(choice, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if any(
            isinstance(item, Mapping) and item.get("type") == "reasoning"
            for item in content or []
        ):
            return True
    return False


def event_coverage(events: Iterable[object]) -> dict[str, Any]:
    """Summarize native event-log evidence without treating absent data as zero.

    ``raw_model_api_complete`` is false when a model event lacks ``call``. The
    usual cause is running Inspect without ``--log-model-api``. Provider-specific
    reasoning is separately counted because a provider may legitimately expose
    neither text nor a token field.
    """
    model_events: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    sandbox_events: list[dict[str, Any]] = []
    for event in events:
        data = _event_dict(event)
        kind = data.get("event") or _value(event, "event")
        if kind == "model":
            model_events.append(data)
        elif kind == "tool":
            tool_events.append(data)
        elif kind == "sandbox":
            sandbox_events.append(data)

    model_intervals = [
        (event.get("timestamp"), event.get("completed"))
        for event in model_events
        if event.get("timestamp") and event.get("completed")
    ]

    def timestamped(event: Mapping[str, Any]) -> bool:
        return bool(event.get("timestamp") and event.get("completed"))

    return {
        "native_telemetry_schema": 1,
        "model_event_count": len(model_events),
        "tool_event_count": len(tool_events),
        "sandbox_event_count": len(sandbox_events),
        "raw_model_api_complete": bool(model_events)
        and all(event.get("call") is not None for event in model_events),
        "model_timestamps_complete": bool(model_events)
        and all(timestamped(event) for event in model_events),
        # Inspect ToolEvent timing covers framework tool execution. It does not
        # establish an internal Claude/Codex CLI command's lifecycle.
        "inspect_tool_timestamps_complete": bool(tool_events)
        and all(timestamped(event) for event in tool_events),
        "inspect_tool_correlation_complete": bool(tool_events)
        and all(event.get("id") and event.get("span_id") for event in tool_events),
        "inspect_tool_inputs_complete": bool(tool_events)
        and all(event.get("arguments") is not None for event in tool_events),
        "inspect_tool_results_complete": bool(tool_events)
        and all("result" in event and "error" in event for event in tool_events),
        "model_error_fields_complete": bool(model_events)
        and all("error" in event and "retries" in event for event in model_events),
        "reasoning_text_model_events": sum(
            _has_reasoning_content(event.get("output") or {}) for event in model_events
        ),
        "reasoning_token_model_events": sum(
            "reasoning_tokens" in ((event.get("output") or {}).get("usage") or {})
            for event in model_events
        ),
        "max_observed_model_event_overlap": _maximum_overlap(model_intervals),
    }


def hook_coverage(
    records: Iterable[Mapping[str, Any]], expected_call_ids: Iterable[str] | None = None
) -> dict[str, Any]:
    """Validate CLI observations without inventing missing completion times.

    Hook intervals include CLI hook dispatch overhead. They establish overlap of
    tool lifecycles, not exact child-process CPU time. Correlation against the
    provider trajectory catches a deleted hook file or a CLI tool with no hook.
    """
    rows = list(records)
    starts: dict[str, list] = {}
    ends: dict[str, list] = {}
    for row in rows:
        call_id = row.get("tool_call_id")
        if not call_id:
            continue
        target = starts if row.get("event") == "PreToolUse" else ends
        target.setdefault(str(call_id), []).append(row)
    paired_ids = starts.keys() & ends.keys()
    valid = all(
        row.get("source") == "cli_hook"
        and row.get("event") in {"PreToolUse", "PostToolUse", "PostToolUseFailure"}
        and row.get("timestamp_utc")
        and isinstance(row.get("monotonic_ns"), int)
        and "payload" in row
        for row in rows
    )
    intervals = []
    for call_id in sorted(paired_ids):
        if len(starts[call_id]) != 1 or len(ends[call_id]) != 1:
            valid = False
            continue
        start, end = starts[call_id][0], ends[call_id][0]
        begin, finish = start.get("monotonic_ns"), end.get("monotonic_ns")
        if not isinstance(begin, int) or not isinstance(finish, int) or finish < begin:
            valid = False
            continue
        intervals.append(
            {
                "tool_call_id": call_id,
                "tool_name": start.get("tool_name"),
                "started_utc": start["timestamp_utc"],
                "ended_utc": end["timestamp_utc"],
                "started_monotonic_ns": begin,
                "ended_monotonic_ns": finish,
                "duration_ms": (finish - begin) / 1e6,
                "completion_event": end.get("event"),
            }
        )
    points = [(row["started_monotonic_ns"], 1) for row in intervals]
    points += [(row["ended_monotonic_ns"], -1) for row in intervals]
    active = maximum = 0
    for _, change in sorted(points):
        active += change
        maximum = max(maximum, active)
    expected = set(expected_call_ids) if expected_call_ids is not None else None
    unobserved = sorted(expected - starts.keys()) if expected is not None else None
    pre_count = sum(row.get("event") == "PreToolUse" for row in rows)
    post_count = len(rows) - pre_count
    return {
        "tool_hook_telemetry_schema": 2,
        "tool_hook_event_count": len(rows),
        "tool_hook_pre_count": pre_count,
        "tool_hook_post_count": post_count,
        "tool_hook_records_valid": bool(rows) and valid,
        "tool_hook_lifecycle_pairs_observed": len(paired_ids),
        "tool_hook_lifecycle_complete": bool(rows)
        and valid
        and not unobserved
        and pre_count == post_count == len(intervals),
        "tool_hook_correlated_event_count": sum(
            bool(row.get("tool_call_id")) for row in rows
        ),
        "tool_hook_correlated_pair_count": len(paired_ids),
        "tool_hook_uncorrelated_event_count": sum(
            not row.get("tool_call_id") for row in rows
        ),
        "tool_hook_missing_start_ids": sorted(ends.keys() - starts.keys()),
        "tool_hook_missing_end_ids": sorted(starts.keys() - ends.keys()),
        "tool_hook_unobserved_requested_ids": unobserved,
        "tool_hook_intervals": intervals,
        "tool_hook_max_observed_overlap": maximum,
    }
