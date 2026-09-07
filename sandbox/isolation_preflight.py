#!/usr/bin/env python3
"""Verify the Inspect-native trial environment before an agent receives a prompt.

The check is intentionally local: a native task uses Docker ``network_mode:
none``, so testing a remote endpoint would weaken the property it is meant to
verify. It produces one compact JSON record that the caller should retain in
the Inspect sample metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from pathlib import Path


REQUIRED_DATA_FILES = frozenset({"events.jsonl", "labels.jsonl", "pages.jsonl", "revisions.jsonl"})
ALLOWED_DATA_AUXILIARY_FILES = frozenset({".gitkeep"})


def file_digest_and_jsonl_count(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    rows = 0
    with path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            if not line.strip():
                raise ValueError(f"blank JSONL record at line {rows + 1}")
            try:
                json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid JSONL record at line {rows + 1}: {exc}") from exc
            rows += 1
    if rows == 0:
        raise ValueError("empty data file")
    return digest.hexdigest(), rows


def _network_interfaces() -> list[str]:
    return sorted(name for _index, name in socket.if_nameindex())


def _is_readonly_mount(path: Path) -> bool:
    try:
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            before_separator = line.split(" - ", 1)[0].split()
            if len(before_separator) >= 6 and before_separator[4] == str(path):
                return "ro" in before_separator[5].split(",")
    except OSError:
        return False
    return False


def preflight(
    work: Path,
    *,
    require_readonly_mount: bool = False,
    require_no_credentials: bool = False,
) -> dict:
    """Check visibility, data integrity, and the native no-network boundary."""
    work = work.resolve()
    data = work / "data"
    visible = sorted(str(path.relative_to(work)) for path in work.rglob("*") if path.is_file() or path.is_symlink())
    problems: list[str] = []
    allowed_visible = {f"data/{name}" for name in REQUIRED_DATA_FILES | ALLOWED_DATA_AUXILIARY_FILES}
    if set(visible) - allowed_visible:
        problems.append(f"unexpected /work visibility: {visible!r}")
    if not data.is_dir():
        problems.append("/work/data is missing")
    data_files = {path.name for path in data.iterdir()} if data.is_dir() else set()
    if not REQUIRED_DATA_FILES <= data_files or data_files - (REQUIRED_DATA_FILES | ALLOWED_DATA_AUXILIARY_FILES):
        problems.append(f"data files are {sorted(data_files)!r}, expected required {sorted(REQUIRED_DATA_FILES)!r}")
    data_readonly = _is_readonly_mount(data)
    if require_readonly_mount and not data_readonly:
        problems.append("/work/data is not a read-only mount")

    files: dict[str, dict[str, int | str]] = {}
    for name in sorted(REQUIRED_DATA_FILES):
        path = data / name
        if not path.is_file() or path.is_symlink():
            problems.append(f"{name} is absent, not a regular file, or a symlink")
            continue
        try:
            digest, rows = file_digest_and_jsonl_count(path)
        except (OSError, ValueError) as exc:
            problems.append(f"{name}: {exc}")
            continue
        files[name] = {"sha256": digest, "bytes": path.stat().st_size, "records": rows}

    interfaces = _network_interfaces()
    if interfaces != ["lo"]:
        problems.append(f"non-loopback network interface visible: {interfaces!r}")
    credential_paths = ["/home/agent/.claude", "/home/agent/.codex"]
    visible_credentials = [path for path in credential_paths if Path(path).exists()]
    if require_no_credentials and visible_credentials:
        problems.append(f"native sandbox exposes credential paths: {visible_credentials!r}")
    credential_env = sorted(
        key for key in os.environ if key in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}
    )
    if require_no_credentials and credential_env:
        problems.append(f"native sandbox exposes credential environment variables: {credential_env!r}")
    report = {
        "preflight_schema": 1,
        "work": str(work),
        "visible_files": visible,
        "files": files,
        "network_interfaces": interfaces,
        "data_readonly_mount": data_readonly,
        "credential_paths_visible": visible_credentials,
        "credential_env_visible": credential_env,
        "network_mode": "loopback-only" if interfaces == ["lo"] else "not-isolated",
        "ok": not problems,
        "problems": problems,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, default=Path("/work"))
    args = parser.parse_args()
    result = preflight(
        args.work,
        require_readonly_mount=True,
        require_no_credentials=True,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
