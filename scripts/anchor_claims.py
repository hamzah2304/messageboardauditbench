#!/usr/bin/env python3
"""Verbatim text anchors, so a UI can highlight the exact span a claim rests on.

Two passes, both asking GPT-5.6 Sol for spans copied character-for-character out of
a source text and then *checking* that every span really is a substring of it:

  --human    where each of the 30 rubric claims lives in the human report as the site
             publishes it (scripts/wiki_report.article_text()). The rubric's own
             report_quote is passed as a hint, but only 26 of 30 survive a literal
             substring test -- the other four are paraphrased or elided -- so the
             anchors, not the quotes, are what a highlighter can trust.
             -> benchmark/claims/anchors_human.json

  --reports  repairs for judge quotes that do not occur in the model report they
             grade. For every (report, claim) in benchmark/graded/graded_<key>.json
             whose quote is unfindable in benchmark/graded_inputs/<dir>/<stem>.md,
             Sol is shown the report, the claim, the quote and the judge's reason and
             asked what the judge was pointing at. Nothing is invented: a pair that
             fails validation twice is recorded with an empty span list.
             -> benchmark/claims/anchors_reports.json

Spans shorter than 25 characters are dropped. A failed span is fed back once with the
strings that were not found; whatever still will not validate is kept under
"unverified" for inspection rather than silently discarded.

Both output files are resumable: --human skips a claim already recorded, and --reports
skips a pair whose recorded judge_quote still matches the quote the judge currently
gives. A regrade rewrites those quotes, so --reports also regenerates any entry whose
quote has moved on and drops any entry whose pair no longer needs repairing at all --
re-running it after a regrade costs only the pairs that actually changed. --force
redoes everything.

    scripts/anchor_claims.py [--human] [--reports] [--force]      (neither = both)
Env: OPENAI_API_KEY (.env), MODEL (default gpt-5.6-sol), EFFORT (default xhigh).
"""
from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import CLAIMS, GRADED, GRADED_INPUTS, RUBRICS, ENV_FILE
from wiki_report import article_text

from dotenv import load_dotenv
load_dotenv(ENV_FILE)
from openai import OpenAI

MODEL = os.getenv("MODEL", "gpt-5.6-sol")
EFFORTS = [os.getenv("EFFORT", "xhigh"), "high", "medium"]
client = OpenAI()

HUMAN_OUT = CLAIMS / "anchors_human.json"
REPORTS_OUT = CLAIMS / "anchors_reports.json"
REPORT_DIRS = ["round2_blind10", "round2_blind20", "round2_blind30",
               "round3_blind10", "round3_blind30", "round3_blind120",
               "round4_blind10"]
MIN_SPAN = 25

SYS = ("You locate evidence in a document. You never paraphrase, never elide with "
       "ellipses, and never fix typography: every span you return is copied "
       "character-for-character from the document you were given, so that a plain "
       "substring search finds it. Output strict JSON only.")

CALLS = 0


