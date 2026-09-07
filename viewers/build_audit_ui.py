#!/usr/bin/env python3
"""Build viewers/audit.html — audit the recall judge claim by claim.

Reads every benchmark/graded_inputs/<dir>/ that has an _index.jsonl (round 2 and 3
batches), the matching benchmark/graded/graded_<key>.json, the six rubric sheets and the
human report. Emits one self-contained page:

- pick a report; every judge quote is highlighted in the model report (colour = score);
- pick a claim; the model pane scrolls to its quote and the human pane snaps to the
  passage the rubric cites;
- record a verdict (TP / FP / TN easy / TN hard / FN / needs investigation), a corrected
  score, a rubric flag and a comment; the page autosaves to
  benchmark/audit/judge_audit.json through the html-viewer's POST /save endpoint
  (localStorage mirror when the server is unreachable).

Quote matching is done here, not in the browser: exact, then whitespace/punctuation-
normalised, then "..." fragments, then a word-overlap fallback marked approximate.
"""
import json, re, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, HUMAN_REPORT, RUBRICS, GRADED, GRADED_INPUTS, VIEWERS

OUT = VIEWERS / "audit.html"
DATA_DIR = VIEWERS / "data" / "audit"          # one <key>.json per report, fetched on demand
AUDIT_PATH = ROOT / "benchmark" / "audit" / "judge_audit.json"

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
        self.lines = []
        off = 0
        for line in text.split("\n"):
            ln, _ = norm_map(line)
            self.lines.append((off, off + len(line), set(re.findall(r"[a-z0-9]{4,}", ln))))
            off += len(line) + 1

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
        q = (quote or "").strip().strip('"“”')
        if len(q) < 4:
            return [], "none"
        i = self.text.find(q)
        if i >= 0:
            return [[i, i + len(q)]], "exact"
        r = self._norm_find(q)
        if r:
            return [r], "norm"
        parts = [p for p in re.split(r"\s*(?:\.\.\.|…|\[\.\.\.\]|\[…\])\s*", q) if len(p.strip()) >= 12]
        rngs = [r for r in (self._norm_find(p) for p in parts) if r]
        if rngs:
            return rngs, "fragment"
        qn, _ = norm_map(q)
        qwords = set(re.findall(r"[a-z0-9]{4,}", qn))
        if len(qwords) >= 3:
            best = None
            for s, e, words in self.lines:
                if not words:
                    continue
                ov = len(qwords & words) / len(qwords)
                if best is None or ov > best[0]:
                    best = (ov, s, e)
            if best and best[0] >= 0.5:
                return [[best[1], best[2]]], "fuzzy"
        return [], "none"


def load_human():
    lines = HUMAN_REPORT.read_text().split("\n")
    # The dump starts with a stray HTML comment from the site's nav; drop it.
    for k in range(min(30, len(lines))):
        if "-->" in lines[k] and lines[2].strip() == "Findings":
            del lines[3:k + 1]
            break
    out, blank = [], False
    for l in lines:
        if l.strip():
            out.append(l.rstrip()); blank = False
        elif not blank:
            out.append(""); blank = True
    return "\n".join(out).strip("\n")


def load_claims(human):
    claims = []
    for i in range(1, 7):
        rub = json.loads((RUBRICS / f"rubric_{i}.json").read_text())
        for c in rub["claims"]:
            gt = c.get("ground_truth") or {}
            rngs, how = human.find(c.get("report_quote", ""))
            claims.append({
                "id": c["id"], "rubric": rub["rubric_id"], "section": c.get("section"), "level": c.get("level"),
                "claim": c["claim"], "report_quote": c.get("report_quote", ""), "mode": c.get("grading_mode"),
                "trap": c.get("trap") or "", "gt_verdict": gt.get("verdict"), "gt_notes": gt.get("notes") or "",
                "gt_corrections": gt.get("corrections") or "", "human_ranges": rngs, "human_match": how,
            })
    return claims


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


