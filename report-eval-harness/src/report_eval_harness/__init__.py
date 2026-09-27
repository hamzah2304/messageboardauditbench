"""Blind incident-investigation evals on urlquery.net records, built on Inspect."""

from __future__ import annotations

import argparse
import sys

from report_eval_harness.corpus import Corpus, fetch, list_corpora, verify


def main() -> None:
    parser = argparse.ArgumentParser(prog="report-eval-harness")
    sub = parser.add_subparsers(dest="command", required=True)
    p_fetch = sub.add_parser("fetch", help="fetch a corpus's raw records into data/")
    p_fetch.add_argument("corpus", choices=list_corpora())
    p_fetch.add_argument("--force", action="store_true", help="re-fetch existing records")
    p_verify = sub.add_parser("verify", help="check records against SHA256SUMS")
    p_verify.add_argument("corpus", choices=list_corpora())
    p_web = sub.add_parser("web", help="web UI: launch Inspect runs, read reports and grades")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.command == "web":
        from report_eval_harness.web import serve

        return serve(args.host, args.port)

    corpus = Corpus(args.corpus)
    if args.command == "fetch":
        fetched = fetch(corpus, force=args.force)
        print(f"fetched {len(fetched)} records into {corpus.data_dir}")
    problems = verify(corpus)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(corpus.records())}/{len(corpus.ids())} records present; {len(problems)} problems")
    sys.exit(1 if problems else 0)
