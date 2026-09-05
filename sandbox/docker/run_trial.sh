#!/usr/bin/env bash
# Run one trial in Docker with structural isolation.
#
#   sandbox/docker/run_trial.sh claude claude-opus-5 1
#   sandbox/docker/run_trial.sh codex  gpt-5.6-sol   1
#   sandbox/docker/run_trial.sh react  moonshotai/kimi-k3 1   # ReAct scaffold via OpenRouter
#
# Env knobs: EFFORT (high), BUDGET_MIN (20; rendered into the prompt, react also stops calling the model after it),
#            TIMEOUT (BUDGET_MIN+5 minutes; hard kill), DATA_DIR (data/raw_stripped; data/verbatim adds _verbatim to
#            the run name; a non-default budget adds _b<min>), IMAGE (mbab-sandbox).
#
# Isolation comes from structure, not permissions:
#   * the agent container is on an `internal` Docker network (no gateway, nothing routable)
#     and its only way out is HTTPS_PROXY -> a proxy container that allowlists vendor API hosts
#   * the container sees /work (data/*.jsonl read-only + prompt.txt) and its own creds. No repo mount.
#   * a canary container on the same network/mounts proves both facts before the agent starts.
set -euo pipefail
AGENT="${1:?claude|codex|react}"; MODEL="${2:?model id}"; SEED="${3:-1}"
EFFORT="${EFFORT:-high}"; IMAGE="${IMAGE:-mbab-sandbox}"
# Time budget: BUDGET_MIN is what the prompt tells the agent; the container is killed TIMEOUT later (default budget + 5 min).
BUDGET_MIN="${BUDGET_MIN:-20}"; TIMEOUT="${TIMEOUT:-$((BUDGET_MIN + 5))m}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT/data/raw_stripped}"
[ -d "$DATA_DIR" ] || { echo "no data at $DATA_DIR; run scripts/build_data.sh" >&2; exit 1; }

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -q -t "$IMAGE" -f "$HERE/Dockerfile" "$ROOT" >/dev/null

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# Data variant (basename of DATA_DIR) goes into the run name unless it is the default, and always into meta.
VARIANT="$(basename "$DATA_DIR")"; SUFFIX=""; [ "$VARIANT" = raw_stripped ] || SUFFIX="_$VARIANT"; [ "$BUDGET_MIN" = 20 ] || SUFFIX="${SUFFIX}_b${BUDGET_MIN}"
RUN="$ROOT/runs/${STAMP}_${AGENT}_${MODEL//\//_}_s${SEED}${SUFFIX}"
# Secrets live under the run dir (not /tmp): Docker Desktop/colima only share $HOME with the VM.
NET="mbab-inner-$STAMP"; PROXY="mbab-proxy-$STAMP"; SECRETS="$RUN/.secrets"
mkdir -p "$RUN/work/data" "$SECRETS/claude" "$SECRETS/codex"
cp "$DATA_DIR"/*.jsonl "$RUN/work/data/"
# The prompt template has one placeholder, {{BUDGET_MIN}}; the rendered prompt is what the agent sees and what gets hashed.
sed "s/{{BUDGET_MIN}}/$BUDGET_MIN/g" "$HERE/../prompt.txt" > "$RUN/work/prompt.txt"
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
printf 'approval_policy = "never"\nsandbox_mode = "danger-full-access"\nweb_search = "disabled"\n' > "$SECRETS/codex/config.toml"
chmod -R a+rwX "$SECRETS" "$RUN/work"   # container user is uid 1000, which may not be us

cleanup() { docker logs "$PROXY" > "$RUN/proxy.log" 2>&1 || true; docker rm -f "$PROXY" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; rm -rf "$SECRETS"; }
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
{"agent":"$AGENT","model":"$MODEL","effort":"$EFFORT","seed":$SEED,"budget_min":$BUDGET_MIN,"timeout":"$TIMEOUT","data_variant":"$VARIANT",
 "started":"$STAMP","data_dir":"$DATA_DIR","prompt_sha256":"$(shasum -a 256 "$RUN/work/prompt.txt" | cut -c1-64)","prompt_template_sha256":"$(shasum -a 256 "$HERE/../prompt.txt" | cut -c1-64)",
 "image":"$IMAGE","cli_version":"$([ "$AGENT" = react ] && echo react_agent.py || docker run --rm "$IMAGE" "$AGENT" --version 2>/dev/null | head -1)"}
JSON

echo "run: $RUN"
START=$(date +%s); set +e
case "$AGENT" in
  claude)
    docker run -i "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" claude -p "$PROMPT" \
      --model "$MODEL" --effort "$EFFORT" \
      --dangerously-skip-permissions --no-chrome --no-session-persistence --setting-sources user \
      --disallowedTools WebFetch WebSearch Task Skill ToolSearch RemoteTrigger SendMessage ListAgents Workflow CronCreate CronDelete CronList ScheduleWakeup EnterWorktree \
      --output-format stream-json --verbose \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  codex)
    docker run -i "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" codex exec -C /work \
      --model "$MODEL" -c "model_reasoning_effort=\"$EFFORT\"" \
      --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --ignore-rules --ephemeral \
      --json -o /work/final_message.md "$PROMPT" \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  react)
    docker run -i "${DOCKER_ARGS[@]}" timeout -k 30s "$TIMEOUT" python3 -u /sandbox/react_agent.py \
      --model "$MODEL" --effort "$EFFORT" --prompt-file /work/prompt.txt --cwd /work --budget-min "$BUDGET_MIN" \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"; RC=$? ;;
  *) echo "unknown agent $AGENT" >&2; exit 2 ;;
esac
set -e; END=$(date +%s)
for f in report.md final_message.md; do [ -f "$RUN/work/$f" ] && cp "$RUN/work/$f" "$RUN/$f"; done
python3 - "$RUN" "$RC" "$((END-START))" <<'PY'
import json,sys,pathlib
run,rc,secs=pathlib.Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
m=json.loads((run/"meta.json").read_text()); m.update(exit_code=rc,wall_seconds=secs,report_exists=(run/"report.md").exists())
(run/"meta.json").write_text(json.dumps(m,indent=1)); print(json.dumps(m,indent=1))
PY