def sol(system, user, max_tok=16000):
    global CALLS
    last = None
    for eff in EFFORTS:
        try:
            r = client.chat.completions.create(model=MODEL, reasoning_effort=eff,
                response_format={"type": "json_object"}, max_completion_tokens=max_tok,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            CALLS += 1
            return r.choices[0].message.content
        except Exception as e:
            last = e
            if "effort" in str(e).lower():
                continue
            raise
    raise RuntimeError(f"all efforts failed: {last}")


def parse_spans(raw):
    """-> (spans, note) from the model's JSON, tolerating a stray shape."""
    try:
        data = json.loads(raw)
    except Exception:
        return [], ""
    spans = data.get("spans") or []
    if isinstance(spans, str):
        spans = [spans]
    spans = [s for s in spans if isinstance(s, str) and s.strip()]
    return spans[:3], str(data.get("note") or "")


def anchor(prompt, source, tries=2):
    """Ask for spans, keep only those that literally occur in `source`.

    Any span that fails the substring test earns one retry, quoting the strings that
    were not found back at the model; spans validated on the first attempt are kept.
    """
    good, bad, note, attempts = [], [], "", 0
    msg = prompt
    while attempts < tries:
        attempts += 1
        spans, note = parse_spans(sol(SYS, msg))
        bad = []
        for s in spans:
            s = s.strip()
            if s in source and len(s) >= MIN_SPAN:
                if s not in good:
                    good.append(s)
            elif s:
                if s not in bad:
                    bad.append(s)
        if not bad or attempts >= tries:
            break
        msg = (prompt + "\n\n=== RETRY ===\nSome of your spans were rejected. These "
               "strings were NOT found in the document by an exact substring search:\n"
               + "\n".join(f"  - {b!r}" for b in bad)
               + "\nYou must COPY the text out of the document exactly as it appears -- "
                 "same words, same punctuation, same spacing, no ' ... ' elisions, no "
                 "paraphrase, no summarising. Each span must be at least "
               f"{MIN_SPAN} characters. Try again, and return only spans you have "
               "checked occur literally in the document.")
    return good[:3], bad, note, attempts


# --------------------------------------------------------------------------- pass 1

def human_prompt(article, claim):
    return f"""Below is the full text of a published incident report, then a claim that
the report makes. Find where in the report that claim is stated.

Return strict JSON: {{"spans": ["...", "..."], "note": "..."}}
  - 1 to 3 spans, each COPIED CHARACTER-FOR-CHARACTER from the REPORT TEXT below,
    each at least {MIN_SPAN} characters. A plain substring search must find them.
  - Prefer whole sentences that state the claim, including any figures it depends on.
  - If several separated sentences are needed, return them as separate spans; never
    join them with " ... ".
  - "note": one sentence on what you anchored and anything the report states
    differently from the claim.

=== CLAIM ({claim['id']}, section "{claim.get('section', '')}") ===
{claim['claim']}

=== HINT (the rubric author's citation; may be paraphrased or elided, so verify it
against the report text and correct it rather than repeating it) ===
{claim.get('report_quote', '')}

=== REPORT TEXT ===
{article}
"""


def run_human(force):
    article = article_text()
    claims = [c for i in range(1, 7)
              for c in json.loads((RUBRICS / f"rubric_{i}.json").read_text())["claims"]]
    out = {} if force or not HUMAN_OUT.exists() else json.loads(HUMAN_OUT.read_text())
    todo = [c for c in claims if c["id"] not in out]
    print(f"[human] {len(claims)} claims, {len(todo)} to do "
          f"(article {len(article)/1000:.0f} KB)")
    if todo:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(anchor, human_prompt(article, c), article): c for c in todo}
            for f in as_completed(futs):
                c = futs[f]
                try:
                    good, bad, note, attempts = f.result()
                except Exception as e:
                    print(f"  [{c['id']}] FAILED: {e!r}")
                    continue
                out[c["id"]] = {"id": c["id"], "spans": good, "note": note,
                                "attempts": attempts, "unverified": bad}
                print(f"  [{c['id']}] {len(good)} span(s), {attempts} attempt(s)"
                      + (f", {len(bad)} unverified" if bad else ""))
    out = {c["id"]: out[c["id"]] for c in claims if c["id"] in out}
    HUMAN_OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    hit = [k for k, v in out.items() if v["spans"]]
    miss = [k for k, v in out.items() if not v["spans"]]
    print(f"[human] {len(hit)}/{len(claims)} claims anchored -> {HUMAN_OUT}")
    print(f"[human] no span: {', '.join(miss) if miss else 'none'}")


# --------------------------------------------------------------------------- pass 2

def findable(quote, text, norm):
    return quote in text or re.sub(r"\s+", " ", quote).lower() in norm


def broken_pairs():
    """Every (report key, claim id) whose judge quote is not findable in the report."""
    claims = {c["id"]: c for i in range(1, 7)
              for c in json.loads((RUBRICS / f"rubric_{i}.json").read_text())["claims"]}
    pairs = []
    for d in REPORT_DIRS:
        for p in sorted((GRADED_INPUTS / d).glob("*.md")):
            key = re.sub(r"[^0-9a-zA-Z]+", "_", p.stem).strip("_")
            g = GRADED / f"graded_{key}.json"
            if not g.exists():
                print(f"  [warn] no grades for {d}/{p.name} (key {key})")
                continue
            text = p.read_text()
            norm = re.sub(r"\s+", " ", text).lower()
            for cid, sc in json.loads(g.read_text())["scores"].items():
                q = (sc.get("quote") or "").strip()
                if q and not findable(q, text, norm):
                    pairs.append({"key": key, "cid": cid, "path": p, "text": text,
                                  "quote": q, "reason": sc.get("reason", ""),
                                  "score": sc.get("score"),
                                  "claim": claims.get(cid, {}).get("claim", "")})
    return pairs


