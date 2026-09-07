#!/usr/bin/env python3
"""Gather every run's report into one folder, keyed by data variant, prompt and time budget.

    scripts/collect_reports.py [--out reports] [--runs runs] [--include-partial] [--include-rejected]

Layout:
    reports/<condition>_<variant>_<effort>_p<prompt8>/<agent>_<model>_r<replicate>_<stamp>.md
    reports/<condition>_<variant>_<effort>_p<prompt8>/CONDITIONS.json
    reports/prompts/<prompt8>.txt                 the exact prompt those runs saw
    reports/index.jsonl                           one line per report with the run's metadata
<prompt8> is a hash of the rendered prompt, so editing a prompt or budget under the same
condition name lands in a new folder instead of mixing with older runs. The
variant and effort are also part of the folder key.

Runs without a successful exit code are skipped unless --include-partial, in
which case their draft report from work/ is copied and flagged partial. Reports
outside their saved acceptance bounds are skipped unless --include-rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from messageboard_audit_bench.report_length import (  # noqa: E402
    acceptance_limits,
    limits,
    measure,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports"))
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--include-partial", action="store_true")
    ap.add_argument("--include-rejected", action="store_true")
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
            continue
        report_text = report.read_text(errors="replace")
        length = measure(
            report_text,
            *limits(meta),
            exists=True,
            acceptance=acceptance_limits(meta),
        )
        rejected = length["report_length_compliant"] is False
        if rejected and not a.include_rejected:
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
        served = meta.get("model_served")  # Claude Code switched model after a safeguard refusal
        tag = f"_served-{str(served).replace('/', '_')}" if served else ""
        name = f"{meta['agent']}_{model}_r{replicate}_{stamp}{tag}{'_partial' if partial else ''}.md"
        config = meta.get("config", "legacy")
        condition = meta.get("condition", meta.get("prompt", config))
        effort = meta.get("effort") or "unknown"
        dest = out / f"{condition}_{variant}_{effort}_p{p8}" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, dest)
        conditions = {
            "condition": condition,
            "prompt": meta.get("prompt", "legacy"),
            "prompt_id": p8,
            "budget_min": budget,
            "data_variant": variant,
            "effort": effort,
        }
        conditions_path = dest.parent / "CONDITIONS.json"
        if conditions_path.exists() and json.loads(conditions_path.read_text()) != conditions:
            raise RuntimeError(f"inconsistent conditions in {dest.parent}")
        conditions_path.write_text(json.dumps(conditions, indent=1))
        if prompt:
            (out / "prompts").mkdir(parents=True, exist_ok=True)
            (out / "prompts" / f"{p8}.txt").write_text(prompt)
        usage = meta.get("usage")
        if usage is not None:
            usage = dict(usage)
            usage.setdefault("usage_schema", 1)
        rows.append({"report": str(dest.relative_to(out)), "run_dir": d.name, "partial": partial, "condition": condition, "config": config,
                     "prompt_name": meta.get("prompt", "legacy"), "prompt_id": p8, "budget_min": budget, "data_variant": variant,
                     "replicate": replicate,
                     **{k: meta.get(k) for k in ("agent", "model", "effort", "run_id", "timeout", "exit_code",
                                                  "wall_seconds", "cli_version", "prompt_sha256")},
                     "model_served": served, "model_fallback": meta.get("model_fallback"),
                     "report_rejected": rejected,
                     **length,
                     "usage": usage})  # tokens incl. reasoning, cache, cost, api calls (see messageboard_audit_bench/usage.py)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    by = {}
    for r in rows:
        key = (r["condition"], r["data_variant"], r["effort"] or "unknown", r["prompt_id"])
        by.setdefault(key, []).append(r)
    for (condition, variant, effort, prompt_id), rs in sorted(by.items()):
        print(
            f"{condition}_{variant}_{effort}_p{prompt_id}: {len(rs)} reports  "
            + ", ".join(f"{r['agent']}:{r['model']}" for r in rs)
        )
    print(f"{len(rows)} reports -> {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
