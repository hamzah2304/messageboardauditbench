"""Inspect solver that runs a coding-agent CLI (Claude Code or Codex) in the
lightweight sandbox, or replays a run directory that already exists.

Live mode shells out to sandbox/run_trial.sh, so the isolation is exactly the
same as a manual baseline run. When it finishes, the CLI's event stream is
converted into Inspect chat messages, the report becomes the sample's
completion, and run metadata (tokens, wall time, exit code, proxy denials)
lands in the sample metadata where `inspect view` shows it.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path

from inspect_ai.model import ModelOutput, ModelUsage
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.log import transcript

from .transcripts import parse

ROOT = Path(__file__).resolve().parent.parent


def _proxy_denials(started_iso: str, run_dir: Path) -> list[str]:
    """Hosts the agent tried and was refused, from runs/proxy.log, during this run."""
    log = ROOT / "runs" / "proxy.log"
    if not log.exists():
        return []
    # started like 20260905T094927Z -> 2026-09-05T09:49:27Z
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", started_iso)
    lo = f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}Z" if m else ""
    meta = json.loads((run_dir / "meta.json").read_text())
    out: list[str] = []
    for line in log.read_text().splitlines():
        ts, _, rest = line.partition(" ")
        if ts >= lo and rest.startswith("deny "):
            out.append(rest)
    return sorted(set(out))


def _ingest(state: TaskState, agent: str, run_dir: Path) -> TaskState:
    meta = json.loads((run_dir / "meta.json").read_text())
    parsed = parse(agent, run_dir / "transcript.jsonl")
    report_path = run_dir / "report.md"
    report = report_path.read_text() if report_path.exists() else ""

    # The conversation: the task prompt, then everything the agent did.
    state.messages = [state.messages[0], *parsed.messages] if state.messages else parsed.messages
    state.output = ModelOutput(
        model=meta.get("model", agent),
        completion=report if report else "(no report.md was written)",
        usage=ModelUsage(
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
            total_tokens=parsed.input_tokens + parsed.output_tokens,
            input_tokens_cache_read=parsed.cache_read_tokens or None,
            input_tokens_cache_write=parsed.cache_write_tokens or None,
            reasoning_tokens=parsed.reasoning_tokens or None,
            total_cost=parsed.cost_usd,
        ),
        time=(meta.get("wall_seconds") or 0) or None,
    )
    stderr = (run_dir / "stderr.log").read_text()[-4000:] if (run_dir / "stderr.log").exists() else ""
    state.metadata.update(
        {
            "run_dir": str(run_dir),
            "agent": agent,
            "agent_model": meta.get("model"),
            "effort": meta.get("effort"),
            "cli_version": meta.get("cli_version"),
            "exit_code": meta.get("exit_code"),
            "wall_seconds": meta.get("wall_seconds"),
            "timeout": meta.get("timeout"),
            "report_exists": bool(report),
            "report_chars": len(report),
            "rev_ids_cited": len(set(re.findall(r"[a-z]+~[A-Za-z0-9_\-]+@\d+", report))),
            "turns": parsed.turns,
            "tool_calls": parsed.tool_calls,
            "proxy_denials": _proxy_denials(meta.get("started", ""), run_dir),
            "stderr_tail": stderr,
            **{f"cli_{k}": v for k, v in parsed.extra.items()},
        }
    )
    transcript().info(
        {k: state.metadata[k] for k in ("run_dir", "exit_code", "wall_seconds", "turns", "tool_calls", "rev_ids_cited", "proxy_denials")},
        source="cli_agent",
    )
    state.completed = True
    return state


@solver
def cli_agent(
    agent: str = "claude",
    agent_model: str = "claude-opus-5",
    effort: str = "medium",
    timeout: str = "25m",
    replay_dir: str | None = None,
) -> Solver:
    """Run (or replay) one coding-agent trial.

    agent:       "claude" or "codex"
    agent_model: model id passed to the CLI
    effort:      reasoning effort passed to the CLI
    timeout:     hard wall-clock cap (GNU timeout syntax)
    replay_dir:  an existing runs/<dir>; skip launching and just ingest it
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        if replay_dir:
            return _ingest(state, agent, Path(replay_dir).resolve())

        seed = state.epoch
        script = ROOT / "sandbox" / "run_trial.sh"
        if not shutil.which("sudo"):
            raise RuntimeError("sandbox needs sudo; see sandbox/README.md")
        proc = await asyncio.create_subprocess_exec(
            str(script), agent, agent_model, str(seed),
            cwd=str(ROOT),
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(Path.home()),
                 "EFFORT": effort, "TIMEOUT": timeout},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        text = out.decode(errors="replace")
        m = re.search(r"^run: (.+)$", text, re.M)
        if not m:
            raise RuntimeError(f"run_trial.sh did not report a run dir:\n{text[-2000:]}")
        return _ingest(state, agent, Path(m[1].strip()))

    return solve
