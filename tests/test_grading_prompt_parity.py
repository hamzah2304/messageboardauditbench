"""The bytes that reach the judge, pinned.

Every score in the corpus is a function of the exact prompt that produced it. A stray
whitespace change in a sheet, a reordered substitution, a sheet renumbered — any of those
would silently reprice all 719 grades, and nothing else in the suite would notice, because
a judge given a slightly different prompt still returns plausible numbers.

So this fixes the assembled prompt for a committed report against a recorded digest, per
mode. The digests below were taken when the grading core was factored out of
benchmark/rubrics/grade_with_rubrics.py, and were verified byte-for-byte against that
script as it stood immediately before the refactor, for all five modes.

A failure here is not necessarily a bug: editing a rubric sheet is a legitimate act and
will trip it. It means "the judge is now being asked something different, and grades made
before this change are no longer comparable with grades made after it" — update the digest
in the same commit as the sheet edit, and say so in the message.
"""

from __future__ import annotations

import hashlib

import pytest

from messageboard_audit_bench.grading import core
from messageboard_audit_bench.runtime import repo_root

# a committed report, so the digest is reproducible from a clean checkout
FIXTURE = (
    repo_root()
    / "benchmark"
    / "graded_inputs"
    / "round4_blind10"
    / "r4b10__claude__claude-haiku-4-5__rep1.md"
)

DIGESTS = {
    "v2": "7788226b0e82fedcd80cc4065455f326a5d0437c5cef56d8301278468b7792a4",
    "tldrh": "14b58704b66df4018eff11f8c627d4f87a3d4abcf1c0e55a09d019f177b60ce4",
    "recall": "1ea0da89804e87752d5762bef7594b67c07126946ee0ceefb63aaf3a25959ea1",
    "contradiction": "dbc08d86c571c5b308e934e2d3585abf60820d617de6e258370f7728c967ba73",
    "tldr": "c808993865f6f21839d1b583a44e8a96422f9ecccd72fd4af5ba63880e208ac7",
}


def report() -> str:
    return FIXTURE.read_text()


def prompts(mode: str) -> list[tuple[str, str, str]]:
    sets, templates = core.load_sheets(mode)
    return [
        core.build_prompt(mode, s["rubric_id"], report(), templates) for s in sets
    ]


@pytest.mark.parametrize("mode", sorted(DIGESTS))
def test_prompt_bytes_are_unchanged(mode: str) -> None:
    digest = hashlib.sha256()
    for parts in prompts(mode):
        for part in parts:
            digest.update(part.encode())
    assert digest.hexdigest() == DIGESTS[mode], (
        f"{mode}: the prompt sent to the judge has changed. If a rubric sheet was edited "
        "deliberately, update the digest here in the same commit and note that grades "
        "either side of it are not comparable."
    )


@pytest.mark.parametrize("mode", sorted(DIGESTS))
def test_the_two_provider_shapes_carry_the_same_bytes(mode: str) -> None:
    """Anthropic sends prefix and suffix as two blocks; OpenAI concatenates them.

    The split exists only to put the cache breakpoint after the sheet. If it ever changed
    what the judge reads, the two providers' grades would stop being comparable — and the
    corpus mixes them.
    """
    text = report()
    for system, prefix, suffix in prompts(mode):
        assert system == core.SYSTEM
        assert prefix and suffix
        # every placeholder is filled, in both halves
        assert "{{HUMAN_REPORT}}" not in prefix + suffix
        assert "{{MODEL_REPORT}}" not in prefix + suffix
        # the report starts the suffix and nothing of it leaks into the cacheable prefix
        head = text[:200] if mode not in ("tldr", "tldrh") else suffix[:200]
        assert suffix.startswith(head)
        assert head not in prefix


@pytest.mark.parametrize("mode", sorted(DIGESTS))
def test_only_the_suffix_changes_between_reports(mode: str) -> None:
    sets, templates = core.load_sheets(mode)
    for spec in sets:
        rid = spec["rubric_id"]
        _, prefix_a, suffix_a = core.build_prompt(mode, rid, report(), templates)
        _, prefix_b, suffix_b = core.build_prompt(mode, rid, "# TL;DR\nA different report.",
                                                  templates)
        assert prefix_a == prefix_b, f"{mode}/{rid}: the cacheable prefix depends on the report"
        assert suffix_a != suffix_b


def test_tldr_rubrics_see_the_summary_only() -> None:
    """The whole point of tldrh: a finding buried in the body must not reach the judge."""
    body_marker = "GRADER_MUST_NOT_SEE_THIS_MARKER"
    doc = f"## TL;DR\nA short summary.\n\n## Findings\n{body_marker}\n"
    for mode in ("tldr", "tldrh"):
        sets, templates = core.load_sheets(mode)
        _, prefix, suffix = core.build_prompt(mode, sets[0]["rubric_id"], doc, templates)
        assert body_marker not in prefix + suffix
        assert "A short summary." in suffix
    # and the full-report rubrics do see it
    sets, templates = core.load_sheets("v2")
    _, prefix, suffix = core.build_prompt("v2", sets[0]["rubric_id"], doc, templates)
    assert body_marker in suffix
