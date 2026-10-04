#!/usr/bin/env python3
"""Resume URLQuery Astra grading through synchronous OpenAI Chat Completions.

Reads the frozen run list from an OpenAI Batch state file and grades reports
that do not already have a complete batch grade. Writes separate provenance-
stamped sync grades after every finding, so an interrupted run can resume.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmarks.urlquery.judge.grade_openai_batch import (  # noqa: E402
    API,
    EFFORT,
    MODEL,
    parse_response,
    save,
)
from benchmarks.urlquery.judge.grade_openai_batch import (  # noqa: E402
    BASE as BATCH_BASE,
)
from messageboard_audit_bench.grading import findings as fj  # noqa: E402

OUT = fj.output_root() / "judge_gpt_6_astra_high_openai_sync"


def needs_sync(run: dict) -> bool:
    batch_path = BATCH_BASE / f"{run['name']}.json"
    if not batch_path.exists():
        return True
    return json.loads(batch_path.read_text()).get("n_scored") != len(fj.headlines())


def judge_one(api: API, head: str, prompt: str) -> dict:
    body = {"model": MODEL, "reasoning_effort": EFFORT,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 24000,
            "messages": [{"role": "system", "content": fj.SYSTEM},
                         {"role": "user", "content": prompt}]}
    for attempt in range(5):
        try:
            response = json.loads(api.request("POST", "/chat/completions",
                                              json.dumps(body, ensure_ascii=False).encode(),
                                              "application/json"))
            return parse_response({"response": {"status_code": 200, "body": response}}, head)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                return {"status": "api_error", "error": f"HTTP {exc.code}: {exc.read(300).decode(errors='replace')}"}
        except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as exc:
            if attempt == 4:
                return {"status": "api_error", "error": f"{type(exc).__name__}: {exc}"}
        time.sleep(min(2 ** attempt, 16))
    raise RuntimeError("unreachable retry exit")


def grade_run(run: dict, heads: list[str], article: str, stamp: dict) -> tuple[str, int, float | None]:
    path = OUT / f"{run['name']}.json"
    run_path = Path(run["path"])
    report = (run_path / "report.md").read_text()
    if fj.sha(report) != run["report_sha256"]:
        raise RuntimeError(f"report changed after batch preparation: {run['name']}")
    if path.exists():
        grade = json.loads(path.read_text())
        if any(grade.get(k) != v for k, v in stamp.items()) or grade.get("report_sha256") != run["report_sha256"]:
            raise RuntimeError(f"grade provenance conflict: {path}")
    else:
        grade = {**fj.run_meta(run_path), **stamp, "article_context": "full",
                 "report_sha256": run["report_sha256"], "findings": {}}
    api = API()
    for head in heads:
        if grade["findings"].get(head, {}).get("status") == "ok":
            continue
        grade["findings"][head] = judge_one(api, head, fj.render(head, article, report))
        save(path, fj.summarize(grade, heads, report))
        print(run["name"], head, grade["findings"][head]["status"], flush=True)
    grade = fj.summarize(grade, heads, report)
    save(path, grade)
    return run["name"], grade["n_scored"], grade["score_mean"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_state", type=Path)
    parser.add_argument("--priority-only", action="store_true", help="grade only the 10-minute Sol ReAct report")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    state = json.loads(args.batch_state.read_text())
    runs = [run for run in state["runs"] if needs_sync(run)]
    runs.sort(key=lambda run: (run["agent"] != "react" or run["model"] != "openai/gpt-6-sol"
                               or run["budget_min"] != 10, run["index"]))
    if args.priority_only:
        runs = [run for run in runs if run["agent"] == "react" and
                run["model"] == "openai/gpt-6-sol" and run["budget_min"] == 10]
    heads = state["headlines"]
    article = fj.article_text("full")
    stamp = {**fj.stamp(MODEL, EFFORT, article), "model_id": MODEL,
             "transport": "openai_chat_completions_sync"}
    print(f"{len(runs)} reports x {len(heads)} findings; {args.workers} workers", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(grade_run, run, heads, article, stamp) for run in runs]
        for future in as_completed(futures):
            print("COMPLETE", *future.result(), flush=True)


if __name__ == "__main__":
    main()
