#!/usr/bin/env python3
"""Prepare a frozen AI Village grading plan, then run it with resumable API jobs."""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from messageboard_audit_bench.grading.aivillage import (  # noqa: F401 — the tests reach them through this module
    EFFORT,
    MODEL,
    digest,
    group_findings,
    instructions,
    max_output_tokens,
    normalize_findings,
    period,
    request_input,
    schema,
    source_excerpt,
    validate,
)

ACCOUNT_BLOCK_CODES = {"credit_balance_exhausted", "insufficient_quota", "billing_hard_limit_reached"}


class AccountBlocked(RuntimeError):
    """A billing failure that must stop all queued API work."""



def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    tmp.replace(path)


def read(path):
    return json.loads(path.read_text())


def prepare(args):
    frozen_findings = read(args.findings)
    findings, excluded = normalize_findings(frozen_findings)
    if args.expected_findings is not None and len(findings) != args.expected_findings:
        raise ValueError(f"Expected {args.expected_findings} findings, found {len(findings)}; input was not launched")
    if args.reports.suffix == ".md":
        manifest_text = args.reports.read_text()
        section = manifest_text.split("## Grade these", 1)[1].split("## Ignore these", 1)[0]
        folders = re.findall(r"^- `([^`]+)`", section, re.M)
        expected_count = re.search(r"\((\d+) runs\)", section)
        if not folders or (expected_count and len(folders) != int(expected_count[1])):
            raise ValueError("Manifest grade-list count mismatch")
        reports = [{"id": rid, "path": str((args.runs_root / rid / "report.md").resolve())} for rid in folders]
    else:
        reports_raw = read(args.reports)
        reports = reports_raw if isinstance(reports_raw, list) else reports_raw["reports"]
    goals = [json.loads(line) for line in args.goals.read_text().splitlines()] if args.goals else []
    overrides = read(args.goal_map) if args.goal_map else {}
    groups = group_findings(findings, goals, overrides, args.group_size, args.max_subfindings)
    rubric = args.rubric.read_text()
    jobs, report_snapshots = [], []
    seen = set()
    for report in reports:
        r = {"path": report} if isinstance(report, str) else dict(report)
        path = Path(r["path"])
        if not path.is_absolute():
            path = args.reports.resolve().parent / path
        text = path.read_text()
        rid = r.get("id", path.parent.name)
        if rid in seen:
            raise ValueError("Duplicate report ID: " + rid)
        seen.add(rid)
        if "reasoning_available" not in r:
            meta = path.parent / "meta.json"
            variant = read(meta).get("data_variant", "") if meta.exists() else ""
            if "noreasoning" in variant:
                r["reasoning_available"] = False
            elif "reasoning" in variant:
                r["reasoning_available"] = True
            else:
                raise ValueError("Specify reasoning_available for report " + rid)
        if not isinstance(r["reasoning_available"], bool):
            raise ValueError("reasoning_available must be boolean")
        report_snapshots.append({"id": rid, "path": str(path.resolve()), "text": text, "sha256": digest(text), "reasoning_available": r["reasoning_available"]})
        for group in groups:
            req = {"model": MODEL, "reasoning": {"effort": EFFORT},
                   "instructions": instructions(rubric, r["reasoning_available"]),
                   "input": request_input(rid, group, text),
                   "text": {"format": {"type": "json_schema", "name": "finding_scores", "strict": True, "schema": schema()}},
                   "max_output_tokens": max_output_tokens(group),
                   "store": False}
            jobs.append({"id": digest(req), "report_id": rid, "goal_period": group["goal_period"], "findings": group["findings"], "report": text, "request": req})
    plan = {"model": MODEL, "effort": EFFORT, "concurrency": args.concurrency, "findings_path": str(args.findings.resolve()),
            "findings_sha256": digest(frozen_findings), "rubric_sha256": digest(rubric), "reports_manifest_sha256": digest(args.reports.read_text()), "excluded": excluded,
            "findings": findings, "reports": report_snapshots, "jobs": jobs, "group_size": args.group_size, "max_subfindings": args.max_subfindings}
    plan_id = digest(plan)
    dest = args.output / "plans" / plan_id
    save(dest / "plan.json", plan)
    save(dest / "findings-snapshot.json", frozen_findings)
    (dest / "rubric-snapshot.txt").write_text(rubric)
    save(args.output / "latest-plan.json", {"plan": str((dest / "plan.json").resolve())})
    print(json.dumps({"plan": str(dest / "plan.json"), "approved_findings": len(findings), "excluded": len(excluded), "reports": len(reports), "groups_per_report": len(groups), "requests": len(jobs), "concurrency": args.concurrency, "effort": EFFORT,
                      "minutes_at_20s": round(len(jobs) * 20 / args.concurrency / 60, 1), "minutes_at_30s": round(len(jobs) * 30 / args.concurrency / 60, 1)}), flush=True)
    return dest / "plan.json"


