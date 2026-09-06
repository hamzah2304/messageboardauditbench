#!/usr/bin/env python3
"""Redo run_trial.sh's post-run bookkeeping for a trial whose runner died after the agent finished.

    scripts/finalize_trial.py <run_dir> [<run_dir> ...]

Reproduces the tail of sandbox/docker/run_trial.sh from what is on disk: copies work/report.md
(and final_message.md) to the run root, summarizes usage (messageboard_audit.usage), and writes
exit_code / wall_seconds / model_fallback / model_served / model_refusal / usage into meta.json.
The container's exit code is gone, so it is inferred: 1 if the transcript's result says
is_error, 5 on a refusal that ended the run, else 0. wall_seconds is transcript mtime - start.
Runs that already have exit_code in meta.json are left alone unless --force.
"""
from __future__ import annotations
import datetime, json, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def finalize(run: pathlib.Path, force: bool = False) -> None:
    meta_p = run / "meta.json"; m = json.loads(meta_p.read_text())
    if "exit_code" in m and not force:
        print(f"{run.name}: already finalized (exit {m['exit_code']})"); return
    tr = run / "transcript.jsonl"
    if not tr.exists(): print(f"{run.name}: no transcript, skipped"); return
    for f in ("report.md", "final_message.md"):
        if (run / "work" / f).exists() and not (run / f).exists(): shutil.copyfile(run / "work" / f, run / f)
    subprocess.run([sys.executable, "-m", "messageboard_audit.usage", str(run), "--quiet"],
                   env={**os.environ, "PYTHONPATH": str(ROOT)}, check=False)
    lines = tr.read_text().splitlines()
    last = {}
    for l in reversed(lines):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("type") == "result": last = r; break
    rc = 1 if last.get("is_error") else 0
    started = datetime.datetime.strptime(m["started"], "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
    secs = int(tr.stat().st_mtime - started.timestamp())
    m.update(exit_code=rc, wall_seconds=secs, report_exists=(run / "report.md").exists(), finalized_by="scripts/finalize_trial.py")
    fb = [json.loads(l) for l in lines if '"model_refusal_fallback"' in l]
    if fb:
        m["model_fallback"] = {"fallback_model": fb[-1].get("fallback_model"), "trigger": fb[0].get("trigger"),
                               "category": fb[0].get("api_refusal_category"), "events": len(fb),
                               "chain": [m["model"]] + [e.get("fallback_model") for e in fb]}
        m["model_served"] = fb[-1].get("fallback_model")
    rf = [l for l in lines if '"native_finish_reason": "refusal"' in l or '"finish_reason": "content_filter"' in l or '"stop_reason":"refusal"' in l]
    if rf:
        m["model_refusal"] = {"events": len(rf)}
        if rc == 0: rc = 5; m["exit_code"] = rc
    u = json.loads((run / "usage.json").read_text()) if (run / "usage.json").exists() else {}
    m["usage"] = {k: u.get(k) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens",
                  "cost_usd", "api_calls", "tool_calls", "api_retries", "api_errors", "peak_context_tokens", "terminal_reason", "is_error", "usage_source")}
    meta_p.write_text(json.dumps(m, indent=1))
    print(f"{run.name}: exit {rc}, wall {secs}s, report={m['report_exists']}, served={m.get('model_served', m['model'])}")

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    for a in args: finalize(pathlib.Path(a), force="--force" in sys.argv)
