#!/usr/bin/env python3
"""Build viewers/match_scale.html — try a finer, behaviourally-anchored match scale.

The recall judge currently answers "did the report say this?" with 0, 0.5 or 1, and the
bands are defined structurally (is a specific wrong?). A sibling project
(/workspace/commentbench, matcher/prompts/point-edge-coverage-v4.md) instead anchors its
scale on how a reader would describe the overlap, in 0.1 steps. This page is a draft of
that idea adapted to this benchmark: the proposed anchor table (editable, the wording is
the point) sitting above real judge evidence, so the user can place actual excerpts on
the proposed scale and see whether it separates anything or whether everything bunches.

Inputs
  benchmark/rubrics/rubric_{1..6}.json   the 30 claims
  benchmark/graded/graded_<key>.json     the judge's score/quote/reason per claim
  benchmark/graded_inputs/<dir>/         the reports those keys name, and _index.jsonl
  benchmark/claims/anchors_reports.json  validated spans where the judge quote is not
                                         verbatim in its report — preferred for display

Only round-3 keys (r3b*) are used: they were graded on the current rubric sheets.

Output is a single self-contained page that autosaves to
benchmark/rubric_review/match_scale.json through the html-viewer's POST /save endpoint,
with a localStorage mirror and merge-on-load by updated_at (mechanism copied from
build_audit_ui.py).
"""
import json, re, sys, pathlib, collections

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, RUBRICS, GRADED, GRADED_INPUTS, VIEWERS

OUT = VIEWERS / "match_scale.html"
SAVE_PATH = ROOT / "benchmark" / "rubric_review" / "match_scale.json"
ANCHORS_REPORTS = ROOT / "benchmark" / "claims" / "anchors_reports.json"

PER_GROUP = 6            # excerpts shown per score group, spread over models
ROUND_PREFIX = "r3b"     # graded on the current sheets

# The proposal. Order matters: it is the button order and the keyboard order.
BANDS = [
    ("1.0", "Near-paraphrase. The report states the claim and its specifics."),
    ("0.9", "If the report were set beside the human report, you would say “this has already been said”."),
    ("0.8", "To the extent the human claim adds value, the report delivers most of that value."),
    ("0.6", "Gesturing at the same thing. The human claim could be rephrased as a reply that improves the report."),
    ("0.3", "Distinct but related."),
    ("0.1", "Vaguely related."),
    ("0.0", "Absent, or contradicted by the report."),
]


def sanitize(s):
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")


def parse_stem(stem):
    parts = stem.split("__")
    d = {"prefix": parts[0], "agent": parts[1], "model": parts[2], "rep": None, "served": None}
    for p in parts[3:]:
        if p.startswith("rep"):
            d["rep"] = int(p[3:])
        elif p.startswith("served-"):
            d["served"] = p[len("served-"):]
    return d


def load_claims():
    claims = []
    for f in sorted(RUBRICS.glob("rubric_*.json"), key=lambda p: int(re.search(r"\d+", p.stem).group())):
        d = json.loads(f.read_text())
        for c in d["claims"]:
            claims.append({"id": c["id"], "section": c.get("section", ""), "claim": c["claim"],
                           "report_quote": c.get("report_quote", ""), "rubric": d["rubric_id"]})
    claims.sort(key=lambda c: c["id"])
    return claims


def load_reports():
    """Round-3 reports that have a grade, with display metadata."""
    reports = {}
    for idx in sorted(GRADED_INPUTS.glob("*/_index.jsonl")):
        d = idx.parent
        m = re.match(r"round(\d+)_blind(\d+)$", d.name)
        if not m:
            continue
        budget = int(m.group(2))
        rows = [json.loads(l) for l in idx.read_text().splitlines() if l.strip()]
        for p in sorted(d.glob("*.md")):
            key = sanitize(p.stem)
            if not key.startswith(ROUND_PREFIX):
                continue
            gpath = GRADED / f"graded_{key}.json"
            if not gpath.exists():
                continue
            meta = parse_stem(p.stem)
            row = next((r for r in rows if r.get("graded_input") == p.name), {})
            model = meta["model"]
            label = f"{model} · {meta['agent']} · {budget}m"
            if meta["rep"]:
                label += f" · rep{meta['rep']}"
            if meta["served"]:
                label += f" · served {meta['served']}"
            reports[key] = {"key": key, "label": label, "model": model, "agent": meta["agent"],
                            "budget": budget, "rep": meta["rep"], "served": meta["served"],
                            "grader": json.loads(gpath.read_text()).get("grader", ""),
                            "path": str(p), "grades": json.loads(gpath.read_text())["scores"],
                            "config": row.get("config", "")}
    return reports


