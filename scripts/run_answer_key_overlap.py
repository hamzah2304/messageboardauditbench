#!/usr/bin/env python3
"""Answer-key overlap check: one sandboxed agent reads a whole QA'd answer key and removes double credit.

    python3 scripts/run_answer_key_overlap.py transluce OUT_DIR [--budget 30]
    python3 scripts/run_answer_key_overlap.py transluce OUT_DIR --prompt-only   # write the prompt, launch nothing
    python3 scripts/run_answer_key_overlap.py transluce OUT_DIR --merge         # store the result in the QA key

The second QA step, after scripts/run_answer_key_qa.py. The agent sees the key as the per-finding QA
leaves it: a key whose review is already applied is used as it is; otherwise every QA proposal is
accepted first (scripts/apply_answer_key_review.py with no hand decisions). The prompt is
sandbox/prompts/answer-key-overlap-v1.txt filled with the eval's data note, finding description and
overlap note (benchmarks/qa/modules/) and the whole key; the key with its evidence and QA verdicts is
also put in /work/answer-key.json (run_trial.sh WORK_FILES_DIR). It runs in the eval's QA container
and config (configs/answer-key-qa-<eval>.toml), with the read-only data mounted, on the subscription.
The agent writes /work/overlap.json; this saves it as OUT_DIR/result.json. --merge stores it in the QA
key file under "overlap" (ids O1, O2, ...); apply_answer_key_review.py applies the edits after review.
"""
import argparse
import copy
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qa = _load("run_answer_key_qa", ROOT / "scripts/run_answer_key_qa.py")
review = _load("apply_answer_key_review", ROOT / "scripts/apply_answer_key_review.py")
answer_key = qa.answer_key
TEMPLATE = ROOT / "sandbox/prompts/answer-key-overlap-v1.txt"


def post_qa_key(ev):
    """The key as the per-finding QA leaves it, without any earlier overlap result."""
    key = copy.deepcopy(answer_key.load(qa.qa_key_path(ev)))
    key.pop("overlap", None)
    if key.get("review"):
        return key
    key = review.apply(key, {"default": "accept_qa"}, "", overlap=False)
    key.pop("review")
    return key


def render_item(x, indent=""):
    lines = [f"{indent}{x['id']} — {x['claim']}"]
    if x.get("significance"):
        lines.append(f"{indent}  Significance: {x['significance']}")
    if x.get("detail"):
        lines.append(f"{indent}  Detail: {x['detail']}")
    if x.get("judge_notes"):
        lines.append(f"{indent}  Judge notes: {x['judge_notes']}")
    if (x.get("qa") or {}).get("reason"):
        lines.append(f"{indent}  Per-finding check: {x['qa']['reason']}")
    return lines


def render_key(key):
    out = []
    for f in key["findings"]:
        lines = render_item(f)
        fl = f.get("fields", {})
        for k in ("section", "kind", "tags", "episode", "behavior_dates"):
            if fl.get(k):
                v = ", ".join(fl[k]) if isinstance(fl[k], list) else fl[k]
                lines.insert(1, f"  {k.replace('_', ' ').capitalize()}: {v}")
        lines.append("  Subfindings:")
        for s in f["subfindings"]:
            lines += render_item(s, "    ")
        out.append("\n".join(lines))
    return "\n\n".join(out)


def build_prompt(ev, key):
    cfg = qa.EVALS[ev]
    mods = {m: (qa.MODULES / m).read_text().strip() for m in cfg["modules"]}
    fill = {
        "{{DATA_NOTE}}": next(v for k, v in mods.items() if k.startswith("data-note")),
        "{{FINDING_DESCRIPTION}}": "\n\n".join(v for k, v in mods.items() if k.startswith("finding-description")),
        "{{OVERLAP_NOTE}}": (qa.MODULES / cfg["overlap_note"]).read_text().strip(),
        "{{ANSWER_KEY}}": render_key(key),
    }
    text = TEMPLATE.read_text()
    for k, v in fill.items():
        text = text.replace(k, v)
    left = set(re.findall(r"\{\{[A-Z_]+\}\}", text)) - {"{{BUDGET_MIN}}"}
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    return text


