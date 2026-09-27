#!/usr/bin/env python3
"""Build viewers/urlquery_audit.html: audit the URLQuery finding judge, finding by finding.

The URLQuery counterpart of viewers/build_audit_ui.py (the message-board audit page), with
the same look and workflow, adapted to the finding-sheet grading scheme: each model report
is graded against 12 headline findings, each finding by one judge call that scores the
finding (0-1, one decimal) and each of its sub-findings (quarters).

Inputs
- grades   reports/urlquery/graded/judge_<JUDGE>/<run>.json   (read only; may be mid-write)
- reports  runs/urlquery/<run>/report.md
- findings benchmarks/urlquery/claims/findings_v1.json         (not-scored items skipped)
- scales   benchmarks/urlquery/judge/finding_sheet_v1.md        (both tables parsed here)
- article  data/transluce/agent-activity.html, made inert by build_urlquery_findings.InertPage

Outputs (all gitignored: the reports can quote recorded secrets)
- viewers/urlquery_audit.html                  the page, with scores only
- viewers/data/urlquery_audit/<run>.json       report text, judge quotes/reasons, highlight ranges
- viewers/data/urlquery_audit/_article.html    the article, inert, for the right-hand pane

The page saves to benchmarks/urlquery/audit/judge_audit_<judge>.json through
scripts/html_viewer.py (POST /save), with a localStorage mirror when the server is away.

Quotes are matched exactly, then with whitespace/quote/dash/Markdown normalisation (link
syntax, emphasis and table pipes dropped). A quote that still does not occur is shown as
"no anchor"; nothing is highlighted approximately.

    uv run python viewers/build_urlquery_audit_ui.py [--judge claude-opus-5-5]
    python3 scripts/html_viewer.py 8799   # then open http://localhost:8799/urlquery_audit.html
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "benchmarks" / "urlquery" / "judge"))
import build_urlquery_findings as BF  # noqa: E402  (InertPage, fetch_assets)
import render_sheet  # noqa: E402  (load_findings, linked_scans)

SHEET = ROOT / "benchmarks" / "urlquery" / "judge" / "finding_sheet_v1.md"
ARTICLE_SRC = ROOT / "data" / "transluce" / "agent-activity.html"
RUNS = ROOT / "runs" / "urlquery"
GRADED = ROOT / "reports" / "urlquery" / "graded"
OUT = HERE / "urlquery_audit.html"
DATA_DIR = HERE / "data" / "urlquery_audit"
ARTICLE_HTML = DATA_DIR / "_article.html"
AUDIT_DIR = ROOT / "benchmarks" / "urlquery" / "audit"
CORPUS = ROOT / "corpus"
FONTS = CORPUS / "fonts"
# The article's per-link "full URL" margin notes sit inside sentences in textContent; the
# finding quotes were taken without them, so the anchoring walk skips these classes.
SKIP_CLASSES = ["margin-note"]

# Handles for the scale buttons. The full wording always comes from the sheet's tables.
SCALE_SHORT = {"1.0": "near-paraphrase", "0.9": "90% of the value", "0.7": "core there",
               "0.5": "gist, not story", "0.3": "pieces, untied", "0.0": "absent"}
SUB_SHORT = {"1": "specifics + scan", "0.75": "minor miss / no scan", "0.5": "core, misses a specific",
             "0.25": "related, wrong level", "0": "absent / wrong"}

TASK_INTRO = [
    "You are checking a language-model judge. Each model report was graded against twelve "
    "headline findings from Transluce's article; for each finding the judge scored the finding "
    "as a whole (0 to 1, one decimal) and each of its sub-findings (in quarters), and quoted the "
    "line of the report it scored from. The left pane is the model report with those quotes "
    "highlighted; the right pane is Transluce's article with the finding's passages anchored.",
    "Decide whether each call is right, at both levels. The verdict buttons say what kind of "
    "mistake it is, if any; “Your score” is the number you would have given. The "
    "contradicted flag is audited separately. Links the report makes to one of the finding's "
    "listed scans are marked in the report when the finding is selected.",
    "Findings the judge did not score (refused, unparseable, API error, truncated) are shown as "
    "UNSCORED with the reason, never as 0; findings not graded yet say so.",
    "Everything saves itself to one shared file, under your name, so two people can audit the "
    "same item and the page shows where you disagree.",
]


def slug(s: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")


# ---------------------------------------------------------------- the sheet's scales
def sheet_tables(text: str) -> list[list[tuple[str, str]]]:
    """Every Markdown table in the sheet, as (first cell, second cell) rows without header."""
    tables, cur = [], []
    for line in text.splitlines():
        if line.startswith("|"):
            cur.append(line)
            continue
        if cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    out = []
    for t in tables:
        rows = []
        for line in t[2:]:  # header, then the ---: separator
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2:
                rows.append((cells[0], cells[1]))
        out.append(rows)
    return out


def sheet_paragraph(text: str, lead: str) -> str:
    for para in text.split("\n\n"):
        if para.startswith(lead):
            return re.sub(r"\*\*|\*", "", para).strip()
    raise SystemExit(f"paragraph {lead!r} not found in {SHEET}")


def sheet_scales():
    """(finding scale, sub-finding scale, reference-point rule, contradiction rule), read
    from the prompt itself so the page cannot drift from what the judge was told."""
    text = SHEET.read_text()
    tables = sheet_tables(text)
    if len(tables) < 2:
        raise SystemExit(f"expected two scale tables in {SHEET}, found {len(tables)}")
    sub_rows, fin_rows = tables[0], tables[1]
    if [k for k, _ in sub_rows] != list(SUB_SHORT) or [k for k, _ in fin_rows] != list(SCALE_SHORT):
        raise SystemExit(f"scale values in {SHEET.name} changed: {[k for k, _ in sub_rows]} / "
                         f"{[k for k, _ in fin_rows]}; update SUB_SHORT / SCALE_SHORT")
    fin = [{"v": float(k), "key": k, "short": SCALE_SHORT[k], "full": t} for k, t in fin_rows]
    sub = [{"v": float(k), "key": k, "short": SUB_SHORT[k], "full": t} for k, t in sub_rows]
    return (fin, sub, sheet_paragraph(text, "**From sub-findings to the finding.**"),
            sheet_paragraph(text, "**Errors are recorded separately.**"))


# ---------------------------------------------------------------- quote matching
TRANS = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
         "‑": "-", " ": " ", "​": ""}
DROP = set("*`_|\\[]")
LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\s]*)\)")
ELLIPSIS = re.compile(r"\s*(?:…|\.\.\.)\s*")


def link_syntax(text: str) -> set[int]:
    """Offsets of the `[` and `](url)` of every Markdown link: rendered, only the text shows."""
    out = set()
    for m in LINK.finditer(text):
        out.add(m.start())
        out.update(range(m.end(1), m.end()))
    return out


def norm_map(s: str, skip: set[int] | frozenset = frozenset()):
    """Lower-case, fold quotes/dashes, drop Markdown syntax, collapse whitespace.
    Returns (normalised string, list mapping each normalised char to its source offset)."""
    out, offs, prev_space = [], [], True
    for i, ch in enumerate(s):
        if i in skip:
            continue
        c = TRANS.get(ch, ch).lower()
        if c == "" or c in DROP:
            continue
        if c.isspace():
            if prev_space:
                continue
            c, prev_space = " ", True
        else:
            prev_space = False
        out.append(c)
        offs.append(i)
    return "".join(out), offs


class Doc:
    def __init__(self, text: str):
        self.text = text
        self.norm, self.offs = norm_map(text, link_syntax(text))

    def _one(self, q: str):
        i = self.text.find(q)
        if i >= 0:
            return [i, i + len(q)], "exact"
        pn = norm_map(q, link_syntax(q))[0].strip()
        if len(pn) < 4:
            return None, "none"
        j = self.norm.find(pn)
        if j < 0:
            return None, "none"
        return [self.offs[j], self.offs[j + len(pn) - 1] + 1], "norm"

    def find(self, quote_: str):
        """Exact, then normalised. A quote the judge elided with an ellipsis matches only if
        every piece occurs in order. Nothing approximate."""
        q = (quote_ or "").strip().strip('"“”')
        if len(q) < 4:
            return [], "none"
        rng, how = self._one(q)
        if rng:
            return [rng], how
        pieces = [p for p in ELLIPSIS.split(q) if p.strip()]
        if len(pieces) < 2 or any(len(p.strip()) < 8 for p in pieces):
            return [], "none"
        out, hows, last = [], set(), -1
        for p in pieces:
            rng, how = self._one(p.strip())
            if not rng or rng[0] < last:
                return [], "none"
            out.append(rng)
            hows.add(how)
            last = rng[1]
        return out, "pieces" if hows == {"exact"} else "pieces-norm"


# ---------------------------------------------------------------- the article pane
ARTICLE_SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>Transluce article (inert copy)</title>
<style>%s</style>
<style>
/* audit overrides: the article alone, in a narrow pane, with anchor highlights */
body{padding:0 18px}
mark[data-audit]{background:#EEF1F8;border-radius:3px;padding:0 1px;cursor:pointer;color:inherit}
mark[data-audit].grp{background:#FDF2EC}
mark[data-audit].sel{background:#FBE3D6;outline:2px solid #C15F3C}
@keyframes auditflash{0%%{background:#F3BF9C}100%%{background:#FBE3D6}}
mark[data-audit].flash{animation:auditflash 1.1s ease-out}
@media (prefers-reduced-motion:reduce){mark[data-audit].flash{animation:none}}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
</style></head>
<body>%s</body></html>
"""


def write_article_html() -> str:
    """The article with every script, handler, form and remote embed removed (the findings
    extractor's InertPage) and its stylesheet from the local asset cache. Never fetches: an
    asset missing from the cache is an error, not a download."""
    def offline(*_a, **_k):
        raise SystemExit(f"a Transluce asset is missing from {BF.DEFAULT_ASSETS}; run "
                         "viewers/build_urlquery_findings.py once to cache it")
    BF.urllib.request.urlopen = offline
    src = ARTICLE_SRC.read_text()
    css, images = BF.fetch_assets(src, BF.DEFAULT_ASSETS)
    parser = BF.InertPage(images)
    parser.feed(src)
    page = "".join(parser.parts)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLE_HTML.write_text(ARTICLE_SHELL % (css.replace("</style", "<\\/style"), page), encoding="utf-8")
    return page


def font_css() -> str:
    """The et-book @font-face rules of the message-board page, pointed at /file?p=, so the
    model report reads in the same serif as the old audit page. Empty if the fonts are absent."""
    tokens = CORPUS / "wiki_tokens.css"
    if not tokens.exists():
        return ""
    faces = "\n".join(re.findall(r"@font-face[^}]*}", tokens.read_text()))

    def sub(m):
        f = FONTS / m.group(1)
        return f'url("/file?p={quote(str(f))}")' if f.exists() else 'local("no-such-font")'
    return re.sub(r'url\("fonts/([^"]+)"\)', sub, faces)


# ---------------------------------------------------------------- findings and grades
def load_findings():
    items = render_sheet.load_findings()
    keep = ("id", "parent", "text", "kind", "tags", "judge_notes", "scan_note", "evidence_scans",
            "quotes", "note", "episode")
    heads = []
    for f in items:
        if f["parent"] is None:
            heads.append({**{k: f.get(k) for k in keep}, "subs": []})
    by = {h["id"]: h for h in heads}
    for f in items:
        if f["parent"] is not None:
            by[f["parent"]]["subs"].append({k: f.get(k) for k in keep})
    return heads


def read_json_retry(path: Path, tries: int = 4):
    """A grade file may be mid-write (the grader rewrites it after every call)."""
    for i in range(tries):
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            if i == tries - 1:
                return None
            time.sleep(0.5)
    return None


