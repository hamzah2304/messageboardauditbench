"""Observable investigation metrics; heuristics are explicitly labelled."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool

_EMPTY_SEARCH = re.compile(r"^\s*(?:rg|grep)\b")
_TIME_FEEDBACK = re.compile(r"\btime budget:\s*(?:about\s+)?\d+", re.IGNORECASE)


def _command(call) -> str:
    """Return the executable text when a call carries one, otherwise empty."""
    arguments = call.arguments
    if not isinstance(arguments, dict):
        return ""
    for key in ("command", "cmd"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
    return ""


def _is_empty_search(call, result: ChatMessageTool) -> bool:
    """Recognise rg/grep's conventional exit 1 for an empty result set.

    This deliberately requires both a search command and the converted Codex
    exit-code marker.  A word such as ``grep`` in corpus output is not enough.
    """
    return (
        bool(_EMPTY_SEARCH.match(_command(call)))
        and result.error is not None
        and "exit code 1" in (result.error.message or "").lower()
    )


def trajectory_metrics(messages) -> dict:
    calls = {}
    batches = []
    for message in messages:
        if isinstance(message, ChatMessageAssistant) and message.tool_calls:
            batches.append(len(message.tool_calls))
            calls.update({call.id: call for call in message.tool_calls})
    failures = []
    empty_searches = []
    outputs = {}
    for message in messages:
        if isinstance(message, ChatMessageTool):
            text = message.text
            outputs[message.tool_call_id] = text
            if message.error:
                call = calls.get(message.tool_call_id)
                failure = {"id": message.tool_call_id, "tool": message.function,
                           "type": message.error.type, "message": message.error.message[:500]}
                if call is not None and _is_empty_search(call, message):
                    empty_searches.append(failure)
                else:
                    failures.append(failure)
    counts = Counter(call.function for call in calls.values())
    commands = [_command(call) or json.dumps(call.arguments, ensure_ascii=False) for call in calls.values()]
    feedback_messages = sum(
        _TIME_FEEDBACK.search(message.text or "") is not None
        for message in messages
    )
    return {
        "tool_calls_by_type": dict(sorted(counts.items())),
        "tool_calls": len(calls),
        "tool_errors": failures,
        "tool_error_count": len(failures),
        "empty_search_exit_1": len(empty_searches),
        "empty_searches_note": "rg/grep exit code 1 is a normal empty result, excluded from tool_error_count.",
        "max_tool_calls_in_assistant_message": max(batches, default=0),
        "multi_tool_messages": sum(n > 1 for n in batches),
        "parallelism_note": "Multiple calls in a message are potential concurrency, not proof of overlapping execution.",
        "network_command_mentions": sum(bool(re.search(r"\b(curl|wget)\b|requests\.(get|post)|urllib\.request|socket\.connect", c)) for c in commands),
        "network_mentions_note": "Command-text heuristic; mentions can quote corpus data and do not prove network access.",
        "time_check_commands": sum(bool(re.search(r"\b(date|time_left)\b", c)) for c in commands),
        "time_feedback_messages": feedback_messages,
        "time_feedback_note": "Counts explicit harness budget messages visible in converted transcript text; it does not show whether the model acted on every message.",
        "truncated_tool_outputs": sum("truncat" in t.lower() for t in outputs.values()),
        "truncation_note": "Text heuristic; corpus quotations can also mention truncation.",
        "no_match_exit_1": len(empty_searches),
    }


def corpus_audit(directory: Path) -> dict:
    files = {}
    field_sets = Counter()
    mixed = []
    for path in sorted(directory.glob('*.jsonl')):
        count = 0
        maximum = 0
        for line in path.open():
            row = json.loads(line)
            count += 1
            maximum = max(maximum, len(line))
            if path.name == 'labels.jsonl':
                field_sets[','.join(sorted(row))] += 1
                label = row.get('label', '')
                if re.search('[A-Za-z]', label) and re.search('[\u0400-\u04ff]', label):
                    mixed.append({'label': label, 'codepoints': [f'U+{ord(c):04X}' for c in label],
                                  'stored_revisions': row.get('stored_revisions')})
        files[path.name] = {'rows': count, 'bytes': path.stat().st_size, 'max_jsonl_line_chars': maximum}
    return {'files': files, 'label_field_sets': dict(field_sets), 'mixed_latin_cyrillic_labels': mixed}
