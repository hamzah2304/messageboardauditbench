"""Exercise normal subscription CLI hooks against a local dummy provider.

This file is copied into a fresh Docker container for manual integration
validation. It deliberately uses the ordinary Claude builtin tools, rather
than the abandoned MCP-only transport, and sends no request beyond loopback.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORK = Path("/work")
RESULT = WORK / "subscription-cli-probe.json"


def sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


class MockAnthropic(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["content-length"])))
        type(self).calls.append(request)
        turn = len(type(self).calls)
        if turn == 1:
            content = [
                {
                    "type": "tool_use",
                    "id": "parallel-success",
                    "name": "Bash",
                    "input": {"command": "sleep 0.2; printf success"},
                },
                {
                    "type": "tool_use",
                    "id": "parallel-failure",
                    "name": "Bash",
                    "input": {"command": "sleep 0.2; printf failure >&2; exit 7"},
                },
            ]
            stop_reason = "tool_use"
        else:
            content = [{"type": "text", "text": "complete"}]
            stop_reason = "end_turn"
        events = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": f"msg-{turn}",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-sonnet-5",
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 10, "output_tokens": 0},
                    },
                },
            )
        ]
        for index, block in enumerate(content):
            input_data = block.pop("input", None) if block["type"] == "tool_use" else None
            events += [
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": block,
                    },
                ),
            ]
            if input_data is not None:
                events.append(
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(input_data),
                            },
                        },
                    )
                )
            events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
        events += [
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop_reason},
                    "usage": {"output_tokens": 4},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
        payload = b"".join(sse(event, body) for event, body in events)
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockAnthropic)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    home = Path("/tmp/home")
    config = home / ".claude"
    config.mkdir(parents=True)
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /sandbox/tool_telemetry.py --event PreToolUse",
                        }
                    ]
                }
            ],
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /sandbox/tool_telemetry.py --event PostToolUse",
                        }
                    ]
                }
            ],
            "PostToolUseFailure": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /sandbox/tool_telemetry.py --event PostToolUseFailure",
                        }
                    ]
                }
            ],
        }
    }
    (config / "settings.json").write_text(json.dumps(settings))
    env = {
        "HOME": str(home),
        "PATH": os.environ["PATH"],
        "ANTHROPIC_API_KEY": "dummy",
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    try:
        completed = subprocess.run(
            [
                "claude",
                "-p",
                "use Bash twice and then finish",
                "--model",
                "claude-sonnet-5",
                "--dangerously-skip-permissions",
                "--no-chrome",
                "--no-session-persistence",
                "--setting-sources",
                "user",
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            cwd=WORK,
            env=env,
            text=True,
            capture_output=True,
            timeout=45,
        )
        hook_path = Path("/tmp/mbab-tool-events.jsonl")
        RESULT.write_text(
            json.dumps(
                {
                    "returncode": completed.returncode,
                    "provider_calls": MockAnthropic.calls,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "hook_rows": [
                        json.loads(line) for line in hook_path.read_text().splitlines()
                    ]
                    if hook_path.exists()
                    else [],
                }
            )
        )
    finally:
        server.shutdown()
        thread.join()


if __name__ == "__main__":
    main()
