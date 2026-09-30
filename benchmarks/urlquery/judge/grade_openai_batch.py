#!/usr/bin/env python3
"""Grade the latest URLQuery reports with Astra through OpenAI's Batch API.

Prepare once, then run ``--watch`` (or repeatedly run ``--step``) to submit and
collect small batches. The state and all raw responses live in the primary
checkout's gitignored reports/urlquery/graded/ tree, so interrupted work resumes.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from messageboard_audit_bench.benchmarks import primary_root  # noqa: E402
from messageboard_audit_bench.grading import findings as fj  # noqa: E402

MODEL = "gpt-6-astra"
EFFORT = "high"
CHUNK_REPORTS = 3
BASE = fj.output_root() / "judge_gpt_6_astra_high_openai_batch"


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def key() -> str:
    for line in (primary_root() / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.partition("=")[2]
    raise RuntimeError("OPENAI_API_KEY missing from primary .env")


class API:
    """Minimal Batch REST calls via the host's working HTTPS proxy."""

    def __init__(self):
        self.authorization = "Bearer " + key()

    def request(self, method: str, path: str, body: bytes | None = None,
                content_type: str | None = None, idempotency_key: str | None = None) -> bytes:
        headers = {"Authorization": self.authorization}
        if content_type:
            headers["Content-Type"] = content_type
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request("https://api.openai.com/v1" + path,
                                         data=body, headers=headers, method=method)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if method != "GET" or exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise
            except urllib.error.URLError:
                if method != "GET" or attempt == 4:
                    raise
            time.sleep(min(2 ** attempt, 16))
        raise RuntimeError("unreachable retry exit")

    def upload(self, path: Path) -> dict:
        boundary = "batch-" + secrets.token_hex(16)
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
                "Content-Type: application/jsonl\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return json.loads(self.request("POST", "/files", body, f"multipart/form-data; boundary={boundary}"))

    def create(self, file_id: str, number: int) -> dict:
        body = {"input_file_id": file_id, "endpoint": "/v1/chat/completions",
                "completion_window": "24h", "metadata": {"benchmark": "urlquery",
                                                         "grading": "reviewed", "chunk": str(number)}}
        return json.loads(self.request("POST", "/batches", json.dumps(body).encode(),
                                       "application/json", f"urlquery-{file_id}-{number}"))

    def retrieve(self, batch_id: str) -> dict:
        return json.loads(self.request("GET", f"/batches/{batch_id}"))

    def content(self, file_id: str) -> bytes:
        return self.request("GET", f"/files/{file_id}/content")


def latest_reports() -> list[Path]:
    """One valid report per active model, harness and time limit."""
    chosen: dict[tuple[str, str, int], Path] = {}
    for path in sorted((primary_root() / "runs/urlquery").glob("*/meta.json")):
        meta = json.loads(path.read_text())
        if (meta.get("benchmark_id") != "urlquery"
                or meta.get("prompt") != "urlquery-agents-v6"
                or meta.get("model") == "claude-sonnet-5"
                or meta.get("termination") not in ("normal", "active_time_limit")
                or meta.get("report_length_compliant") is not True
                or not (path.parent / "report.md").is_file()):
            continue
        identity = (meta["agent"], meta["model"], meta["budget_min"])
        chosen[identity] = path.parent
    runs = sorted(chosen.values())
    if len(runs) != 26:
        raise RuntimeError(f"expected 26 active model/time pairs, found {len(runs)}")
    return runs