def load_reports(claim_ids):
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
            gpath = GRADED / f"graded_{key}.json"
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
                rngs, how = doc.find(s.get("quote", "")) if s.get("quote") else ([], "none")
                scores[cid] = {"score": s.get("score"), "quote": s.get("quote", ""), "reason": s.get("reason", ""),
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
    human = Doc(load_human())
    claims = load_claims(human)
    reports, warn = load_reports([c["id"] for c in claims])
    for w in warn:
        print("warn:", w)
    tot = {}
    for r in reports:
        for k, v in r["match_counts"].items():
            tot[k] = tot.get(k, 0) + v
    for stale in DATA_DIR.glob("*.json"):
        if stale.stem not in {r["key"] for r in reports}:
            stale.unlink()
    data = {"audit_path": str(AUDIT_PATH), "data_dir": str(DATA_DIR), "human_text": human.text,
            "claims": claims, "reports": reports,
            "built": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload))
    det = sum(f.stat().st_size for f in DATA_DIR.glob("*.json"))
    print(f"{OUT}: {len(reports)} reports, {len(claims)} claims; shell {OUT.stat().st_size/1e6:.2f} MB inline + "
          f"{det/1e6:.2f} MB in {DATA_DIR.name}/ fetched on demand; quote matches {tot}; "
          f"human anchors {sum(1 for c in claims if c['human_ranges'])}/{len(claims)}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Judge audit — MessageBoardAuditBench</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666666;--mut:#999999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok:#065F46;--warn-bg:#FEF3C7;--warn:#92400E;--dang-bg:#FEE2E2;--dang:#991B1B;--grey-bg:#ECEAE3;--grey:#555}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);font-size:13px;line-height:1.45;display:grid;grid-template-rows:auto 1fr;height:100vh;overflow:hidden}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
header{padding:8px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
h1{color:var(--accent);font-size:17px;margin:0;white-space:nowrap}
.sub{color:var(--mut);font-size:11px}
.tabs{display:flex;gap:4px}
.tab{padding:5px 12px;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--ink2);cursor:pointer;font-weight:600;font-size:12px;font-family:inherit}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.stats{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto;align-items:center}
.badge{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--soft);color:var(--accent2);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.dang{background:var(--dang-bg);color:var(--dang)}.badge.grey{background:var(--grey-bg);color:var(--grey)}
#save{font-size:11px;color:var(--mut);min-width:150px;text-align:right}#save.err{color:var(--dang);font-weight:600}
#layout{display:grid;grid-template-columns:290px 1fr;min-height:0}
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
#rail{display:flex;gap:4px;padding:7px 12px;overflow-x:auto;border-bottom:1px solid var(--border);background:var(--bg);align-items:center}
.chip{flex:none;padding:2px 7px;border-radius:6px;border:1px solid var(--border);background:var(--card);cursor:pointer;font-size:11px;font-weight:600;display:flex;gap:5px;align-items:center;font-family:inherit}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--grey-bg)}
.dot.s1{background:#34A87A}.dot.s05{background:#E4A93A}.dot.s0{background:#D6D3CB}
.chip.sel{border-color:var(--accent);box-shadow:0 0 0 2px var(--soft);background:var(--soft)}
.chip .st{font-size:10px;color:var(--mut)}
#audit{padding:10px 14px;border-bottom:1px solid var(--border);background:var(--card);display:grid;grid-template-columns:1.25fr 1fr;gap:16px;max-height:40vh;overflow:auto}
.cl-id{font-size:11px;color:var(--mut);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.cl-text{font-weight:600;font-size:14px;margin:4px 0 6px}
.hq{font-style:italic;color:var(--ink2);border-left:3px solid var(--soft);padding-left:8px;margin:4px 0}
.gt{font-size:11.5px;color:var(--ink2);margin-top:4px}.gt b{color:var(--ink)}
.judge{margin-top:8px;padding:8px 10px;background:var(--row);border:1px solid var(--border);border-radius:8px}
.judge .q{font-style:italic;margin:4px 0}.judge .r{color:var(--ink2)}
.sc{display:inline-block;padding:1px 8px;border-radius:20px;font-weight:700;font-size:11px}
.sc.s1{background:var(--ok-bg);color:var(--ok)}.sc.s05{background:var(--warn-bg);color:var(--warn)}.sc.s0{background:var(--grey-bg);color:var(--grey)}
.verd{display:flex;flex-wrap:wrap;gap:5px;margin:4px 0 8px}
.vb{padding:4px 10px;border:1px solid var(--border);border-radius:7px;background:transparent;cursor:pointer;font-size:12px;font-weight:600;color:var(--ink2);font-family:inherit}
.vb:hover{background:var(--row)}
.vb.on.ok{background:var(--ok-bg);color:var(--ok);border-color:#9AD6BC}.vb.on.warn{background:var(--warn-bg);color:var(--warn);border-color:#E5CB7A}.vb.on.dang{background:var(--dang-bg);color:var(--dang);border-color:#F0A6A6}.vb.on.grey{background:var(--grey-bg);color:var(--grey);border-color:#C9C6BC}
.vb .k{font-size:10px;color:var(--mut);font-weight:400;margin-right:4px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0;font-size:12px;color:var(--ink2)}
.row .vb{padding:2px 9px}
textarea{width:100%;min-height:54px;border:1px solid var(--border);border-radius:7px;padding:6px 8px;font-family:inherit;font-size:12.5px;resize:vertical;background:#fff}
textarea:focus{outline:2px solid var(--soft);border-color:var(--accent)}
.cat{font-size:11px;color:var(--mut)}
#panes{display:grid;grid-template-columns:1fr 1fr;min-height:0}
.pane{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--border)}
.pane:last-child{border-right:0}
.pane h3{margin:0;padding:5px 12px;font-size:12px;color:var(--accent);border-bottom:1px solid var(--border);background:var(--card);display:flex;justify-content:space-between;gap:8px;align-items:center}
.pane h3 span{color:var(--mut);font-weight:400}
.pane h3 button{margin-left:auto}
.remind{font-size:11px;color:var(--mut);padding:3px 12px 3px 26px;border-bottom:1px solid var(--border);background:var(--card);font-style:italic}
.doc{overflow:auto;padding:10px 14px 40vh 26px;background:var(--card);flex:1;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.5}
.ln{min-height:1.4em}
.ln.h1{font-size:16px;font-weight:700;color:var(--accent);margin-top:8px}.ln.h2{font-size:14px;font-weight:700;color:var(--accent2);margin-top:6px}.ln.h3{font-weight:700;margin-top:4px}
.ln.code,.ln.tbl{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;background:var(--row)}
.ln.quote{color:var(--ink2);border-left:3px solid var(--border);padding-left:8px}
.ln.p{position:relative;border-left:3px solid transparent;margin-left:-12px;padding-left:9px;cursor:pointer}
.ln.p:hover{background:var(--row)}
.ln.p .g{position:absolute;left:-17px;top:3px;width:14px;height:14px;border-radius:4px;border:1px solid var(--border);background:var(--card);color:var(--mut);font-size:10px;line-height:12px;text-align:center;opacity:0;font-style:normal}
.ln.p:hover .g,.ln.p.has .g{opacity:1}.ln.p.has .g{color:var(--accent);border-color:var(--accent)}
.ln.p.a-true{border-left-color:#34A87A}.ln.p.a-false{border-left-color:#D9534F}.ln.p.a-irr{border-left-color:#C9C6BC;color:var(--mut)}.ln.p.a-note{border-left-color:var(--accent)}
.strip{margin:2px 0 8px -12px;padding:6px 10px;background:var(--row);border:1px solid var(--border);border-radius:8px;font-size:12px;white-space:normal;cursor:default}
.strip .row{margin:2px 0}.strip textarea{min-height:34px;margin-top:4px}
.strip .lab{font-weight:600;color:var(--ink2)}
#mnotes{padding:8px 12px;border-bottom:1px solid var(--border);background:var(--soft);max-height:34vh;overflow:auto}
#mnotes label,.ncard label{font-size:11px;color:var(--accent2);display:block;margin:6px 0 2px;font-weight:600}
mark{background:transparent;border-radius:3px;padding:0 1px;cursor:pointer;color:inherit}
mark.s1{background:#D1FAE5}mark.s05{background:#FEF3C7}mark.s0{background:#FEE2E2}
mark.approx{text-decoration:underline dashed #B0ACA2;text-underline-offset:2px}
mark.sel{outline:2px solid var(--accent);background:#FBE3D6}
mark.hq{background:#FDF2EC}mark.hq.sel{background:#FBE3D6}
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
  <div><h1>Judge audit</h1><div class="sub" id="built"></div></div>
  <div class="tabs"><button class="tab active" data-view="report">By report</button><button class="tab" data-view="claim">By claim</button><button class="tab" data-view="notes">Notes</button></div>
  <div class="stats" id="stats"></div>
  <div id="save">loading…</div>
</header>
<div id="layout">
  <aside>
    <input class="search" id="q" placeholder="Search reports / claims…">
    <div class="filt" id="f-round"><span class="lab">round</span></div>
    <div class="filt" id="f-budget"><span class="lab">budget</span></div>
    <div class="filt" id="f-agent"><span class="lab">harness</span></div>
    <div class="filt" id="f-status"><span class="lab">show</span></div>
    <div id="list"></div>
    <div class="hint"><b>Keys</b> <kbd>j</kbd>/<kbd>k</kbd> claim · <kbd>n</kbd>/<kbd>p</kbd> report · <kbd>1</kbd>–<kbd>4</kbd> verdict · <kbd>c</kbd> comment · <kbd>e</kbd> report notes · <kbd>Esc</kbd> leave box · click a paragraph to note it</div>
  </aside>
  <main id="main">
    <div id="rail"></div>
    <div id="audit"></div>
    <div id="panes">
      <div class="pane">
        <h3>Model report <span id="mr-title"></span><button class="vb grey" id="mnotes-btn">notes</button></h3>
        <div class="remind">For each paragraph: is it relevant? · if it matches nothing in the human report, is it true or false? · if it matches, do I agree with the judge's rating? — hypotheses and biases go in the report notes.</div>
        <div id="mnotes" hidden></div>
        <div class="doc" id="mdoc"></div>
      </div>
      <div class="pane"><h3>Human report <span id="hr-note"></span></h3><div class="doc" id="hdoc"></div></div>
    </div>
    <div id="claimhead" hidden></div>
    <div id="cards" hidden></div>
    <div id="notes" hidden></div>
  </main>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const AUDIT_PATH = D.audit_path, LS_KEY = 'judge_audit:' + AUDIT_PATH;
const CLAIMS = D.claims, CIDS = CLAIMS.map(c => c.id), CBY = Object.fromEntries(CLAIMS.map(c => [c.id, c]));
const REPORTS = D.reports, RBY = Object.fromEntries(REPORTS.map(r => [r.key, r]));
/* Report bodies and judge quotes load per report; the page itself carries only scores. */
const PEND = {};
function loaded(rk) { return RBY[rk].text != null; }
function details(rk) {
  if (loaded(rk)) return Promise.resolve(RBY[rk]);
  if (!PEND[rk]) PEND[rk] = fetch('/file?p=' + encodeURIComponent(D.data_dir + '/' + rk + '.json'))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(d => { const rep = RBY[rk]; for (const [cid, s] of Object.entries(d.scores)) Object.assign(rep.scores[cid], s); rep.text = d.text; return rep; })
    .catch(e => { delete PEND[rk]; throw e; });
  return PEND[rk];
}
document.getElementById('built').textContent = REPORTS.length + ' reports · ' + CLAIMS.length + ' claims · judge ' + (REPORTS[0] && REPORTS[0].grader) + ' · built ' + D.built;

const VERDICTS = {
  pos: [{v:'tp', l:'Correct (TP)', c:'ok'}, {v:'adjust', l:'Right find, wrong score', c:'warn'}, {v:'fp', l:'Not supported (FP)', c:'dang'}, {v:'todo', l:'Needs investigation', c:'grey'}],
  neg: [{v:'tn_easy', l:'Contradicted by report (TN easy)', c:'ok'}, {v:'tn_hard', l:'Absent, checked (TN hard)', c:'ok'}, {v:'fn', l:'Actually present (FN)', c:'dang'}, {v:'todo', l:'Needs investigation', c:'grey'}],
};
const CAT = {tp:['TP','ok'], adjust:['TP·adj','warn'], fp:['FP','dang'], tn_easy:['TN easy','ok'], tn_hard:['TN hard','ok'], fn:['FN','dang'], todo:['Flagged','grey']};
const GLOBAL = '_global';

let state = {version: 2, updated_at: null, entries: {}, paragraphs: {}, notes: {}};
let view = 'report', selReport = null, selClaim = CIDS[0], selClaimView = CIDS[0];
const filters = {round: new Set(['r3']), budget: new Set(), agent: new Set(), status: new Set(), q: ''};
const openParas = new Set();

/* ---------- persistence ---------- */
function ekey(rk, cid) { return rk + '/' + cid; }
function entry(rk, cid) { return state.entries[ekey(rk, cid)] || null; }
function blank(e) { return !e.verdict && !e.comment && !e.rubric_issue && e.corrected == null && !e.relevant && !e.truth && !e.rating && !e.note && !e.hypotheses && !e.biases; }
function setIn(map, k, patch) {
  const e = Object.assign({}, state[map][k] || {}, patch, {updated_at: new Date().toISOString()});
  for (const key of Object.keys(e)) if (e[key] === null || e[key] === '' || e[key] === false) delete e[key];
  if (blank(e)) delete state[map][k]; else state[map][k] = e;
  scheduleSave();
}
function setEntry(rk, cid, patch) { setIn('entries', ekey(rk, cid), patch); }
function pkey(rk, li) { return rk + '/p' + li; }
function para(rk, li) { return state.paragraphs[pkey(rk, li)] || null; }
function setPara(rk, li, patch) { setIn('paragraphs', pkey(rk, li), Object.assign({anchor: RBY[rk].text.split('\n')[li].slice(0, 100)}, patch)); }
function note(rk) { return state.notes[rk] || null; }
function setNote(rk, patch) { setIn('notes', rk, patch); }
let saveTimer = null;
function setStatus(t, err) { const el = document.getElementById('save'); el.textContent = t; el.className = err ? 'err' : ''; }
function scheduleSave() { clearTimeout(saveTimer); setStatus('unsaved…'); saveTimer = setTimeout(saveNow, 500); }
async function saveNow() {
  state.updated_at = new Date().toISOString();
  const body = JSON.stringify(state, null, 1);
  try { localStorage.setItem(LS_KEY, body); } catch (e) {}
  try {
    const r = await fetch('/save?p=' + encodeURIComponent(AUDIT_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    setStatus('saved to disk ' + new Date().toLocaleTimeString());
  } catch (e) { setStatus('NOT on disk (browser copy kept): ' + e.message, true); }
}
function merge(a, b) {
  const out = {version: 2, updated_at: null, entries: {}, paragraphs: {}, notes: {}};
  for (const src of [a, b]) { if (!src) continue;
    for (const map of ['entries', 'paragraphs', 'notes']) for (const [k, e] of Object.entries(src[map] || {})) { const cur = out[map][k]; if (!cur || (e.updated_at || '') > (cur.updated_at || '')) out[map][k] = e; } }
  return out;
}
function sameContent(a, b) { const s = x => JSON.stringify([x.entries || {}, x.paragraphs || {}, x.notes || {}]); return s(a) === s(b); }
async function load() {
  let server = null, local = null;
  try { const r = await fetch('/file?p=' + encodeURIComponent(AUDIT_PATH)); if (r.ok) server = await r.json(); } catch (e) {}
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = merge(server, local);
  const n = Object.keys(state.entries).length + Object.keys(state.paragraphs).length + Object.keys(state.notes).length;
  if (server === null && local === null) setStatus('no saved audits yet');
  else if (local && !sameContent(state, server || {})) scheduleSave();
  else setStatus('loaded ' + n + ' saved items (' + (server ? 'from disk' : 'browser copy only') + ')', !server);
}

/* ---------- helpers ---------- */
function scoreClass(s) { return s == null ? 's0' : s >= 0.75 ? 's1' : s > 0 ? 's05' : 's0'; }
function isPos(s) { return s != null && s > 0; }
function category(rk, cid) { const e = entry(rk, cid); return e && e.verdict ? e.verdict : null; }
function filteredReports() {
  const q = filters.q.toLowerCase();
  return REPORTS.filter(r => (!filters.round.size || filters.round.has(r.round)) && (!filters.budget.size || filters.budget.has(String(r.budget)))
    && (!filters.agent.size || filters.agent.has(r.agent)) && (!q || (r.title + ' ' + r.file + ' ' + r.budget).toLowerCase().includes(q)));
}
function statusOk(rk, cid) {
  if (!filters.status.size) return true;
  const e = entry(rk, cid), s = RBY[rk].scores[cid].score;
  for (const f of filters.status) {
    if (f === 'pos' && isPos(s)) return true; if (f === 'neg' && !isPos(s)) return true;
    if (f === 'unreviewed' && !(e && e.verdict)) return true; if (f === 'reviewed' && e && e.verdict && e.verdict !== 'todo') return true;
    if (f === 'flagged' && e && (e.verdict === 'todo' || e.rubric_issue)) return true;
  }
  return false;
}
function paraCount(rk) { let n = 0; for (const k of Object.keys(state.paragraphs)) if (k.startsWith(rk + '/p')) n++; return n; }
function hasNotes(rk) { const nt = note(rk); return !!(nt && (nt.hypotheses || nt.biases)); }
function el(tag, cls, text) { const x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; }
function fmtScore(s) { return s == null ? '–' : (s === 1 ? '1' : s === 0 ? '0' : String(s)); }
function chipBtn(parent, on, label, fn, cls) { const b = el('button', 'vb ' + (cls || 'grey') + (on ? ' on' : '')); b.textContent = label; b.onclick = ev => { ev.stopPropagation(); fn(); }; parent.appendChild(b); return b; }

/* ---------- header ---------- */
function renderStats() {
  const reps = filteredReports(); const counts = {}; let pos = 0, reviewed = 0, total = 0, paras = 0, noted = 0;
  for (const r of reps) { paras += paraCount(r.key); if (hasNotes(r.key)) noted++;
    for (const cid of CIDS) { total++; if (isPos(r.scores[cid].score)) pos++; const v = category(r.key, cid); if (v) { counts[v] = (counts[v] || 0) + 1; if (v !== 'todo') reviewed++; } } }
  const box = document.getElementById('stats'); box.replaceChildren();
  box.appendChild(el('span', 'badge grey', reps.length + ' reports'));
  box.appendChild(el('span', 'badge grey', pos + ' judge-positive · ' + (total - pos) + ' negative'));
  box.appendChild(el('span', 'badge', reviewed + '/' + total + ' audited'));
  for (const [v, [lab, c]] of Object.entries(CAT)) if (counts[v]) box.appendChild(el('span', 'badge ' + c, lab + ' ' + counts[v]));
  if (paras || noted) box.appendChild(el('span', 'badge', paras + ' ¶ noted · ' + noted + ' reports with notes'));
}

/* ---------- sidebar ---------- */
function chipRow(id, values, set, labels) {
  const box = document.getElementById(id); box.querySelectorAll('button').forEach(b => b.remove());
  for (const v of values) { const b = el('button', set.has(v) ? 'on' : '', (labels && labels[v]) || v); b.onclick = () => { set.has(v) ? set.delete(v) : set.add(v); renderAll(); }; box.appendChild(b); }
}
function renderFilters() {
  chipRow('f-round', [...new Set(REPORTS.map(r => r.round))].sort(), filters.round, {r2: 'round 2', r3: 'round 3'});
  const budgets = [...new Set(REPORTS.map(r => String(r.budget)))].sort((a, b) => a - b);
  chipRow('f-budget', budgets, filters.budget, Object.fromEntries(budgets.map(b => [b, b + ' min'])));
  chipRow('f-agent', [...new Set(REPORTS.map(r => r.agent))].sort(), filters.agent);
  chipRow('f-status', ['pos', 'neg', 'unreviewed', 'reviewed', 'flagged'], filters.status, {pos: 'judge +', neg: 'judge 0', unreviewed: 'unreviewed', reviewed: 'reviewed', flagged: 'flagged'});
}
function reportItem(r) {
  const it = el('div', 'item' + (r.key === selReport ? ' sel' : '')); it.dataset.key = r.key;
  const nm = el('div', 'nm'); nm.appendChild(el('span', '', r.title + ' · rep' + r.rep)); nm.appendChild(el('span', 'sc ' + scoreClass(r.accuracy), r.accuracy == null ? '–' : r.accuracy.toFixed(2))); it.appendChild(nm);
  const done = CIDS.filter(c => { const v = category(r.key, c); return v && v !== 'todo'; }).length;
  const flagged = CIDS.filter(c => { const e = entry(r.key, c); return e && (e.verdict === 'todo' || e.rubric_issue); }).length;
  const pc = paraCount(r.key);
  const meta = el('div', 'meta'); meta.appendChild(el('span', '', r.budget + ' min')); meta.appendChild(el('span', '', r.round));
  meta.appendChild(el('span', '', done + '/' + CIDS.length + ' audited' + (flagged ? ' · ' + flagged + ' flagged' : '') + (pc ? ' · ' + pc + ' ¶' : '') + (hasNotes(r.key) ? ' · notes' : '')));
  it.appendChild(meta);
  const pg = el('div', 'prog'); const i = el('i'); i.style.width = (100 * done / CIDS.length) + '%'; pg.appendChild(i); it.appendChild(pg);
  it.onclick = () => { selReport = r.key; openParas.clear(); renderMain(); renderList(); };
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
      for (const r of reps) { if (isPos(r.scores[c.id].score)) pos++; const e = entry(r.key, c.id); if (e && e.verdict && e.verdict !== 'todo') done++; if (e && (e.verdict === 'todo' || e.rubric_issue)) flagged++; }
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

/* ---------- audit controls (shared) ---------- */
function auditControls(rk, cid, opts) {
  const r = RBY[rk], s = r.scores[cid], e = entry(rk, cid) || {}; const pos = isPos(s.score);
  const box = el('div');
  const verd = el('div', 'verd');
  VERDICTS[pos ? 'pos' : 'neg'].forEach((o, i) => {
    const b = el('button', 'vb ' + o.c + (e.verdict === o.v ? ' on' : '')); const k = el('span', 'k', String(i + 1)); b.appendChild(k); b.appendChild(document.createTextNode(o.l));
    b.onclick = () => { setEntry(rk, cid, {verdict: e.verdict === o.v ? null : o.v}); refresh(rk, cid); }; verd.appendChild(b);
  });
  box.appendChild(verd);
  const row = el('div', 'row'); row.appendChild(el('span', '', 'Your score:'));
  for (const v of [0, 0.5, 1]) chipBtn(row, e.corrected === v, fmtScore(v), () => { setEntry(rk, cid, {corrected: e.corrected === v ? null : v}); refresh(rk, cid); });
  row.appendChild(el('span', 'cat', '(judge gave ' + fmtScore(s.score) + ')'));
  chipBtn(row, !!e.rubric_issue, (e.rubric_issue ? '⚑ ' : '') + 'rubric / claim needs fixing', () => { setEntry(rk, cid, {rubric_issue: !e.rubric_issue}); refresh(rk, cid); }, 'warn');
  box.appendChild(row);
  const ta = el('textarea'); ta.placeholder = 'Comment — why, what the report actually says, what the rubric should say…'; ta.value = e.comment || '';
  ta.oninput = () => setEntry(rk, cid, {comment: ta.value}); box.appendChild(ta);
  const foot = el('div', 'cat'); const v = e.verdict ? CAT[e.verdict] : null;
  foot.textContent = (v ? 'Category: ' + v[0] : 'Not audited yet') + (e.updated_at ? ' · ' + new Date(e.updated_at).toLocaleString() : '');
  if (opts && opts.jump) { foot.appendChild(document.createTextNode('  ')); const a = el('a', 'link', 'open in report view →'); a.onclick = () => switchView('report', () => { selReport = rk; selClaim = cid; openParas.clear(); }); foot.appendChild(a); }
  box.appendChild(foot);
  return box;
}
function refresh(rk, cid) {
  if (view === 'report') { renderAudit(); renderRail(); } else if (view === 'claim') { const c = document.querySelector('.card[data-key="' + rk + '"]'); if (c) c.replaceWith(cardFor(rk, cid)); }
  renderStats(); renderList();
}

/* ---------- claim info (shared) ---------- */
function claimInfo(cid) {
  const c = CBY[cid]; const box = el('div');
  const id = el('div', 'cl-id'); id.appendChild(el('span', 'badge', c.id)); id.appendChild(el('span', '', c.section + ' · L' + c.level + ' · ' + c.rubric));
  if (c.gt_verdict) id.appendChild(el('span', 'badge grey', 'ground truth: ' + c.gt_verdict)); box.appendChild(id);
  box.appendChild(el('div', 'cl-text', c.claim));
  box.appendChild(el('div', 'hq', '“' + c.report_quote + '”'));
  for (const [lab, txt] of [['Trap: ', c.trap], ['Corrections: ', c.gt_corrections], ['Feasibility notes: ', c.gt_notes]]) if (txt) { const g = el('div', 'gt'); g.appendChild(el('b', '', lab)); g.appendChild(document.createTextNode(txt)); box.appendChild(g); }
  return box;
}
function judgeBox(rk, cid) {
  const s = RBY[rk].scores[cid]; const j = el('div', 'judge');
  if (!loaded(rk)) { j.appendChild(el('span', 'sc ' + scoreClass(s.score), 'judge score ' + fmtScore(s.score))); j.appendChild(el('div', 'r', 'loading the judge quote…')); return j; }
  const hd = el('div'); hd.appendChild(el('span', 'sc ' + scoreClass(s.score), 'judge score ' + fmtScore(s.score)));
  hd.appendChild(el('span', 'cat', '  quote match: ' + s.match)); j.appendChild(hd);
  if (s.quote) j.appendChild(el('div', 'q', '“' + s.quote + '”'));
  j.appendChild(el('div', 'r', s.reason || '')); return j;
}

/* ---------- report view ---------- */
function renderRail() {
  const rail = document.getElementById('rail'); rail.replaceChildren(); if (!selReport) return;
  const r = RBY[selReport];
  for (const cid of CIDS) {
    if (!statusOk(selReport, cid)) continue;
    const s = r.scores[cid], e = entry(selReport, cid);
    const ch = el('button', 'chip' + (cid === selClaim ? ' sel' : '')); ch.appendChild(el('span', 'dot ' + scoreClass(s.score))); ch.appendChild(document.createTextNode(cid));
    const st = e && e.verdict ? (e.verdict === 'todo' ? '?' : CAT[e.verdict][1] === 'dang' ? '✗' : '✓') : ''; if (st || (e && e.rubric_issue)) ch.appendChild(el('span', 'st', st + (e.rubric_issue ? '⚑' : '')));
    ch.title = CBY[cid].claim; ch.onclick = () => { selClaim = cid; renderAudit(); renderRail(); highlight(); }; rail.appendChild(ch);
  }
}
function renderAudit() {
  const a = document.getElementById('audit'); a.replaceChildren(); if (!selReport) return;
  const left = el('div'); left.appendChild(claimInfo(selClaim)); left.appendChild(judgeBox(selReport, selClaim)); a.appendChild(left);
  a.appendChild(auditControls(selReport, selClaim));
}
function lineClass(line, inCode) {
  if (inCode || line.startsWith('```')) return 'code';
  if (/^#\s/.test(line)) return 'h1'; if (/^##\s/.test(line)) return 'h2'; if (/^#{3,}\s/.test(line)) return 'h3';
  if (line.startsWith('|')) return 'tbl'; if (line.startsWith('>')) return 'quote'; return '';
}
/* paragraph notes */
function decorateLine(div, rk, li) {
  const a = para(rk, li); div.classList.remove('has', 'a-true', 'a-false', 'a-irr', 'a-note');
  if (!a) return; div.classList.add('has');
  if (a.truth === 'false' || a.rating === 'high') div.classList.add('a-false'); else if (a.relevant === 'no') div.classList.add('a-irr'); else if (a.truth === 'true' || a.relevant === 'yes' || a.rating) div.classList.add('a-true'); else div.classList.add('a-note');
}
function paraStrip(rk, li, cids) {
  const a = para(rk, li) || {}; const s = el('div', 'strip'); s.dataset.li = li; s.onclick = ev => ev.stopPropagation();
  const r1 = el('div', 'row'); r1.appendChild(el('span', 'lab', 'Relevant?'));
  for (const v of ['yes', 'no']) chipBtn(r1, a.relevant === v, v, () => { setPara(rk, li, {relevant: a.relevant === v ? null : v}); updateParaLine(rk, li); });
  if (!cids.length) {
    r1.appendChild(el('span', 'lab', '· No human match — true?'));
    for (const [v, l] of [['true', 'true'], ['false', 'false'], ['unsure', 'unsure']]) chipBtn(r1, a.truth === v, l, () => { setPara(rk, li, {truth: a.truth === v ? null : v}); updateParaLine(rk, li); }, v === 'true' ? 'ok' : v === 'false' ? 'dang' : 'grey');
  } else {
    r1.appendChild(el('span', 'lab', '· Matched ' + cids.map(c => c + ' (' + fmtScore(RBY[rk].scores[c].score) + ')').join(', ') + ' — the rating is'));
    for (const [v, l] of [['agree', 'right'], ['high', 'too high'], ['low', 'too low']]) chipBtn(r1, a.rating === v, l, () => { setPara(rk, li, {rating: a.rating === v ? null : v}); updateParaLine(rk, li); }, v === 'agree' ? 'ok' : 'warn');
    r1.appendChild(el('span', 'lab', '· also true?'));
    for (const [v, l] of [['true', 'true'], ['false', 'false']]) chipBtn(r1, a.truth === v, l, () => { setPara(rk, li, {truth: a.truth === v ? null : v}); updateParaLine(rk, li); }, v === 'true' ? 'ok' : 'dang');
  }
  s.appendChild(r1);
  const ta = el('textarea'); ta.placeholder = 'Note — hypothesis about what is actually true, or a bias the model is running into…'; ta.value = a.note || '';
  ta.oninput = () => { setPara(rk, li, {note: ta.value}); const div = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (div) decorateLine(div, rk, li); }; s.appendChild(ta);
  return s;
}
function updateParaLine(rk, li) {
  const div = document.querySelector('#mdoc .ln[data-li="' + li + '"]'); if (!div) return;
  decorateLine(div, rk, li); const old = div.nextElementSibling; if (old && old.classList.contains('strip')) old.remove();
  if (openParas.has(li)) div.after(paraStrip(rk, li, (div.dataset.cids || '').split(',').filter(Boolean)));
  renderStats();
}
function togglePara(rk, li) { openParas.has(li) ? openParas.delete(li) : openParas.add(li); updateParaLine(rk, li); if (openParas.has(li)) { const ta = document.querySelector('#mdoc .strip[data-li="' + li + '"] textarea'); if (ta) ta.focus(); } }

function renderDoc(target, text, ranges, rk) {
  const human = !rk; const lines = text.split('\n'); const frag = document.createDocumentFragment(); let off = 0, inCode = false;
  lines.forEach((line, li) => {
    const ls = off, le = off + line.length; off = le + 1;
    const div = el('div', 'ln ' + lineClass(line, inCode)); if (line.startsWith('```')) inCode = !inCode;
    const cuts = new Set([ls, le]); const hits = [];
    for (const r of ranges) if (r.e > ls && r.s < le) { hits.push(r); cuts.add(Math.max(r.s, ls)); cuts.add(Math.min(r.e, le)); }
    if (!hits.length) div.textContent = line;
    else {
      const pts = [...cuts].sort((a, b) => a - b);
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1]; if (a >= b) continue; const seg = text.slice(a, b); const cover = hits.filter(r => r.s < b && r.e > a);
        if (!cover.length) { div.appendChild(document.createTextNode(seg)); continue; }
        const m = el('mark'); const sel = cover.find(r => r.cid === selClaim); const top = sel || cover.slice().sort((x, y) => (y.score || 0) - (x.score || 0))[0];
        m.className = (human ? 'hq' : scoreClass(top.score)) + (sel ? ' sel' : '') + (top.approx ? ' approx' : ''); m.dataset.cids = cover.map(r => r.cid).join(',');
        m.title = cover.map(r => r.cid + (human ? '' : ' (' + fmtScore(r.score) + ')')).join(', '); m.textContent = seg;
        m.onclick = ev => { ev.stopPropagation(); selClaim = sel && cover.length > 1 ? cover[(cover.indexOf(sel) + 1) % cover.length].cid : cover[0].cid; renderAudit(); renderRail(); highlight(); };
        div.appendChild(m);
      }
    }
    if (!human && line.trim()) {
      div.classList.add('p'); div.dataset.li = li; div.dataset.cids = [...new Set(hits.map(h => h.cid))].join(',');
      const g = el('span', 'g', '✎'); g.title = 'note this paragraph'; div.prepend(g);
      div.onclick = () => togglePara(rk, li);
      decorateLine(div, rk, li);
      frag.appendChild(div);
      if (openParas.has(li)) frag.appendChild(paraStrip(rk, li, div.dataset.cids.split(',').filter(Boolean)));
      return;
    }
    frag.appendChild(div);
  });
  target.replaceChildren(frag);
}
let humanRendered = false;
function renderDocs() {
  if (!selReport) { document.getElementById('mdoc').replaceChildren(); return; }
  if (!loaded(selReport)) {
    const want = selReport;
    document.getElementById('mdoc').replaceChildren(el('div', 'empty', 'loading report…'));
    document.getElementById('mr-title').textContent = RBY[want].file;
    details(want).then(() => { if (selReport === want && view === 'report') { renderDocs(); renderAudit(); } })
                 .catch(e => { if (selReport === want) document.getElementById('mdoc').replaceChildren(el('div', 'empty', 'could not load this report: ' + e.message)); });
    return;
  }
  const r = RBY[selReport];
  document.getElementById('mr-title').textContent = r.file;
  const ranges = []; for (const cid of CIDS) for (const [s, e] of r.scores[cid].ranges) ranges.push({s, e, cid, score: r.scores[cid].score, approx: r.scores[cid].match === 'fuzzy' || r.scores[cid].match === 'fragment'});
  renderDoc(document.getElementById('mdoc'), r.text, ranges, selReport);
  if (!humanRendered) { const hr = []; for (const c of CLAIMS) for (const [s, e] of c.human_ranges) hr.push({s, e, cid: c.id, score: 1, approx: c.human_match === 'fuzzy' || c.human_match === 'fragment'}); renderDoc(document.getElementById('hdoc'), D.human_text, hr, null); humanRendered = true; }
  renderReportNotes();
  highlight();
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
function highlight() {
  for (const box of ['mdoc', 'hdoc']) {
    const root = document.getElementById(box); let first = null;
    for (const m of root.querySelectorAll('mark')) { const on = m.dataset.cids.split(',').includes(selClaim); m.classList.toggle('sel', on); if (on && !first) first = m; }
    if (first) first.scrollIntoView({block: 'center', behavior: 'smooth'});
    else if (box === 'mdoc') root.scrollTop = 0;
  }
  const c = CBY[selClaim];
  document.getElementById('hr-note').textContent = c.human_ranges.length ? (c.human_match === 'exact' || c.human_match === 'norm' ? 'anchored to the cited passage' : 'approximate anchor (' + c.human_match + ')') : 'no anchor for ' + selClaim;
}

/* ---------- claim view ---------- */
function cardFor(rk, cid) {
  const r = RBY[rk]; const card = el('div', 'card'); card.dataset.key = rk;
  const left = el('div'); const hd = el('div', 'hd'); hd.appendChild(el('span', '', r.title + ' · rep' + r.rep)); hd.appendChild(el('span', 'b', r.budget + ' min · ' + r.round + ' · judge mean ' + (r.accuracy == null ? '–' : r.accuracy.toFixed(2))));
  left.appendChild(hd); left.appendChild(judgeBox(rk, cid)); card.appendChild(left);
  card.appendChild(auditControls(rk, cid, {jump: true})); return card;
}
function renderClaimView() {
  const head = document.getElementById('claimhead'); head.replaceChildren(); head.appendChild(claimInfo(selClaimView));
  const cards = document.getElementById('cards'); cards.replaceChildren();
  const reps = filteredReports().filter(r => statusOk(r.key, selClaimView)).sort((a, b) => (b.scores[selClaimView].score || 0) - (a.scores[selClaimView].score || 0) || a.title.localeCompare(b.title) || a.budget - b.budget);
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
    const ps = Object.entries(state.paragraphs).filter(([k]) => k.startsWith(rk + '/p')).map(([k, v]) => [parseInt(k.split('/p')[1]), v]).sort((a, b) => a[0] - b[0]);
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
  view = v; if (before) before(); document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === v)); renderAll(); if (after) setTimeout(after, 0);
}
function renderMain() {
  const main = document.getElementById('main');
  main.classList.toggle('claimview', view === 'claim'); main.classList.toggle('notesview', view === 'notes');
  for (const id of ['rail', 'audit', 'panes']) document.getElementById(id).hidden = view !== 'report';
  for (const id of ['claimhead', 'cards']) document.getElementById(id).hidden = view !== 'claim';
  document.getElementById('notes').hidden = view !== 'notes';
  if (view === 'report') { renderRail(); renderAudit(); renderDocs(); } else if (view === 'claim') renderClaimView(); else renderNotesView();
  renderStats();
}
function renderAll() { renderFilters(); renderList(); renderMain(); }
document.querySelectorAll('.tab').forEach(t => t.onclick = () => switchView(t.dataset.view));
document.getElementById('q').oninput = e => { filters.q = e.target.value; renderList(); if (view !== 'report') renderMain(); else renderStats(); };
document.addEventListener('keydown', ev => {
  const tag = (ev.target.tagName || '').toLowerCase();
  if (tag === 'textarea' || tag === 'input') { if (ev.key === 'Escape') ev.target.blur(); return; }
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const reps = filteredReports();
  if (view === 'report' && selReport) {
    const vis = CIDS.filter(c => statusOk(selReport, c)); const ci = vis.indexOf(selClaim);
    if (ev.key === 'j' || ev.key === 'ArrowDown') { if (ci < vis.length - 1) { selClaim = vis[ci + 1]; renderAudit(); renderRail(); highlight(); } ev.preventDefault(); return; }
    if (ev.key === 'k' || ev.key === 'ArrowUp') { if (ci > 0) { selClaim = vis[ci - 1]; renderAudit(); renderRail(); highlight(); } ev.preventDefault(); return; }
    const ri = reps.findIndex(r => r.key === selReport);
    if (ev.key === 'n' && ri < reps.length - 1) { selReport = reps[ri + 1].key; openParas.clear(); renderMain(); renderList(); return; }
    if (ev.key === 'p' && ri > 0) { selReport = reps[ri - 1].key; openParas.clear(); renderMain(); renderList(); return; }
    if (/^[1-4]$/.test(ev.key)) { const pos = isPos(RBY[selReport].scores[selClaim].score); const o = VERDICTS[pos ? 'pos' : 'neg'][+ev.key - 1]; const e = entry(selReport, selClaim) || {}; setEntry(selReport, selClaim, {verdict: e.verdict === o.v ? null : o.v}); refresh(selReport, selClaim); return; }
    if (ev.key === 'c') { const ta = document.querySelector('#audit textarea'); if (ta) { ta.focus(); ev.preventDefault(); } return; }
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
renderAll();
load().then(renderAll);
</script></body></html>'''

if __name__ == "__main__":
    main()
