"""Host-side, non-secret provenance for reproducible benchmark runs."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tomllib
from pathlib import Path

from messageboard_audit_bench.runtime import repo_root


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git(root: Path, *args: str) -> str | None:
    try:
        value = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return value or None


def _declared_versions(dockerfile: Path) -> dict[str, str | None]:
    try:
        text = dockerfile.read_text()
    except OSError:
        return {"codex": None, "claude": None}
    return {
        "codex": (
            match.group(1)
            if (match := re.search(r"(?:ARG CODEX_VERSION=|rust-v)([0-9.]+)", text))
            else None
        ),
        "claude": (
            match.group(1)
            if (match := re.search(r"(?:ARG CLAUDE_VERSION=|base/)([0-9.]+)", text))
            else None
        ),
    }



DATA_MANIFEST = "data/SHA256SUMS.variants"


def _resolve_data_dir(root: Path, data_variant: str) -> Path:
    """The directory actually mounted, mirroring the sandbox's symlink handling.

    A task worktree holds per-file symlinks into the primary checkout, and a bind
    mount cannot follow them, so the sandbox mounts the directory they resolve to.
    Recording that same path is what makes the digests below comparable across
    worktrees.
    """
    data_dir = (root / "data" / data_variant).resolve()
    targets = {p.resolve().parent for p in data_dir.glob("*.jsonl") if p.is_symlink()}
    return targets.pop() if len(targets) == 1 else data_dir


def _manifest_digests(root: Path, data_variant: str) -> dict[str, str]:
    """The committed digests for one variant, keyed by file name."""
    prefix = f"data/{data_variant}/"
    try:
        lines = (root / DATA_MANIFEST).read_text().splitlines()
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in lines:
        digest, _, path = line.partition("  ")
        if path.startswith(prefix) and digest:
            out[path[len(prefix) :]] = digest
    return out


def data_provenance(
    data_variant: str, root: Path | None = None, data_dir: Path | None = None
) -> dict:
    """Hash the dataset a run actually mounted and check it against the manifest.

    The code beside a run is captured by git; ``data/`` is a gitignored build
    output that can be older than the code that built it, so a run record without
    these digests cannot establish which build of a derived variant it consumed.
    """
    root = root or repo_root()
    # The subscription runner resolves and may override the directory itself.
    data_dir = Path(data_dir) if data_dir else _resolve_data_dir(root, data_variant)
    files = sorted(data_dir.glob("*.jsonl"))
    digests = {path.name: _sha256(path) for path in files}
    expected = _manifest_digests(root, data_variant)

    if not digests:
        status = "absent_not_built"
    elif not expected:
        status = "no_manifest_entry"
    else:
        mismatched = sorted(
            name
            for name, digest in digests.items()
            if name in expected and digest != expected[name]
        )
        missing = sorted(set(expected) - set(digests))
        status = "matches_manifest" if not (mismatched or missing) else "differs_from_manifest"

    record = {
        "data_variant": data_variant,
        "data_dir": str(data_dir),
        "data_files_sha256": digests,
        "data_manifest_status": status,
    }
    if status == "differs_from_manifest":
        record["data_manifest_mismatched"] = mismatched
        record["data_manifest_missing"] = missing
    return record


def host_provenance(
    config_name: str,
    prompt_name: str | None = None,
    data_variant: str | None = None,
) -> dict:
    """Record source identities; no credentials, environment values, or diffs."""
    root = repo_root()
    config = root / "configs" / f"{config_name}.toml"
    if prompt_name is None and config.is_file():
        try:
            prompt_name = tomllib.loads(config.read_text()).get("prompt")
        except (OSError, tomllib.TOMLDecodeError):
            prompt_name = None
    prompt_name = prompt_name or "unknown"
    prompt = root / "sandbox" / "prompts" / f"{prompt_name}.txt"
    dockerfile = root / "sandbox" / "docker" / "Dockerfile"
    sources = sorted(
        {
            config,
            prompt,
            dockerfile,
            root / "uv.lock",
            *root.glob("messageboard_audit_bench/*.py"),
            *root.glob("sandbox/*.py"),
            *root.glob("sandbox/*.sh"),
        }
    )
    dirty = _git(root, "diff", "--no-ext-diff", "--binary", "HEAD")
    return {
        "provenance_schema": 2,
        "config_source_path": str(config.relative_to(root)),
        "config_source_text": config.read_text() if config.is_file() else None,
        "config_source_sha256": _sha256(config),
        "prompt_template_path": str(prompt.relative_to(root)),
        "prompt_template_sha256": _sha256(prompt),
        "source_files_sha256": {
            str(path.relative_to(root)): _sha256(path) for path in sources
        },
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "git_dirty_sha256": hashlib.sha256(dirty.encode()).hexdigest()
        if dirty is not None
        else None,
        "declared_cli_versions": _declared_versions(dockerfile),
        "docker_image_identity": None,
        "docker_image_identity_status": "unknown_not_exposed_by_inspect_sandbox",
        "note": "The rendered prompt is retained by Inspect as sample input; this record identifies its template and configuration source.",
        **(
            data_provenance(data_variant, root)
            if data_variant
            else {"data_manifest_status": "not_recorded_no_variant_supplied"}
        ),
    }
