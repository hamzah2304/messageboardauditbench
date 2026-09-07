#!/usr/bin/env bash
# How much of the trial's time budget is left. run_trial.sh sets MBAB_DEADLINE_EPOCH (unix seconds)
# and MBAB_BUDGET_MIN when the agent starts. Two callers:
#   * Claude Code and Codex PostToolUse hook: prints the hook JSON, so the note lands in the
#     agent's context after every tool call
#   * `time_left` on the agent's PATH (--plain): prints the note as text, so any agent can ask
[ -n "${MBAB_DEADLINE_EPOCH:-}" ] || {
  if [ -r /tmp/mbab-time-budget ]; then
    MBAB_DEADLINE_EPOCH="$(sed -n '1p' /tmp/mbab-time-budget)"
    MBAB_BUDGET_MIN="$(sed -n '2p' /tmp/mbab-time-budget)"
  else
    exit 0
  fi
}
case "$MBAB_DEADLINE_EPOCH" in ''|*[!0-9]*) exit 0 ;; esac
case "${MBAB_BUDGET_MIN:-}" in ''|*[!0-9]*) MBAB_BUDGET_MIN='?' ;; esac
left=$(( (MBAB_DEADLINE_EPOCH - $(date +%s) + 30) / 60 ))
if [ "$left" -gt 0 ]; then msg="Time budget: about $left of ${MBAB_BUDGET_MIN:-?} minutes left."
else msg="Time budget: exhausted (about $(( -left )) minutes over). The session will be stopped any moment; make sure report.md is complete."; fi
if [ "${1:-}" = --plain ]; then echo "$msg"; exit 0; fi
printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$msg"
