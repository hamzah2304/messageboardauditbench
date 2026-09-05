#!/usr/bin/env bash
# Run one trial in Docker with structural isolation.
#
#   sandbox/docker/run_trial.sh claude claude-opus-5 1
#   sandbox/docker/run_trial.sh codex  gpt-5.6-sol   1
#   sandbox/docker/run_trial.sh react  moonshotai/kimi-k3 1   # ReAct scaffold via OpenRouter
#
# Conditions come from a config: CONFIG=configs/<name>.toml (default configs/default.toml) sets the prompt,
# the time budget, the kill timeout, the data variant, the effort and the Claude tool denylist. Env vars
# PROMPT, BUDGET_MIN, TIMEOUT, DATA_DIR, EFFORT override individual values. IMAGE (mbab-sandbox).
# The run is named <stamp>_<agent>_<model>_r<replicate>_<config name>_<run id>.
#
# Isolation comes from structure, not permissions:
#   * the agent container is on an `internal` Docker network (no gateway, nothing routable)
#     and its only way out is HTTPS_PROXY -> a proxy container that allowlists vendor API hosts
#   * the container sees /work (data/*.jsonl read-only + prompt.txt) and its own creds. No repo mount.
#   * a canary container on the same network/mounts proves both facts before the agent starts.
set -euo pipefail
AGENT="${1:?claude|codex|react}"; MODEL="${2:?model id}"; REPLICATE="${3:-1}"
IMAGE="${IMAGE:-mbab-sandbox}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
CONFIG="${CONFIG:-$ROOT/configs/default.toml}"; [ -f "$CONFIG" ] || CONFIG="$ROOT/configs/$CONFIG.toml"
[ -f "$CONFIG" ] || { echo "no config at $CONFIG" >&2; exit 1; }
eval "$(python3 "$ROOT/scripts/read_config.py" "$CONFIG")"
PROMPT_NAME="${PROMPT:-$CFG_PROMPT}"; PROMPT_FILE="$HERE/../prompts/$PROMPT_NAME.txt"
[ -f "$PROMPT_FILE" ] || { echo "no prompt at $PROMPT_FILE" >&2; exit 1; }
BUDGET_MIN="${BUDGET_MIN:-$CFG_BUDGET_MIN}"; TIMEOUT="${TIMEOUT:-${CFG_TIMEOUT_MIN}m}"; EFFORT="${EFFORT:-$CFG_EFFORT}"
DATA_DIR="${DATA_DIR:-$ROOT/data/$CFG_DATA_VARIANT}"
read -r -a CLAUDE_DISALLOWED <<< "${CFG_CLAUDE_DISALLOWED_TOOLS:-}"
[ -d "$DATA_DIR" ] || { echo "no data at $DATA_DIR; run scripts/build_data.sh" >&2; exit 1; }

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -q -t "$IMAGE" -f "$HERE/Dockerfile" "$ROOT" >/dev/null

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
VARIANT="$(basename "$DATA_DIR")"
RUN="$ROOT/runs/${STAMP}_${AGENT}_${MODEL//\//_}_r${REPLICATE}_${CFG_NAME}_${RUN_ID:0:12}"
# Secrets live under the run dir (not /tmp): Docker Desktop/colima only share $HOME with the VM.
NET="mbab-inner-$RUN_ID"; PROXY="mbab-proxy-$RUN_ID"; SECRETS="$RUN/.secrets"
mkdir -p "$RUN/work/data" "$SECRETS/claude" "$SECRETS/codex"
cp "$DATA_DIR"/*.jsonl "$RUN/work/data/"
# The prompt template has one placeholder, {{BUDGET_MIN}}; the rendered prompt is what the agent sees and what gets hashed.
sed "s/{{BUDGET_MIN}}/$BUDGET_MIN/g" "$PROMPT_FILE" > "$RUN/work/prompt.txt"
PROMPT="$(cat "$RUN/work/prompt.txt")"

# Credentials: a throwaway copy, mounted as the container user's ~/.claude and ~/.codex.
# Claude: a login done inside the container (sandbox/docker/claude_login.sh) lands in
# runs/.claude-home/.credentials.json. Fallbacks: CLAUDE_CODE_OAUTH_TOKEN, or the host's
# ~/.claude/.credentials.json (Linux hosts only; macOS keeps it in the Keychain).
CLAUDE_ENV=()
if [ -f "$ROOT/runs/.claude-home/.credentials.json" ]; then
  cp "$ROOT/runs/.claude-home/.credentials.json" "$SECRETS/claude/.credentials.json"
elif [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  CLAUDE_ENV=(-e CLAUDE_CODE_OAUTH_TOKEN)
elif [ -f "$HOME/.claude/.credentials.json" ]; then
  cp "$HOME/.claude/.credentials.json" "$SECRETS/claude/.credentials.json"
elif [ "$AGENT" = claude ]; then
  echo "no Claude credentials: run sandbox/docker/claude_login.sh once" >&2; exit 1
fi
# ReAct scaffold: OpenRouter key from env or runs/.openrouter_key (gitignored).
REACT_ENV=()
if [ "$AGENT" = react ]; then
  [ -z "${OPENROUTER_API_KEY:-}" ] && [ -s "$ROOT/runs/.openrouter_key" ] && export OPENROUTER_API_KEY="$(cat "$ROOT/runs/.openrouter_key")"
  [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "no OpenRouter key: export OPENROUTER_API_KEY or write runs/.openrouter_key" >&2; exit 1; }
  REACT_ENV=(-e OPENROUTER_API_KEY)
fi
if [ -f "$HOME/.codex/auth.json" ]; then cp "$HOME/.codex/auth.json" "$SECRETS/codex/auth.json"
elif [ "$AGENT" = codex ]; then echo "no Codex credentials: run \`codex login\` on the host" >&2; exit 1; fi
# Codex: ask for detailed reasoning summaries (and raw reasoning where the model emits it) so the
# transcript carries them; keep session persistence on so the rollout (per-call token counts,
# reasoning items) lands in $SECRETS/codex/sessions and can be copied to <run>/codex_sessions.
printf 'approval_policy = "never"\nsandbox_mode = "danger-full-access"\nweb_search = "disabled"\nmodel_reasoning_summary = "detailed"\nshow_raw_agent_reasoning = true\n' > "$SECRETS/codex/config.toml"
# After every tool call, Claude Code feeds the agent its remaining time (sandbox/time_left.sh reads MBAB_DEADLINE_EPOCH).
printf '{"hooks":{"PostToolUse":[{"hooks":[{"type":"command","command":"/sandbox/time_left.sh"}]}]}}\n' > "$SECRETS/claude/settings.json"
chmod -R a+rwX "$SECRETS" "$RUN/work"   # container user is uid 1000, which may not be us

cleanup() {
  docker logs "$PROXY" > "$RUN/proxy.log" 2>&1 || true; docker rm -f "$PROXY" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true
  # Codex's session rollout is the only place with per-API-call usage and the reasoning items. Keep it (no credentials in it).
  [ -d "$SECRETS/codex/sessions" ] && [ ! -d "$RUN/codex_sessions" ] && cp -R "$SECRETS/codex/sessions" "$RUN/codex_sessions" 2>/dev/null || true
  rm -rf "$SECRETS"; }
trap cleanup EXIT

docker network create --internal "$NET" >/dev/null
docker run -d --name "$PROXY" --network bridge "$IMAGE" python3 -u /sandbox/proxy.py --bind 0.0.0.0 --port 3128 >/dev/null
docker network connect "$NET" "$PROXY"

# Everything the agent container gets. Note NO_PROXY is empty and DNS points nowhere.
DOCKER_ARGS=(--rm --network "$NET" --dns 0.0.0.0 --cap-drop ALL --security-opt no-new-privileges ${CLAUDE_ENV[@]+"${CLAUDE_ENV[@]}"} ${REACT_ENV[@]+"${REACT_ENV[@]}"}
  -e HTTPS_PROXY="http://$PROXY:3128" -e HTTP_PROXY="http://$PROXY:3128" -e NO_PROXY=
  -v "$RUN/work:/work" -v "$RUN/work/data:/work/data:ro"
  -v "$SECRETS/claude:/home/agent/.claude" -v "$SECRETS/codex:/home/agent/.codex"
  -w /work "$IMAGE")

# Canary: same image, network and mounts. Abort the trial if isolation does not hold.
case "$AGENT" in claude) VENDOR_HOST=api.anthropic.com ;; codex) VENDOR_HOST=chatgpt.com ;; react) VENDOR_HOST=openrouter.ai ;; *) echo "unknown agent $AGENT" >&2; exit 2 ;; esac
docker run -e VENDOR_HOST="$VENDOR_HOST" "${DOCKER_ARGS[@]}" bash -c '
  fail=0
  getent hosts collusion.wiki >/dev/null 2>&1 && { echo "FAIL dns resolves"; fail=1; }
  curl -s -m 8 https://collusion.wiki/ >/dev/null 2>&1 && { echo "FAIL proxy let collusion.wiki through"; fail=1; }
  env -u HTTPS_PROXY -u HTTP_PROXY curl -s -m 8 https://collusion.wiki/ >/dev/null 2>&1 && { echo "FAIL direct egress"; fail=1; }
  env -u HTTPS_PROXY -u HTTP_PROXY curl -s -m 8 https://1.1.1.1/ >/dev/null 2>&1 && { echo "FAIL direct egress by ip"; fail=1; }
  code=$(curl -s -m 20 -o /dev/null -w "%{http_code}" "https://$VENDOR_HOST/"); [ "$code" != 000 ] || { echo "FAIL vendor host $VENDOR_HOST unreachable via proxy"; fail=1; }
  echo "--- files visible under /work:"; find /work -type f | sort
  echo "--- bind mounts:"; awk "\$2 ~ /^\/(work|home)/ {print \$2, \$4}" /proc/mounts
  exit $fail' > "$RUN/canary.log" 2>&1 || { cat "$RUN/canary.log"; echo "canary failed; trial aborted" >&2; exit 3; }
EXPECT="$( (cd "$RUN/work" && find . -type f | sed 's#^\./#/work/#') | sort)"
GOT="$(sed -n '/^--- files/,/^--- bind/p' "$RUN/canary.log" | grep '^/work')"
[ "$EXPECT" = "$GOT" ] || { echo "canary: unexpected files in /work" >&2; diff <(echo "$EXPECT") <(echo "$GOT") >&2; exit 3; }

cat > "$RUN/meta.json" <<JSON
{"agent":"$AGENT","model":"$MODEL","effort":"$EFFORT","replicate":$REPLICATE,"run_id":"$RUN_ID","config":"$CFG_NAME","config_sha256":"$(shasum -a 256 "$CONFIG" | cut -c1-64)",
 "prompt":"$PROMPT_NAME","budget_min":$BUDGET_MIN,"timeout":"$TIMEOUT","data_variant":"$VARIANT",
 "started":"$STAMP","data_dir":"$DATA_DIR","prompt_sha256":"$(shasum -a 256 "$RUN/work/prompt.txt" | cut -c1-64)","prompt_template_sha256":"$(shasum -a 256 "$PROMPT_FILE" | cut -c1-64)",
 "image":"$IMAGE","cli_version":"$([ "$AGENT" = react ] && echo react_agent.py || docker run --rm "$IMAGE" "$AGENT" --version 2>/dev/null | head -1)"}
JSON

echo "run: $RUN"
START=$(date +%s); set +e
# The clock the agent is told about: the deadline is BUDGET_MIN from launch, exported so the hook and the ReAct loop agree.
TIME_ENV=(-e MBAB_DEADLINE_EPOCH="$((START + BUDGET_MIN * 60))" -e MBAB_BUDGET_MIN="$BUDGET_MIN")
case "$AGENT" in
  claude)
    docker run -i "${TIME_ENV[@]}" "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" claude -p "$PROMPT" \
      --model "$MODEL" --effort "$EFFORT" \
      --dangerously-skip-permissions --no-chrome --no-session-persistence --setting-sources user \
      ${CLAUDE_DISALLOWED[@]+--disallowedTools "${CLAUDE_DISALLOWED[@]}"} \
      --output-format stream-json --verbose \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  codex)
    docker run -i "${TIME_ENV[@]}" "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" codex exec -C /work \
      --model "$MODEL" -c "model_reasoning_effort=\"$EFFORT\"" \
      --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --ignore-rules \
      --json -o /work/final_message.md "$PROMPT" \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  react)
    docker run -i "${TIME_ENV[@]}" "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" python3 -u /sandbox/react_agent.py \
      --model "$MODEL" --effort "$EFFORT" --prompt-file /work/prompt.txt --cwd /work --budget-min "$BUDGET_MIN" \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  *) echo "unknown agent $AGENT" >&2; exit 2 ;;
esac
set -e; END=$(date +%s)
for f in report.md final_message.md; do [ -f "$RUN/work/$f" ] && cp "$RUN/work/$f" "$RUN/$f"; done
# Codex rollout must be in place before usage is summarized (cleanup would otherwise copy it only at exit).
[ -d "$SECRETS/codex/sessions" ] && [ ! -d "$RUN/codex_sessions" ] && cp -R "$SECRETS/codex/sessions" "$RUN/codex_sessions" 2>/dev/null || true
# Tokens (incl. reasoning), cache, cost, API calls/retries, how the run ended -> <run>/usage.json, key figures into meta.json.
PYTHONPATH="$ROOT" python3 -m messageboard_audit.usage "$RUN" --quiet || echo "usage summary failed" >&2
python3 - "$RUN" "$RC" "$((END-START))" <<'PY'
import json,sys,pathlib
run,rc,secs=pathlib.Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
m=json.loads((run/"meta.json").read_text()); m.update(exit_code=rc,wall_seconds=secs,report_exists=(run/"report.md").exists())
u=json.loads((run/"usage.json").read_text()) if (run/"usage.json").exists() else {}
m["usage"]={k:u.get(k) for k in ("input_tokens","output_tokens","cache_read_tokens","cache_write_tokens","reasoning_tokens",
            "cost_usd","api_calls","tool_calls","api_retries","api_errors","peak_context_tokens","terminal_reason","is_error","usage_source")}
(run/"meta.json").write_text(json.dumps(m,indent=1)); print(json.dumps(m,indent=1))
PY
exit "$RC"
