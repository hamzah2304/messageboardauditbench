#!/usr/bin/env bash
# Preflight for running the benchmark. Checks each prerequisite and prints the fix.
#
#   scripts/doctor.sh            # everything except data checksums
#   scripts/doctor.sh --verify   # also verify data/ against data/SHA256SUMS.variants (~10 s)
#
# Exit 1 if a hard requirement (Python, uv, Docker, disk, data) is missing; credentials and
# judge keys are reported but only fail the harness you try to run without them.
set -u
cd "$(dirname "$0")/.." || exit 1
ROOT="$PWD"; fail=0
ok()   { printf '  ok    %s\n' "$*"; }
warn() { printf '  --    %s\n' "$*"; }
bad()  { printf '  MISSING %s\n' "$*"; fail=1; }
# .env is read by the graders; read it here too so keys set only there count.
if [ -f .env ]; then set -a; . ./.env 2>/dev/null; set +a; fi

echo "tools"
if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
  ok "python3 $(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
else bad "python3 >= 3.11"; fi
if command -v uv >/dev/null; then ok "uv $(uv --version | awk '{print $2}')"; else bad "uv: https://docs.astral.sh/uv/getting-started/installation/"; fi
if [ -d .venv ] && uv run --no-sync python -c 'import inspect_ai, messageboard_audit_bench' 2>/dev/null; then
  ok "package installed (inspect_ai + messageboard_audit_bench importable)"
else bad "package not installed: run  uv sync"; fi
for t in curl unzip; do command -v "$t" >/dev/null && ok "$t" || bad "$t (needed by scripts/fetch_data.sh)"; done

echo "docker"
if ! command -v docker >/dev/null; then bad "docker CLI"
elif ! docker info >/dev/null 2>&1; then bad "docker daemon not reachable (macOS: colima start, or open Docker Desktop)"
else
  ok "daemon reachable ($(docker version --format '{{.Server.Version}}' 2>/dev/null))"
  if docker image inspect "${IMAGE:-mbab-sandbox}" >/dev/null 2>&1; then ok "image ${IMAGE:-mbab-sandbox} built"
  else warn "image ${IMAGE:-mbab-sandbox} not built yet; the first run_trial.sh builds it (a few minutes)"; fi
fi
FREE_GB=$(( $(df -Pk "$ROOT" | awk 'NR==2{print $4}') / 1048576 ))
if [ "$FREE_GB" -ge "${MIN_FREE_GB:-10}" ]; then ok "${FREE_GB} GB free disk"
else bad "${FREE_GB} GB free; run_trial.sh refuses below MIN_FREE_GB=${MIN_FREE_GB:-10}"; fi

echo "data"
if [ -f data/raw_stripped/revisions.jsonl ] && [ -d data/verbatim ]; then
  ok "data/raw_stripped and data/verbatim present"
  if [ "${1:-}" = "--verify" ]; then
    if scripts/build_data.sh --verify >/dev/null 2>&1; then ok "checksums match data/SHA256SUMS.variants"
    else bad "checksums do not match; rebuild with scripts/build_data.sh"; fi
  else warn "checksums not verified (pass --verify)"; fi
else bad "data not built: run  scripts/build_data.sh"; fi

echo "agent credentials (only the harness you run needs one)"
if [ -s runs/.claude-oauth-token ]; then ok "claude: runs/.claude-oauth-token"
elif [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then ok "claude: CLAUDE_CODE_OAUTH_TOKEN in env"
elif [ -f runs/.claude-home/.credentials.json ]; then ok "claude: runs/.claude-home/.credentials.json (claude_login.sh)"
elif [ -f "$HOME/.claude/.credentials.json" ]; then ok "claude: ~/.claude/.credentials.json (host fallback, Linux only)"
else warn "claude: none.  claude setup-token > runs/.claude-oauth-token"; fi
if [ -f "$HOME/.codex/auth.json" ]; then ok "codex: ~/.codex/auth.json"; else warn "codex: none.  codex login"; fi
if [ -s runs/.openrouter_key ] || ls runs/.openrouter_key.* >/dev/null 2>&1; then ok "react: runs/.openrouter_key"
elif [ -n "${OPENROUTER_API_KEY:-}" ]; then ok "react: OPENROUTER_API_KEY in env"
else warn "react: none.  export OPENROUTER_API_KEY or write runs/.openrouter_key"; fi

echo "judge keys"
[ -n "${OPENAI_API_KEY:-}" ] && ok "OPENAI_API_KEY (30-claim grader, default judge gpt-5.6-sol)" || warn "OPENAI_API_KEY not set; benchmark/rubrics/grade_with_rubrics.py needs it (env or .env)"
[ -n "${ANTHROPIC_API_KEY:-}" ] && ok "ANTHROPIC_API_KEY (Inspect rubric_scorer default judge)" || warn "ANTHROPIC_API_KEY not set; Inspect scoring needs it, or pass -T judge=openai/..."

echo
if [ "$fail" = 0 ]; then echo "ready. Smoke test:  CONFIG=blind BUDGET_MIN=3 TIMEOUT=6m sandbox/docker/run_trial.sh <agent> <model> 1"
else echo "fix the MISSING items above, then rerun scripts/doctor.sh"; fi
exit "$fail"
