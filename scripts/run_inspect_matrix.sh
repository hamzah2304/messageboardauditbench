#!/usr/bin/env bash
# Run one declared MessageBoardAuditBench config with explicit operational
# limits. Invoke this script once per model/agent/config cell; doing so keeps
# native and subscription scaffolds visibly separate in Inspect logs.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/run_inspect_matrix.sh [options]

Required:
  --agent AGENT                 claude, codex, or react
  --config CONFIG               blind or context

Backend/model:
  --backend BACKEND             inspect (default) or subscription
  --model MODEL                 Inspect model for backend=inspect
  --subscription-model MODEL    CLI model for backend=subscription

Run shape:
  --time-limit-minutes N        agent budget (default: 20)
  --min-runtime-fraction F      minimum fraction before completion (default: 0.75; 0 disables)
  --epochs N                    independent replicates (default: 1)
  --judge MODEL                 grader model (default: anthropic/claude-sonnet-5)
  --logs DIR                    Inspect log directory (default: logs)

Operational limits (all explicit in the resulting command):
  --max-samples N               default: 1
  --max-sandboxes N             default: 1
  --max-connections N           default: 4 (Muse requires and defaults to 2)
  --max-retries N               API retries per request (default: 5)
  --request-timeout N           total API request timeout seconds (default: 900)
  --attempt-timeout N           timeout for each API attempt (default: 600)
  --retry-on-error N            sample reruns after error (default: 2)
  --no-log-model-api            omit raw model API logging
  --no-log-refusals             omit refusal warnings
  --dry-run                     print, do not run
  --                            pass remaining arguments directly to inspect eval

On macOS, the process is wrapped in caffeinate -dimsu to prevent sleep from
freezing Docker containers. There is deliberately no disk-space floor check.
EOF
}

backend=inspect
agent=""
config=""
model=""
subscription_model=""
time_limit_minutes=20
min_runtime_fraction=0.75
epochs=1
judge="anthropic/claude-sonnet-5"
logs=logs
max_samples=1
max_sandboxes=1
max_connections=""
max_retries=5
request_timeout=900
attempt_timeout=600
retry_on_error=2
log_model_api=1
log_refusals=1
dry_run=0
extra=()

while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --backend|--agent|--config|--model|--subscription-model|--time-limit-minutes|--min-runtime-fraction|--epochs|--judge|--logs|--max-samples|--max-sandboxes|--max-connections|--max-retries|--request-timeout|--attempt-timeout|--retry-on-error)
      (($# >= 2)) || { echo "missing value for $1" >&2; exit 2; }
      key=${1#--}; key=${key//-/_}; printf -v "$key" '%s' "$2"; shift 2 ;;
    --no-log-model-api) log_model_api=0; shift ;;
    --no-log-refusals) log_refusals=0; shift ;;
    --dry-run) dry_run=1; shift ;;
    --) shift; extra=("$@"); break ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$agent" && -n "$config" ]] || { echo "--agent and --config are required" >&2; exit 2; }
case "$backend" in inspect|subscription) ;; *) echo "invalid --backend: $backend" >&2; exit 2;; esac
if [[ "$backend" == inspect ]]; then
  [[ -n "$model" ]] || { echo "--model is required for backend=inspect" >&2; exit 2; }
  [[ -z "$subscription_model" ]] || { echo "--subscription-model only applies to backend=subscription" >&2; exit 2; }
else
  [[ -n "$subscription_model" ]] || { echo "--subscription-model is required for backend=subscription" >&2; exit 2; }
  [[ -z "$model" ]] || { echo "--model only applies to backend=inspect" >&2; exit 2; }
fi

selected_model="${model:-$subscription_model}"
case "$selected_model" in
  *[Mm][Uu][Ss][Ee]*)
    if [[ -n "$max_connections" && "$max_connections" != 2 ]]; then
      echo "Muse requires --max-connections 2" >&2
      exit 2
    fi
    max_connections=2
    ;;
  *) max_connections="${max_connections:-4}" ;;
esac

cmd=(uv run inspect eval messageboard_audit_bench/messageboard_audit_bench
  -T "backend=$backend" -T "agent=$agent" -T "config=$config"
  -T "time_limit_minutes=$time_limit_minutes" -T "min_runtime_fraction=$min_runtime_fraction" -T "judge=$judge"
  --epochs "$epochs" --max-samples "$max_samples" --max-sandboxes "$max_sandboxes"
  --max-connections "$max_connections" --max-retries "$max_retries"
  --timeout "$request_timeout" --attempt-timeout "$attempt_timeout"
  --retry-on-error="$retry_on_error" --log-dir "$logs")
if [[ "$backend" == inspect ]]; then
  cmd+=(--model "$model")
else
  cmd+=(-T "subscription_model=$subscription_model")
fi
(( log_model_api )) && cmd+=(--log-model-api)
(( log_refusals )) && cmd+=(--log-refusals)
if ((${#extra[@]})); then
  cmd+=("${extra[@]}")
fi

printf 'Running:'; printf ' %q' "${cmd[@]}"; printf '\n'
if (( dry_run )); then exit 0; fi
# Avoid inheriting a virtual environment from another worktree. `uv run`
# resolves this worktree's locked environment itself.
unset VIRTUAL_ENV
if [[ "$(uname -s)" == Darwin ]] && command -v caffeinate >/dev/null; then
  exec caffeinate -dimsu -- "${cmd[@]}"
else
  exec "${cmd[@]}"
fi
