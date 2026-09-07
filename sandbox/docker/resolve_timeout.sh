#!/usr/bin/env bash
# Resolve the agent-visible budget and hard timeout after a config is loaded.
# Expects CFG_BUDGET_MIN and CFG_TIMEOUT_MIN; honours optional BUDGET_MIN/TIMEOUT.

resolve_trial_time() {
  local requested_budget_min="${BUDGET_MIN:-}"
  local requested_timeout="${TIMEOUT:-}"

  BUDGET_MIN="${requested_budget_min:-$CFG_BUDGET_MIN}"
  if [ -n "$requested_timeout" ]; then
    TIMEOUT="$requested_timeout"
  elif [ -n "$requested_budget_min" ]; then
    TIMEOUT="$((BUDGET_MIN + CFG_TIMEOUT_MIN - CFG_BUDGET_MIN))m"
  else
    TIMEOUT="${CFG_TIMEOUT_MIN}m"
  fi
}
