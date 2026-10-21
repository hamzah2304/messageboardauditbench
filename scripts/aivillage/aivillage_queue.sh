#!/usr/bin/env bash
# One queue of AI Village trials that can be stopped without touching the runs it started.
#
#   scripts/aivillage/aivillage_queue.sh <queue file> <agent> <max in flight> <out dir> [stop launching at HH:MM UTC]
#
# Queue lines are "config agent model replicate". A line is launched whenever fewer than <max>
# trials of <agent> are running on this machine (live agent containers, plus launches in the last
# three minutes that have no container yet). Each trial starts in its own session (setsid) with no
# stdin, so killing this script, its terminal or its tmux session never reaches a running trial.
# To stop a queue: touch <out dir>/STOP (all queues) or <out dir>/STOP-<agent>; no new trials
# start, running ones finish. Progress: <out dir>/done.txt.
set -uo pipefail
cd "$(dirname "$0")/../.."
Q="$1"; AGENT="$2"; MAX="$3"; OUT="$4"; CUTOFF="${5:-}"
mkdir -p "$OUT/launched"; touch "$OUT/done.txt"
if docker info >/dev/null 2>&1; then wrap() { "$@"; }; else wrap() { sg docker -c "$*"; }; fi
detach() {  # new session, so no signal sent to this script or its terminal reaches the trial
  if command -v setsid >/dev/null; then setsid nohup "$@"
  else python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' nohup "$@"; fi
}
active() {
  local n=0 id
  for id in $(wrap docker ps --format '{{.Names}}' | sed -n 's/^mbab-agent-//p' | cut -c1-12); do
    ls -d runs/*_"${AGENT}"_*_"$id" >/dev/null 2>&1 && n=$((n + 1))
  done
  echo $((n + $(find "$OUT/launched" -name "$AGENT.*" -mmin -3 | wc -l)))
}
while read -r cfg agent model rep; do
  [ -n "${cfg:-}" ] || continue
  while [ "$(active)" -ge "$MAX" ]; do
    [ -e "$OUT/STOP" ] || [ -e "$OUT/STOP-$AGENT" ] && break
    sleep 20
  done
  if [ -e "$OUT/STOP" ] || [ -e "$OUT/STOP-$AGENT" ]; then echo "$cfg $agent $model r$rep NOT STARTED (stopped)" >> "$OUT/done.txt"; continue; fi
  if [ -n "$CUTOFF" ] && [[ "$(date -u +%H:%M)" > "$CUTOFF" ]]; then echo "$cfg $agent $model r$rep NOT STARTED (past $CUTOFF)" >> "$OUT/done.txt"; continue; fi
  touch "$OUT/launched/$AGENT.$(date +%s).$RANDOM"
  log="$OUT/$cfg-$(echo "$model" | tr / -)-r$rep.log"; job="$OUT/launched/job-$(date +%s)-$RANDOM.sh"
  cat > "$job" <<JOB
cd "$PWD"
ALLOW_NETWORKED_SUBSCRIPTION=1 CONFIG=configs/$cfg.toml sandbox/docker/run_trial.sh $agent $model $rep > "$log" 2>&1
echo "$cfg $agent $model r$rep exit=\$? \$(date -u +%H:%M)" >> "$OUT/done.txt"
JOB
  if docker info >/dev/null 2>&1; then detach bash "$job"; else detach sg docker -c "bash $job"; fi < /dev/null > /dev/null 2>&1 &
  sleep 30
done < "$Q"
echo "QUEUE DONE $AGENT $(date -u)" >> "$OUT/done.txt"
