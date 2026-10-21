#!/usr/bin/env bash
# Prepare a second machine (e.g. a Mac) to run AI Village trials with scripts/aivillage_batch.sh.
#
#   scripts/aivillage/aivillage_worker_setup.sh [vm-ssh-alias, default fuzzy]
#
# Copies the reasoning dataset (~16 GB) and .env from the VM, installs the Python environment,
# checks credentials and Docker, and builds the sandbox image. Safe to re-run: rsync resumes.
set -euo pipefail
cd "$(dirname "$0")/../.."
VM="${1:-fuzzy}"
for tool in docker jq uv rsync; do command -v "$tool" >/dev/null || { echo "missing $tool (brew install $tool, or Docker Desktop)" >&2; exit 1; }; done
docker info >/dev/null 2>&1 || { echo "Docker is not running" >&2; exit 1; }
mem_gb=$(( $(docker info --format '{{.MemTotal}}') / 1000000000 ))
[ "$mem_gb" -ge 24 ] || echo "WARNING: Docker has ${mem_gb} GB of memory; give it at least 24 GB for 11 runs at once"

[ -f .env ] || rsync -a "$VM:Dev/MessageBoardAuditBench/.env" .env
mkdir -p data/aivillage runs
rsync -az --partial --info=progress2 "$VM:Dev/MessageBoardAuditBench/data/aivillage/full-v2-reasoning" data/aivillage/
uv sync -q

[ -f "$HOME/.codex/auth.json" ] || echo "MISSING Codex login: run 'codex login'"
[ -s runs/.claude-oauth-token ] || echo "MISSING Claude token: run 'claude setup-token' and save the token to runs/.claude-oauth-token"

docker build -q -t mbab-pinned-sandbox-codex-0.160.0-claude-2.1.283 \
  --build-arg CODEX_VERSION=rust-v0.160.0 --build-arg CLAUDE_VERSION=2.1.283 -f sandbox/docker/Dockerfile . >/dev/null
echo "ready: scripts/aivillage/aivillage_batch.sh --replicates 3 --sync-to $VM"
