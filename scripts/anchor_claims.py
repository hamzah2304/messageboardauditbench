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

  --v2       the same job for the auditor's finer 39-claim list, whose entries carry
             no rubric quote to hint from and where a claim may genuinely have no
             support in the report. Fills "spans" and "report_quote" in place in
             benchmark/claims/claims_v2.json, leaving anchors_human.json (still live
             in the audit UI) alone. Resumable: a claim with spans is skipped.
             -> benchmark/claims/claims_v2.json

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

Why the second pass exists at all: 8.2% of the recall judge's non-empty quotes (166 of
2,034) are not findable in the report they grade. The contradiction rubric in
benchmark/graded/contradiction/ misses on only 5.1% (9 of 177) over the same 109
reports. The asymmetry is the expected one -- a contradiction quote has to point at
something the report actually said, whereas a recall quote can be the judge
paraphrasing an absence or stitching together evidence scattered across sections --
so it is recall grades whose quotes need repairing before a UI can highlight them.

Both output files are resumable: --human skips a claim already recorded, and --reports
skips a pair whose recorded judge_quote still matches the quote the judge currently
gives. A regrade rewrites those quotes, so --reports also regenerates any entry whose
quote has moved on and drops any entry whose pair no longer needs repairing at all --
re-running it after a regrade costs only the pairs that actually changed. --force
redoes everything.

    scripts/anchor_claims.py [--human] [--reports] [--v2] [--force]   (none = human+reports)
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
CLAIMS_V2 = CLAIMS / "claims_v2.json"
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


# ------------------------------------------------------------------------ pass 1b

def v2_prompt(article, claim):
    """Like human_prompt, but for the auditor's finer v2 claim list.

    No rubric hint exists for these, and the list is deliberately fine-grained -- two
    v2 claims may legitimately land on the same sentence -- so the prompt asks for a
    quote as well as spans and is explicit that an unsupported claim gets nothing.
    """
    note = claim.get("note") or ""
    return f"""Below is the full text of a published incident report, then a claim drawn
from it. Find where in the report that claim is stated.

Return strict JSON: {{"spans": ["...", "..."], "quote": "...", "note": "..."}}
  - 1 to 3 spans, each COPIED CHARACTER-FOR-CHARACTER from the REPORT TEXT below,
    each at least {MIN_SPAN} characters. A plain substring search must find them.
  - Prefer whole sentences that state the claim, including any figures, names,
    handles or spellings it depends on. If the claim carries a specific -- a
    duration, a hostname, a provider list, an account name, an unusual character --
    anchor the sentence that carries that specific, not a general one nearby.
  - If several separated sentences are needed, return them as separate spans; never
    join them with " ... ".
  - "quote": the single most representative span, the one sentence a human would
    quote to show the report makes this claim. It too must be COPIED
    CHARACTER-FOR-CHARACTER from the report text -- it may be one of your spans, or
    a shorter contiguous run inside one if a span is very long. Do not stitch.
  - IMPORTANT: this claim list is finer-grained than the report's own structure, and
    some claims may simply not be supported anywhere in the report. If the report
    does not state this claim, return {{"spans": [], "quote": "", "note": "why"}}.
    Do NOT reach for a loosely related or merely adjacent sentence: an empty result
    is far more useful than a wrong anchor. It is fine for a span to be one another
    claim also anchors to.
  - "note": one sentence on what you anchored, or why nothing matched.

=== CLAIM ({claim['id']}, section "{claim.get('section', '')}") ===
{claim['claim']}

=== GRADING NOTE (what the auditor considers the load-bearing part of this claim) ===
{note or "(none)"}

=== REPORT TEXT ===
{article}
"""


def parse_v2(raw):
    try:
        data = json.loads(raw)
    except Exception:
        return [], "", ""
    spans = data.get("spans") or []
    if isinstance(spans, str):
        spans = [spans]
    spans = [s for s in spans if isinstance(s, str) and s.strip()]
    return spans[:3], str(data.get("quote") or ""), str(data.get("note") or "")


