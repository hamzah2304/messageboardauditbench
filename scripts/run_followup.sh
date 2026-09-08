#!/usr/bin/env bash
# Follow-up round on round 4: give one finished 120-minute trial per system ten more
# minutes of its own conversation and ask for a 4,500-5,000 word report.
#
#   scripts/run_followup.sh            # launch every job below in parallel, wait for all
#   scripts/run_followup.sh --dry-run  # print the commands
#
# Codex trials resume through `RESUME_FROM=<parent run dir> run_trial.sh` (native CLI resume).
# ReAct trials continue through the messageboard_audit_bench_continue Inspect task.
# Claude Code round-4 runs kept no session store and are not continued here.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROUND4="${ROUND4:-$ROOT/.worktrees/inspect-eval}"   # where round 4's logs/ and runs/ live
[ -d "$ROUND4/logs/round4" ] || ROUND4="$(git -C "$ROOT" worktree list --porcelain | awk '/^worktree /{print $2; exit}')/.worktrees/inspect-eval"
[ -d "$ROUND4/logs/round4" ] || { echo "round-4 logs not found under $ROUND4" >&2; exit 1; }
CONFIG="${CONFIG:-followup-5k}"
OUT="$ROOT/logs/$CONFIG"; mkdir -p "$OUT"
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
ONLY="${ONLY:-}"   # ONLY=codex or ONLY=react restricts the launch to one harness

# Codex: parent run dir (epoch 1 of each system's 120-minute cell) and its CLI model.
CODEX_JOBS=(
  "gpt-5.6-sol   20260907T154517Z_codex_gpt-5.6-sol_r1_blind_81d3f39f1a93"
  "gpt-5.6-terra 20260907T154518Z_codex_gpt-5.6-terra_r1_blind_2a9aa2883ba4"
  "gpt-5.6-luna  20260907T154518Z_codex_gpt-5.6-luna_r1_blind_050681286eec"
  "gpt-6-astra   20260907T154819Z_codex_gpt-6-astra_r1_blind_96ba17bd22c3"
)
# ReAct: system id, epoch (kimi's 120-minute log has no epoch 1), max connections.
REACT_JOBS=(
  "react-gemini-3-8-flash 1 4"
  "react-muse-spark-1-3   1 2"
  "react-kimi-k3          2 4"
  "react-glm-5-3          1 4"
)

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -s "$ROOT/runs/.openrouter_key" ]; then
  export OPENROUTER_API_KEY="$(tr -d '[:space:]' < "$ROOT/runs/.openrouter_key")"
fi
unset VIRTUAL_ENV
pids=()
for job in "${CODEX_JOBS[@]}"; do
  [ -z "$ONLY" ] || [ "$ONLY" = codex ] || continue
  read -r model parent <<< "$job"
  cmd=(env CONFIG="$CONFIG" RESUME_FROM="$ROUND4/runs/$parent" "$ROOT/sandbox/docker/run_trial.sh" codex "$model" 1)
  printf 'codex %s: ' "$model"; printf '%q ' "${cmd[@]}"; echo
  (( DRY )) || { "${cmd[@]}" > "$OUT/codex_$model.out" 2>&1 & pids+=($!); }
done
for job in "${REACT_JOBS[@]}"; do
  [ -z "$ONLY" ] || [ "$ONLY" = react ] || continue
  read -r system epoch conns <<< "$job"
  log="$(ls "$ROUND4/logs/round4/$system/120m/"*.eval | tail -1)"
  cmd=(uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_continue
       -T "parent_log=$log" -T "parent_epoch=$epoch" -T "config=$CONFIG"
       --max-samples 1 --max-sandboxes 1 --max-connections "$conns" --max-retries 5
       --timeout 900 --attempt-timeout 600 --retry-on-error=2 --log-model-api --log-refusals
       --log-dir "$OUT/$system")
  printf 'react %s: ' "$system"; printf '%q ' "${cmd[@]}"; echo
  (( DRY )) || { (cd "$ROOT" && "${cmd[@]}") > "$OUT/$system.out" 2>&1 & pids+=($!); }
done
(( DRY )) && exit 0
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
echo "all follow-up jobs finished (rc=$rc); outputs under $OUT"
exit $rc
