#!/usr/bin/env python3
"""Run a benchmark at a chosen version.

    uv run python scripts/run_eval.py german-wiki-report -- -T agent=codex --model openai/gpt-5.6-sol
    uv run python scripts/run_eval.py german-wiki-report --version 9.0 -- -T agent=codex ...
    uv run python scripts/run_eval.py transluce-report --version 1.0 --task grade -- -T launch=...
    uv run python scripts/run_eval.py german-wiki-report --version 9.0 --dry-run -- ...

Every version is a git tag, <benchmark>-v<MAJOR.MINOR> (docs/benchmark-versions.md).
Without --version, or with the version this checkout already is, the eval runs here and
the task's own version guard (-T version=...) confirms it. Any other version runs from
its tag: the tag is checked out, detached, into .worktrees/version-<tag>/ (made once and
reused), with its own .venv and the primary checkout's data/, runs/, logs/ and .env
linked in, so it reads the same inputs and writes to the same archive. Older versions
predate the task rename and the version guard; the launcher uses the name that version
had and records the tag in the command it prints.

Everything after `--` is passed to `inspect eval`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from messageboard_audit_bench.benchmarks import BY_NAME, normalize_version  # noqa: E402

# The task each role had before the rename (versions before german-wiki-report-v10.0 /
# transluce-report-v1.0 only know these names).
LEGACY = {
    "german_wiki_report": "messageboard_audit_bench",
    "german_wiki_report_replay": "messageboard_audit_bench_replay",
    "german_wiki_report_continue": "messageboard_audit_bench_continue",
    "german_wiki_report_grade": "grade_reports",
    "transluce_report": "urlquery_audit_bench",
    "transluce_report_grade": "urlquery_grade_reports",
}
ROLES = {"run": "", "grade": "_grade", "replay": "_replay", "continue": "_continue"}


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def primary_root() -> Path:
    return Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def tags_for(name: str) -> list[str]:
    """Tagged versions, oldest first (6.1 before 10.0)."""
    tags = [t for t in git("tag", "--list", f"{name}-v*").splitlines() if t]
    return sorted(tags, key=lambda tag: tuple(int(n) for n in tag.rsplit("-v", 1)[1].split(".")))


def link_shared(primary: Path, worktree: Path) -> None:
    """Point the version checkout at the primary checkout's gitignored state."""
    for name in ("runs", "logs", ".env"):
        if (primary / name).exists() and not (worktree / name).exists():
            (worktree / name).symlink_to(primary / name)
    data = primary / "data"
    for entry in sorted(data.iterdir()) if data.is_dir() else []:
        target = worktree / "data" / entry.name
        if not target.exists() and not target.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(entry)
        elif entry.is_dir() and target.is_dir() and not target.is_symlink():
            # A tracked placeholder directory (e.g. data/verbatim/.gitkeep): link its files.
            for item in entry.iterdir():
                if not (target / item.name).exists():
                    (target / item.name).symlink_to(item)


def source_at(ref: str | None, path: str) -> str:
    """A file as the tag has it (or this checkout, for ref=None); empty if absent."""
    if ref is None:
        file = ROOT / path
        return file.read_text() if file.is_file() else ""
    result = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def task_name(ref: str | None, task: str) -> str:
    """The name `task` has at that version: renamed, or the pre-rename name."""
    source = source_at(ref, "messageboard_audit_bench/task.py") + source_at(ref, "messageboard_audit_bench/grading/task.py")
    return task if f'name="{task}"' in source else LEGACY[task]


def has_version_guard(ref: str | None) -> bool:
    return "def check_version" in source_at(ref, "messageboard_audit_bench/benchmarks.py")


def plan(name: str, version: str | None, role: str) -> dict:
    spec = BY_NAME[name]
    task = spec.task + ROLES[role]
    wanted = normalize_version(version) if version else spec.eval_version
    if wanted == spec.eval_version:
        return {"checkout": ROOT, "tag": None, "version": wanted, "task": task, "create": False}
    tag = f"{name}-v{wanted}"
    if tag not in tags_for(name):
        known = ", ".join(tags_for(name)) or "none"
        raise SystemExit(f"no tag {tag}; tagged versions of {name}: {known}")
    checkout = primary_root() / ".worktrees" / f"version-{tag}"
    return {"checkout": checkout, "tag": tag, "version": wanted, "task": task, "create": not checkout.exists()}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, extra = argv[:split], argv[split + 1:]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("benchmark", choices=sorted(BY_NAME))
    parser.add_argument("--version", help="MAJOR.MINOR (default: this checkout's version)")
    parser.add_argument("--task", choices=sorted(ROLES), default="run",
                        help="run fresh trials (default), grade, replay or continue")
    parser.add_argument("--dry-run", action="store_true", help="print what would run and stop")
    parser.add_argument("--list", action="store_true", help="list tagged versions and stop")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(tags_for(args.benchmark)) or f"no tagged versions of {args.benchmark}")
        return 0

    p = plan(args.benchmark, args.version, args.task)
    checkout = p["checkout"]
    if p["create"] and not args.dry_run:
        subprocess.run(["git", "worktree", "add", "--detach", str(checkout), p["tag"]], cwd=ROOT, check=True)
    if checkout.exists() and not args.dry_run and p["tag"]:
        link_shared(primary_root(), checkout)
        subprocess.run(["uv", "sync", "--quiet"], cwd=checkout, check=True)
    name = task_name(p["tag"], p["task"])
    command = ["uv", "run", "inspect", "eval", f"messageboard_audit_bench/{name}"]
    # Fresh-trial tasks guard their version; grading/replay tasks have no such option.
    if args.task == "run" and has_version_guard(p["tag"]):
        command += ["-T", f"version={p['version']}"]
    command += extra
    where = f"{checkout} (tag {p['tag']})" if p["tag"] else f"{checkout} (this checkout)"
    print(f"{args.benchmark} v{p['version']} in {where}:\n  {' '.join(command)}", flush=True)
    if args.dry_run:
        return 0
    return subprocess.run(command, cwd=checkout).returncode


if __name__ == "__main__":
    sys.exit(main())
