# Two images from one file (compose picks the stage with `target:`). Runtime hardening
# (read-only root, tmpfs, limits, no network) is in report_eval_harness/sandbox.py.

# tools: where the investigation happens. Stdlib Python, jq, ripgrep, sqlite3 (no
# pandas/numpy, by design), the corpus at /work/data. Every agent's shell runs here.
FROM python:3.12-slim AS tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq ripgrep sqlite3 file less \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 agent \
    && mkdir -p /work/data \
    && chown agent:agent /work \
    && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
    && rm -rf /var/cache/* /var/log/*
USER agent
WORKDIR /work
CMD ["tail", "-f", "/dev/null"]

# claude: the Claude Code CLI and inspect_swe's model bridge, and nothing else: no data
# and no shell tools for the model. Its tools are Inspect's bash/text_editor, bridged over
# MCP and executed in the tools container, so nothing the model runs can reach the bridge.
# curl stays: inspect_swe uses it to check the MCP endpoints are up before starting.
FROM python:3.12-slim AS claude
ARG CLAUDE_CODE_VERSION=stable
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://claude.ai/install.sh | bash -s ${CLAUDE_CODE_VERSION} \
    && cp -L /root/.local/bin/claude /usr/local/bin/claude \
    && rm -rf /root/.local /root/.claude* /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 agent \
    && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
    && rm -rf /var/cache/* /var/log/*
USER agent
WORKDIR /home/agent
CMD ["tail", "-f", "/dev/null"]
