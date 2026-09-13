"""Single source of truth for benchmark incidents and their lifecycle state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from messageboard_audit_bench.runtime import repo_root

MATURITIES = {"candidate", "pilot", "reviewed", "published"}
RESULT_STATUSES = {"none", "pilot", "published"}


@dataclass(frozen=True)
class Incident:
    """A validated incident manifest."""

    id: str
    title: str
    maturity: str
    investigation_url: str
    corpus: dict[str, Any]
    runtime: dict[str, Any]
    grading: dict[str, Any]
    review: dict[str, Any]
    results: dict[str, Any]
    manifest_path: Path

    @property
    def variants(self) -> tuple[str, ...]:
        return tuple(self.corpus["variants"])

    @property
    def configs(self) -> tuple[str, ...]:
        return tuple(self.runtime["configs"])

    @property
    def rubrics(self) -> tuple[str, str]:
        return self.grading["finding_mode"], self.grading["summary_mode"]


def _require(data: dict[str, Any], keys: set[str], where: str) -> None:
    missing = sorted(keys - data.keys())
    if missing:
        raise ValueError(f"{where}: missing {', '.join(missing)}")


def _load(path: Path) -> Incident:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read incident manifest {path}: {exc}") from exc
    _require(
        data,
        {
            "schema",
            "id",
            "title",
            "maturity",
            "investigation_url",
            "corpus",
            "runtime",
            "grading",
            "review",
            "results",
        },
        path.name,
    )
    if data["schema"] != 1:
        raise ValueError(f"{path.name}: unsupported schema {data['schema']!r}")
    if data["id"] != path.stem:
        raise ValueError(f"{path.name}: id must match the filename")
    if data["maturity"] not in MATURITIES:
        raise ValueError(f"{path.name}: unknown maturity {data['maturity']!r}")
    if data["results"].get("status") not in RESULT_STATUSES:
        raise ValueError(f"{path.name}: unknown results status")
    _require(
        data["corpus"],
        {"primary_variant", "variants", "files", "builder", "build_command", "blindness", "limitations"},
        f"{path.name}/corpus",
    )
    _require(
        data["runtime"],
        {"configs", "default_config", "default_minutes"},
        f"{path.name}/runtime",
    )
    _require(
        data["grading"],
        {"finding_mode", "summary_mode", "claims_file", "answer_key", "rubric_builder"},
        f"{path.name}/grading",
    )
    if data["corpus"]["primary_variant"] not in data["corpus"]["variants"]:
        raise ValueError(f"{path.name}: primary variant is not listed in variants")
    if data["runtime"]["default_config"] not in data["runtime"]["configs"]:
        raise ValueError(f"{path.name}: default config is not listed in configs")
    if not isinstance(data["runtime"]["default_minutes"], int) or data["runtime"]["default_minutes"] <= 0:
        raise ValueError(f"{path.name}: default_minutes must be a positive integer")
    return Incident(
        id=data["id"],
        title=data["title"],
        maturity=data["maturity"],
        investigation_url=data["investigation_url"],
        corpus=data["corpus"],
        runtime=data["runtime"],
        grading=data["grading"],
        review=data["review"],
        results=data["results"],
        manifest_path=path,
    )


@lru_cache(maxsize=1)
def incidents() -> dict[str, Incident]:
    directory = repo_root() / "benchmark" / "incidents"
    paths = sorted(directory.glob("*.json"), key=lambda path: (path.stem != "wiki", path.stem))
    loaded = {path.stem: _load(path) for path in paths}
    if not loaded:
        raise RuntimeError(f"no incident manifests found under {directory}")
    configs: dict[str, str] = {}
    variants: dict[str, str] = {}
    modes: dict[str, str] = {}
    for incident in loaded.values():
        for value, owners, label in (
            *((value, configs, "config") for value in incident.configs),
            *((value, variants, "data variant") for value in incident.variants),
            *((value, modes, "rubric mode") for value in incident.rubrics),
        ):
            if value in owners:
                raise ValueError(
                    f"{label} {value!r} belongs to both {owners[value]!r} and {incident.id!r}"
                )
            owners[value] = incident.id
    return loaded


def incident(incident_id: str) -> Incident:
    try:
        return incidents()[incident_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown incident {incident_id!r}; choose from: {', '.join(incidents())}"
        ) from exc


def incident_for_variant(data_variant: str) -> Incident:
    matches = [item for item in incidents().values() if data_variant in item.variants]
    if len(matches) != 1:
        raise ValueError(f"data variant {data_variant!r} does not identify one incident")
    return matches[0]


def config_names() -> tuple[str, ...]:
    return tuple(config for item in incidents().values() for config in item.configs)


def data_variants() -> frozenset[str]:
    return frozenset(variant for item in incidents().values() for variant in item.variants)


def default_rubrics(data_variant: str) -> str:
    return ",".join(incident_for_variant(data_variant).rubrics)


def registered_mode_specs() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in incidents().values():
        out.update(item.grading.get("modes", {}))
    return out
