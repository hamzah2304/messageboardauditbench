"""Prompt templates in ``prompts/``.

Templates use ``{{NAME}}`` for values and ``{{#NAME}}...{{/NAME}}`` for sections kept only
when NAME is truthy. Unknown names and stray tags are errors, so a typo can't reach the
model as literal text. Other braces are left alone.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from report_eval_harness.corpus import PROJECT_ROOT

PROMPTS_DIR = PROJECT_ROOT / "prompts"

SECTION = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.DOTALL)
VALUE = re.compile(r"\{\{(\w+)\}\}")
TAG = re.compile(r"\{\{[#/^]?\w+\}\}")


def list_prompts() -> list[str]:
    return sorted(p.name for p in PROMPTS_DIR.glob("*.txt") if p.name != "analyst.txt")


def load(name: str) -> str:
    text = (PROMPTS_DIR / name).read_text()
    if not text.strip():
        raise ValueError(f"prompts/{name} is empty")
    return text


def values(
    *,
    n_records: int,
    budget_min: int,
    report_min_words: int,
    report_max_words: int,
    subagent_note: str = "",
    finish_note: str = "",
) -> dict[str, object]:
    """The placeholders a task prompt can use. ``report_max_words=0`` means no length limit."""
    if report_max_words and report_min_words > report_max_words:
        raise ValueError(f"report_min_words {report_min_words} > max {report_max_words}")
    return {
        "N_RECORDS": n_records,
        "BUDGET_MIN": budget_min,
        "REPORT_LENGTH": report_max_words > 0,
        "REPORT_MIN_WORDS": f"{report_min_words:,}",
        "REPORT_MAX_WORDS": f"{report_max_words:,}",
        "SUBAGENT_NOTE": subagent_note,
        "FINISH_NOTE": finish_note,
    }


def render(text: str, values: Mapping[str, object]) -> str:
    def known(name: str) -> object:
        if name not in values:
            raise ValueError(f"unknown prompt placeholder {name!r}; known: {sorted(values)}")
        return values[name]

    while (kept := SECTION.sub(lambda m: m[2] if known(m[1]) else "", text)) != text:
        text = kept
    text = VALUE.sub(lambda m: str(known(m[1])), text)
    if stray := TAG.search(text):
        raise ValueError(f"unbalanced prompt tag {stray[0]}")
    # A dropped section can leave a run of blank lines behind.
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
