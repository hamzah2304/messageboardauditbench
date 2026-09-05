#!/usr/bin/env bash
# Start the allowlisting proxy in the background (idempotent). Log: runs/proxy.log
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
PORT="${PROXY_PORT:-3128}"
mkdir -p "$ROOT/runs"
if pgrep -f "proxy.py --port $PORT" >/dev/null; then echo "proxy already running on $PORT"; exit 0; fi
nohup python3 "$HERE/proxy.py" --port "$PORT" --log "$ROOT/runs/proxy.log" >/dev/null 2>&1 &
sleep 0.5
echo "proxy started on 127.0.0.1:$PORT, log $ROOT/runs/proxy.log"
