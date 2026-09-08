#!/usr/bin/env bash
# Follow-up round on round 4: continue finished 120-minute trials in their own conversation
# with more time and a request for a longer report (configs/<CONFIG>.toml sets both).
#
#   scripts/run_followup.sh            # every system below, all its round-4 replicates
#   scripts/run_followup.sh --dry-run  # print the commands
#   ONLY=codex|react  MATCH='sol|glm'  EPOCHS=1,3  CONFIG=followup-5k  scripts/run_followup.sh
#
# Codex trials resume through `RESUME_FROM=<parent run dir> run_trial.sh` (native CLI resume).
# ReAct trials continue through the messageboard_audit_bench_continue Inspect task, unscored
# like round 4 (reports are graded afterwards by the rubric scripts).
# Claude Code round-4 runs kept no session store and are not continued here.
# Systems run in parallel; a system's replicates run one after another, as in round 4.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROUND4="${ROUND4:-$ROOT/.worktrees/inspect-eval}"   # where round 4's logs/ and runs/ live
[ -d "$ROUND4/logs/round4" ] || ROUND4="$(git -C "$ROOT" worktree list --porcelain | awk '/^worktree /{print $2; exit}')/.worktrees/inspect-eval"
[ -d "$ROUND4/logs/round4" ] || { echo "round-4 logs not found under $ROUND4" >&2; exit 1; }
CONFIG="${CONFIG:-followup-5k-min5}"
PARENT_BUDGET="${PARENT_BUDGET:-120}"
OUT="$ROOT/logs/$CONFIG"; mkdir -p "$OUT"
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
ONLY="${ONLY:-}"     # ONLY=codex or ONLY=react restricts the launch to one harness
MATCH="${MATCH:-.}"  # extended regex a job's system id must match
EPOCHS="${EPOCHS:-all}"

# Round-4 system ids: Codex (CLI model) and ReAct (Inspect log; max connections).
CODEX_SYSTEMS=(
  "codex-gpt-5-6-sol   gpt-5.6-sol"
  "codex-gpt-5-6-terra gpt-5.6-terra"
  "codex-gpt-5-6-luna  gpt-5.6-luna"
  "codex-gpt-6-astra   gpt-6-astra"
)
REACT_SYSTEMS=(
  "react-gpt-5-6-sol            4"
  "react-gemini-3-8-flash       4"
  "react-muse-spark-1-3         2"
  "react-kimi-k3                4"
  "react-glm-5-3                4"
  "react-gpt-6-astra-exploratory 4"
)
# Replicates that cannot be continued: kimi's 120-minute epoch 2 history (385k tokens)
# exceeds the 262k context of the provider OpenRouter routes it to.
skip_epochs() { case "$1:$PARENT_BUDGET" in react-kimi-k3:120) echo 2 ;; *) echo "" ;; esac; }

# Same key file convention as run_trial.sh's ReAct path: per-model file first, generic file second.
openrouter_key_for() {
  local f="$ROOT/runs/.openrouter_key.${1//\//_}"
  [ -s "$f" ] || f="$ROOT/runs/.openrouter_key"
  [ -s "$f" ] && tr -d '[:space:]' < "$f"
}
unset VIRTUAL_ENV
# The newest log at that budget that holds finished samples (a retried cell can leave
# a newer, cancelled, empty log beside the real one).
latest_log() {
  uv run python - "$ROUND4/logs/round4/$1/${PARENT_BUDGET}m" <<'PY'
import sys
from pathlib import Path
from inspect_ai.log import read_eval_log
folder = Path(sys.argv[1])
for path in sorted(folder.glob("*.eval"), reverse=True) if folder.is_dir() else []:
    log = read_eval_log(str(path))
    if any(s.metadata.get("report_written") for s in log.samples or []):
        print(path)
        break
PY
}
# "<epoch> <run dir basename> <cli model>" per finished parent sample of a subscription log.
parent_runs() {
  uv run python - "$1" <<'PY'
import sys
from inspect_ai.log import read_eval_log
from pathlib import Path
log = read_eval_log(sys.argv[1])
for s in log.samples or []:
    m = s.metadata
    if m.get("report_written", True) and m.get("run_dir"):
        print(s.epoch, Path(m["run_dir"]).name, m.get("subscription_model"))
PY
}
epoch_wanted() {  # epoch, system
  [ "$EPOCHS" = all ] || grep -qx "$1" <<< "${EPOCHS//,/$'\n'}" || return 1
  [ "$(skip_epochs "$2")" != "$1" ]
}

