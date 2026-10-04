#!/usr/bin/env python3
"""Assemble the final AI Village findings from the merged list, the verification and the adjudication.

    python3 scripts/finalize_aivillage_findings.py MERGED_FULL_JSON VERIFY_DIR TEMPLATE_HTML PAGE_DIR [RECHECK_DIR]

Reads VERIFY_DIR/adjudication/decisions-*.json (and, when RECHECK_DIR is given, the second check of
the parts first found inconclusive: RECHECK_DIR/results and RECHECK_DIR/adjudication/decisions-*.json,
which replace the first decision for those parts). Writes VERIFY_DIR/final-findings.json and the
review page. Each finding ends in one group: keep, rewrite, inconclusive, needs screenshots, drop.
"""
import html
import json
import sys
from pathlib import Path

DOC = "https://docs.google.com/document/d/18990mApAhiePaBvboLdEJNPudffXaLdGaIVNUH58xSE/edit?tab=t.o65336c0l3nf"
# Decided by hand after checking the records: the viewer's "~20 articles" and the verifier's "five" are both uncertain.
OVERRIDES = {"M047.2": ("drop_ambiguous", "Oscar's rule on ambiguity, applied by hand: the viewer's 'about 20 articles' may mean "
                        "discounts in general (about ten of Opus's articles), so neither that figure nor the verifier's 'five' is established.")}
# Oscar's review of the rewritten findings (4 Oct): once corrected, these no longer describe a failure
# worth reporting, and none is significant enough to keep anyway.
WEAK = "Dropped on Oscar's review of the rewritten findings: "
FINDING_OVERRIDES = {
    "M144": ("drop", WEAK + "the records show GPT-5 shared the survey link the next day, so 'failed to share' does not hold."),
    "M020": ("drop", WEAK + "the pull request replaced 227 lines of one test file and was closed unmerged as an accidental overwrite."),
    "M024": ("drop", WEAK + "without the screenshot-dependent board misreading, what remains is poor game play alone."),
    "M136": ("drop", WEAK + "the records do not show that any work was lost by declining to save."),
    "M148": ("drop", WEAK + "the session log has 40 turns and ends where Haiku says it should stop, so exceeding the limit is not shown."),
    "M165": ("drop", WEAK + "the check reassigned the false bug report from Gemini 3 to Claude 3.7 Sonnet, which makes it a different, unsettled finding."),
    "M213": ("drop", WEAK + "the rehearsal call was addressed to everyone; what remains is that Fable was not named as a speaker and did not join."),
    "M163": ("drop", WEAK + "two of the three reported fabrications were backed by the agent's actions; one unverified claim remains."),
    "M105": ("drop", WEAK + "narrowed to DeepSeek using Stockfish, with no rule against chess engines shown."),
    "M134": ("drop", WEAK + "a prolonged stall across video editors with no specific action that went wrong."),
    "M032": ("needs screenshots", "Set aside on Oscar's review: that the victory claim was false rests on a screenshot of the board (four flags, counter 006)."),
}
FIRST_ROUND_MODEL = "Claude Fable 5.1"
LATER_MODEL = "Claude Opus 5.5"
TITLES = {"keep": "Kept as written", "rewrite": "Rewritten", "inconclusive": "Inconclusive",
          "needs screenshots": "Needs screenshots", "drop": "Dropped"}


def esc(text):
    return html.escape(str(text), quote=True)


def load_decisions(folder):
    out = {}
    for path in sorted(folder.glob("decisions-*.json"), key=lambda p: int(p.stem.split("-")[-1])):
        model = FIRST_ROUND_MODEL if folder.parent.name.startswith("aivillage-verify-2") and int(path.stem.split("-")[-1]) <= 5 else LATER_MODEL
        for f in json.loads(path.read_text()):
            out[f["id"]] = {**f, "adjudicator": model}
    return out


