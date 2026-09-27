"""Web UI for Inspect runs of the investigation task: launch, watch, read the graded report.

    uv run report-eval-harness web      # http://127.0.0.1:8765

Runs are ordinary ``inspect eval`` subprocesses writing to ``logs/``, so the UI and the CLI
see the same runs. Each launch is tagged with eval metadata ``webui_run=<id>``; its launch
record and console output live in ``build/webui/``. Transcripts open in Inspect View, which
this server starts on the next port up (it refuses to be framed, so it opens in a tab).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log

from report_eval_harness import prompts
from report_eval_harness.corpus import PROJECT_ROOT, Corpus, list_corpora
from report_eval_harness.task import FINISH_NOTE, SUBAGENT_NOTE, investigation

STATIC = Path(__file__).parent / "static"
LOG_DIR = PROJECT_ROOT / "logs"
LAUNCH_DIR = PROJECT_ROOT / "build" / "webui"
EDITED_PROMPTS = prompts.PROMPTS_DIR / ".webui"  # gitignored
INSPECT = str(Path(sys.executable).parent / "inspect")
TASK = "report_eval_harness/investigation"
DONE = ("success", "error", "cancelled")

MODELS = [
    "anthropic/claude-sonnet-5",
    "anthropic/claude-opus-5-5",
    "anthropic/claude-fable-5-1",
    "anthropic/claude-haiku-4-5-20251001",
    "mockllm/model",
]
TASK_DEFAULTS = {
    name: p.default
    for name, p in inspect.signature(investigation).parameters.items()
    if p.default is not inspect.Parameter.empty
}

_procs: dict[str, subprocess.Popen] = {}
_view: dict[str, object] = {"url": None, "proc": None}


# -- launching ----------------------------------------------------------------


def _save_prompt(text: str) -> str:
    """Store an edited prompt under prompts/.webui/ and return its name for ``-T prompt``."""
    EDITED_PROMPTS.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(text.encode()).hexdigest()[:12] + ".txt"
    (EDITED_PROMPTS / name).write_text(text)
    return f".webui/{name}"


def _check_prompt(body: dict, text: str) -> None:
    """Render the prompt as the task will, so template mistakes fail here, not in the run."""
    try:
        prompts.render(
            text,
            prompts.values(
                n_records=1,
                budget_min=int(body["time_limit_minutes"]),
                report_min_words=int(body["report_min_words"]),
                report_max_words=int(body["report_max_words"]),
                subagent_note=SUBAGENT_NOTE,
                finish_note=FINISH_NOTE[body["agent"]],
            ),
        )
    except ValueError as ex:
        raise HTTPException(400, f"prompt: {ex}") from ex


def _argv(run_id: str, body: dict) -> list[str]:
    argv = [INSPECT, "eval", TASK, "--model", body["model"], "--log-dir", str(LOG_DIR)]
    argv += ["--display", "plain", "--metadata", f"webui_run={run_id}"]
    argv += ["--epochs", str(int(body.get("epochs") or 1))]
    task_args = {
        "corpus": body["corpus"],
        "agent": body["agent"],
        "prompt": body["prompt"],
        "time_limit_minutes": int(body["time_limit_minutes"]),
        "report_min_words": int(body["report_min_words"]),
        "report_max_words": int(body["report_max_words"]),
    }
    if body["agent"] == "claude_code":
        if body.get("effort"):
            task_args["effort"] = body["effort"]
    else:
        task_args["subagents"] = bool(body.get("subagents"))
    for key, value in task_args.items():
        argv += ["-T", f"{key}={value}"]
    if body["agent"] == "react" and body.get("subagents") and body.get("subagent_model"):
        argv += ["--model-role", f"subagent={body['subagent_model']}"]
    if body.get("score", True):
        if body.get("judge_model"):
            argv += ["--model-role", f"grader={body['judge_model']}"]
    else:
        argv.append("--no-score")
    return argv


def _write_launch(record: dict) -> None:
    (LAUNCH_DIR / f"{record['id']}.json").write_text(json.dumps(record, indent=2))


def start_run(body: dict) -> str:
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    argv = _argv(run_id, body)
    record = {"id": run_id, "argv": argv, "started": time.time(), "returncode": None}
    _write_launch(record)
    console = (LAUNCH_DIR / f"{run_id}.out").open("w")
    # Own process group, so Stop can SIGINT inspect and its docker children together.
    proc = subprocess.Popen(
        argv,
        cwd=PROJECT_ROOT,
        stdout=console,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=os.environ,
    )
    _procs[run_id] = proc

    def wait() -> None:
        record["returncode"] = proc.wait()
        record["finished"] = time.time()
        console.close()
        _write_launch(record)

    threading.Thread(target=wait, daemon=True).start()
    return run_id


def stop_run(run_id: str) -> bool:
    proc = _procs.get(run_id)
    if proc is None or proc.poll() is not None:
        return False
    # SIGINT lets Inspect cancel cleanly: it writes a "cancelled" log and tears down Docker.
    os.killpg(proc.pid, signal.SIGINT)
    return True


# -- reading runs -------------------------------------------------------------


def _log_rows() -> dict[str, tuple[Path, EvalLog]]:
    """Every log in logs/, keyed by webui run id (UI launches) or by file stem (CLI runs)."""
    rows = {}
    for info in list_eval_logs(str(LOG_DIR)):
        path = Path(info.name.removeprefix("file://"))
        try:
            header = read_eval_log(str(path), header_only=True)
        except Exception:  # noqa: BLE001 - a log mid-write can be briefly unreadable
            continue
        key = (header.eval.metadata or {}).get("webui_run") or path.stem
        # A retried run can leave several logs under one id; keep the newest.
        if key not in rows or path.stat().st_mtime > rows[key][0].stat().st_mtime:
            rows[key] = (path, header)
    return rows


def _scores(header: EvalLog) -> dict[str, float]:
    out = {}
    for score in (header.results.scores if header.results else []) or []:
        if "mean" in score.metrics:
            out[score.name] = score.metrics["mean"].value
    return out


def _flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


def _task_args_from_argv(argv: list[str]) -> dict:
    return dict(argv[i + 1].split("=", 1) for i, a in enumerate(argv) if a == "-T")


def _summary(run_id: str, path: Path | None, header: EvalLog | None) -> dict:
    launch_file = LAUNCH_DIR / f"{run_id}.json"
    launch = json.loads(launch_file.read_text()) if launch_file.exists() else None
    proc = _procs.get(run_id)
    alive = proc is not None and proc.poll() is None
    if header is not None:
        status = header.status
        if status == "started":
            status = "running" if alive or launch is None else "interrupted"
        stats = header.stats
        return {
            "id": run_id,
            "log": path.name,
            "status": status,
            "source": "webui" if launch else "cli",
            "task_args": header.eval.task_args,
            "model": header.eval.model,
            "roles": {k: v.model for k, v in (header.eval.model_roles or {}).items()},
            "scores": _scores(header),
            "started": stats.started_at,
            "completed": stats.completed_at or None,
            "tokens": sum(u.total_tokens for u in stats.model_usage.values()),
            "error": header.error.message if header.error else None,
            "view_url": f"{_view['url']}#/logs/{path.name}" if _view["url"] else None,
        }
    # Launched, but no log yet: still starting, or inspect failed before creating one.
    if alive:
        status, error = "starting", None
    else:
        status, error = "failed", "inspect exited before writing a log; see the console"
    return {
        "id": run_id,
        "log": None,
        "status": status,
        "source": "webui",
        "task_args": _task_args_from_argv(launch["argv"]) if launch else {},
        "model": _flag(launch["argv"], "--model") if launch else None,
        "roles": {},
        "scores": {},
        "started": datetime.fromtimestamp(launch["started"], UTC).isoformat() if launch else None,
        "completed": None,
        "tokens": 0,
        "error": error,
        "view_url": None,
    }


def list_runs() -> list[dict]:
    rows = _log_rows()
    ids = set(rows) | {p.stem for p in LAUNCH_DIR.glob("*.json")}
    runs = [_summary(i, *rows.get(i, (None, None))) for i in ids]
    return sorted(runs, key=lambda r: r["started"] or "", reverse=True)


def run_detail(run_id: str) -> dict:
    rows = _log_rows()
    if run_id not in rows and not (LAUNCH_DIR / f"{run_id}.json").exists():
        raise HTTPException(404)
    path, header = rows.get(run_id, (None, None))
    out = _summary(run_id, path, header)
    out["samples"] = []
    if header is not None and header.status in DONE:
        for sample in read_eval_log(str(path)).samples or []:
            score = next(iter((sample.scores or {}).values()), None)
            meta = (score.metadata or {}) if score else {}
            out["samples"].append(
                {
                    "epoch": sample.epoch,
                    "value": score.value if score else None,
                    "report": score.answer if score else None,
                    "grades": meta.get("grades"),
                    "report_words": meta.get("report_words"),
                    "error": sample.error.message if sample.error else None,
                    "prompt": sample.input if isinstance(sample.input, str) else None,
                }
            )
    console = LAUNCH_DIR / f"{run_id}.out"
    out["console"] = console.read_text()[-20000:] if console.exists() else None
    return out


# -- app ----------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    view = _view.get("proc")
    if isinstance(view, subprocess.Popen):
        view.terminate()


app = FastAPI(title="report-eval-harness", lifespan=lifespan)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/options")
def options() -> dict:
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        auth = "subscription token (ANTHROPIC_AUTH_TOKEN)"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        auth = "API key (ANTHROPIC_API_KEY)"
    else:
        auth = None
    return {
        "corpora": [{"name": c, "records": len(Corpus(c).records())} for c in list_corpora()],
        "prompts": prompts.list_prompts(),
        "models": MODELS,
        "defaults": {
            **TASK_DEFAULTS,
            "model": MODELS[0],
            "judge_model": "anthropic/claude-fable-5-1",
            "subagent_model": "",
            "epochs": 1,
            "score": True,
        },
        "auth": auth,
        "view_url": _view["url"],
    }


@app.get("/api/prompts/{name}")
def prompt(name: str) -> dict:
    if name not in prompts.list_prompts():
        raise HTTPException(404)
    return {"name": name, "text": prompts.load(name)}


@app.post("/api/runs")
def create_run(body: dict) -> dict:
    body = {**options()["defaults"], **body}
    if body["corpus"] not in list_corpora():
        raise HTTPException(400, f"unknown corpus {body['corpus']!r}")
    if body["agent"] not in FINISH_NOTE:
        raise HTTPException(400, f"unknown agent {body['agent']!r}")
    if body.get("prompt_text"):
        _check_prompt(body, body["prompt_text"])
        body["prompt"] = _save_prompt(body["prompt_text"])
    elif body["prompt"] not in prompts.list_prompts():
        raise HTTPException(400, f"unknown prompt {body['prompt']!r}")
    return {"id": start_run(body)}


@app.get("/api/runs")
def runs() -> list[dict]:
    return list_runs()


@app.get("/api/runs/{run_id}")
def run(run_id: str) -> dict:
    return run_detail(run_id)


@app.post("/api/runs/{run_id}/stop")
def stop(run_id: str) -> dict:
    return {"stopped": stop_run(run_id)}


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    LOG_DIR.mkdir(exist_ok=True)
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    view_port = port + 1
    _view["proc"] = subprocess.Popen(
        [INSPECT, "view", "--log-dir", str(LOG_DIR), "--host", "127.0.0.1"]
        + ["--port", str(view_port)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _view["url"] = f"http://127.0.0.1:{view_port}/"
    uvicorn.run(app, host=host, port=port)
