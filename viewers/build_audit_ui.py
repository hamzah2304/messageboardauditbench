#!/usr/bin/env python3
"""Build viewers/audit.html — audit the recall judge claim by claim.

Reads every benchmark/graded_inputs/<dir>/ that has an _index.jsonl (round 2 and 3
batches), the matching benchmark/graded/graded_<key>.json, the six rubric sheets and the
published human report (corpus/wiki_index.html, via scripts/wiki_report.py). Emits one
self-contained page:

- pick a report; every judge quote is highlighted in the model report (colour = score);
- pick a claim; the model pane scrolls to its quote and the human pane — the published
  page itself, in an iframe, with its own stylesheets — scrolls to the anchored passage;
- score and comment inline, in a card that opens under the matched line;
- the page autosaves to benchmark/audit/judge_audit.json through the html-viewer's
  POST /save endpoint (localStorage mirror when the server is unreachable).

Anchors, not guesses. benchmark/claims/anchors_human.json gives verbatim spans that are
known to occur in the rendered article; benchmark/claims/anchors_reports.json does the
same for the judge quotes that are not verbatim in their model report. Where no anchor
exists the quote is matched exactly or with whitespace/punctuation normalised, and if
that fails the claim is reported as having no anchor rather than highlighted approximately.
"""
import ast, importlib.util, json, os, re, shutil, sys, pathlib
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, RUBRICS, GRADED, GRADED_INPUTS, VIEWERS, CORPUS

# Which rubric and whose grades this build audits. The v1 page (default) audits the
# 30-point rubric graded by Sol; RUBRIC=v2 with JUDGE=<model> audits the 38-point one.
_RUB = os.getenv("RUBRIC", "v1")
_JUDGE = os.getenv("JUDGE", "")
IS_V2 = _RUB == "v2"
OUT = VIEWERS / ("audit_v2.html" if IS_V2 else "audit.html")
DATA_DIR = VIEWERS / "data" / ("audit_v2" if IS_V2 else "audit")   # per-report payloads; the two
# rubrics share report keys but not scores, so they must not share a payload directory
HUMAN_HTML = DATA_DIR / "_human.html"          # the published report, styled, for the iframe
AUDIT_PATH = ROOT / "benchmark" / "audit" / (
    f"judge_audit_v2_{re.sub(r'[^0-9a-zA-Z]+','_',_JUDGE).strip('_')}.json" if IS_V2
    else "judge_audit.json")
# where the grades for this build live
GRADE_DIR = (GRADED / f"judge_{re.sub(r'[^0-9a-zA-Z]+','_',_JUDGE).strip('_')}" / "v2") if IS_V2 else GRADED
N_SHEETS = 8 if IS_V2 else 6
SHEET_JSON = "v2" if IS_V2 else "rubric"
ANCHORS_HUMAN = ROOT / "benchmark" / "claims" / "anchors_human.json"
ANCHORS_REPORTS = ROOT / "benchmark" / "claims" / "anchors_reports.json"
BUILD_RUBRICS = ROOT / "benchmark" / "rubrics" / "build_rubrics.py"
# one-time copy of the pre-namespacing audit file, taken before the page can rewrite it
AUDIT_BACKUP = AUDIT_PATH.with_name("judge_audit.pre-auditors.json")

# Two or three words per anchor, for the reminder under each anchor button. The full
# wording always comes from SHEET_SCALE below; these are only the handle.
SCALE_SHORT = {"1.0": "near-paraphrase", "0.9": "90% of the value", "0.7": "core there",
               "0.5": "real effort", "0.3": "gesturing", "0.0": "absent"}

# What the auditor is being asked to do, shown once on the intro panel.
TASK_INTRO = [
    "You are checking a language-model judge, one claim at a time. A claim is a point from "
    "the human incident report. For each model report the judge gave that claim a score and "
    "quoted the line it scored from; the left pane is the model report with those quotes "
    "highlighted, the right pane is the human report with the claim's passage anchored.",
    "Decide whether the judge's call is right. The verdict buttons say what kind of mistake "
    "it is, if any; \u201cYour score\u201d is the number you would have given. You can also "
    "note a paragraph directly in the model report, and record hypotheses and biases per "
    "report under \u201cnotes\u201d.",
    "Everything saves itself to one shared file. Your judgements are kept under your name, so "
    "two people can score the same claim and the page can show where you disagree.",
]


def sheet_scale():
    """The behavioural scale, read out of build_rubrics.py's SHEET_SCALE literal.

    Parsed rather than imported: build_rubrics.py rewrites the rubric sheets at import
    time. Parsing keeps this page's anchor wording tied to the rubric's own source, so
    the page cannot drift from the sheets the judge was given.
    """
    tree = ast.parse(BUILD_RUBRICS.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SHEET_SCALE"
                                                for t in node.targets):
            out = []
            for v, text in ast.literal_eval(node.value):
                out.append({"v": float(v), "key": v, "short": SCALE_SHORT.get(v, v), "full": text})
            return sorted(out, key=lambda a: -a["v"])
    raise SystemExit("SHEET_SCALE not found in " + str(BUILD_RUBRICS))

TRANS = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
         "‑": "-", " ": " ", "​": ""}
DROP = set("*`_")


def norm_map(s):
    """Lower-case, fold quotes/dashes, drop markdown emphasis, collapse whitespace.
    Returns (normalised string, list mapping each normalised char to its source offset)."""
    out, offs, prev_space = [], [], True
    for i, ch in enumerate(s):
        c = TRANS.get(ch, ch).lower()
        if c == "" or c in DROP:
            continue
        if c.isspace():
            if prev_space:
                continue
            c, prev_space = " ", True
        else:
            prev_space = False
        out.append(c); offs.append(i)
    return "".join(out), offs


def sanitize(s):
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")


class Doc:
    def __init__(self, text):
        self.text = text
        self.norm, self.offs = norm_map(text)

    def _norm_find(self, piece):
        pn, _ = norm_map(piece)
        pn = pn.strip()
        if len(pn) < 4:
            return None
        j = self.norm.find(pn)
        if j < 0:
            return None
        return [self.offs[j], self.offs[j + len(pn) - 1] + 1]

    def find(self, quote):
        """Exact, then whitespace/punctuation-normalised. Nothing approximate."""
        q = (quote or "").strip().strip('"“”')
        if len(q) < 4:
            return [], "none"
        i = self.text.find(q)
        if i >= 0:
            return [[i, i + len(q)]], "exact"
        r = self._norm_find(q)
        if r:
            return [r], "norm"
        return [], "none"

    def find_spans(self, spans):
        """Ranges for a list of validated verbatim spans; skips any that do not occur."""
        out = []
        for s in spans:
            rngs, _ = self.find(s)
            out.extend(rngs)
        return sorted(out)


def load_anchor_file(path):
    """Tolerate either {"<key>": {...}} or {"claims": [{"id": ..., "spans": [...]}, ...]}."""
    if not path.exists():
        return {}
    d = json.loads(path.read_text())
    if isinstance(d, dict) and isinstance(d.get("claims"), list):
        out = {}
        for c in d["claims"]:
            k = c.get("key") or c.get("id")
            if c.get("key") and c.get("id") and "/" not in str(c["key"]):
                k = f"{c['key']}/{c['id']}"
            if k:
                out[k] = c
        return out
    if isinstance(d, dict) and isinstance(d.get("anchors"), dict):
        d = d["anchors"]
    return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


def spans_of(anchors, key):
    a = anchors.get(key) or {}
    return [s for s in (a.get("spans") or []) if isinstance(s, str) and s.strip()]