def retry_delay(exc, attempt):
    headers = getattr(getattr(exc, "response", None), "headers", {})
    value = headers.get("retry-after")
    if value:
        try:
            return max(0, float(value)) + random.uniform(.1, 1)
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()) + .5
            except (ValueError, TypeError):
                pass
    return min(60, 2 ** attempt) + random.uniform(.1, 1)


class Gate:
    def __init__(self, rpm=0, tpm=0):
        self.lock = threading.Lock()
        self.next_start = 0.0
        self.cooldown = 0.0
        self.rpm, self.tpm = rpm, tpm
        self.blocked = None

    def abort(self, code):
        with self.lock:
            self.blocked = code

    def defer(self, seconds):
        with self.lock:
            self.cooldown = max(self.cooldown, time.monotonic() + seconds)

    def enter(self, req, deadline):
        tokens = max(req["max_output_tokens"], len(req["input"] + req["instructions"]) / 3.5)
        spacing = max(60 / self.rpm if self.rpm else 0, 60 * tokens / self.tpm if self.tpm else 0)
        while True:
            with self.lock:
                if self.blocked:
                    raise AccountBlocked(self.blocked)
                now = time.monotonic()
                wait = max(self.next_start, self.cooldown) - now
                if wait <= 0:
                    self.next_start = now + spacing
                    return
            if time.monotonic() + max(wait, 0) >= deadline:
                raise TimeoutError("Run deadline reached while waiting for capacity")
            time.sleep(min(wait, .5))


def perform(client, job, output, gate, deadline, attempts=5):
    folder = output / "jobs" / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / "result.json"
    if result_path.exists():
        result = read(result_path)
        if result.get("request_sha256") != job["id"]:
            raise ValueError("Cached result fingerprint mismatch")
        validate(result, job)
        return "cached", result
    save(folder / "request.json", job["request"])
    provider = "openrouter" if "openrouter.ai" in str(getattr(client, "base_url", "")) else "openai"
    transport = dict(job["request"])
    if provider == "openrouter":
        transport["model"] = "openai/" + MODEL
        transport["extra_body"] = {"provider": {"allow_fallbacks": False, "require_parameters": True}}
    save(folder / "transport-request.json", {"provider": provider, "request": transport})
    for attempt in range(attempts):
        gate.enter(job["request"], deadline)
        if time.monotonic() >= deadline:
            raise TimeoutError("Run deadline reached")
        started = time.monotonic()
        try:
            raw = client.with_options(timeout=min(240, max(1, deadline - started))).responses.with_raw_response.create(**transport)
            response = raw.parse()
            body = response.model_dump(mode="json")
            save(folder / f"response-{attempt + 1}.json", body)
            headers = {k: v for k, v in raw.headers.items() if k.lower().startswith("x-ratelimit-") or k.lower() in {"retry-after", "x-request-id"}}
            save(folder / f"headers-{attempt + 1}.json", headers)
            if body.get("error"):
                error_code = str(body["error"].get("code", "provider_response_error"))
                if error_code in ACCOUNT_BLOCK_CODES or error_code == "402":
                    gate.abort(error_code)
                    raise AccountBlocked(error_code)
                raise ValueError("Provider returned a response error")
            returned_model = (response.model or "").removeprefix("openai/")
            if returned_model != MODEL and not returned_model.startswith(MODEL + "-"):
                raise ValueError("Returned model differs from requested Sol 6.1")
            if body.get("reasoning", {}).get("effort") not in {None, EFFORT}:
                raise ValueError("Returned reasoning differs from requested medium")
            if response.status != "completed":
                raise ValueError("Incomplete or refused response")
            result = validate(json.loads(response.output_text), job)
            result.update({"request_sha256": job["id"], "response_id": response.id, "returned_model": response.model, "effort": EFFORT, "usage": body["usage"], "elapsed_seconds": time.monotonic() - started, "report_id": job["report_id"], "provider": provider})
            save(result_path, result)
            return "complete", result
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            code = getattr(exc, "code", None)
            # Keep error logs free of provider messages that may echo sensitive inputs.
            save(folder / f"error-{attempt + 1}.json", {"type": type(exc).__name__, "http_status": status, "code": code})
            if isinstance(exc, AccountBlocked):
                raise
            if status == 402 or code in ACCOUNT_BLOCK_CODES:
                gate.abort(code or "http_402")
                raise AccountBlocked(code or "http_402") from exc
            transient = (status in {429, 500, 502, 503, 504} and code not in ACCOUNT_BLOCK_CODES) or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}
            if not transient or attempt + 1 == attempts:
                raise
            gate.defer(retry_delay(exc, attempt + 1))
    raise RuntimeError("No result")


