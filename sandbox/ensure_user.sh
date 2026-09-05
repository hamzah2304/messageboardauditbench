#!/usr/bin/env bash
# Create (idempotently) one sandbox user for a single concurrent trial slot.
#   sandbox/ensure_user.sh agentbox2
# Every sandbox user has primary group `agentbox`, a 700 home with its own copy
# of the CLI credentials, and is covered by the group-level egress lock.
set -euo pipefail
U="${1:?user name}"
getent group agentbox >/dev/null || sudo groupadd agentbox
if ! id "$U" >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash -g agentbox "$U"
fi
H="$(getent passwd "$U" | cut -d: -f6)"
sudo chmod 700 "$H"
sudo mkdir -p "$H/.claude" "$H/.codex"
sudo cp -f "$HOME/.claude/.credentials.json" "$H/.claude/.credentials.json"
sudo cp -f "$HOME/.codex/auth.json" "$H/.codex/auth.json"
sudo tee "$H/.codex/config.toml" >/dev/null <<'EOF'
approval_policy = "never"
sandbox_mode = "danger-full-access"
EOF
sudo tee "$H/.claude/settings.json" >/dev/null <<'EOF'
{"env":{"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC":"1","DISABLE_AUTOUPDATER":"1"}}
EOF
sudo chown -R "$U:agentbox" "$H/.claude" "$H/.codex"
sudo chmod 600 "$H/.claude/.credentials.json" "$H/.codex/auth.json"

# Egress lock keyed on the shared group, so every sandbox user is covered.
GID="$(getent group agentbox | cut -d: -f3)"
if ! sudo iptables -C OUTPUT -m owner --gid-owner "$GID" -j AGENTBOX 2>/dev/null; then
  sudo iptables -I OUTPUT 1 -m owner --gid-owner "$GID" -j AGENTBOX
fi
if command -v ip6tables >/dev/null && ! sudo ip6tables -C OUTPUT -m owner --gid-owner "$GID" -j AGENTBOX 2>/dev/null; then
  sudo ip6tables -I OUTPUT 1 -m owner --gid-owner "$GID" -j AGENTBOX
fi
echo "sandbox user $U ready (uid $(id -u "$U"), group agentbox, home $H mode 700)"
