"""Grade completed final URLQuery reports with synchronous GPT-6 Astra API calls.

    .venv/bin/python benchmarks/urlquery/judge/grade_openrouter.py \
      --launch runs/urlquery/final-20260927-agents-v6/launch.json --workers 32

Each finding is a separate synchronous OpenRouter chat-completion request. The
runner saves each result immediately and resumes only matching, successful
grades. It never reads Claude judge output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import grade as common
import render_sheet
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[3]
MODEL = "openai/gpt-6-astra"
EFFORT = "high"
OUT = ROOT / "reports/urlquery/graded/judge_gpt_6_astra_high"
KEY_FILE = (ROOT / "runs/.openrouter_key.openai_gpt-6-astra").resolve()
SYSTEM = common.SYSTEM


def completed_reports(launch_path: Path) -> list[Path]:
    launch = json.loads(launch_path.read_text())
    out: list[Path] = []
    for plan in launch["plans"]:
        for result in sorted(Path(plan).parent.glob("*.result.json")):
            run_dir = Path(json.loads(result.read_text())["run_dir"])
            if (run_dir / "report.md").is_file():
                out.append(run_dir)
    return list(dict.fromkeys(out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--launch", type=Path)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--findings", nargs="*")
    ap.add_argument("--plan", action="store_true")
    args = ap.parse_args()

    run_dirs = list(args.runs)
    if args.launch:
        run_dirs += completed_reports(args.launch)
    run_dirs = list(dict.fromkeys(d for d in run_dirs if (d / "report.md").is_file()))
    if not run_dirs:
        sys.exit("no completed reports")

    findings = render_sheet.load_findings()
    heads = [f["id"] for f in findings if f["parent"] is None]
    if args.findings:
        heads = [h for h in heads if h in args.findings]
    subs = {h: [f["id"] for f in findings if f["parent"] == h] for h in heads}
    article = common.article_text()
    stamp = {
        "judge": MODEL,
        "effort": EFFORT,
        "prompt_sha256": common.sha(render_sheet.TEMPLATE.read_bytes()),
        "findings_sha256": common.sha(render_sheet.FINDINGS.read_bytes()),
        "article_sha256": common.sha(article),
    }
    print(f"{len(run_dirs)} final-run reports x {len(heads)} findings = {len(run_dirs) * len(heads)} calls", flush=True)
    if args.plan:
        return

    key = os.environ.get("OPENROUTER_API_KEY") or KEY_FILE.read_text().strip()
    if not key:
        sys.exit("OpenRouter API key is missing")
    client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", timeout=600.0, max_retries=2)
    OUT.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    files: dict[str, dict] = {}
    reports: dict[str, str] = {}
    todo: list[tuple[Path, str]] = []
    for d in run_dirs:
        report = (d / "report.md").read_text()
        reports[d.name] = report
        path = OUT / f"{d.name}.json"
        prev = json.loads(path.read_text()) if path.exists() else {}
        same = all(prev.get(k) == v for k, v in stamp.items()) and prev.get("report_sha256") == common.sha(report)
        body = {**common.run_meta(d), **stamp, "report_sha256": common.sha(report),
                "findings": prev.get("findings", {}) if same else {}}
        files[d.name] = body
        todo += [(d, h) for h in heads if body["findings"].get(h, {}).get("status") != "ok"]
    print(f"{len(todo)} synchronous API calls to make; workers={args.workers}; output={OUT}", flush=True)

    def write(name: str) -> None:
        body = files[name]
        scored = [body["findings"][h]["score"] for h in heads if body["findings"].get(h, {}).get("status") == "ok"]
        body["n_scored"] = len(scored)
        body["n_findings"] = len(heads)
        body["score_mean"] = round(sum(scored) / len(scored), 3) if len(scored) == len(heads) else None
        body["unscored"] = [h for h in heads if body["findings"].get(h, {}).get("status") != "ok"]
        body["scan_coverage"] = render_sheet.coverage(reports[name])
        tmp = OUT / f".{name}.json.tmp"
        tmp.write_text(json.dumps(body, indent=1, ensure_ascii=False))
        tmp.replace(OUT / f"{name}.json")

    done = 0

    def do(item: tuple[Path, str]) -> tuple[str, str, str]:
        d, h = item
        prompt = render_sheet.render(h, article, reports[d.name])
        try:
            response = client.chat.completions.create(
                model=MODEL,
                reasoning_effort=EFFORT,
                response_format={"type": "json_object"},
                max_completion_tokens=24000,
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            )
            choice = response.choices[0]
            raw = choice.message.content or ""
            usage = response.usage.model_dump() if response.usage else {}
            if choice.message.refusal or choice.finish_reason == "content_filter":
                result = {"status": "refused", "refusal": choice.message.refusal or choice.finish_reason,
                          "raw": [raw], "usage": [usage]}
            elif choice.finish_reason == "length":
                result = {"status": "truncated", "raw": [raw], "usage": [usage]}
            else:
                data = common.extract_json(raw)
                if data is None:
                    result = {"status": "unparseable", "raw": [raw], "usage": [usage]}
                else:
                    clean, notes = common.validate(data, h, subs[h])
                    result = {"status": "ok", **clean, "validation": notes,
                              "raw": [raw], "usage": [usage]}
        except Exception as exc:  # noqa: BLE001
            result = {"status": "api_error", "error": f"{type(exc).__name__}: {exc}"[:500]}
        with lock:
            nonlocal done
            files[d.name]["findings"][h] = result
            write(d.name)
            done += 1
            label = f"{result['score']:.1f}" if result["status"] == "ok" else result["status"]
            print(f"[{done}/{len(todo)}] {d.name[:64]} {h} {label}", flush=True)
        return d.name, h, result["status"]

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(do, item) for item in todo]
        for future in as_completed(futures):
            future.result()
    print(f"done in {(time.time() - started) / 60:.1f} minutes", flush=True)
    statuses = {"ok": 0, "other": 0}
    for body in files.values():
        for h in heads:
            status = body["findings"].get(h, {}).get("status")
            statuses["ok" if status == "ok" else "other"] += 1
    print(f"graded {statuses['ok']}/{sum(statuses.values())} finding calls", flush=True)


if __name__ == "__main__":
    main()
