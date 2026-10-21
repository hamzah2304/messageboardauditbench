"""Does a finished run count? One fail-closed rule for every benchmark.

A run counts when its report exists, the requested model answered throughout (no switch to
another model after a safety flag), it ran for its minimum time, its report is within the
accepted length and its data matched the manifest. Anything unrecorded counts against it.

Nothing here retries or replaces a run: an ineligible run stays in the results as a failure,
with its reasons, so a model's failure rate is reported next to its score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_OK = {"matches_manifest", "verified"}


@dataclass(frozen=True)
class Verdict:
    eligible: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    model: str = ""
    served_model: str = ""
    safety_flags: int = 0


def check_meta(meta: dict) -> Verdict:
    reasons = []
    if "exit_code" not in meta:
        reasons.append("unfinished")  # still running, or killed before the runner recorded the end
    model = str(meta.get("model", ""))
    served = str(meta.get("model_served") or model)
    if meta.get("model_fallback") or served != model:
        reasons.append("model_switched")
    if meta.get("model_refusal") or meta.get("termination") == "refusal":
        reasons.append("refused")
    if meta.get("report_exists") is not True or not meta.get("report_words"):
        reasons.append("no_report")
    if meta.get("minimum_runtime_reached") is not True:
        reasons.append("below_minimum_runtime")
    if meta.get("report_length_compliant") is not True:
        reasons.append("report_length")
    if meta.get("data_manifest_status") not in DATA_OK:
        reasons.append("data_unverified")
    if meta.get("termination") in ("error", "capacity_exhausted"):
        reasons.append(f"ended_{meta['termination']}")
    return Verdict(not reasons, tuple(reasons), model, served, int(meta.get("safety_flags") or 0))


def check(run_dir: Path) -> Verdict:
    meta_path = Path(run_dir) / "meta.json"
    if not meta_path.is_file():
        return Verdict(False, ("no_meta",))
    return check_meta(json.loads(meta_path.read_text()))
