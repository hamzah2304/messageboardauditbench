#!/usr/bin/env bash
# Exercise the subscription network topology without credentials or model calls.
# Prints one JSON result and exits non-zero if direct bridge access succeeds.
set -euo pipefail

IMAGE="${IMAGE:-mbab-sandbox-isolation-audit}"
RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
NET="mbab-probe-inner-$RUN_ID"
PROXY="mbab-probe-proxy-$RUN_ID"
TARGET="mbab-probe-target-$RUN_ID"

cleanup() {
  docker rm -f "$PROXY" "$TARGET" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create --internal "$NET" >/dev/null
docker run -d --name "$TARGET" --network bridge -p 127.0.0.1::8080 "$IMAGE" python3 -m http.server 8080 >/dev/null
TARGET_IP="$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$TARGET")"
HOST_PORT="$(docker inspect -f '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}' "$TARGET")"
docker run -d --name "$PROXY" --network bridge "$IMAGE" python3 -u /sandbox/proxy.py --bind 0.0.0.0 --port 3128 --agent claude >/dev/null
docker network connect "$NET" "$PROXY"

set +e
docker run --rm --network "$NET" --dns 0.0.0.0 "$IMAGE" sh -c "curl --noproxy '*' -fsS --connect-timeout 3 --max-time 5 http://$TARGET_IP:8080/ >/dev/null" >/dev/null 2>&1
DIRECT_RC=$?
set -e

set +e
docker run --rm --network "$NET" --dns 0.0.0.0 --add-host host.docker.internal:host-gateway "$IMAGE" sh -c "curl --noproxy '*' -fsS --connect-timeout 3 --max-time 5 http://host.docker.internal:$HOST_PORT/ >/dev/null" >/dev/null 2>&1
HOST_GATEWAY_RC=$?
set -e

python3 - "$TARGET_IP" "$DIRECT_RC" "$HOST_GATEWAY_RC" <<'PY'
import json, sys
target, rc, host_gateway_rc = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
print(json.dumps({
    "probe_schema": 1,
    "credentials_used": False,
    "model_calls": False,
    "topology": "agent on internal network; proxy attached to internal and bridge; target on bridge",
    "bridge_target_ip": target,
    "direct_bridge_service_reachable": rc == 0,
    "host_gateway_reachable": host_gateway_rc == 0,
    "result": "FAIL" if rc == 0 or host_gateway_rc == 0 else "PASS",
}, sort_keys=True))
PY
[ "$DIRECT_RC" -ne 0 ] && [ "$HOST_GATEWAY_RC" -ne 0 ]
