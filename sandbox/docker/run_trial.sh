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
[ "${ALLOW_NETWORKED_SUBSCRIPTION:-0}" = 1 ] || { echo "subscription mode shares model-network access with the shell; use native Inspect or explicitly set ALLOW_NETWORKED_SUBSCRIPTION=1" >&2; exit 2; }
IMAGE="${IMAGE:-mbab-sandbox}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
CONFIG="${CONFIG:-$ROOT/configs/default.toml}"; [ -f "$CONFIG" ] || CONFIG="$ROOT/configs/$CONFIG.toml"
[ -f "$CONFIG" ] || { echo "no config at $CONFIG" >&2; exit 1; }
CONFIG_ASSIGNMENTS="$(python3 "$ROOT/scripts/read_config.py" "$CONFIG")"
eval "$CONFIG_ASSIGNMENTS"
REPORT_MIN_WORDS="${CFG_REPORT_MIN_WORDS:-0}"
REPORT_MAX_WORDS="${CFG_REPORT_MAX_WORDS:-0}"
REPORT_ACCEPT_MIN_WORDS="${CFG_REPORT_ACCEPT_MIN_WORDS:-$REPORT_MIN_WORDS}"
REPORT_ACCEPT_MAX_WORDS="${CFG_REPORT_ACCEPT_MAX_WORDS:-$REPORT_MAX_WORDS}"
PROMPT_NAME="${PROMPT:-$CFG_PROMPT}"; PROMPT_FILE="$HERE/../prompts/$PROMPT_NAME.txt"
[ -f "$PROMPT_FILE" ] || { echo "no prompt at $PROMPT_FILE" >&2; exit 1; }
. "$HERE/resolve_timeout.sh"
resolve_trial_time
EFFORT="${EFFORT:-$CFG_EFFORT}"
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
mkdir -p "$RUN/work" "$SECRETS"
echo "run: $RUN"
cleanup() {
  docker logs "$PROXY" > "$RUN/proxy.log" 2>&1 || true
  docker rm -f "$PROXY" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  # Codex's session rollout is the only place with per-API-call usage and the
  # reasoning items. It contains no credentials and is retained for auditing.
  [ -d "$SECRETS/codex/sessions" ] && [ ! -d "$RUN/codex_sessions" ] && cp -R "$SECRETS/codex/sessions" "$RUN/codex_sessions" 2>/dev/null || true
  rm -rf "$SECRETS"
}
trap cleanup EXIT

timeout_seconds() {
  if [[ "$1" =~ ^([0-9]+)([smhd]?)$ ]]; then
    local value="${BASH_REMATCH[1]}" unit="${BASH_REMATCH[2]}"
    case "$unit" in ""|s) echo "$value" ;; m) echo "$((value * 60))" ;; h) echo "$((value * 3600))" ;; d) echo "$((value * 86400))" ;; esac
  else
    echo "unsupported timeout format: $1 (use Ns, Nm, Nh, or Nd)" >&2
    return 2
  fi
}
# data/<variant> is bind-mounted read-only straight into /work/data: no per-run copy (42 MB each; this filled the disk once).
# The prompt template has one placeholder, {{BUDGET_MIN}}; the rendered prompt is what the agent sees and what gets hashed.
python3 "$ROOT/messageboard_audit_bench/report_length.py" --template "$PROMPT_FILE" --budget-min "$BUDGET_MIN" --min-words "$REPORT_MIN_WORDS" --max-words "$REPORT_MAX_WORDS" > "$RUN/work/prompt.txt"
PROMPT="$(cat "$RUN/work/prompt.txt")"