def wiki_report():
    spec = importlib.util.spec_from_file_location("wiki_report", ROOT / "scripts" / "wiki_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HUMAN_SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Human report</title>
<style>%s</style>
<style>
/* audit overrides: the article alone, in a narrow pane, with anchor highlights */
body{padding:0 18px}
.frame{display:block;max-width:none;padding:0}
.main{max-width:none}
mark[data-audit]{background:#FDF2EC;border-radius:3px;padding:0 1px;cursor:pointer;color:inherit}
mark[data-audit].sel{background:#FBE3D6;outline:2px solid #C15F3C}
/* a snap from the model report flashes its passage, so the jump is visible */
@keyframes auditflash{0%%{background:#F3BF9C}100%%{background:#FBE3D6}}
mark[data-audit].flash{animation:auditflash 1.1s ease-out}
@media (prefers-reduced-motion:reduce){mark[data-audit].flash{animation:none}}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
</style></head>
<body><div class="frame"><div class="main">%s</div></div></body></html>
"""


FONTS = CORPUS / "fonts"


def font_css(css: str) -> str:
    """Point the site's @font-face rules at the vendored font files.

    The stylesheet asks for fonts/et-book-*.woff relative to the page. Both panes are
    served from the viewer's /file endpoint, where a relative URL resolves to nothing,
    so rewrite each to an absolute /file?p= path. Without this both panes fall back to
    Palatino and the report stops looking like the report.
    """
    def sub(m):
        f = FONTS / m.group(1)
        return f'url("/file?p={quote(str(f))}")' if f.exists() else 'local("no-such-font")'
    return re.sub(r'url\("fonts/([^"]+)"\)', sub, css)


def face_css() -> str:
    """Just the @font-face rules, for the audit page's own document."""
    faces = re.findall(r"@font-face[^}]*}", (CORPUS / "wiki_tokens.css").read_text())
    return font_css("\n".join(faces))


def write_human_html():
    """The published report, styled, with every collapsed block already open.

    The site hides long posts behind a checkbox and its "Show the whole post" label.
    An auditor reading for evidence wants all of it, so the embedded copy ships with
    those checkboxes checked and any <details> open.
    """
    w = wiki_report()
    html = w.article_html()
    html = re.sub(r'(<input(?=[^>]*\bclass="[^"]*\bex-toggle\b)(?![^>]*\bchecked\b)[^>]*?)/?>',
                  r'\1 checked>', html)
    html = re.sub(r'<details(?![^>]*\bopen\b)', '<details open', html)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HUMAN_HTML.write_text(HUMAN_SHELL % (font_css(w.css()), html))
    return w.article_text()


def load_claims(anchors, article_text):
    claims, missing = [], []
    for i in range(1, N_SHEETS + 1):
        rub = json.loads((RUBRICS / f"{SHEET_JSON}_{i}.json").read_text())
        for c in rub["claims"]:
            gt = c.get("ground_truth") or {}
            quote = c.get("report_quote", "") or ""
            spans = spans_of(anchors, c["id"])
            source = "anchors"
            if not spans:
                # No validated anchor: the rubric quote only counts if it is verbatim.
                source = "rubric" if quote and quote in article_text else "none"
                spans = [quote] if source == "rubric" else []
            if not spans:
                missing.append(c["id"])
            claims.append({
                "id": c["id"], "rubric": rub["rubric_id"], "section": c.get("section"), "level": c.get("level"),
                "claim": c["claim"], "report_quote": quote, "mode": c.get("grading_mode"),
                "trap": c.get("trap") or "", "gt_verdict": gt.get("verdict"), "gt_notes": gt.get("notes") or "",
                "gt_corrections": gt.get("corrections") or "",
                "human_spans": spans, "anchor_source": source,
            })
    return claims, missing


def parse_stem(stem):
    parts = stem.split("__")
    d = {"prefix": parts[0], "agent": parts[1], "model": parts[2], "rep": None, "served": None, "partial": False}
    for p in parts[3:]:
        if p.startswith("rep"):
            d["rep"] = int(p[3:])
        elif p.startswith("served-"):
            d["served"] = p[len("served-"):]
        elif p == "partial":
            d["partial"] = True
    return d


def load_reports(claim_ids, ranchors):
    reports, warn = [], []
    for idx in sorted(GRADED_INPUTS.glob("*/_index.jsonl")):
        d = idx.parent
        m = re.match(r"round(\d+)_blind(\d+)$", d.name)
        if not m:
            continue
        rnd, budget = f"r{m.group(1)}", int(m.group(2))
        rows = [json.loads(l) for l in idx.read_text().splitlines() if l.strip()]
        for p in sorted(d.glob("*.md")):
            key = sanitize(p.stem)
            gpath = GRADE_DIR / f"graded_{key}.json"
            if not gpath.exists():
                warn.append(f"no grade for {p.name}"); continue
            g = json.loads(gpath.read_text())
            meta = parse_stem(p.stem)
            row = next((r for r in rows if r.get("graded_input") == p.name), None)
            if row is None:
                row = next((r for r in rows if r["agent"] == meta["agent"]
                            and str(r["model"]).replace("/", "-") == meta["model"]
                            and int(r.get("replicate", -1)) == meta["rep"]
                            and (str(r.get("model_served") or "") or None) == meta["served"]), {})
            text = p.read_text()
            doc = Doc(text)
            scores, hows = {}, {}
            for cid in claim_ids:
                s = g["scores"].get(cid) or {"score": None, "quote": "", "reason": "(no judgement recorded)"}
                quote = s.get("quote", "")
                rngs, how = ([], "none")
                spans = spans_of(ranchors, f"{key}/{cid}")
                if spans:
                    rngs = doc.find_spans(spans)
                    how = "anchor" if rngs else "none"
                if not rngs and quote:
                    rngs, how = doc.find(quote)
                scores[cid] = {"score": s.get("score"), "quote": quote, "reason": s.get("reason", ""),
                               "ranges": rngs, "match": how}
                hows[how] = hows.get(how, 0) + 1
            title = f"{meta['agent']} · {meta['model']}" + (f" (served {meta['served']})" if meta["served"] else "")
            # Only the score numbers travel in the page; quotes, reasons, highlight ranges
            # and the report body live in a per-report file the page fetches when opened.
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / f"{key}.json").write_text(json.dumps({"text": text, "scores": scores}, ensure_ascii=False))
            reports.append({
                "key": key, "file": p.name, "dir": d.name, "round": rnd, "budget": budget,
                "agent": meta["agent"], "model": meta["model"], "served": meta["served"], "rep": meta["rep"],
                "title": title, "accuracy": g.get("accuracy"), "grader": g.get("grader"),
                "wall_seconds": row.get("wall_seconds"), "effort": row.get("effort"),
                "scores": {cid: {"score": v["score"]} for cid, v in scores.items()}, "match_counts": hows,
            })
    return reports, warn


def main():
    article_text = write_human_html()
    hanch = load_anchor_file(ANCHORS_HUMAN)
    ranch = load_anchor_file(ANCHORS_REPORTS)
    claims, missing = load_claims(hanch, article_text)
    reports, warn = load_reports([c["id"] for c in claims], ranch)
    for w in warn:
        print("warn:", w)
    tot = {}
    for r in reports:
        for k, v in r["match_counts"].items():
            tot[k] = tot.get(k, 0) + v
    for stale in DATA_DIR.glob("*.json"):
        if stale.stem not in {r["key"] for r in reports}:
            stale.unlink()
    # Snapshot the audit file while it is still in the flat, unnamespaced shape. Once the
    # page has migrated it (version 3) the backup freezes, so it always holds the last
    # state before the auditor names took over.
    if AUDIT_PATH.exists():
        try:
            pre = json.loads(AUDIT_PATH.read_text()).get("version", 2) < 3
        except Exception:
            pre = False
        if pre:
            shutil.copyfile(AUDIT_PATH, AUDIT_BACKUP)
            print("snapshot of the pre-namespacing audit file ->", AUDIT_BACKUP.name)
    scale = sheet_scale()
    data = {"audit_path": str(AUDIT_PATH), "data_dir": str(DATA_DIR),
            "skip_classes": wiki_report().skip_classes(), "human_html": str(HUMAN_HTML),
            "scale": scale, "intro": TASK_INTRO,
            "claims": claims, "reports": reports,
            "built": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload).replace("/*__FONTS__*/", face_css()))
    det = sum(f.stat().st_size for f in DATA_DIR.glob("*.json"))
    anchored = sum(1 for c in claims if c["anchor_source"] == "anchors")
    print(f"{OUT}: {len(reports)} reports, {len(claims)} claims; shell {OUT.stat().st_size/1e6:.2f} MB inline + "
          f"{det/1e6:.2f} MB in {DATA_DIR.name}/ fetched on demand; quote matches {tot}")
    print(f"  human anchors: {anchored} from anchors_human.json, "
          f"{sum(1 for c in claims if c['anchor_source'] == 'rubric')} from a verbatim rubric quote"
          + (f"; NO anchor for {', '.join(missing)}" if missing else "; every claim anchored"))
    print(f"  scale: {len(scale)} anchors read from {BUILD_RUBRICS.name} "
          f"({', '.join(a['key'] for a in scale)}); 11 values 0.0-1.0 offered")
    print(f"  report anchors: {len(ranch)} entries in anchors_reports.json"
          + ("" if ranch else " (file absent — falling back to exact/normalised quote matching)")
          + f"; human page {HUMAN_HTML.stat().st_size/1e6:.2f} MB")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Judge audit — MessageBoardAuditBench</title>
<style>
/*__FONTS__*/
:root{--essay-serif:"et-book",Palatino,"Palatino Linotype","Palatino LT STD","Book Antiqua",Georgia,serif;--essay-mono:SFMono-Regular,Menlo,Consolas,Monaco,"Liberation Mono",monospace;--sans-ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--paper:#FFFFF8;--essay-ink:#111;--essay-dull:#666;--essay-wash:#F6F6EE;--essay-dull-bg:#F0F0F0;--essay-hair:#E8E8DF;--essay-rule:#D6D6CC;--essay-green:#2A623D;--essay-ui:#31566F;--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666666;--mut:#999999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok:#065F46;--warn-bg:#FEF3C7;--warn:#92400E;--dang-bg:#FEE2E2;--dang:#991B1B;--grey-bg:#ECEAE3;--grey:#555}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);font-size:13px;line-height:1.45;display:grid;grid-template-rows:auto 1fr;height:100vh;overflow:hidden}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
header{padding:6px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
h1{color:var(--accent);font-size:16px;margin:0;white-space:nowrap}
.sub{color:var(--mut);font-size:10.5px}
.tabs{display:flex;gap:4px}
.tab{padding:5px 12px;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--ink2);cursor:pointer;font-weight:600;font-size:12px;font-family:inherit}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
#sb-btn{padding:5px 9px;font-size:13px}
.stats{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto;align-items:center}
.badge{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--soft);color:var(--accent2);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.dang{background:var(--dang-bg);color:var(--dang)}.badge.grey{background:var(--grey-bg);color:var(--grey)}
#save{font-size:11px;color:var(--mut);min-width:150px;text-align:right}#save.err{color:var(--dang);font-weight:600}
#layout{display:grid;grid-template-columns:290px 1fr;min-height:0}
#layout.collapsed{grid-template-columns:1fr}#layout.collapsed aside{display:none}
aside{border-right:1px solid var(--border);display:flex;flex-direction:column;min-height:0;background:var(--card)}
.search{margin:8px 8px 4px;padding:6px 9px;border:1px solid var(--border);border-radius:7px;font-size:12px;font-family:inherit}
.filt{display:flex;gap:4px;flex-wrap:wrap;padding:2px 8px 4px;align-items:center}
.filt .lab{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;width:44px}
.filt button{font-size:11px;padding:1px 8px;border:1px solid var(--border);border-radius:20px;background:transparent;color:var(--ink2);cursor:pointer;font-family:inherit}
.filt button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#list{overflow:auto;flex:1;border-top:1px solid var(--border)}
.item{padding:6px 10px;border-bottom:1px solid var(--border);cursor:pointer;font-size:12px}
.item:hover{background:var(--row)}.item.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--accent)}
.item .nm{font-weight:600;display:flex;justify-content:space-between;gap:6px}
.item .meta{color:var(--mut);font-size:11px;display:flex;gap:8px;flex-wrap:wrap}
.item .prog{height:3px;background:var(--grey-bg);border-radius:2px;margin-top:4px;overflow:hidden}.item .prog i{display:block;height:100%;background:var(--accent)}
main{display:grid;grid-template-rows:auto auto 1fr;min-height:0}
main.claimview{grid-template-rows:auto 1fr}main.notesview{grid-template-rows:1fr}
#rail{display:flex;gap:4px;padding:5px 12px;overflow-x:auto;border-bottom:1px solid var(--border);background:var(--bg);align-items:center}
.chip{flex:none;padding:2px 7px;border-radius:6px;border:1px solid var(--border);background:var(--card);cursor:pointer;font-size:11px;font-weight:600;display:flex;gap:5px;align-items:center;font-family:inherit}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--grey-bg)}
.dot.s1{background:#34A87A}.dot.s05{background:#E4A93A}.dot.s0{background:#D6D3CB}
.chip.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--soft);background:var(--soft)}
.chip .st{font-size:10px;color:var(--mut)}
#claimline{display:flex;gap:8px;align-items:center;padding:4px 12px;border-bottom:1px solid var(--border);background:var(--card);font-size:12px;white-space:nowrap;overflow:hidden}
#claimline .txt{overflow:hidden;text-overflow:ellipsis;font-weight:600}
#claimline .anchor{color:var(--mut);font-size:11px;white-space:nowrap}
#claimline .spacer{flex:1}
.cl-id{font-size:11px;color:var(--mut);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.cl-text{font-weight:600;font-size:13.5px;margin:4px 0 6px}
.hq{font-style:italic;color:var(--ink2);border-left:3px solid var(--soft);padding-left:8px;margin:4px 0}
.gt{font-size:11.5px;color:var(--ink2);margin-top:3px}.gt b{color:var(--ink)}
.judge{margin-top:6px;padding:7px 9px;background:var(--row);border:1px solid var(--border);border-radius:8px}
.judge .q{font-style:italic;margin:4px 0}.judge .r{color:var(--ink2)}
.sc{display:inline-block;padding:1px 8px;border-radius:20px;font-weight:700;font-size:11px}
.sc.s1{background:var(--ok-bg);color:var(--ok)}.sc.s05{background:var(--warn-bg);color:var(--warn)}.sc.s0{background:var(--grey-bg);color:var(--grey)}
.verd{display:flex;flex-wrap:wrap;gap:5px;margin:4px 0 8px}
.vb{padding:4px 10px;border:1px solid var(--border);border-radius:7px;background:transparent;cursor:pointer;font-size:12px;font-weight:600;color:var(--ink2);font-family:inherit}
.vb:hover{background:var(--row)}
.vb.on.ok{background:var(--ok-bg);color:var(--ok);border-color:#9AD6BC}.vb.on.warn{background:var(--warn-bg);color:var(--warn);border-color:#E5CB7A}.vb.on.dang{background:var(--dang-bg);color:var(--dang);border-color:#F0A6A6}.vb.on.grey{background:var(--grey-bg);color:var(--grey);border-color:#C9C6BC}
.vb.on.plain{background:var(--soft);color:var(--accent2);border-color:var(--accent)}
.vb .k{font-size:10px;color:var(--mut);font-weight:400;margin-right:4px}
/* a verdict saved before its button was retired: readable, clearable, not settable */
.vkept{display:inline-flex;align-items:center;gap:5px;padding:3px 6px 3px 10px;border:1px dashed var(--border);border-radius:7px;font-size:12px;font-weight:600;color:var(--mut)}
.vkept .x{border:0;background:transparent;color:var(--mut);cursor:pointer;font-size:11px;font-family:inherit;padding:0 2px}
.vkept .x:hover{color:var(--accent)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0;font-size:12px;color:var(--ink2)}
.row .vb{padding:2px 9px}
textarea{width:100%;min-height:48px;border:1px solid var(--border);border-radius:7px;padding:6px 8px;font-family:inherit;font-size:12.5px;resize:vertical;background:#fff}
textarea:focus{outline:2px solid var(--soft);border-color:var(--accent)}
.cat{font-size:11px;color:var(--mut)}
/* the 0.0-1.0 scale: eleven buttons, the six rubric anchors raised out of the rest */
.scale{display:flex;gap:3px;flex-wrap:wrap;margin:3px 0 2px}
.sb{flex:1 1 0;min-width:46px;border:1px solid var(--border);border-radius:7px;background:transparent;cursor:pointer;font-family:inherit;padding:2px 2px 3px;color:var(--ink2);display:flex;flex-direction:column;align-items:center;gap:0;line-height:1.15}
.sb .n{font-weight:600;font-size:12px;color:var(--mut)}
.sb .sl{font-size:9px;color:var(--mut);text-align:center;min-height:1.05em;letter-spacing:-.01em}
.sb.anch{background:var(--row);border-color:#CDC9BE}
.sb.anch .n{color:var(--ink);font-weight:800;font-size:12.5px}
.sb:hover{background:var(--soft);border-color:var(--accent)}
.sb.on{background:var(--accent);border-color:var(--accent)}
.sb.on .n,.sb.on .sl{color:#fff}
.scnum{width:52px;border:1px solid var(--border);border-radius:7px;padding:2px 6px;font-family:inherit;font-size:12px;background:#fff}
.scnum:focus{outline:2px solid var(--soft);border-color:var(--accent)}
/* what the other auditor said about the same claim */
.other{margin-top:5px;border-top:1px dashed var(--border);padding-top:5px;font-size:11.5px}
.oline{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0}
.oline .who{font-weight:700;color:var(--accent2)}
.oline .ocmt{flex-basis:100%;color:var(--ink2);font-style:italic;margin-left:2px}
.chip.dis{border-color:#D9534F;background:var(--dang-bg)}
/* the intro / scale panel */
#intro{position:fixed;inset:0;background:rgba(26,26,26,.45);z-index:50;display:flex;align-items:center;justify-content:center;padding:20px}
#intro[hidden]{display:none}
#intro .sheet{background:var(--card);border:1px solid var(--border);border-radius:10px;max-width:780px;width:100%;max-height:88vh;overflow:auto;padding:18px 22px 20px}
#intro h2{color:var(--accent);margin:0 0 4px;font-size:17px}
#intro h3{color:var(--accent2);font-size:13px;margin:14px 0 4px}
#intro p{margin:6px 0;font-size:12.5px;line-height:1.5}
#intro table{border-collapse:collapse;width:100%;font-size:12.5px}
#intro td{border-top:1px solid var(--border);padding:5px 6px;vertical-align:top;line-height:1.45}
#intro td.v{font-weight:800;width:38px;white-space:nowrap}
#intro td.s{color:var(--accent2);width:118px;font-weight:600}
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
/* The model report in the published report's clothes: the essay's serif, its narrow
   type rung (root 15px, body 1.2rem = 18px) and its cream paper, so the two panes read
   as one document. Every character of the markdown is still in the DOM in source order —
   the syntax markers are merely hidden — so the Python character offsets still land. */
.doc{overflow:auto;padding:14px 18px 45vh 34px;background:var(--paper);color:var(--essay-ink);flex:1;white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--essay-serif);font-size:18px;line-height:1.42}
#hframe{flex:1;width:100%;border:0;background:#fff;min-height:0}
.ln{min-height:1.42em;max-width:34em}
.ln.h1{font-size:30px;line-height:1.15;font-weight:700;margin:22px 0 4px}
.ln.h2{font-size:24.75px;line-height:1.2;font-weight:700;margin:18px 0 3px}
.ln.h3{font-size:21px;line-height:1.25;font-weight:700;margin:14px 0 2px}
.ln.code,.ln.tbl{font-family:var(--essay-mono);font-size:13px;line-height:1.45;background:var(--essay-wash);max-width:none}
.ln.quote{color:#333;border-left:3px solid var(--essay-green);background:var(--essay-wash);padding:1px 10px}
/* inline markdown: the marker characters stay in the DOM and are hidden, the text between
   them is rendered — so offsets are untouched and the reader sees prose, not asterisks */
.md-mk{display:none}
.md-bul{font-size:0}.md-bul::before{content:'•';font-size:18px;color:var(--essay-dull)}
.md-pipe{color:#B9B9AE}
.doc strong{font-weight:700}.doc em{font-style:italic}
.doc code{font-family:var(--essay-mono);font-size:.86em;background:var(--essay-dull-bg);padding:0 .3em;border-radius:2px}
.doc a{color:inherit;text-decoration:underline}
/* the paragraph body is not a click target any more: no pointer, no row highlight. Only the
   marks open a card; the gutter pencil is the way to note an unmatched paragraph. */
.ln.p{position:relative;border-left:3px solid transparent;margin-left:-12px;padding-left:9px}
.ln.p .g{position:absolute;left:-22px;top:5px;font-family:var(--sans-ui);width:14px;height:14px;padding:0;border-radius:4px;border:1px solid var(--border);background:var(--card);color:var(--mut);font-size:10px;line-height:12px;text-align:center;opacity:0;font-style:normal;cursor:pointer}
.ln.p:hover .g,.ln.p.has .g{opacity:1}.ln.p.has .g{color:var(--accent);border-color:var(--accent)}
.ln.p .g:hover{opacity:1;background:var(--soft);color:var(--accent);border-color:var(--accent)}
.ln.p.a-true{border-left-color:#34A87A}.ln.p.a-false{border-left-color:#D9534F}.ln.p.a-irr{border-left-color:#C9C6BC;color:var(--mut)}.ln.p.a-note{border-left-color:var(--accent)}
.strip{margin:6px 0 12px -12px;padding:8px 10px;background:var(--row);border:1px solid var(--border);border-radius:8px;font-family:var(--sans-ui);font-size:12px;line-height:1.45;color:var(--ink);white-space:normal;cursor:default;max-width:none}
.strip .row{margin:2px 0}.strip textarea{min-height:34px;margin-top:4px}
.strip .lab{font-weight:600;color:var(--ink2)}
.cbox{border:1px solid var(--border);border-radius:8px;padding:8px 10px;margin-bottom:8px;background:var(--card)}
.cbox.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--soft)}
.qs{border-top:1px dashed var(--border);padding-top:6px}
#claimcard{position:absolute;left:0;right:0;bottom:0;max-height:58%;overflow:auto;background:var(--card);border-top:2px solid var(--accent);box-shadow:0 -6px 16px rgba(0,0,0,.10);padding:8px 12px 12px;z-index:5}
#claimcard .hdr{display:flex;gap:8px;align-items:center;font-size:11px;color:var(--mut);margin-bottom:2px}
#claimcard .hdr .x{margin-left:auto;cursor:pointer;font-weight:700;color:var(--ink2);border:1px solid var(--border);border-radius:6px;padding:0 6px;background:var(--card)}
#mnotes{padding:8px 12px;border-bottom:1px solid var(--border);background:var(--soft);max-height:34vh;overflow:auto}
#mnotes label,.ncard label{font-size:11px;color:var(--accent2);display:block;margin:6px 0 2px;font-weight:600}
mark{background:transparent;border-radius:3px;padding:0 1px;cursor:pointer;color:inherit;box-shadow:0 1px 0 rgba(193,95,60,.28)}
mark:hover{box-shadow:0 1px 0 var(--accent),0 0 0 2px var(--soft)}
mark.s1{background:#D1FAE5}mark.s05{background:#FEF3C7}mark.s0{background:#FEE2E2}
mark.sel{outline:2px solid var(--accent);background:#FBE3D6}
.hint{font-size:10.5px;color:var(--mut);padding:0 8px 6px}
.hint b{font-weight:600;color:var(--ink2)}
kbd{background:var(--soft);border:1px solid var(--border);border-radius:4px;padding:0 4px;font-size:10px;font-family:inherit}
#cards{overflow:auto;padding:10px 14px;display:flex;flex-direction:column;gap:10px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 14px;display:grid;grid-template-columns:1.25fr 1fr;gap:14px}
.card .hd{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:600}
.card .hd .b{font-size:11px;color:var(--mut);font-weight:400}
.link{color:var(--accent);cursor:pointer;font-size:11.5px;font-weight:600;text-decoration:none}
.link:hover{text-decoration:underline}
#claimhead{padding:10px 14px;border-bottom:1px solid var(--border);background:var(--card)}
#claimhead .hq{font-style:italic;color:var(--ink2);border-left:3px solid var(--soft);padding-left:8px;margin:4px 0}
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
  <button class="tab" id="sb-btn" title="hide / show the report list  ([)">&#9776;</button>
  <div><h1>Judge audit</h1><div class="sub" id="built"></div></div>
  <div class="tabs"><button class="tab active" data-view="report">By report</button><button class="tab" data-view="claim">By claim</button><button class="tab" data-view="notes">Notes</button></div>
  <div class="tabs"><button class="tab" id="who-btn" title="who is auditing — click to change the name your judgements are filed under">auditor?</button><button class="tab" id="guide-btn" title="the task and the six scale anchors">the scale</button></div>
  <div class="stats" id="stats"></div>
  <div id="save">loading&hellip;</div>
</header>
<div id="layout">
  <aside>
    <input class="search" id="q" placeholder="Search reports / claims&hellip;">
    <div class="filt" id="f-round"><span class="lab">round</span></div>
    <div class="filt" id="f-budget"><span class="lab">budget</span></div>
    <div class="filt" id="f-agent"><span class="lab">harness</span></div>
    <div class="filt" id="f-status"><span class="lab">show</span></div>
    <div id="list"></div>
    <div class="hint"><b>Reports: best judge score first.</b> <kbd>j</kbd>/<kbd>k</kbd> claim &middot; <kbd>n</kbd>/<kbd>p</kbd> report &middot; <kbd>1</kbd>&ndash;<kbd>4</kbd> verdict &middot; <kbd>c</kbd> comment &middot; <kbd>e</kbd> report notes &middot; <kbd>[</kbd> hide this list &middot; <kbd>Esc</kbd> leave box &middot; click a highlight to score it, the &#9998; in the margin to note a paragraph</div>
  </aside>
  <main id="main">
    <div id="rail"></div>
    <div id="claimline"></div>
    <div id="panes">
      <div class="pane" id="mpane">
        <h3>Model report <span id="mr-title"></span><button class="vb grey" id="mnotes-btn">notes</button></h3>
        <div class="remind">For each paragraph: if it matches nothing in the human report, is it true or false? &middot; if it matches, do I agree with the judge's rating? &mdash; hypotheses and biases go in the report notes.</div>
        <div id="mnotes" hidden></div>
        <div class="doc" id="mdoc"></div>
        <div id="claimcard" hidden></div>
      </div>
      <div class="pane">
        <h3>Human report <span id="hr-note"></span></h3>
        <iframe id="hframe" title="the published human report"></iframe>
      </div>
    </div>
    <div id="claimhead" hidden></div>
    <div id="cards" hidden></div>
    <div id="notes" hidden></div>
  </main>
</div>
<div id="intro" hidden><div class="sheet">
  <h2>Auditing the recall judge</h2>
  <div id="intro-task"></div>
  <div class="whoerr" id="who-err" hidden>Type a name first — it is what keeps your judgements separate from your partner's.</div>
  <label class="whoin">Your name <input id="who-in" placeholder="first name" autocomplete="off" spellcheck="false"></label>
  <h3>One scale, 0 to 1, to one decimal place</h3>
  <p class="fine">How much of the human point does the model report actually deliver? Same scale on all six rubric sheets, read from the rubric source at build time.</p>
  <table><tbody id="scaletab"></tbody></table>
  <p class="fine">Those six are the defined anchors. 0.1, 0.2, 0.4, 0.6 and 0.8 are there for a claim that sits between two of them &mdash; the buttons show the anchors raised, the in-between values plain.</p>
  <button class="vb plain" id="intro-ok">Start auditing</button>
</div></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const AUDIT_PATH = D.audit_path, LS_KEY = 'judge_audit:' + AUDIT_PATH, SB_KEY = 'judge_audit:sidebar';
const WHO_KEY = 'judge_audit:auditor', INTRO_KEY = 'judge_audit:intro_seen';
/* The behavioural scale, straight out of the rubric source. Eleven values are offered;
   the six in SCALE are the defined anchors, the rest are interpolation between them. */
const SCALE = D.scale, SCALE_BY = Object.fromEntries(SCALE.map(a => [a.key, a]));
const SCALE_VALS = []; for (let i = 10; i >= 0; i--) SCALE_VALS.push(i / 10);
const DISAGREE = 0.2;                                /* a gap larger than this is flagged */
const CLAIMS = D.claims, CIDS = CLAIMS.map(c => c.id), CBY = Object.fromEntries(CLAIMS.map(c => [c.id, c]));
const REPORTS = D.reports, RBY = Object.fromEntries(REPORTS.map(r => [r.key, r]));
/* Report bodies and judge quotes load per report; the page itself carries only scores. */
const PEND = {};
function fileURL(p) { return '/file?p=' + encodeURIComponent(p); }
function loaded(rk) { return RBY[rk].text != null; }
function details(rk) {
  if (loaded(rk)) return Promise.resolve(RBY[rk]);
  if (!PEND[rk]) PEND[rk] = fetch(fileURL(D.data_dir + '/' + rk + '.json'))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(d => { const rep = RBY[rk]; for (const [cid, s] of Object.entries(d.scores)) Object.assign(rep.scores[cid], s); rep.text = d.text; return rep; })
    .catch(e => { delete PEND[rk]; throw e; });
  return PEND[rk];
}
document.getElementById('built').textContent = REPORTS.length + ' reports · ' + CLAIMS.length + ' claims · judge ' + (REPORTS[0] && REPORTS[0].grader) + ' · built ' + D.built;

/* "Correct (TP)" is gone from the buttons: agreeing with the judge is already said by the
   score matching. Entries saved as tp before that change still load, display and count —
   CAT keeps the label, and auditControls shows an existing tp as a static, clearable tag. */
const VERDICTS = {
  pos: [{v:'adjust', l:'Right find, wrong score', c:'warn'}, {v:'fp', l:'Not supported (FP)', c:'dang'}, {v:'todo', l:'Needs investigation', c:'grey'}],
  neg: [{v:'tn_easy', l:'Contradicted by report (TN easy)', c:'ok'}, {v:'tn_hard', l:'Absent, checked (TN hard)', c:'ok'}, {v:'fn', l:'Actually present (FN)', c:'dang'}, {v:'todo', l:'Needs investigation', c:'grey'}],
};
const CAT = {tp:['TP','ok'], adjust:['TP·adj','warn'], fp:['FP','dang'], tn_easy:['TN easy','ok'], tn_hard:['TN hard','ok'], fn:['FN','dang'], todo:['Flagged','grey']};
const MATCHLAB = {exact: 'quote found verbatim', norm: 'quote found (punctuation normalised)', anchor: 'validated anchor span', none: 'quote NOT found in this report'};
const GLOBAL = '_global';

/* Two auditors, one file. Everything is filed under the auditor's name; version-2 files
   kept their maps at the top level, and those are adopted by the first auditor to name
   themselves (recorded as legacy_owner, so the other browser agrees). */
let state = {version: 3, updated_at: null, legacy_owner: null, auditors: {}};
let ME = '';
let view = 'report', selReport = null, selClaim = CIDS[0], selClaimView = CIDS[0], cardForced = false;
const filters = {round: new Set(['r3']), budget: new Set(), agent: new Set(), status: new Set(), q: ''};
const openParas = new Set();

/* ---------- persistence ---------- */
const MAPS = ['entries', 'paragraphs', 'notes'];
function fresh() { return {entries: {}, paragraphs: {}, notes: {}}; }
function bkt(st, who) { return (st.auditors && st.auditors[who]) || null; }         /* read-only */
function mkBkt(st, who) { const a = bkt(st, who) || (st.auditors[who] = fresh()); for (const m of MAPS) a[m] = a[m] || {}; return a; }
function myMap(map) { const b = bkt(state, ME); return (b && b[map]) || {}; }
function auditors() { return Object.keys(state.auditors).sort(); }
function ekey(rk, cid) { return rk + '/' + cid; }
function entry(rk, cid) { return myMap('entries')[ekey(rk, cid)] || null; }
function entryOf(who, rk, cid) { const b = bkt(state, who); return (b && b.entries[ekey(rk, cid)]) || null; }
function blank(e) { return !e.verdict && !e.comment && !e.rubric_issue && e.corrected == null && !e.relevant && !e.truth && !e.rating && !e.note && !e.hypotheses && !e.biases; }
function setIn(map, k, patch) {
  if (!ME) { openIntro(); return; }                  /* nothing is written unnamed */
  const b = mkBkt(state, ME);
  const e = Object.assign({}, b[map][k] || {}, patch, {updated_at: new Date().toISOString()});
  for (const key of Object.keys(e)) if (e[key] === null || e[key] === '' || e[key] === false) delete e[key];
  if (blank(e)) delete b[map][k]; else b[map][k] = e;
  scheduleSave();
}
function setEntry(rk, cid, patch) { setIn('entries', ekey(rk, cid), patch); }
function pkey(rk, li) { return rk + '/p' + li; }
function para(rk, li) { return myMap('paragraphs')[pkey(rk, li)] || null; }
function setPara(rk, li, patch) { setIn('paragraphs', pkey(rk, li), Object.assign({anchor: RBY[rk].text.split('\n')[li].slice(0, 100)}, patch)); }
function note(rk) { return myMap('notes')[rk] || null; }
/* every auditor's own score for one claim, and the spread between them */
function allCorrected(rk, cid) {
  const out = [];
  for (const w of auditors()) { const e = entryOf(w, rk, cid); if (e && e.corrected != null) out.push([w, e.corrected]); }
  return out;
}
function round1(x) { return Math.round(x * 10) / 10; }
function disagreement(rk, cid) {
  const v = allCorrected(rk, cid).map(x => x[1]);
  if (v.length < 2) return 0;
  const d = round1(Math.max.apply(null, v) - Math.min.apply(null, v));
  return d > DISAGREE ? d : 0;
}
function setNote(rk, patch) { setIn('notes', rk, patch); }
let saveTimer = null;
function setStatus(t, err) { const el = document.getElementById('save'); el.textContent = t; el.className = err ? 'err' : ''; }
function scheduleSave() { clearTimeout(saveTimer); setStatus('unsaved…'); saveTimer = setTimeout(saveNow, 500); }
/* On disk: auditors keyed by name, plus any still-unadopted version-2 maps, left where
   they were so an older reader still finds them. */
function serialize() {
  const o = {version: 3, updated_at: state.updated_at, legacy_owner: state.legacy_owner || null, auditors: state.auditors};
  if (state._legacy) Object.assign(o, state._legacy);
  return JSON.stringify(o, null, 1);
}
async function saveNow() {
  state.updated_at = new Date().toISOString();
  const body = serialize();
  try { localStorage.setItem(LS_KEY, body); } catch (e) {}
  try {
    const r = await fetch('/save?p=' + encodeURIComponent(AUDIT_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    setStatus('saved to disk ' + new Date().toLocaleTimeString());
  } catch (e) { setStatus('NOT on disk (browser copy kept): ' + e.message, true); }
}
function mergeInto(dst, src) {
  for (const map of MAPS) for (const [k, e] of Object.entries((src && src[map]) || {})) {
    const cur = dst[map][k]; if (!cur || (e.updated_at || '') > (cur.updated_at || '')) dst[map][k] = e;
  }
}
function merge(a, b) {
  const out = {version: 3, updated_at: null, legacy_owner: null, auditors: {}};
  const leg = fresh(); let anyLeg = false;
  for (const src of [a, b]) {
    if (!src) continue;
    out.legacy_owner = out.legacy_owner || src.legacy_owner || null;
    for (const w of Object.keys(src.auditors || {})) mergeInto(mkBkt(out, w), src.auditors[w]);
    if (MAPS.some(m => Object.keys(src[m] || {}).length)) { mergeInto(leg, src); anyLeg = true; }
  }
  if (anyLeg) out._legacy = leg;
  return out;
}
/* Unnamespaced version-2 entries go to whoever names themselves first; the choice is then
   written into the file as legacy_owner, so the second auditor sees the same attribution. */
function adoptLegacy() {
  if (!ME || !state._legacy) return;
  const owner = state.legacy_owner || ME;
  state.legacy_owner = owner;
  mergeInto(mkBkt(state, owner), state._legacy);
  delete state._legacy;
  scheduleSave();
}
function countAll(st) { let n = 0; for (const w of Object.keys(st.auditors || {})) for (const m of MAPS) n += Object.keys(st.auditors[w][m] || {}).length; for (const m of MAPS) n += Object.keys((st._legacy || {})[m] || {}).length; return n; }
function sameContent(a, b) { const f = x => JSON.stringify([x.auditors || {}, x._legacy || null]); return f(a) === f(b); }
async function load() {
  let server = null, local = null;
  try { const r = await fetch(fileURL(AUDIT_PATH)); if (r.ok) server = await r.json(); } catch (e) {}
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = merge(server, local);
  const n = countAll(state);
  if (server === null && local === null) setStatus('no saved audits yet');
  else if (local && !sameContent(state, server || {})) scheduleSave();
  else setStatus('loaded ' + n + ' saved items (' + (server ? 'from disk' : 'browser copy only') + ')', !server);
}

/* ---------- helpers ---------- */
function scoreClass(s) { return s == null ? 's0' : s >= 0.75 ? 's1' : s > 0 ? 's05' : 's0'; }
function isPos(s) { return s != null && s > 0; }
function category(rk, cid) { const e = entry(rk, cid); return e && e.verdict ? e.verdict : null; }
/* A claim counts as audited once it carries a score or a verdict. Agreeing with the judge
   is expressed by the score alone now that the "Correct" button is gone, so keying the
   counters off the verdict would leave every agreement looking unreviewed. */
function audited(rk, cid) {
  const e = entry(rk, cid);
  return !!e && (e.corrected != null || (e.verdict && e.verdict !== 'todo'));
}
function filteredReports() {
  const q = filters.q.toLowerCase();
  return REPORTS.filter(r => (!filters.round.size || filters.round.has(r.round)) && (!filters.budget.size || filters.budget.has(String(r.budget)))
    && (!filters.agent.size || filters.agent.has(r.agent)) && (!q || (r.title + ' ' + r.file + ' ' + r.budget).toLowerCase().includes(q)))
    /* best judge score first, so the strongest runs are audited first */
    .sort((a, b) => (b.accuracy == null ? -1 : b.accuracy) - (a.accuracy == null ? -1 : a.accuracy)
                    || a.title.localeCompare(b.title) || a.budget - b.budget || (a.rep || 0) - (b.rep || 0));
}
function statusOk(rk, cid) {
  if (!filters.status.size) return true;
  const e = entry(rk, cid), s = RBY[rk].scores[cid].score;
  for (const f of filters.status) {
    if (f === 'pos' && isPos(s)) return true; if (f === 'neg' && !isPos(s)) return true;
    if (f === 'unreviewed' && !audited(rk, cid)) return true; if (f === 'reviewed' && audited(rk, cid)) return true;
    if (f === 'flagged' && e && (e.verdict === 'todo' || e.rubric_issue)) return true;
    if (f === 'disagree' && disagreement(rk, cid)) return true;
  }
  return false;
}
function paraCount(rk) { let n = 0; for (const k of Object.keys(myMap('paragraphs'))) if (k.startsWith(rk + '/p')) n++; return n; }
function hasNotes(rk) { const nt = note(rk); return !!(nt && (nt.hypotheses || nt.biases)); }
function el(tag, cls, text) { const x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; }
function fmtScore(s) { return s == null ? '–' : Number(s).toFixed(1); }
function chipBtn(parent, on, label, fn, cls) { const b = el('button', 'vb ' + (cls || 'grey') + (on ? ' on' : '')); b.textContent = label; b.onclick = ev => { ev.stopPropagation(); fn(); }; parent.appendChild(b); return b; }

/* ---------- header ---------- */
function renderStats() {
  const reps = filteredReports(); const counts = {}; let pos = 0, reviewed = 0, total = 0, paras = 0, noted = 0, dis = 0;
  for (const r of reps) { paras += paraCount(r.key); if (hasNotes(r.key)) noted++;
    for (const cid of CIDS) { total++; if (isPos(r.scores[cid].score)) pos++; if (disagreement(r.key, cid)) dis++;
      if (audited(r.key, cid)) reviewed++;
      const v = category(r.key, cid); if (v) counts[v] = (counts[v] || 0) + 1; } }
  const box = document.getElementById('stats'); box.replaceChildren();
  box.appendChild(el('span', 'badge grey', reps.length + ' reports'));
  box.appendChild(el('span', 'badge grey', pos + ' judge-positive · ' + (total - pos) + ' negative'));
  box.appendChild(el('span', 'badge', reviewed + '/' + total + ' audited'));
  for (const [v, [lab, c]] of Object.entries(CAT)) if (counts[v]) box.appendChild(el('span', 'badge ' + c, lab + ' ' + counts[v]));
  if (dis) box.appendChild(el('span', 'badge dang', dis + ' auditors differ >' + fmtScore(DISAGREE)));
  if (paras || noted) box.appendChild(el('span', 'badge', paras + ' ¶ noted · ' + noted + ' reports with notes'));
}

/* ---------- who is auditing, and the intro panel that teaches the scale ----------
   The scale is long-winded to state and short to apply, so it is stated once here and
   reduced to a two-word handle under each anchor button at the point of scoring. */
function renderWho() {
  const b = document.getElementById('who-btn');
  b.textContent = ME ? 'auditor: ' + ME : 'who are you?';
  b.classList.toggle('active', !!ME);
  b.title = ME ? 'auditing as ' + ME + ' — click to change' : 'click to say who you are';
}
function setMe(n) {
  ME = n;
  try { localStorage.setItem(WHO_KEY, n); } catch (e) {}
  adoptLegacy(); renderWho(); renderAll();
}
function buildIntro() {
  const task = document.getElementById('intro-task'); task.replaceChildren();
  for (const t of (D.intro || [])) task.appendChild(el('p', '', t));
  const tab = document.getElementById('scaletab'); tab.replaceChildren();
  for (const a of SCALE) {
    const tr = el('tr');
    tr.appendChild(el('td', 'v', a.key)); tr.appendChild(el('td', 's', a.short)); tr.appendChild(el('td', '', a.full));
    tab.appendChild(tr);
  }
}
function openIntro() {
  const o = document.getElementById('intro'); o.hidden = false;
  document.getElementById('who-err').hidden = true;
  const inp = document.getElementById('who-in'); inp.value = ME;
  setTimeout(() => { inp.focus(); inp.select(); }, 0);
}
function closeIntro() {
  const inp = document.getElementById('who-in'), n = inp.value.trim().slice(0, 40);
  if (!n) { document.getElementById('who-err').hidden = false; inp.focus(); return; }
  document.getElementById('intro').hidden = true;
  try { localStorage.setItem(INTRO_KEY, '1'); } catch (e) {}
  if (n !== ME) setMe(n); else renderWho();
}
try { ME = localStorage.getItem(WHO_KEY) || ''; } catch (e) { ME = ''; }
buildIntro(); renderWho();
document.getElementById('who-btn').onclick = openIntro;
document.getElementById('guide-btn').onclick = openIntro;
document.getElementById('intro-ok').onclick = closeIntro;
document.getElementById('who-in').onkeydown = ev => { ev.stopPropagation(); if (ev.key === 'Enter') { ev.preventDefault(); closeIntro(); } };

/* ---------- collapsible sidebar ---------- */
let sbHidden = false;
try { sbHidden = localStorage.getItem(SB_KEY) === '1'; } catch (e) {}
function applySidebar() {
  document.getElementById('layout').classList.toggle('collapsed', sbHidden);
  const b = document.getElementById('sb-btn'); b.classList.toggle('active', !sbHidden);
  b.title = (sbHidden ? 'show' : 'hide') + ' the report list  ([)';
}
function toggleSidebar() { sbHidden = !sbHidden; try { localStorage.setItem(SB_KEY, sbHidden ? '1' : '0'); } catch (e) {} applySidebar(); }
document.getElementById('sb-btn').onclick = toggleSidebar;
applySidebar();

/* ---------- sidebar list ---------- */
function chipRow(id, values, set, labels) {
  const box = document.getElementById(id); box.querySelectorAll('button').forEach(b => b.remove());
  for (const v of values) { const b = el('button', set.has(v) ? 'on' : '', (labels && labels[v]) || v); b.onclick = () => { set.has(v) ? set.delete(v) : set.add(v); renderAll(); }; box.appendChild(b); }
}
function renderFilters() {
  chipRow('f-round', [...new Set(REPORTS.map(r => r.round))].sort(), filters.round, {r2: 'round 2', r3: 'round 3'});
  const budgets = [...new Set(REPORTS.map(r => String(r.budget)))].sort((a, b) => a - b);
  chipRow('f-budget', budgets, filters.budget, Object.fromEntries(budgets.map(b => [b, b + ' min'])));
  chipRow('f-agent', [...new Set(REPORTS.map(r => r.agent))].sort(), filters.agent);
  chipRow('f-status', ['pos', 'neg', 'unreviewed', 'reviewed', 'flagged', 'disagree'], filters.status, {pos: 'judge +', neg: 'judge 0', unreviewed: 'unreviewed', reviewed: 'reviewed', flagged: 'flagged', disagree: 'auditors differ'});
}
function reportItem(r) {
  const it = el('div', 'item' + (r.key === selReport ? ' sel' : '')); it.dataset.key = r.key;
  const nm = el('div', 'nm'); nm.appendChild(el('span', '', r.title + ' · rep' + r.rep)); nm.appendChild(el('span', 'sc ' + scoreClass(r.accuracy), r.accuracy == null ? '–' : r.accuracy.toFixed(2))); it.appendChild(nm);
  const done = CIDS.filter(c => audited(r.key, c)).length;
  const flagged = CIDS.filter(c => { const e = entry(r.key, c); return e && (e.verdict === 'todo' || e.rubric_issue); }).length;
  const pc = paraCount(r.key);
  const dis = CIDS.filter(c => disagreement(r.key, c)).length;
  const meta = el('div', 'meta'); meta.appendChild(el('span', '', r.budget + ' min')); meta.appendChild(el('span', '', r.round));
  meta.appendChild(el('span', '', done + '/' + CIDS.length + ' audited' + (flagged ? ' · ' + flagged + ' flagged' : '') + (dis ? ' · ' + dis + ' ≠' : '') + (pc ? ' · ' + pc + ' ¶' : '') + (hasNotes(r.key) ? ' · notes' : '')));
  it.appendChild(meta);
  const pg = el('div', 'prog'); const i = el('i'); i.style.width = (100 * done / CIDS.length) + '%'; pg.appendChild(i); it.appendChild(pg);
  it.onclick = () => { selReport = r.key; openParas.clear(); cardForced = false; renderMain(); renderList(); };
  return it;
}
function renderList() {
  const list = document.getElementById('list'); list.replaceChildren();
  if (view === 'report' || view === 'notes') {
    const reps = filteredReports();
    if (!selReport || !reps.some(r => r.key === selReport)) selReport = reps.length ? reps[0].key : null;
    for (const r of reps) list.appendChild(reportItem(r));
    if (!reps.length) list.appendChild(el('div', 'empty', 'no reports match the filters'));
  } else {
    const reps = filteredReports(); const q = filters.q.toLowerCase();
    for (const c of CLAIMS) {
      if (q && !(c.id + ' ' + c.section + ' ' + c.claim).toLowerCase().includes(q)) continue;
      let pos = 0, done = 0, flagged = 0;
      for (const r of reps) { if (isPos(r.scores[c.id].score)) pos++; const e = entry(r.key, c.id); if (audited(r.key, c.id)) done++; if (e && (e.verdict === 'todo' || e.rubric_issue)) flagged++; }
      const it = el('div', 'item' + (c.id === selClaimView ? ' sel' : ''));
      const nm = el('div', 'nm'); nm.appendChild(el('span', '', c.id + ' · ' + c.section)); it.appendChild(nm);
      it.appendChild(el('div', '', c.claim.length > 110 ? c.claim.slice(0, 110) + '…' : c.claim));
      const meta = el('div', 'meta'); meta.appendChild(el('span', '', pos + '/' + reps.length + ' judge-positive')); meta.appendChild(el('span', '', done + ' audited' + (flagged ? ' · ' + flagged + ' flagged' : ''))); it.appendChild(meta);
      const pg = el('div', 'prog'); const i = el('i'); i.style.width = (reps.length ? 100 * done / reps.length : 0) + '%'; pg.appendChild(i); it.appendChild(pg);
      it.onclick = () => { selClaimView = c.id; renderMain(); renderList(); };
      list.appendChild(it);
    }
  }
}

/* ---------- audit controls (shared by the inline card, the floating card and the claim view) ---------- */
function auditControls(rk, cid, opts) {
  const r = RBY[rk], s = r.scores[cid], e = entry(rk, cid) || {}; const pos = isPos(s.score);
  const box = el('div');
  const verd = el('div', 'verd');
  const vopts = VERDICTS[pos ? 'pos' : 'neg'];
  vopts.forEach((o, i) => {
    const b = el('button', 'vb ' + o.c + (e.verdict === o.v ? ' on' : '')); const k = el('span', 'k', String(i + 1)); b.appendChild(k); b.appendChild(document.createTextNode(o.l));
    b.onclick = ev => { ev.stopPropagation(); setEntry(rk, cid, {verdict: e.verdict === o.v ? null : o.v}); refresh(rk, cid); }; verd.appendChild(b);
  });
  /* a verdict that is on the entry but no longer offered (a tp saved earlier): shown as it
     is, with an ✕ to clear it, so old judgements stay readable without being re-settable. */
  if (e.verdict && !vopts.some(o => o.v === e.verdict)) {
    const tag = el('span', 'vkept'); tag.appendChild(document.createTextNode(CAT[e.verdict] ? CAT[e.verdict][0] : e.verdict));
    const x = el('button', 'x', '✕'); x.title = 'clear this verdict';
    x.onclick = ev => { ev.stopPropagation(); setEntry(rk, cid, {verdict: null}); refresh(rk, cid); };
    tag.appendChild(x); verd.appendChild(tag);
  }
  box.appendChild(verd);
  const row = el('div', 'row'); row.appendChild(el('span', '', 'Your score:'));
  const num = el('input'); num.className = 'scnum'; num.type = 'text'; num.inputMode = 'decimal';
  num.placeholder = '0.0–1.0'; num.title = 'type a score and press Enter';
  num.value = e.corrected == null ? '' : fmtScore(e.corrected);
  const commit = () => {
    const t = num.value.trim();
    if (t === '') { setEntry(rk, cid, {corrected: null}); refresh(rk, cid); return; }
    const x = parseFloat(t); if (isNaN(x)) { num.value = e.corrected == null ? '' : fmtScore(e.corrected); return; }
    setEntry(rk, cid, {corrected: Math.min(1, Math.max(0, round1(x)))}); refresh(rk, cid);
  };
  num.onkeydown = ev => { ev.stopPropagation(); if (ev.key === 'Enter') { ev.preventDefault(); commit(); } };
  num.onchange = commit; row.appendChild(num);
  row.appendChild(el('span', 'cat', '(judge gave ' + fmtScore(s.score) + ')'));
  chipBtn(row, !!e.rubric_issue, (e.rubric_issue ? '⚑ ' : '') + 'rubric / claim needs fixing', () => { setEntry(rk, cid, {rubric_issue: !e.rubric_issue}); refresh(rk, cid); }, 'warn');
  const g = el('a', 'link', 'the scale →'); g.onclick = ev => { ev.stopPropagation(); openIntro(); }; row.appendChild(g);
  box.appendChild(row);
  box.appendChild(scaleRow(rk, cid, e));
  const oth = othersRow(rk, cid, e); if (oth) box.appendChild(oth);
  const ta = el('textarea'); ta.className = 'cmt'; ta.dataset.cid = cid;
  ta.placeholder = 'Comment — why, what the report actually says, what the rubric should say…'; ta.value = e.comment || '';
  ta.oninput = () => setEntry(rk, cid, {comment: ta.value}); box.appendChild(ta);
  const foot = el('div', 'cat'); const v = e.verdict ? CAT[e.verdict] : null;
  foot.textContent = (v ? 'Category: ' + v[0] : (e.corrected != null ? 'Scored' : 'Not audited yet')) + (e.updated_at ? ' · ' + new Date(e.updated_at).toLocaleString() : '');
  if (opts && opts.jump) { foot.appendChild(document.createTextNode('  ')); const a = el('a', 'link', 'open in report view →'); a.onclick = () => switchView('report', () => { selReport = rk; selClaim = cid; openParas.clear(); cardForced = false; }); foot.appendChild(a); }
  box.appendChild(foot);
  return box;
}
/* Eleven values, 0.0 to 1.0. The six rubric anchors carry their two-word handle and the
   full sentence on hover; the five in between say which anchors they sit between. */
function tweenTitle(v) {
  const below = SCALE.filter(a => a.v < v), above = SCALE.filter(a => a.v > v);
  const lo = below.length ? below[0] : null, hi = above.length ? above[above.length - 1] : null;
  return fmtScore(v) + ' — between ' + (lo ? fmtScore(lo.v) + ' (' + lo.short + ')' : '?')
       + ' and ' + (hi ? fmtScore(hi.v) + ' (' + hi.short + ')' : '?');
}
function scaleRow(rk, cid, e) {
  const wrap = el('div', 'scale');
  for (const v of SCALE_VALS) {
    const key = fmtScore(v), a = SCALE_BY[key];
    const b = el('button', 'sb' + (a ? ' anch' : '') + (e.corrected === v ? ' on' : ''));
    b.appendChild(el('span', 'n', key));
    b.appendChild(el('span', 'sl', a ? a.short : ''));
    b.title = a ? key + ' — ' + a.full : tweenTitle(v);
    b.onclick = ev => { ev.stopPropagation(); setEntry(rk, cid, {corrected: e.corrected === v ? null : v}); refresh(rk, cid); };
    wrap.appendChild(b);
  }
  return wrap;
}
function othersRow(rk, cid, e) {
  const rows = [];
  for (const w of auditors()) {
    if (w === ME) continue;
    const o = entryOf(w, rk, cid);
    if (!o || (o.corrected == null && !o.verdict && !o.comment)) continue;
    rows.push([w, o]);
  }
  if (!rows.length) return null;
  const box = el('div', 'other');
  for (const [w, o] of rows) {
    const line = el('div', 'oline');
    line.appendChild(el('span', 'who', w + ' said'));
    if (o.corrected != null) line.appendChild(el('span', 'sc ' + scoreClass(o.corrected), fmtScore(o.corrected)));
    if (o.verdict) line.appendChild(el('span', 'cat', CAT[o.verdict][0]));
    if (o.rubric_issue) line.appendChild(el('span', 'cat', '⚑ rubric'));
    const d = (e.corrected != null && o.corrected != null) ? round1(Math.abs(e.corrected - o.corrected)) : 0;
    if (d > DISAGREE) line.appendChild(el('span', 'badge dang', 'you disagree by ' + fmtScore(d)));
    if (o.comment) line.appendChild(el('div', 'ocmt', '“' + o.comment + '”'));
    box.appendChild(line);
  }
  return box;
}
function refresh(rk, cid) {
  if (view === 'report') { renderRail(); renderClaimLine(); for (const li of [...openParas]) updateParaLine(rk, li); renderClaimCard(); }
  else if (view === 'claim') { const c = document.querySelector('.card[data-key="' + rk + '"]'); if (c) c.replaceWith(cardFor(rk, cid)); }
  renderStats(); renderList();
}

/* ---------- claim info (shared) ---------- */
function claimHead(cid, withQuote) {
  const c = CBY[cid]; const box = el('div');
  const id = el('div', 'cl-id'); id.appendChild(el('span', 'badge', c.id)); id.appendChild(el('span', '', c.section + ' · L' + c.level + ' · ' + c.rubric));
  if (c.gt_verdict) id.appendChild(el('span', 'badge grey', 'ground truth: ' + c.gt_verdict));
  const a = el('a', 'link', 'show in the human report →'); a.onclick = ev => { ev.stopPropagation(); selectClaim(cid); }; id.appendChild(a);
  box.appendChild(id);
  box.appendChild(el('div', 'cl-text', c.claim));
  if (withQuote && c.report_quote) box.appendChild(el('div', 'hq', '“' + c.report_quote + '”'));
  /* the feasibility notes, corrections and trap are deliberately not shown: the panel asks
     for a score and a comment, and nothing else competes for the eye. */
  return box;
}
function judgeBox(rk, cid) {
  const s = RBY[rk].scores[cid]; const j = el('div', 'judge');
  if (!loaded(rk)) { j.appendChild(el('span', 'sc ' + scoreClass(s.score), 'judge score ' + fmtScore(s.score))); j.appendChild(el('div', 'r', 'loading the judge quote…')); return j; }
  const hd = el('div'); hd.appendChild(el('span', 'sc ' + scoreClass(s.score), 'judge score ' + fmtScore(s.score)));
  hd.appendChild(el('span', 'cat', '  ' + (MATCHLAB[s.match] || s.match))); j.appendChild(hd);
  if (s.quote) j.appendChild(el('div', 'q', '“' + s.quote + '”'));
  j.appendChild(el('div', 'r', s.reason || '')); return j;
}

/* ---------- the human report: the published page in an iframe ---------- */
const HF = {ready: false, marks: {}, err: null};
function initHuman() {
  const f = document.getElementById('hframe');
  f.onload = () => { try { indexHuman(f.contentDocument); } catch (e) { HF.err = e.message; setHrNote('could not read the published report: ' + e.message); } };
  f.onerror = () => { HF.err = 'load failed'; setHrNote('could not load the published report'); };
  f.src = fileURL(D.human_html);
}
/* Walk the iframe's text nodes once, building the same whitespace-collapsed string the
   anchors were validated against, plus a per-character (node, offset) map. */
/* The anchors were validated against the report's text with margin notes and the
   show-more labels left out — their words sit inside a sentence in textContent and
   splice a footnote into the middle of a claim. Skip the same elements here or a
   validated span is not findable in the page. */
const SKIP = new Set(D.skip_classes || []);
function skipped(node) {
  for (let e = node.parentElement; e; e = e.parentElement) {
    const cl = e.classList; if (!cl) continue;
    for (const c of SKIP) if (cl.contains(c)) return true;
  }
  return false;
}
function indexHuman(doc) {
  const w = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, null);
  const nodes = [], offs = []; const buf = []; let prev = true, n;
  while ((n = w.nextNode())) {
    if (skipped(n)) continue;
    const t = n.nodeValue;
    for (let i = 0; i < t.length; i++) {
      const ch = t[i];
      if (/\s/.test(ch)) { if (prev) continue; buf.push(' '); nodes.push(n); offs.push(i); prev = true; }
      else { buf.push(ch); nodes.push(n); offs.push(i); prev = false; }
    }
  }
  HF.doc = doc; HF.text = buf.join(''); HF.nodes = nodes; HF.offs = offs;
  markHuman();
  HF.ready = true;
  if (HF.pending) { selClaim = HF.pending; HF.pending = null; }
  highlightHuman();
}
function collectSegs(a, b, cid, map) {
  let k = a;
  while (k < b) {
    const node = HF.nodes[k]; let j = k;
    while (j + 1 < b && HF.nodes[j + 1] === node) j++;
    if (!map.has(node)) map.set(node, []);
    map.get(node).push({a: HF.offs[k], b: HF.offs[j] + 1, cid});
    k = j + 1;
  }
}
function markHuman() {
  const map = new Map();
  for (const c of CLAIMS) for (const sp of (c.human_spans || [])) {
    const q = sp.replace(/\s+/g, ' ').trim(); if (q.length < 8) continue;
    const i = HF.text.indexOf(q); if (i < 0) continue;
    collectSegs(i, i + q.length, c.id, map);
  }
  HF.marks = {};
  for (const [node, segs] of map) {
    segs.sort((x, y) => y.a - x.a);
    let last = Infinity;
    for (const sg of segs) {
      if (!node.parentNode || sg.b > last || sg.a >= sg.b || sg.b > node.nodeValue.length) continue;
      node.splitText(sg.b);
      const mid = node.splitText(sg.a);
      const m = HF.doc.createElement('mark');
      m.setAttribute('data-audit', sg.cid);
      m.title = sg.cid + ' · ' + CBY[sg.cid].claim;
      m.onclick = () => selectClaim(sg.cid);
      mid.parentNode.replaceChild(m, mid); m.appendChild(mid);
      (HF.marks[sg.cid] = HF.marks[sg.cid] || []).push(m);
      last = sg.a;
    }
  }
}
function anchorNote(cid) {
  const c = CBY[cid];
  if (HF.err) return 'human report unavailable (' + HF.err + ')';
  if (!HF.ready) return 'loading the published report…';
  const n = (HF.marks[cid] || []).length;
  if (!n) return 'no anchor for ' + cid + ' — nothing from the rubric occurs verbatim in the page';
  return n + ' anchored passage' + (n > 1 ? 's' : '') + (c.anchor_source === 'anchors' ? '' : ' (from the rubric quote)');
}
function setHrNote(msg) { document.getElementById('hr-note').textContent = msg != null ? msg : anchorNote(selClaim); }
function highlightHuman() {
  setHrNote();
  if (!HF.ready) { HF.pending = selClaim; return; }   /* snap as soon as the page is indexed */
  for (const [cid, ms] of Object.entries(HF.marks)) for (const m of ms) m.classList.toggle('sel', cid === selClaim);
  const ms = HF.marks[selClaim];
  if (!ms || !ms.length) return;
  ms[0].scrollIntoView({block: 'center', behavior: 'smooth'});
  /* a brief flash, so it is obvious which passage the click landed on */
  for (const m of ms) { m.classList.remove('flash'); void m.offsetWidth; m.classList.add('flash'); }
}

/* ---------- report view ---------- */
function selectClaim(cid) {
  selClaim = cid; cardForced = false;
  renderRail(); renderClaimLine(); highlightModel(); highlightHuman();
  for (const li of [...openParas]) updateParaLine(selReport, li);
  renderClaimCard();
}
function renderRail() {
  const rail = document.getElementById('rail'); rail.replaceChildren(); if (!selReport) return;
  const r = RBY[selReport];
  for (const cid of CIDS) {
    if (!statusOk(selReport, cid)) continue;
    const s = r.scores[cid], e = entry(selReport, cid);
    const ch = el('button', 'chip' + (cid === selClaim ? ' sel' : '')); ch.appendChild(el('span', 'dot ' + scoreClass(s.score))); ch.appendChild(document.createTextNode(cid));
    const dis = disagreement(selReport, cid); if (dis) ch.classList.add('dis');
    const st = e && e.verdict ? (e.verdict === 'todo' ? '?' : CAT[e.verdict][1] === 'dang' ? '✗' : '✓') : ''; if (st || dis || (e && e.rubric_issue)) ch.appendChild(el('span', 'st', st + (e.rubric_issue ? '⚑' : '') + (dis ? '≠' : '')));
    ch.title = CBY[cid].claim; ch.onclick = () => { selectClaim(cid); jumpToClaim(); }; rail.appendChild(ch);
  }
}
function lineFor(cid) {
  for (const d of document.querySelectorAll('#mdoc .ln.p')) if ((d.dataset.cids || '').split(',').includes(cid)) return +d.dataset.li;
  return null;
}
/* clicking a chip both scrolls to the match and opens its card, so scoring is one click away */
function jumpToClaim() {
  const li = lineFor(selClaim);
  if (li == null) { cardForced = true; renderClaimCard(); return; }
  openParas.add(li); updateParaLine(selReport, li);
}
function renderClaimLine() {
  const box = document.getElementById('claimline'); box.replaceChildren(); if (!selReport) return;
  const c = CBY[selClaim], s = RBY[selReport].scores[selClaim];
  box.appendChild(el('span', 'badge', c.id));
  box.appendChild(el('span', 'sc ' + scoreClass(s.score), 'judge ' + fmtScore(s.score)));
  const t = el('span', 'txt', c.section + ' — ' + c.claim); box.appendChild(t);
  box.appendChild(el('span', 'spacer'));
  box.appendChild(el('span', 'anchor', anchorNote(selClaim)));
  const b = el('button', 'vb plain' + (cardForced ? ' on' : ''), lineFor(selClaim) == null ? 'score this claim' : 'card');
  b.onclick = () => { const li = lineFor(selClaim); if (li == null) { cardForced = !cardForced; renderClaimCard(); } else { openParas.add(li); updateParaLine(selReport, li); const d = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (d) d.scrollIntoView({block: 'center'}); } };
  box.appendChild(b);
}
/* A claim the judge did not quote (or whose quote is nowhere in the report) has no line to
   open a card under; it gets this floating card instead, so negatives stay auditable. */
function renderClaimCard() {
  const box = document.getElementById('claimcard');
  if (view !== 'report' || !selReport) { box.hidden = true; return; }
  const matched = lineFor(selClaim) != null;
  if (matched && !cardForced) { box.hidden = true; box.replaceChildren(); return; }
  box.hidden = false; box.replaceChildren();
  const hdr = el('div', 'hdr', matched ? 'this claim also has a highlighted line in the report' : 'no match in this report — audit it here');
  const x = el('button', 'x', '✕'); x.onclick = () => { cardForced = false; box.hidden = true; renderClaimLine(); }; hdr.appendChild(x);
  box.appendChild(hdr);
  box.appendChild(claimHead(selClaim, true));
  box.appendChild(judgeBox(selReport, selClaim));
  box.appendChild(auditControls(selReport, selClaim));
}
function lineClass(line, inCode) {
  if (inCode || line.startsWith('```')) return 'code';
  if (/^#\s/.test(line)) return 'h1'; if (/^##\s/.test(line)) return 'h2'; if (/^#{3,}\s/.test(line)) return 'h3';
  if (line.startsWith('|')) return 'tbl'; if (line.startsWith('>')) return 'quote'; return '';
}
function decorateLine(div, rk, li) {
  const a = para(rk, li); div.classList.remove('has', 'a-true', 'a-false', 'a-irr', 'a-note');
  if (!a) return; div.classList.add('has');
  if (a.truth === 'false' || a.rating === 'high') div.classList.add('a-false'); else if (a.relevant === 'no') div.classList.add('a-irr'); else if (a.truth === 'true' || a.relevant === 'yes' || a.rating) div.classList.add('a-true'); else div.classList.add('a-note');
}
/* the standing question for a paragraph: unmatched, is it true; matched, is the rating right.
   The relevance row and the paragraph note box were removed — the per-claim comment is where
   prose goes. Existing relevant/note values still load and still colour the line. */
function paraQuestions(rk, li, cids) {
  const a = para(rk, li) || {}; const box = el('div', 'qs');
  const r1 = el('div', 'row');
  if (!cids.length) {
    r1.appendChild(el('span', 'lab', 'No human match — true?'));
    for (const [v, l] of [['true', 'true'], ['false', 'false'], ['unsure', 'unsure']]) chipBtn(r1, a.truth === v, l, () => { setPara(rk, li, {truth: a.truth === v ? null : v}); updateParaLine(rk, li); }, v === 'true' ? 'ok' : v === 'false' ? 'dang' : 'grey');
  } else {
    r1.appendChild(el('span', 'lab', 'Matched ' + cids.map(c => c + ' (' + fmtScore(RBY[rk].scores[c].score) + ')').join(', ') + ' — the rating is'));
    for (const [v, l] of [['agree', 'right'], ['high', 'too high'], ['low', 'too low']]) chipBtn(r1, a.rating === v, l, () => { setPara(rk, li, {rating: a.rating === v ? null : v}); updateParaLine(rk, li); }, v === 'agree' ? 'ok' : 'warn');
    r1.appendChild(el('span', 'lab', '· also true?'));
    for (const [v, l] of [['true', 'true'], ['false', 'false']]) chipBtn(r1, a.truth === v, l, () => { setPara(rk, li, {truth: a.truth === v ? null : v}); updateParaLine(rk, li); }, v === 'true' ? 'ok' : 'dang');
  }
  box.appendChild(r1);
  return box;
}
/* One card under the line: the claim controls for every judge match on it, then the paragraph questions. */
function lineCard(rk, li, cids) {
  const s = el('div', 'strip'); s.dataset.li = li; s.onclick = ev => ev.stopPropagation();
  const order = cids.slice().sort((a, b) => (a === selClaim ? -1 : 0) - (b === selClaim ? -1 : 0));
  for (const cid of order) {
    const cb = el('div', 'cbox' + (cid === selClaim ? ' sel' : ''));
    cb.appendChild(claimHead(cid, false));
    cb.appendChild(judgeBox(rk, cid));
    cb.appendChild(auditControls(rk, cid));
    s.appendChild(cb);
  }
  s.appendChild(paraQuestions(rk, li, cids));
  return s;
}
function updateParaLine(rk, li) {
  const div = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (!div) return;
  decorateLine(div, rk, li); const old = div.nextElementSibling; if (old && old.classList.contains('strip')) old.remove();
  if (openParas.has(li)) div.after(lineCard(rk, li, (div.dataset.cids || '').split(',').filter(Boolean)));
  renderStats();
}
function togglePara(rk, li) {
  openParas.has(li) ? openParas.delete(li) : openParas.add(li); updateParaLine(rk, li);
  if (openParas.has(li)) { const ta = document.querySelector('#mdoc .strip[data-li="' + li + '"] textarea'); if (ta) ta.focus(); }
}

/* ---------- markdown, rendered without moving a character ----------
   Every character of the line keeps its place and its order in the DOM; the syntax markers
   are simply wrapped in a span the stylesheet hides. So the Python character offsets that
   drive the highlights, and the data-li line indices the paragraph cards key off, are
   untouched — the reader just sees bold text instead of asterisks.
   Returns one tag per character: '' plain, 'mk' a hidden marker, or strong/em/code/bul/pipe. */
function mdRuns(line, cls) {
  const n = line.length, k = new Array(n).fill('');
  if (cls === 'code') return k;                       /* inside a fence, nothing is markup */
  const set = (s, e, v) => { for (let i = s; i < e; i++) k[i] = v; };
  const free = (s, e) => { for (let i = s; i < e; i++) if (k[i]) return false; return true; };
  if (/^\s*(?:[-*_] *){3,}$/.test(line)) { set(0, n, 'mk'); return k; }   /* a horizontal rule */
  let m;
  if ((m = /^(\s*)#{1,6}\s+/.exec(line))) set(m[1].length, m[0].length, 'mk');
  else if ((m = /^(\s*)>+\s?/.exec(line))) set(m[1].length, m[0].length, 'mk');
  else if ((m = /^(\s*)[-*+](\s+)/.exec(line))) set(m[1].length, m[1].length + 1, 'bul');
  if (cls === 'tbl') { for (let i = 0; i < n; i++) if (line[i] === '|') k[i] = 'pipe'; return k; }
  const pass = (re, kind) => {
    re.lastIndex = 0; let mm;
    while ((mm = re.exec(line))) {
      const s = mm.index, e = s + mm[0].length, w = mm[1].length;
      if (!free(s, e)) continue;
      if (mm[1][0] === '_') {                         /* leave snake_case identifiers alone */
        if (/[A-Za-z0-9]/.test(s ? line[s - 1] : ' ') || /[A-Za-z0-9]/.test(e < n ? line[e] : ' ')) continue;
      }
      set(s, s + w, 'mk'); set(e - w, e, 'mk'); set(s + w, e - w, kind);
    }
  };
  pass(/(`+)([^`]+?)\1/g, 'code');
  pass(/(\*\*|__)(\S(?:[\s\S]*?\S)?)\1/g, 'strong');
  pass(/(\*|_)(\S(?:[\s\S]*?\S)?)\1/g, 'em');
  return k;
}
function mdRun(parent, text, kind) {
  if (!kind) { parent.appendChild(document.createTextNode(text)); return; }
  const x = document.createElement(kind === 'strong' ? 'strong' : kind === 'em' ? 'em' : kind === 'code' ? 'code' : 'span');
  if (kind === 'mk' || kind === 'bul' || kind === 'pipe') x.className = 'md-' + kind;
  x.textContent = text; parent.appendChild(x);
}
/* emit line[from,to) into parent, one element per run of like-tagged characters */
function mdEmit(parent, line, k, from, to) {
  let i = from;
  while (i < to) { let j = i; while (j + 1 < to && k[j + 1] === k[i]) j++; mdRun(parent, line.slice(i, j + 1), k[i]); i = j + 1; }
}

function renderDoc(target, text, ranges, rk) {
  const lines = text.split('\n'); const frag = document.createDocumentFragment(); let off = 0, inCode = false;
  lines.forEach((line, li) => {
    const ls = off, le = off + line.length; off = le + 1;
    const cls = lineClass(line, inCode);
    const div = el('div', 'ln ' + cls); if (line.startsWith('```')) inCode = !inCode;
    const k = mdRuns(line, cls);
    const cuts = new Set([ls, le]); const hits = [];
    for (const r of ranges) if (r.e > ls && r.s < le) { hits.push(r); cuts.add(Math.max(r.s, ls)); cuts.add(Math.min(r.e, le)); }
    if (!hits.length) mdEmit(div, line, k, 0, line.length);
    else {
      const pts = [...cuts].sort((a, b) => a - b);
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1]; if (a >= b) continue; const cover = hits.filter(r => r.s < b && r.e > a);
        if (!cover.length) { mdEmit(div, line, k, a - ls, b - ls); continue; }
        const m = el('mark'); const sel = cover.find(r => r.cid === selClaim); const top = sel || cover.slice().sort((x, y) => (y.score || 0) - (x.score || 0))[0];
        m.className = scoreClass(top.score) + (sel ? ' sel' : ''); m.dataset.cids = cover.map(r => r.cid).join(',');
        m.title = cover.map(r => r.cid + ' (' + fmtScore(r.score) + ') ' + CBY[r.cid].claim).join(' · '); mdEmit(m, line, k, a - ls, b - ls);
        m.onclick = ev => {
          ev.stopPropagation();
          const next = sel && cover.length > 1 ? cover[(cover.indexOf(sel) + 1) % cover.length].cid : cover[0].cid;
          selectClaim(next); openParas.add(li); updateParaLine(rk, li);
        };
        div.appendChild(m);
      }
    }
    if (line.trim()) {
      div.classList.add('p'); div.dataset.li = li; div.dataset.cids = [...new Set(hits.map(h => h.cid))].join(',');
      /* only the highlighted spans open a claim's card. The gutter pencil is the way in for
         a paragraph the judge did not match, so the body of the report is not a minefield. */
      const g = el('button', 'g', '✎'); g.title = 'note this paragraph';
      g.onclick = ev => { ev.stopPropagation(); togglePara(rk, li); };
      div.prepend(g);
      decorateLine(div, rk, li);
      frag.appendChild(div);
      if (openParas.has(li)) frag.appendChild(lineCard(rk, li, div.dataset.cids.split(',').filter(Boolean)));
      return;
    }
    frag.appendChild(div);
  });
  target.replaceChildren(frag);
}
function highlightModel() {
  const root = document.getElementById('mdoc'); let first = null;
  for (const m of root.querySelectorAll('mark')) { const on = (m.dataset.cids || '').split(',').includes(selClaim); m.classList.toggle('sel', on); if (on && !first) first = m; }
  if (first) first.scrollIntoView({block: 'center', behavior: 'smooth'});
}
function renderDocs() {
  if (!selReport) { document.getElementById('mdoc').replaceChildren(); document.getElementById('mr-title').textContent = ''; return; }
  if (!loaded(selReport)) {
    const want = selReport;
    document.getElementById('mdoc').replaceChildren(el('div', 'empty', 'loading report…'));
    document.getElementById('mr-title').textContent = RBY[want].file;
    details(want).then(() => { if (selReport === want && view === 'report') { renderDocs(); renderClaimLine(); renderClaimCard(); } })
                 .catch(e => { if (selReport === want) document.getElementById('mdoc').replaceChildren(el('div', 'empty', 'could not load this report: ' + e.message)); });
    return;
  }
  const r = RBY[selReport];
  document.getElementById('mr-title').textContent = r.file;
  const ranges = []; for (const cid of CIDS) for (const [s, e] of r.scores[cid].ranges) ranges.push({s, e, cid, score: r.scores[cid].score});
  renderDoc(document.getElementById('mdoc'), r.text, ranges, selReport);
  renderReportNotes();
  highlightModel(); highlightHuman(); renderClaimLine(); renderClaimCard();
}
function renderReportNotes() {
  const box = document.getElementById('mnotes'); box.replaceChildren(); if (!selReport) return;
  const nt = note(selReport) || {};
  for (const [k, lab, ph] of [['hypotheses', 'Hypotheses — what in this report is true vs false', 'e.g. the 06-22 collapse is real but the "site-level block" story is wrong; the proxy recipes are real…'], ['biases', 'Biases the model is running into', 'e.g. over-reads deletion counts as moderator action; anchors on the first named agent…']]) {
    box.appendChild(el('label', '', lab)); const ta = el('textarea'); ta.placeholder = ph; ta.value = nt[k] || ''; ta.oninput = () => { setNote(selReport, {[k]: ta.value}); }; box.appendChild(ta);
  }
  const btn = document.getElementById('mnotes-btn'); btn.textContent = 'notes' + (hasNotes(selReport) ? ' ●' : ''); btn.classList.toggle('on', !box.hidden);
}
document.getElementById('mnotes-btn').onclick = () => { const b = document.getElementById('mnotes'); b.hidden = !b.hidden; document.getElementById('mnotes-btn').classList.toggle('on', !b.hidden); if (!b.hidden) { const ta = b.querySelector('textarea'); if (ta) ta.focus(); } };

/* ---------- claim view ---------- */
function cardFor(rk, cid) {
  const r = RBY[rk]; const card = el('div', 'card'); card.dataset.key = rk;
  const left = el('div'); const hd = el('div', 'hd'); hd.appendChild(el('span', '', r.title + ' · rep' + r.rep)); hd.appendChild(el('span', 'b', r.budget + ' min · ' + r.round + ' · judge mean ' + (r.accuracy == null ? '–' : r.accuracy.toFixed(2))));
  left.appendChild(hd); left.appendChild(judgeBox(rk, cid)); card.appendChild(left);
  card.appendChild(auditControls(rk, cid, {jump: true})); return card;
}
function renderClaimView() {
  const head = document.getElementById('claimhead'); head.replaceChildren(); head.appendChild(claimHead(selClaimView, true));
  const cards = document.getElementById('cards'); cards.replaceChildren();
  const reps = filteredReports().filter(r => statusOk(r.key, selClaimView)).sort((a, b) => (b.scores[selClaimView].score || 0) - (a.scores[selClaimView].score || 0) || (b.accuracy || 0) - (a.accuracy || 0) || a.title.localeCompare(b.title));
  const n = reps.length, pos = reps.filter(r => isPos(r.scores[selClaimView].score)).length;
  head.appendChild(el('div', 'cat', n + ' reports shown · ' + pos + ' judge-positive · sorted by judge score'));
  for (const r of reps) cards.appendChild(cardFor(r.key, selClaimView));
  if (!n) cards.appendChild(el('div', 'empty', 'no reports match the filters'));
  const cid = selClaimView;
  for (const r of reps) if (!loaded(r.key)) details(r.key).then(() => {
    if (view !== 'claim' || selClaimView !== cid) return;
    const old = document.querySelector('#cards .card[data-key="' + r.key + '"]');
    if (old) old.replaceWith(cardFor(r.key, cid));
  }).catch(() => {});
}

/* ---------- notes view ---------- */
function notesCard(rk) {
  const c = el('div', 'ncard'); const global = rk === GLOBAL; const nt = note(rk) || {};
  const h = el('h4', '', global ? 'Across reports' : RBY[rk].title + ' · rep' + RBY[rk].rep);
  if (!global) { h.appendChild(el('span', '', RBY[rk].budget + ' min · ' + RBY[rk].round + ' · judge mean ' + (RBY[rk].accuracy == null ? '–' : RBY[rk].accuracy.toFixed(2)))); const a = el('a', 'link', 'open →'); a.onclick = () => switchView('report', () => { selReport = rk; }); h.appendChild(a); }
  c.appendChild(h);
  for (const [k, lab, ph] of [['hypotheses', global ? 'Hypotheses — what tends to be true vs false in the model reports' : 'Hypotheses — what in this report is true vs false', ''], ['biases', global ? 'Biases the models run into' : 'Biases this model is running into', '']]) {
    c.appendChild(el('label', '', lab)); const ta = el('textarea'); ta.value = nt[k] || ''; ta.placeholder = ph; ta.oninput = () => setNote(rk, {[k]: ta.value}); c.appendChild(ta);
  }
  if (!global) {
    const lines = (RBY[rk].text || '').split('\n');
    const ps = Object.entries(myMap('paragraphs')).filter(([k]) => k.startsWith(rk + '/p')).map(([k, v]) => [parseInt(k.split('/p')[1]), v]).sort((a, b) => a[0] - b[0]);
    if (ps.length) c.appendChild(el('label', '', ps.length + ' paragraph notes'));
    for (const [li, a] of ps) {
      const p = el('div', 'pl'); const fake = el('div'); decorateLine(fake, rk, li); p.className = 'pl ' + [...fake.classList].filter(x => x.startsWith('a-')).join(' ');
      const tags = el('div', 'tags'); if (a.relevant) tags.appendChild(el('span', '', 'relevant: ' + a.relevant)); if (a.truth) tags.appendChild(el('span', '', 'true? ' + a.truth)); if (a.rating) tags.appendChild(el('span', '', 'rating: ' + (a.rating === 'agree' ? 'right' : 'too ' + a.rating)));
      const jump = el('a', 'link', '¶ ' + (li + 1) + ' →'); jump.onclick = () => switchView('report', () => { selReport = rk; openParas.clear(); openParas.add(li); }, () => { const d = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (d) d.scrollIntoView({block: 'center'}); }); tags.prepend(jump);
      p.appendChild(tags); const t = (lines[li] || a.anchor || ''); p.appendChild(el('div', 't', t.length > 400 ? t.slice(0, 400) + '…' : t)); if (a.note) p.appendChild(el('div', 'n', a.note)); c.appendChild(p);
    }
  }
  return c;
}
function renderNotesView() {
  const box = document.getElementById('notes'); box.replaceChildren();
  box.appendChild(notesCard(GLOBAL));
  const reps = filteredReports(); const shown = new Set();
  const order = []; if (selReport) order.push(selReport);
  for (const r of reps) if (r.key !== selReport && (hasNotes(r.key) || paraCount(r.key))) order.push(r.key);
  for (const rk of order) if (!shown.has(rk)) { shown.add(rk); box.appendChild(notesCard(rk)); }
  for (const rk of order) if (!loaded(rk) && paraCount(rk)) details(rk).then(() => { if (view === 'notes') renderNotesView(); }).catch(() => {});
  if (order.length <= 1) box.appendChild(el('div', 'empty', 'Reports with notes or paragraph annotations appear here as you add them.'));
}

/* ---------- top level ---------- */
function switchView(v, before, after) {
  view = v; if (before) before(); document.querySelectorAll('.tab[data-view]').forEach(t => t.classList.toggle('active', t.dataset.view === v)); renderAll(); if (after) setTimeout(after, 0);
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
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  if (ev.key === '[') { toggleSidebar(); ev.preventDefault(); return; }
  const reps = filteredReports();
  if (view === 'report' && selReport) {
    const vis = CIDS.filter(c => statusOk(selReport, c)); const ci = vis.indexOf(selClaim);
    if (ev.key === 'j' || ev.key === 'ArrowDown') { if (ci < vis.length - 1) { selectClaim(vis[ci + 1]); jumpToClaim(); } ev.preventDefault(); return; }
    if (ev.key === 'k' || ev.key === 'ArrowUp') { if (ci > 0) { selectClaim(vis[ci - 1]); jumpToClaim(); } ev.preventDefault(); return; }
    const ri = reps.findIndex(r => r.key === selReport);
    if (ev.key === 'n' && ri < reps.length - 1) { selReport = reps[ri + 1].key; openParas.clear(); cardForced = false; renderMain(); renderList(); return; }
    if (ev.key === 'p' && ri > 0) { selReport = reps[ri - 1].key; openParas.clear(); cardForced = false; renderMain(); renderList(); return; }
    if (/^[1-4]$/.test(ev.key)) { const pos = isPos(RBY[selReport].scores[selClaim].score); const o = VERDICTS[pos ? 'pos' : 'neg'][+ev.key - 1]; if (!o) return; const e = entry(selReport, selClaim) || {}; setEntry(selReport, selClaim, {verdict: e.verdict === o.v ? null : o.v}); refresh(selReport, selClaim); return; }
    if (ev.key === 'c') {
      jumpToClaim();
      const ta = document.querySelector('#mdoc textarea.cmt[data-cid="' + selClaim + '"]') || document.querySelector('#claimcard textarea.cmt');
      if (ta) { ta.focus(); ta.scrollIntoView({block: 'center'}); ev.preventDefault(); }
      return;
    }
    if (ev.key === 'e') { document.getElementById('mnotes-btn').click(); ev.preventDefault(); return; }
  } else if (view === 'claim') {
    const ci = CIDS.indexOf(selClaimView);
    if ((ev.key === 'j' || ev.key === 'ArrowDown') && ci < CIDS.length - 1) { selClaimView = CIDS[ci + 1]; renderMain(); renderList(); ev.preventDefault(); }
    if ((ev.key === 'k' || ev.key === 'ArrowUp') && ci > 0) { selClaimView = CIDS[ci - 1]; renderMain(); renderList(); ev.preventDefault(); }
  } else if (view === 'notes') {
    const ri = reps.findIndex(r => r.key === selReport);
    if (ev.key === 'n' && ri < reps.length - 1) { selReport = reps[ri + 1].key; renderMain(); renderList(); }
    if (ev.key === 'p' && ri > 0) { selReport = reps[ri - 1].key; renderMain(); renderList(); }
  }
});
initHuman();
renderAll();
load().then(() => {
  adoptLegacy(); renderWho(); renderAll();
  let seen = false; try { seen = localStorage.getItem(INTRO_KEY) === '1'; } catch (e) {}
  if (!ME || !seen) openIntro();          /* first visit: the task, the scale, and a name */
});
</script></body></html>'''

if __name__ == "__main__":
    main()
