"""Identity checks for evaluator-only manual findings and feasibility artifacts."""
from __future__ import annotations

import re


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"review template drift: expected one occurrence of {old!r}")
    return text.replace(old, new, 1)


def validate_review_scope(data: dict, benchmark_id: str) -> dict:
    if benchmark_id == "messageboard":
        return {}
    meta = data.get("meta", {})
    if meta.get("benchmark_id") != benchmark_id:
        raise ValueError("wrong benchmark in review artifact")
    for key in ("report_sha256", "dataset_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", str(meta.get(key, ""))):
            raise ValueError(f"review artifact requires {key}")
    return {key: meta[key] for key in ("benchmark_id", "report_sha256", "dataset_sha256")}