def prepare(ev, out):
    key = post_qa_key(ev)
    (out / "work-files").mkdir(parents=True, exist_ok=True)
    answer_key.dump(key, out / "work-files/answer-key.json")
    # The agent's self-check (prompt step 5) applies its edits exactly as the review step will.
    for src in ("slopvestigator_bench/answer_key.py", "scripts/apply_answer_key_review.py",
                "scripts/check_overlap_edits.py"):
        shutil.copy(ROOT / src, out / "work-files" / Path(src).name)
    # The QA config, renamed so the run folder and metadata say this is the overlap check.
    cfg = (ROOT / "configs" / f"{qa.EVALS[ev]['config']}.toml").read_text()
    cfg = re.sub(r'^name = ".*"$', f'name = "answer-key-overlap-{ev}"', cfg, count=1, flags=re.M)
    cfg = re.sub(r'^prompt = ".*"$', 'prompt = "answer-key-overlap-v1"', cfg, count=1, flags=re.M)
    (out / "config.toml").write_text(cfg)
    (out / "prompt.txt").write_text(build_prompt(ev, key))
    return key


def launch(ev, out, model, budget):
    env = {**os.environ, "CONFIG": str(out / "config.toml"),
           "DATA_DIR": str(qa.EVALS[ev]["data"]), "PROMPT_FILE_OVERRIDE": str(out / "prompt.txt"),
           "BUDGET_MIN": str(budget), "WORK_FILES_DIR": str(out / "work-files")}
    log = out / "run.log"
    with log.open("w") as f:
        subprocess.run(["sg", "docker", "-c", f"sandbox/docker/run_trial.sh claude {model} 1"], cwd=ROOT,
                       env=env, stdout=f, stderr=subprocess.STDOUT)
    run = re.search(r"^run: (.+)$", log.read_text(), re.M)
    if not run:
        raise SystemExit(f"no run folder; see {log}")
    return Path(run.group(1))


def collect(out, key, run_dir):
    path = run_dir / "work/overlap.json"
    if not path.exists():
        raise SystemExit(f"no overlap.json in {run_dir}")
    result = json.loads(path.read_text())
    result["run_dir"] = str(run_dir)
    result["format_problems"] = answer_key.overlap_problems(result, key)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return result


def merge(ev, out, model, budget):
    result = json.loads((out / "result.json").read_text())
    if result["format_problems"]:
        raise SystemExit(f"not merged, format problems: {result['format_problems']}")
    path = qa.qa_key_path(ev)
    key = answer_key.load(path)
    overlaps = [{"id": f"O{i}", **{k: o.get(k, "") for k in ("items", "fact", "reason", "qa_override")}, "edits": o["edits"],
                 "after": o.get("after", {})}
                for i, o in enumerate(result["overlaps"], 1)]
    key["overlap"] = {
        "process": {"prompt": "sandbox/prompts/answer-key-overlap-v1.txt", "prompt_sha256": qa.sha(TEMPLATE),
                    "modules": {m: qa.sha(qa.MODULES / m) for m in [*qa.EVALS[ev]["modules"], qa.EVALS[ev]["overlap_note"]]},
                    "config": f"configs/{qa.EVALS[ev]['config']}.toml (renamed answer-key-overlap-{ev})",
                    "model": model, "budget_min": budget,
                    "key_sha256": qa.sha(out / "work-files/answer-key.json"),
                    "run": os.path.relpath(os.path.realpath(result["run_dir"]), qa.PRIMARY),
                    "merged": datetime.date.today().isoformat()},
        "applied": "",
        "overlaps": overlaps,
        "kept_separate": [{"items": k.get("items", []), "reason": k.get("reason", "")} for k in result.get("kept_separate", [])],
    }
    problems = answer_key.validate(key)
    if problems:
        raise SystemExit("\n".join(problems))
    answer_key.dump(key, path)
    print(f"stored {len(overlaps)} overlaps in {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval", choices=sorted(qa.EVALS))
    ap.add_argument("out", type=Path)
    ap.add_argument("--budget", type=int, default=30, help="minutes")
    ap.add_argument("--model", default=qa.configured_model("answer_key_qa"),
                    help="Claude Code model (default: configs/standard.toml [helpers.answer_key_qa])")
    ap.add_argument("--prompt-only", action="store_true", help="write the prompt and work files, launch nothing")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    out = a.out.resolve()
    if a.merge:
        return merge(a.eval, out, a.model, a.budget)
    if (out / "result.json").exists():
        sys.exit(f"{out / 'result.json'} exists; use a new OUT_DIR or --merge")
    out.mkdir(parents=True, exist_ok=True)
    key = prepare(a.eval, out)
    if a.prompt_only:
        print(f"wrote {out / 'prompt.txt'} and {out / 'work-files/answer-key.json'}")
        return
    result = collect(out, key, launch(a.eval, out, a.model, a.budget))
    print(json.dumps({"overlaps": len(result.get("overlaps", [])), "kept_separate": len(result.get("kept_separate", [])),
                      "format_problems": result["format_problems"]}, indent=1))


if __name__ == "__main__":
    main()
