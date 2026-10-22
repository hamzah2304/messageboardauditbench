#!/usr/bin/env python3
"""Answer-key QA: one sandboxed agent checks one headline finding (or a small group) against the data.

    python3 scripts/run_answer_key_qa.py german-wiki OUT_DIR [--only W02 W11] [--workers 4]
    python3 scripts/run_answer_key_qa.py aivillage OUT_DIR --group M029 M053 --focus "..."
    python3 scripts/run_answer_key_qa.py german-wiki OUT_DIR --status
    python3 scripts/run_answer_key_qa.py german-wiki OUT_DIR --merge     # write results into the answer key

Each launch fills sandbox/prompts/answer-key-qa-v1.txt with the eval's modules (benchmarks/qa/modules/:
finding description plus the eval's addendum, derivability, data note), the finding(s) to check and the
rest of the answer key, and runs sandbox/docker/run_trial.sh with PROMPT_FILE_OVERRIDE and the eval's
config (configs/answer-key-qa-<eval>.toml): the same isolated container and read-only data the
investigators get, Claude Code on the subscription. The agent writes /work/qa/<id>.json; this saves it
as OUT_DIR/results/<id>.json with its run folder and any format problems. A finding with a saved result
is skipped, so rerunning resumes. --merge folds the results into benchmarks/<eval>/answer-key.json
(answer-key-v1) and records the prompt, modules and model under qa_process.
"""
import argparse
import importlib.util
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configured_model(helper: str) -> str:
    """The model configs/standard.toml [helpers] names for this script (its bare id); no fallback."""
    import tomllib

    entry = tomllib.loads((ROOT / "configs/standard.toml").read_text())["helpers"][helper]
    return entry["model"].split("/", 1)[1]
PRIMARY = Path(subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute",
                                        "--git-common-dir"], text=True).strip()).parent
# Loaded from its file, not via sys.path: the package folder also holds a benchmarks.py that would
# shadow the top-level benchmarks package for anything imported later.
_spec = importlib.util.spec_from_file_location("answer_key", ROOT / "slopvestigator_bench/answer_key.py")
answer_key = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_key)

TEMPLATE = ROOT / "sandbox/prompts/answer-key-qa-v1.txt"
MODULES = ROOT / "benchmarks/qa/modules"
EVALS = {
    "german-wiki": {"config": "answer-key-qa-german-wiki", "data": PRIMARY / "data/verbatim",
                    "modules": ["finding-description.txt", "finding-description-german-wiki.txt",
                                "derivability.txt", "data-note-german-wiki.txt"],
                    "full_key_in_prompt": True},
    "aivillage": {"config": "answer-key-qa-aivillage", "data": PRIMARY / "data/aivillage/full-v2-reasoning",
                  "modules": ["finding-description.txt", "finding-description-aivillage.txt",
                              "derivability.txt", "data-note-aivillage.txt"],
                  "full_key_in_prompt": False},
}
lock = threading.Lock()
start_lock = threading.Lock()


def key_path(ev):
    return ROOT / "benchmarks" / ev / "answer-key.json"


