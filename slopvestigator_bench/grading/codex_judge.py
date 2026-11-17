"""A judge call through the Codex CLI on the ChatGPT subscription, instead of a paid API.

`codex exec` is a full agent session. Left as it is, it adds Codex's own system prompt, the
user's global AGENTS.md, a skills list, multi-agent instructions, the environment and a set of
tools, so the judge would not see what the API judge sees. Each call here strips that down:

* a separate CODEX_HOME that holds only a link to the login (~/.codex/auth.json), so no
  AGENTS.md, skills, plugins, hooks or user config are loaded;
* `model_instructions_file` replaces Codex's system prompt with the grader's (`findings.SYSTEM`);
* the include_* switches, `agents.enabled=false` and every enabled feature disabled, so no
  developer messages are added and almost no tools are offered;
* an empty working directory, a read-only sandbox, and a JSON schema for the answer;
* `--ephemeral`, so Codex saves no session log or conversation history. Saved, each call's
  conversation (the whole report included) took about 350 KB, about 3 GB for a full grading.

What remains is about 2,700 tokens of tool definitions (a shell, apply_patch, MCP listing,
user-input requests). The prompt holds everything the judge needs; a call that uses a tool
anyway records how many it used (`usage["tool_calls"]`).

The subscription has a weekly usage window. The window's use is read from Codex's app server
(`account/rateLimits/read`, no model call) before the batch starts and at most every
`LIMITS_EVERY` seconds after a call; `limit_reason` says when it passes `stop_at` percent or the
limit is reached, and the batch grader then stops, so it never runs into paid Codex credits.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

USAGE_LIMIT_SIGNS = ("usage limit", "rate_limit_reached", "rate limit reached")
LIMITS_EVERY = 30  # seconds between reads of the usage window
NOT_TOOLS = {"agent_message", "reasoning", "error"}  # "error": notices such as "code mode is disabled"

ANSWER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["finding_id", "sub_findings", "contradicted", "score", "quote", "reason"],
    "properties": {
        "finding_id": {"type": "string"},
        "sub_findings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "score", "contradicted", "quote", "reason"],
            "properties": {"id": {"type": "string"}, "score": {"type": "number"},
                           "contradicted": {"type": "boolean"}, "quote": {"type": "string"},
                           "reason": {"type": "string"}}}},
        "contradicted": {"type": "boolean"},
        "score": {"type": "number"},
        "quote": {"type": "string"},
        "reason": {"type": "string"},
    },
}


class UsageLimit(RuntimeError):
    """The subscription's usage limit was reached; stop rather than retry."""


def enabled_features(exe: str) -> list[str]:
    out = subprocess.run([exe, "features", "list"], capture_output=True, text=True, check=True).stdout
    return [cols[0] for cols in (line.split() for line in out.splitlines())
            if len(cols) >= 3 and cols[-1] == "true" and cols[1] != "removed"]


