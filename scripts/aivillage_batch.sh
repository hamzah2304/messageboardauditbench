#!/usr/bin/env bash
# Run a batch of AI Village trials (prompt v3.17, 30 minutes) on this machine, Linux or macOS.
#
#   scripts/aivillage_batch.sh --replicates "3" [--claude 3] [--codex 3] [--react 5] [--sync-to fuzzy]
#
# Builds one queue per subscription from the model lists below (Claude and Codex models with and
# without subagents, OpenRouter models without: they have no subagent tool), runs each queue with
# the given number in flight, and records progress in logs/aivillage-batch/<started>/done.txt.
# Replicate 1 of everything runs before replicate 2, alternating conditions. --sync-to HOST copies
# the finished runs to HOST:Dev/MessageBoardAuditBench/runs/ (never the Claude token).
set -euo pipefail
cd "$(dirname "$0")/.."

CLAUDE_MODELS=(claude-opus-5 claude-opus-4-8 claude-opus-4-6 claude-sonnet-5-5)
CODEX_MODELS=(gpt-6-astra gpt-6.1-sol gpt-6-luna)
REACT_MODELS=(google/gemini-3.8-flash meta/muse-spark-1.3 moonshotai/kimi-k3 z-ai/glm-5.3 deepseek/deepseek-v4-flash)
CONFIG=aivillage-v12-30
REPLICATES="1"; P_CLAUDE=3; P_CODEX=3; P_REACT=5; SYNC_TO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --replicates) REPLICATES="$2"; shift 2 ;;
    --claude) P_CLAUDE="$2"; shift 2 ;;
    --codex) P_CODEX="$2"; shift 2 ;;
    --react) P_REACT="$2"; shift 2 ;;
    --sync-to) SYNC_TO="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

OUT="logs/aivillage-batch/$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"; : > "$OUT/done.txt"
for r in $REPLICATES; do
  for m in "${CLAUDE_MODELS[@]}"; do for c in "$CONFIG" "$CONFIG-subagents"; do echo "$c claude $m $r"; done; done
done > "$OUT/claude.txt"
for r in $REPLICATES; do
  for m in "${CODEX_MODELS[@]}"; do for c in "$CONFIG" "$CONFIG-subagents"; do echo "$c codex $m $r"; done; done
done > "$OUT/codex.txt"
for r in $REPLICATES; do for m in "${REACT_MODELS[@]}"; do echo "$CONFIG react $m $r"; done; done > "$OUT/react.txt"

set -a; [ -f .env ] && . ./.env; set +a
[ -f .venv/bin/activate ] && . .venv/bin/activate   # the runner's helpers need python3 >= 3.11
# On Linux the user may need the docker group through sg; macOS Docker Desktop needs nothing.
if docker info >/dev/null 2>&1; then DOCKER_WRAP=""; else DOCKER_WRAP="sg docker -c"; fi
IMAGE=mbab-pinned-sandbox-codex-0.160.0-claude-2.1.283
build="docker build -q -t $IMAGE --build-arg CODEX_VERSION=rust-v0.160.0 --build-arg CLAUDE_VERSION=2.1.283 -f sandbox/docker/Dockerfile ."
if [ -n "$DOCKER_WRAP" ]; then $DOCKER_WRAP "$build"; else $build; fi >/dev/null   # once, so parallel runs do not race

lane() {  # lane <queue> <in flight>
  [ "$2" -gt 0 ] && [ -s "$1" ] || return 0
  OUT="$OUT" DOCKER_WRAP="$DOCKER_WRAP" xargs -P "$2" -L 1 sh -c '
    sleep $(( $(od -An -N1 -tu1 /dev/urandom) % 30 ))
    log="$OUT/$0-$(echo "$2" | tr / -)-r$3.log"
    cmd="sandbox/docker/run_trial.sh $1 $2 $3"
    if [ -n "$DOCKER_WRAP" ]; then ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/$0.toml $DOCKER_WRAP "$cmd" > "$log" 2>&1
    else ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/$0.toml $cmd > "$log" 2>&1; fi
    echo "$0 $1 $2 r$3 exit=$? $(date -u +%H:%M)" >> "$OUT/done.txt"' < "$1"
}
echo "batch $OUT: $(cat "$OUT"/claude.txt "$OUT"/codex.txt "$OUT"/react.txt | wc -l | tr -d ' ') runs; progress in $OUT/done.txt"
lane "$OUT/claude.txt" "$P_CLAUDE" & sleep 40
lane "$OUT/codex.txt" "$P_CODEX" & sleep 40
lane "$OUT/react.txt" "$P_REACT" &
wait
echo "ALL DONE $(date -u)" >> "$OUT/done.txt"
if [ -n "$SYNC_TO" ]; then
  rsync -a --exclude '.claude*' runs/ "$SYNC_TO:Dev/MessageBoardAuditBench/runs/" && echo "SYNCED to $SYNC_TO $(date -u)" >> "$OUT/done.txt"
fi
