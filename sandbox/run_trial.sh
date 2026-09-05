#!/usr/bin/env bash
# Launch one baseline trial in the lightweight sandbox.
#
#   sandbox/run_trial.sh claude claude-opus-5 1
#   sandbox/run_trial.sh codex  gpt-5.6-sol   1
#
# Env knobs: EFFORT (default medium), TIMEOUT (default 25m), PROXY_PORT (3128),
#            DATA_DIR (default data/raw_stripped).
set -euo pipefail
AGENT="${1:?claude|codex}"; MODEL="${2:?model id}"; SEED="${3:-1}"
EFFORT="${EFFORT:-medium}"; TIMEOUT="${TIMEOUT:-25m}"; PROXY_PORT="${PROXY_PORT:-3128}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT/data/raw_stripped}"
[ -d "$DATA_DIR" ] || { echo "no data at $DATA_DIR; run scripts/fetch_data.sh then strip_analysis_fields.py" >&2; exit 1; }

# Proxy must be up (start with: sandbox/start_proxy.sh)
curl -s -o /dev/null -x "http://127.0.0.1:$PROXY_PORT" https://api.anthropic.com/ >/dev/null 2>&1 || true
python3 - "$PROXY_PORT" <<'EOF' || { echo "proxy not listening; run sandbox/start_proxy.sh" >&2; exit 1; }
import socket,sys; s=socket.create_connection(("127.0.0.1",int(sys.argv[1])),2); s.close()
EOF

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="$ROOT/runs/${STAMP}_${AGENT}_${MODEL}_s${SEED}"
mkdir -p "$RUN/data"
cp "$DATA_DIR"/*.jsonl "$RUN/data/"
cp "$HERE/prompt.txt" "$RUN/prompt.txt"
cat > "$RUN/meta.json" <<EOF
{"agent":"$AGENT","model":"$MODEL","effort":"$EFFORT","seed":$SEED,"timeout":"$TIMEOUT",
 "started":"$STAMP","data_dir":"$DATA_DIR","prompt_sha256":"$(sha256sum "$HERE/prompt.txt" | cut -c1-64)",
 "cli_version":"$(/opt/agentbox/bin/$AGENT --version 2>/dev/null | head -1)"}
EOF
# The agent owns the run dir; the two log files stay ours because this shell
# (not the agent) opens them for the redirects below.
touch "$RUN/transcript.jsonl" "$RUN/stderr.log"
sudo chown -R agentbox:agentbox "$RUN"
sudo chown "$(id -un):$(id -gn)" "$RUN/transcript.jsonl" "$RUN/stderr.log"

ENVV=(HOME="$(getent passwd agentbox | cut -d: -f6)" PATH="/opt/agentbox/bin:/usr/local/bin:/usr/bin:/bin"
      HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT" HTTP_PROXY="http://127.0.0.1:$PROXY_PORT" NO_PROXY="127.0.0.1,localhost"
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 TERM=dumb)
PROMPT="$(cat "$HERE/prompt.txt")"

echo "run: $RUN"
START=$(date +%s)
set +e
case "$AGENT" in
  claude)
    (cd "$RUN" && sudo -u agentbox env "${ENVV[@]}" timeout "$TIMEOUT" /opt/agentbox/bin/claude -p "$PROMPT" \
      --model "$MODEL" --effort "$EFFORT" \
      --dangerously-skip-permissions --no-chrome --no-session-persistence \
      --setting-sources user \
      --output-format stream-json --verbose \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log")
    RC=$?
    ;;
  codex)
    (cd "$RUN" && sudo -u agentbox env "${ENVV[@]}" timeout "$TIMEOUT" /opt/agentbox/bin/codex exec -C "$RUN" \
      --model "$MODEL" -c "model_reasoning_effort=\"$EFFORT\"" \
      --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --ignore-rules \
      --json -o "$RUN/final_message.md" \
      "$PROMPT" \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log")
    RC=$?
    ;;
  *) echo "unknown agent $AGENT" >&2; exit 2 ;;
esac
set -e
END=$(date +%s)
sudo chown -R "$(id -un):$(id -gn)" "$RUN"
python3 - "$RUN" "$RC" "$((END-START))" <<'EOF'
import json,sys,pathlib
run,rc,secs=pathlib.Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
m=json.loads((run/"meta.json").read_text()); m.update(exit_code=rc,wall_seconds=secs,report_exists=(run/"report.md").exists())
(run/"meta.json").write_text(json.dumps(m,indent=1))
print(json.dumps(m,indent=1))
EOF
