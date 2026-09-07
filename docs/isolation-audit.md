# Isolation audit

The native Inspect task now has the stronger network boundary: its Docker
service uses `network_mode: none`. The agent has only the loopback interface;
there is no route to the host, another trial, DNS, or the public internet. The
preflight check runs before the prompt reaches the agent. It hashes and parses
every mounted JSONL file, confirms that `/work` contains only the four intended
data files, and fails if a non-loopback interface is present. The resulting
record belongs in each Inspect sample's metadata.

Inspect's bridge normally starts its remote-exec server as root. That conflicts
with a non-root CLI when `cap_drop: ALL` removes root's usual override for file
permissions: the proxy cannot write an agent-owned bridge request directory.
The benchmark registers an Inspect Docker environment that declines root exec.
Inspect then follows its documented rootless path, so the server, model proxy,
and agent CLI all run as uid 1000. This keeps `network_mode: none`,
`cap_drop: ALL`, and `no-new-privileges` in place. A clean offline mock-model
smoke run completed for both native Claude and native Codex on 2026-09-07,
producing a verified `report.md` and two model calls for each harness.

This relies on the current Inspect Docker factory and its documented rootless
injection fallback. It should be rechecked when the Inspect dependency lock is
updated. The bridge helpers share the agent's uid, so they must remain
answer-free and are not a boundary against code running as that agent.

The subscription runner is a different execution mode. It needs a connection
to the vendor because Claude Code and Codex authenticate and make model calls
from inside the shell. It therefore cannot make the same isolation claim. Its
agent container has an internal Docker network, but it can reach a dedicated
proxy container. The proxy only permits the exact vendor hosts for that agent,
only on TCP 443. It rejects IP CONNECT targets, non-public DNS answers, other
ports, subdomains, malformed requests, and oversized request headers. It pins
the upstream socket to the public address it validated, preventing a second DNS
lookup from changing the destination.

`curl`, Python HTTP libraries, and the vendor CLIs are present in the image.
That is not itself an escape: with the native backend they have no network
interface, and with subscriptions their HTTPS CONNECT requests are subject to
the proxy. We retain allow and deny records in `proxy.log`; this is evidence of
requests that used the proxy, not proof that a subscription shell made no
vendor-mediated communication.

The remaining limitation is fundamental to in-shell subscriptions. The model
service receives each prompt and response, and a shell holding subscription
credentials can send arbitrary HTTPS application data to the allowed vendor
hosts. Separate trials must use separate credential directories, and the
subscription backend should remain an explicit opt-in. It is useful for testing
the real vendor CLI, but it is not suitable when the claim to test is that the
agent cannot communicate externally at all.

The preflight visibility check protects `/work`, where benchmark data and the
answer live. The shared image still contains the CLI binaries and small harness
helpers under `/sandbox`; those helpers must remain answer-free. Do not copy
the repository, reports, rubrics, configs, README files, evaluator outputs,
or host credential directories into the image or `/work`. A new image helper
should be reviewed as part of this audit and the preflight's expected visible
file list updated deliberately.

## Evidence recorded per run

Native Inspect logs should retain the preflight JSON alongside Inspect's live
tool trajectory and model usage. Subscription logs retain `canary.log`,
`proxy.log`, `transcript.jsonl`, `stderr.log`, and `usage.json`. The transcript
and usage parser provide tool-call counts and types, batches of parallel tool
calls, tool failures, API latency, retries, rate limits, and reported thinking
tokens when vendors expose them. A missing reported reasoning count is recorded
as unavailable rather than zero.

These records answer whether a model could read the data, what it attempted,
whether tools refused or failed, how long requests waited, and whether it made
parallel tool requests. They do not reveal encrypted reasoning text that a
vendor chooses not to expose.

## Controlled checks

The unit suite uses no credentials or model calls. It covers agent-scoped
allowlists, rejection of alternate ports and IP authorities, rejection of
loopback/private/link-local DNS answers, use of the already-validated address,
and native-preflight rejection of extra files and non-loopback interfaces.

Before a real batch, run the container canary for each subscription agent. The
controlled `bash sandbox/docker/isolation_probe.sh` check starts a temporary
bridge service plus the same internal-network/proxy topology used by a
subscription trial. It also publishes that service on a temporary loopback host
port and tries the Docker host gateway. The probe produces JSON, uses no
credentials or model calls, and fails if either path is reachable directly. On
this machine it passed on 2026-09-07 (`direct_bridge_service_reachable: false`,
`host_gateway_reachable: false`).

This is a regression check for the Docker runtime used here. It is not a proof
against every future Docker, Colima, or host-network configuration. Repeat it
before a batch after changing runtimes or network settings. The native Inspect
backend has the simpler boundary because it uses `network_mode: none` rather
than an internal network.
