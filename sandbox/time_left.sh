#!/usr/bin/env bash
# Claude Code PostToolUse hook: after every tool call, tell the agent how much of its time budget is left.
# run_trial.sh sets MBAB_DEADLINE_EPOCH (unix seconds) and MBAB_BUDGET_MIN when the agent starts.
[ -n "${MBAB_DEADLINE_EPOCH:-}" ] || exit 0
left=$(( (MBAB_DEADLINE_EPOCH - $(date +%s) + 30) / 60 ))
if [ "$left" -gt 0 ]; then msg="Time budget: about $left of ${MBAB_BUDGET_MIN:-?} minutes left."
else msg="Time budget: exhausted (about $(( -left )) minutes over). The session will be stopped any moment; make sure report.md is complete."; fi
printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$msg"
