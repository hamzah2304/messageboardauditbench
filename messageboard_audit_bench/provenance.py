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


def host_provenance(config_name: str, prompt_name: str | None = None) -> dict:
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
        "provenance_schema": 1,
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
    }
