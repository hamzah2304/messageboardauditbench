"""Inspect AI tasks for the German wiki, Transluce and AI Village report benchmarks."""

from slopvestigator_bench.grading.task import (
    aivillage_report_grade,
    german_wiki_report_grade,
    transluce_report_grade,
)
from slopvestigator_bench.task import (
    aivillage_report,
    german_wiki_report,
    german_wiki_report_continue,
    german_wiki_report_replay,
    transluce_report,
)

__all__ = [
    "aivillage_report",
    "aivillage_report_grade",
    "german_wiki_report",
    "german_wiki_report_continue",
    "german_wiki_report_grade",
    "german_wiki_report_replay",
    "transluce_report",
    "transluce_report_grade",
]
