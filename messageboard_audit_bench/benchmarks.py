"""The benchmark registry: which benchmarks exist, and what each one owns.

Both benchmarks share one harness (configs, prompts rendering, the Docker runner,
the Inspect solvers and the grading plumbing). What differs is recorded here:

* ``messageboard`` — the original MessageBoardAuditBench. Its corpora, configs
  and rubrics are the incident manifests under ``benchmark/incidents/``
  (`messageboard_audit_bench.incidents`), and its data lives in ``data/<variant>/``.
* ``urlquery`` — the Transluce urlquery.net agent-activity audit. Its manifest is
  ``benchmarks/urlquery/benchmark.json``: one frozen, hash-pinned snapshot under the
  primary checkout's ``data/urlquery/``, its trial configs, and its per-finding rubric.

Each benchmark is its own Inspect task with its own version (``eval_version``);
bump it when a change alters what that benchmark's agent sees, what it can do,
whether its report is accepted, or how its default grading scores it. The
history is in docs/benchmark-versions.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from messageboard_audit_bench.dataset_manifest import file_sha256, validate_dataset
from messageboard_audit_bench.runtime import repo_root


@dataclass(frozen=True)
class BenchmarkSpec:
    id: str
    title: str
    task: str            # the Inspect task that runs fresh trials
    eval_version: str    # Inspect task version; see docs/benchmark-versions.md
    evaluator_root: str  # evaluator-only material, never mounted into a trial
    run_root: str
    report_root: str
    log_root: str


SPECS = {
    "messageboard": BenchmarkSpec(
        "messageboard", "MessageBoardAuditBench", "messageboard_audit_bench", "10-A",
        "benchmark", "runs", "reports", "logs",
    ),
    "urlquery": BenchmarkSpec(
        "urlquery", "URLQuery agent-activity audit", "urlquery_audit_bench", "1-A",
        "benchmarks/urlquery", "runs/urlquery", "reports/urlquery", "logs/urlquery",
    ),
}


def benchmark_spec(benchmark_id: str) -> BenchmarkSpec:
    try:
        return SPECS[benchmark_id]
    except KeyError as exc:
        raise ValueError(f"unknown benchmark: {benchmark_id!r}") from exc


def primary_root() -> Path:
    """The primary checkout, which alone holds the gitignored data/ and runs/."""
    common = subprocess.check_output(
        ["git", "-C", str(repo_root()), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
    ).strip()
    return Path(common).parent


@lru_cache(maxsize=1)
def urlquery_manifest() -> dict[str, Any]:
    """benchmarks/urlquery/benchmark.json, validated."""
    path = repo_root() / SPECS["urlquery"].evaluator_root / "benchmark.json"
    data = json.loads(path.read_text())
    if data.get("schema") != 1 or data.get("id") != "urlquery":
        raise ValueError(f"{path}: expected schema 1 manifest for urlquery")
    dataset, runtime, grading = data["dataset"], data["runtime"], data["grading"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", dataset["snapshot"]):
        raise ValueError(f"{path}: invalid dataset snapshot")
    if not re.fullmatch(r"[0-9a-f]{64}", dataset["sha256"]):
        raise ValueError(f"{path}: dataset sha256 must be 64 hex characters")
    if runtime["default_config"] not in runtime["configs"]:
        raise ValueError(f"{path}: default config is not listed in configs")
    if grading["default_article_context"] not in {"full", "omitted"}:
        raise ValueError(f"{path}: default_article_context must be full or omitted")
    return data


def config_names(benchmark_id: str) -> tuple[str, ...]:
    """The configs a benchmark's Inspect task accepts as fresh-trial conditions."""
    if benchmark_id == "messageboard":
        from messageboard_audit_bench.incidents import config_names as incident_configs

        return incident_configs()
    benchmark_spec(benchmark_id)
    return tuple(urlquery_manifest()["runtime"]["configs"])


def default_config(benchmark_id: str) -> str:
    if benchmark_id == "messageboard":
        return "blind"
    benchmark_spec(benchmark_id)
    return urlquery_manifest()["runtime"]["default_config"]


def urlquery_data_variant() -> str:
    return f"urlquery/{urlquery_manifest()['dataset']['snapshot']}"


def urlquery_dataset_dir() -> Path:
    return primary_root() / "data" / urlquery_data_variant()


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
    return {"benchmark_id": spec.id, "benchmark_version": spec.eval_version,
            "dataset_sha256": manifest["dataset_sha256"],
            "run_root": spec.run_root, "report_root": spec.report_root, "log_root": spec.log_root,
            "dataset_version": manifest["snapshot"],
            "rubric_version": urlquery_manifest()["grading"]["rubric"],
            "scoring_status": "ungraded", "data_manifest_status": "verified",
            "data_manifest_sha256": file_sha256(data / "manifest.json")}


def check_resume(parent: dict, benchmark_id: str, dataset_sha256: str | None) -> None:
    if parent.get("benchmark_id", "messageboard") != benchmark_id:
        raise ValueError("cross-benchmark resume rejected")
    if benchmark_id == "urlquery":
        if not dataset_sha256 or parent.get("dataset_sha256") != dataset_sha256:
            raise ValueError("resume dataset mismatch")
        raise ValueError("URLQuery continuation is not yet supported; launch a fresh trial")


def reject_foreign_grading(benchmark_id: str, grader: str = "messageboard") -> None:
    """Each benchmark is graded only by its own rubric."""
    benchmark_spec(benchmark_id)
    if benchmark_id != grader:
        raise ValueError(
            f"cross-benchmark grading rejected: {benchmark_id} reports are graded by "
            f"{SPECS[benchmark_id].task}'s own rubric, not {grader}'s"
        )


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
