"""Explicit benchmark namespaces; the original benchmark keeps its paths."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from messageboard_audit_bench.dataset_manifest import file_sha256, validate_dataset


@dataclass(frozen=True)
class BenchmarkSpec:
    id: str
    evaluator_root: str
    run_root: str
    report_root: str
    log_root: str
    scoring_ready: bool


SPECS = {
    "messageboard": BenchmarkSpec("messageboard", "benchmark", "runs", "reports", "logs", True),
    "urlquery": BenchmarkSpec("urlquery", "benchmarks/urlquery", "runs/urlquery", "reports/urlquery", "logs/urlquery", False),
}


def benchmark_spec(benchmark_id: str) -> BenchmarkSpec:
    try:
        return SPECS[benchmark_id]
    except KeyError as exc:
        raise ValueError(f"unknown benchmark: {benchmark_id!r}") from exc


def validate_trial_data(benchmark_id: str, data: Path, expected_sha256: str | None = None) -> dict:
    spec = benchmark_spec(benchmark_id)
    if spec.id != "urlquery":
        raise ValueError("manifest trial validation currently applies to urlquery only")
    manifest = validate_dataset(data, benchmark_id=spec.id, expected_sha256=expected_sha256)
    if (not manifest.get("acquisition_closed") or
            manifest["downloaded_count"] + manifest["unavailable_scan_count"] != manifest["catalog_count"]):
        raise ValueError("pilot requires settled acquisition; no silently unfinished corpus")
    if data.name != manifest["snapshot"]:
        raise ValueError("dataset version/path mismatch")
    return {"benchmark_id": spec.id, "dataset_sha256": manifest["dataset_sha256"],
            "run_root": spec.run_root, "report_root": spec.report_root, "log_root": spec.log_root,
            "dataset_version": manifest["snapshot"], "rubric_version": None,
            "scoring_status": "unscored_pending_manual_rubric", "data_manifest_status": "verified",
            "data_manifest_sha256": file_sha256(data / "manifest.json")}


def check_resume(parent: dict, benchmark_id: str, dataset_sha256: str | None) -> None:
    if parent.get("benchmark_id", "messageboard") != benchmark_id:
        raise ValueError("cross-benchmark resume rejected")
    if benchmark_id == "urlquery":
        if not dataset_sha256 or parent.get("dataset_sha256") != dataset_sha256:
            raise ValueError("resume dataset mismatch")
        raise ValueError("URLQuery continuation is not yet supported; launch a fresh trial")


def require_scoring_ready(benchmark_id: str):
    if not benchmark_spec(benchmark_id).scoring_ready:
        raise ValueError("URLQuery has no approved rubric; original benchmark grading is forbidden")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark_id", choices=SPECS)
    parser.add_argument("data", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.data.name):
        raise ValueError("invalid dataset version")
    metadata = validate_trial_data(args.benchmark_id, args.data, args.expected_sha256)
    if args.resume:
        check_resume(json.loads((args.resume / "meta.json").read_text()), args.benchmark_id, metadata["dataset_sha256"])
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
