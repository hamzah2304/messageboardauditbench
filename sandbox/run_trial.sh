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
# One sandbox user per concurrent trial, so runs cannot see each other. Pick an
# idle user from the pool (create more with sandbox/ensure_user.sh agentboxN).
if [ -z "${SANDBOX_USER:-}" ]; then
  for u in agentbox1 agentbox2 agentbox3 agentbox4 agentbox5 agentbox6; do
    id "$u" >/dev/null 2>&1 || continue
    pgrep -u "$u" >/dev/null 2>&1 && continue
    SANDBOX_USER="$u"; break
  done
fi
SBU="${SANDBOX_USER:?no idle sandbox user; run sandbox/ensure_user.sh agentboxN}"
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT/data/raw_stripped}"
[ -d "$DATA_DIR" ] || { echo "no data at $DATA_DIR; run scripts/fetch_data.sh then strip_analysis_fields.py" >&2; exit 1; }

# Proxy must be up (start with: sandbox/start_proxy.sh)
curl -s -o /dev/null -x "http://127.0.0.1:$PROXY_PORT" https://api.anthropic.com/ >/dev/null 2>&1 || true
python3 - "$PROXY_PORT" <<'EOF' || { echo "proxy not listening; run sandbox/start_proxy.sh" >&2; exit 1; }
import socket,sys; s=socket.create_connection(("127.0.0.1",int(sys.argv[1])),2); s.close()
EOF

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${STAMP}_${AGENT}_${MODEL}_s${SEED}"
RUN="$ROOT/runs/$NAME"                      # host side: logs + meta, never visible to the agent
AB_RUNS="/srv/agentbox/runs"               # outside agentbox's home so our group can traverse
WORK="$AB_RUNS/$NAME"                  # agent side: data + prompt only
mkdir -p "$RUN"
sudo mkdir -p "$WORK/data"
sudo cp "$DATA_DIR"/*.jsonl "$WORK/data/"
sudo cp "$HERE/prompt.txt" "$WORK/prompt.txt"
# The trial user owns its work dir; our group can traverse (the launching shell cds in); other sandbox users cannot.
sudo mkdir -p "$AB_RUNS" && sudo chown "root:$(id -gn)" "$AB_RUNS" && sudo chown "$SBU:$(id -gn)" "$WORK" "$WORK/data" && sudo chown "$SBU" "$WORK"/data/* "$WORK/prompt.txt"
sudo chmod 751 "$AB_RUNS" && sudo chmod 750 "$WORK"   # parent: traversable, not listable
cat > "$RUN/meta.json" <<EOF
{"agent":"$AGENT","model":"$MODEL","effort":"$EFFORT","seed":$SEED,"timeout":"$TIMEOUT","sandbox_user":"$SBU",
 "started":"$STAMP","data_dir":"$DATA_DIR","prompt_sha256":"$(sha256sum "$HERE/prompt.txt" | cut -c1-64)",
 "cli_version":"$(/opt/agentbox/bin/$AGENT --version 2>/dev/null | head -1)"}
EOF
# Canary: from the agent's identity, the repo must be unreadable and the web unreachable.
sudo -u "$SBU" ls "$ROOT" >/dev/null 2>&1 && { echo "CANARY FAIL: $SBU can read the repo" >&2; exit 3; }
sudo -u "$SBU" getent hosts collusion.wiki >/dev/null 2>&1 && { echo "CANARY FAIL: $SBU can resolve DNS" >&2; exit 3; }
[ "$(sudo -u "$SBU" find /tmp -maxdepth 2 -type f -readable 2>/dev/null | wc -l)" = "0" ] || { echo "CANARY FAIL: $SBU can read files in /tmp" >&2; exit 3; }
sudo -u "$SBU" curl -s -m 5 -o /dev/null https://collusion.wiki/ && { echo "CANARY FAIL: direct egress works" >&2; exit 3; }
sudo -u "$SBU" env HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT" curl -s -m 5 -o /dev/null https://collusion.wiki/ && { echo "CANARY FAIL: proxy forwards non-vendor host" >&2; exit 3; }
sudo -u "$SBU" env HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT" curl -s -m 10 -o /dev/null https://api.anthropic.com/ || { echo "CANARY FAIL: vendor host unreachable via proxy" >&2; exit 3; }
echo "canary ok: repo unreadable, egress blocked, vendor reachable" | tee "$RUN/canary.txt"

ENVV=(HOME="$(getent passwd "$SBU" | cut -d: -f6)" PATH="/opt/agentbox/bin:/usr/local/bin:/usr/bin:/bin"
      HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT" HTTP_PROXY="http://127.0.0.1:$PROXY_PORT" NO_PROXY="127.0.0.1,localhost"
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 TERM=dumb)
PROMPT="$(cat "$HERE/prompt.txt")"

echo "run: $RUN"
START=$(date +%s)
set +e
case "$AGENT" in
  claude)
    (cd "$WORK" && sudo -u "$SBU" env "${ENVV[@]}" timeout "$TIMEOUT" /opt/agentbox/bin/claude -p "$PROMPT" \
      --model "$MODEL" --effort "$EFFORT" \
      --dangerously-skip-permissions --no-chrome --no-session-persistence \
      --setting-sources user \
      --output-format stream-json --verbose \
      --disallowedTools WebFetch WebSearch Task Skill ToolSearch RemoteTrigger SendMessage ListAgents Workflow CronCreate CronDelete CronList ScheduleWakeup EnterWorktree \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log")
    RC=$?
    ;;
  codex)
    (cd "$WORK" && sudo -u "$SBU" env "${ENVV[@]}" timeout "$TIMEOUT" /opt/agentbox/bin/codex exec -C "$WORK" \
      --model "$MODEL" -c "model_reasoning_effort=\"$EFFORT\"" \
      --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --ignore-rules \
      --json -o "$WORK/final_message.md" \
      "$PROMPT" \
      < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log")
    RC=$?
    ;;
  *) echo "unknown agent $AGENT" >&2; exit 2 ;;
esac
set -e
END=$(date +%s)
# Pull the agent's outputs back to the host-side run dir, then remove its copy and
# the CLI's per-user scratch (Claude Code writes task output under /tmp/claude-<uid>).
sudo mv "$WORK"/* "$RUN"/ 2>/dev/null || true
sudo rm -rf "$WORK" "/tmp/claude-$(id -u "$SBU")"
sudo chown -R "$(id -un):$(id -gn)" "$RUN"
python3 - "$RUN" "$RC" "$((END-START))" <<'EOF'
import json,sys,pathlib
run,rc,secs=pathlib.Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
m=json.loads((run/"meta.json").read_text()); m.update(exit_code=rc,wall_seconds=secs,report_exists=(run/"report.md").exists())
(run/"meta.json").write_text(json.dumps(m,indent=1))
print(json.dumps(m,indent=1))
EOF
