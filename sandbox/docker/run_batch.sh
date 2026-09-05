#!/usr/bin/env bash
# Run a matrix of trials. One line per trial in the matrix file:
#
#   <agent> <model> <config> [replicate] # config = configs/<name>.toml; '#' starts a comment
#   claude claude-opus-5 blind-20 1
#   codex  gpt-5.6-sol   context-40 1
#   react  moonshotai/kimi-k3 blind-20 1
#
#   sandbox/docker/run_batch.sh matrix.txt
#
# Trials are grouped into lanes by agent. Lanes run concurrently; within the claude and
# codex lanes trials run one at a time (one subscription each); the react lane runs all
# its trials at once (API-metered). LANE_PARALLEL=1 makes every lane fully parallel; LANE_MAX=N caps a
# parallel claude/codex lane at N trials in flight (subscription rate limits); the react lane is never capped.
# Each trial gets its own network and proxy, so nothing is shared between them.
# Detached with nohup: survives this shell. Progress in runs/batch_<stamp>.log.
set -euo pipefail
MATRIX="${1:?matrix file}"; HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; LOG="$ROOT/runs/batch_$STAMP.log"; mkdir -p "$ROOT/runs"
LANE_PARALLEL="${LANE_PARALLEL:-0}"; LANE_MAX="${LANE_MAX:-0}"
docker image inspect "${IMAGE:-mbab-sandbox}" >/dev/null 2>&1 || docker build -q -t "${IMAGE:-mbab-sandbox}" -f "$HERE/Dockerfile" "$ROOT" >/dev/null

one() {  # agent model config replicate
  local a="$1" m="$2" c="${3:-default}" r="${4:-1}" rc
  echo "$(date -u +%H:%M:%S) start $a $m $c r=$r"
  set +e
  CONFIG="$c" "$HERE/run_trial.sh" "$a" "$m" "$r" 2>&1 \
    | grep -E '^run: |"exit_code"|"wall_seconds"|FAIL|canary|Error|error|^no ' | sed "s|^|  [$a $m $c r$r] |"
  rc=${PIPESTATUS[0]}
  set -e
  if [ "$rc" -eq 0 ]; then
    echo "$(date -u +%H:%M:%S) done  $a $m $c r=$r"
  else
    echo "$(date -u +%H:%M:%S) FAILED $a $m $c r=$r rc=$rc"
  fi
  return "$rc"
}
lane() {  # agent, then reads its lines from stdin
  local a="$1" parallel="$2" failed=0 pid
  local -a pids=()
  while read -r _ m c r; do
    if [ "$parallel" = 1 ]; then
      if [ "$a" != react ] && [ "$LANE_MAX" -gt 0 ]; then
        while [ "$(jobs -rp | wc -l)" -ge "$LANE_MAX" ]; do sleep 10; done
      fi
      one "$a" "$m" "$c" "$r" & pids+=("$!")
    else
      one "$a" "$m" "$c" "$r" || failed=1
    fi
  done
  for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
  return "$failed"
}
export -f one lane; export HERE ROOT IMAGE LANE_MAX
LINES="$(grep -vE '^\s*(#|$)' "$MATRIX")"
echo "batch $STAMP: $(echo "$LINES" | wc -l | tr -d ' ') trials, log $LOG"
(
  failed=0; pids=()
  for a in $(echo "$LINES" | awk '{print $1}' | sort -u); do
    p="$LANE_PARALLEL"; [ "$a" = react ] && p=1
    echo "$LINES" | awk -v a="$a" '$1==a' | lane "$a" "$p" &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
  if [ "$failed" -eq 0 ]; then
    echo "BATCH_OK $(date -u +%H:%M:%S)"
  else
    echo "BATCH_FAILED $(date -u +%H:%M:%S)"
  fi
  exit "$failed"
) > "$LOG" 2>&1 < /dev/null &
disown; echo "started (pid $!). tail -f $LOG"
