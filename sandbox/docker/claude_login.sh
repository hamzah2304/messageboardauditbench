#!/usr/bin/env bash
# One-time: log Claude Code in *inside the sandbox image*, so a Linux-format
# ~/.claude/.credentials.json exists. Kept in runs/.claude-home (gitignored) and
# copied into every trial by run_trial.sh. Interactive: run it in a real terminal.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"; IMAGE="${IMAGE:-mbab-sandbox}"
H="$ROOT/runs/.claude-home"; mkdir -p "$H"; chmod a+rwX "$H"
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -q -t "$IMAGE" -f "$HERE/Dockerfile" "$ROOT" >/dev/null
docker run -it --rm -v "$H:/home/agent/.claude" "$IMAGE" claude login
[ -f "$H/.credentials.json" ] && echo "ok: $H/.credentials.json" || { echo "login did not write credentials" >&2; exit 1; }
