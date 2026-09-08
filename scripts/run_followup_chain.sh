#!/usr/bin/env bash
# Queue follow-up batches for the shorter round-4 budgets behind the running 120-minute batch.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
until grep -q 'all follow-up jobs finished' "$ROOT/logs/followup-5k-min5.launcher.out" 2>/dev/null; do sleep 60; done
for b in 30 10; do
  echo "== parents ${b}m: $(date -u +%H:%M:%SZ)"
  PARENT_BUDGET=$b "$ROOT/scripts/run_followup.sh" > "$ROOT/logs/followup-5k-min5.launcher-${b}m.out" 2>&1
  echo "== parents ${b}m done rc=$? $(date -u +%H:%M:%SZ)"
done