# Credentials: only the selected harness receives its throwaway credential directory.
# Claude: a login done inside the container (sandbox/docker/claude_login.sh) lands in
# runs/.claude-home/.credentials.json. Fallbacks: CLAUDE_CODE_OAUTH_TOKEN, or the host's
# ~/.claude/.credentials.json (Linux hosts only; macOS keeps it in the Keychain).
CLAUDE_ENV=()
AGENT_SECRET_MOUNTS=()
if [ "$AGENT" = claude ]; then
  mkdir -p "$SECRETS/claude"
  # Preferred: a long-lived setup token. Copied refresh credentials otherwise
  # rotate under parallel trials and are deliberately never mounted for another agent.
  if [ -s "$ROOT/runs/.claude-oauth-token" ]; then
    export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < "$ROOT/runs/.claude-oauth-token")"
    CLAUDE_ENV=(-e CLAUDE_CODE_OAUTH_TOKEN)
  elif [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    CLAUDE_ENV=(-e CLAUDE_CODE_OAUTH_TOKEN)
  elif [ -f "$ROOT/runs/.claude-home/.credentials.json" ]; then
    cp "$ROOT/runs/.claude-home/.credentials.json" "$SECRETS/claude/.credentials.json"
  elif [ -f "$HOME/.claude/.credentials.json" ]; then
    cp "$HOME/.claude/.credentials.json" "$SECRETS/claude/.credentials.json"
  else
    echo "no Claude credentials: run sandbox/docker/claude_login.sh once" >&2; exit 1
  fi
  AGENT_SECRET_MOUNTS=(-v "$SECRETS/claude:/home/agent/.claude")
fi
# ReAct scaffold: OpenRouter key from runs/.openrouter_key.<model with / -> _> (per-model), else env, else runs/.openrouter_key (all gitignored).
REACT_ENV=()
if [ "$AGENT" = react ]; then
  [ -s "$ROOT/runs/.openrouter_key.${MODEL//\//_}" ] && export OPENROUTER_API_KEY="$(cat "$ROOT/runs/.openrouter_key.${MODEL//\//_}")"
  [ -z "${OPENROUTER_API_KEY:-}" ] && [ -s "$ROOT/runs/.openrouter_key" ] && export OPENROUTER_API_KEY="$(cat "$ROOT/runs/.openrouter_key")"
  [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "no OpenRouter key: export OPENROUTER_API_KEY or write runs/.openrouter_key" >&2; exit 1; }
  REACT_ENV=(-e OPENROUTER_API_KEY)
fi
if [ "$AGENT" = codex ]; then
  mkdir -p "$SECRETS/codex"
  if [ -f "$HOME/.codex/auth.json" ]; then
    cp "$HOME/.codex/auth.json" "$SECRETS/codex/auth.json"
  else
    echo "no Codex credentials: run \`codex login\` on the host" >&2; exit 1
  fi
  # Keep the rollout for per-call token and reasoning-item auditing.
  printf 'approval_policy = "never"\nsandbox_mode = "danger-full-access"\nweb_search = "disabled"\nmodel_reasoning_summary = "detailed"\nshow_raw_agent_reasoning = true\n[features]\nhooks = true\n' > "$SECRETS/codex/config.toml"
  AGENT_SECRET_MOUNTS=(-v "$SECRETS/codex:/home/agent/.codex")
fi
# After every tool call, Claude Code and Codex feed the agent its remaining time (sandbox/time_left.sh reads MBAB_DEADLINE_EPOCH).
# Both CLIs accept the same hook file shape; Codex additionally needs the codex_hooks feature and the hook-trust bypass flag.
HOOKS='{"hooks":{"PostToolUse":[{"hooks":[{"type":"command","command":"/sandbox/time_left.sh"},{"type":"command","command":"python3 /sandbox/report_length.py --hook PostToolUse"}]}],"Stop":[{"hooks":[{"type":"command","command":"python3 /sandbox/report_length.py --hook Stop"}]}]}}'
# Claude Code may switch model after a safeguard refusal (fable-5.1 -> opus-5 -> opus-4.8). We let it: the
# trial keeps running and the switch is recorded in meta.json (model_fallback) and in the report's filename.
if [ "$AGENT" = claude ]; then printf '%s\n' "$HOOKS" > "$SECRETS/claude/settings.json"; fi
if [ "$AGENT" = codex ]; then printf '%s\n' "$HOOKS" > "$SECRETS/codex/hooks.json"; fi
chmod -R a+rwX "$SECRETS" "$RUN/work"   # container user is uid 1000, which may not be us

docker network create --internal "$NET" >/dev/null
docker run -d --name "$PROXY" --network bridge "$IMAGE" python3 -u /sandbox/proxy.py --bind 0.0.0.0 --port 3128 --agent "$AGENT" >/dev/null
docker network connect "$NET" "$PROXY"

# The canary gets the identical network and data view, but never a credential.
DOCKER_BASE=(--rm --network "$NET" --dns 0.0.0.0 --cap-drop ALL --security-opt no-new-privileges
  -e HTTPS_PROXY="http://$PROXY:3128" -e HTTP_PROXY="http://$PROXY:3128" -e NO_PROXY=
  -v "$RUN/work:/work" -v "$DATA_DIR:/work/data:ro"
  -w /work)
CANARY_ARGS=("${DOCKER_BASE[@]}" "$IMAGE")
# The agent gets only its own credentials. The image already contains the helper scripts.
DOCKER_ARGS=("${DOCKER_BASE[@]}" ${CLAUDE_ENV[@]+"${CLAUDE_ENV[@]}"} ${REACT_ENV[@]+"${REACT_ENV[@]}"} ${AGENT_SECRET_MOUNTS[@]+"${AGENT_SECRET_MOUNTS[@]}"} "$IMAGE")

# Canary: same image, network and mounts. Abort the trial if isolation does not hold.
case "$AGENT" in claude) VENDOR_HOST=api.anthropic.com ;; codex) VENDOR_HOST=chatgpt.com ;; react) VENDOR_HOST=openrouter.ai ;; *) echo "unknown agent $AGENT" >&2; exit 2 ;; esac
docker run -e VENDOR_HOST="$VENDOR_HOST" "${CANARY_ARGS[@]}" bash -c '
  fail=0
  getent hosts collusion.wiki >/dev/null 2>&1 && { echo "FAIL dns resolves"; fail=1; }
  curl -s -m 8 https://collusion.wiki/ >/dev/null 2>&1 && { echo "FAIL proxy let collusion.wiki through"; fail=1; }
  env -u HTTPS_PROXY -u HTTP_PROXY curl -s -m 8 https://collusion.wiki/ >/dev/null 2>&1 && { echo "FAIL direct egress"; fail=1; }
  env -u HTTPS_PROXY -u HTTP_PROXY curl -s -m 8 https://1.1.1.1/ >/dev/null 2>&1 && { echo "FAIL direct egress by ip"; fail=1; }
  code=$(curl -s -m 20 -o /dev/null -w "%{http_code}" "https://$VENDOR_HOST/"); [ "$code" != 000 ] || { echo "FAIL vendor host $VENDOR_HOST unreachable via proxy"; fail=1; }
  echo "--- files visible under /work:"; find /work -type f | sort
  echo "--- bind mounts:"; awk "\$2 ~ /^\/(work|home)/ {print \$2, \$4}" /proc/mounts
  exit $fail' > "$RUN/canary.log" 2>&1 || { cat "$RUN/canary.log"; echo "canary failed; trial aborted" >&2; exit 3; }