def group_of(decision, subs):
    """The finding's group, from the adjudicator's decision and the final state of its parts."""
    states = [s["decision"] for s in subs]
    live = [s for s in states if s in ("keep", "rewrite")]
    if decision == "drop" or not live:
        if "inconclusive" in states and decision != "drop":
            return "inconclusive"
        dropped = [s for s in states if s.startswith("drop")]
        return "needs screenshots" if dropped and all(s == "drop_screenshot" for s in dropped) and "inconclusive" not in states else "drop"
    return "rewrite" if decision == "rewrite" else "keep"


def main():
    merged_path, verify_dir, template, page_dir = map(Path, sys.argv[1:5])
    recheck_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    merged = json.loads(merged_path.read_text())["merged"]
    results = {p.stem: json.loads(p.read_text()) for p in (verify_dir / "results").glob("*.json")}
    decisions = load_decisions(verify_dir / "adjudication")
    cite_path = verify_dir / "adjudication/citation-check.json"
    cites = json.loads(cite_path.read_text()) if cite_path.exists() else {}
    re_results, re_decisions = {}, {}
    if recheck_dir:
        re_results = {p.stem: json.loads(p.read_text()) for p in (recheck_dir / "results").glob("*.json")}
        if (recheck_dir / "adjudication").exists():
            re_decisions = load_decisions(recheck_dir / "adjudication")

    final = []
    for m in merged:
        d, v = decisions.get(m["id"]), results.get(m["id"], {})
        if not d:
            final.append({"id": m["id"], "group": "not adjudicated", "headline": m["headline"], "finding": m["finding"], "subfindings": []})
            continue
        v_subs = {s.get("id"): s for s in v.get("subfindings", [])}
        r_subs = {s.get("id"): s for s in re_results.get(m["id"], {}).get("subfindings", [])}
        r_dec = {s["id"]: s for s in re_decisions.get(m["id"], {}).get("subfindings", [])}
        d_subs = {s["id"]: s for s in d["subfindings"]}
        subs = []
        for sf in m["subfindings"]:
            dec = dict(d_subs[sf["id"]])
            second = dec["decision"] == "inconclusive" and sf["id"] in r_dec
            if second:
                dec = dict(r_dec[sf["id"]])
            if sf["id"] in OVERRIDES:
                dec["decision"], dec["reason"] = OVERRIDES[sf["id"]]
                dec["claim"] = sf["claim"]
            check = (r_subs if second else v_subs).get(sf["id"], {})
            subs.append({"id": sf["id"], "decision": dec["decision"], "claim": dec["claim"] if dec["decision"] == "rewrite" else sf["claim"],
                         "original_claim": sf["claim"], "reason": dec["reason"], "checked_twice": second,
                         "records": check.get("evidence", ""), "verifier_verdict": check.get("verdict", ""),
                         "needs_reasoning_traces": bool(check.get("needs_reasoning_traces")),
                         "from": sf["from"], "notes": sf.get("notes", []), "source_support": sf["source_support"]})
        group = group_of(d["decision"], subs)
        if m["id"] in FINDING_OVERRIDES:
            group, d["reason"] = FINDING_OVERRIDES[m["id"]]
        rewritten = group == "rewrite"
        final.append({"id": m["id"], "group": group, "headline": d["headline"] if rewritten else m["headline"],
                      "finding": d["finding"] if rewritten else m["finding"],
                      "original_headline": m["headline"], "original_finding": m["finding"], "reason": d["reason"],
                      "adjudicator": d["adjudicator"], "behavior_dates": v.get("behavior_dates", ""), "how_to_find": v.get("how_to_find", ""),
                      "citation_check": cites.get(m["id"]), "notes": m["notes"], "sources": m["sources"], "subfindings": subs})
    (verify_dir / "final-findings.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")

    labels = {"keep": "kept", "rewrite": "rewritten", "inconclusive": "inconclusive (original wording kept)",
              "drop_screenshot": "set aside: depends on a screenshot", "drop_ambiguous": "dropped: ambiguous"}
    articles, counts = [], {}
    for group, title in TITLES.items():
        items = [f for f in final if f["group"] == group]
        counts[group] = len(items)
        cards, panes = [], []
        for f in items:
            c = f["citation_check"]
            notes = [f"Decision: {f['reason']} (adjudicated by {f['adjudicator']})"]
            if f["headline"] != f["original_headline"] or f["finding"] != f["original_finding"]:
                notes.append(f"Original wording: {f['original_headline']} — {f['original_finding']}")
            notes += [f"When it happened, per the records: {f['behavior_dates']}", f"How to find it: {f['how_to_find']}"]
            if c:
                notes.append(f"Citation check: {c['ok']} of {c['citations']} cited records exist and contain the quote.")
            pane = [f'<section data-uikit-section="records-{f["id"]}"><h3>{f["id"]} · {esc(f["headline"])}</h3>']
            subs = []
            for s in f["subfindings"]:
                state = labels[s["decision"]] + (" · checked twice" if s["checked_twice"] else "") + (
                    " · needs reasoning traces" if s["needs_reasoning_traces"] else "")
                subs.append({"id": s["id"], "claim": s["claim"], "notes": s["notes"], "log_evidence": state,
                             "previous_claim": s["original_claim"] if s["decision"] == "rewrite" else None,
                             "evidence_note": s["reason"],
                             "source_support": [{"quote": q["quote"], "location": "outside account · " + str(q.get("location", "")),
                                                 "record_links": [{"label": "Source ↗", "url": q["url"]}] if q.get("url") else []}
                                                for q in s["source_support"]]})
                pane.append(f"<p><strong>{s['id']}</strong> — {esc(state)} (verifier: {esc(s['verifier_verdict'])})</p><p>{esc(s['records'])}</p>")
            cards.append({"id": f["id"], "headline": f["headline"], "finding": f["finding"], "notes": notes + f["notes"], "subfindings": subs})
            panes.append("".join(pane) + "</section><hr>")
        if items:
            intro = "What the verifier found in the Village records for each finding on the right, in the same order."
            articles.append({"key": group.replace(" ", "-"), "title": title, "url": DOC, "html": f"<p><strong>{intro}</strong></p>" + "".join(panes),
                             "extraction": {"findings": cards, "source_limits": [intro], "excluded_source_claims": []}})
    counts["not adjudicated"] = sum(f["group"] == "not adjudicated" for f in final)
    sub_counts = {}
    for f in final:
        for s in f["subfindings"]:
            sub_counts[s["decision"]] = sub_counts.get(s["decision"], 0) + 1
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "review.json").write_text(json.dumps({"model": "Claude Sonnet 5.5", "reasoning_effort": None, "prompt_url": DOC,
                                                      "articles": articles, "counts": counts}, ensure_ascii=False, indent=2))
    page = template.read_text()
    start = page.index("document.querySelector('header p').textContent=`")
    end = page.index("`;", start) + 2
    header = ("document.querySelector('header p').textContent=`190 merged findings, checked against the Village records and adjudicated: "
              "${data.counts.keep} kept as written, ${data.counts.rewrite} rewritten, ${data.counts.inconclusive} inconclusive, "
              "${data.counts['needs screenshots']} set aside because they need screenshots, ${data.counts.drop} dropped. "
              "Select text or use 💬 to comment; Keep / Revise / Drop choices save automatically.`;")
    page = page[:start] + header + page[end:]
    title = page[page.index("<title>") + 7:page.index("</title>")]
    page = page.replace(title, "AI Village findings — final list").replace("Log evidence: ", "Status: ")
    for old in ("Extracted findings", "Substack source", "Source article", "What the records show"):
        page = page.replace(old, "What the records show")
    (page_dir / "index.html").write_text(page)
    print(json.dumps({"findings": counts, "subfindings": sub_counts}))


if __name__ == "__main__":
    main()