def anchor_v2(prompt, source, tries=2):
    """anchor(), plus a representative quote that is validated the same way.

    The quote is held to the same literal-substring test as the spans; a quote that
    fails, or that the model omits, falls back to the shortest validated span so the
    rubric sheet never prints something the report does not say.
    """
    good, bad, note, quote, attempts = [], [], "", "", 0
    msg = prompt
    while attempts < tries:
        attempts += 1
        spans, q, note = parse_v2(sol(SYS, msg))
        bad = []
        for s in spans:
            s = s.strip()
            if s in source and len(s) >= MIN_SPAN:
                if s not in good:
                    good.append(s)
            elif s:
                if s not in bad:
                    bad.append(s)
        q = (q or "").strip()
        if q and q in source and len(q) >= MIN_SPAN:
            quote = q
        elif q:
            bad.append(q)
        if not bad or attempts >= tries:
            break
        msg = (prompt + "\n\n=== RETRY ===\nSome of your strings were rejected. These "
               "were NOT found in the document by an exact substring search:\n"
               + "\n".join(f"  - {b!r}" for b in bad)
               + "\nYou must COPY the text out of the document exactly as it appears -- "
                 "same words, same punctuation, same spacing, no ' ... ' elisions, no "
                 "paraphrase, no summarising. Each span and the quote must be at least "
               f"{MIN_SPAN} characters. Try again, and return only strings you have "
               "checked occur literally in the document. If the claim is genuinely "
               "unsupported, return empty spans rather than guessing.")
    good = good[:3]
    if good and quote not in good and quote not in source:
        quote = ""
    if not quote and good:
        quote = min(good, key=len)
    if not good:
        quote = ""
    return good, quote, bad, note, attempts


def run_v2(force):
    """Fill report_quote + spans on every claim in benchmark/claims/claims_v2.json.

    Rewrites that file in place, preserving id/section/claim/descends_from/note and
    the claim order; anchors_human.json (v1, live in the audit UI) is untouched.
    """
    article = article_text()
    doc = json.loads(CLAIMS_V2.read_text())
    claims = doc["claims"]
    todo = [c for c in claims if force or not c.get("spans")]
    print(f"[v2] {len(claims)} claims, {len(todo)} to do "
          f"(article {len(article)/1000:.0f} KB)")
    if todo:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(anchor_v2, v2_prompt(article, c), article): c for c in todo}
            for f in as_completed(futs):
                c = futs[f]
                try:
                    good, quote, bad, note, attempts = f.result()
                except Exception as e:
                    print(f"  [{c['id']}] FAILED: {e!r}")
                    continue
                c["spans"] = good
                c["report_quote"] = quote
                c["anchor_note"] = note
                if bad:
                    c["unverified"] = bad
                else:
                    c.pop("unverified", None)
                print(f"  [{c['id']}] {len(good)} span(s), {attempts} attempt(s)"
                      + (f", {len(bad)} unverified" if bad else ""))
    for c in claims:
        for s in c.get("spans", []):
            assert s in article, f"{c['id']}: span not in article"
        assert not c.get("report_quote") or c["report_quote"] in article, c["id"]
    CLAIMS_V2.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    hit = [c["id"] for c in claims if c.get("spans")]
    miss = [c["id"] for c in claims if not c.get("spans")]
    print(f"[v2] {len(hit)}/{len(claims)} claims anchored, "
          f"{sum(len(c.get('spans', [])) for c in claims)} spans -> {CLAIMS_V2}")
    print(f"[v2] no span: {', '.join(miss) if miss else 'none'}")


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
    do_v2 = "--v2" in args
    if not do_human and not do_reports and not do_v2:
        do_human = do_reports = True
    CLAIMS.mkdir(parents=True, exist_ok=True)
    print(f"model={MODEL} efforts={EFFORTS}")
    if do_human:
        run_human(force)
    if do_v2:
        run_v2(force)
    if do_reports:
        run_reports(force)
    print(f"[total] {CALLS} Sol calls")


if __name__ == "__main__":
    main()