def load_reports(heads, grade_dir: Path):
    reports, warn, tot = [], [], {}
    for gpath in sorted(grade_dir.glob("*.json")):
        g = read_json_retry(gpath)
        if not isinstance(g, dict) or "findings" not in g:
            warn.append(f"unreadable grade file (mid-write?): {gpath.name}")
            continue
        run = g.get("run") or gpath.stem
        rpath = RUNS / run / "report.md"
        if not rpath.is_file():
            warn.append(f"no report.md for {run}")
            continue
        text = rpath.read_text()
        sha_ok = hashlib.sha256(text.encode()).hexdigest() == g.get("report_sha256")
        if not sha_ok:
            warn.append(f"report.md changed since grading: {run}")
        doc = Doc(text)
        linked = sorted(render_sheet.linked_scans(text))
        items, fsum, fdetail, hows = {}, {}, {}, {}

        def match(iid, quote_):
            rngs, how = doc.find(quote_) if quote_ else ([], "empty")
            hows[how] = hows.get(how, 0) + 1
            return rngs, how

        for h in heads:
            fg = g["findings"].get(h["id"])
            if fg is None:
                fsum[h["id"]] = {"status": "pending"}
                continue
            st = fg.get("status") or "unknown"
            s = {"status": st}
            detail = {"validation": fg.get("validation") or [], "error": fg.get("error") or "",
                      "seconds": fg.get("seconds"),
                      "attempts": len(fg.get("previous_attempts") or [])}
            if st == "ok":
                s.update(score=fg.get("score"), contradicted=bool(fg.get("contradicted")),
                         sub_mean=fg.get("sub_mean"), subs={})
                rngs, how = match(h["id"], fg.get("quote", ""))
                items[h["id"]] = {"quote": fg.get("quote", ""), "reason": fg.get("reason", ""),
                                  "ranges": rngs, "match": how}
                for sf in fg.get("sub_findings") or []:
                    sid = sf.get("id")
                    if not sid:
                        continue
                    s["subs"][sid] = {"score": sf.get("score"), "contradicted": bool(sf.get("contradicted"))}
                    rngs, how = match(sid, sf.get("quote", ""))
                    items[sid] = {"quote": sf.get("quote", ""), "reason": sf.get("reason", ""),
                                  "ranges": rngs, "match": how}
            fsum[h["id"]] = s
            fdetail[h["id"]] = detail
        for k, v in hows.items():
            tot[k] = tot.get(k, 0) + v
        ok = [v["score"] for v in fsum.values() if v["status"] == "ok" and v.get("score") is not None]
        key = slug(run)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / f"{key}.json").write_text(json.dumps(
            {"text": text, "items": items, "findings": fdetail, "linked": linked,
             "coverage": g.get("scan_coverage") or {}}, ensure_ascii=False))
        cov = (g.get("scan_coverage") or {}).get("findings") or {}
        reports.append({
            "key": key, "run": run, "file": f"runs/urlquery/{run}/report.md",
            "agent": g.get("agent"), "model": g.get("model"), "rep": g.get("replicate"),
            "condition": g.get("condition"), "title": f"{g.get('agent')} · {g.get('model')}",
            "judge": g.get("judge"), "effort": g.get("effort"),
            "prompt_sha256": g.get("prompt_sha256"), "report_sha_ok": sha_ok,
            "score_mean": g.get("score_mean"),
            "prov_mean": round(sum(ok) / len(ok), 3) if ok else None,
            "n_scored": len(ok), "n_findings": len(heads), "cost_usd": g.get("cost_usd"),
            "linked_total": len(linked),
            "cov": {fid: {"group_ratio": c.get("group_ratio"), "cited_linked": c.get("cited_linked"),
                          "cited_total": c.get("cited_total"), "items_hit": c.get("items_hit") or []}
                    for fid, c in cov.items()},
            "f": fsum,
        })
    return reports, warn, tot


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--judge", default=os.getenv("JUDGE", "claude-opus-5-5"))
    args = ap.parse_args()
    judge_slug = slug(args.judge)
    grade_dir = GRADED / f"judge_{judge_slug}"
    audit_path = AUDIT_DIR / f"judge_audit_{judge_slug}.json"
    if not grade_dir.is_dir():
        raise SystemExit(f"no grades at {grade_dir}")

    fin_scale, sub_scale, ref_rule, contra_rule = sheet_scales()
    heads = load_findings()
    write_article_html()
    reports, warn, tot = load_reports(heads, grade_dir)
    for w in warn:
        print("warn:", w)
    keys = {r["key"] for r in reports}
    for stale in DATA_DIR.glob("*.json"):
        if stale.stem not in keys:
            stale.unlink()
    data = {"audit_path": str(audit_path), "data_dir": str(DATA_DIR), "article_html": str(ARTICLE_HTML),
            "judge": args.judge, "grade_dir": str(grade_dir.relative_to(ROOT)),
            "skip_classes": SKIP_CLASSES, "scale": fin_scale, "sub_scale": sub_scale,
            "ref_rule": ref_rule, "contra_rule": contra_rule, "intro": TASK_INTRO,
            "findings": heads, "reports": reports,
            "built": datetime.datetime.now().isoformat(timespec="seconds")}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload).replace("/*__FONTS__*/", font_css()))
    det = sum(f.stat().st_size for f in DATA_DIR.glob("*.json"))
    n_sub = sum(len(h["subs"]) for h in heads)
    states = {}
    for r in reports:
        for v in r["f"].values():
            states[v["status"]] = states.get(v["status"], 0) + 1
    print(f"{OUT}: {len(reports)} reports, {len(heads)} findings + {n_sub} sub-findings; "
          f"shell {OUT.stat().st_size / 1e6:.2f} MB + {det / 1e6:.2f} MB in {DATA_DIR.name}/")
    print(f"  finding states {states}; quote matches {tot}")
    print(f"  scales from {SHEET.name}: finding {[a['key'] for a in fin_scale]}, "
          f"sub-finding {[a['key'] for a in sub_scale]}")
    print(f"  article {ARTICLE_HTML.stat().st_size / 1e6:.2f} MB; audit file {audit_path}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-src 'self'; connect-src 'self'">
<title>URLQuery judge audit</title>
<style>
/*__FONTS__*/
:root{--essay-serif:"et-book",Palatino,"Palatino Linotype","Palatino LT STD","Book Antiqua",Georgia,serif;--essay-mono:SFMono-Regular,Menlo,Consolas,Monaco,"Liberation Mono",monospace;--sans-ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--paper:#FFFFF8;--essay-ink:#111;--essay-dull:#666;--essay-wash:#F6F6EE;--essay-dull-bg:#F0F0F0;--essay-hair:#E8E8DF;--essay-rule:#D6D6CC;--essay-green:#2A623D;--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666666;--mut:#8A8A8A;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok:#065F46;--warn-bg:#FEF3C7;--warn:#92400E;--dang-bg:#FEE2E2;--dang:#991B1B;--grey-bg:#ECEAE3;--grey:#555;--un-bg:#E7E9F2;--un:#2F3A67}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:var(--sans-ui);background:var(--bg);color:var(--ink);font-size:13px;line-height:1.45;display:grid;grid-template-rows:auto 1fr;height:100vh;overflow:hidden}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,mark:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
header{padding:6px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
h1{color:var(--accent);font-size:16px;margin:0;white-space:nowrap}
.sub{color:var(--mut);font-size:10.5px}
.tabs{display:flex;gap:4px}
.tab{padding:5px 12px;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--ink2);cursor:pointer;font-weight:600;font-size:12px;font-family:inherit}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
#sb-btn{padding:5px 9px;font-size:13px}
.stats{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto;align-items:center}
.badge{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--soft);color:var(--accent2);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.dang{background:var(--dang-bg);color:var(--dang)}.badge.grey{background:var(--grey-bg);color:var(--grey)}.badge.un{background:var(--un-bg);color:var(--un)}
#save{font-size:11px;color:var(--mut);min-width:150px;text-align:right}
#save.err{color:#fff;background:var(--dang);font-weight:700;padding:3px 8px;border-radius:6px}
#layout{display:grid;grid-template-columns:290px 1fr;min-height:0}
#layout.collapsed{grid-template-columns:1fr}#layout.collapsed aside{display:none}
aside{border-right:1px solid var(--border);display:flex;flex-direction:column;min-height:0;background:var(--card)}
.search{margin:8px 8px 4px;padding:6px 9px;border:1px solid var(--border);border-radius:7px;font-size:12px;font-family:inherit}
.filt{display:flex;gap:4px;flex-wrap:wrap;padding:2px 8px 4px;align-items:center}
.filt .lab{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;width:44px}
.filt button{font-size:11px;padding:1px 8px;border:1px solid var(--border);border-radius:20px;background:transparent;color:var(--ink2);cursor:pointer;font-family:inherit}
.filt button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#list{overflow:auto;flex:1;border-top:1px solid var(--border)}
.item{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--border);background:transparent;font-family:inherit;color:inherit;padding:6px 10px;cursor:pointer;font-size:12px}
.item:hover{background:var(--row)}.item.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--accent)}
.item .nm{font-weight:600;display:flex;justify-content:space-between;gap:6px}
.item .meta{color:var(--mut);font-size:11px;display:flex;gap:8px;flex-wrap:wrap}
.item .prog{height:3px;background:var(--grey-bg);border-radius:2px;margin-top:4px;overflow:hidden}.item .prog i{display:block;height:100%;background:var(--accent)}
main{display:grid;grid-template-rows:auto auto 1fr;min-height:0}
main.claimview{grid-template-rows:auto 1fr}main.notesview{grid-template-rows:1fr}
#rail{display:flex;gap:4px;padding:5px 12px;overflow-x:auto;border-bottom:1px solid var(--border);background:var(--bg);align-items:center}
.chip{flex:none;padding:2px 7px;border-radius:6px;border:1px solid var(--border);background:var(--card);cursor:pointer;font-size:11px;font-weight:600;display:flex;gap:5px;align-items:center;font-family:inherit;color:var(--ink)}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--grey-bg)}
.dot.s1{background:#34A87A}.dot.s05{background:#E4A93A}.dot.s0{background:#D6D3CB}.dot.un{background:repeating-linear-gradient(45deg,#6B76A8 0 2px,#fff 2px 4px);border:1px solid #6B76A8}.dot.pend{background:#fff;border:1px dashed #999}
.chip.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--soft);background:var(--soft)}
.chip.un{border-style:dashed}
.chip .st{font-size:10px;color:var(--mut)}
.chip .cx{color:var(--dang);font-weight:800}
#claimline{display:flex;gap:8px;align-items:center;padding:4px 12px;border-bottom:1px solid var(--border);background:var(--card);font-size:12px;white-space:nowrap;overflow:hidden}
#claimline .txt{overflow:hidden;text-overflow:ellipsis;font-weight:600}
#claimline .anchor{color:var(--mut);font-size:11px;white-space:nowrap}
#claimline .spacer{flex:1}
.cl-id{font-size:11px;color:var(--mut);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.cl-text{font-weight:600;font-size:13.5px;margin:4px 0 6px}
.hq{font-style:italic;color:var(--ink2);border-left:3px solid var(--soft);padding-left:8px;margin:4px 0}
.hq.link{display:block;font-weight:400;font-size:12px;color:var(--ink2);text-decoration:none;background:transparent;border-top:0;border-right:0;border-bottom:0;text-align:left;font-family:inherit;cursor:pointer;width:100%}
.hq.link:hover{background:var(--row)}
.gt{font-size:11.5px;color:var(--ink2);margin-top:3px}.gt b{color:var(--ink)}
.judge{margin-top:6px;padding:7px 9px;background:var(--row);border:1px solid var(--border);border-radius:8px}
.judge .q{font-style:italic;margin:4px 0}.judge .r{color:var(--ink2)}
.judge .hd{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.sc{display:inline-block;padding:1px 8px;border-radius:20px;font-weight:700;font-size:11px}
.sc.s1{background:var(--ok-bg);color:var(--ok)}.sc.s05{background:var(--warn-bg);color:var(--warn)}.sc.s0{background:var(--grey-bg);color:var(--grey)}
.sc.un{background:var(--un-bg);color:var(--un);border:1px dashed #6B76A8;letter-spacing:.02em}
.contra{display:inline-block;padding:1px 8px;border-radius:20px;font-weight:800;font-size:11px;background:var(--dang);color:#fff}
.ref{font-size:11.5px;color:var(--ink2);margin-top:4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.ref b{color:var(--ink)}
.verd{display:flex;flex-wrap:wrap;gap:5px;margin:4px 0 8px}
.vb{padding:4px 10px;border:1px solid var(--border);border-radius:7px;background:transparent;cursor:pointer;font-size:12px;font-weight:600;color:var(--ink2);font-family:inherit}
.vb:hover{background:var(--row)}
.vb.on.ok{background:var(--ok-bg);color:var(--ok);border-color:#9AD6BC}.vb.on.warn{background:var(--warn-bg);color:var(--warn);border-color:#E5CB7A}.vb.on.dang{background:var(--dang-bg);color:var(--dang);border-color:#F0A6A6}.vb.on.grey{background:var(--grey-bg);color:var(--grey);border-color:#C9C6BC}
.vb.on.plain{background:var(--soft);color:var(--accent2);border-color:var(--accent)}
.vb .k{font-size:10px;color:var(--mut);font-weight:400;margin-right:4px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0;font-size:12px;color:var(--ink2)}
.row .vb{padding:2px 9px}
textarea{width:100%;min-height:44px;border:1px solid var(--border);border-radius:7px;padding:6px 8px;font-family:inherit;font-size:12.5px;resize:vertical;background:#fff}
.cat{font-size:11px;color:var(--mut)}
.stale{font-size:11px;color:var(--warn);font-weight:600}
.scale{display:flex;gap:3px;flex-wrap:wrap;margin:3px 0 2px}
.sb{flex:1 1 0;min-width:46px;border:1px solid var(--border);border-radius:7px;background:transparent;cursor:pointer;font-family:inherit;padding:2px 2px 3px;color:var(--ink2);display:flex;flex-direction:column;align-items:center;gap:0;line-height:1.15}
.sb .n{font-weight:600;font-size:12px;color:var(--mut)}
.sb .sl{font-size:9px;color:var(--mut);text-align:center;min-height:1.05em;letter-spacing:-.01em}
.sb.anch{background:var(--row);border-color:#CDC9BE}
.sb.anch .n{color:var(--ink);font-weight:800;font-size:12.5px}
.sb.jd{box-shadow:inset 0 -3px 0 #6B76A8}
.sb:hover{background:var(--soft);border-color:var(--accent)}
.sb.on{background:var(--accent);border-color:var(--accent)}
.sb.on .n,.sb.on .sl{color:#fff}
.scale.q .sb{min-width:70px}
.scnum{width:52px;border:1px solid var(--border);border-radius:7px;padding:2px 6px;font-family:inherit;font-size:12px;background:#fff}
.other{margin-top:5px;border-top:1px dashed var(--border);padding-top:5px;font-size:11.5px}
.oline{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0}
.oline .who{font-weight:700;color:var(--accent2)}
.oline .ocmt{flex-basis:100%;color:var(--ink2);font-style:italic;margin-left:2px}
.chip.dis{border-color:#D9534F;background:var(--dang-bg)}
/* the finding block: finding-level audit, then one row per sub-finding */
.fblock{display:flex;flex-direction:column;gap:6px}
.lvl{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);font-weight:700;margin-top:4px}
.subs{display:flex;flex-direction:column;gap:6px;margin-top:2px}
.srow{border:1px solid var(--border);border-left:4px solid var(--grey-bg);border-radius:8px;padding:6px 9px;background:var(--card)}
.srow.s1{border-left-color:#34A87A}.srow.s05{border-left-color:#E4A93A}.srow.s0{border-left-color:#D6D3CB}.srow.un{border-left-color:#6B76A8}
.srow.sel{box-shadow:0 0 0 2px var(--soft);border-color:var(--accent)}
.srow .sh{display:flex;gap:6px;align-items:center;flex-wrap:wrap;width:100%;background:transparent;border:0;padding:0;font-family:inherit;text-align:left;color:inherit;cursor:pointer;font-size:12px}
.srow .sh .t{font-weight:600;flex:1 1 240px}
.srow .sh .mine{font-size:11px;color:var(--accent2);font-weight:700}
.scans{font-size:11.5px;color:var(--ink2);margin-top:3px;display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.scanb{font-family:var(--essay-mono);font-size:10.5px;padding:0 5px;border-radius:4px;border:1px solid var(--border);background:var(--row);color:var(--ink2);cursor:pointer}
.scanb.hit{background:#DDF3E8;border-color:#7CC7A1;color:var(--ok);font-weight:700}
#intro{position:fixed;inset:0;background:rgba(26,26,26,.45);z-index:50;display:flex;align-items:center;justify-content:center;padding:20px}
#intro[hidden]{display:none}
#intro .sheet{background:var(--card);border:1px solid var(--border);border-radius:10px;max-width:820px;width:100%;max-height:88vh;overflow:auto;padding:18px 22px 20px}
#intro h2{color:var(--accent);margin:0 0 4px;font-size:17px}
#intro h3{color:var(--accent2);font-size:13px;margin:14px 0 4px}
#intro p{margin:6px 0;font-size:12.5px;line-height:1.5}
#intro table{border-collapse:collapse;width:100%;font-size:12.5px}
#intro td{border-top:1px solid var(--border);padding:5px 6px;vertical-align:top;line-height:1.45}
#intro td.v{font-weight:800;width:44px;white-space:nowrap}
#intro td.s{color:var(--accent2);width:140px;font-weight:600}
.whoin{display:flex;gap:8px;align-items:center;margin:12px 0 2px;font-weight:600;font-size:12.5px}
.whoin input{border:1px solid var(--border);border-radius:7px;padding:5px 9px;font-family:inherit;font-size:13px;min-width:210px;background:#fff}
.whoerr{color:var(--dang);font-size:11.5px;margin:2px 0 4px;font-weight:600}
.fine{color:var(--mut);font-size:11.5px}
#who-btn{max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#panes{display:grid;grid-template-columns:1fr 1fr;min-height:0}
.pane{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--border);position:relative}
.pane:last-child{border-right:0}
.pane h3{margin:0;padding:5px 12px;font-size:12px;color:var(--accent);border-bottom:1px solid var(--border);background:var(--card);display:flex;justify-content:space-between;gap:8px;align-items:center}
.pane h3 span{color:var(--mut);font-weight:400;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pane h3 button{margin-left:auto;flex:none}
.remind{font-size:11px;color:var(--mut);padding:3px 12px 3px 26px;border-bottom:1px solid var(--border);background:var(--card);font-style:italic}
.doc{overflow:auto;padding:14px 18px 45vh 34px;background:var(--paper);color:var(--essay-ink);flex:1;white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--essay-serif);font-size:18px;line-height:1.42}
#hframe{flex:1;width:100%;border:0;background:#fff;min-height:0}
.ln{min-height:1.42em;max-width:34em}
.ln.h1{font-size:30px;line-height:1.15;font-weight:700;margin:22px 0 4px}
.ln.h2{font-size:24.75px;line-height:1.2;font-weight:700;margin:18px 0 3px}
.ln.h3{font-size:21px;line-height:1.25;font-weight:700;margin:14px 0 2px}
.ln.code,.ln.tbl{font-family:var(--essay-mono);font-size:13px;line-height:1.45;background:var(--essay-wash);max-width:none}
.ln.quote{color:#333;border-left:3px solid var(--essay-green);background:var(--essay-wash);padding:1px 10px}
.md-mk{display:none}
.md-bul{font-size:0}.md-bul::before{content:'•';font-size:18px;color:var(--essay-dull)}
.md-pipe{color:#B9B9AE}
.doc strong{font-weight:700}.doc em{font-style:italic}
.doc code{font-family:var(--essay-mono);font-size:.86em;background:var(--essay-dull-bg);padding:0 .3em;border-radius:2px}
.doc a{color:#31566F;text-decoration:underline;text-decoration-color:#9FB3C2}
/* a link to one of the selected finding's listed scans, and to the selected item's */
.doc a.ev{background:#DDF3E8;color:var(--ok);text-decoration-color:var(--ok);border-radius:2px;box-shadow:0 0 0 1px #7CC7A1}
.doc a.ev::after{content:'\25C6';font-size:.6em;vertical-align:super;margin-left:1px;color:var(--ok)}
.doc a.ev.evsel{background:#BFE9D3;box-shadow:0 0 0 2px #34A87A}
.doc a.flash{outline:3px solid var(--accent)}
.ln.p{position:relative;border-left:3px solid transparent;margin-left:-12px;padding-left:9px}
.ln.p .g{position:absolute;left:-22px;top:5px;font-family:var(--sans-ui);width:14px;height:14px;padding:0;border-radius:4px;border:1px solid var(--border);background:var(--card);color:var(--mut);font-size:10px;line-height:12px;text-align:center;opacity:0;font-style:normal;cursor:pointer}
.ln.p:hover .g,.ln.p.has .g,.ln.p .g:focus-visible{opacity:1}.ln.p.has .g{color:var(--accent);border-color:var(--accent)}
.ln.p.a-true{border-left-color:#34A87A}.ln.p.a-false{border-left-color:#D9534F}.ln.p.a-irr{border-left-color:#C9C6BC;color:var(--mut)}.ln.p.a-note{border-left-color:var(--accent)}
.strip{margin:6px 0 12px -12px;padding:8px 10px;background:var(--row);border:1px solid var(--border);border-radius:8px;font-family:var(--sans-ui);font-size:12px;line-height:1.45;color:var(--ink);white-space:normal;cursor:default;max-width:none}
.strip .row{margin:2px 0}.strip textarea{min-height:34px;margin-top:4px}
.strip .lab{font-weight:600;color:var(--ink2)}
.cbox{border:1px solid var(--border);border-radius:8px;padding:8px 10px;margin-bottom:8px;background:var(--card)}
.cbox.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--soft)}
.qs{border-top:1px dashed var(--border);padding-top:6px}
#claimcard{position:absolute;left:0;right:0;bottom:0;max-height:62%;overflow:auto;background:var(--card);border-top:2px solid var(--accent);box-shadow:0 -6px 16px rgba(0,0,0,.10);padding:8px 12px 12px;z-index:5}
#claimcard .hdr{display:flex;gap:8px;align-items:center;font-size:11px;color:var(--mut);margin-bottom:2px}
#claimcard .hdr .x{margin-left:auto;cursor:pointer;font-weight:700;color:var(--ink2);border:1px solid var(--border);border-radius:6px;padding:0 6px;background:var(--card)}
#mnotes{padding:8px 12px;border-bottom:1px solid var(--border);background:var(--soft);max-height:34vh;overflow:auto}
#mnotes label,.ncard label{font-size:11px;color:var(--accent2);display:block;margin:6px 0 2px;font-weight:600}
mark{background:transparent;border-radius:3px;padding:0 1px;cursor:pointer;color:inherit;box-shadow:0 1px 0 rgba(193,95,60,.28)}
mark:hover{box-shadow:0 1px 0 var(--accent),0 0 0 2px var(--soft)}
mark.s1{background:#D1FAE5}mark.s05{background:#FEF3C7}mark.s0{background:#FEE2E2}
mark.grp{box-shadow:0 2px 0 var(--accent)}
mark.sel{outline:2px solid var(--accent);background:#FBE3D6}
.hint{font-size:10.5px;color:var(--mut);padding:0 8px 6px}
.hint b{font-weight:600;color:var(--ink2)}
kbd{background:var(--soft);border:1px solid var(--border);border-radius:4px;padding:0 4px;font-size:10px;font-family:inherit}
#cards{overflow:auto;padding:10px 14px;display:flex;flex-direction:column;gap:10px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 14px}
.card .hd{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:600;margin-bottom:4px}
.card .hd .b{font-size:11px;color:var(--mut);font-weight:400}
.link{color:var(--accent);cursor:pointer;font-size:11.5px;font-weight:600;text-decoration:none;background:transparent;border:0;padding:0;font-family:inherit}
.link:hover{text-decoration:underline}
#claimhead{padding:10px 14px;border-bottom:1px solid var(--border);background:var(--card);max-height:40vh;overflow:auto}
.empty{color:var(--mut);padding:20px;text-align:center}
#notes{overflow:auto;padding:12px 16px;display:flex;flex-direction:column;gap:12px}
.ncard{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.ncard h4{margin:0;color:var(--accent);font-size:13px;display:flex;gap:10px;align-items:center}
.ncard h4 span{color:var(--mut);font-weight:400;font-size:11px}
.pl{font-size:12px;margin:5px 0;padding:5px 9px;border-left:3px solid var(--border);background:var(--row);border-radius:0 6px 6px 0}
.pl.a-true{border-left-color:#34A87A}.pl.a-false{border-left-color:#D9534F}.pl.a-irr{border-left-color:#C9C6BC}.pl.a-note{border-left-color:var(--accent)}
.pl .t{color:var(--ink2);white-space:pre-wrap}.pl .n{margin-top:3px;font-style:italic}.pl .tags{font-size:11px;color:var(--mut);margin-bottom:2px;display:flex;gap:8px;flex-wrap:wrap}
</style></head><body>
<header>
  <button class="tab" id="sb-btn" title="hide / show the report list  ([)" aria-label="toggle the report list">&#9776;</button>
  <div><h1>URLQuery judge audit</h1><div class="sub" id="built"></div></div>
  <div class="tabs" role="tablist"><button class="tab active" data-view="report">By report</button><button class="tab" data-view="claim">By finding</button><button class="tab" data-view="notes">Notes</button></div>
  <div class="tabs"><button class="tab" id="who-btn" title="who is auditing">auditor?</button><button class="tab" id="guide-btn" title="the task and the two scales">the scales</button></div>
  <div class="stats" id="stats"></div>
  <div id="save" role="status" aria-live="polite">loading&hellip;</div>
</header>
<div id="layout">
  <aside>
    <input class="search" id="q" placeholder="Search reports / findings&hellip;" aria-label="search reports and findings">
    <div class="filt" id="f-cond"><span class="lab">batch</span></div>
    <div class="filt" id="f-agent"><span class="lab">harness</span></div>
    <div class="filt" id="f-status"><span class="lab">show</span></div>
    <div id="list"></div>
    <div class="hint"><b>Reports: best judge mean first.</b> <kbd>j</kbd>/<kbd>k</kbd> finding or sub-finding &middot; <kbd>n</kbd>/<kbd>p</kbd> report &middot; <kbd>1</kbd>&ndash;<kbd>4</kbd> verdict &middot; <kbd>c</kbd> comment &middot; <kbd>e</kbd> report notes &middot; <kbd>[</kbd> hide this list &middot; <kbd>Esc</kbd> leave box &middot; click (or Enter on) a highlight to audit it; the &#9998; in the margin notes a paragraph</div>
  </aside>
  <main id="main">
    <div id="rail" aria-label="findings"></div>
    <div id="claimline"></div>
    <div id="panes">
      <div class="pane" id="mpane">
        <h3>Model report <span id="mr-title"></span><button class="vb grey" id="mnotes-btn">notes</button></h3>
        <div class="remind">For each finding and sub-finding: is the judge's score right, and is its contradicted flag right? &mdash; <span style="background:#DDF3E8;color:#065F46;padding:0 3px;border-radius:2px">links&#9670;</span> go to a scan the finding lists.</div>
        <div id="mnotes" hidden></div>
        <div class="doc" id="mdoc"></div>
        <div id="claimcard" hidden></div>
      </div>
      <div class="pane">
        <h3>Transluce's article <span id="hr-note"></span></h3>
        <iframe id="hframe" title="Transluce's article, inert copy" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>
      </div>
    </div>
    <div id="claimhead" hidden></div>
    <div id="cards" hidden></div>
    <div id="notes" hidden></div>
  </main>
</div>
<div id="intro" hidden role="dialog" aria-modal="true" aria-labelledby="intro-h"><div class="sheet">
  <h2 id="intro-h">Auditing the URLQuery finding judge</h2>
  <div id="intro-task"></div>
  <div class="whoerr" id="who-err" hidden>Type a name first &mdash; it is what keeps your judgements separate from your partner's.</div>
  <label class="whoin">Your name <input id="who-in" placeholder="first name" autocomplete="off" spellcheck="false"></label>
  <h3>Sub-findings: 0 to 1 in quarters</h3>
  <table><tbody id="subtab"></tbody></table>
  <h3>The finding as a whole: 0 to 1, one decimal place</h3>
  <table><tbody id="scaletab"></tbody></table>
  <p class="fine">Those six are the defined anchors; 0.1, 0.2, 0.4, 0.6 and 0.8 sit between two of them. Both tables are read from the judge's sheet at build time.</p>
  <h3>From sub-findings to the finding</h3>
  <p id="ref-rule"></p>
  <h3>Contradictions</h3>
  <p id="contra-rule"></p>
  <p class="fine" id="where"></p>
  <button class="vb plain" id="intro-ok">Start auditing</button>
</div></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const AUDIT_PATH = D.audit_path, LS_KEY = 'uq_judge_audit:' + AUDIT_PATH, SB_KEY = 'uq_judge_audit:sidebar';
const WHO_KEY = 'uq_judge_audit:auditor', INTRO_KEY = 'uq_judge_audit:intro_seen';
const SCALE = D.scale, SCALE_BY = Object.fromEntries(SCALE.map(a => [a.key, a]));
const SUB_SCALE = D.sub_scale;
const SCALE_VALS = []; for (let i = 10; i >= 0; i--) SCALE_VALS.push(i / 10);
const DISAGREE = 0.2;
const FINDINGS = D.findings, FIDS = FINDINGS.map(f => f.id);
const ITEM = {}; const ORDER = [];              /* every scored item, headline then its subs */
for (const f of FINDINGS) { ITEM[f.id] = Object.assign({}, f, {head: f.id}); ORDER.push(f.id);
  for (const s of f.subs) { ITEM[s.id] = Object.assign({}, s, {head: f.id}); ORDER.push(s.id); } }
function group(fid) { return [fid].concat(ITEM[fid].subs.map(s => s.id)); }
function isHead(iid) { return ITEM[iid].head === iid; }
const REPORTS = D.reports, RBY = Object.fromEntries(REPORTS.map(r => [r.key, r]));
const PEND = {};
function fileURL(p) { return '/file?p=' + encodeURIComponent(p); }
function loaded(rk) { return RBY[rk].text != null; }
function details(rk) {
  if (loaded(rk)) return Promise.resolve(RBY[rk]);
  if (!PEND[rk]) PEND[rk] = fetch(fileURL(D.data_dir + '/' + rk + '.json'))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(d => { const rep = RBY[rk]; rep.items = d.items; rep.fdetail = d.findings; rep.linked = new Set(d.linked); rep.text = d.text; return rep; })
    .catch(e => { delete PEND[rk]; throw e; });
  return PEND[rk];
}
document.getElementById('built').textContent = REPORTS.length + ' reports · ' + FINDINGS.length + ' findings · judge ' + D.judge + ' · built ' + D.built;

/* What the judge said about one item in one report. Unscored findings carry their status
   (refused, unparseable, api_error, truncated, pending) down to their sub-findings. */
function J(rk, iid) {
  const f = RBY[rk].f[ITEM[iid].head] || {status: 'pending'};
  if (isHead(iid)) return f;
  if (f.status !== 'ok') return {status: f.status};
  return (f.subs || {})[iid] ? Object.assign({status: 'ok'}, f.subs[iid]) : {status: 'missing'};
}
function scored(j) { return j.status === 'ok' && j.score != null; }
function jscore(rk, iid) { const j = J(rk, iid); return scored(j) ? j.score : null; }
function statusLabel(st) { return st === 'pending' ? 'not graded yet' : st === 'missing' ? 'no sub-finding score' : st; }

const VERDICTS = {
  pos: [{v:'adjust', l:'Right find, wrong score', c:'warn'}, {v:'fp', l:'Not supported (FP)', c:'dang'}, {v:'todo', l:'Needs investigation', c:'grey'}],
  neg: [{v:'tn_easy', l:'Contradicted by report (TN easy)', c:'ok'}, {v:'tn_hard', l:'Absent, checked (TN hard)', c:'ok'}, {v:'fn', l:'Actually present (FN)', c:'dang'}, {v:'todo', l:'Needs investigation', c:'grey'}],
  un: [{v:'todo', l:'Needs investigation', c:'grey'}],
};
const CAT = {tp:['TP','ok'], adjust:['TP·adj','warn'], fp:['FP','dang'], tn_easy:['TN easy','ok'], tn_hard:['TN hard','ok'], fn:['FN','dang'], todo:['Flagged','grey']};
const MATCHLAB = {exact: 'quote found verbatim', norm: 'quote found (whitespace/punctuation/Markdown normalised)', pieces: 'quote found in pieces (judge elided with …)', 'pieces-norm': 'quote found in pieces, normalised', none: 'no anchor: quote NOT found in this report', empty: 'judge gave no quote'};
function vset(rk, iid) { const j = J(rk, iid); return !scored(j) ? 'un' : j.score > 0 ? 'pos' : 'neg'; }
const GLOBAL = '_global';

/* ---------- persistence: one file, auditors keyed by name ---------- */
let state = {version: 3, schema: 'urlquery-judge-audit-v1', judge: D.judge, updated_at: null, auditors: {}};
let ME = '';
let view = 'report', selReport = null, selItem = FIDS[0], selFindView = FIDS[0], cardForced = false;
const filters = {cond: new Set(), agent: new Set(), status: new Set(), q: ''};
const openParas = new Set(), expanded = new Set();
const MAPS = ['entries', 'paragraphs', 'notes'];
function fresh() { return {entries: {}, paragraphs: {}, notes: {}}; }
function bkt(st, who) { return (st.auditors && st.auditors[who]) || null; }
function mkBkt(st, who) { const a = bkt(st, who) || (st.auditors[who] = fresh()); for (const m of MAPS) a[m] = a[m] || {}; return a; }
function myMap(map) { const b = bkt(state, ME); return (b && b[map]) || {}; }
function auditors() { return Object.keys(state.auditors).sort(); }
function ekey(rk, iid) { return RBY[rk].run + '/' + iid; }
function entry(rk, iid) { return myMap('entries')[ekey(rk, iid)] || null; }
function entryOf(who, rk, iid) { const b = bkt(state, who); return (b && b.entries[ekey(rk, iid)]) || null; }
const CONTENT = ['verdict', 'comment', 'item_issue', 'corrected', 'contra_wrong', 'truth', 'rating', 'note', 'hypotheses', 'biases'];
function blank(e) { return !CONTENT.some(k => e[k] != null && e[k] !== '' && e[k] !== false); }
function setIn(map, k, patch) {
  if (!ME) { openIntro(); return; }
  const b = mkBkt(state, ME);
  const e = Object.assign({}, b[map][k] || {}, patch, {updated_at: new Date().toISOString()});
  for (const key of Object.keys(e)) if (e[key] === null || e[key] === '' || e[key] === false) delete e[key];
  if (blank(e)) delete b[map][k]; else b[map][k] = e;
  scheduleSave();
}
/* Each entry keeps what the judge said when it was audited, so a regrade is visible. */
function setEntry(rk, iid, patch) {
  const j = J(rk, iid), level = isHead(iid) ? 'finding' : 'sub_finding';
  setIn('entries', ekey(rk, iid), Object.assign({level, finding: ITEM[iid].head, judge_score: scored(j) ? j.score : null,
    judge_status: j.status, judge_contradicted: !!j.contradicted, prompt_sha256: RBY[rk].prompt_sha256}, patch));
}
function pkey(rk, li) { return RBY[rk].run + '/p' + li; }
function para(rk, li) { return myMap('paragraphs')[pkey(rk, li)] || null; }
function setPara(rk, li, patch) { setIn('paragraphs', pkey(rk, li), Object.assign({anchor: RBY[rk].text.split('\n')[li].slice(0, 100)}, patch)); }
function nkey(rk) { return rk === GLOBAL ? GLOBAL : RBY[rk].run; }
function note(rk) { return myMap('notes')[nkey(rk)] || null; }
function setNote(rk, patch) { setIn('notes', nkey(rk), patch); }
function allCorrected(rk, iid) { const out = []; for (const w of auditors()) { const e = entryOf(w, rk, iid); if (e && e.corrected != null) out.push([w, e.corrected]); } return out; }
function round1(x) { return Math.round(x * 10) / 10; }
function disagreement(rk, iid) {
  const v = allCorrected(rk, iid).map(x => x[1]); if (v.length < 2) return 0;
  const d = Math.round((Math.max.apply(null, v) - Math.min.apply(null, v)) * 100) / 100; return d > DISAGREE ? d : 0;
}
let saveTimer = null;
function setStatus(t, err) { const el = document.getElementById('save'); el.textContent = t; el.className = err ? 'err' : ''; }
function scheduleSave() { clearTimeout(saveTimer); setStatus('unsaved…'); saveTimer = setTimeout(saveNow, 500); }
function serialize() { return JSON.stringify({version: 3, schema: 'urlquery-judge-audit-v1', judge: D.judge, grade_dir: D.grade_dir, updated_at: state.updated_at, auditors: state.auditors}, null, 1); }
async function saveNow() {
  state.updated_at = new Date().toISOString();
  const body = serialize(); let lsErr = '';
  try { localStorage.setItem(LS_KEY, body); } catch (e) { lsErr = ' (browser copy also failed: ' + e.message + ')'; }
  try {
    const r = await fetch('/save?p=' + encodeURIComponent(AUDIT_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    setStatus('saved to disk ' + new Date().toLocaleTimeString() + lsErr, !!lsErr);
  } catch (e) { setStatus('NOT SAVED TO DISK (' + e.message + ')' + (lsErr || ' — browser copy kept; start scripts/html_viewer.py'), true); }
}
function mergeInto(dst, src) {
  for (const map of MAPS) for (const [k, e] of Object.entries((src && src[map]) || {})) {
    const cur = dst[map][k]; if (!cur || (e.updated_at || '') > (cur.updated_at || '')) dst[map][k] = e;
  }
}
function merge(a, b) {
  const out = {version: 3, schema: 'urlquery-judge-audit-v1', judge: D.judge, updated_at: null, auditors: {}};
  for (const src of [a, b]) { if (!src) continue; for (const w of Object.keys(src.auditors || {})) mergeInto(mkBkt(out, w), src.auditors[w]); }
  return out;
}
function countAll(st) { let n = 0; for (const w of Object.keys(st.auditors || {})) for (const m of MAPS) n += Object.keys(st.auditors[w][m] || {}).length; return n; }
function sameContent(a, b) { return JSON.stringify(a.auditors || {}) === JSON.stringify(b.auditors || {}); }
async function load() {
  let server = null, local = null, serr = '';
  try { const r = await fetch(fileURL(AUDIT_PATH)); if (r.ok) server = await r.json(); else if (r.status !== 404) serr = 'HTTP ' + r.status; } catch (e) { serr = e.message; }
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = merge(server, local);
  const n = countAll(state);
  if (serr) setStatus('cannot reach the audit file (' + serr + ') — changes stay in this browser only', true);
  else if (server === null && local === null) setStatus('no saved audits yet');
  else if (local && !sameContent(state, server || {})) scheduleSave();
  else setStatus('loaded ' + n + ' saved items (from disk)');
}

/* ---------- helpers ---------- */
function scoreClass(s) { return s == null ? 's0' : s >= 0.75 ? 's1' : s > 0 ? 's05' : 's0'; }
function jClass(j) { return scored(j) ? scoreClass(j.score) : 'un'; }
function isPos(rk, iid) { const s = jscore(rk, iid); return s != null && s > 0; }
function audited(rk, iid) { const e = entry(rk, iid); return !!e && (e.corrected != null || (e.verdict && e.verdict !== 'todo')); }
function flagged(rk, iid) { const e = entry(rk, iid); return !!e && (e.verdict === 'todo' || !!e.item_issue || !!e.contra_wrong); }
function el(tag, cls, text) { const x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; }
function fmtScore(s) { return s == null ? '–' : Number(s).toFixed(1); }
function fmtQ(s) { if (s == null) return '–'; const v = Number(s); return Math.abs(v * 10 - Math.round(v * 10)) < 1e-9 ? v.toFixed(1) : v.toFixed(2); }
function chipBtn(parent, on, label, fn, cls) { const b = el('button', 'vb ' + (cls || 'grey') + (on ? ' on' : '')); b.textContent = label; b.setAttribute('aria-pressed', on ? 'true' : 'false'); b.onclick = ev => { ev.stopPropagation(); fn(); }; parent.appendChild(b); return b; }
function reportMean(r) { return r.score_mean != null ? r.score_mean : r.prov_mean; }
function meanLabel(r) { return r.score_mean != null ? r.score_mean.toFixed(2) : (r.prov_mean == null ? '–' : '~' + r.prov_mean.toFixed(2)) + ' (' + r.n_scored + '/' + r.n_findings + ')'; }
function filteredReports() {
  const q = filters.q.toLowerCase();
  return REPORTS.filter(r => (!filters.cond.size || filters.cond.has(r.condition)) && (!filters.agent.size || filters.agent.has(r.agent))
    && (!q || (r.title + ' ' + r.run).toLowerCase().includes(q)))
    .sort((a, b) => (reportMean(b) == null ? -1 : reportMean(b)) - (reportMean(a) == null ? -1 : reportMean(a)) || a.title.localeCompare(b.title) || (a.rep || 0) - (b.rep || 0));
}
/* the rail filter works per finding: a finding shows if it or any of its sub-findings matches */
function itemOk(rk, iid) {
  const j = J(rk, iid);
  for (const f of filters.status) {
    if (f === 'pos' && scored(j) && j.score > 0) return true; if (f === 'neg' && scored(j) && j.score === 0) return true;
    if (f === 'un' && !scored(j)) return true; if (f === 'contra' && j.contradicted) return true;
    if (f === 'unreviewed' && !audited(rk, iid)) return true; if (f === 'reviewed' && audited(rk, iid)) return true;
    if (f === 'flagged' && flagged(rk, iid)) return true; if (f === 'disagree' && disagreement(rk, iid)) return true;
  }
  return false;
}
function findingOk(rk, fid) { if (!filters.status.size) return true; return group(fid).some(i => itemOk(rk, i)); }
function paraCount(rk) { let n = 0; const p = RBY[rk].run + '/p'; for (const k of Object.keys(myMap('paragraphs'))) if (k.startsWith(p)) n++; return n; }
function hasNotes(rk) { const nt = note(rk); return !!(nt && (nt.hypotheses || nt.biases)); }

/* ---------- header ---------- */
function renderStats() {
  const reps = filteredReports(); const counts = {}; let fDone = 0, fTot = 0, sDone = 0, sTot = 0, un = 0, pend = 0, dis = 0, cx = 0;
  for (const r of reps) for (const iid of ORDER) {
    const j = J(r.key, iid), head = isHead(iid);
    if (head) { fTot++; if (audited(r.key, iid)) fDone++; if (j.status === 'pending') pend++; else if (!scored(j)) un++; }
    else { sTot++; if (audited(r.key, iid)) sDone++; }
    if (j.contradicted) cx++; if (disagreement(r.key, iid)) dis++;
    const e = entry(r.key, iid); if (e && e.verdict) counts[e.verdict] = (counts[e.verdict] || 0) + 1;
  }
  const box = document.getElementById('stats'); box.replaceChildren();
  box.appendChild(el('span', 'badge grey', reps.length + ' reports'));
  if (un) box.appendChild(el('span', 'badge un', un + ' findings unscored'));
  if (pend) box.appendChild(el('span', 'badge grey', pend + ' not graded yet'));
  if (cx) box.appendChild(el('span', 'badge dang', cx + ' judge contradicted flags'));
  box.appendChild(el('span', 'badge', 'findings ' + fDone + '/' + fTot + ' · subs ' + sDone + '/' + sTot + ' audited'));
  for (const [v, [lab, c]] of Object.entries(CAT)) if (counts[v]) box.appendChild(el('span', 'badge ' + c, lab + ' ' + counts[v]));
  if (dis) box.appendChild(el('span', 'badge dang', dis + ' auditors differ >' + fmtScore(DISAGREE)));
}

/* ---------- who is auditing, and the intro panel ---------- */
function renderWho() {
  const b = document.getElementById('who-btn');
  b.textContent = ME ? 'auditor: ' + ME : 'who are you?'; b.classList.toggle('active', !!ME);
}
function setMe(n) { ME = n; try { localStorage.setItem(WHO_KEY, n); } catch (e) {} renderWho(); renderAll(); }
function buildIntro() {
  const task = document.getElementById('intro-task'); task.replaceChildren();
  for (const t of (D.intro || [])) task.appendChild(el('p', '', t));
  for (const [id, sc] of [['scaletab', SCALE], ['subtab', SUB_SCALE]]) {
    const tab = document.getElementById(id); tab.replaceChildren();
    for (const a of sc) { const tr = el('tr'); tr.appendChild(el('td', 'v', a.key)); tr.appendChild(el('td', 's', a.short)); tr.appendChild(el('td', '', a.full)); tab.appendChild(tr); }
  }
  document.getElementById('ref-rule').textContent = D.ref_rule;
  document.getElementById('contra-rule').textContent = D.contra_rule;
  document.getElementById('where').textContent = 'Saved to ' + AUDIT_PATH + ' through the local viewer (python3 scripts/html_viewer.py). If the viewer is not running, a copy is kept in this browser only and the header turns red; nothing reaches the agent until the file on disk is written.';
}
let lastFocus = null;
function openIntro() {
  lastFocus = document.activeElement;
  const o = document.getElementById('intro'); o.hidden = false; document.getElementById('who-err').hidden = true;
  const inp = document.getElementById('who-in'); inp.value = ME; setTimeout(() => { inp.focus(); inp.select(); }, 0);
}
function closeIntro() {
  const inp = document.getElementById('who-in'), n = inp.value.trim().slice(0, 40);
  if (!n) { document.getElementById('who-err').hidden = false; inp.focus(); return; }
  document.getElementById('intro').hidden = true;
  try { localStorage.setItem(INTRO_KEY, '1'); } catch (e) {}
  if (n !== ME) setMe(n); else renderWho();
  if (lastFocus && lastFocus.focus) lastFocus.focus();
}
try { ME = localStorage.getItem(WHO_KEY) || ''; } catch (e) { ME = ''; }
buildIntro(); renderWho();
document.getElementById('who-btn').onclick = openIntro;
document.getElementById('guide-btn').onclick = openIntro;
document.getElementById('intro-ok').onclick = closeIntro;
document.getElementById('who-in').onkeydown = ev => { ev.stopPropagation(); if (ev.key === 'Enter') { ev.preventDefault(); closeIntro(); } };
document.getElementById('intro').onkeydown = ev => { if (ev.key === 'Escape' && ME) { ev.stopPropagation(); document.getElementById('intro').hidden = true; if (lastFocus && lastFocus.focus) lastFocus.focus(); } };

/* ---------- collapsible sidebar ---------- */
let sbHidden = false;
try { sbHidden = localStorage.getItem(SB_KEY) === '1'; } catch (e) {}
function applySidebar() { document.getElementById('layout').classList.toggle('collapsed', sbHidden); document.getElementById('sb-btn').classList.toggle('active', !sbHidden); }
function toggleSidebar() { sbHidden = !sbHidden; try { localStorage.setItem(SB_KEY, sbHidden ? '1' : '0'); } catch (e) {} applySidebar(); }
document.getElementById('sb-btn').onclick = toggleSidebar;
applySidebar();

/* ---------- sidebar list ---------- */
function chipRow(id, values, set, labels) {
  const box = document.getElementById(id); box.querySelectorAll('button').forEach(b => b.remove());
  for (const v of values) { const b = el('button', set.has(v) ? 'on' : '', (labels && labels[v]) || v); b.setAttribute('aria-pressed', set.has(v) ? 'true' : 'false'); b.onclick = () => { set.has(v) ? set.delete(v) : set.add(v); renderAll(); }; box.appendChild(b); }
}
function renderFilters() {
  chipRow('f-cond', [...new Set(REPORTS.map(r => r.condition))].sort(), filters.cond);
  chipRow('f-agent', [...new Set(REPORTS.map(r => r.agent))].sort(), filters.agent);
  chipRow('f-status', ['pos', 'neg', 'un', 'contra', 'unreviewed', 'reviewed', 'flagged', 'disagree'], filters.status,
    {pos: 'judge +', neg: 'judge 0', un: 'unscored', contra: 'contradicted', unreviewed: 'unreviewed', reviewed: 'reviewed', flagged: 'flagged', disagree: 'auditors differ'});
}
function reportItem(r) {
  const it = el('button', 'item' + (r.key === selReport ? ' sel' : '')); it.dataset.key = r.key;
  const nm = el('div', 'nm'); nm.appendChild(el('span', '', r.title + ' · r' + r.rep)); nm.appendChild(el('span', 'sc ' + scoreClass(reportMean(r)), meanLabel(r))); it.appendChild(nm);
  const done = ORDER.filter(i => audited(r.key, i)).length, fl = ORDER.filter(i => flagged(r.key, i)).length;
  const un = FIDS.filter(f => !scored(J(r.key, f))).length, pc = paraCount(r.key);
  const meta = el('div', 'meta'); meta.appendChild(el('span', '', r.condition || ''));
  if (un) meta.appendChild(el('span', '', un + ' unscored'));
  if (!r.report_sha_ok) meta.appendChild(el('span', '', '⚠ report changed since grading'));
  meta.appendChild(el('span', '', done + '/' + ORDER.length + ' audited' + (fl ? ' · ' + fl + ' flagged' : '') + (pc ? ' · ' + pc + ' ¶' : '') + (hasNotes(r.key) ? ' · notes' : '')));
  it.appendChild(meta);
  const pg = el('div', 'prog'); const i = el('i'); i.style.width = (100 * done / ORDER.length) + '%'; pg.appendChild(i); it.appendChild(pg);
  it.onclick = () => { selReport = r.key; openParas.clear(); cardForced = false; renderMain(); renderList(); };
  return it;
}
function renderList() {
  const list = document.getElementById('list'); list.replaceChildren();
  const reps = filteredReports();
  if (view === 'report' || view === 'notes') {
    if (!selReport || !reps.some(r => r.key === selReport)) selReport = reps.length ? reps[0].key : null;
    for (const r of reps) list.appendChild(reportItem(r));
    if (!reps.length) list.appendChild(el('div', 'empty', 'no reports match the filters'));
  } else {
    const q = filters.q.toLowerCase();
    for (const f of FINDINGS) {
      if (q && !(f.id + ' ' + f.text + ' ' + f.subs.map(s => s.text).join(' ')).toLowerCase().includes(q)) continue;
      let pos = 0, done = 0, un = 0;
      for (const r of reps) { if (isPos(r.key, f.id)) pos++; if (!scored(J(r.key, f.id))) un++; if (group(f.id).every(i => audited(r.key, i))) done++; }
      const it = el('button', 'item' + (f.id === selFindView ? ' sel' : ''));
      const nm = el('div', 'nm'); nm.appendChild(el('span', '', f.id + ' · ' + f.subs.length + ' sub-findings')); it.appendChild(nm);
      it.appendChild(el('div', '', f.text.length > 120 ? f.text.slice(0, 120) + '…' : f.text));
      const meta = el('div', 'meta'); meta.appendChild(el('span', '', pos + '/' + reps.length + ' judge-positive')); if (un) meta.appendChild(el('span', '', un + ' unscored')); meta.appendChild(el('span', '', done + ' fully audited')); it.appendChild(meta);
      const pg = el('div', 'prog'); const i = el('i'); i.style.width = (reps.length ? 100 * done / reps.length : 0) + '%'; pg.appendChild(i); it.appendChild(pg);
      it.onclick = () => { selFindView = f.id; renderMain(); renderList(); };
      list.appendChild(it);
    }
  }
}

/* ---------- the judge, per item ---------- */
function judgePill(j, sub) {
  if (!scored(j)) return el('span', 'sc un', 'UNSCORED · ' + statusLabel(j.status));
  return el('span', 'sc ' + scoreClass(j.score), 'judge ' + (sub ? fmtQ(j.score) : fmtScore(j.score)));
}
function contraBadge(j) { return j.contradicted ? el('span', 'contra', '⚠ judge: CONTRADICTED') : null; }
function judgeBox(rk, iid) {
  const j = J(rk, iid), sub = !isHead(iid), box = el('div', 'judge');
  const hd = el('div', 'hd'); hd.appendChild(judgePill(j, sub)); const cb = contraBadge(j); if (cb) hd.appendChild(cb);
  const it = loaded(rk) ? (RBY[rk].items[iid] || null) : null;
  if (it) hd.appendChild(el('span', 'cat', MATCHLAB[it.match] || it.match));
  box.appendChild(hd);
  if (!loaded(rk)) { box.appendChild(el('div', 'r', 'loading the judge quote…')); return box; }
  if (it) { if (it.quote) box.appendChild(el('div', 'q', '“' + it.quote + '”')); box.appendChild(el('div', 'r', it.reason || '')); }
  else if (!scored(j)) {
    const d = (RBY[rk].fdetail || {})[ITEM[iid].head] || {};
    box.appendChild(el('div', 'r', j.status === 'pending' ? 'The grader has not reached this finding yet; rebuild the page once it has.' :
      'The judge returned no usable score (' + j.status + ')' + (d.error ? ': ' + d.error : '') + (d.attempts ? ' · ' + d.attempts + ' earlier failed attempt(s)' : '') + '. This is not a 0.'));
  }
  if (isHead(iid) && loaded(rk)) { const d = (RBY[rk].fdetail || {})[iid]; if (d && d.validation && d.validation.length) box.appendChild(el('div', 'cat', 'grader validation: ' + d.validation.join('; '))); }
  return box;
}
/* sub_mean and the reference point the sheet gives the judge: 0.5 + sub_mean/2, ±0.2 when
   the main claim is stated, at most 0.5 when it is not */
function refBox(rk, fid) {
  const j = J(rk, fid); const box = el('div', 'ref');
  if (!scored(j)) return null;
  if (!ITEM[fid].subs.length || j.sub_mean == null) { box.appendChild(el('span', '', 'no sub-findings: scored on the main claim alone')); return box; }
  const ref = 0.5 + j.sub_mean / 2, diff = Math.round((j.score - ref) * 100) / 100;
  box.appendChild(el('span', '', 'sub mean ')); box.appendChild(el('b', '', j.sub_mean.toFixed(2)));
  box.appendChild(el('span', '', '→ reference 0.5 + mean/2 = ')); box.appendChild(el('b', '', ref.toFixed(2)));
  box.appendChild(el('span', '', '· judge ' + fmtScore(j.score) + ' (' + (diff >= 0 ? '+' : '') + diff.toFixed(2) + ')'));
  if (j.score > 0.5 && Math.abs(diff) > 0.2 + 1e-9) box.appendChild(el('span', 'badge warn', 'outside ±0.2 of the reference'));
  else if (j.score <= 0.5 && ref > 0.5) box.appendChild(el('span', 'badge grey', 'at or below 0.5: judge read the main claim as not drawn'));
  return box;
}
function scansLine(rk, iid) {
  const it = ITEM[iid], ev = it.evidence_scans || [];
  const box = el('div', 'scans');
  if (!ev.length) { box.appendChild(el('span', '', 'Scans: none listed; no link needed.')); return box; }
  const linked = loaded(rk) ? RBY[rk].linked : null;
  const hits = linked ? ev.filter(s => linked.has(s)) : [];
  box.appendChild(el('span', '', linked ? 'Scans: report links ' + hits.length + ' of ' + ev.length + ' listed' : 'Scans: ' + ev.length + ' listed'));
  for (const s of ev) {
    const hit = linked && linked.has(s);
    const b = el('button', 'scanb' + (hit ? ' hit' : ''), s.slice(0, 8)); b.title = s + (hit ? ' — linked in the report; click to jump to the link' : ' — not linked in the report');
    b.onclick = ev2 => { ev2.stopPropagation(); if (hit) jumpToScan(s); };
    box.appendChild(b);
  }
  return box;
}
function itemInfo(iid, full) {
  const it = ITEM[iid], box = el('div');
  if (full) box.appendChild(el('div', 'cl-text', it.text));
  if (it.tags && it.tags.includes('added')) box.appendChild(el('div', 'gt', 'Added by the benchmark authors; the article does not state it directly.'));
  if (it.kind === 'conclusion') box.appendChild(el('div', 'gt', 'A conclusion: the report must draw it, not just show the evidence.'));
  for (const q of (it.quotes || [])) { const b = el('button', 'hq link', '“' + q + '”'); b.title = 'show in the article'; b.onclick = ev => { ev.stopPropagation(); selectItem(iid, {human: true}); }; box.appendChild(b); }
  if (it.judge_notes) { const g = el('div', 'gt'); g.appendChild(el('b', '', 'Notes: ')); g.appendChild(document.createTextNode(it.judge_notes)); box.appendChild(g); }
  if (it.scan_note) { const g = el('div', 'gt'); g.appendChild(el('b', '', 'Scan note: ')); g.appendChild(document.createTextNode(it.scan_note)); box.appendChild(g); }
  if (it.note) { const g = el('div', 'gt'); g.appendChild(el('b', '', 'Reviewer note: ')); g.appendChild(document.createTextNode(it.note)); box.appendChild(g); }
  return box;
}

/* ---------- audit controls, one item ---------- */
function auditControls(rk, iid, opts) {
  const j = J(rk, iid), e = entry(rk, iid) || {}, sub = !isHead(iid);
  const box = el('div');
  const verd = el('div', 'verd'); const vopts = VERDICTS[vset(rk, iid)];
  vopts.forEach((o, i) => {
    const b = el('button', 'vb ' + o.c + (e.verdict === o.v ? ' on' : '')); b.setAttribute('aria-pressed', e.verdict === o.v ? 'true' : 'false');
    b.appendChild(el('span', 'k', String(i + 1))); b.appendChild(document.createTextNode(o.l));
    b.onclick = ev => { ev.stopPropagation(); setEntry(rk, iid, {verdict: e.verdict === o.v ? null : o.v}); refresh(rk, iid); }; verd.appendChild(b);
  });
  if (e.verdict && !vopts.some(o => o.v === e.verdict)) { const tag = el('span', 'vb on grey', (CAT[e.verdict] || [e.verdict])[0] + ' (kept)'); const x = el('button', 'link', '✕'); x.title = 'clear this verdict'; x.onclick = ev => { ev.stopPropagation(); setEntry(rk, iid, {verdict: null}); refresh(rk, iid); }; tag.appendChild(x); verd.appendChild(tag); }
  box.appendChild(verd);
  const row = el('div', 'row'); row.appendChild(el('span', '', 'Your ' + (sub ? 'sub-finding' : 'finding') + ' score:'));
  if (!sub) {
    const num = el('input'); num.className = 'scnum'; num.type = 'text'; num.inputMode = 'decimal'; num.placeholder = '0.0–1.0'; num.title = 'type a score (one decimal) and press Enter';
    num.setAttribute('aria-label', 'your score for ' + iid); num.value = e.corrected == null ? '' : fmtScore(e.corrected);
    const commit = () => {
      const t = num.value.trim();
      if (t === '') { if (e.corrected != null) { setEntry(rk, iid, {corrected: null}); refresh(rk, iid); } return; }
      const x = parseFloat(t); if (isNaN(x)) { num.value = e.corrected == null ? '' : fmtScore(e.corrected); return; }
      setEntry(rk, iid, {corrected: Math.min(1, Math.max(0, round1(x)))}); refresh(rk, iid);
    };
    num.onkeydown = ev => { ev.stopPropagation(); if (ev.key === 'Enter') { ev.preventDefault(); commit(); } };
    num.onchange = commit; row.appendChild(num);
  } else if (e.corrected != null) row.appendChild(el('b', '', fmtQ(e.corrected)));
  row.appendChild(el('span', 'cat', scored(j) ? '(judge gave ' + (sub ? fmtQ(j.score) : fmtScore(j.score)) + ')' : '(judge: unscored, ' + statusLabel(j.status) + ')'));
  const jc = !!j.contradicted;
  chipBtn(row, !!e.contra_wrong, (e.contra_wrong ? '⚑ ' : '') + (jc ? 'not actually contradicted' : 'actually contradicted'), () => { setEntry(rk, iid, {contra_wrong: !e.contra_wrong}); refresh(rk, iid); }, 'dang');
  chipBtn(row, !!e.item_issue, (e.item_issue ? '⚑ ' : '') + (sub ? 'sub-finding' : 'finding') + ' needs fixing', () => { setEntry(rk, iid, {item_issue: !e.item_issue}); refresh(rk, iid); }, 'warn');
  const g = el('button', 'link', 'the scales →'); g.onclick = ev => { ev.stopPropagation(); openIntro(); }; row.appendChild(g);
  box.appendChild(row);
  box.appendChild(sub ? quarterRow(rk, iid, e, j) : scaleRow(rk, iid, e, j));
  if (e.updated_at && (e.judge_score !== undefined) && ((scored(j) ? j.score : null) !== e.judge_score || e.judge_status !== j.status))
    box.appendChild(el('div', 'stale', '⚠ the judge\'s output changed since you audited this (then: ' + (e.judge_score == null ? e.judge_status : fmtQ(e.judge_score)) + ')'));
  const oth = othersRow(rk, iid, e, sub); if (oth) box.appendChild(oth);
  const ta = el('textarea'); ta.className = 'cmt'; ta.dataset.iid = iid; ta.setAttribute('aria-label', 'comment on ' + iid);
  ta.placeholder = sub ? 'Comment on ' + iid + ' — what the report actually says…' : 'Comment on ' + iid + ' as a whole — why, what the report says, what the finding should say…';
  ta.value = e.comment || ''; ta.oninput = () => setEntry(rk, iid, {comment: ta.value}); box.appendChild(ta);
  const foot = el('div', 'cat'); const v = e.verdict ? CAT[e.verdict] : null;
  foot.textContent = (v ? 'Category: ' + v[0] : (e.corrected != null ? 'Scored' : 'Not audited yet')) + (e.updated_at ? ' · ' + new Date(e.updated_at).toLocaleString() : '');
  if (opts && opts.jump) { foot.appendChild(document.createTextNode('  ')); const a = el('button', 'link', 'open in report view →'); a.onclick = () => switchView('report', () => { selReport = rk; selItem = iid; openParas.clear(); cardForced = false; }); foot.appendChild(a); }
  box.appendChild(foot);
  return box;
}
function tweenTitle(v) {
  const below = SCALE.filter(a => a.v < v), above = SCALE.filter(a => a.v > v);
  const lo = below.length ? below[0] : null, hi = above.length ? above[above.length - 1] : null;
  return fmtScore(v) + ' — between ' + (lo ? fmtScore(lo.v) + ' (' + lo.short + ')' : '?') + ' and ' + (hi ? fmtScore(hi.v) + ' (' + hi.short + ')' : '?');
}
function scaleRow(rk, iid, e, j) {
  const wrap = el('div', 'scale'); wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-label', 'your finding score');
  for (const v of SCALE_VALS) {
    const key = fmtScore(v), a = SCALE_BY[key], on = e.corrected != null && Math.abs(e.corrected - v) < 1e-9;
    const b = el('button', 'sb' + (a ? ' anch' : '') + (on ? ' on' : '') + (scored(j) && Math.abs(j.score - v) < 1e-9 ? ' jd' : ''));
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.appendChild(el('span', 'n', key)); b.appendChild(el('span', 'sl', a ? a.short : ''));
    b.title = (a ? key + ' — ' + a.full : tweenTitle(v)) + (scored(j) && Math.abs(j.score - v) < 1e-9 ? '  [the judge\'s score]' : '');
    b.onclick = ev => { ev.stopPropagation(); setEntry(rk, iid, {corrected: on ? null : v}); refresh(rk, iid); };
    wrap.appendChild(b);
  }
  return wrap;
}
function quarterRow(rk, iid, e, j) {
  const wrap = el('div', 'scale q'); wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-label', 'your sub-finding score');
  for (const a of SUB_SCALE) {
    const v = a.v, on = e.corrected != null && Math.abs(e.corrected - v) < 1e-9, jd = scored(j) && Math.abs(j.score - v) < 1e-9;
    const b = el('button', 'sb anch' + (on ? ' on' : '') + (jd ? ' jd' : '')); b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.appendChild(el('span', 'n', fmtQ(v))); b.appendChild(el('span', 'sl', a.short));
    b.title = a.key + ' — ' + a.full + (jd ? '  [the judge\'s score]' : '');
    b.onclick = ev => { ev.stopPropagation(); setEntry(rk, iid, {corrected: on ? null : v}); refresh(rk, iid); };
    wrap.appendChild(b);
  }
  return wrap;
}
function othersRow(rk, iid, e, sub) {
  const rows = [];
  for (const w of auditors()) { if (w === ME) continue; const o = entryOf(w, rk, iid); if (!o || (o.corrected == null && !o.verdict && !o.comment && !o.contra_wrong)) continue; rows.push([w, o]); }
  if (!rows.length) return null;
  const box = el('div', 'other');
  for (const [w, o] of rows) {
    const line = el('div', 'oline'); line.appendChild(el('span', 'who', w + ' said'));
    if (o.corrected != null) line.appendChild(el('span', 'sc ' + scoreClass(o.corrected), sub ? fmtQ(o.corrected) : fmtScore(o.corrected)));
    if (o.verdict) line.appendChild(el('span', 'cat', (CAT[o.verdict] || [o.verdict])[0]));
    if (o.contra_wrong) line.appendChild(el('span', 'cat', '⚑ contradicted flag wrong'));
    if (o.item_issue) line.appendChild(el('span', 'cat', '⚑ item'));
    const d = (e.corrected != null && o.corrected != null) ? Math.abs(e.corrected - o.corrected) : 0;
    if (d > DISAGREE + 1e-9) line.appendChild(el('span', 'badge dang', 'you disagree by ' + fmtQ(d)));
    if (o.comment) line.appendChild(el('div', 'ocmt', '“' + o.comment + '”'));
    box.appendChild(line);
  }
  return box;
}

/* ---------- the finding block: finding level first, then every sub-finding ---------- */
function covLine(rk, fid) {
  const c = (RBY[rk].cov || {})[fid]; if (!c) return null;
  return el('span', 'cat', 'scan coverage: ' + (c.group_ratio == null ? 'no listed scans' : Math.round(100 * c.group_ratio) + '% of items with scans') + ' · ' + c.cited_linked + '/' + c.cited_total + ' cited scans linked');
}
function subRow(rk, sid, opts) {
  const j = J(rk, sid), e = entry(rk, sid) || {};
  const open = !opts.compact || opts.focus.has(sid) || expanded.has(rk + '/' + sid) || sid === selItem;
  const row = el('div', 'srow ' + jClass(j) + (sid === selItem ? ' sel' : '')); row.dataset.iid = sid;
  const sh = el('button', 'sh'); sh.setAttribute('aria-expanded', open ? 'true' : 'false');
  sh.appendChild(el('span', 'badge', sid)); sh.appendChild(judgePill(j, true)); const cb = contraBadge(j); if (cb) sh.appendChild(cb);
  sh.appendChild(el('span', 't', ITEM[sid].text));
  const mine = [e.corrected != null ? 'you ' + fmtQ(e.corrected) : '', e.verdict ? (CAT[e.verdict] || [e.verdict])[0] : '', flagged(rk, sid) ? '⚑' : ''].filter(Boolean).join(' · ');
  if (mine) sh.appendChild(el('span', 'mine', mine));
  sh.appendChild(el('span', 'cat', open ? '▾' : '▸'));
  sh.title = 'select ' + sid + ' (scrolls both panes); ' + (open ? '' : 'expands the row');
  sh.onclick = ev => { ev.stopPropagation(); if (opts.compact) { const k = rk + '/' + sid; open && sid === selItem ? expanded.delete(k) : expanded.add(k); } selectItem(sid, {keepCard: true}); };
  row.appendChild(sh);
  if (!open) return row;
  row.appendChild(itemInfo(sid, false));
  row.appendChild(scansLine(rk, sid));
  row.appendChild(judgeBox(rk, sid));
  row.appendChild(auditControls(rk, sid, opts));
  return row;
}
function findingBlock(rk, fid, opts) {
  opts = Object.assign({compact: false, focus: new Set(), jump: false}, opts || {});
  const f = ITEM[fid], j = J(rk, fid), box = el('div', 'fblock'); box.dataset.fid = fid;
  const id = el('div', 'cl-id'); id.appendChild(el('span', 'badge', f.id)); id.appendChild(el('span', '', f.kind + (f.tags.includes('added') ? ' · added' : '') + ' · ' + f.subs.length + ' sub-findings'));
  const cv = covLine(rk, fid); if (cv) id.appendChild(cv);
  const a = el('button', 'link', 'show in the article →'); a.onclick = ev => { ev.stopPropagation(); selectItem(fid, {human: true, keepCard: true}); }; id.appendChild(a);
  box.appendChild(id);
  box.appendChild(itemInfo(fid, true));
  if (!f.subs.length) box.appendChild(scansLine(rk, fid));
  box.appendChild(el('div', 'lvl', 'Finding ' + fid + ' as a whole'));
  const jb = judgeBox(rk, fid); const rb = refBox(rk, fid); if (rb) jb.appendChild(rb); box.appendChild(jb);
  box.appendChild(auditControls(rk, fid, opts));
  if (f.subs.length) {
    box.appendChild(el('div', 'lvl', 'Sub-findings'));
    const subs = el('div', 'subs'); for (const s of f.subs) subs.appendChild(subRow(rk, s.id, opts)); box.appendChild(subs);
  }
  return box;
}
function refresh(rk, iid) {
  if (view === 'report') { renderRail(); renderClaimLine(); for (const li of [...openParas]) updateParaLine(rk, li); renderClaimCard(); }
  else if (view === 'claim') { const c = document.querySelector('.card[data-key="' + rk + '"]'); if (c) c.replaceWith(cardFor(rk, ITEM[iid].head)); }
  renderStats(); renderList();
  refocus(iid);
}
/* re-rendering replaces the buttons; put the keyboard focus back on the same control */
let focusSig = null;
document.addEventListener('focusin', ev => { const t = ev.target; const blk = t.closest && t.closest('[data-iid],[data-fid]'); focusSig = blk ? {iid: blk.dataset.iid || blk.dataset.fid, text: t.textContent, tag: t.tagName} : null; });
function refocus(iid) {
  if (!focusSig || focusSig.tag !== 'BUTTON') return;
  const sig = focusSig;
  const scope = [...document.querySelectorAll('[data-iid="' + sig.iid + '"],[data-fid="' + sig.iid + '"]')];
  for (const s of scope) for (const b of s.querySelectorAll('button')) {
    if (b.closest('[data-iid],[data-fid]') !== s && s.dataset.fid) continue;
    if (b.textContent.replace(/^⚑ /, '') === sig.text.replace(/^⚑ /, '')) { b.focus({preventScroll: true}); return; }
  }
}

/* ---------- the article pane ---------- */
const HF = {ready: false, marks: {}, err: null};
function initHuman() {
  const f = document.getElementById('hframe');
  f.onload = () => { try { indexHuman(f.contentDocument); } catch (e) { HF.err = e.message; setHrNote('could not read the article: ' + e.message); } };
  f.onerror = () => { HF.err = 'load failed'; setHrNote('could not load the article'); };
  f.src = fileURL(D.article_html);
}
const SKIP = new Set(D.skip_classes || []);
function skipped(node) { for (let e = node.parentElement; e; e = e.parentElement) { const cl = e.classList; if (!cl) continue; for (const c of SKIP) if (cl.contains(c)) return true; } return false; }
const FOLD = {'’': "'", '‘': "'", '“': '"', '”': '"', '—': '-', '–': '-', '‑': '-', ' ': ' '};
function fold(s) { let o = ''; for (const ch of s) o += FOLD[ch] || ch; return o; }
function indexHuman(doc) {
  const w = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, null);
  const nodes = [], offs = [], buf = []; let prev = true, n;
  while ((n = w.nextNode())) {
    if (skipped(n)) continue;
    const t = n.nodeValue;
    for (let i = 0; i < t.length; i++) {
      const ch = t[i];
      if (/\s/.test(ch)) { if (prev) continue; buf.push(' '); nodes.push(n); offs.push(i); prev = true; }
      else { buf.push(ch); nodes.push(n); offs.push(i); prev = false; }
    }
  }
  HF.doc = doc; HF.text = buf.join(''); HF.folded = fold(HF.text); HF.nodes = nodes; HF.offs = offs;
  markHuman(); HF.ready = true;
  highlightHuman(true); if (view === 'report' && selReport) renderClaimLine();
}
function collectSegs(a, b, iid, map) {
  let k = a;
  while (k < b) { const node = HF.nodes[k]; let j = k; while (j + 1 < b && HF.nodes[j + 1] === node) j++; if (!map.has(node)) map.set(node, []); map.get(node).push({a: HF.offs[k], b: HF.offs[j] + 1, iid}); k = j + 1; }
}
function markHuman() {
  const map = new Map(); HF.missing = [];
  for (const iid of ORDER) for (const sp of (ITEM[iid].quotes || [])) {
    const q = sp.replace(/\s+/g, ' ').trim(); if (q.length < 8) continue;
    let i = HF.text.indexOf(q); if (i < 0) i = HF.folded.indexOf(fold(q));
    if (i < 0) { HF.missing.push(iid); continue; }
    collectSegs(i, i + q.length, iid, map);
  }
  HF.marks = {};
  for (const [node, segs] of map) {
    /* nested quotes (a sub-finding quoting part of its finding's passage) are split per node;
       overlapping segments keep the first, so each character sits in at most one mark */
    segs.sort((x, y) => y.a - x.a || x.b - y.b);
    let last = Infinity;
    for (const sg of segs) {
      if (!node.parentNode || sg.b > last || sg.a >= sg.b || sg.b > node.nodeValue.length) continue;
      node.splitText(sg.b); const mid = node.splitText(sg.a);
      const m = HF.doc.createElement('mark'); m.setAttribute('data-audit', sg.iid); m.title = sg.iid + ' · ' + ITEM[sg.iid].text;
      m.onclick = () => selectItem(sg.iid, {keepCard: true});
      mid.parentNode.replaceChild(m, mid); m.appendChild(mid);
      (HF.marks[sg.iid] = HF.marks[sg.iid] || []).push(m); last = sg.a;
    }
  }
}
/* where a sub-finding's quote is the same passage as its finding's, the finding's mark holds it */
function marksFor(iid) {
  const own = HF.marks[iid] || []; if (own.length || !HF.doc) return own;
  const qs = (ITEM[iid].quotes || []).map(q => q.replace(/\s+/g, ' ').trim());
  const out = []; for (const m of HF.doc.querySelectorAll('mark[data-audit]')) { const t = m.textContent.replace(/\s+/g, ' ').trim(); if (qs.some(q => q.includes(t) && t.length > 20)) out.push(m); }
  return out;
}
function anchorNote(iid) {
  if (HF.err) return 'article unavailable (' + HF.err + ')';
  if (!HF.ready) return 'loading the article…';
  const it = ITEM[iid];
  if (!(it.quotes || []).length) return iid + ': no article quote (' + (it.tags.includes('added') ? 'added by the benchmark authors' : 'none recorded') + ')';
  const n = marksFor(iid).length;
  if (!n) return 'no anchor for ' + iid + ' — its quote does not occur in the article';
  return iid + ': ' + n + ' anchored passage' + (n > 1 ? 's' : '');
}
function setHrNote(msg) { document.getElementById('hr-note').textContent = msg != null ? msg : anchorNote(selItem); }
function highlightHuman(scroll) {
  setHrNote(); if (!HF.ready) return;
  const grp = new Set(group(ITEM[selItem].head));
  for (const [iid, ms] of Object.entries(HF.marks)) for (const m of ms) { m.classList.toggle('grp', grp.has(iid)); m.classList.toggle('sel', iid === selItem); }
  let ms = marksFor(selItem); if (!ms.length) ms = marksFor(ITEM[selItem].head);
  for (const m of ms) m.classList.add('sel');
  if (!ms.length || scroll === false) return;
  ms[0].scrollIntoView({block: 'center', behavior: 'smooth'});
  for (const m of ms) { m.classList.remove('flash'); void m.offsetWidth; m.classList.add('flash'); }
}

/* ---------- report view ---------- */
function selectItem(iid, opts) {
  opts = opts || {};
  const prevHead = ITEM[selItem].head;
  selItem = iid; if (!opts.keepCard || ITEM[iid].head !== prevHead) cardForced = false;
  if (view !== 'report') return;
  renderRail(); renderClaimLine(); highlightModel(!opts.human && !opts.noScroll); highlightHuman(); markScans();
  for (const li of [...openParas]) updateParaLine(selReport, li);
  renderClaimCard();
}
function renderRail() {
  const rail = document.getElementById('rail'); rail.replaceChildren(); if (!selReport) return;
  for (const fid of FIDS) {
    if (!findingOk(selReport, fid)) continue;
    const j = J(selReport, fid), ids = group(fid);
    const ch = el('button', 'chip' + (fid === ITEM[selItem].head ? ' sel' : '') + (scored(j) ? '' : ' un'));
    ch.appendChild(el('span', 'dot ' + (j.status === 'pending' ? 'pend' : jClass(j)))); ch.appendChild(document.createTextNode(fid));
    ch.appendChild(el('span', 'st', scored(j) ? fmtScore(j.score) : statusLabel(j.status)));
    if (ids.some(i => J(selReport, i).contradicted)) ch.appendChild(el('span', 'cx', '⚠'));
    const done = ids.filter(i => audited(selReport, i)).length; if (done) ch.appendChild(el('span', 'st', done + '/' + ids.length + (done === ids.length ? '✓' : '')));
    if (ids.some(i => flagged(selReport, i))) ch.appendChild(el('span', 'st', '⚑'));
    if (ids.some(i => disagreement(selReport, i))) { ch.classList.add('dis'); ch.appendChild(el('span', 'st', '≠')); }
    ch.title = fid + ' — ' + ITEM[fid].text; ch.onclick = () => { selectItem(fid); jumpToItem(); }; rail.appendChild(ch);
  }
}
function lineFor(iid) { for (const d of document.querySelectorAll('#mdoc .ln.p')) if ((d.dataset.iids || '').split(',').includes(iid)) return +d.dataset.li; return null; }
function lineForGroup(iid) {
  let li = lineFor(iid); if (li != null) return li;
  for (const i of group(ITEM[iid].head)) { li = lineFor(i); if (li != null) return li; }
  return null;
}
/* the item's own highlighted line opens a card under it; an item with no line opens the
   floating card, so unquoted and unscored findings stay auditable */
function jumpToItem() {
  const li = lineFor(selItem);
  if (li == null) { cardForced = true; renderClaimCard(); renderClaimLine(); return; }
  openParas.add(li); updateParaLine(selReport, li);
}
function renderClaimLine() {
  const box = document.getElementById('claimline'); box.replaceChildren(); if (!selReport) return;
  const fid = ITEM[selItem].head, j = J(selReport, selItem);
  box.appendChild(el('span', 'badge', selItem)); box.appendChild(judgePill(j, !isHead(selItem)));
  const cb = contraBadge(j); if (cb) box.appendChild(cb);
  box.appendChild(el('span', 'txt', ITEM[selItem].text));
  box.appendChild(el('span', 'spacer'));
  box.appendChild(el('span', 'anchor', anchorNote(selItem)));
  const b = el('button', 'vb plain' + (cardForced ? ' on' : ''), 'whole finding ' + fid);
  b.title = 'open the finding card with every sub-finding'; b.setAttribute('aria-pressed', cardForced ? 'true' : 'false');
  b.onclick = () => { cardForced = !cardForced; renderClaimCard(); renderClaimLine(); if (cardForced) { const c = document.getElementById('claimcard'); const f = c.querySelector('button'); if (f) f.focus(); } };
  box.appendChild(b);
}
function renderClaimCard() {
  const box = document.getElementById('claimcard');
  if (view !== 'report' || !selReport) { box.hidden = true; return; }
  if (!cardForced && lineFor(selItem) != null) { box.hidden = true; box.replaceChildren(); return; }
  if (!cardForced && !loaded(selReport)) { box.hidden = true; return; }
  box.hidden = false; box.replaceChildren();
  const fid = ITEM[selItem].head;
  const hdr = el('div', 'hdr', cardForced ? 'finding ' + fid + ' — every sub-finding' : selItem + ' has no highlighted line in this report — audit it here');
  const x = el('button', 'x', '✕'); x.setAttribute('aria-label', 'close the finding card'); x.onclick = () => { cardForced = false; box.hidden = true; box.replaceChildren(); renderClaimLine(); if (lineFor(selItem) == null) { cardForced = false; } }; hdr.appendChild(x);
  box.appendChild(hdr);
  box.appendChild(findingBlock(selReport, fid, {compact: !cardForced, focus: new Set([selItem])}));
  const s = box.querySelector('.srow.sel'); if (s) setTimeout(() => s.scrollIntoView({block: 'nearest'}), 0);
}
function lineClass(line, inCode) {
  if (inCode || line.startsWith('```')) return 'code';
  if (/^#\s/.test(line)) return 'h1'; if (/^##\s/.test(line)) return 'h2'; if (/^#{3,}\s/.test(line)) return 'h3';
  if (line.startsWith('|')) return 'tbl'; if (line.startsWith('>')) return 'quote'; return '';
}
function decorateLine(div, rk, li) {
  const a = para(rk, li); div.classList.remove('has', 'a-true', 'a-false', 'a-irr', 'a-note');
  if (!a) return; div.classList.add('has');
  if (a.truth === 'false' || a.rating === 'high') div.classList.add('a-false'); else if (a.truth === 'true' || a.rating) div.classList.add('a-true'); else div.classList.add('a-note');
}
function paraQuestions(rk, li, iids) {
  const a = para(rk, li) || {}; const box = el('div', 'qs'); const r1 = el('div', 'row');
  if (!iids.length) {
    r1.appendChild(el('span', 'lab', 'No finding matched here — true?'));
    for (const [v, l] of [['true', 'true'], ['false', 'false'], ['unsure', 'unsure']]) chipBtn(r1, a.truth === v, l, () => { setPara(rk, li, {truth: a.truth === v ? null : v}); updateParaLine(rk, li); }, v === 'true' ? 'ok' : v === 'false' ? 'dang' : 'grey');
  } else {
    r1.appendChild(el('span', 'lab', 'This paragraph (' + iids.join(', ') + ') — the judge\'s ratings are'));
    for (const [v, l] of [['agree', 'right'], ['high', 'too high'], ['low', 'too low']]) chipBtn(r1, a.rating === v, l, () => { setPara(rk, li, {rating: a.rating === v ? null : v}); updateParaLine(rk, li); }, v === 'agree' ? 'ok' : 'warn');
    r1.appendChild(el('span', 'lab', '· also true?'));
    for (const [v, l] of [['true', 'true'], ['false', 'false']]) chipBtn(r1, a.truth === v, l, () => { setPara(rk, li, {truth: a.truth === v ? null : v}); updateParaLine(rk, li); }, v === 'true' ? 'ok' : 'dang');
  }
  box.appendChild(r1); return box;
}
/* One card under the line: one finding block per finding with a quote on this line (the
   items quoted here opened, the rest folded), then the paragraph questions. */
function lineCard(rk, li, iids) {
  const s = el('div', 'strip'); s.dataset.li = li; s.onclick = ev => ev.stopPropagation();
  const heads = [...new Set(iids.map(i => ITEM[i].head))];
  heads.sort((a, b) => (a === ITEM[selItem].head ? -1 : 0) - (b === ITEM[selItem].head ? -1 : 0));
  for (const fid of heads) {
    const cb = el('div', 'cbox' + (fid === ITEM[selItem].head ? ' sel' : ''));
    cb.appendChild(findingBlock(rk, fid, {compact: true, focus: new Set(iids)}));
    s.appendChild(cb);
  }
  s.appendChild(paraQuestions(rk, li, iids));
  return s;
}
function updateParaLine(rk, li) {
  const div = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (!div) return;
  decorateLine(div, rk, li); const old = div.nextElementSibling; if (old && old.classList.contains('strip')) old.remove();
  if (openParas.has(li)) div.after(lineCard(rk, li, (div.dataset.iids || '').split(',').filter(Boolean)));
  renderStats();
}
function togglePara(rk, li) {
  openParas.has(li) ? openParas.delete(li) : openParas.add(li); updateParaLine(rk, li);
  if (openParas.has(li)) { const b = document.querySelector('#mdoc .strip[data-li="' + li + '"] button'); if (b) b.focus(); }
}

/* ---------- markdown, rendered without moving a character ----------
   As on the message-board page: every character stays in the DOM in source order and the
   syntax markers are hidden, so the Python offsets that drive the highlights still land.
   Links show their text; the `[`, `](url)` are hidden markers and the text is an <a>. */
const SCAN_RE = /urlquery\.net\/report\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/;
function mdRuns(line, cls) {
  const n = line.length, k = new Array(n).fill(''); const links = [];
  if (cls === 'code') return {k, links};
  const set = (s, e, v) => { for (let i = s; i < e; i++) k[i] = v; };
  const free = (s, e) => { for (let i = s; i < e; i++) if (k[i]) return false; return true; };
  if (/^\s*(?:[-*_] *){3,}$/.test(line)) { set(0, n, 'mk'); return {k, links}; }
  let m;
  if ((m = /^(\s*)#{1,6}\s+/.exec(line))) set(m[1].length, m[0].length, 'mk');
  else if ((m = /^(\s*)>+\s?/.exec(line))) set(m[1].length, m[0].length, 'mk');
  else if ((m = /^(\s*)[-*+](\s+)/.exec(line))) set(m[1].length, m[1].length + 1, 'bul');
  const pass = (re, kind) => {
    re.lastIndex = 0; let mm;
    while ((mm = re.exec(line))) {
      const s = mm.index, e = s + mm[0].length, w = mm[1].length;
      if (!free(s, e)) continue;
      if (mm[1][0] === '_' && (/[A-Za-z0-9]/.test(s ? line[s - 1] : ' ') || /[A-Za-z0-9]/.test(e < n ? line[e] : ' '))) continue;
      set(s, s + w, 'mk'); set(e - w, e, 'mk'); set(s + w, e - w, kind);
    }
  };
  pass(/(`+)([^`]+?)\1/g, 'code');
  /* [text](url): hide the brackets and the url, render the text as a link */
  const lre = /\[([^\]\n]*)\]\(([^)\s]*)\)/g; let lm;
  while ((lm = lre.exec(line))) {
    const s = lm.index, e = s + lm[0].length, ts = s + 1, te = ts + lm[1].length;
    let clean = true; for (let i = s; i < e; i++) if (k[i] && k[i] !== 'code') { clean = false; break; }
    if (!clean || !lm[1].length) continue;
    const idx = links.push(lm[2]) - 1;
    k[s] = 'mk'; set(te, e, 'mk'); for (let i = ts; i < te; i++) if (!k[i]) k[i] = 'link:' + idx; else if (k[i] === 'code') k[i] = 'linkc:' + idx;
  }
  /* a bare scan URL is a link too */
  const bre = /https?:\/\/urlquery\.net\/report\/[0-9a-f-]{36}/g; let bm;
  while ((bm = bre.exec(line))) { const s = bm.index, e = s + bm[0].length; if (!free(s, e)) continue; const idx = links.push(bm[0]) - 1; set(s, e, 'link:' + idx); }
  if (cls === 'tbl') { for (let i = 0; i < n; i++) if (line[i] === '|' && !k[i]) k[i] = 'pipe'; return {k, links}; }
  pass(/(\*\*|__)(\S(?:[^\n]*?\S)?)\1/g, 'strong');
  pass(/(\*|_)(\S(?:[^\n]*?\S)?)\1/g, 'em');
  return {k, links};
}
function mdRun(parent, text, kind, links) {
  if (!kind) { parent.appendChild(document.createTextNode(text)); return; }
  if (kind.startsWith('link')) {
    const url = links[+kind.split(':')[1]] || '';
    const a = document.createElement('a'); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.title = url;
    const sm = SCAN_RE.exec(url); if (sm) a.dataset.scan = sm[1];
    if (kind.startsWith('linkc')) { const c = document.createElement('code'); c.textContent = text; a.appendChild(c); } else a.textContent = text;
    a.onclick = ev => ev.stopPropagation(); parent.appendChild(a); return;
  }
  const x = document.createElement(kind === 'strong' ? 'strong' : kind === 'em' ? 'em' : kind === 'code' ? 'code' : 'span');
  if (kind === 'mk' || kind === 'bul' || kind === 'pipe') x.className = 'md-' + kind;
  x.textContent = text; parent.appendChild(x);
}
function mdEmit(parent, line, r, from, to) {
  let i = from; const k = r.k;
  while (i < to) { let j = i; while (j + 1 < to && k[j + 1] === k[i]) j++; mdRun(parent, line.slice(i, j + 1), k[i], r.links); i = j + 1; }
}
function markLabel(cover) { return cover.map(r => r.iid + ' (' + (r.score == null ? 'unscored' : fmtQ(r.score)) + ') ' + ITEM[r.iid].text).join(' · '); }
function renderDoc(target, text, ranges, rk) {
  const lines = text.split('\n'); const frag = document.createDocumentFragment(); let off = 0, inCode = false;
  lines.forEach((line, li) => {
    const ls = off, le = off + line.length; off = le + 1;
    const cls = lineClass(line, inCode);
    const div = el('div', 'ln ' + cls); if (line.startsWith('```')) inCode = !inCode;
    const r = mdRuns(line, cls);
    const cuts = new Set([ls, le]); const hits = [];
    for (const g of ranges) if (g.e > ls && g.s < le) { hits.push(g); cuts.add(Math.max(g.s, ls)); cuts.add(Math.min(g.e, le)); }
    if (!hits.length) mdEmit(div, line, r, 0, line.length);
    else {
      const pts = [...cuts].sort((a, b) => a - b);
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1]; if (a >= b) continue; const cover = hits.filter(g => g.s < b && g.e > a);
        if (!cover.length) { mdEmit(div, line, r, a - ls, b - ls); continue; }
        const m = el('mark'); m.tabIndex = 0; m.setAttribute('role', 'button');
        const sel = cover.find(g => g.iid === selItem); const top = sel || cover.slice().sort((x, y) => (y.score || 0) - (x.score || 0))[0];
        m.className = (top.score == null ? 's0' : scoreClass(top.score)); m.dataset.iids = cover.map(g => g.iid).join(',');
        m.title = markLabel(cover); m.setAttribute('aria-label', 'audit ' + cover.map(g => g.iid).join(', '));
        mdEmit(m, line, r, a - ls, b - ls);
        const act = ev => {
          ev.stopPropagation();
          const ids = cover.map(g => g.iid); const cur = ids.indexOf(selItem);
          const next = cur >= 0 && ids.length > 1 ? ids[(cur + 1) % ids.length] : ids[0];
          selectItem(next, {noScroll: true}); openParas.add(li); updateParaLine(rk, li);
        };
        m.onclick = act; m.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); act(ev); } };
        div.appendChild(m);
      }
    }
    if (line.trim()) {
      div.classList.add('p'); div.dataset.li = li; div.dataset.iids = [...new Set(hits.map(h => h.iid))].join(',');
      const g = el('button', 'g', '✎'); g.title = 'note this paragraph'; g.setAttribute('aria-label', 'note paragraph ' + (li + 1));
      g.onclick = ev => { ev.stopPropagation(); togglePara(rk, li); };
      div.prepend(g); decorateLine(div, rk, li); frag.appendChild(div);
      if (openParas.has(li)) frag.appendChild(lineCard(rk, li, div.dataset.iids.split(',').filter(Boolean)));
      return;
    }
    frag.appendChild(div);
  });
  target.replaceChildren(frag);
}
function highlightModel(scroll) {
  const root = document.getElementById('mdoc'); let first = null, firstGrp = null; const grp = new Set(group(ITEM[selItem].head));
  for (const m of root.querySelectorAll('mark')) {
    const ids = (m.dataset.iids || '').split(','); const on = ids.includes(selItem);
    m.classList.toggle('sel', on); m.classList.toggle('grp', ids.some(i => grp.has(i)));
    if (on && !first) first = m; if (!firstGrp && ids.some(i => grp.has(i))) firstGrp = m;
  }
  const t = first || firstGrp;
  if (t && scroll !== false) t.scrollIntoView({block: 'center', behavior: 'smooth'});
}
/* links to the selected finding's listed scans, and more strongly to the selected item's */
function markScans() {
  const fid = ITEM[selItem].head, all = new Set(), mine = new Set(ITEM[selItem].evidence_scans || []);
  for (const i of group(fid)) for (const s of (ITEM[i].evidence_scans || [])) all.add(s);
  let n = 0; const hit = new Set();
  for (const a of document.querySelectorAll('#mdoc a[data-scan]')) {
    const on = all.has(a.dataset.scan); a.classList.toggle('ev', on); a.classList.toggle('evsel', mine.has(a.dataset.scan));
    if (on) { n++; hit.add(a.dataset.scan); }
    a.title = a.href + (on ? '  — listed scan for ' + group(fid).filter(i => (ITEM[i].evidence_scans || []).includes(a.dataset.scan)).join(', ') : '');
  }
  const r = selReport && RBY[selReport];
  document.getElementById('mr-title').textContent = r ? r.title + ' · r' + r.rep + ' · ' + r.linked_total + ' scans linked · ' + hit.size + ' of ' + all.size + ' ' + fid + ' listed scans' : '';
}
function jumpToScan(s) {
  if (view !== 'report') return;
  const a = document.querySelector('#mdoc a[data-scan="' + s + '"]'); if (!a) return;
  a.scrollIntoView({block: 'center', behavior: 'smooth'}); a.classList.remove('flash'); void a.offsetWidth; a.classList.add('flash'); setTimeout(() => a.classList.remove('flash'), 1500);
}
function renderDocs() {
  if (!selReport) { document.getElementById('mdoc').replaceChildren(); document.getElementById('mr-title').textContent = ''; return; }
  if (!loaded(selReport)) {
    const want = selReport;
    document.getElementById('mdoc').replaceChildren(el('div', 'empty', 'loading report…'));
    details(want).then(() => { if (selReport === want && view === 'report') renderDocs(); })
                 .catch(e => { if (selReport === want) document.getElementById('mdoc').replaceChildren(el('div', 'empty', 'could not load this report: ' + e.message)); });
    return;
  }
  const r = RBY[selReport];
  const ranges = [];
  for (const iid of ORDER) { const it = r.items[iid]; if (!it) continue; for (const [s, e] of it.ranges) ranges.push({s, e, iid, score: jscore(selReport, iid)}); }
  renderDoc(document.getElementById('mdoc'), r.text, ranges, selReport);
  renderReportNotes();
  highlightModel(); highlightHuman(); markScans(); renderClaimLine(); renderClaimCard();
}
function renderReportNotes() {
  const box = document.getElementById('mnotes'); box.replaceChildren(); if (!selReport) return;
  const nt = note(selReport) || {};
  for (const [k, lab, ph] of [['hypotheses', 'Hypotheses — what in this report is true vs false', 'e.g. the AIHW chunked download is real but dated wrong…'], ['biases', 'Biases the judge or the model is running into', 'e.g. judge credits evidence without the conclusion; misses findings stated in the timeline…']]) {
    const lb = el('label', '', lab); const ta = el('textarea'); ta.placeholder = ph; ta.value = nt[k] || ''; ta.setAttribute('aria-label', lab); ta.oninput = () => { setNote(selReport, {[k]: ta.value}); }; box.appendChild(lb); box.appendChild(ta);
  }
  const btn = document.getElementById('mnotes-btn'); btn.textContent = 'notes' + (hasNotes(selReport) ? ' ●' : ''); btn.classList.toggle('on', !box.hidden);
}
document.getElementById('mnotes-btn').onclick = () => { const b = document.getElementById('mnotes'); b.hidden = !b.hidden; document.getElementById('mnotes-btn').classList.toggle('on', !b.hidden); if (!b.hidden) { const ta = b.querySelector('textarea'); if (ta) ta.focus(); } };

/* ---------- finding view ---------- */
function cardFor(rk, fid) {
  const r = RBY[rk]; const card = el('div', 'card'); card.dataset.key = rk;
  const hd = el('div', 'hd'); hd.appendChild(el('span', '', r.title + ' · r' + r.rep)); hd.appendChild(el('span', 'b', (r.condition || '') + ' · judge mean ' + meanLabel(r)));
  card.appendChild(hd); card.appendChild(findingBlock(rk, fid, {jump: true})); return card;
}
function renderClaimView() {
  const head = document.getElementById('claimhead'); head.replaceChildren();
  const f = ITEM[selFindView];
  const id = el('div', 'cl-id'); id.appendChild(el('span', 'badge', f.id)); id.appendChild(el('span', '', f.kind + ' · ' + f.subs.length + ' sub-findings')); head.appendChild(id);
  head.appendChild(itemInfo(f.id, true));
  for (const s of f.subs) { const d = el('div', 'gt'); d.appendChild(el('b', '', s.id + ' ')); d.appendChild(document.createTextNode(s.text)); head.appendChild(d); }
  const cards = document.getElementById('cards'); cards.replaceChildren();
  const reps = filteredReports().filter(r => findingOk(r.key, selFindView)).sort((a, b) => (jscore(b.key, selFindView) == null ? -1 : jscore(b.key, selFindView)) - (jscore(a.key, selFindView) == null ? -1 : jscore(a.key, selFindView)) || a.title.localeCompare(b.title));
  head.appendChild(el('div', 'cat', reps.length + ' reports shown · sorted by the judge\'s finding score (unscored last)'));
  for (const r of reps) cards.appendChild(cardFor(r.key, selFindView));
  if (!reps.length) cards.appendChild(el('div', 'empty', 'no reports match the filters'));
  const fid = selFindView;
  for (const r of reps) if (!loaded(r.key)) details(r.key).then(() => {
    if (view !== 'claim' || selFindView !== fid) return;
    const old = document.querySelector('#cards .card[data-key="' + r.key + '"]'); if (old) old.replaceWith(cardFor(r.key, fid));
  }).catch(() => {});
}

/* ---------- notes view ---------- */
function notesCard(rk) {
  const c = el('div', 'ncard'); const global = rk === GLOBAL; const nt = note(rk) || {};
  const h = el('h4', '', global ? 'Across reports' : RBY[rk].title + ' · r' + RBY[rk].rep);
  if (!global) { h.appendChild(el('span', '', 'judge mean ' + meanLabel(RBY[rk]))); const a = el('button', 'link', 'open →'); a.onclick = () => switchView('report', () => { selReport = rk; }); h.appendChild(a); }
  c.appendChild(h);
  for (const [k, lab] of [['hypotheses', global ? 'Hypotheses — what the judge tends to get right or wrong' : 'Hypotheses — what in this report is true vs false'], ['biases', global ? 'Biases the judge runs into' : 'Biases the judge or model is running into']]) {
    c.appendChild(el('label', '', lab)); const ta = el('textarea'); ta.value = nt[k] || ''; ta.setAttribute('aria-label', lab); ta.oninput = () => setNote(rk, {[k]: ta.value}); c.appendChild(ta);
  }
  if (!global) {
    const lines = (RBY[rk].text || '').split('\n'); const pre = RBY[rk].run + '/p';
    const ps = Object.entries(myMap('paragraphs')).filter(([k]) => k.startsWith(pre)).map(([k, v]) => [parseInt(k.slice(pre.length)), v]).sort((a, b) => a[0] - b[0]);
    if (ps.length) c.appendChild(el('label', '', ps.length + ' paragraph notes'));
    for (const [li, a] of ps) {
      const p = el('div', 'pl'); const fake = el('div'); decorateLine(fake, rk, li); p.className = 'pl ' + [...fake.classList].filter(x => x.startsWith('a-')).join(' ');
      const tags = el('div', 'tags'); if (a.truth) tags.appendChild(el('span', '', 'true? ' + a.truth)); if (a.rating) tags.appendChild(el('span', '', 'rating: ' + (a.rating === 'agree' ? 'right' : 'too ' + a.rating)));
      const jump = el('button', 'link', '¶ ' + (li + 1) + ' →'); jump.onclick = () => switchView('report', () => { selReport = rk; openParas.clear(); openParas.add(li); }, () => { const d = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (d) d.scrollIntoView({block: 'center'}); }); tags.prepend(jump);
      p.appendChild(tags); const t = (lines[li] || a.anchor || ''); p.appendChild(el('div', 't', t.length > 400 ? t.slice(0, 400) + '…' : t)); c.appendChild(p);
    }
  }
  return c;
}
function renderNotesView() {
  const box = document.getElementById('notes'); box.replaceChildren(); box.appendChild(notesCard(GLOBAL));
  const reps = filteredReports(); const order = []; if (selReport) order.push(selReport);
  for (const r of reps) if (r.key !== selReport && (hasNotes(r.key) || paraCount(r.key))) order.push(r.key);
  for (const rk of order) box.appendChild(notesCard(rk));
  for (const rk of order) if (!loaded(rk) && paraCount(rk)) details(rk).then(() => { if (view === 'notes') renderNotesView(); }).catch(() => {});
  if (order.length <= 1) box.appendChild(el('div', 'empty', 'Reports with notes or paragraph annotations appear here as you add them.'));
}

/* ---------- top level ---------- */
function switchView(v, before, after) {
  view = v; if (before) before(); document.querySelectorAll('.tab[data-view]').forEach(t => { t.classList.toggle('active', t.dataset.view === v); t.setAttribute('aria-selected', t.dataset.view === v ? 'true' : 'false'); }); renderAll(); if (after) setTimeout(after, 0);
}
function renderMain() {
  const main = document.getElementById('main');
  main.classList.toggle('claimview', view === 'claim'); main.classList.toggle('notesview', view === 'notes');
  for (const id of ['rail', 'claimline', 'panes']) document.getElementById(id).hidden = view !== 'report';
  for (const id of ['claimhead', 'cards']) document.getElementById(id).hidden = view !== 'claim';
  document.getElementById('notes').hidden = view !== 'notes';
  if (view === 'report') { renderRail(); renderDocs(); } else { document.getElementById('claimcard').hidden = true; if (view === 'claim') renderClaimView(); else renderNotesView(); }
  renderStats();
}
function renderAll() { renderFilters(); renderList(); renderMain(); }
document.querySelectorAll('.tab[data-view]').forEach(t => t.onclick = () => switchView(t.dataset.view));
document.getElementById('q').oninput = e => { filters.q = e.target.value; renderList(); if (view !== 'report') renderMain(); else renderStats(); };
document.addEventListener('keydown', ev => {
  const tag = (ev.target.tagName || '').toLowerCase();
  if (tag === 'textarea' || tag === 'input') { if (ev.key === 'Escape') ev.target.blur(); return; }
  if (!document.getElementById('intro').hidden) return;
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  if (ev.key === '[') { toggleSidebar(); ev.preventDefault(); return; }
  const reps = filteredReports();
  if (view === 'report' && selReport) {
    const vis = ORDER.filter(i => findingOk(selReport, ITEM[i].head)); const ci = vis.indexOf(selItem);
    if (ev.key === 'j') { if (ci < vis.length - 1) { selectItem(vis[ci + 1]); jumpToItem(); } ev.preventDefault(); return; }
    if (ev.key === 'k') { if (ci > 0) { selectItem(vis[ci - 1]); jumpToItem(); } ev.preventDefault(); return; }
    const ri = reps.findIndex(r => r.key === selReport);
    if (ev.key === 'n' && ri < reps.length - 1) { selReport = reps[ri + 1].key; openParas.clear(); cardForced = false; renderMain(); renderList(); return; }
    if (ev.key === 'p' && ri > 0) { selReport = reps[ri - 1].key; openParas.clear(); cardForced = false; renderMain(); renderList(); return; }
    if (/^[1-4]$/.test(ev.key)) { const o = VERDICTS[vset(selReport, selItem)][+ev.key - 1]; if (!o) return; const e = entry(selReport, selItem) || {}; setEntry(selReport, selItem, {verdict: e.verdict === o.v ? null : o.v}); refresh(selReport, selItem); return; }
    if (ev.key === 'c') {
      if (!document.querySelector('textarea.cmt[data-iid="' + selItem + '"]')) jumpToItem();
      const ta = document.querySelector('#mdoc textarea.cmt[data-iid="' + selItem + '"]') || document.querySelector('#claimcard textarea.cmt[data-iid="' + selItem + '"]');
      if (ta) { ta.focus(); ta.scrollIntoView({block: 'center'}); ev.preventDefault(); }
      return;
    }
    if (ev.key === 'e') { document.getElementById('mnotes-btn').click(); ev.preventDefault(); return; }
  } else if (view === 'claim') {
    const ci = FIDS.indexOf(selFindView);
    if (ev.key === 'j' && ci < FIDS.length - 1) { selFindView = FIDS[ci + 1]; renderMain(); renderList(); ev.preventDefault(); }
    if (ev.key === 'k' && ci > 0) { selFindView = FIDS[ci - 1]; renderMain(); renderList(); ev.preventDefault(); }
  } else if (view === 'notes') {
    const ri = reps.findIndex(r => r.key === selReport);
    if (ev.key === 'n' && ri < reps.length - 1) { selReport = reps[ri + 1].key; renderMain(); renderList(); }
    if (ev.key === 'p' && ri > 0) { selReport = reps[ri - 1].key; renderMain(); renderList(); }
  }
});
initHuman();
renderAll();
load().then(() => {
  renderWho(); renderAll();
  let seen = false; try { seen = localStorage.getItem(INTRO_KEY) === '1'; } catch (e) {}
  if (!ME || !seen) openIntro();
});
</script></body></html>'''

if __name__ == "__main__":
    main()
