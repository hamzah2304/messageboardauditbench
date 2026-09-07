#!/usr/bin/env python3
"""Append one CLI lifecycle-hook observation without affecting hook output.

The payload is deliberately retained verbatim: hook schemas vary by CLI version,
and normalizing only selected keys would discard tool arguments or results. This
is a tool-lifecycle timestamp, not a provider/model-emission timestamp.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import sys
import time
from pathlib import Path


def _first_key(value: object, names: tuple[str, ...]) -> object | None:
    if isinstance(value, dict):
        for name in names:
            if value.get(name) is not None:
                return value[name]
        for child in value.values():
            found = _first_key(child, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_key(child, names)
            if found is not None:
                return found
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, choices=("PreToolUse", "PostToolUse", "PostToolUseFailure"))
    parser.add_argument("--path", type=Path, default=Path("/tmp/mbab-tool-events.jsonl"))
    args = parser.parse_args()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        payload = {"_unparsed_stdin": raw}
    tool_call_id = _first_key(payload, ("tool_use_id", "tool_call_id", "toolUseId"))
    tool_name = _first_key(payload, ("tool_name", "toolName"))
    record = {
        "schema": 1,
        "source": "cli_hook",
        "event": args.event,
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        "pid": os.getpid(),
        "tool_call_id": str(tool_call_id) if tool_call_id is not None else None,
        "tool_name": str(tool_name) if tool_name is not None else None,
        "payload": payload,
    }
    # Serialize full payloads even when parallel tools produce large results.
    # Do not contaminate the CLI hook stdout.
    fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        data = memoryview((json.dumps(record, ensure_ascii=False) + "\n").encode())
        while data:
            data = data[os.write(fd, data):]
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
