#!/usr/bin/env python3
"""Check merged AI Village findings against the Village records, one sandboxed agent per group of findings.

    python3 scripts/run_aivillage_verify.py OUT_DIR MERGED_FULL_JSON [--only M001 M002 ...] [--workers 3]
    python3 scripts/run_aivillage_verify.py OUT_DIR MERGED_FULL_JSON --status

Findings are grouped by the Village goal period they probably fall in, at most 8 per group, with
about two minutes of budget per finding. For each group this fills the findings into the config's
prompt, runs sandbox/docker/run_trial.sh (configs/aivillage-verify.toml) and saves each finding's
verified/<ID>.json as OUT_DIR/results/<ID>.json.
A finding with a saved result is skipped, so rerunning the same command resumes. A failed
finding is a row in OUT_DIR/failures.jsonl and is retried on the next run. Exit code 0 when
every requested finding has a result, 2 otherwise.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aivillage-verify.toml"
TEMPLATE = ROOT / "sandbox/prompts/aivillage-verify-v2.txt"
DATA = Path("/home/oscar_gilg18/Dev/MessageBoardAuditBench/data/aivillage/full-v2-reasoning")
MODEL = "claude-sonnet-5-5"
LAUNCH = datetime.date(2025, 4, 2)  # Day 1 of the Village
GROUP_SIZE = 8
MINUTES_PER_FINDING = 2
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


def estimated_date(finding):
    """Roughly when the behavior happened: a 'Day N' in the text, else the earliest X or Discord
    source (those are written within days). None when only later articles report it."""
    text = json.dumps(finding, ensure_ascii=False)
    day = re.search(r"\bDay (\d{1,3})\b", text)
    if day:
        return (LAUNCH + datetime.timedelta(days=int(day.group(1)) - 1)).isoformat()
    dates = [s["source_date"] for s in finding["sources"] if s["id"][0] in "XD"]
    return min(dates) if dates else None


def groups(findings):
    """Findings grouped by the Village goal period they probably fall in (or, when only an article
    reports them, by that article), at most GROUP_SIZE per group."""
    goals = sorted((json.loads(line) for line in (DATA / "village_goals.jsonl").read_text().splitlines()),
                   key=lambda g: g["start_time"])
    by_key = {}
    for f in findings:
        date = estimated_date(f)
        if date:
            goal = [g for g in goals if g["start_time"][:10] <= date][-1:] or goals[:1]
            g = goal[0]
            key = "goal " + g["start_time"][:10]
            note = (f"These findings probably fall in or near the goal period that started {g['start_time'][:10]}"
                    f" and ended {(g['end_time'] or 'after the records end')[:10]}: \"{g['goal'][:300]}\". "
                    "The period is an estimate from publication dates; a finding may belong to an earlier one.")
        else:
            src = f["sources"][0]["source"]
            key = "article " + src.get("title", "")
            note = (f"These findings come from the article \"{src.get('title', '')}\", published "
                    f"{f['sources'][0]['source_date']}. The behavior happened before that, possibly months before.")
        by_key.setdefault(key, {"note": note, "findings": []})["findings"].append(f)
    out = []
    for key in sorted(by_key):
        fs = by_key[key]["findings"]
        for i in range(0, len(fs), GROUP_SIZE):
            out.append({"name": re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:50] + f"-{i // GROUP_SIZE + 1}",
                        "note": by_key[key]["note"], "findings": fs[i:i + GROUP_SIZE]})
    return out


def verify(out, group):
    todo = [f for f in group["findings"] if not (out / "results" / f"{f['id']}.json").exists()]
    if not todo:
        return
    name = group["name"]
    prompt = out / "prompts" / f"{name}.txt"
    text = "\n\n---\n\n".join(render(f) for f in todo)
    prompt.write_text(TEMPLATE.read_text().replace("{{GROUP_NOTE}}", group["note"]).replace("{{FINDING}}", text))
    env = {**os.environ, "ALLOW_NETWORKED_SUBSCRIPTION": "1", "CONFIG": str(CONFIG), "DATA_DIR": str(DATA),
           "PROMPT_FILE_OVERRIDE": str(prompt), "BUDGET_MIN": str(MINUTES_PER_FINDING * len(todo) + 3)}
    log = out / "logs" / f"{name}.log"
    with start_lock:  # simultaneous launches race on the image build, so start them a few seconds apart
        time.sleep(8)
    with log.open("w") as f:
        subprocess.run(["sg", "docker", "-c", f"sandbox/docker/run_trial.sh claude {MODEL} 1"], cwd=ROOT, env=env,
                       stdout=f, stderr=subprocess.STDOUT)
    if not re.search(r"^run: (.+)$", log.read_text(), re.M):
        return [fail(out, f["id"], "no_run", log.read_text()[-300:]) for f in todo]
    collect(out, todo, report_missing=True)


def collect(out, findings, report_missing=False):
    """Save every finished verification found in the launched runs' folders as results/<ID>.json."""
    produced = {}
    for log in sorted((out / "logs").glob("*.log"), key=lambda p: p.stat().st_mtime):
        run = re.search(r"^run: (.+)$", log.read_text(), re.M)
        if run:
            for path in list(Path(run.group(1), "work/verified").glob("*.json")) + list(Path(run.group(1), "work").glob("verified.json")):
                produced[path.stem if path.stem != "verified" else log.stem] = (path, run.group(1))
    for finding in findings:
        fid = finding["id"]
        if (out / "results" / f"{fid}.json").exists():
            continue
        if fid not in produced:
            if report_missing:
                fail(out, fid, "no_output", "")
            continue
        path, run_dir = produced[fid]
        try:
            result = json.loads(path.read_text())
        except ValueError as exc:
            fail(out, fid, "malformed", f"{run_dir}: {exc}")
            continue
        result["run_dir"] = run_dir
        result["format_problems"] = problems(result, finding)
        (out / "results" / f"{fid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"finding": fid, "verdict": result.get("verdict"), "format_problems": result["format_problems"]}), flush=True)


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
    ap.add_argument("--skip", nargs="*", default=[], help="group names another process is already running")
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
            list(pool.map(lambda g: verify(out, g), [g for g in groups(findings) if g["name"] not in args.skip]))
        collect(out, findings)
    final = status(out, findings)
    print(json.dumps(final, indent=2))
    raise SystemExit(0 if final["next"] == "complete" else 2)


if __name__ == "__main__":
    main()