class CodexJudge:
    def __init__(self, model: str, effort: str, system: str, home: Path, stop_at: float = 90.0):
        self.exe = shutil.which("codex")
        if not self.exe:
            raise SystemExit("codex CLI not found")
        self.model, self.effort, self.stop_at = model, effort, stop_at
        self.home = home
        self.home.mkdir(parents=True, exist_ok=True)
        self.login = Path.home() / ".codex" / "auth.json"
        self.lock = threading.Lock()
        self._link_login()
        (self.home / "system.txt").write_text(system)
        (self.home / "schema.json").write_text(json.dumps(ANSWER_SCHEMA))
        self.disable = [x for f in enabled_features(self.exe) for x in ("--disable", f)]
        self.rate_limits: dict | None = None
        self.limits_read_at = 0.0

    def _link_login(self) -> None:
        """Keep the judge home's auth.json a link to the real login.

        If Codex refreshed the token by replacing the link with a file, that file is the newer
        login: copy it back over the real one before relinking, so the main login stays valid.
        """
        link = self.home / "auth.json"
        with self.lock:
            if link.exists() and not link.is_symlink():
                shutil.copy2(link, self.login)
                link.unlink()
            if not link.is_symlink():
                link.symlink_to(self.login)

    def argv(self) -> list[str]:
        return [
            self.exe, "exec", "-m", self.model,
            "-c", f"model_reasoning_effort={self.effort}",
            "-c", f"model_instructions_file={self.home / 'system.txt'}",
            "-c", 'web_search="disabled"',
            "-c", "include_environment_context=false", "-c", "include_permissions_instructions=false",
            "-c", "include_apps_instructions=false", "-c", "include_collaboration_mode_instructions=false",
            "-c", "skills.include_instructions=false", "-c", "agents.enabled=false",
            *self.disable,
            "--ephemeral", "--ignore-rules", "--skip-git-repo-check", "-s", "read-only",
            "--output-schema", str(self.home / "schema.json"), "--json", "-",
        ]

    def call(self, prompt: str) -> tuple[str, dict, str | None, str | None]:
        """One judge call: (answer text, usage, "truncated"/None, None)."""
        with tempfile.TemporaryDirectory(prefix="codex-judge-") as cwd:
            proc = subprocess.run(self.argv() + ["-C", cwd], input=prompt, capture_output=True, text=True,
                                  timeout=1800, cwd=cwd, env={**os.environ, "CODEX_HOME": str(self.home)})
        self._link_login()
        events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
        errors = " ".join(json.dumps(e) for e in events if e.get("type") in ("error", "turn.failed"))
        if any(sign in (errors + proc.stderr).lower() for sign in USAGE_LIMIT_SIGNS):
            raise UsageLimit((errors or proc.stderr)[-500:])
        self.refresh_limits()
        done = next((e for e in events if e.get("type") == "turn.completed"), None)
        if proc.returncode or done is None:
            raise RuntimeError(f"codex exec exit {proc.returncode}: {(errors or proc.stderr)[-500:]}")
        items = [e["item"] for e in events if e.get("type") == "item.completed"]
        text = next((i.get("text", "") for i in reversed(items) if i.get("type") == "agent_message"), "")
        usage = {**done.get("usage", {}), "tool_calls": sum(i.get("type") not in NOT_TOOLS for i in items)}
        return text, usage, None, None

    def refresh_limits(self, force: bool = False) -> None:
        """Read the subscription window's use from Codex's app server, at most every LIMITS_EVERY s."""
        with self.lock:
            if not force and time.time() - self.limits_read_at < LIMITS_EVERY:
                return
            self.limits_read_at = time.time()
        requests = [{"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "judge", "version": "0"}}},
                    {"method": "initialized"}, {"id": 2, "method": "account/rateLimits/read"}]
        proc = subprocess.Popen([self.exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, env={**os.environ, "CODEX_HOME": str(self.home)})
        try:
            proc.stdin.write("".join(json.dumps({"jsonrpc": "2.0", **r}) + "\n" for r in requests))
            proc.stdin.flush()
            for line in proc.stdout:
                reply = json.loads(line) if line.startswith("{") else {}
                if reply.get("id") == 2:
                    if "result" in reply:
                        with self.lock:
                            self.rate_limits = reply["result"]
                    break
        finally:
            proc.kill()
            proc.wait()

    def limit_reason(self) -> str | None:
        if self.rate_limits is None:
            return "could not read the subscription usage window"
        limits = self.rate_limits.get("rateLimits") or {}
        if self.rate_limits.get("ordinaryUsageAllowed") is False or limits.get("spendControlReached"):
            return "ordinary subscription usage is not allowed"
        if limits.get("rateLimitReachedType"):
            return f"usage limit reached ({limits['rateLimitReachedType']})"
        used = (limits.get("primary") or {}).get("usedPercent")
        if used is not None and used >= self.stop_at:
            return f"subscription window {used:.0f}% used (stop at {self.stop_at:.0f}%)"
        return None

    def window(self) -> str:
        primary = ((self.rate_limits or {}).get("rateLimits") or {}).get("primary") or {}
        return f"window {primary.get('usedPercent', '?')}%"