def prepare(runs_file: Path | None = None) -> Path:
    if runs_file is None:
        runs = latest_reports()
    else:
        names = json.loads(runs_file.read_text())
        if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names):
            raise ValueError("runs file must be a nonempty JSON list of run directory names")
        if len(names) != len(set(names)) or any(Path(name).name != name for name in names):
            raise ValueError("runs file contains duplicate or invalid run directory names")
        runs = [primary_root() / "runs" / "urlquery" / name for name in names]
        if any(not (run / "report.md").is_file() or not (run / "meta.json").is_file() for run in runs):
            raise ValueError("runs file names a missing report or metadata file")
        for run in runs:
            meta = json.loads((run / "meta.json").read_text())
            if (meta.get("benchmark_id") != "urlquery" or meta.get("prompt") != "urlquery-agents-v6"
                    or meta.get("data_manifest_status") != "verified"
                    or meta.get("termination") not in ("normal", "active_time_limit")
                    or meta.get("minimum_runtime_reached") is not True
                    or meta.get("report_length_compliant") is not True
                    or meta.get("model_fallback")
                    or (meta.get("model_served") and meta["model_served"] != meta.get("model"))):
                raise ValueError(f"ineligible run in runs file: {run.name}")
    article = fj.article_text("full")
    heads = fj.headlines()
    stamp = fj.stamp(MODEL, EFFORT, article)
    stamp["transport"] = "openai_batch_chat_completions"
    stamp["model_id"] = MODEL
    name = datetime.now(UTC).strftime("batch_%Y%m%dT%H%M%SZ")
    folder = BASE / name
    if folder.exists():
        raise RuntimeError(f"batch folder already exists: {folder}")
    folder.mkdir(parents=True)
    manifest = {"schema": 1, "model": MODEL, "effort": EFFORT,
                "article_context": "full", "stamp": stamp, "headlines": heads,
                "runs": [], "chunks": []}
    for index, run in enumerate(runs):
        report = (run / "report.md").read_text()
        meta = json.loads((run / "meta.json").read_text())
        manifest["runs"].append({"index": index, "path": str(run), "name": run.name,
                                 "report_sha256": fj.sha(report), "agent": meta["agent"],
                                 "model": meta["model"], "budget_min": meta["budget_min"],
                                 "termination": meta["termination"]})
    for start in range(0, len(runs), CHUNK_REPORTS):
        number = len(manifest["chunks"])
        filename = f"requests_{number:02d}.jsonl"
        with (folder / filename).open("w") as output:
            for index in range(start, min(start + CHUNK_REPORTS, len(runs))):
                report = (runs[index] / "report.md").read_text()
                for head in heads:
                    request = {"custom_id": f"{index:03d}-{head}", "method": "POST",
                               "url": "/v1/chat/completions",
                               "body": {"model": MODEL, "reasoning_effort": EFFORT,
                                        "response_format": {"type": "json_object"},
                                        "max_completion_tokens": 24000,
                                        "messages": [{"role": "system", "content": fj.SYSTEM},
                                                     {"role": "user", "content": fj.render(head, article, report)}]}}
                    output.write(json.dumps(request, ensure_ascii=False) + "\n")
        manifest["chunks"].append({"file": filename, "sha256": fj.sha((folder / filename).read_bytes()),
                                   "requests": (min(start + CHUNK_REPORTS, len(runs)) - start) * len(heads),
                                   "status": "prepared", "batch_id": None})
    save(folder / "state.json", manifest)
    return folder


def parse_response(row: dict, head: str) -> dict:
    response = row.get("response") or {}
    if response.get("status_code") != 200:
        return {"status": "api_error", "error": row.get("error") or response.get("body")}
    body = response.get("body") or {}
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    raw = message.get("content") or ""
    usage = body.get("usage") or {}
    if message.get("refusal") or choice.get("finish_reason") == "content_filter":
        return {"status": "refused", "raw": [raw], "usage": [usage],
                "refusal": message.get("refusal") or choice.get("finish_reason")}
    if choice.get("finish_reason") == "length":
        return {"status": "truncated", "raw": [raw], "usage": [usage]}
    data = fj.extract_json(raw)
    if data is None:
        return {"status": "unparseable", "raw": [raw], "usage": [usage]}
    try:
        result, notes = fj.validate(data, head, fj.sub_ids(head))
    except (TypeError, ValueError, KeyError) as exc:
        return {"status": "invalid", "error": str(exc), "raw": [raw], "usage": [usage]}
    return {"status": "ok", **result, "validation": notes, "raw": [raw], "usage": [usage]}