EXPECT="$( { (cd "$RUN/work" && find . -type f | sed 's#^\./#/work/#'); (cd "$DATA_DIR" && find . -type f | sed 's#^\./#/work/data/#'); } | sort)"
GOT="$(sed -n '/^--- files/,/^--- bind/p' "$RUN/canary.log" | grep '^/work')"
[ "$EXPECT" = "$GOT" ] || { echo "canary: unexpected files in /work" >&2; diff <(echo "$EXPECT") <(echo "$GOT") >&2; exit 3; }

cat > "$RUN/meta.json" <<JSON
{"agent":"$AGENT","model":"$MODEL","effort":"$EFFORT","replicate":$REPLICATE,"run_id":"$RUN_ID","config":"$CFG_NAME","config_sha256":"$(shasum -a 256 "$CONFIG" | cut -c1-64)",
 "isolation":"provider_network_shared","allow_networked_subscription":true,
 "report_min_words":$REPORT_MIN_WORDS,"report_max_words":$REPORT_MAX_WORDS,"report_accept_min_words":$REPORT_ACCEPT_MIN_WORDS,"report_accept_max_words":$REPORT_ACCEPT_MAX_WORDS,
 "prompt":"$PROMPT_NAME","condition":"$CFG_NAME","budget_min":$BUDGET_MIN,"timeout":"$TIMEOUT","data_variant":"$VARIANT",
 "started":"$STAMP","data_dir":"$DATA_DIR","prompt_sha256":"$(shasum -a 256 "$RUN/work/prompt.txt" | cut -c1-64)","prompt_template_sha256":"$(shasum -a 256 "$PROMPT_FILE" | cut -c1-64)",
 "image":"$IMAGE","cli_version":"$([ "$AGENT" = react ] && echo react_agent.py || docker run --rm "$IMAGE" "$AGENT" --version 2>/dev/null | head -1)"}
JSON

