#!/usr/bin/env python3
"""Audit CLI-to-Inspect conversion across completed benchmark runs."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from messageboard_audit_bench.transcripts import parse_claude, parse_codex


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path, help="directory containing run directories")
    args = parser.parse_args()

    totals: Counter[str] = Counter()
    auxiliary: Counter[str] = Counter()
    problems: list[str] = []
    checked = 0
    for run_dir in sorted(args.runs.iterdir()):
        transcript = run_dir / "transcript.jsonl"
        meta_path = run_dir / "meta.json"
        if not transcript.is_file() or not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError) as error:
            problems.append(f"{run_dir.name}: unreadable meta.json: {error}")
            continue
        if meta.get("exit_code") != 0:
            continue
        agent = meta.get("agent", "claude")
        try:
            parsed = (
                parse_codex(transcript)
                if agent == "codex"
                else parse_claude(transcript)
            )
        except Exception as error:  # noqa: BLE001 - audit must identify every bad run
            problems.append(f"{run_dir.name}: parser failed: {error!r}")
            continue

        checked += 1
        diagnostics = parsed.extra["transcript_diagnostics"]
        for key in (
            "malformed_json",
            "non_object_events",
            "duplicate_blocks",
            "renamed_duplicate_tool_ids",
            "synthetic_call_ids",
            "orphan_tool_results",
            "incomplete_tool_calls",
        ):
            totals[key] += diagnostics[key]
        auxiliary.update(diagnostics["auxiliary_events"])
        fatal = {
            key: diagnostics[key]
            for key in (
                "malformed_json",
                "non_object_events",
                "unknown_events",
                "unknown_items",
                "unmatched_tool_calls",
                "unmatched_tool_results",
                "duplicate_tool_call_ids",
                "duplicate_tool_result_ids",
            )
            if diagnostics[key]
        }
        if fatal:
            problems.append(f"{run_dir.name}: {fatal}")

    print(json.dumps({
        "completed_runs_checked": checked,
        "problems": problems,
        "repairs_and_warnings": dict(totals),
        "known_auxiliary_events": dict(auxiliary),
    }, indent=2, sort_keys=True))
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
