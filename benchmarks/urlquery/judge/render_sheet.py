"""Print a filled URLQuery finding sheet, or a report's scan coverage.

    python benchmarks/urlquery/judge/render_sheet.py F4 [--article A.txt] [--report R.md]
    python benchmarks/urlquery/judge/render_sheet.py --coverage R.md

The sheet itself lives in `messageboard_audit_bench.grading.findings`; this script and
its names are kept for the viewers and commands that used them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from messageboard_audit_bench.grading.findings import (  # noqa: E402
    coverage,
    findings_path,
    linked_scans,
    load_findings,
    render,
    scored_group,
    template_path,
)

TEMPLATE = template_path()
FINDINGS = findings_path()

__all__ = ["FINDINGS", "TEMPLATE", "coverage", "linked_scans", "load_findings", "render", "scored_group"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("headline", nargs="?")
    parser.add_argument("--article", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--coverage", type=Path, help="print scan coverage for a report and exit")
    args = parser.parse_args()
    if args.coverage:
        print(json.dumps(coverage(args.coverage.read_text()), indent=1))
        return
    if not args.headline:
        parser.error("give a headline finding id, or --coverage REPORT")
    article = args.article.read_text() if args.article else "{{SOURCE_ARTICLE}}"
    report = args.report.read_text() if args.report else None
    print(render(args.headline, article, report))


if __name__ == "__main__":
    main()
