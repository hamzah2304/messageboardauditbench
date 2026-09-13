"""What a grade is: the sheets, the prompt, the parsing, the arithmetic, the path.

Every definition here was lifted from benchmark/rubrics/grade_with_rubrics.py rather than
rewritten, because 719 committed grade files were produced by that code and must remain
reproducible from it. The legacy script now imports these functions instead of defining
them, so the two paths cannot diverge; tests/test_grading_aggregate_parity.py replays every
committed file through `aggregate` to prove the arithmetic still matches.

No provider clients and no network here. `build_prompt` returns the three pieces a caller
needs — system, a cacheable prefix, and the suffix carrying the report — and each caller
assembles them the way its own API wants. That split is the Anthropic cache breakpoint in
the legacy script and the block ordering in the Inspect scorer, and it is why the same
bytes reach the judge either way.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from messageboard_audit_bench.runtime import repo_root

SYSTEM = (
    "You are a careful grader. Follow the grading sheet exactly and output strict JSON only."
)

# Appended on the one retry when a judge wrapped its JSON in prose or fences.
JSON_ONLY = (
    "\n\nIMPORTANT: return ONLY the JSON object itself — no prose before or "
    "after it, and no markdown code fences."
)

DEFAULT_JUDGE = "gpt-5.6-sol"


@dataclass(frozen=True)
class ModeSpec:
    """One rubric: which sheets it uses, what range it scores on, where it is filed.

    `sheet` and `sheet_set` differ only for the contradiction rubric, which scores the
    recall rubric's claim set against a different set of sheets.
    """

    sheet: str          # <sheet>_<i>.md, the prompt template
    sheet_set: str      # <sheet_set>_<i>.json, the claim set
    n_sheets: int
    lo: float
    hi: float
    prefix: str         # rubric_id prefix: R1..R6, V1..V8, TLDR, TLDRH
    numbered: bool      # False when the single sheet's rubric_id carries no number
    tldr_only: bool     # the summary alone is what this rubric judges
    directory: str | None = None  # optional subdirectory under benchmark/rubrics
    answer_key: str = "human_report.txt"  # relative to benchmark/


MODES: dict[str, ModeSpec] = {
    "recall": ModeSpec("rubric", "rubric", 6, 0.0, 1.0, "R", True, False),
    "contradiction": ModeSpec("contra", "rubric", 6, -1.0, 0.0, "R", True, False),
    "v2": ModeSpec("v2", "v2", 8, 0.0, 1.0, "V", True, False),
    "tldr": ModeSpec("tldr", "tldr", 1, 0.0, 1.0, "TLDR", False, True),
    "tldrh": ModeSpec("tldrh", "tldrh", 1, 0.0, 1.0, "TLDRH", False, True),
    # a one-question probe over the whole report; no answer key, so build_prompt tolerates
    # a sheet with no {{HUMAN_REPORT}} placeholder
    "origin": ModeSpec("origin", "origin", 1, 0.0, 1.0, "ORIGIN", False, False),
    "m5": ModeSpec(
        "m5", "m5", 3, 0.0, 1.0, "M", True, False,
        directory="mythos5", answer_key="rubrics/mythos5/mythos5_report.txt",
    ),
    "m5tldrh": ModeSpec(
        "m5tldrh", "m5tldrh", 1, 0.0, 1.0, "M5TLDRH", False, True,
        directory="mythos5", answer_key="rubrics/mythos5/mythos5_report.txt",
    ),
    "rh": ModeSpec(
        "rh", "rh", 3, 0.0, 1.0, "RH", True, False,
        directory="rubyhack", answer_key="rubrics/rubyhack/rubyhack_report.txt",
    ),
    "rhtldrh": ModeSpec(
        "rhtldrh", "rhtldrh", 1, 0.0, 1.0, "RHTLDRH", False, True,
        directory="rubyhack", answer_key="rubrics/rubyhack/rubyhack_report.txt",
    ),
}


def sanitise(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_")


def judge_name(model: str) -> str:
    """The bare model name, as the grade files have always recorded it.

    Inspect names models `provider/model`; the standalone grader names them `model`. If the
    two disagreed, Sol's grades would file under `judge_openai_gpt_5_6_sol/` from one path
    and `benchmark/graded/` from the other, and a corpus that is supposed to be one judge's
    work would be split across two directories.
    """
    return model.split("/", 1)[-1] if "/" in model else model


def rubric_ids(mode: str) -> list[str]:
    spec = MODES[mode]
    if not spec.numbered:
        return [spec.prefix]
    return [f"{spec.prefix}{i}" for i in range(1, spec.n_sheets + 1)]


# Rubric variants. A data variant that rewrites who the agents are (verbatim_anthropic,
# built by scripts/swap_provider.py) needs sheets and an answer key rewritten the same
# way, or the judge marks "Anthropic agents on AWS" as contradicting "OpenAI agents on
# Azure". benchmark/rubrics/build_rubrics_anthropic.py builds those files; this table says
# which data variant reads which.
VARIANT_FOR_DATA: dict[str, str] = {"verbatim_anthropic": "anthropic"}
VARIANTS = (None, "anthropic")


def variant_for_data(data_variant: str | None) -> str | None:
    return VARIANT_FOR_DATA.get(data_variant or "")


def variant_version(variant: str | None) -> str | None:
    """The version the variant's builder stamped into VERSION.json, or None for the default."""
    if not variant:
        return None
    path = _rubrics_dir(variant) / "VERSION.json"
    return json.loads(path.read_text())["version"] if path.is_file() else "unversioned"