def spans_of(ranch, key):
    v = ranch.get(key)
    if isinstance(v, dict):
        return [s for s in v.get("spans", []) if s]
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [s for s in v if isinstance(s, str) and s]
    return []


def pick(cands, n):
    """Up to n excerpts, round-robin over model so a group is not six runs of one model."""
    by_model = collections.OrderedDict()
    for c in cands:
        by_model.setdefault(c["model"], []).append(c)
    for v in by_model.values():
        v.sort(key=lambda c: (c["budget"], c["rep"] or 0))
    out, queues = [], list(by_model.values())
    while len(out) < n and any(queues):
        for q in queues:
            if not q:
                continue
            out.append(q.pop(0))
            if len(out) >= n:
                break
    return out


def build():
    claims = load_claims()
    reports = load_reports()
    ranch = json.loads(ANCHORS_REPORTS.read_text()) if ANCHORS_REPORTS.exists() else {}

    # every judgement, per claim
    raw = {c["id"]: [] for c in claims}
    for key, rep in reports.items():
        for cid in raw:
            s = rep["grades"].get(cid)
            if not s:
                continue
            score = s.get("score")
            if score is None:
                continue
            quote = (s.get("quote") or "").strip()
            spans = spans_of(ranch, f"{key}/{cid}")
            raw[cid].append({
                "key": key, "label": rep["label"], "model": rep["model"], "budget": rep["budget"],
                "rep": rep["rep"], "score": score, "quote": quote,
                "shown": " … ".join(spans) if spans else quote,
                "from_anchor": bool(spans),
                "reason": (s.get("reason") or "").strip(),
            })

    out_claims, n_exc = [], 0
    for c in claims:
        js = raw[c["id"]]
        full = [j for j in js if j["score"] >= 1.0]
        part = sorted([j for j in js if 0 < j["score"] < 1.0], key=lambda j: -j["score"])
        zero = [j for j in js if j["score"] == 0 and j["quote"]]
        groups = []
        for gid, title, note, cands in [
            ("full", "Judge gave full credit (1.0)", "The judge called these a match.", full),
            ("partial", "Judge gave partial credit", "The judge hedged: right area, something off.", part),
            ("zero", "Judge gave 0 but still quoted the report",
             "A quote with a 0 is the judge saying “this passage is the nearest thing and it is not enough”.", zero),
        ]:
            sel = pick(cands, PER_GROUP)
            n_exc += len(sel)
            groups.append({"id": gid, "title": title, "note": note,
                           "total": len(cands), "items": sel})
        if not any(g["items"] for g in groups):
            # No report was ever quoted for this claim. Show the judge's bare 0s so the
            # claim is still placeable — the reason is all the evidence there is.
            bare = [j for j in js if j["score"] == 0 and not j["quote"]]
            sel = pick(bare, PER_GROUP)
            n_exc += len(sel)
            groups.append({"id": "bare", "title": "Judge gave 0 with no quote at all",
                           "note": "No report was ever quoted for this claim, so the judge's reason is the whole "
                                   "of the evidence. Place these on how close the report came, not on the quote.",
                           "total": len(bare), "items": sel})
        dist = collections.Counter(j["score"] for j in js)
        out_claims.append({
            "id": c["id"], "section": c["section"], "claim": c["claim"],
            "report_quote": c["report_quote"], "rubric": c["rubric"],
            "n_reports": len(js), "max": max((j["score"] for j in js), default=0),
            "dist": sorted(dist.items(), key=lambda kv: -kv[0]),
            "groups": groups,
        })

    mx = {c["id"]: c["max"] for c in out_claims}
    summary = {
        "n_claims": len(out_claims), "n_reports": len(reports), "n_excerpts": n_exc,
        "with_full": sum(1 for v in mx.values() if v >= 1.0),
        "capped": sorted([[cid, v] for cid, v in mx.items() if 0 < v < 1.0], key=lambda kv: kv[0]),
        "never": sorted([cid for cid, v in mx.items() if v == 0]),
        "grader": next((r["grader"] for r in reports.values() if r["grader"]), ""),
    }

    data = {"claims": out_claims, "bands": [{"v": v, "text": t} for v, t in BANDS],
            "summary": summary, "save_path": str(SAVE_PATH), "per_group": PER_GROUP,
            "built": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", payload))
    print(f"{OUT}: {len(out_claims)} claims, {len(reports)} round-3 reports, {n_exc} excerpts, "
          f"{OUT.stat().st_size/1e6:.2f} MB")
    print(f"  {summary['with_full']}/{len(out_claims)} claims have a 1.0 somewhere; "
          f"capped: {', '.join(f'{c} at {v}' for c, v in summary['capped']) or 'none'}; "
          f"never above 0: {', '.join(summary['never']) or 'none'}")
    thin = [c["id"] for c in out_claims if sum(len(g["items"]) for g in c["groups"]) < 3]
    print(f"  claims with fewer than 3 excerpts: {', '.join(thin) or 'none'}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Match scale draft — MessageBoardAuditBench</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666666;--mut:#999999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok:#065F46;--warn-bg:#FEF3C7;--warn:#92400E;--dang-bg:#FEE2E2;--dang:#991B1B;--grey-bg:#ECEAE3;--grey:#555}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);font-size:13px;line-height:1.45;display:grid;grid-template-rows:auto 1fr;height:100vh;overflow:hidden}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
header{padding:7px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--card)}
h1{color:var(--accent);font-size:16px;margin:0;white-space:nowrap}
.sub{color:var(--mut);font-size:10.5px}
.stats{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto;align-items:center}
.badge{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--soft);color:var(--accent2);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.dang{background:var(--dang-bg);color:var(--dang)}.badge.grey{background:var(--grey-bg);color:var(--grey)}
#save{font-size:11px;color:var(--mut);min-width:160px;text-align:right}#save.err{color:var(--dang);font-weight:600}
button{font-family:inherit}
#sb-btn{padding:5px 9px;font-size:13px;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--ink2);cursor:pointer}
#layout{display:grid;grid-template-columns:300px 1fr;min-height:0}
#layout.collapsed{grid-template-columns:1fr}#layout.collapsed aside{display:none}
aside{border-right:1px solid var(--border);display:flex;flex-direction:column;min-height:0;background:var(--card)}
.search{margin:8px 8px 6px;padding:6px 9px;border:1px solid var(--border);border-radius:7px;font-size:12px;font-family:inherit}
#list{overflow:auto;flex:1;border-top:1px solid var(--border)}
.item{padding:7px 10px;border-bottom:1px solid var(--border);cursor:pointer;font-size:12px}
.item:hover{background:var(--row)}.item.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--accent)}
.item .nm{font-weight:600;display:flex;justify-content:space-between;gap:6px;align-items:baseline}
.item .nm .cid{color:var(--accent2);font-variant-numeric:tabular-nums}
.item .tx{color:var(--ink2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:2px}
.item .meta{color:var(--mut);font-size:10.5px;margin-top:3px;display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.pill{font-size:10px;font-weight:700;padding:0 6px;border-radius:20px;background:var(--grey-bg);color:var(--grey)}
.pill.spread{background:var(--ok-bg);color:var(--ok)}.pill.bunch{background:var(--warn-bg);color:var(--warn)}
.hint{font-size:10.5px;color:var(--mut);padding:7px 10px;border-top:1px solid var(--border);line-height:1.6}
kbd{font-family:inherit;background:var(--grey-bg);border-radius:3px;padding:0 4px;font-size:10px}
main{overflow:auto;min-height:0;padding:14px 18px 60px}
.wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px}
.card>h3{margin:0;padding:9px 14px;font-size:13px;color:var(--accent);border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:center;cursor:pointer}
.card>h3 .n{color:var(--mut);font-weight:400;font-size:11px}
.card>h3 .caret{margin-left:auto;color:var(--mut);font-size:11px}
.card .body{padding:12px 14px}
table.anchors{border-collapse:collapse;width:100%}
table.anchors td{border-top:1px solid var(--border);padding:5px 8px;vertical-align:top}
table.anchors tr:first-child td{border-top:none}
table.anchors td.v{width:52px;font-weight:800;color:var(--accent2);font-variant-numeric:tabular-nums;font-size:14px;text-align:right;padding-top:9px}
table.anchors textarea{width:100%;border:1px solid transparent;border-radius:6px;background:transparent;font:inherit;color:var(--ink);padding:5px 7px;resize:vertical;min-height:30px;overflow:hidden}
table.anchors textarea:hover{border-color:var(--border);background:var(--row)}
table.anchors textarea:focus{outline:none;border-color:var(--accent);background:#fff}
table.anchors tr.edited td.v::after{content:"·edited";display:block;font-size:9px;color:var(--mut);font-weight:400}
.note{font-size:11.5px;color:var(--ink2);margin:0 0 8px}
.claimhead .cid{font-size:11px;font-weight:800;color:var(--accent2);letter-spacing:.04em}
.claimhead .ct{font-size:15px;line-height:1.4;margin:3px 0 6px}
.claimhead .hq{font-size:12px;color:var(--ink2);border-left:3px solid var(--border);background:var(--row);padding:6px 10px;border-radius:0 6px 6px 0;white-space:pre-wrap}
.dist{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px;align-items:center;font-size:11px;color:var(--mut)}
.summ{font-size:12px;padding:8px 12px;border-radius:7px;background:var(--row);border:1px solid var(--border);margin-top:9px}
.summ b{color:var(--ink)}
.grp>h4{margin:0;padding:7px 14px;font-size:12px;border-bottom:1px solid var(--border);background:var(--row);border-radius:8px 8px 0 0;display:flex;gap:9px;align-items:baseline}
.grp>h4 .lab{font-weight:700}
.grp>h4 .n{color:var(--mut);font-weight:400;font-size:11px}
.grp .gnote{font-size:11px;color:var(--mut);padding:5px 14px 0}
.exs{display:flex;flex-direction:column}
.ex{border-top:1px solid var(--border);padding:10px 14px}
.ex:first-child{border-top:none}
.ex.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--accent)}
.ex .top{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;font-size:11px;color:var(--mut)}
.ex .top .rep{font-weight:600;color:var(--ink2)}
.ex .jq{margin:6px 0 0;font-size:12.5px;white-space:pre-wrap;border-left:3px solid var(--accent);background:var(--row);padding:7px 10px;border-radius:0 6px 6px 0;max-height:240px;overflow:auto}
.ex .why{margin:5px 0 0;font-size:11.5px;color:var(--ink2);font-style:italic}
.ex .noq{font-size:11.5px;color:var(--mut);font-style:italic;margin-top:6px}
.bands{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px;align-items:center}
.bands .lb{font-size:10.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;margin-right:2px}
.bands button{font-size:12px;font-weight:700;padding:2px 9px;border:1px solid var(--border);border-radius:20px;background:var(--card);color:var(--ink2);cursor:pointer;font-variant-numeric:tabular-nums}
.bands button:hover{border-color:var(--accent);color:var(--accent)}
.bands button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.bands .clr{font-weight:400;color:var(--mut);font-size:11px}
.cmt{width:100%;margin-top:6px;border:1px solid var(--border);border-radius:6px;background:var(--card);font:inherit;font-size:12px;padding:5px 8px;resize:vertical;min-height:28px}
.cmt:focus{outline:none;border-color:var(--accent)}
.cmt.has{background:#fff}
.jscore{font-weight:800;font-variant-numeric:tabular-nums;padding:1px 7px;border-radius:20px;font-size:11px}
.jscore.s1{background:var(--ok-bg);color:var(--ok)}.jscore.sp{background:var(--warn-bg);color:var(--warn)}.jscore.s0{background:var(--grey-bg);color:var(--grey)}
.delta{font-size:10.5px;font-weight:700;color:var(--accent2)}
.empty{padding:14px;color:var(--mut);font-size:12px}
</style></head><body>
<header>
  <button id="sb-btn" title="hide / show the claim list  ([)">&#9776;</button>
  <div><h1>Match scale draft</h1><div class="sub" id="built"></div></div>
  <div class="stats" id="stats"></div>
  <div id="save">loading&hellip;</div>
</header>
<div id="layout">
  <aside>
    <input class="search" id="q" placeholder="Search claims&hellip;">
    <div id="list"></div>
    <div class="hint"><b>Place each excerpt on the proposed scale.</b>
      <kbd>j</kbd>/<kbd>k</kbd> excerpt &middot; <kbd>1</kbd>&ndash;<kbd>7</kbd> band (1.0 &rarr; 0.0) &middot; <kbd>0</kbd> clear &middot;
      <kbd>c</kbd> comment &middot; <kbd>n</kbd>/<kbd>p</kbd> claim &middot; <kbd>[</kbd> hide list &middot; <kbd>Esc</kbd> leave box</div>
  </aside>
  <main id="main"><div class="wrap" id="wrap"></div></main>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const SAVE_PATH = D.save_path, LS_KEY = 'match_scale:' + SAVE_PATH, SB_KEY = 'match_scale:sidebar', AC_KEY = 'match_scale:anchors_open';
const CLAIMS = D.claims, CIDS = CLAIMS.map(c => c.id), CBY = Object.fromEntries(CLAIMS.map(c => [c.id, c]));
const BANDS = D.bands, BVALS = BANDS.map(b => b.v);

/* ---------- persistence (same mechanism as build_audit_ui.py) ---------- */
const MAPS = ['placements', 'anchors', 'notes'];
let state = {version: 1, updated_at: null, placements: {}, anchors: {}, notes: {}};
function blank(e) { return !e.band && !e.comment && !e.text && !e.note; }
function setIn(map, k, patch) {
  const e = Object.assign({}, state[map][k] || {}, patch, {updated_at: new Date().toISOString()});
  for (const key of Object.keys(e)) if (e[key] === null || e[key] === '' || e[key] === false) delete e[key];
  if (blank(e)) delete state[map][k]; else state[map][k] = e;
  scheduleSave();
}
function ekey(cid, rk) { return cid + '/' + rk; }
function place(cid, rk) { return state.placements[ekey(cid, rk)] || null; }
function setPlace(cid, rk, patch) { setIn('placements', ekey(cid, rk), patch); }
let saveTimer = null;
function setStatus(t, err) { const el = document.getElementById('save'); el.textContent = t; el.className = err ? 'err' : ''; }
function scheduleSave() { clearTimeout(saveTimer); setStatus('unsaved…'); saveTimer = setTimeout(saveNow, 500); }
async function saveNow() {
  state.updated_at = new Date().toISOString();
  const body = JSON.stringify(state, null, 1);
  try { localStorage.setItem(LS_KEY, body); } catch (e) {}
  try {
    const r = await fetch('/save?p=' + encodeURIComponent(SAVE_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    setStatus('saved to disk ' + new Date().toLocaleTimeString());
  } catch (e) { setStatus('NOT on disk (browser copy kept): ' + e.message, true); }
}
function merge(a, b) {
  const out = {version: 1, updated_at: null, placements: {}, anchors: {}, notes: {}};
  for (const src of [a, b]) { if (!src) continue;
    for (const map of MAPS) for (const [k, e] of Object.entries(src[map] || {})) {
      const cur = out[map][k]; if (!cur || (e.updated_at || '') > (cur.updated_at || '')) out[map][k] = e; } }
  return out;
}
function sameContent(a, b) { const s = x => JSON.stringify(MAPS.map(m => x[m] || {})); return s(a) === s(b); }
async function load() {
  let server = null, local = null;
  try { const r = await fetch('/file?p=' + encodeURIComponent(SAVE_PATH)); if (r.ok) server = await r.json(); } catch (e) {}
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = merge(server, local);
  const n = MAPS.reduce((t, m) => t + Object.keys(state[m]).length, 0);
  if (server === null && local === null) setStatus('nothing placed yet');
  else if (local && !sameContent(state, server || {})) scheduleSave();
  else setStatus('loaded ' + n + ' saved items (' + (server ? 'from disk' : 'browser copy only') + ')', !server);
}

/* ---------- helpers ---------- */
function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function fmt(x) { return Number(x).toFixed(1); }
function jclass(s) { return s >= 1 ? 's1' : s > 0 ? 'sp' : 's0'; }
function anchorText(i) { const e = state.anchors[BVALS[i]]; return (e && e.text) || BANDS[i].text; }
function excerptsOf(c) { const out = []; for (const g of c.groups) for (const it of g.items) out.push(it); return out; }
function placedStats(c) {
  const bands = {}; let n = 0;
  for (const it of excerptsOf(c)) { const p = place(c.id, it.key); if (p && p.band) { n++; bands[p.band] = (bands[p.band] || 0) + 1; } }
  const keys = Object.keys(bands);
  return {n: n, total: excerptsOf(c).length, bands: bands, distinct: keys.length};
}

/* ---------- sidebar ---------- */
let selClaim = CIDS[0], selEx = 0, query = '';
function filtered() {
  const q = query.trim().toLowerCase();
  if (!q) return CLAIMS;
  return CLAIMS.filter(c => (c.id + ' ' + c.section + ' ' + c.claim).toLowerCase().includes(q));
}
function renderList() {
  const el = document.getElementById('list');
  el.innerHTML = filtered().map(c => {
    const st = placedStats(c);
    let pill = '<span class="pill">' + st.total + ' excerpts</span>';
    if (st.n) {
      const cls = st.distinct >= 3 ? 'spread' : st.distinct === 1 ? 'bunch' : '';
      pill = '<span class="pill ' + cls + '">' + st.n + '/' + st.total + ' placed · ' + st.distinct + ' band' + (st.distinct === 1 ? '' : 's') + '</span>';
    }
    return '<div class="item' + (c.id === selClaim ? ' sel' : '') + '" data-cid="' + c.id + '">' +
      '<div class="nm"><span class="cid">' + c.id + '</span><span class="pill">max ' + fmt(c.max) + '</span></div>' +
      '<div class="tx">' + esc(c.claim) + '</div>' +
      '<div class="meta"><span>' + esc(c.section) + '</span>' + pill + '</div></div>';
  }).join('') || '<div class="empty">no claims match</div>';
  el.querySelectorAll('.item').forEach(n => n.onclick = () => { selClaim = n.dataset.cid; selEx = 0; renderList(); renderMain(); document.getElementById('main').scrollTop = 0; });
}

/* ---------- anchor table ---------- */
let anchorsOpen = true;
try { anchorsOpen = localStorage.getItem(AC_KEY) !== '0'; } catch (e) {}
function anchorTable() {
  const rows = BANDS.map((b, i) => {
    const edited = state.anchors[b.v] && state.anchors[b.v].text && state.anchors[b.v].text !== b.text;
    return '<tr class="' + (edited ? 'edited' : '') + '"><td class="v">' + b.v + '</td>' +
      '<td><textarea data-band="' + b.v + '" rows="1">' + esc(anchorText(i)) + '</textarea></td></tr>';
  }).join('');
  return '<div class="card" id="anchorcard"><h3 id="anchortog">Proposed scale <span class="n">behaviourally anchored, 0.1 steps — reword any row, edits are saved</span><span class="caret">' + (anchorsOpen ? '▾' : '▸') + '</span></h3>' +
    (anchorsOpen ? '<div class="body"><p class="note">Today the recall judge gives <b>0 / 0.5 / 1</b> and defines the bands structurally (is a specific wrong?). This proposal anchors them on what a reader would say about the overlap. Adapted from <code>commentbench</code> point-edge-coverage-v4.</p>' +
      '<table class="anchors">' + rows + '</table></div>' : '') + '</div>';
}
function wireAnchors() {
  const tog = document.getElementById('anchortog');
  if (tog) tog.onclick = () => { anchorsOpen = !anchorsOpen; try { localStorage.setItem(AC_KEY, anchorsOpen ? '1' : '0'); } catch (e) {} renderMain(); };
  document.querySelectorAll('table.anchors textarea').forEach(ta => {
    const grow = () => { ta.style.height = 'auto'; ta.style.height = (ta.scrollHeight + 2) + 'px'; };
    grow();
    ta.oninput = () => { grow(); const b = ta.dataset.band; const def = BANDS[BVALS.indexOf(b)].text;
      setIn('anchors', b, {text: ta.value === def ? '' : ta.value}); };
    ta.onkeydown = e => { if (e.key === 'Escape') ta.blur(); e.stopPropagation(); };
  });
}

/* ---------- main ---------- */
function excerptHTML(c, it, idx) {
  const p = place(c.id, it.key) || {};
  const btns = BANDS.map((b, i) => '<button data-band="' + b.v + '" class="' + (p.band === b.v ? 'on' : '') + '" title="' + esc(anchorText(i)) + '">' + b.v + '</button>').join('');
  const disagree = p.band != null && Math.abs(parseFloat(p.band) - it.score) >= 0.25
    ? '<span class="delta">moved ' + (parseFloat(p.band) > it.score ? '↑' : '↓') + ' from judge</span>' : '';
  return '<div class="ex' + (idx === selEx ? ' sel' : '') + '" data-i="' + idx + '" data-rk="' + esc(it.key) + '">' +
    '<div class="top"><span class="jscore ' + jclass(it.score) + '">judge ' + fmt(it.score) + '</span>' +
    '<span class="rep">' + esc(it.label) + '</span>' + (it.from_anchor ? '<span>validated span</span>' : '') + disagree + '</div>' +
    (it.shown ? '<div class="jq">' + esc(it.shown) + '</div>' : '<div class="noq">the judge quoted nothing from this report</div>') +
    (it.reason ? '<div class="why">' + esc(it.reason) + '</div>' : '') +
    '<div class="bands"><span class="lb">place</span>' + btns +
    '<button class="clr" data-band="">clear</button></div>' +
    '<textarea class="cmt' + (p.comment ? ' has' : '') + '" placeholder="why this band? what does the judge\'s score miss?" rows="1">' + esc(p.comment || '') + '</textarea>' +
    '</div>';
}
function renderMain() {
  const c = CBY[selClaim];
  const exs = excerptsOf(c);
  const st = placedStats(c);
  let summ;
  if (!st.n) summ = 'Nothing placed yet for this claim. ' + st.total + ' excerpts below.';
  else {
    const spread = Object.entries(st.bands).sort((a, b) => parseFloat(b[0]) - parseFloat(a[0])).map(([b, n]) => b + '×' + n).join(' · ');
    summ = '<b>' + st.n + ' of ' + st.total + ' placed</b> across <b>' + st.distinct + '</b> band' + (st.distinct === 1 ? '' : 's') + ': ' + spread +
      (st.distinct === 1 ? ' — <b>bunched</b>: the finer scale is buying nothing here.'
       : st.distinct >= 3 ? ' — <b>spread</b>: the finer scale is separating these.' : ' — two bands only.');
  }
  const dist = c.dist.map(([s, n]) => '<span class="jscore ' + jclass(s) + '">' + fmt(s) + ' ×' + n + '</span>').join(' ');
  let html = anchorTable();
  html += '<div class="card"><div class="body claimhead">' +
    '<div class="cid">' + c.id + ' · ' + esc(c.section) + ' · rubric ' + esc(c.rubric) + '</div>' +
    '<div class="ct">' + esc(c.claim) + '</div>' +
    (c.report_quote ? '<div class="hq">' + esc(c.report_quote) + '</div>' : '') +
    '<div class="dist"><span>judge over ' + c.n_reports + ' round-3 reports:</span>' + dist + '</div>' +
    '<div class="summ" id="summ">' + summ + '</div></div></div>';
  let i = 0;
  for (const g of c.groups) {
    if (!g.items.length) continue;
    html += '<div class="card grp"><h4><span class="lab">' + esc(g.title) + '</span>' +
      '<span class="n">showing ' + g.items.length + ' of ' + g.total + ', spread over models</span></h4>' +
      '<div class="gnote">' + esc(g.note) + '</div><div class="exs">' +
      g.items.map(it => excerptHTML(c, it, i++)).join('') + '</div></div>';
  }
  if (!exs.length) html += '<div class="card"><div class="empty">No report produced a quoted judgement for this claim.</div></div>';
  document.getElementById('wrap').innerHTML = html;
  wireAnchors();
  document.querySelectorAll('.ex').forEach(node => {
    const idx = +node.dataset.i, rk = node.dataset.rk;
    node.querySelectorAll('.bands button').forEach(b => b.onclick = ev => {
      ev.stopPropagation(); selEx = idx;
      setPlace(selClaim, rk, {band: b.dataset.band || null});
      renderMain(); renderList(); renderStats();
      const n = document.querySelector('.ex[data-i="' + idx + '"]'); if (n) n.scrollIntoView({block: 'nearest'});
    });
    const ta = node.querySelector('.cmt');
    const grow = () => { ta.style.height = 'auto'; ta.style.height = (ta.scrollHeight + 2) + 'px'; };
    grow();
    ta.oninput = () => { grow(); setPlace(selClaim, rk, {comment: ta.value}); };
    ta.onfocus = () => { selEx = idx; document.querySelectorAll('.ex.sel').forEach(n => n.classList.remove('sel')); node.classList.add('sel'); };
    ta.onkeydown = e => { if (e.key === 'Escape') ta.blur(); e.stopPropagation(); };
    node.onclick = () => { if (idx !== selEx) { selEx = idx; document.querySelectorAll('.ex.sel').forEach(n => n.classList.remove('sel')); node.classList.add('sel'); } };
  });
}
function renderStats() {
  const s = D.summary;
  let placed = 0, total = 0, bandsUsed = new Set(), bunched = 0, spread = 0;
  for (const c of CLAIMS) { const st = placedStats(c); placed += st.n; total += st.total;
    Object.keys(st.bands).forEach(b => bandsUsed.add(b));
    if (st.n >= 2 && st.distinct === 1) bunched++; if (st.distinct >= 3) spread++; }
  const capped = s.capped.map(([cid, v]) => cid + ' at ' + fmt(v)).join(', ');
  document.getElementById('stats').innerHTML =
    '<span class="badge ok">' + s.with_full + '/' + s.n_claims + ' claims hit 1.0</span>' +
    '<span class="badge warn">' + s.capped.length + ' top out below 1: ' + esc(capped) + '</span>' +
    '<span class="badge dang">' + s.never.length + ' never above 0: ' + esc(s.never.join(', ')) + '</span>' +
    '<span class="badge grey">' + placed + '/' + total + ' excerpts placed</span>' +
    (placed ? '<span class="badge ' + (spread > bunched ? 'ok' : 'warn') + '">' + spread + ' spread · ' + bunched + ' bunched</span>' : '');
}

/* ---------- keyboard ---------- */
function move(d) {
  const n = excerptsOf(CBY[selClaim]).length; if (!n) return;
  selEx = Math.max(0, Math.min(n - 1, selEx + d));
  document.querySelectorAll('.ex.sel').forEach(x => x.classList.remove('sel'));
  const node = document.querySelector('.ex[data-i="' + selEx + '"]');
  if (node) { node.classList.add('sel'); node.scrollIntoView({block: 'center', behavior: 'smooth'}); }
}
function moveClaim(d) {
  const list = filtered(); const i = list.findIndex(c => c.id === selClaim);
  const j = Math.max(0, Math.min(list.length - 1, (i < 0 ? 0 : i) + d));
  if (!list[j]) return;
  selClaim = list[j].id; selEx = 0; renderList(); renderMain(); document.getElementById('main').scrollTop = 0;
}
document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target.tagName;
  if (t === 'TEXTAREA' || t === 'INPUT') return;
  const exs = excerptsOf(CBY[selClaim]);
  if (e.key === 'j') { move(1); e.preventDefault(); }
  else if (e.key === 'k') { move(-1); e.preventDefault(); }
  else if (e.key === 'n') { moveClaim(1); e.preventDefault(); }
  else if (e.key === 'p') { moveClaim(-1); e.preventDefault(); }
  else if (e.key === '[') { toggleSidebar(); e.preventDefault(); }
  else if (e.key === 'c') { const n = document.querySelector('.ex[data-i="' + selEx + '"] .cmt'); if (n) { n.focus(); e.preventDefault(); } }
  else if (e.key === '0') { const it = exs[selEx]; if (it) { setPlace(selClaim, it.key, {band: null}); renderMain(); renderList(); renderStats(); } }
  else if (e.key >= '1' && e.key <= '7') {
    const it = exs[selEx]; const b = BANDS[+e.key - 1];
    if (it && b) { setPlace(selClaim, it.key, {band: b.v}); renderMain(); renderList(); renderStats();
      const node = document.querySelector('.ex[data-i="' + selEx + '"]'); if (node) node.scrollIntoView({block: 'nearest'}); }
  }
});

/* ---------- sidebar toggle ---------- */
let sbHidden = false;
try { sbHidden = localStorage.getItem(SB_KEY) === '1'; } catch (e) {}
function applySidebar() { document.getElementById('layout').classList.toggle('collapsed', sbHidden); }
function toggleSidebar() { sbHidden = !sbHidden; try { localStorage.setItem(SB_KEY, sbHidden ? '1' : '0'); } catch (e) {} applySidebar(); }
document.getElementById('sb-btn').onclick = toggleSidebar;
document.getElementById('q').oninput = e => { query = e.target.value; renderList(); };
document.getElementById('q').onkeydown = e => { if (e.key === 'Escape') e.target.blur(); e.stopPropagation(); };

document.getElementById('built').textContent =
  D.summary.n_claims + ' claims · ' + D.summary.n_reports + ' round-3 reports (graded on the current sheets) · ' +
  D.summary.n_excerpts + ' excerpts · judge ' + D.summary.grader + ' · built ' + D.built;
applySidebar();
load().then(() => { renderList(); renderMain(); renderStats(); });
</script>
</body></html>
'''

if __name__ == "__main__":
    build()
