# One image, three roles: agent (runs a CLI or the ReAct scaffold), proxy (sandbox/proxy.py), canary.
# Nothing from the repo is copied in except proxy.py and react_agent.py.
FROM python:3.12-slim
ARG CODEX_VERSION=rust-v0.153.4
ARG CLAUDE_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl jq ripgrep sqlite3 && rm -rf /var/lib/apt/lists/*
RUN set -eux; arch="$(uname -m)"; \
    case "$arch" in aarch64) ca=arm64 ;; x86_64) ca=x64 ;; *) exit 1 ;; esac; \
    base=https://downloads.claude.ai/claude-code-releases; \
    v="$CLAUDE_VERSION"; [ "$v" = latest ] && v="$(curl -fsSL $base/latest)"; \
    curl -fsSL -o /usr/local/bin/claude "$base/$v/linux-$ca/claude"; chmod 755 /usr/local/bin/claude; \
    for b in codex codex-code-mode-host; do \
      curl -fsSL "https://github.com/openai/codex/releases/download/$CODEX_VERSION/$b-$arch-unknown-linux-musl.tar.gz" \
        | tar xz -C /usr/local/bin; mv "/usr/local/bin/$b-$arch-unknown-linux-musl" "/usr/local/bin/$b"; \
    done; chmod 755 /usr/local/bin/codex*
COPY sandbox/proxy.py sandbox/react_agent.py sandbox/time_left.sh /sandbox/
# `time_left` on the agent's PATH: the same remaining-time note the hooks inject, on demand.
RUN chmod 755 /sandbox/time_left.sh && printf '#!/bin/sh\nexec /sandbox/time_left.sh --plain\n' > /usr/local/bin/time_left && chmod 755 /usr/local/bin/time_left
# Non-root: claude refuses --dangerously-skip-permissions as root.
RUN useradd -m -u 1000 agent && mkdir -p /work && chown agent /work
USER agent
WORKDIR /work
ENV HOME=/home/agent TERM=dumb \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 DISABLE_TELEMETRY=1