def collect(folder: Path, state: dict, number: int, batch: dict, api: API) -> None:
    chunk = state["chunks"][number]
    rows = {}
    if batch.get("output_file_id"):
        content = api.content(batch["output_file_id"]).decode()
        (folder / f"output_{number:02d}.jsonl").write_text(content)
        rows.update({row["custom_id"]: row for row in map(json.loads, content.splitlines())})
    if batch.get("error_file_id"):
        content = api.content(batch["error_file_id"]).decode()
        (folder / f"errors_{number:02d}.jsonl").write_text(content)
        rows.update({row["custom_id"]: row for row in map(json.loads, content.splitlines())})
    expected = [json.loads(line)["custom_id"] for line in (folder / chunk["file"]).read_text().splitlines()]
    for custom_id in expected:
        index_text, head = custom_id.split("-", 1)
        run = state["runs"][int(index_text)]
        report = (Path(run["path"]) / "report.md").read_text()
        if fj.sha(report) != run["report_sha256"]:
            raise RuntimeError(f"report changed after preparation: {run['name']}")
        path = BASE / f"{run['name']}.json"
        grade = json.loads(path.read_text()) if path.exists() else {
            **fj.run_meta(Path(run["path"])), **state["stamp"],
            "article_context": "full", "report_sha256": run["report_sha256"], "findings": {}}
        if any(grade.get(k) != v for k, v in state["stamp"].items()) or grade.get("report_sha256") != run["report_sha256"]:
            raise RuntimeError(f"grade provenance conflict: {path}")
        grade["findings"][head] = (parse_response(rows[custom_id], head) if custom_id in rows else
                                   {"status": "missing", "error": f"batch {batch['status']}: no response"})
        save(path, fj.summarize(grade, state["headlines"], report))
    chunk.update(status="collected", output_file_id=batch.get("output_file_id"),
                 error_file_id=batch.get("error_file_id"), batch_status=batch["status"])
    save(folder / "state.json", state)


def step(folder: Path) -> str:
    state_path = folder / "state.json"
    state = json.loads(state_path.read_text())
    pending = [(i, c) for i, c in enumerate(state["chunks"]) if c["status"] != "collected"]
    if not pending:
        return "complete"
    # Submit every prepared chunk before polling an earlier in-progress batch.
    # The API processes independent input files concurrently.
    number, chunk = next(((i, c) for i, c in pending if not c["batch_id"]), pending[0])
    api = API()
    if not chunk["batch_id"]:
        if fj.sha((folder / chunk["file"]).read_bytes()) != chunk["sha256"]:
            raise RuntimeError(f"batch input changed: {chunk['file']}")
        if not chunk.get("input_file_id"):
            uploaded = api.upload(folder / chunk["file"])
            chunk["input_file_id"] = uploaded["id"]
            save(state_path, state)
        batch = api.create(chunk["input_file_id"], number)
        chunk.update(status=batch["status"], batch_id=batch["id"])
        save(state_path, state)
        return f"submitted {number + 1}/{len(state['chunks'])}: {batch['id']} ({batch['status']})"
    batch = api.retrieve(chunk["batch_id"])
    chunk["status"] = batch["status"]
    save(state_path, state)
    if batch["status"] in ("completed", "expired", "cancelled"):
        collect(folder, state, number, batch, api)
        return f"collected {number + 1}/{len(state['chunks'])}: {batch['status']}"
    if batch["status"] == "failed":
        save(folder / f"failed_{number:02d}.json", batch)
        raise RuntimeError(f"batch validation failed: {batch['id']}; see failed_{number:02d}.json")
    return f"waiting {number + 1}/{len(state['chunks'])}: {batch['id']} ({batch['status']})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--runs-file", type=Path, help="JSON list of specific run directory names to prepare")
    parser.add_argument("--step", type=Path)
    parser.add_argument("--watch", type=Path)
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if args.prepare:
        folder = prepare(args.runs_file)
        state = json.loads((folder / "state.json").read_text())
        print(f"{folder}: {len(state['runs'])} reports, {sum(c['requests'] for c in state['chunks'])} requests, {len(state['chunks'])} batches")
    elif args.step:
        print(step(args.step), flush=True)
    elif args.watch:
        with (args.watch / "watch.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            while True:
                try:
                    result = step(args.watch)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                    result = f"temporary API error: {type(exc).__name__}: {exc}"
                print(datetime.now(UTC).isoformat(), result, flush=True)
                if result == "complete":
                    break
                time.sleep(args.interval)
    else:
        parser.error("choose --prepare, --step FOLDER, or --watch FOLDER")


if __name__ == "__main__":
    main()
