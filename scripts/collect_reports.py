#!/usr/bin/env python3
"""Gather every run's report into one folder, keyed by data variant, prompt and time budget.

    scripts/collect_reports.py [--out reports] [--runs runs] [--include-partial]

Layout:
    reports/<config>_p<prompt8>/<agent>_<model>_r<replicate>_<stamp>.md
    reports/<config>_p<prompt8>/CONDITIONS.json   prompt name, budget, data variant, effort, prompt hash
    reports/prompts/<prompt8>.txt                 the exact prompt those runs saw
    reports/index.jsonl                           one line per report with the run's metadata
<prompt8> is a hash of the rendered prompt, so editing a prompt or budget under the same
config name lands in a new folder instead of mixing with older runs.

Runs without a successful exit code are skipped unless --include-partial, in
which case their draft report from work/ is copied and flagged partial.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports")); ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--include-partial", action="store_true")
    a = ap.parse_args()
    out, runs = Path(a.out), Path(a.runs)
    rows = []
    for d in sorted(runs.iterdir()):
        meta_p = d / "meta.json"
        if not d.is_dir() or not meta_p.exists():
            continue
        meta = json.loads(meta_p.read_text())
        partial = meta.get("exit_code") != 0
        if partial and not a.include_partial:
            continue
        report = d / "report.md"
        if not report.exists():
            report = d / "work" / "report.md"
        if not report.exists():
            report = d / "final_message.md"
        if not report.exists():
            continue
        prompt_p = d / "work" / "prompt.txt"
        if not prompt_p.exists():
            prompt_p = d / "prompt.txt"
        prompt = prompt_p.read_text() if prompt_p.exists() else ""
        p8 = hashlib.sha256(prompt.encode()).hexdigest()[:8] if prompt else "noprompt"
        budget = meta.get("budget_min", 20)
        variant = meta.get("data_variant", "raw_stripped")
        stamp = d.name.split("_", 1)[0]
        model = str(meta["model"]).replace("/", "_")
        replicate = meta.get("replicate", meta.get("seed", 0))
        name = f"{meta['agent']}_{model}_r{replicate}_{stamp}{'_partial' if partial else ''}.md"
        config = meta.get("config", "legacy")
        dest = out / f"{config}_p{p8}" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, dest)
        (dest.parent / "CONDITIONS.json").write_text(json.dumps({
            "config": config, "prompt": meta.get("prompt", "legacy"), "prompt_id": p8, "budget_min": budget,
            "data_variant": variant, "effort": meta.get("effort"), "timeout": meta.get("timeout")}, indent=1))
        if prompt:
            (out / "prompts").mkdir(parents=True, exist_ok=True)
            (out / "prompts" / f"{p8}.txt").write_text(prompt)
        rows.append({"report": str(dest.relative_to(out)), "run_dir": d.name, "partial": partial, "config": config,
                     "prompt_name": meta.get("prompt", "legacy"), "prompt_id": p8, "budget_min": budget, "data_variant": variant,
                     "replicate": replicate,
                     **{k: meta.get(k) for k in ("agent", "model", "effort", "run_id", "timeout", "exit_code",
                                                  "wall_seconds", "cli_version", "prompt_sha256")},
                     "usage": meta.get("usage")})  # tokens incl. reasoning, cache, cost, api calls (see messageboard_audit/usage.py)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    by = {}
    for r in rows:
        by.setdefault((r["config"], r["prompt_id"]), []).append(r)
    for (c, p), rs in sorted(by.items()):
        print(f"{c}_p{p}: {len(rs)} reports  " + ", ".join(f"{r['agent']}:{r['model']}" for r in rs))
    print(f"{len(rows)} reports -> {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
