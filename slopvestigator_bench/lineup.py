"""The model lineup (configs/lineup.toml): who runs, in which harness, at what list price."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache

from slopvestigator_bench.runtime import repo_root

HARNESSES = ("claude", "codex", "react")


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    lab: str
    lab_name: str
    colour: str
    harness: str
    price_in: float   # USD per million input tokens
    price_out: float  # USD per million output tokens


@lru_cache(maxsize=1)
def _lineup() -> dict:
    return tomllib.loads((repo_root() / "configs" / "lineup.toml").read_text())


@lru_cache(maxsize=1)
def models() -> tuple[Model, ...]:
    data = _lineup()
    labs, out, seen = data["labs"], [], set()
    for row in data["models"]:
        if row["id"] in seen:
            raise ValueError(f"lineup lists {row['id']} twice")
        if row["harness"] not in HARNESSES:
            raise ValueError(f"{row['id']}: harness must be one of {HARNESSES}")
        if row["lab"] not in labs:
            raise ValueError(f"{row['id']}: unknown lab {row['lab']!r}")
        seen.add(row["id"])
        lab = labs[row["lab"]]
        out.append(Model(row["id"], row["label"], row["lab"], lab["name"], lab["colour"], row["harness"],
                         float(row["price"][0]), float(row["price"][1])))
    return tuple(out)


def model(model_id: str) -> Model:
    for m in models():
        if m.id == model_id:
            return m
    raise KeyError(f"{model_id!r} is not in configs/lineup.toml")


def lab_colours() -> dict[str, str]:
    """Lab display name -> colour, for figure legends."""
    return {lab["name"]: lab["colour"] for lab in _lineup()["labs"].values()}
