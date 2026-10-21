#!/usr/bin/env bash
# End-to-end smoke test: one short trial of each Inspect eval, through the real Docker
# sandbox, agent and judge, graded inline. It checks the plumbing, not the scores: the
# agent gets MINUTES minutes and may finish early.
#
#   MODEL=openai/gpt-6-luna scripts/e2e_smoke.sh                    # all three evals
#   MODEL=openai/gpt-6-luna scripts/e2e_smoke.sh aivillage_report   # just one
#
# MODEL    the agent's Inspect model (required)
# AGENT    react (default), claude or codex; claude/codex need an Anthropic/OpenAI MODEL
# JUDGE    the grader for every eval; unset, each eval uses its own default judge
#          (German wiki: openai/gpt-5.6-sol, Transluce: anthropic/claude-opus-5-5,
#          AI Village: openai/gpt-6.1-sol), which needs that provider's key
# MINUTES  trial budget in minutes (default 5)
#
# Needs Docker, uv sync, the provider keys in .env or the environment, and each eval's
# data: scripts/build_data.sh (German wiki), data/urlquery/<snapshot>/ (Transluce, see
# benchmarks/transluce/README.md), scripts/build_aivillage_data.py --variant reasoning
# (AI Village). Logs go to logs/e2e/<eval>/; open them with `uv run inspect view`.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -n "${MODEL:-}" ] || { echo "set MODEL, e.g. MODEL=openai/gpt-6-luna $0" >&2; exit 2; }
AGENT="${AGENT:-react}"
MINUTES="${MINUTES:-5}"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
[ "$#" -gt 0 ] || set -- german_wiki_report transluce_report aivillage_report

failed=()
for eval_name in "$@"; do
  echo "=== $eval_name ($AGENT, $MODEL, $MINUTES min)"
  args=(-T agent="$AGENT" -T time_limit_minutes="$MINUTES" -T min_runtime_fraction=0
        --model "$MODEL" --log-dir "logs/e2e/$eval_name")
  [ -z "${JUDGE:-}" ] || args+=(--model-role grader="$JUDGE")
  if uv run inspect eval "messageboard_audit_bench/$eval_name" "${args[@]}"; then
    echo "=== $eval_name: ok"
  else
    echo "=== $eval_name: FAILED" >&2
    failed+=("$eval_name")
  fi
done
[ "${#failed[@]}" -eq 0 ] || { echo "failed: ${failed[*]}" >&2; exit 1; }
echo "all passed; inspect the scores with: uv run inspect view --log-dir logs/e2e"
