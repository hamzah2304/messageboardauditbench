#!/usr/bin/env python3
"""Claude Code WorktreeCreate hook: route EnterWorktree through scripts/worktree_add.sh.

Reads {"name": ..., "cwd": ...} on stdin, creates .worktrees/claude-<name> on claude/<name>
from main with the shared-state symlinks, and prints the worktree path.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        name = payload["name"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"error: WorktreeCreate input must be JSON with a name: {exc}", file=sys.stderr)
        return 2
    result = subprocess.run(
        [str(ROOT / "scripts" / "worktree_add.sh"), name, "claude"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return 2
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