pids=()
for entry in "${CODEX_SYSTEMS[@]}"; do
  [ -z "$ONLY" ] || [ "$ONLY" = codex ] || continue
  read -r system model <<< "$entry"
  grep -Eq "$MATCH" <<< "$system" || continue
  log="$(latest_log "$system")"
  [ -n "$log" ] || { echo "codex $system: no finished ${PARENT_BUDGET}m log, skipped"; continue; }
  cmds=()
  while read -r epoch run cli_model; do
    epoch_wanted "$epoch" "$system" || continue
    [ -d "$ROUND4/runs/$run" ] || { echo "missing parent run dir $run" >&2; exit 1; }
    cmds+=("CONFIG=$CONFIG RESUME_FROM=$ROUND4/runs/$run $ROOT/sandbox/docker/run_trial.sh codex $model $epoch")
  done < <(parent_runs "$log")
  printf 'codex %s: %d replicate(s)\n' "$system" "${#cmds[@]}"
  [ "${#cmds[@]}" -gt 0 ] || continue
  printf '  %s\n' "${cmds[@]}"
  (( DRY )) || {
    ( for c in "${cmds[@]}"; do echo "== $c"; eval "env $c"; done ) > "$OUT/${system}_from${PARENT_BUDGET}m.out" 2>&1 & pids+=($!)
  }
done
for entry in "${REACT_SYSTEMS[@]}"; do
  [ -z "$ONLY" ] || [ "$ONLY" = react ] || continue
  read -r system conns <<< "$entry"
  grep -Eq "$MATCH" <<< "$system" || continue
  log="$(latest_log "$system")"
  [ -n "$log" ] || { echo "react $system: no finished ${PARENT_BUDGET}m log, skipped"; continue; }
  model="$(uv run python -c 'import sys; from inspect_ai.log import read_eval_log; print(read_eval_log(sys.argv[1], header_only=True).eval.model)' "$log")"
  epochs="$EPOCHS"
  if [ -n "$(skip_epochs "$system")" ]; then
    all="$(uv run python -c 'import sys; from inspect_ai.log import read_eval_log; print(",".join(str(s.epoch) for s in read_eval_log(sys.argv[1]).samples))' "$log")"
    [ "$epochs" = all ] && epochs="$all"
    epochs="$(tr , '\n' <<< "$epochs" | grep -vx "$(skip_epochs "$system")" | paste -sd, -)"
  fi
  key="${OPENROUTER_API_KEY:-$(openrouter_key_for "${model#openrouter/}")}"
  [ -n "$key" ] || { echo "no OpenRouter key for $model" >&2; exit 1; }
  cmd=(uv run inspect eval messageboard_audit_bench/messageboard_audit_bench_continue
       -T "parent_log=$log" -T "parent_epochs=$epochs" -T "config=$CONFIG"
       --max-samples 1 --max-sandboxes 1 --max-connections "$conns" --max-retries 5
       --timeout 900 --attempt-timeout 600 --retry-on-error=2 --log-model-api --log-refusals --no-score
       --log-dir "$OUT/$system/from${PARENT_BUDGET}m")
  printf 'react %s (%s, epochs %s): ' "$system" "$model" "$epochs"; printf '%q ' "${cmd[@]}"; echo
  (( DRY )) || { (cd "$ROOT" && OPENROUTER_API_KEY="$key" "${cmd[@]}") > "$OUT/${system}_from${PARENT_BUDGET}m.out" 2>&1 & pids+=($!); }
done
(( DRY )) && exit 0
rc=0
for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
echo "all follow-up jobs finished (rc=$rc, parents ${PARENT_BUDGET}m); outputs under $OUT"
exit $rc
