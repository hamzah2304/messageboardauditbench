#!/usr/bin/env python3
"""Build the review page for the merged AI Village findings.

    python3 viewers/build_aivillage_merge_review.py MERGED_FULL_JSON MERGE_INPUT_DIR TEMPLATE_HTML OUT_DIR

Reuses the findings-review page (TEMPLATE_HTML is an existing review page's index.html). Three
tabs: findings merged from several extracted findings, findings kept unchanged, and dropped
findings. The left pane shows the extracted findings each merged finding was built from.
"""
import html
import json
import sys
from pathlib import Path

DOC = "https://docs.google.com/document/d/18990mApAhiePaBvboLdEJNPudffXaLdGaIVNUH58xSE/edit?tab=t.wk9kswq4iols"
KIND = {"S": "Substack", "X": "X", "D": "Discord"}


def esc(text):
    return html.escape(str(text), quote=True)


def extracted_html(f):
    """One extracted finding as it went into the merge, quotes included."""
    src = f["source"]
    label = src.get("title") or src.get("author") or src.get("channel") or ""
    parts = [f'<section data-uikit-section="source-{f["id"]}"><h3>{f["id"]} · {esc(f["headline"])}</h3>',
             f'<p><em>{KIND[f["id"][0]]} · {esc(label)} · published {f["source_date"]} · '
             f'<a target="_blank" rel="noopener" href="{esc(src["url"])}">source ↗</a></em></p>',
             f'<p>{esc(f["finding"])}</p>']
    for sf in f["subfindings"]:
        parts.append(f'<p><strong>{sf["id"]}</strong> {esc(sf["claim"])}</p>')
        parts += [f'<blockquote>{esc(s["quote"])}</blockquote>' for s in sf["source_support"]]
    return "".join(parts) + "</section><hr>"


def main():
    full = json.loads(Path(sys.argv[1]).read_text())
    source_dir, template, out = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    extracted = {p.stem: json.loads(p.read_text()) for p in (source_dir / "findings").glob("*.json")}

    def card(m):
        ids = [s["id"] for s in m["sources"]]
        notes = ([f"Why merged: {m['merge_note']}"] if m.get("merge_note") else []) + list(m["notes"])
        subs = [{"id": sf["id"], "claim": sf["claim"], "notes": sf["notes"], "log_evidence": sf["log_evidence"],
                 "evidence_note": "Built from " + ", ".join(sf["from"]) + ".",
                 "source_support": [{"quote": s["quote"], "location": f'{s["from"]} · {s.get("location", "")}',
                                     "record_links": [{"label": "Source ↗", "url": s["url"]}] if s.get("url") else []}
                                    for s in sf["source_support"]]} for sf in m["subfindings"]]
        return {"id": m["id"], "headline": f'{m["headline"]}  [{", ".join(ids)}]', "finding": m["finding"],
                "notes": notes, "subfindings": subs}, "".join(extracted_html(extracted[i]) for i in ids)

    def tab(key, title, items, intro):
        cards, panes = zip(*(card(m) for m in items)) if items else ((), ())
        return {"key": key, "title": title, "url": DOC, "html": f"<p><strong>{esc(intro)}</strong></p>" + "".join(panes),
                "extraction": {"findings": list(cards), "source_limits": [intro], "excluded_source_claims": []}}

    merged = [m for m in full["merged"] if len(m["sources"]) > 1]
    single = [m for m in full["merged"] if len(m["sources"]) == 1]
    dropped = [{"id": d["id"], "headline": d["finding"]["headline"], "finding": "Dropped: " + d["reason"], "notes": [],
                "merge_note": "", "sources": [{"id": d["id"]}],
                "subfindings": [{"id": sf["id"], "from": [sf["id"]], "claim": sf["claim"], "notes": [], "log_evidence": "not yet verified",
                                 "source_support": [{**s, "from": sf["id"]} for s in sf["source_support"]]}
                                for sf in d["finding"]["subfindings"]]} for d in full["dropped"]]
    tabs = [tab("merged", "Merged from several findings", merged,
                "Each finding on the right combines the extracted findings shown here, in the same order."),
            tab("unchanged", "Kept unchanged", single, "Extracted findings that matched nothing else and were passed through as they were."),
            tab("dropped", "Dropped", dropped, "Extracted findings the merge step dropped, each with its reason.")]
    tabs[2]["extraction"]["excluded_source_claims"] = [
        {"claim": f'{d["id"]}: {d["subfinding"]["claim"]}', "reason": d["reason"]} for d in full["dropped_subfindings"]]
    data = {"model": "Claude Opus 5.5", "reasoning_effort": None, "prompt_url": DOC, "articles": tabs,
            "counts": {"extracted": len(extracted), "merged": len(full["merged"]), "combined": len(merged),
                       "unchanged": len(single), "dropped": len(dropped)}}
    (out / "review.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))

    page = template.read_text()
    start = page.index("document.querySelector('header p').textContent=`")
    end = page.index("`;", start) + 2
    header = ("document.querySelector('header p').textContent=`${data.counts.extracted} extracted findings from Substack, X and Discord "
              "became ${data.counts.merged}: ${data.counts.combined} combine several extracted findings, ${data.counts.unchanged} are unchanged, "
              "${data.counts.dropped} were dropped. Merged by ${data.model}; not yet checked against the Village records. "
              "Select text or use 💬 to comment; Keep / Revise / Drop choices save automatically.`;")
    page = page[:start] + header + page[end:]
    for old, new in [("What Sol left out", "Subfindings dropped as restatements"), ("Substack source", "Extracted findings"),
                     ("Source article", "Extracted findings")]:
        page = page.replace(old, new)
    a = page.index("if(extraction.status!=='pending'){const download=")
    b = page.index("root.append(download);}", a) + len("root.append(download);}")
    page = page[:a] + page[b:]
    title_start, title_end = page.index("<title>") + 7, page.index("</title>")
    old_title = page[title_start:title_end]
    page = page.replace(old_title, "AI Village findings — merged across sources")
    (out / "index.html").write_text(page)
    print(json.dumps(data["counts"]))


if __name__ == "__main__":
    main()
