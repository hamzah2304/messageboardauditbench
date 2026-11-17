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
# A task branch starts from local main; say so when main is behind origin (a stale base is easy to miss).
if git -C "$ROOT" fetch --quiet origin main 2>/dev/null; then
  behind="$(git -C "$ROOT" rev-list --count main..origin/main 2>/dev/null || echo 0)"
  [ "$behind" = 0 ] || echo "warning: local main is $behind commit(s) behind origin/main; fast-forward it (git merge --ff-only origin/main) before branching" >&2
fi
if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$ROOT" worktree add --quiet "$WT" "$BRANCH"
else
  git -C "$ROOT" worktree add --quiet -b "$BRANCH" "$WT" main
fi
# The worktree's own environment first: listing the data variants imports the package.
(cd "$WT" && uv sync --quiet 2>/dev/null) || { echo "uv sync failed in $WT; run it by hand, then link data/ (see below)" >&2; exit 1; }
# Shared, gitignored state lives in the primary checkout only. data/ itself is tracked (checksums,
# .gitkeep files), so the built variants are linked underneath it: whole directories where the
# directory is ignored, file by file where only the contents are (raw_stripped, verbatim, verbatim_anthropic).
link() { [ -e "$1" ] && [ ! -e "$2" ] && ln -s "$1" "$2" || true; }
for p in runs logs .env data/raw data/aivillage data/augmented data/transluce data/urlquery; do link "$ROOT/$p" "$WT/$p"; done
variants="$(cd "$WT" && .venv/bin/python -c \
  'from slopvestigator_bench.incidents import data_variants; print(*sorted(data_variants()), sep="\n")')" \
  || { echo "could not list the data variants in $WT; data/ is not linked" >&2; exit 1; }
built=0; linked=0
while IFS= read -r v; do
  [ -d "$ROOT/data/$v" ] || continue
  built=$((built + 1))
  if [ ! -e "$WT/data/$v" ]; then
    link "$ROOT/data/$v" "$WT/data/$v"
  else
    for f in "$ROOT/data/$v"/*; do
      [ -e "$f" ] && link "$f" "$WT/data/$v/$(basename "$f")"
    done
  fi
  compgen -G "$WT/data/$v/*" >/dev/null && linked=$((linked + 1))
done <<< "$variants"
if [ "$built" -eq 0 ]; then
  echo "warning: the primary checkout has no built data variants; run scripts/build_data.sh there" >&2
elif [ "$linked" -lt "$built" ]; then
  echo "linked only $linked of the $built built data variants into $WT/data" >&2; exit 1
fi
echo "$WT"
