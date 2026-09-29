"""Inspect AI tasks for the German wiki report and Transluce report benchmarks.

The pre-rename task names are kept as deprecated aliases.
"""

from messageboard_audit_bench.grading.task import (
    german_wiki_report_grade,
    grade_reports,
    transluce_report_grade,
    urlquery_grade_reports,
)
from messageboard_audit_bench.task import (
    german_wiki_report,
    german_wiki_report_continue,
    german_wiki_report_replay,
    messageboard_audit_bench,
    messageboard_audit_bench_continue,
    messageboard_audit_bench_replay,
    transluce_report,
    urlquery_audit_bench,
)

__all__ = [
    "german_wiki_report",
    "german_wiki_report_continue",
    "german_wiki_report_grade",
    "german_wiki_report_replay",
    "transluce_report",
    "transluce_report_grade",
    # deprecated aliases
    "grade_reports",
    "messageboard_audit_bench",
    "messageboard_audit_bench_continue",
    "messageboard_audit_bench_replay",
    "urlquery_audit_bench",
    "urlquery_grade_reports",
]
