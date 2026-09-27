"""Join explicit pilot plans and all attempts, without copying evidence payloads.

No grading or model ranking. Startup failures remain alongside generated reports.
Codex client-declared model names are not promoted to provider-served identities.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from messageboard_audit_bench.dataset_manifest import file_sha256
from messageboard_audit_bench.runtime import repo_root
from messageboard_audit_bench.urlquery_data import primary_root


def summarize(experiments: list[Path], reports_root: Path) -> dict:
    shared_runs = (primary_root() / "runs/urlquery").resolve()
    reports_root = reports_root.resolve()
    exports = {row["run_dir"]: row for row in
               (json.loads(line) for line in (reports_root / "index.jsonl").read_text().splitlines())}
    plans, attempts, seen = [], [], set()
    for directory in experiments:
        directory = directory.resolve()
        if directory.parent != shared_runs:
            raise ValueError("experiment must be in the primary URLQuery run archive")
        plan_file = directory / "plan.json"
        plan = json.loads(plan_file.read_text())
        if plan.get("benchmark_id") != "urlquery" or plan["status"] not in ("finished", "stopped_with_unlaunched_trials"):
            raise ValueError("only finished URLQuery launch plans can be summarized")
        plans.append({key: plan.get(key) for key in (
            "experiment_id", "status", "code_revision", "config_sha256", "dataset_sha256",
            "matrix", "budget_minutes", "effort", "image", "image_build_args")}
                     | {"plan_path": str(plan_file), "plan_sha256": file_sha256(plan_file)})
        for result in json.loads((directory / "results.json").read_text()):
            run = Path(result["run_dir"]).resolve() if result.get("run_dir") else None
            if run and (run.parent != shared_runs or str(run) in seen):
                raise ValueError("wrong run archive or duplicate attempt")
            if run:
                seen.add(str(run))
            metadata = json.loads((run / "meta.json").read_text()) if run and (run / "meta.json").exists() else {}
            if metadata.get("benchmark_id") not in (None, "urlquery"):
                raise ValueError("cross-benchmark run")
            if metadata.get("dataset_sha256") not in (None, plan["dataset_sha256"]):
                raise ValueError("run input differs from plan")
            audit = json.loads((run / "audit.json").read_text()) if run and (run / "audit.json").exists() else {}
            row = {"experiment_id": plan["experiment_id"], **result,
                   "run_name": run.name if run else None,
                   "metadata_available": bool(metadata),
                   **{key: metadata.get(key) for key in (
                       "run_id", "dataset_sha256", "config_sha256", "prompt_sha256", "git_commit",
                       "image_id", "wall_seconds", "report_words", "report_length_compliant",
                       "report_finalization", "minimum_runtime_reached", "isolation", "model_fallback")},
                   "provider_served_model": audit.get("served_model"),
                   "observed_tool_calls": audit.get("tool_calls"),
                   "observed_tool_errors": audit.get("tool_error_count"),
                   "network_command_attempt_count": len(audit.get("tool_evidence", {}).get("network_command_attempts", []))
                       if audit.get("tool_evidence") is not None else None,
                   "proxy_evidence": audit.get("proxy_evidence"),
                   "cli_version": (run / "cli.version.txt").read_text().strip()
                       if run and (run / "cli.version.txt").exists() else None}
            observed = sorted({m["model"] for m in (audit.get("served_model") or {}).get("observed_served_models", [])
                               if not m["model"].startswith("<")})
            row["model_identity"] = {"observed_provider_models": observed,
                                     "mixed_model": len(observed) > 1 if observed else None,
                                     "single_served_model": observed[0] if len(observed) == 1 else None,
                                     "note": "All observed identities, not the legacy audit's first served-model field."}
            export = exports.get(run.name) if run else None
            if export:
                if not metadata.get("run_id") or metadata.get("dataset_sha256") != plan["dataset_sha256"]:
                    raise ValueError("exported run requires run_id and matching dataset_sha256 metadata")
                path = (reports_root / export["report"]).resolve()
                if reports_root not in path.parents or export.get("benchmark_id") != "urlquery":
                    raise ValueError("report export is outside this benchmark")
                if export.get("dataset_sha256") != plan["dataset_sha256"]:
                    raise ValueError("report export has the wrong dataset")
                if not (run / "report.md").exists() or file_sha256(path) != file_sha256(run / "report.md"):
                    raise ValueError("export differs from archived report")
                slug = re.sub(r"[^a-z0-9_]", "_", f"urlquery_{result['agent']}_{result['requested_model']}_r{result['replicate']}_{metadata['run_id'][:12]}")
                chain = (metadata.get("model_fallback") or {}).get("chain")
                label = " → ".join(chain) + " (fallback)" if chain else result["requested_model"]
                row.update(report_label=label, report_path=str(path), report_sha256=file_sha256(path),
                           preview_name=slug, report_url=f"http://localhost:8792/{slug}.html")
            attempts.append(row)
    hashes = {plan["dataset_sha256"] for plan in plans}
    if len(hashes) != 1:
        raise ValueError("the pilot index requires exactly one frozen dataset")
    return {"benchmark_id": "urlquery", "dataset_sha256": hashes.pop(), "grading": "none",
            "plans": plans, "attempts": attempts, "report_count": sum("report_path" in row for row in attempts),
            "summary_script_sha256": file_sha256(Path(__file__)), "interpretation": __doc__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    root = repo_root()
    data = summarize(args.experiment, root / "reports/urlquery")
    if args.render:
        for row in data["attempts"]:
            if "report_path" in row:
                subprocess.run([sys.executable, str(Path(__file__).with_name("build_preview.py")),
                                "--source", row["report_path"], "--output-name", row["preview_name"],
                                "--report-id", "urlquery-report-" + row["run_id"],
                                "--title", f"{row['report_label']} · run {row['replicate']} · unscored",
                                "--notice", f"{row['report_label']} · run {row['replicate']}. Original, unscored report; claims are not verified. Keep private: recorded credential values may appear."
                                + (" The requested Opus 5.5 switched to Opus 4.8 after a cyber-safety refusal; this is not a pure Opus 5.5 run." if row["model_fallback"] else "")],
                               cwd=root, check=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"attempts": len(data["attempts"]), "reports": data["report_count"]}))


if __name__ == "__main__":
    main()