def aggregate(plan, output):
    by_report = defaultdict(dict)
    complete, pending, warnings = [], [], []
    for job in plan["jobs"]:
        path = output / "jobs" / job["id"] / "result.json"
        if not path.exists():
            pending.append(job["id"])
            continue
        r = read(path)
        if r.get("request_sha256") != job["id"]:
            raise ValueError("Cached result fingerprint mismatch")
        validate(r, job)
        complete.append(r)
        for f in r["findings"]:
            by_report[job["report_id"]][f["finding_id"]] = f
            for s in [f, *f["sub_findings"]]:
                if not s["quote_verified"] or s.get("quote_contains_email"):
                    warnings.append({"report": job["report_id"], "finding": f["finding_id"], "item": s.get("id", f["finding_id"])})
    reports = []
    expected = {f["id"] for f in plan["findings"]}
    for r in plan["reports"]:
        scores = by_report[r["id"]]
        missing = sorted(expected - scores.keys())
        reports.append({"report_id": r["id"], "complete": not missing, "missing_findings": missing, "scores": scores,
                        "mean_coverage": sum(f["score"] for f in scores.values()) / len(scores) if scores and not missing else None,
                        "main_contradiction_flags": [fid for fid, f in scores.items() if f["contradicted"]], "contradiction_penalties": "pending human review"})
    return {"model": MODEL, "effort": EFFORT, "total_jobs": len(plan["jobs"]), "completed_jobs": len(complete), "pending_jobs": pending,
            "reports": reports, "quote_warnings": warnings,
            "usage": {k: sum(r["usage"].get(k, 0) for r in complete) for k in ["input_tokens", "output_tokens", "total_tokens"]}}


def run(args):
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    plan_path = args.plan or Path(read(args.output / "latest-plan.json")["plan"])
    plan = read(plan_path)
    if plan["model"] != MODEL or plan["effort"] != EFFORT:
        raise ValueError("Plan settings differ from Sol 6.1 medium")
    if args.provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY is missing")
        client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", max_retries=0)
    else:
        client = OpenAI(max_retries=0)
    deadline = time.monotonic() + args.deadline_minutes * 60
    gate = Gate(args.rpm, args.tpm)
    # Interleave reports rather than finish one report before beginning the next.
    jobs = sorted(plan["jobs"], key=lambda j: (j["goal_period"], j["report_id"], j["id"]))
    failures, latencies = [], []
    blocked = None
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(perform, client, j, args.output, gate, deadline): j for j in jobs}
        for index, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                status, result = future.result()
                if status != "cached":
                    latencies.append(result["elapsed_seconds"])
            except AccountBlocked as exc:
                blocked = str(exc)
                for queued in futures:
                    queued.cancel()
                break
            except Exception as exc:
                status = "failed"
                failures.append({"job": job["id"], "report": job["report_id"], "type": type(exc).__name__})
            avg = sum(latencies) / len(latencies) if latencies else None
            print(json.dumps({"done": index, "total": len(jobs), "status": status, "report": job["report_id"], "mean_call_seconds": round(avg, 1) if avg else None,
                              "elapsed_minutes": round((time.monotonic() - started) / 60, 1)}), flush=True)
            if index % 32 == 0 or index == len(jobs):
                save(plan_path.parent / "grades.json", aggregate(plan, args.output))
                save(plan_path.parent / "status.json", {"finished_jobs": index, "total": len(jobs), "failures": failures, "concurrency": args.concurrency})
    grades = aggregate(plan, args.output)
    if blocked:
        grades["blocked"] = blocked
    save(plan_path.parent / "grades.json", grades)
    save(plan_path.parent / "status.json", {"completed_jobs": grades["completed_jobs"], "total": len(jobs), "failures": failures, "concurrency": args.concurrency, "blocked": blocked})
    if blocked:
        raise SystemExit(f"Stopped: {blocked}; {len(grades['pending_jobs'])} jobs remain. Resume after restoring API credit.")
    if grades["pending_jobs"]:
        raise SystemExit(f"Incomplete: {len(grades['pending_jobs'])} jobs remain; rerun the same plan to resume.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=["prepare", "run"])
    p.add_argument("--findings", type=Path)
    p.add_argument("--expected-findings", type=int, default=96)
    p.add_argument("--reports", type=Path)
    p.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parents[2] / "runs")
    p.add_argument("--rubric", type=Path, default=Path(__file__).resolve().parents[2] / "benchmarks/aivillage/judge-prompt-v8.txt")
    p.add_argument("--goals", type=Path)
    p.add_argument("--goal-map", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--plan", type=Path)
    p.add_argument("--provider", choices=["openai", "openrouter"], default="openai")
    p.add_argument("--concurrency", type=int, default=32)
    p.add_argument("--group-size", type=int, default=3)
    p.add_argument("--max-subfindings", type=int, default=12)
    p.add_argument("--deadline-minutes", type=float, default=65)
    p.add_argument("--rpm", type=float, default=0, help="Optional account request-per-minute pacing")
    p.add_argument("--tpm", type=float, default=0, help="Optional approximate token-per-minute pacing")
    args = p.parse_args()
    if min(args.concurrency, args.group_size, args.max_subfindings) <= 0 or args.deadline_minutes <= 0:
        p.error("Concurrency, group limits and deadline must be positive")
    if args.stage == "prepare":
        if not args.findings or not args.reports:
            p.error("prepare requires --findings and --reports")
        prepare(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
