#!/usr/bin/env bash
# One-time (idempotent) host setup for the lightweight sandbox. Needs sudo.
#
#   * creates an unprivileged user `agentbox` with its own home
#   * copies the claude and codex binaries into /opt/agentbox/bin
#   * copies the subscription credentials into agentbox's home (mode 600)
#   * installs iptables rules so agentbox can only talk to 127.0.0.1
#     (the allowlisting proxy) and nothing else
#
# Re-run after upgrading a CLI or re-logging in.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ME="$(id -un)"

if ! id agentbox >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash agentbox
fi
AB_HOME="$(getent passwd agentbox | cut -d: -f6)"

# CLI binaries (both are standalone executables)
sudo mkdir -p /opt/agentbox/bin
sudo cp -f "$(readlink -f "$(command -v claude)")" /opt/agentbox/bin/claude
# codex needs its sibling helper (codex-code-mode-host) in the same directory
sudo cp -f "$(dirname "$(readlink -f "$(command -v codex)")")"/* /opt/agentbox/bin/
sudo chmod 755 /opt/agentbox/bin/*

# Credentials. Claude Code keeps a refreshable OAuth token; Codex keeps auth.json.
sudo mkdir -p "$AB_HOME/.claude" "$AB_HOME/.codex"
sudo cp -f "$HOME/.claude/.credentials.json" "$AB_HOME/.claude/.credentials.json"
sudo cp -f "$HOME/.codex/auth.json" "$AB_HOME/.codex/auth.json"
# Minimal codex config: no project trust, no features, model set per run.
sudo tee "$AB_HOME/.codex/config.toml" >/dev/null <<'EOF'
approval_policy = "never"
sandbox_mode = "danger-full-access"
EOF
# Minimal claude settings: no telemetry/update traffic, no plugins.
sudo tee "$AB_HOME/.claude/settings.json" >/dev/null <<'EOF'
{"env":{"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC":"1","DISABLE_AUTOUPDATER":"1"}}
EOF
sudo chown -R agentbox:agentbox "$AB_HOME/.claude" "$AB_HOME/.codex"
sudo chmod 600 "$AB_HOME/.claude/.credentials.json" "$AB_HOME/.codex/auth.json"

# Runs directory: owned by us, each run dir handed to agentbox at launch.
mkdir -p "$HERE/../runs"
sudo chmod 755 "$HOME"   # agentbox needs to traverse into the repo

# Egress lock: agentbox may only reach loopback.
AB_UID="$(id -u agentbox)"
sudo iptables -N AGENTBOX 2>/dev/null || sudo iptables -F AGENTBOX
sudo iptables -A AGENTBOX -o lo -j ACCEPT
sudo iptables -A AGENTBOX -j REJECT --reject-with icmp-port-unreachable
if ! sudo iptables -C OUTPUT -m owner --uid-owner "$AB_UID" -j AGENTBOX 2>/dev/null; then
  sudo iptables -I OUTPUT 1 -m owner --uid-owner "$AB_UID" -j AGENTBOX
fi
# IPv6 too, if present
if command -v ip6tables >/dev/null; then
  sudo ip6tables -N AGENTBOX 2>/dev/null || sudo ip6tables -F AGENTBOX
  sudo ip6tables -A AGENTBOX -o lo -j ACCEPT
  sudo ip6tables -A AGENTBOX -j REJECT
  sudo ip6tables -C OUTPUT -m owner --uid-owner "$AB_UID" -j AGENTBOX 2>/dev/null \
    || sudo ip6tables -I OUTPUT 1 -m owner --uid-owner "$AB_UID" -j AGENTBOX
fi

echo "sandbox user: agentbox (uid $AB_UID), home $AB_HOME"
echo "binaries:     /opt/agentbox/bin/{claude,codex}"
echo "egress:       loopback only (iptables chain AGENTBOX)"
echo "next:         sandbox/run_trial.sh <claude|codex> <model> <seed>"
