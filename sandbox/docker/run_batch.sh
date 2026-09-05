#!/usr/bin/env bash
# Run a matrix of trials. One line per trial in the matrix file:
#
#   <agent> <model> [budget_min] [seed] [data_dir]      # '#' starts a comment
#   claude claude-opus-5 20 1
#   codex  gpt-5.6-sol   40 1 data/verbatim
#   react  moonshotai/kimi-k3 20 1
#
#   sandbox/docker/run_batch.sh matrix.txt
#
# Trials are grouped into lanes by agent. Lanes run concurrently; within the claude and
# codex lanes trials run one at a time (one subscription each); the react lane runs all
# its trials at once (API-metered). LANE_PARALLEL=1 makes every lane fully parallel.
# Each trial gets its own network and proxy, so nothing is shared between them.
# Detached with nohup: survives this shell. Progress in runs/batch_<stamp>.log.
set -euo pipefail
MATRIX="${1:?matrix file}"; HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; LOG="$ROOT/runs/batch_$STAMP.log"; mkdir -p "$ROOT/runs"
EFFORT="${EFFORT:-high}"; LANE_PARALLEL="${LANE_PARALLEL:-0}"
docker image inspect "${IMAGE:-mbab-sandbox}" >/dev/null 2>&1 || docker build -q -t "${IMAGE:-mbab-sandbox}" -f "$HERE/Dockerfile" "$ROOT" >/dev/null

one() {  # agent model budget seed data_dir
  local a="$1" m="$2" b="${3:-20}" s="${4:-1}" d="${5:-}"
  echo "$(date -u +%H:%M:%S) start $a $m b=$b s=$s ${d:+data=$d}"
  DATA_DIR="${d:+$ROOT/$d}" BUDGET_MIN="$b" EFFORT="$EFFORT" "$HERE/run_trial.sh" "$a" "$m" "$s" 2>&1 \
    | grep -E '^run: |"exit_code"|"wall_seconds"|FAIL|canary|Error|error' | sed "s/^/  [$a $m s$s] /" || true
  echo "$(date -u +%H:%M:%S) done  $a $m b=$b s=$s"
}
lane() {  # agent, then reads its lines from stdin
  local a="$1"; local parallel="$2"
  while read -r _ m b s d; do
    if [ "$parallel" = 1 ]; then one "$a" "$m" "$b" "$s" "$d" & else one "$a" "$m" "$b" "$s" "$d"; fi
  done; wait
}
export -f one lane; export HERE ROOT EFFORT IMAGE
LINES="$(grep -vE '^\s*(#|$)' "$MATRIX")"
echo "batch $STAMP: $(echo "$LINES" | wc -l | tr -d ' ') trials, log $LOG"
(
  for a in $(echo "$LINES" | awk '{print $1}' | sort -u); do
    p="$LANE_PARALLEL"; [ "$a" = react ] && p=1
    echo "$LINES" | awk -v a="$a" '$1==a' | lane "$a" "$p" &
  done
  wait; echo "BATCH_DONE $(date -u +%H:%M:%S)"
) > "$LOG" 2>&1 < /dev/null &
disown; echo "started (pid $!). tail -f $LOG"