echo "run: $RUN"
START=$(date +%s); set +e
HARD_DEADLINE="$((START + $(timeout_seconds "$TIMEOUT")))"
# The clock the agent is told about: the deadline is BUDGET_MIN from launch, exported so the hook and the ReAct loop agree.
TIME_ENV=(-e MBAB_REPORT_MIN_WORDS="$REPORT_MIN_WORDS" -e MBAB_REPORT_MAX_WORDS="$REPORT_MAX_WORDS" -e MBAB_DEADLINE_EPOCH="$((START + BUDGET_MIN * 60))" -e MBAB_BUDGET_MIN="$BUDGET_MIN")
case "$AGENT" in
  claude)
    docker run -i "${TIME_ENV[@]}" "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" claude -p "$PROMPT" \
      --model "$MODEL" --effort "$EFFORT" \
      --dangerously-skip-permissions --no-chrome --no-session-persistence --setting-sources user \
      ${CLAUDE_DISALLOWED[@]+--disallowedTools "${CLAUDE_DISALLOWED[@]}"} \
      --output-format stream-json --verbose \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  codex)
    # Codex does not retry "Selected model is at capacity" (a provider blip that killed a 2 h trial once).
    # Relaunch up to 3 times when the run ends on that error before any turn completed; the deadline stays fixed.
    for attempt in 1 2 3; do
      remaining="$((HARD_DEADLINE - $(date +%s)))"
      if [ "$remaining" -le 0 ]; then RC=124; break; fi
      docker run -i "${TIME_ENV[@]}" "${DOCKER_ARGS[@]}" timeout -k 30s "${remaining}s" codex exec -C /work \
        --model "$MODEL" -c "model_reasoning_effort=\"$EFFORT\"" \
        --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust --skip-git-repo-check --ignore-rules \
        --json -o /work/final_message.md "$PROMPT" \
        < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$?
      if grep -q 'is at capacity' "$RUN/transcript.jsonl" && ! grep -q '"turn.completed"' "$RUN/transcript.jsonl" && [ "$attempt" -lt 3 ]; then
        echo "codex: model at capacity, relaunching (attempt $((attempt+1)))" >&2
        mv "$RUN/transcript.jsonl" "$RUN/transcript.attempt$attempt.jsonl"
        mv "$RUN/stderr.log" "$RUN/stderr.attempt$attempt.log"
        remaining="$((HARD_DEADLINE - $(date +%s)))"
        [ "$remaining" -gt 0 ] || { RC=124; break; }
        sleep_seconds=$((remaining < 30 ? remaining : 30))
        sleep "$sleep_seconds"
        continue
      fi
      break
    done ;;
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
python3 "$ROOT/messageboard_audit_bench/usage.py" "$RUN" --quiet || { echo "usage summary failed" >&2; [ "$RC" -eq 0 ] && RC=6; }
python3 - "$RUN" "$RC" "$((END-START))" <<'PY'
import json,sys,pathlib
run,rc,secs=pathlib.Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
m=json.loads((run/"meta.json").read_text()); m.update(exit_code=rc,wall_seconds=secs,report_exists=(run/"report.md").exists())
# Claude Code may switch models after a refusal ({"type":"system","subtype":"model_refusal_fallback",...}). The trial
# stays valid but is labelled: meta.model_fallback and meta.model_served (the last model that answered) record it.
fb=[json.loads(l) for l in (run/"transcript.jsonl").read_text().splitlines() if '"model_refusal_fallback"' in l]
if fb:
    m["model_fallback"]={"fallback_model":fb[-1].get("fallback_model"),"trigger":fb[0].get("trigger"),"category":fb[0].get("api_refusal_category"),"events":len(fb),
                         "chain":[m["model"]]+[e.get("fallback_model") for e in fb]}
    m["model_served"]=fb[-1].get("fallback_model")
    print(f"WARN model fallback: {' -> '.join(m['model_fallback']['chain'])} ({fb[0].get('api_refusal_category')})",file=sys.stderr)
# ReAct: a provider refusal ends the turn with no tool call (OpenRouter native_finish_reason "refusal"); same treatment, exit 5.
rf=[l for l in (run/"transcript.jsonl").read_text().splitlines() if '"native_finish_reason": "refusal"' in l or '"finish_reason": "content_filter"' in l or '"stop_reason":"refusal"' in l]
if rf:
    m["model_refusal"]={"events":len(rf)}
    print(f"FAIL model refusal: {m['model']} refused ({len(rf)} refusal responses)",file=sys.stderr)
    # exit 5 = ended by a refusal (ReAct exits 0 in that case; Claude Code exits 1 with "safeguards flagged" as its
    # result). One code for both so the Inspect solver's refusal rerun applies to every harness.
    if rc in (0,1): rc=5; m["exit_code"]=rc
u=json.loads((run/"usage.json").read_text()) if (run/"usage.json").exists() else {}
m["usage"]={k:u.get(k) for k in ("usage_schema","input_tokens","input_tokens_uncached","output_tokens","cache_read_tokens","cache_write_tokens","cache_read_fraction","reasoning_tokens",
            "cost_usd","api_calls","tool_calls","api_retries","api_errors","peak_context_tokens","terminal_reason","is_error","usage_source")}
(run/"meta.json").write_text(json.dumps(m,indent=1)); print(json.dumps(m,indent=1))
(run/".final_exit_code").write_text(str(rc))
PY
RC="$(< "$RUN/.final_exit_code")"; rm -f "$RUN/.final_exit_code"
exit "$RC"