def report_prompt(pair):
    return f"""A judge graded the model-written audit report below against one claim, and
quoted the report as its evidence -- but the judge's quote does not actually occur in
the report: it was reworded or stitched together. Find the real passage the judge was
pointing at.

Return strict JSON: {{"spans": ["...", "..."], "note": "..."}}
  - 1 to 3 spans, each COPIED CHARACTER-FOR-CHARACTER from the MODEL REPORT below,
    each at least {MIN_SPAN} characters. A plain substring search must find them.
  - Anchor what the judge's quote and reasoning were actually about. If the report
    truly contains nothing corresponding to it, return "spans": [] -- do NOT
    substitute a passage that says something else.
  - Do NOT improve on the judge. The score below runs on a continuous 0-to-1 scale
    and says how COMPLETELY the report covers the claim, so a low or partial score
    is usually attached to a passage that only gestures at the point, states it
    vaguely, or gets part of it wrong. That is the passage to anchor. If a stronger,
    more complete passage exists elsewhere in the report, ignore it: the span must be
    the evidence for the score the judge actually gave, not the evidence you would
    have picked.
  - Keep markdown as it appears (bullets, "**", headings) if it falls inside a span.
  - "note": one sentence on what you anchored, or why nothing matched.

=== CLAIM BEING GRADED ({pair['cid']}) ===
{pair['claim']}

=== JUDGE'S SCORE (0 = absent, 1 = fully and accurately covered) ===
{pair['score']}

=== JUDGE'S QUOTE (not verbatim; this is the thing to repair) ===
{pair['quote']}

=== JUDGE'S REASON ===
{pair['reason']}

=== MODEL REPORT ===
{pair['text']}
"""


def run_reports(force):
    pairs = broken_pairs()
    keyed = {f"{p['key']}/{p['cid']}": p for p in pairs}
    print(f"[reports] {len(pairs)} unfindable (report, claim) pairs")
    prev = {} if not REPORTS_OUT.exists() else json.loads(REPORTS_OUT.read_text())
    # A regrade rewrites the judge's quotes, so a recorded repair is only reusable
    # while it still answers the quote the judge currently gives; anything else is
    # regenerated, and a pair that no longer needs repairing is dropped outright.
    dead = [k for k in prev if k not in keyed]
    out, todo = {}, []
    for k, p in keyed.items():
        e = prev.get(k)
        if e and not force and (e.get("judge_quote") or "").strip() == p["quote"].strip():
            out[k] = e
        else:
            todo.append(p)
    stale = sum(1 for p in todo if f"{p['key']}/{p['cid']}" in prev)
    print(f"[reports] reuse {len(out)}, regenerate {len(todo)} "
          f"({stale} stale quote, {len(todo) - stale} missing), drop {len(dead)} dead")
    if todo:
        with ThreadPoolExecutor(max_workers=12) as ex:
            futs = {ex.submit(anchor, report_prompt(p), p["text"]): p for p in todo}
            done = 0
            for f in as_completed(futs):
                p = futs[f]
                k = f"{p['key']}/{p['cid']}"
                try:
                    good, bad, note, attempts = f.result()
                except Exception as e:
                    print(f"  [{k}] FAILED: {e!r}")
                    continue
                out[k] = {"spans": good, "judge_quote": p["quote"], "attempts": attempts,
                          "note": note, "unverified": bad}
                done += 1
                print(f"  [{done}/{len(todo)}] {k}: {len(good)} span(s), "
                      f"{attempts} attempt(s)")
    out = {k: out[k] for k in keyed if k in out}
    REPORTS_OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    fixed = sum(1 for v in out.values() if v["spans"])
    spans = sum(len(v["spans"]) for v in out.values())
    print(f"[reports] {fixed} repaired, {len(out) - fixed} empty, "
          f"{len(pairs) - len(out)} unrecorded, {len(dead)} dropped, "
          f"{spans} spans -> {REPORTS_OUT}")


def main():
    args = sys.argv[1:]
    force = "--force" in args
    do_human = "--human" in args
    do_reports = "--reports" in args
    if not do_human and not do_reports:
        do_human = do_reports = True
    CLAIMS.mkdir(parents=True, exist_ok=True)
    print(f"model={MODEL} efforts={EFFORTS}")
    if do_human:
        run_human(force)
    if do_reports:
        run_reports(force)
    print(f"[total] {CALLS} Sol calls")


if __name__ == "__main__":
    main()
