#!/usr/bin/env python3
"""Check merged AI Village findings against the Village records, one sandboxed agent per finding.

    python3 scripts/run_aivillage_verify.py OUT_DIR MERGED_FULL_JSON [--only M001 M002 ...] [--workers 3]
    python3 scripts/run_aivillage_verify.py OUT_DIR MERGED_FULL_JSON --status

For each finding this fills {{FINDING}} in the config's prompt, runs sandbox/docker/run_trial.sh
(configs/aivillage-verify.toml) and saves the agent's verified.json as OUT_DIR/results/<ID>.json.
A finding with a saved result is skipped, so rerunning the same command resumes. A failed
finding is a row in OUT_DIR/failures.jsonl and is retried on the next run. Exit code 0 when
every requested finding has a result, 2 otherwise.
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aivillage-verify.toml"
TEMPLATE = ROOT / "sandbox/prompts/aivillage-verify-v1.txt"
DATA = Path("/home/oscar_gilg18/Dev/MessageBoardAuditBench/data/aivillage/full-v2-reasoning")
MODEL = "claude-sonnet-5-5"
SUB_VERDICTS = {"supported", "partly supported", "contradicted", "not found", "outside the records"}
lock = threading.Lock()
start_lock = threading.Lock()


def render(finding):
    """The finding as the agent reads it: wording, notes and the outside quotes that say what to look for."""
    lines = [f"{finding['id']} — {finding['headline']}", "", f"Finding: {finding['finding']}"]
    lines += [f"Note: {n}" for n in finding.get("notes", [])]
    sources = "; ".join(f"{s['source']['type']}, published {s['source_date']}" for s in finding["sources"])
    lines += ["", f"Written from: {sources}", ""]
    for sf in finding["subfindings"]:
        lines.append(f"{sf['id']} — {sf['claim']}")
        lines += [f"  Note: {n}" for n in sf.get("notes", [])]
        lines += [f"  Outside account ({s.get('source_kind') or 'source'}): \"{s['quote']}\"" for s in sf["source_support"]]
        lines.append("")
    return "\n".join(lines).rstrip()


def problems(result, finding):
    """Why a verified.json cannot be used as is; empty when it can."""
    out = []
    if result.get("id") != finding["id"]:
        out.append("wrong finding id")
    if result.get("verdict") not in {"keep", "needs rewording", "drop"}:
        out.append(f"unknown verdict {result.get('verdict')!r}")
    want = [sf["id"] for sf in finding["subfindings"]]
    got = [sf.get("id") for sf in result.get("subfindings", [])]
    if sorted(want) != sorted(got):
        out.append(f"subfindings {got} do not match {want}")
    out += [f"{sf.get('id')}: unknown verdict {sf.get('verdict')!r}" for sf in result.get("subfindings", [])
            if sf.get("verdict") not in SUB_VERDICTS]
    return out


def fail(out, fid, kind, detail):
    with lock, (out / "failures.jsonl").open("a") as f:
        f.write(json.dumps({"finding": fid, "class": kind, "detail": str(detail)[:500]}) + "\n")


def verify(out, finding):
    fid = finding["id"]
    target = out / "results" / f"{fid}.json"
    if target.exists():
        return
    prompt = out / "prompts" / f"{fid}.txt"
    prompt.write_text(TEMPLATE.read_text().replace("{{FINDING}}", render(finding)))
    env = {**os.environ, "ALLOW_NETWORKED_SUBSCRIPTION": "1", "CONFIG": str(CONFIG), "DATA_DIR": str(DATA),
           "PROMPT_FILE_OVERRIDE": str(prompt)}
    log = out / "logs" / f"{fid}.log"
    with start_lock:  # simultaneous launches race on the image build, so start them 20 seconds apart
        time.sleep(20)
    with log.open("w") as f:
        subprocess.run(["sg", "docker", "-c", f"sandbox/docker/run_trial.sh claude {MODEL} 1"], cwd=ROOT, env=env,
                       stdout=f, stderr=subprocess.STDOUT)
    run = re.search(r"^run: (.+)$", log.read_text(), re.M)
    if not run:
        return fail(out, fid, "no_run", log.read_text()[-300:])
    verified = Path(run.group(1)) / "work/verified.json"
    if not verified.exists():
        return fail(out, fid, "no_output", run.group(1))
    try:
        result = json.loads(verified.read_text())
    except ValueError as exc:
        return fail(out, fid, "malformed", f"{run.group(1)}: {exc}")
    issues = problems(result, finding)
    result["run_dir"] = run.group(1)
    result["format_problems"] = issues
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"finding": fid, "verdict": result.get("verdict"), "format_problems": issues}), flush=True)


def status(out, findings):
    done = [json.loads((out / "results" / f"{f['id']}.json").read_text()) for f in findings
            if (out / "results" / f"{f['id']}.json").exists()]
    verdicts, subs = {}, {}
    for r in done:
        verdicts[r.get("verdict")] = verdicts.get(r.get("verdict"), 0) + 1
        for sf in r.get("subfindings", []):
            subs[sf.get("verdict")] = subs.get(sf.get("verdict"), 0) + 1
    return {"findings": len(findings), "done": len(done), "finding_verdicts": verdicts, "subfinding_verdicts": subs,
            "with_format_problems": sum(bool(r["format_problems"]) for r in done),
            "next": "complete" if len(done) == len(findings) else "resume (rerun the same command)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("merged", type=Path)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    findings = json.loads(args.merged.read_text())["merged"]
    if args.only:
        findings = [f for f in findings if f["id"] in args.only]
    out = args.out.resolve()
    if not args.status:
        for sub in ("results", "prompts", "logs"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        (out / "failures.jsonl").unlink(missing_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(lambda f: verify(out, f), findings))
    final = status(out, findings)
    print(json.dumps(final, indent=2))
    raise SystemExit(0 if final["next"] == "complete" else 2)


if __name__ == "__main__":
    main()
