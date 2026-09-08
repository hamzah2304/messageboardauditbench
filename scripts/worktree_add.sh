#!/usr/bin/env bash
# Create a linked task worktree inside the repo: .worktrees/<tool>-<task> on branch <tool>/<task>, from main.
#
#   scripts/worktree_add.sh <task> [claude|codex]      # tool defaults to claude
#   scripts/worktree_add.sh interrogate codex          # -> .worktrees/codex-interrogate on codex/interrogate
#
# The worktree gets symlinks to the primary checkout's gitignored inputs and outputs, so trials launched
# from it read the same data/ and land in the same runs/ (one archive, no drifting copies), plus its own
# .venv via `uv sync`. Prints the worktree path. See AGENTS.md for when to use one.
set -euo pipefail
TASK="${1:?task slug (lowercase letters, digits, hyphens)}"; TOOL="${2:-claude}"
[[ "$TASK" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || { echo "task must be a lowercase slug: $TASK" >&2; exit 2; }
[[ "$TOOL" =~ ^(claude|codex)$ ]] || { echo "tool must be claude or codex: $TOOL" >&2; exit 2; }
ROOT="$(git -C "$(dirname "$0")" rev-parse --path-format=absolute --git-common-dir)"; ROOT="$(dirname "$ROOT")"
WT="$ROOT/.worktrees/$TOOL-$TASK"; BRANCH="$TOOL/$TASK"
[ -e "$WT" ] && { echo "already exists: $WT" >&2; exit 1; }
mkdir -p "$ROOT/.worktrees"
if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$ROOT" worktree add --quiet "$WT" "$BRANCH"
else
  git -C "$ROOT" worktree add --quiet -b "$BRANCH" "$WT" main
fi
# Shared, gitignored state lives in the primary checkout only. data/ itself is tracked (checksums,
# .gitkeep files), so the built variants are linked underneath it: whole directories where the
# directory is ignored, file by file where only the contents are (raw_stripped, verbatim).
link() { [ -e "$1" ] && [ ! -e "$2" ] && ln -s "$1" "$2" || true; }
for p in runs logs .env data/raw data/augmented; do link "$ROOT/$p" "$WT/$p"; done
for v in raw_stripped verbatim; do
  for f in "$ROOT/data/$v"/*; do [ -e "$f" ] && link "$f" "$WT/data/$v/$(basename "$f")"; done
done
(cd "$WT" && uv sync --quiet 2>/dev/null) || echo "uv sync failed in $WT; run it by hand" >&2
echo "$WT"
