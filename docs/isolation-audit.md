# Isolation and logging for future runs

Subscription evaluations preserve the normal Claude Code and Codex CLI tools.
Their containers hold the selected subscription credentials and can reach that
provider's permitted HTTPS endpoints through the restricted proxy. This is the
accepted evaluation setup. A successful run does not establish that commands
could not communicate through those endpoints or read those credentials.

The proxy permits exact provider hosts on port 443, rejects other hosts and
ports, rejects non-public DNS answers, and connects to the address it validated.
The agent container uses an internal Docker network and has no direct internet
route. A preflight checks DNS, direct egress, denied proxy destinations,
provider connectivity, and visible work files. These checks test the configured
boundary on the current Docker runtime; they are not evidence that every
possible communication channel is impossible.

Native Inspect runs retain their separate offline Docker setup, with no real
provider credentials in the container. Inspect transports model requests through
its bridge. The bridge permission fix keeps the remote-exec server and agent at
uid 1000, with `cap_drop: ALL` and `no-new-privileges`; it does not restore root's
filesystem override. Both native CLI harnesses passed the merged mock-model
integration test, including report writing, tool failure, and a parallel batch.
The normal built-in tools remain available. The abandoned MCP tool replacement
is not part of either evaluation path.

Only the four intended JSONL data files are mounted read-only as benchmark data.
Native preflight parses and hashes every file. Repository documentation, scoring
rubrics, and human reports are not mounted into the agent's work directory.
Small runtime helpers and the time/length policy are visible. The synthetic
administrator name and Cyrillic `е` remain intentional corpus evidence.

## What each run records

| Evidence | Native Inspect | Normal subscription |
|---|---|---|
| Provider-exposed reasoning and usage | Raw model API events and normalized usage | Raw CLI stream, including partial messages; Codex session rollouts; usage summary |
| Tool inputs, results, errors, refusals | Inspect messages plus CLI hook payloads; ReAct ToolEvents | Raw CLI stream/rollouts plus CLI hook payloads |
| Actual tool timing | CLI Pre/Post lifecycle timestamps, or ReAct ToolEvents | CLI Pre/Post lifecycle timestamps where emitted |
| Retries | Inspect model events and adapter events | CLI events/stderr, retained capacity-attempt streams, and recorded whole-run retries |
| Prompt and configuration | Exact sample input, config text/hash and source provenance | Immutable `prompt.txt`, config source/parsed values, resolved run metadata |
| Implementation identity | Git/source hashes, declared CLI versions; unavailable image identity explicitly flagged | Git commit/dirty patch, source archive, exact CLI version output and Docker image ID |

Hook intervals measure tool lifecycles, including hook-dispatch overhead. They
are not CPU time, and a shell tool that returns a background session can finish
before its child command does. Missing starts, missing ends, uncorrelated IDs,
and requested calls with no hook are explicit coverage gaps. A batch of tool
requests is not counted as concurrent execution unless the recorded intervals
overlap. Hook files are observable instrumentation, not tamper-proof records
against the agent sharing their filesystem permissions.

A provider may withhold reasoning text or token counts. Missing reasoning counts
remain unavailable; reported zero remains zero. Encrypted reasoning stays
opaque. Retaining the raw records lets later analysis use fields the current
parser does not recognize. Subscription imports also retain these raw artifacts
inside the portable Inspect log, including Codex rollouts and retry streams.

## Per-run audit

The subscription runner writes `audit.json` and `audit.md` after collecting its
logs. The Inspect importer includes the audit in sample metadata. They show tool
counts/types and failures, suspicious network or file-access attempts, observed
provider model changes, and logging gaps. To regenerate a single audit:

```sh
uv run python -m messageboard_audit_bench.run_audit runs/<run> --out runs/<run>
```

Command text establishes an attempt. A tool returning without a recorded error
does not prove that every operation inside its shell command succeeded. An
allowed proxy CONNECT establishes an allowed tunnel, not a successful HTTP
request. Missing served-model information is unknown, not an assumed match to
the requested model. “Nothing observed” does not mean access was impossible.

The CLI probes use dummy local providers and no credentials. The native probe
can be repeated with `uv run python tests/fixtures_native_cli_probe.py` from a
checkout with the data and Docker available. Real subscription smoke results
are recorded separately because they exercise authentication and the proxy.
