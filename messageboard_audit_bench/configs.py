"""Load a named trial config (configs/<name>.toml) for one benchmark.

Every benchmark uses the same flat config format: ``prompt``, ``budget_min``,
``timeout_min``, ``data_variant``, ``effort``, report word limits, the Claude tool
denylist and optionally ``min_runtime_fraction``. A config names its benchmark with
``benchmark_id`` (default ``messageboard``). URLQuery configs also pin the frozen
dataset (``dataset_sha256``) and the exact CLI versions the subscription runner
installs; both must agree with benchmarks/urlquery/benchmark.json.

The shell runner reads the same files through scripts/read_config.py.
"""
from __future__ import annotations

import re
import tomllib

from messageboard_audit_bench.benchmarks import (
    benchmark_spec,
    config_names,
    draft_config_names,
    urlquery_data_variant,
    urlquery_manifest,
)
from messageboard_audit_bench.report_length import acceptance_limits
from messageboard_audit_bench.runtime import repo_root

CONFIG_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CLI_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def load_config(config_name: str, benchmark_id: str = "messageboard", *, allow_drafts: bool = False) -> dict:
    """Load one of a benchmark's registered fresh-trial configurations.

    ``allow_drafts`` also admits the draft incidents' configs (Mythos 5, RubyHack),
    which only the incident pipeline builds; they are not part of any eval yet.
    """
    benchmark_spec(benchmark_id)
    repo = repo_root()
    if not CONFIG_NAME.fullmatch(config_name):
        raise ValueError(
            f"invalid config name {config_name!r}; use a name from {repo / 'configs'}"
        )
    available = config_names(benchmark_id)
    if benchmark_id == "messageboard" and config_name in draft_config_names():
        if not allow_drafts:
            raise ValueError(
                f"{config_name!r} belongs to a draft incident, not the German wiki report; "
                "see docs/adding-an-incident.md"
            )
        available = (*available, config_name)
    if config_name not in available:
        raise ValueError(
            f"unknown {benchmark_id} config {config_name!r}; available configs: {', '.join(available)}"
        )
    path = repo / "configs" / f"{config_name}.toml"
    if not path.is_file():
        raise RuntimeError(f"config file is missing: {path}")
    cfg = tomllib.loads(path.read_text())
    validate_config(cfg, benchmark_id)
    return cfg


def validate_config(cfg: dict, benchmark_id: str) -> None:
    if cfg.get("benchmark_id", "messageboard") != benchmark_id:
        raise ValueError(
            f"config {cfg.get('name')!r} belongs to {cfg.get('benchmark_id', 'messageboard')!r}, "
            f"not {benchmark_id!r}"
        )
    acceptance_limits(cfg)
    if benchmark_id != "urlquery":
        return
    dataset = urlquery_manifest()["dataset"]
    if cfg.get("data_variant") != urlquery_data_variant():
        raise ValueError(
            f"URLQuery config {cfg.get('name')!r} must use data_variant {urlquery_data_variant()!r}"
        )
    if cfg.get("dataset_sha256") != dataset["sha256"]:
        raise ValueError(
            f"URLQuery config {cfg.get('name')!r} dataset_sha256 does not match the manifest pin"
        )
    for key in ("claude_cli_version", "codex_cli_version"):
        if not isinstance(cfg.get(key), str) or not CLI_VERSION.fullmatch(cfg[key]):
            raise ValueError(f"URLQuery config {cfg.get('name')!r} needs an exact {key}")
