"""The benchmark registry: which benchmarks exist, and what each one owns.

Both benchmarks share one harness (configs, prompt rendering, the Docker runner,
the Inspect solvers and the grading plumbing). What differs is recorded here:

* ``german-wiki-report`` (Inspect task ``german_wiki_report``; storage id
  ``messageboard``) — the original MessageBoardAuditBench on the collusion.wiki
  incident. Its corpus, configs and rubrics are the ``wiki`` incident manifest under
  ``benchmark/incidents/``, and its data lives in ``data/<variant>/``. The other
  manifests there (Mythos 5, RubyHack) are drafts for future evals, not part of it.
* ``transluce-report`` (Inspect task ``transluce_report``; storage id ``urlquery``) —
  the Transluce urlquery.net agent-activity audit. Its manifest is
  ``benchmarks/urlquery/benchmark.json``: one frozen, hash-pinned snapshot under the
  primary checkout's ``data/urlquery/``, its trial configs, and its per-finding rubric.

The storage ids predate the public names and stay as they are: they are written into
every run record, config and grade file.

Each benchmark has its own version, ``MAJOR.MINOR``: bump MAJOR when a change alters
what the agent sees, what it can do, whether its report is accepted, or how the default
grading scores it (results stop being comparable); bump MINOR for a compatible change.
Every version is a git tag, ``<name>-v<version>``, and ``scripts/run_eval.py --version``
runs any tagged version. The history is in docs/benchmark-versions.md.
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
    id: str              # storage id, recorded in run records and configs
    name: str            # public name; version tags are <name>-v<version>
    title: str
    task: str            # the Inspect task that runs fresh trials
    legacy_task: str     # its name before the rename, kept as an alias
    eval_version: str    # MAJOR.MINOR; see docs/benchmark-versions.md
    evaluator_root: str  # evaluator-only material, never mounted into a trial
    run_root: str
    report_root: str
    log_root: str


SPECS = {
    "messageboard": BenchmarkSpec(
        "messageboard", "german-wiki-report", "German wiki report", "german_wiki_report",
        "messageboard_audit_bench", "10.0", "benchmark", "runs", "reports", "logs",
    ),
    "urlquery": BenchmarkSpec(
        "urlquery", "transluce-report", "Transluce report", "transluce_report",
        "urlquery_audit_bench", "1.0", "benchmarks/urlquery", "runs/urlquery",
        "reports/urlquery", "logs/urlquery",
    ),
}
BY_NAME = {spec.name: spec for spec in SPECS.values()}
# The one incident the German wiki report runs. Other incident manifests are drafts.
WIKI_INCIDENT = "wiki"
# Labels used before dotted versions: <major>-<letter>, letter A = minor 0.
_LEGACY_VERSION = re.compile(r"(\d+)-([A-Z])")


def normalize_version(value: str | int | float) -> str:
    """'10', '10.0', 'v10.0' and the old '10-A' all mean '10.0'; '6-B' means '6.1'."""
    text = str(value).strip().removeprefix("v")
    if legacy := _LEGACY_VERSION.fullmatch(text):
        return f"{legacy.group(1)}.{ord(legacy.group(2)) - ord('A')}"
    if re.fullmatch(r"\d+", text):
        return f"{text}.0"
    if re.fullmatch(r"\d+\.\d+", text):
        return text
    raise ValueError(f"invalid version {value!r}; use MAJOR.MINOR, e.g. 10.0")


def version_tag(benchmark_id: str, version: str) -> str:
    return f"{benchmark_spec(benchmark_id).name}-v{normalize_version(version)}"


def check_version(benchmark_id: str, requested: str | None) -> None:
    """Refuse to run a different version than the one checked out."""
    if requested is None:
        return
    spec = benchmark_spec(benchmark_id)
    wanted = normalize_version(requested)
    if wanted != spec.eval_version:
        raise ValueError(
            f"this checkout is {spec.name} v{spec.eval_version}, not v{wanted}. Run that version "
            f"from its tag with: uv run python scripts/run_eval.py {spec.name} --version {wanted} -- <inspect args>"
        )


# Codex features the URLQuery trials disable, on both backends (the subscription
# runner writes the same list into the trial's config.toml; a test keeps them equal).
URLQUERY_CODEX_FEATURES_OFF = (
    "multi_agent", "multi_agent_v2", "apps", "plugins", "remote_plugin", "browser_use",
    "browser_use_external", "computer_use", "in_app_browser", "in_app_local_automation",
)


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
    contexts = grading["default_article_context"]
    if set(contexts) != {"anthropic", "openrouter"} or set(contexts.values()) - {"full", "omitted"}:
        raise ValueError(f"{path}: default_article_context maps anthropic/openrouter to full or omitted")
    return data


def config_names(benchmark_id: str) -> tuple[str, ...]:
    """The configs a benchmark's Inspect task accepts as fresh-trial conditions."""
    if benchmark_id == "messageboard":
        from messageboard_audit_bench.incidents import incident

        return incident(WIKI_INCIDENT).configs
    benchmark_spec(benchmark_id)
    return tuple(urlquery_manifest()["runtime"]["configs"])


def draft_config_names() -> tuple[str, ...]:
    """Configs of the draft incidents (Mythos 5, RubyHack): runnable for validation only."""
    from messageboard_audit_bench.incidents import incidents

    return tuple(c for item in incidents().values() if item.id != WIKI_INCIDENT for c in item.configs)


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
