"""Locate the repository assets required by the Docker-backed eval."""
from __future__ import annotations

import os
from pathlib import Path

_ROOT_ENV = "MESSAGEBOARD_AUDIT_BENCH_ROOT"


def _is_checkout(path: Path) -> bool:
    return (path / "configs").is_dir() and (
        path / "sandbox" / "docker" / "run_trial.sh"
    ).is_file()


def repo_root() -> Path:
    """Return a checkout containing the configs and sandbox runtime."""
    override = os.environ.get(_ROOT_ENV)
    if override:
        root = Path(override).expanduser().resolve()
        if _is_checkout(root):
            return root
        raise RuntimeError(
            f"{_ROOT_ENV}={override!r} is not a MessageBoardAuditBench checkout"
        )

    package_checkout = Path(__file__).resolve().parent.parent
    for root in (package_checkout, Path.cwd().resolve()):
        if _is_checkout(root):
            return root

    raise RuntimeError(
        "messageboard_audit_bench needs the repository's configs, sandbox, and "
        "data. Run Inspect from a MessageBoardAuditBench checkout or set "
        f"{_ROOT_ENV} to its root."
    )