def _check_variant(variant: str | None) -> None:
    if variant not in VARIANTS:
        raise ValueError(f"unknown rubric variant {variant!r}; expected one of {VARIANTS}")


def _rubrics_dir(variant: str | None = None, mode: str | None = None) -> Path:
    _check_variant(variant)
    d = repo_root() / "benchmark" / "rubrics"
    d = d / variant if variant else d
    directory = MODES[mode].directory if mode else None
    return d / directory if directory else d


def human_report(variant: str | None = None, mode: str | None = None) -> str:
    _check_variant(variant)
    if mode and MODES[mode].answer_key != "human_report.txt":
        if variant:
            raise ValueError(f"rubric {mode!r} has no {variant!r} provider variant")
        name = MODES[mode].answer_key
    else:
        name = f"human_report_{variant}.txt" if variant else "human_report.txt"
    return (repo_root() / "benchmark" / name).read_text()


def load_sheets(mode: str, variant: str | None = None) -> tuple[list[dict], dict[str, str]]:
    """(claim sets, rubric_id -> prompt template) for one mode.

    The .md is the whole prompt, with {{HUMAN_REPORT}} and {{MODEL_REPORT}} placeholders;
    the .json is the machine-readable claim set the aggregation reads grading_mode from.
    """
    spec, d = MODES[mode], _rubrics_dir(variant, mode)
    sets = [
        json.loads((d / f"{spec.sheet_set}_{i}.json").read_text())
        for i in range(1, spec.n_sheets + 1)
    ]
    ids = rubric_ids(mode)
    templates = {
        ids[i - 1]: (d / f"{spec.sheet}_{i}.md").read_text()
        for i in range(1, spec.n_sheets + 1)
    }
    return sets, templates


def extract_tldr(report_md: str) -> tuple[str, str]:
    """The summary alone, via the same extractor the legacy script uses."""
    scripts = repo_root() / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from extract_tldr import extract  # noqa: PLC0415  (path-dependent import)

    return extract(report_md)


def build_prompt(
    mode: str,
    rubric_id: str,
    report_md: str,
    templates: dict[str, str] | None = None,
    variant: str | None = None,
) -> tuple[str, str, str]:
    """(system, prefix, suffix) for one sheet.

    `prefix` is the sheet and the answer key — identical for every report on this rubric,
    which is what makes it worth caching. `suffix` is the model's report followed by the
    sheet's tail (the JSON contract). Concatenating prefix and suffix gives exactly the
    single-message prompt the OpenAI path sends.
    """
    if templates is None:
        _, templates = load_sheets(mode, variant)
    if MODES[mode].tldr_only:
        report_md, _how = extract_tldr(report_md)
    filled = templates[rubric_id].replace(
        "{{HUMAN_REPORT}}", human_report(variant, mode)
    )
    prefix, sep, tail = filled.partition("{{MODEL_REPORT}}")
    if not sep:
        raise ValueError(f"{mode}/{rubric_id}: sheet has no {{{{MODEL_REPORT}}}} placeholder")
    return SYSTEM, prefix, report_md + tail


