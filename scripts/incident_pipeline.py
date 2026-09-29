#!/usr/bin/env python3
"""Inspect, validate, scaffold, and operate benchmark incidents."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from messageboard_audit_bench.grading import core  # noqa: E402
from messageboard_audit_bench.incidents import (  # noqa: E402
    Incident,
    incident,
    incidents,
)
from messageboard_audit_bench.provenance import data_provenance  # noqa: E402
from messageboard_audit_bench.runtime import repo_root  # noqa: E402
from messageboard_audit_bench.task import incident_task  # noqa: E402

ROOT = repo_root()


class Check:
    def __init__(self, item: Incident) -> None:
        self.item = item
        self.problems: list[str] = []
        self.notes: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.problems.append(message)

    def path(self, value: str | None, label: str) -> Path | None:
        if not value:
            self.problems.append(f"{label} is not declared")
            return None
        path = ROOT / value
        self.require(path.is_file(), f"{label} is missing: {value}")
        return path


def _actual_data_dir(variant: str) -> Path:
    directory = (ROOT / "data" / variant).resolve()
    targets = {path.resolve().parent for path in directory.glob("*.jsonl") if path.is_symlink()}
    return targets.pop() if len(targets) == 1 else directory


def _check_jsonl(check: Check, variant: str) -> None:
    expected = set(check.item.corpus["files"])
    directory = _actual_data_dir(variant)
    actual = {path.name for path in directory.glob("*.jsonl")}
    check.require(actual == expected, f"data/{variant} files are {sorted(actual)}, expected {sorted(expected)}")
    for name in sorted(expected & actual):
        rows = 0
        try:
            with (directory / name).open() as stream:
                for rows, line in enumerate(stream, start=1):
                    if not line.strip():
                        raise ValueError(f"blank row {rows}")
                    json.loads(line)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            check.problems.append(f"data/{variant}/{name} is not valid JSONL: {exc}")
        else:
            check.require(rows > 0, f"data/{variant}/{name} is empty")
    provenance = data_provenance(variant, ROOT, directory)
    check.require(
        provenance["data_manifest_status"] == "matches_manifest",
        f"data/{variant} checksum status is {provenance['data_manifest_status']}",
    )


def validate(item: Incident) -> Check:
    check = Check(item)
    asset_paths = [
        check.path(item.grading["claims_file"], "claims file"),
        check.path(item.grading["answer_key"], "answer key"),
        check.path(item.grading["rubric_builder"], "rubric builder"),
    ]
    builder = item.corpus.get("builder")
    if builder:
        check.path(builder, "corpus builder")

    for config_name in item.configs:
        path = check.path(f"configs/{config_name}.toml", f"config {config_name}")
        if not path or not path.is_file():
            continue
        try:
            config = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            check.problems.append(f"config {config_name} is invalid TOML: {exc}")
            continue
        check.require(config.get("name") == config_name, f"config {config_name} has a different name")
        check.require(config.get("data_variant") in item.variants, f"config {config_name} selects an unregistered variant")
        if config_name == item.runtime["default_config"]:
            check.require(
                config.get("data_variant") == item.corpus["primary_variant"],
                f"default config {config_name} does not select the primary variant",
            )
            check.require(
                config.get("budget_min") == item.runtime["default_minutes"],
                f"config {config_name} budget and manifest default_minutes disagree",
            )

    try:
        claims = json.loads((ROOT / item.grading["claims_file"]).read_text())["claims"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        check.problems.append(f"cannot load claims: {exc}")
        claims = []
    ids = [claim.get("id") for claim in claims if isinstance(claim, dict)]
    check.require(bool(ids), "claims file has no claims")
    check.require(len(ids) == len(set(ids)), "claim IDs are not unique")

    finding_mode, summary_mode = item.rubrics
    for mode in (finding_mode, summary_mode):
        try:
            sets, templates = core.load_sheets(mode)
            for rubric_id in core.rubric_ids(mode):
                core.build_prompt(mode, rubric_id, "# TL;DR\nA test report.", templates)
        except Exception as exc:
            check.problems.append(f"rubric {mode} does not load: {type(exc).__name__}: {exc}")
            continue
        if mode == finding_mode:
            sheet_ids = [claim["id"] for sheet in sets for claim in sheet.get("claims", [])]
            check.require(sheet_ids == ids, f"rubric {mode} claim order differs from the claims file")

    for variant in item.variants:
        _check_jsonl(check, variant)

    try:
        task = incident_task(item.runtime["default_config"])
        metadata = task.dataset[0].metadata
        check.require(metadata["data_variant"] == item.corpus["primary_variant"], "task mounts the wrong data variant")
        check.require(metadata["budget_min"] == item.runtime["default_minutes"], "task ignores the incident's default budget")
        service = task.sandbox.config.services["default"]
        check.require(
            service.environment.get("MBAB_DATA_FILES") == ",".join(item.corpus["files"]),
            "sandbox expected-file declaration disagrees with the manifest",
        )
        check.require(len(task.scorer) == 4, "task does not attach finding, summary, process, and length scorers")
    except Exception as exc:
        check.problems.append(f"task construction failed: {type(exc).__name__}: {exc}")

    risks = item.review.get("validity_risks", [])
    requirements = item.review.get("publication_requirements", [])
    check.require(item.investigation_url.startswith("https://"), "investigation_url must be HTTPS")
    check.require(bool(item.review.get("interest")), "the incident's research interest is not recorded")
    for path in [item.manifest_path, *[path for path in asset_paths if path and path.is_file()]]:
        check.require("TODO" not in path.read_text(), f"unfinished TODO in {path.relative_to(ROOT)}")
    if item.maturity != "published":
        check.require(bool(risks), "a candidate incident must record validity risks")
        check.require(bool(requirements), "a candidate incident must record publication requirements")
        check.notes.extend(requirements)
    if item.results["status"] == "published":
        check.require(item.maturity == "published", "published results require published maturity")
        check.path(item.results.get("path"), "published results")
    else:
        check.require(item.maturity != "published", "published maturity requires published results")
        check.require(not item.results.get("path"), "unpublished results must not claim a publication path")
    return check


def docker_check(selected: list[Incident]) -> list[str]:
    problems: list[str] = []
    image = "mbab-incident-preflight"
    subprocess.run(
        ["docker", "build", "-q", "-t", image, "-f", "sandbox/docker/Dockerfile", "."],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    for item in selected:
        variant = item.corpus["primary_variant"]
        directory = _actual_data_dir(variant)
        command = [
            "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "1000:1000",
            "-e", f"MBAB_DATA_FILES={','.join(item.corpus['files'])}",
            "-v", f"{directory}:/work/data:ro", "-w", "/work", image,
            "python", "/sandbox/isolation_preflight.py",
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        try:
            record = json.loads(result.stdout)
        except json.JSONDecodeError:
            record = {}
        if result.returncode or not record.get("ok"):
            problems.append(f"{item.id}: Docker preflight failed: {result.stdout or result.stderr}")
        else:
            print(f"  ok    {item.id}: Docker isolation ({len(record['files'])} data files)")
    return problems


def cmd_list(_args: argparse.Namespace) -> int:
    print(f"{'incident':<12}{'maturity':<11}{'minutes':>8}  {'rubrics':<18}{'results':<10} title")
    for item in incidents().values():
        print(
            f"{item.id:<12}{item.maturity:<11}{item.runtime['default_minutes']:>8}  "
            f"{'+'.join(item.rubrics):<18}{item.results['status']:<10} {item.title}"
        )
    return 0


def _selected(names: list[str]) -> list[Incident]:
    return [incident(name) for name in names] if names else list(incidents().values())


def cmd_check(args: argparse.Namespace) -> int:
    selected = _selected(args.incident)
    failed = False
    for item in selected:
        result = validate(item)
        if result.problems:
            failed = True
            print(f"FAIL  {item.id}")
            for problem in result.problems:
                print(f"  - {problem}")
        else:
            print(f"ok    {item.id}: corpus, config, task, rubrics, and lifecycle metadata")
        if result.notes:
            print("      publication gates: " + "; ".join(result.notes))
    if args.docker:
        try:
            problems = docker_check(selected)
        except (OSError, subprocess.CalledProcessError) as exc:
            problems = [f"could not run Docker checks: {exc}"]
        for problem in problems:
            failed = True
            print(f"FAIL  {problem}")
    return 1 if failed else 0


def cmd_guide(args: argparse.Namespace) -> int:
    item = incident(args.incident)
    config = item.runtime["default_config"]
    minutes = item.runtime["default_minutes"]
    finding, summary = item.rubrics
    print(f"{item.title} [{item.maturity}]")
    print(f"Investigation: {item.investigation_url}")
    print(f"Why it is interesting: {item.review.get('interest', 'not recorded')}")
    print("\nValidity risks:")
    for risk in item.review.get("validity_risks", []):
        print(f"  - {risk}")
    print("\nReproduce and validate (no model calls):")
    print(f"  {item.corpus['build_command']}")
    print(f"  uv run python scripts/incident_pipeline.py check {item.id} --docker")
    print("\nUngraded pilot (paid report model; no judge call):")
    if item.id == "wiki":
        print("  uv run inspect eval messageboard_audit_bench/german_wiki_report \\")
        print(f"    -T agent=react -T config={config} -T time_limit_minutes={minutes} \\")
        print("    --model <provider/report-model> --no-score --epochs 1 --max-samples 1")
    else:
        # Drafts are not part of any Inspect eval yet; the shell runner takes any config.
        print(f"  CONFIG={config} BUDGET_MIN={minutes} sandbox/docker/run_trial.sh react <provider/report-model> 1")
    print("\nExport, manually review, then grade both registered modes:")
    print("  uv run python scripts/export_inspect_reports.py --logs logs --out reports/native --graded-inputs pilot")
    print(f"  uv run inspect eval messageboard_audit_bench/german_wiki_report_grade -T dir=<staged-folder> -T rubric={finding} --model-role grader=<provider/judge-model>")
    print(f"  uv run inspect eval messageboard_audit_bench/german_wiki_report_grade -T dir=<staged-folder> -T rubric={summary} --model-role grader=<provider/judge-model>")
    print("  uv run python scripts/export_grades.py logs/<finding-grade-run>.eval")
    print("  uv run python scripts/export_grades.py logs/<summary-grade-run>.eval")
    print(
        "  uv run python scripts/score_reports.py "
        f"--incident {item.id} benchmark/graded/judge_<judge> \\\n"
        f"    --json-out benchmark/results/{item.id}/scores.json \\\n"
        f"    --markdown-out benchmark/results/{item.id}/README.md  # {finding} + {summary}"
    )
    print("\nBefore publication:")
    for requirement in item.review.get("publication_requirements", []):
        print(f"  - {requirement}")
    return 0


def _slug(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise ValueError("incident ID must be a lowercase slug beginning with a letter")
    return value


def cmd_new(args: argparse.Namespace) -> int:
    incident_id = _slug(args.id)
    if args.minutes <= 0:
        raise ValueError("minutes must be a positive integer")
    prefix = re.sub(r"[^A-Z0-9]", "", args.prefix.upper())
    if not prefix:
        raise ValueError("prefix must contain a letter or digit")
    targets = [
        ROOT / "benchmark" / "incidents" / f"{incident_id}.json",
        ROOT / "configs" / f"{incident_id}.toml",
        ROOT / "benchmark" / "rubrics" / incident_id,
        ROOT / "scripts" / f"build_{incident_id.replace('-', '_')}_data.py",
    ]
    if any(path.exists() for path in targets):
        raise FileExistsError(f"refusing to overwrite existing scaffold: {targets}")
    rubric_dir = targets[2]
    rubric_dir.mkdir(parents=True)
    builder = f"scripts/build_{incident_id.replace('-', '_')}_data.py"
    finding, summary = incident_id.replace("-", ""), f"{incident_id.replace('-', '')}tldrh"
    answer_key = f"benchmark/rubrics/{incident_id}/{incident_id}_report.txt"
    claims_file = f"benchmark/rubrics/{incident_id}/claims_{incident_id.replace('-', '_')}.json"
    rubric_builder = f"benchmark/rubrics/build_rubrics_{incident_id.replace('-', '_')}.py"
    manifest = {
        "schema": 1,
        "id": incident_id,
        "title": args.title,
        "maturity": "candidate",
        "investigation_url": args.investigation_url,
        "corpus": {
            "primary_variant": incident_id,
            "variants": [incident_id],
            "files": [args.data_file],
            "builder": builder,
            "build_command": f"uv run python {builder}",
            "blindness": "TODO: state exactly what was removed and retained.",
            "limitations": ["TODO: document corpus coverage and selection limits."],
        },
        "runtime": {"configs": [incident_id], "default_config": incident_id, "default_minutes": args.minutes},
        "grading": {
            "finding_mode": finding,
            "summary_mode": summary,
            "claims_file": claims_file,
            "answer_key": answer_key,
            "rubric_builder": rubric_builder,
            "modes": {
                finding: {"sheet": finding, "sheet_set": finding, "n_sheets": 1, "lo": 0.0, "hi": 1.0, "prefix": prefix, "numbered": True, "tldr_only": False, "directory": incident_id, "answer_key": f"rubrics/{incident_id}/{incident_id}_report.txt"},
                summary: {"sheet": summary, "sheet_set": summary, "n_sheets": 1, "lo": 0.0, "hi": 1.0, "prefix": f"{prefix}TLDRH", "numbered": False, "tldr_only": True, "directory": incident_id, "answer_key": f"rubrics/{incident_id}/{incident_id}_report.txt"},
            },
        },
        "review": {
            "interest": "TODO: explain what capability or transfer question this incident tests.",
            "validity_risks": ["TODO: contamination, selection, redaction, and judge-independence review."],
            "publication_requirements": ["Manual derivability review", "Independent pilot", "Results audit"],
        },
        "results": {"status": "none", "path": None},
    }
    targets[0].write_text(json.dumps(manifest, indent=2) + "\n")
    targets[1].write_text(
        f'name = "{incident_id}"\nprompt = "blind-v2"\nbudget_min = {args.minutes}\n'
        f'timeout_min = {args.minutes + 5}\ndata_variant = "{incident_id}"\neffort = "xhigh"\n'
        'claude_disallowed_tools = ["WebFetch", "WebSearch", "Task", "Skill", "ToolSearch", "RemoteTrigger", "SendMessage", "ListAgents", "Workflow", "CronCreate", "CronDelete", "CronList", "ScheduleWakeup", "EnterWorktree"]\n\n'
        "report_min_words = 2500\nreport_max_words = 3000\nreport_accept_min_words = 0\nreport_accept_max_words = 3200\n"
    )
    (rubric_dir / f"claims_{incident_id.replace('-', '_')}.json").write_text('{\n  "claims": []\n}\n')
    (rubric_dir / f"{incident_id}_report.txt").write_text("TODO: corpus-scoped human answer key.\n")
    (rubric_dir / "README.md").write_text(f"# {args.title}\n\nCandidate incident. Follow `docs/adding-an-incident.md`.\n")
    targets[3].write_text(
        '#!/usr/bin/env python3\n"""Build the stripped, deterministic incident corpus."""\n'
        'raise SystemExit("TODO: implement source verification, stripping, and deterministic JSONL output")\n'
    )
    (ROOT / rubric_builder).write_text(
        '#!/usr/bin/env python3\n"""Generate finding and summary sheets for this incident."""\n'
        'raise SystemExit("TODO: generate sheets from the reviewed claims and shared 0-1 scale")\n'
    )
    with (ROOT / ".gitignore").open("a") as stream:
        stream.write(f"\n/data/{incident_id}\n")
    print(f"created candidate incident {incident_id}; fill the TODOs, build data and run:")
    print(f"  uv run python scripts/incident_pipeline.py check {incident_id} --docker")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    list_parser = commands.add_parser("list", help="show lifecycle state for every incident")
    list_parser.set_defaults(func=cmd_list)
    check_parser = commands.add_parser("check", help="validate one or every incident without model calls")
    check_parser.add_argument("incident", nargs="*")
    check_parser.add_argument("--docker", action="store_true", help="also build the image and test isolation")
    check_parser.set_defaults(func=cmd_check)
    guide_parser = commands.add_parser("guide", help="print exact build, run, export, and score commands")
    guide_parser.add_argument("incident")
    guide_parser.set_defaults(func=cmd_guide)
    new_parser = commands.add_parser("new", help="create a candidate incident scaffold")
    new_parser.add_argument("id")
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--investigation-url", required=True)
    new_parser.add_argument("--data-file", default="records.jsonl")
    new_parser.add_argument("--prefix", required=True, help="short uppercase rubric ID prefix")
    new_parser.add_argument("--minutes", type=int, default=20)
    new_parser.set_defaults(func=cmd_new)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
