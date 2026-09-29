#!/usr/bin/env python3
"""Fetch Transluce's urlquery.net agent-activity catalogue plus the raw urlquery
JSON for an explorable subset of its reports.

    uv run scripts/fetch_transluce.py [--per-source 15] [--suggestive 120] [--dry-run]

Everything lands in the primary checkout's gitignored data/transluce/:
  urlquery-agent-activity-2026-09-23.zip + the unzipped catalogue
  agent-activity.html        the blog post (cited report ids come from here)
  reports/<report_id>.json   one raw urlquery report per id, cached
  subset.json                which ids were chosen and why

urlquery's terms allow personal, non-commercial use and forbid redistribution,
so none of this is committed. See docs/transluce-urlquery-assessment.md.

The subset: every report the post links to, every supplemental (hand-reviewed)
row, catalogue reports within 45 minutes of a cited report with the same data
source (so the cited sequences reconstruct), a per-source sample of significant
reports, a random suggestive sample, and the background / review-required rows.
Requests are serial at one per second; a rerun only fetches what is missing.
"""
import argparse
import csv
import json
import random
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ZIP_URL = "https://transluce.org/data/urlquery-agent-activity-2026-09-23.zip"
ZIP_BYTES = 4_570_708
POST_URL = "https://transluce.org/agent-activity"
REPORT_JSON = "https://urlquery.net/report/{}/json"
UA = "Mozilla/5.0 (research; messageboardauditbench explorer)"


def primary_root():
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


OUT = primary_root() / "data" / "transluce"
REPORTS = OUT / "reports"


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def catalogue_dir():
    hits = sorted(OUT.glob("urlquery-agent-activity-*/all-reports.csv"))
    return hits[0].parent if hits else None


def ensure_catalogue():
    OUT.mkdir(parents=True, exist_ok=True)
    z = OUT / Path(ZIP_URL).name
    if not z.exists():
        print(f"downloading {ZIP_URL}")
        z.write_bytes(get(ZIP_URL))
    if z.stat().st_size != ZIP_BYTES:
        sys.exit(f"{z} is {z.stat().st_size} bytes, expected {ZIP_BYTES}; delete it and rerun")
    if not catalogue_dir():
        zipfile.ZipFile(z).extractall(OUT)
    post = OUT / "agent-activity.html"
    if not post.exists():
        print(f"downloading {POST_URL}")
        post.write_bytes(get(POST_URL))
    return catalogue_dir()


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def choose(cat, per_source, n_suggestive, seed=20260923):
    rows = {r["report_id"]: r for r in csv.DictReader(open(cat / "all-reports.csv"))}
    src = {r["report_id"]: r["data_source"] for r in csv.DictReader(open(cat / "report-sources.csv"))}
    supp = [r["report_id"] for r in csv.DictReader(open(cat / "additional-cited-reports.csv"))]
    post = (OUT / "agent-activity.html").read_text(errors="replace")
    cited = sorted(set(re.findall(r"urlquery\.net/report/([0-9a-f-]{36})", post)))
    rng = random.Random(seed)
    why = defaultdict(set)
    for i in cited:
        why[i].add("cited")
    for i in supp:
        why[i].add("supplement")

    # neighbours: same data source within 45 minutes of a cited report
    by_src = defaultdict(list)
    for i, r in rows.items():
        by_src[src.get(i, "")].append((ts(r["report_date_utc"]), i))
    for s in by_src:
        by_src[s].sort()
    win = timedelta(minutes=45)
    for c in cited:
        if c not in rows:
            continue
        t0, s = ts(rows[c]["report_date_utc"]), src.get(c, "")
        near = [i for t, i in by_src[s] if abs(t - t0) <= win and i != c]
        for i in near[:60]:
            why[i].add("neighbour")

    sig = defaultdict(list)
    sug = []
    for i, r in rows.items():
        if r["confidence"] == "significant":
            sig[src.get(i, "")].append(i)
        elif r["confidence"] == "suggestive":
            sug.append(i)
        elif r["disposition"] == "background":
            why[i].add("background_control")
    for s, ids in sig.items():
        for i in rng.sample(sorted(ids), min(per_source, len(ids))):
            why[i].add("significant_sample")
    for i in rng.sample(sorted(sug), min(n_suggestive, len(sug))):
        why[i].add("suggestive_sample")
    rr = sorted(i for i, r in rows.items() if r["disposition"] == "review_required")
    for i in rng.sample(rr, min(40, len(rr))):
        why[i].add("review_required_sample")
    return {i: sorted(w) for i, w in sorted(why.items())}, cited


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-source", type=int, default=15)
    ap.add_argument("--suggestive", type=int, default=120)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cat = ensure_catalogue()
    subset, cited = choose(cat, a.per_source, a.suggestive)
    (OUT / "subset.json").write_text(json.dumps(
        {"catalogue": cat.name, "cited_in_post": cited, "reasons": subset}, indent=1))
    REPORTS.mkdir(exist_ok=True)
    todo = [i for i in subset if not (REPORTS / f"{i}.json").exists()]
    counts = defaultdict(int)
    for w in subset.values():
        for x in w:
            counts[x] += 1
    print(f"subset {len(subset)} reports {dict(counts)}; {len(todo)} to fetch "
          f"(~{len(todo) * (a.delay + 0.4) / 60:.0f} min)")
    if a.dry_run:
        return
    fails = []
    for n, i in enumerate(todo, 1):
        try:
            body = get(REPORT_JSON.format(i))
            json.loads(body)
            (REPORTS / f"{i}.json").write_bytes(body)
        except Exception as e:  # missing / expired reports are recorded, not fatal
            fails.append((i, str(e)[:120]))
        if n % 50 == 0:
            print(f"  {n}/{len(todo)} fetched, {len(fails)} failed", flush=True)
        time.sleep(a.delay)
    if fails:
        (OUT / "fetch_failures.json").write_text(json.dumps(fails, indent=1))
    print(f"done: {len(todo) - len(fails)} fetched, {len(fails)} failed -> {REPORTS}")


if __name__ == "__main__":
    main()
