#!/usr/bin/env python3
"""Join the verification results onto the merged AI Village findings, check their citations, build the review page.

    python3 viewers/build_aivillage_verified_review.py MERGED_FULL_JSON VERIFY_DIR DATA_DIR TEMPLATE_HTML OUT_DIR

Writes VERIFY_DIR/verified-all.json (each merged finding with its verification and the citation
check of its evidence) and OUT_DIR/{index.html,review.json}, one tab per verdict. TEMPLATE_HTML is
an existing findings-review page's index.html.
"""
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DOC = "https://docs.google.com/document/d/18990mApAhiePaBvboLdEJNPudffXaLdGaIVNUH58xSE/edit?tab=t.z1uie99jofwv"
ROOT = Path(__file__).resolve().parents[1]


def esc(text):
    return html.escape(str(text), quote=True)


def check_citations(results, data):
    """Run the citation checker on each finding's evidence text: {finding id: {citations, ok, failures}}."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for fid, r in results.items():
            path = Path(tmp) / f"{fid}.md"
            path.write_text("\n\n".join(str(sf.get("evidence", "")) for sf in r.get("subfindings", [])))
            paths.append(str(path))
        out = subprocess.run([sys.executable, str(ROOT / "scripts/check_aivillage_citations.py"), str(data), *paths, "--json"],
                             capture_output=True, text=True, check=True).stdout
    return {Path(c["report"]).stem: {"citations": c["citations"], "ok": c["counts"].get("ok", 0), "failures": c["failures"]}
            for c in json.loads(out)}


def main():
    merged_path, verify_dir, data, template, out = map(Path, sys.argv[1:6])
    merged = json.loads(merged_path.read_text())["merged"]
    results = {p.stem: json.loads(p.read_text()) for p in (verify_dir / "results").glob("*.json")}
    cites = check_citations(results, data) if results else {}
    joined = [{**m, "verification": results.get(m["id"]), "citation_check": cites.get(m["id"])} for m in merged]
    (verify_dir / "verified-all.json").write_text(json.dumps(joined, ensure_ascii=False, indent=2) + "\n")

    tabs = {k: {"cards": [], "panes": []} for k in ("keep", "needs rewording", "drop", "not checked")}
    for m in joined:
        v, c = m["verification"], m["citation_check"]
        key = v.get("verdict") if v and v.get("verdict") in tabs else "not checked"
        by_id = {sf.get("id"): sf for sf in (v or {}).get("subfindings", [])}
        notes = []
        if v:
            if v.get("proposed_headline"):
                notes.append("Proposed headline: " + v["proposed_headline"])
            if v.get("proposed_finding"):
                notes.append("Proposed finding: " + v["proposed_finding"])
            notes += [f"When it happened, per the records: {v.get('behavior_dates', '')}", f"How to find it: {v.get('how_to_find', '')}"]
            if c:
                notes.append(f"Citation check: {c['ok']} of {c['citations']} cited records exist and contain the quote.")
            notes += [f"Verifier's note: {n}" for n in v.get("notes", [])]
        pane = [f'<section data-uikit-section="evidence-{m["id"]}"><h3>{m["id"]} · {esc(m["headline"])}</h3>']
        subs = []
        for sf in m["subfindings"]:
            r = by_id.get(sf["id"], {})
            state = (f"{r.get('verdict', 'not checked')} · wording {r.get('wording', '?')} · confidence {r.get('confidence', '?')}"
                     + (" · needs reasoning traces" if r.get("needs_reasoning_traces") else "")) if r else "not checked"
            extra = [f"Problem with the wording: {r['wording_problem']}"] if r.get("wording_problem") else []
            extra += [f"Proposed wording: {r['proposed_claim']}"] if r.get("proposed_claim") else []
            extra += [f"Searched: {r['searched']}"] if r.get("searched") else []
            subs.append({"id": sf["id"], "claim": sf["claim"], "notes": sf.get("notes", []), "log_evidence": state,
                         "evidence_note": " ".join(extra),
                         "source_support": [{"quote": s["quote"], "location": "outside account · " + str(s.get("location", "")),
                                             "record_links": [{"label": "Source ↗", "url": s["url"]}] if s.get("url") else []}
                                            for s in sf["source_support"]]})
            pane.append(f"<p><strong>{sf['id']}</strong> — {esc(state)}</p><p>{esc(r.get('evidence', 'No verification result.'))}</p>")
        pane.append("</section><hr>")
        tabs[key]["cards"].append({"id": m["id"], "headline": m["headline"], "finding": m["finding"], "notes": notes + m["notes"],
                                   "subfindings": subs})
        tabs[key]["panes"].append("".join(pane))

    titles = {"keep": "Supported as written", "needs rewording": "Needs rewording", "drop": "Not supported by the records",
              "not checked": "Not checked yet"}
    intro = "What the verifier found in the Village records for each finding on the right, in the same order, with its citations."
    articles = [{"key": k.replace(" ", "-"), "title": titles[k], "url": DOC,
                 "html": f"<p><strong>{intro}</strong></p>" + "".join(t["panes"]),
                 "extraction": {"findings": t["cards"], "source_limits": [intro], "excluded_source_claims": []}}
                for k, t in tabs.items() if t["cards"]]
    counts = {k: len(t["cards"]) for k, t in tabs.items()}
    total_c, ok_c = sum(c["citations"] for c in cites.values()), sum(c["ok"] for c in cites.values())
    out.mkdir(parents=True, exist_ok=True)
    (out / "review.json").write_text(json.dumps({"model": "Claude Sonnet 5.5", "reasoning_effort": None, "prompt_url": DOC,
                                                 "articles": articles, "counts": counts,
                                                 "citations": {"total": total_c, "ok": ok_c}}, ensure_ascii=False, indent=2))
    page = template.read_text()
    start = page.index("document.querySelector('header p').textContent=`")
    end = page.index("`;", start) + 2
    header = ("document.querySelector('header p').textContent=`Merged findings checked against the Village records by ${data.model}: "
              "${data.counts.keep} supported as written, ${data.counts['needs rewording']} need rewording, ${data.counts.drop} not supported, "
              "${data.counts['not checked']} not checked. ${data.citations.ok} of ${data.citations.total} cited records exist and contain their quote. "
              "Select text or use 💬 to comment; Keep / Revise / Drop choices save automatically.`;")
    page = page[:start] + header + page[end:]
    title = page[page.index("<title>") + 7:page.index("</title>")]
    page = page.replace(title, "AI Village findings — checked against the records").replace("Log evidence: ", "Records: ")
    for old in ("Extracted findings", "Substack source", "Source article"):
        page = page.replace(old, "What the records show")
    (out / "index.html").write_text(page)
    print(json.dumps({"counts": counts, "citations": {"total": total_c, "ok": ok_c}}))


if __name__ == "__main__":
    main()