def extract_json(raw: str | None) -> dict | None:
    """Anthropic gives no response_format guarantee; strip fences/prose around the object."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


def parse_items(data: dict | None, lo: float, hi: float) -> dict[str, dict]:
    """The sheet's items keyed by claim id, clamped to the rubric's range and rounded to 1dp.

    A judge that returns a score outside the range, or something that is not a number, is
    corrected rather than rejected: one malformed claim should not throw away the other
    four on the sheet.
    """
    items = {
        x["id"]: x
        for x in (data or {}).get("items", [])
        if isinstance(x, dict) and "id" in x
    }
    for item in items.values():
        try:
            item["score"] = round(max(lo, min(hi, float(item.get("score", 0)))), 1)
        except Exception:
            item["score"] = 0.0
    return items


def aggregate(
    key: str,
    title: str,
    judge: str,
    mode: str,
    per_claim: dict[str, dict],
    per_rubric: dict[str, dict],
    sets: list[dict] | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    """The graded_<key>.json body. Returns max=0 when nothing came back.

    With a rubric variant the body also records which variant and version graded it, so a
    grade against the swapped answer key can never be mistaken for one against the real one.

    A report whose every call failed — an auth or billing error hits all of them at once —
    must not be recorded as having scored zero. Callers check `max` and skip writing.
    """
    if not per_claim:
        return {"report": key, "total": None, "max": 0, "accuracy": None, "per_rubric": {}}

    total = round(sum(i["score"] for i in per_claim.values()), 2)
    count = len(per_claim)
    out: dict[str, Any] = {
        "report": key,
        "title": title,
        "grader": judge,
        "rubric": mode,
        "total": total,
        "max": count,
        "per_rubric": per_rubric,
        "scores": per_claim,
    }
    if variant:
        out["rubric_variant"] = variant
        out["rubric_variant_version"] = variant_version(variant)
    if mode == "contradiction":
        out["contradiction"] = round(total / count, 3) if count else 0
        out["n_contradicted"] = len([i for i in per_claim.values() if i["score"] < 0])
        out["worst"] = round(min([i["score"] for i in per_claim.values()] or [0]), 1)
        return out

    out["accuracy"] = round(total / count, 3) if count else 0
    # tldrh returns one item keyed TLDRH, not per-claim ids, so there is nothing to split
    # by grading mode; emitting the split would put two zeroes where a reader expects scores.
    if mode not in {"tldrh", "m5tldrh", "rhtldrh"}:
        if sets is None:
            sets, _ = load_sheets(mode, variant)
        grading_mode = {
            c["id"]: c.get("grading_mode", "recall_accuracy")
            for s in sets
            for c in s["claims"]
        }

        def mean(ids: list[str]) -> float:
            xs = [per_claim[i]["score"] for i in ids if i in per_claim]
            return round(sum(xs) / len(xs), 3) if xs else 0.0

        out["by_mode"] = {
            m: mean([cid for cid in per_claim if grading_mode.get(cid) == m])
            for m in ("recall_accuracy", "recall_calibrated")
        }
    return out


def out_dir(judge: str, mode: str, variant: str | None = None) -> Path:
    """Where a judge's grades for one rubric are filed.

    The default judge keeps writing to benchmark/graded/ (where every committed grade
    lives); any other judge gets its own namespace so the two never collide. A rubric
    variant gets a further subdirectory, so grades against the swapped answer key never
    sit next to grades against the real one.
    """
    _check_variant(variant)
    graded = repo_root() / "benchmark" / "graded"
    name = judge_name(judge)
    path = graded if name == DEFAULT_JUDGE else graded / f"judge_{sanitise(name)}"
    if mode != "recall":
        path = path / mode
    if variant:
        path = path / f"variant_{variant}"
    return path