def render_finding(f):
    lines = [f"{f['id']} — {f['claim']}"]
    if f.get("detail"):
        lines.append(f"Detail: {f['detail']}")
    if f.get("judge_notes"):
        lines.append(f"Judge notes: {f['judge_notes']}")
    for k, v in f.get("fields", {}).items():
        if k in ("section", "behavior_dates"):
            lines.append(f"{k.replace('_', ' ').capitalize()}: {v}")
    lines += ["", "Subfindings:"]
    for s in f["subfindings"]:
        lines.append(f"{s['id']} — {s['claim']}")
        if s.get("judge_notes"):
            lines.append(f"  Judge notes: {s['judge_notes']}")
        quote = s.get("fields", {}).get("report_quote")
        if quote:
            lines.append(f"  The original report's wording: \"{quote}\"")
        for e in s.get("evidence", []):
            lines.append(f"  Earlier check's evidence (verify it yourself): {e['text']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_key(key, skip, with_subfindings):
    lines = []
    for f in key["findings"]:
        if f["id"] in skip:
            continue
        lines.append(f"{f['id']} — {f['claim']}")
        if with_subfindings:
            lines += [f"  {s['id']} — {s['claim']}" for s in f["subfindings"]]
    return "\n".join(lines)


def build_prompt(ev, key, group, focus):
    cfg = EVALS[ev]
    mods = {m: (MODULES / m).read_text().strip() for m in cfg["modules"]}
    desc = "\n\n".join(mods[m] for m in cfg["modules"] if m.startswith("finding-description"))
    ids = [f["id"] for f in group]
    many = len(group) > 1
    fill = {
        "{{FINDING_COUNT_TEXT}}": f"the {len(group)} findings" if many else "the finding",
        "{{FINDING_HEADING}}": "The findings to check" if many else "The finding to check",
        "{{FOCUS}}": f"{focus.strip()}\n\n" if focus else "",
        "{{FINDINGS}}": "\n\n---\n\n".join(render_finding(f) for f in group),
        "{{ANSWER_KEY}}": render_key(key, set(ids), cfg["full_key_in_prompt"]),
        "{{OUTPUT_TEXT}}": ("one file per finding, " + " and ".join(f"/work/qa/{i}.json" for i in ids)) if many
        else f"/work/qa/{ids[0]}.json",
        "{{DATA_NOTE}}": next(v for k, v in mods.items() if k.startswith("data-note")),
        "{{FINDING_DESCRIPTION}}": desc,
        "{{DERIVABILITY}}": mods["derivability.txt"],
    }
    text = TEMPLATE.read_text()
    for k, v in fill.items():
        text = text.replace(k, v)
    left = set(re.findall(r"\{\{[A-Z_]+\}\}", text)) - {"{{BUDGET_MIN}}"}
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    return text


def fail(out, fid, kind, detail):
    with lock, (out / "failures.jsonl").open("a") as f:
        f.write(json.dumps({"finding": fid, "class": kind, "detail": str(detail)[:500]}) + "\n")


def run_group(ev, out, key, group, focus, model, budget):
    todo = [f for f in group if not (out / "results" / f"{f['id']}.json").exists()]
    if not todo:
        return
    name = "-".join(f["id"] for f in todo)
    prompt = out / "prompts" / f"{name}.txt"
    prompt.write_text(build_prompt(ev, key, todo, focus))
    env = {**os.environ, "CONFIG": str(ROOT / "configs" / f"{EVALS[ev]['config']}.toml"),
           "DATA_DIR": str(EVALS[ev]["data"]), "PROMPT_FILE_OVERRIDE": str(prompt), "BUDGET_MIN": str(budget)}
    log = out / "logs" / f"{name}.log"
    # Simultaneous launches race on tagging the image they each build, so the next launch waits until
    # this one has built it and printed its run folder.
    with start_lock, log.open("w") as f:
        proc = subprocess.Popen(["sg", "docker", "-c", f"sandbox/docker/run_trial.sh claude {model} 1"], cwd=ROOT,
                                env=env, stdout=f, stderr=subprocess.STDOUT)
        while proc.poll() is None and not re.search(r"^run: ", log.read_text(), re.M):
            time.sleep(2)
        time.sleep(5)
    proc.wait()
    run = re.search(r"^run: (.+)$", log.read_text(), re.M)
    if not run:
        return [fail(out, f["id"], "no_run", log.read_text()[-300:]) for f in todo]
    collect(ev, out, todo, Path(run.group(1)))


def collect(ev, out, findings, run_dir):
    kinds = answer_key.CITATION_KINDS[ev]
    for f in findings:
        path = run_dir / "work/qa" / f"{f['id']}.json"
        if not path.exists():
            fail(out, f["id"], "no_output", str(run_dir))
            continue
        try:
            result = json.loads(path.read_text())
        except ValueError as exc:
            fail(out, f["id"], "malformed", f"{run_dir}: {exc}")
            continue
        result["run_dir"] = str(run_dir)
        result["format_problems"] = answer_key.qa_problems(result, f)
        result["citations"] = sum(len(answer_key.parse_citations(t, kinds))
                                  for t in [*result.get("evidence", []),
                                            *[e for s in result.get("subfindings", []) for e in s.get("evidence", [])]])
        (out / "results" / f"{f['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
        print(json.dumps({"finding": f["id"], "outcome": result.get("outcome"),
                          "format_problems": result["format_problems"]}), flush=True)


def status(out, findings):
    done = {f["id"]: json.loads((out / "results" / f"{f['id']}.json").read_text()) for f in findings
            if (out / "results" / f"{f['id']}.json").exists()}
    rows = []
    for fid, r in done.items():
        rows.append({"id": fid, "outcome": r.get("outcome"), "significance": r.get("significance"),
                     "subfindings": {s.get("id"): f"{s.get('verdict')}/{s.get('significance')}"
                                     + ("/overstated" if str(s.get("overstated")).lower() == "yes" else "")
                                     for s in r.get("subfindings", [])},
                     "format_problems": r["format_problems"]})
    return {"findings": len(findings), "done": len(done), "results": rows,
            "next": "complete" if len(done) == len(findings) else "resume (rerun the same command)"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def merge(ev, out, key, model, budget):
    kinds = answer_key.CITATION_KINDS[ev]
    merged = []
    for i, f in enumerate(key["findings"]):
        p = out / "results" / f"{f['id']}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        if r["format_problems"]:
            print(f"{f['id']}: not merged, format problems {r['format_problems']}")
            continue
        key["findings"][i] = answer_key.apply_qa(f, r, kinds, run=os.path.relpath(os.path.realpath(r["run_dir"]), PRIMARY))
        merged.append(f["id"])
    key["qa_process"] = {
        "prompt": "sandbox/prompts/answer-key-qa-v1.txt", "prompt_sha256": sha(TEMPLATE),
        "modules": {m: sha(MODULES / m) for m in EVALS[ev]["modules"]},
        "config": f"configs/{EVALS[ev]['config']}.toml", "model": model, "budget_min_per_finding": budget,
        "harness": "Claude Code (subscription) in sandbox/docker/run_trial.sh", "results": os.path.relpath(os.path.realpath(out), PRIMARY),
        "merged": datetime.date.today().isoformat(),
    }
    problems = answer_key.validate(key)
    if problems:
        raise SystemExit("\n".join(problems))
    answer_key.dump(key, key_path(ev))
    print(f"merged {len(merged)} findings into {key_path(ev)}: {merged}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval", choices=sorted(EVALS))
    ap.add_argument("out", type=Path)
    ap.add_argument("--only", nargs="*", help="finding ids, each checked on its own")
    ap.add_argument("--group", nargs="*", help="finding ids checked together by one agent")
    ap.add_argument("--focus", default="", help="a note placed before the findings (with --group)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=int, default=20, help="minutes per finding")
    ap.add_argument("--model", default=configured_model("answer_key_qa"),
                    help="Claude Code model (default: configs/standard.toml [helpers.answer_key_qa])")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    key = answer_key.load(key_path(a.eval))
    out = a.out.resolve()
    findings = key["findings"]
    if a.only:
        findings = [f for f in findings if f["id"] in a.only]
    if a.group:
        findings = [f for f in key["findings"] if f["id"] in a.group]
    if a.merge:
        return merge(a.eval, out, key, a.model, a.budget)
    if not a.status:
        for sub in ("results", "prompts", "logs"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        if a.group:
            run_group(a.eval, out, key, findings, a.focus, a.model, a.budget * len(findings))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
                list(pool.map(lambda f: run_group(a.eval, out, key, [f], "", a.model, a.budget), findings))
    final = status(out, findings)
    print(json.dumps(final, indent=1, ensure_ascii=False))
    raise SystemExit(0 if final["next"] == "complete" else 2)


if __name__ == "__main__":
    main()
