#!/usr/bin/env python3
"""Gather every run's report into one folder, keyed by data variant, prompt and time budget.

    scripts/collect_reports.py [--out reports] [--runs runs] [--include-partial]

Layout:
    reports/<variant>/p<prompt8>_b<budget>/<agent>_<model>_s<seed>_<stamp>.md
    reports/prompts/<prompt8>.txt         the exact prompt those runs saw
    reports/index.jsonl                   one line per report with the run's metadata

Runs without an exit code (killed mid-way) are skipped unless --include-partial, in
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
        partial = "exit_code" not in meta
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
        name = f"{meta['agent']}_{model}_s{meta.get('seed', 0)}_{stamp}{'_partial' if partial else ''}.md"
        dest = out / variant / f"p{p8}_b{budget}" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, dest)
        if prompt:
            (out / "prompts").mkdir(parents=True, exist_ok=True)
            (out / "prompts" / f"{p8}.txt").write_text(prompt)
        rows.append({"report": str(dest.relative_to(out)), "run_dir": d.name, "partial": partial,
                     "prompt_id": p8, "budget_min": budget, "data_variant": variant,
                     **{k: meta.get(k) for k in ("agent", "model", "effort", "seed", "timeout", "exit_code",
                                                  "wall_seconds", "cli_version", "prompt_sha256")}})
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    by = {}
    for r in rows:
        by.setdefault((r["data_variant"], r["prompt_id"], r["budget_min"]), []).append(r)
    for (v, p, b), rs in sorted(by.items()):
        print(f"{v}/p{p}_b{b}: {len(rs)} reports  " + ", ".join(f"{r['agent']}:{r['model']}" for r in rs))
    print(f"{len(rows)} reports -> {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
