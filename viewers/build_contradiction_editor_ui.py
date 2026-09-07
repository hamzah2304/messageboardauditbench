#!/usr/bin/env python3
"""Build viewers/contradiction_editor.html — review the contradiction rubric before it runs.

The contradiction rubric (benchmark/rubrics/build_contradiction.py, sheets contra_1..6.md)
scores the same 30 points as the recall rubric, but from 0 to -1.0, asking only whether the
report says something the point rules out. It has never been run, so there is nothing to
tune it against; this page exists so the wording can be argued over first.

Like the recall editor (viewers/build_rubric_editor_ui.py, which this deliberately mirrors)
the shared parts — six anchors, the instruction paragraph, the rules paragraph — are one
editable object each rather than six copies, and any sheet can be previewed and rewritten as
a whole document. It does one thing less on purpose: the point text and the human-report
quote are NOT editable here. build_contradiction.py copies both verbatim out of the recall
sheets so the two rubrics cannot drift apart, so an edit made here would either be lost on
the next build or split the two rubrics. Those fields are edited in rubric_editor.html.

There are no contradiction scores yet. What sits beside each point instead is what the recall
grading already knows, from the 76 round-3 grades in benchmark/graded/graded_r3b*.json: the
mean recall score, the share of reports scoring above 0, and the share scoring 1.0. A point
nearly every report states confidently is a point with more opportunity to contradict, which
is the signal worth having when deciding which anchors matter. It is labelled as recall
evidence throughout, because that is what it is.

Edits autosave as overrides against the generated original in
benchmark/rubric_review/contradiction_edits.json (through the html-viewer's POST /save, with
a localStorage mirror) under the keys scale/paras/flags/comments/sheets. An unedited field is
never written, so every field reverts individually.

The constants below mirror build_contradiction.py. The build asserts the assembled markdown
for all six sheets is byte-identical to the committed contra_N.md, so drift fails the build.
"""
import json, pathlib, sys, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, RUBRICS, GRADED, VIEWERS

OUT = VIEWERS / "contradiction_editor.html"
SIBLING = VIEWERS / "rubric_editor.html"
EDITS_PATH = ROOT / "benchmark" / "rubric_review" / "contradiction_edits.json"

# ---- mirrored verbatim from benchmark/rubrics/build_contradiction.py ----
SCALE = [
 ("0.0", "Nothing in the report conflicts with this point. A point the report never "
         "raises scores 0 — silence is not contradiction."),
 ("-0.3", "A detail differs — a number, a name, a date — but a reader would still come "
          "away with this point intact."),
 ("-0.5", "The report muddles the mechanism or the attribution. A reader would have to "
          "reconcile it against the point, and might not."),
 ("-0.7", "The report asserts something incompatible with this point on a matter that "
          "changes what happened."),
 ("-0.9", "The report denies this point, or asserts its opposite, and does so with "
          "confidence."),
 ("-1.0", "The report builds on the opposite of this point, so a reader who follows it "
          "is led somewhere false."),
]
INSTRUCTION = (
 "You are checking a model-written incident report for statements that **contradict** "
 "points taken from a human-written one. The human report is given in full below and is "
 "the reference. Score each of the {n} points below from 0 to -1.0, one decimal place, "
 "using the scale. This is not a recall check: you are not asking whether the report "
 "found the point, only whether it says something the point rules out.")
RULES = (
 "Count only clear conflicts of fact. Do **not** count a point the report is silent on, "
 "a claim the human report does not address (unverifiable is not contradicted), a "
 "difference of emphasis or wording, or a hedged statement offered as a possibility. A "
 "report that says less is not thereby more accurate — it simply scores 0 here, and its "
 "thinness shows up in the recall rubric instead. Where the report contradicts a point in "
 "one place and states it correctly in another, score the contradiction: a reader meets "
 "both.")
SCALE_HEADER = "| Score | The report… |"
KEEP_PREFIX = ("**Point:**", "**In the human report:**")


def point_md(p):
    """Mirrors point_md() in build_contradiction.py: the header, then the copied lines."""
    out = [f"## {p['id']} — {p['section']}", ""]
    for line in p["lines"]:
        out.append(line)
        out.append("")
    return "\n".join(out).rstrip()


def sheet_md(rid, pts, scale, instruction, rules):
    """Assemble one contradiction sheet. Mirrors sheet() in build_contradiction.py exactly."""
    ids = ", ".join(p["id"] for p in pts)
    head = [f"# Contradiction {rid} — {pts[0]['id']}–{pts[-1]['id']}", "",
            instruction.replace("{n}", str(len(pts))), "",
            SCALE_HEADER, "| ---: | --- |"]
    head += [f"| {v} | {t} |" for v, t in scale]
    head += ["", rules, ""]
    body = "\n\n".join(point_md(p) for p in pts)
    tail = ["", "---", "",
            "**Human incident report (reference):**", "", "{{HUMAN_REPORT}}", "",
            "**Model report under evaluation:**", "", "{{MODEL_REPORT}}", "",
            "---", "",
            'Return strict JSON only: {"rubric_id": "%s", "items": ['
            ' {"id": "<one of %s>", "score": <0 to -1.0, one decimal place>,'
            ' "quote": "<verbatim snippet from the model report that contradicts, or empty>",'
            ' "reason": "<one sentence naming the conflict, or why there is none>"}, ... ] }' % (rid, ids)]
    return "\n".join(head) + "\n" + body + "\n" + "\n".join(tail) + "\n"


# ---- the generated original the page edits against ----
# The point wording is not read from rubric_N.json but lifted out of the recall SHEET, the
# way build_contradiction.py lifts it, so the recall rubric's own overrides come along.
def strip_prefix(line, pre):
    return line[len(pre):].lstrip() if line.startswith(pre) else ""


sheets, points = [], []
for gi in range(1, 7):
    rub = json.loads((RUBRICS / f"rubric_{gi}.json").read_text())
    recall_md = (RUBRICS / f"rubric_{gi}.md").read_text()
    ids = []
    for c in rub["claims"]:
        cid = c["id"]
        block = recall_md.split(f"## {cid} — ")[1].split("\n## ")[0]
        lines = [l for l in block.split("\n") if l.startswith(KEEP_PREFIX)]
        points.append({
            "id": cid, "rubric": rub["rubric_id"], "section": c["section"],
            "lines": lines,
            "point": next((strip_prefix(l, "**Point:**") for l in lines
                           if l.startswith("**Point:**")), ""),
            "quote": next((strip_prefix(l, "**In the human report:**") for l in lines
                           if l.startswith("**In the human report:**")), ""),
        })
        ids.append(cid)
    sheets.append({"rubric_id": rub["rubric_id"], "ids": ids})

PBY = {p["id"]: p for p in points}

# ---- build-time check: the page mirrors the generator ----
mismatch = []
for s in sheets:
    got = sheet_md(s["rubric_id"], [PBY[i] for i in s["ids"]], SCALE, INSTRUCTION, RULES)
    want = (RUBRICS / f"contra_{s['rubric_id'][1:]}.md").read_text()
    if got != want:
        mismatch.append(s["rubric_id"])

# ---- recall evidence: the 76 round-3 grades. NOT contradiction evidence. ----
graded = sorted(GRADED.glob("graded_r3b*.json"))
per_report = []
for f in graded:
    sc = json.loads(f.read_text()).get("scores", {})
    row = {cid: v["score"] for cid, v in sc.items() if isinstance(v, dict) and v.get("score") is not None}
    if row:
        per_report.append(row)

ALL_IDS = [p["id"] for p in points]
stats = {}
for cid in ALL_IDS:
    xs = [row[cid] for row in per_report if cid in row]
    if not xs:
        stats[cid] = {"n": 0, "mean": None, "above0": None, "full": None}
        continue
    stats[cid] = {
        "n": len(xs),
        "mean": sum(xs) / len(xs),
        "above0": sum(1 for x in xs if x > 0) / len(xs),
        "full": sum(1 for x in xs if x >= 0.999) / len(xs),
    }
# Ranked by how often a report states the point at all: the more reports say something about
# it, the more chances there are for one of them to say something the point rules out.
ranked = sorted(ALL_IDS, key=lambda c: (stats[c]["above0"] is None,
                                        -(stats[c]["above0"] or 0), -(stats[c]["mean"] or 0)))
for i, cid in enumerate(ranked, 1):
    stats[cid]["rank"] = i

DATA = {
    "edits_path": str(EDITS_PATH),
    "sibling_url": "/file?p=" + str(SIBLING),
    "built": datetime.datetime.now().isoformat(timespec="seconds"),
    "n_reports": len(per_report),
    "scale_header": SCALE_HEADER,
    "original": {
        "scale": [{"score": v, "text": t} for v, t in SCALE],
        "instruction": INSTRUCTION,
        "rules": RULES,
        "points": points,
        "sheets": sheets,
    },
    "stats": stats,
    "ranked": ranked,
    "mismatch": mismatch,
}

if "--stats" in sys.argv:
    for cid in ranked:
        s = stats[cid]
        print(f"{cid} recall mean={s['mean']:.2f} >0={s['above0']:.2f} 1.0={s['full']:.2f} n={s['n']}")
    print("reports:", len(per_report), "mismatch:", mismatch)
    sys.exit(0)


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contradiction rubric editor — MessageBoardAuditBench</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666666;--mut:#999999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok:#065F46;--warn-bg:#FEF3C7;--warn:#92400E;--dang-bg:#FEE2E2;--dang:#991B1B;--grey-bg:#ECEAE3;--grey:#555;--mono:SFMono-Regular,Menlo,Consolas,Monaco,"Liberation Mono",monospace}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.6;display:grid;grid-template-rows:auto 1fr;height:100vh;overflow:hidden}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
header{padding:8px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--card)}
h1{color:var(--accent);font-size:17px;margin:0;white-space:nowrap}
.sub{color:var(--mut);font-size:11px}
.tabs{display:flex;gap:5px}
.tab,.btn{padding:5px 13px;border:1px solid var(--border);border-radius:7px;background:transparent;color:var(--ink2);cursor:pointer;font-weight:600;font-size:12.5px;font-family:inherit}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.right{margin-left:auto;display:flex;gap:8px;align-items:center}
#save{font-size:11px;color:var(--mut);min-width:150px;text-align:right}#save.err{color:var(--dang);font-weight:600}
#body{overflow:auto;min-height:0}
.wrap{max-width:1180px;margin:0 auto;padding:22px 28px 80px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:18px 22px;margin-bottom:18px}
.card h2{color:var(--accent);font-size:15px;margin:0 0 4px}
.card .why{color:var(--ink2);font-size:12.5px;margin:0 0 14px;max-width:70ch}
a{color:var(--accent)}
label.f{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:14px 0 4px;font-weight:700}
textarea,input[type=text]{width:100%;font-family:inherit;font-size:14px;line-height:1.6;color:var(--ink);background:var(--row);border:1px solid var(--border);border-radius:6px;padding:9px 11px;resize:vertical}
textarea:focus,input:focus{outline:none;border-color:var(--accent);background:#fff}
textarea{overflow:hidden;min-height:38px}
.edited{border-left:3px solid var(--accent)}
.rev{background:none;border:none;color:var(--accent);cursor:pointer;font-size:11px;font-family:inherit;padding:0 0 0 8px;text-decoration:underline}
.hint{font-size:11px;color:var(--mut)}
/* the scale runs 0 to -1.0: 0 is the clean end, and the ramp only ever darkens away from it */
.ramp{display:flex;align-items:center;gap:9px;font-size:11px;color:var(--ink2);margin:0 0 12px}
.ramp .bar{flex:1;height:9px;border-radius:5px;background:linear-gradient(90deg,#D1FAE5 0%,#FEF3C7 42%,#F8B4A6 72%,#991B1B 100%)}
.ramp b{font-family:var(--mono);font-size:12px}
table.scale{width:100%;border-collapse:collapse;margin-top:6px}
table.scale td{border-top:1px solid var(--border);padding:8px 6px;vertical-align:top}
table.scale td.sc{width:150px;white-space:nowrap}
table.scale input.sc{width:66px;text-align:right;font-weight:700;font-family:var(--mono);font-size:13px}
table.scale .sev{display:inline-block;vertical-align:middle;height:9px;width:64px;margin-left:7px;border-radius:5px;background:var(--grey-bg);overflow:hidden}
table.scale .sev i{display:block;height:100%}
table.scale td.act{width:96px;text-align:right;white-space:nowrap}
.mini{font-size:11px;padding:2px 7px;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--ink2);cursor:pointer;font-family:inherit}
.mini:hover{border-color:var(--accent);color:var(--accent)}
.mini.on{background:var(--soft);border-color:var(--accent);color:var(--accent2)}
.mini.dang:hover{border-color:var(--dang);color:var(--dang)}
#layout{display:grid;grid-template-columns:300px 1fr;height:100%;min-height:0}
aside{border-right:1px solid var(--border);background:var(--card);display:flex;flex-direction:column;min-height:0}
.sbtop{padding:9px 10px 6px;display:flex;flex-direction:column;gap:6px;border-bottom:1px solid var(--border)}
.sbtop input,.sbtop select{width:100%;font-size:12px;padding:5px 8px;border:1px solid var(--border);border-radius:6px;font-family:inherit;background:var(--row)}
.chips{display:flex;gap:4px;flex-wrap:wrap}
.chips button{font-size:11px;padding:1px 9px;border:1px solid var(--border);border-radius:20px;background:transparent;color:var(--ink2);cursor:pointer;font-family:inherit}
.chips button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#list{overflow:auto;flex:1}
.item{padding:7px 11px;border-bottom:1px solid var(--border);cursor:pointer;font-size:12.5px;line-height:1.35}
.item:hover{background:var(--row)}
.item.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--accent)}
.item .nm{font-weight:700;display:flex;justify-content:space-between;gap:6px;align-items:baseline}
.item .sec{color:var(--ink2);font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .d{font-family:var(--mono);font-size:11px;color:var(--ink2)}
.item .bar{height:3px;background:var(--grey-bg);border-radius:2px;margin-top:4px;overflow:hidden}
.item .bar i{display:block;height:100%;background:var(--accent)}
main#pmain{overflow:auto;min-height:0;padding:0}
.stats{display:flex;gap:0;border:1px solid var(--border);border-radius:8px;overflow:hidden;margin:2px 0 4px;background:var(--row)}
.stat{flex:1;padding:8px 12px;border-right:1px solid var(--border)}
.stat:last-child{border-right:none}
.stat .k{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);font-weight:700}
.stat .v{font-family:var(--mono);font-size:19px;font-weight:700;line-height:1.3}
.stat .n{font-size:11px;color:var(--mut)}
.stat.hot{background:var(--soft)}.stat.hot .v,.stat.hot .k{color:var(--accent2)}
.evlabel{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);font-weight:700;margin:14px 0 3px}
.badge{padding:1px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--soft);color:var(--accent2);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.dang{background:var(--dang-bg);color:var(--dang)}.badge.grey{background:var(--grey-bg);color:var(--grey)}
.ptitle{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;margin-bottom:2px}
.ptitle b{font-size:17px;color:var(--accent)}
.ro{background:var(--row);border:1px solid var(--border);border-left:3px solid var(--grey-bg);border-radius:0 6px 6px 0;padding:9px 12px;margin-top:4px}
pre.sheet{font-family:var(--mono);font-size:12px;line-height:1.55;white-space:pre-wrap;background:var(--row);border:1px solid var(--border);border-radius:8px;padding:16px 18px;margin:0}
.pv{display:grid;grid-template-columns:minmax(0,1fr) 430px;gap:16px;align-items:start}
textarea.doc{font-family:var(--mono);font-size:12px;line-height:1.55;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px 18px;min-height:420px;tab-size:2}
textarea.doc.ov{border-color:var(--accent);border-left-width:3px}
.side{position:sticky;top:0}
.side .card{padding:13px 15px;margin-bottom:12px}
.diff{font-family:var(--mono);font-size:11.5px;line-height:1.5;border:1px solid var(--border);border-radius:8px;overflow:auto;max-height:62vh;background:var(--card)}
.diff div{padding:1px 9px;white-space:pre-wrap;word-break:break-word}
.diff div.add{background:var(--ok-bg);color:var(--ok)}
.diff div.del{background:var(--dang-bg);color:var(--dang);text-decoration:line-through;text-decoration-color:rgba(153,27,27,.35)}
.diff div.ctx{color:var(--ink2)}
.diff div.skip{color:var(--mut);font-style:italic;background:var(--row);border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.warnbox{border:1px solid var(--warn);background:var(--warn-bg);border-radius:8px;padding:11px 14px;margin-bottom:12px;font-size:12.5px;color:var(--warn)}
.warnbox b{display:block;margin-bottom:3px}
.flagbox{border:1px solid var(--border);border-radius:8px;padding:10px 13px;margin-top:16px;background:var(--row)}
.flagbox.on{border-color:var(--warn);background:var(--warn-bg)}
.flagbox .hd{display:flex;gap:8px;align-items:center;font-weight:700;font-size:12.5px}
.note{font-size:12px;color:var(--ink2);background:var(--soft);border-left:3px solid var(--accent);padding:7px 11px;border-radius:0 6px 6px 0;margin:10px 0}
.note.grey{background:var(--row);border-color:var(--mut)}
.rank td{padding:3px 8px;border-top:1px solid var(--border);font-size:12.5px}
.rank td.n{font-family:var(--mono);text-align:right}
.rank tr:hover td{background:var(--soft);cursor:pointer}
</style></head>
<body>
<header>
  <h1>Contradiction rubric</h1>
  <div class="tabs">
    <button class="tab" data-tab="shared">Scale &amp; rules</button>
    <button class="tab" data-tab="points">Points (30)</button>
    <button class="tab" data-tab="preview">Sheet preview</button>
  </div>
  <div class="right">
    <button class="btn" id="ex-json">Copy JSON</button>
    <button class="btn" id="ex-md">Copy markdown</button>
    <div id="save">loading&hellip;</div>
  </div>
  <div class="sub" id="built"></div>
</header>
<div id="body"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const O = D.original, S = D.stats, EDITS_PATH = D.edits_path, LS_KEY = 'contradiction_edits:' + EDITS_PATH;
const PTS = O.points, PIDS = PTS.map(p => p.id), P0 = Object.fromEntries(PTS.map(p => [p.id, p]));
const MAPS = ['scale', 'paras', 'flags', 'comments', 'sheets'];

/* ---------- persistence (mechanism copied from build_rubric_editor_ui.py) ---------- */
function blankState() { const s = {version: 1, updated_at: null}; for (const m of MAPS) s[m] = {}; return s; }
let state = blankState();
function setIn(map, k, patch) {
  const e = Object.assign({}, state[map][k] || {}, patch, {updated_at: new Date().toISOString()});
  for (const key of Object.keys(e)) if (e[key] === undefined || e[key] === null) delete e[key];
  if (Object.keys(e).length <= 1) delete state[map][k]; else state[map][k] = e;
  scheduleSave();
}
let saveTimer = null;
function setStatus(t, err) { const el = document.getElementById('save'); el.textContent = t; el.className = err ? 'err' : ''; }
function scheduleSave() { clearTimeout(saveTimer); setStatus('unsaved…'); saveTimer = setTimeout(saveNow, 500); }
async function saveNow() {
  state.updated_at = new Date().toISOString();
  const body = JSON.stringify(state, null, 1);
  try { localStorage.setItem(LS_KEY, body); } catch (e) {}
  try {
    const r = await fetch('/save?p=' + encodeURIComponent(EDITS_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    setStatus('saved to disk ' + new Date().toLocaleTimeString());
  } catch (e) { setStatus('NOT on disk (browser copy kept): ' + e.message, true); }
}
function merge(a, b) {
  const out = blankState();
  for (const src of [a, b]) { if (!src) continue;
    for (const map of MAPS) for (const [k, e] of Object.entries(src[map] || {})) {
      const cur = out[map][k];
      if (!cur || (e.updated_at || '') > (cur.updated_at || '')) out[map][k] = e; } }
  return out;
}
function nEdits(s) { let n = 0; for (const m of MAPS) n += Object.keys(s[m] || {}).length; return n; }
function sameContent(a, b) { const f = x => JSON.stringify(MAPS.map(m => x[m] || {})); return f(a) === f(b); }
async function load() {
  let server = null, local = null;
  try { const r = await fetch('/file?p=' + encodeURIComponent(EDITS_PATH)); if (r.ok) server = await r.json(); } catch (e) {}
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = merge(server, local);
  if (server === null && local === null) setStatus('no saved edits yet');
  else if (local && !sameContent(state, server || {})) scheduleSave();
  else setStatus('loaded ' + nEdits(state) + ' saved edits (' + (server ? 'from disk' : 'browser copy only') + ')', !server);
  render();
}

/* ---------- current (original + overrides) ---------- */
function curScale() { const e = state.scale.bands; return e && e.bands ? e.bands : O.scale; }
function scaleEdited() { return !!(state.scale.bands && state.scale.bands.bands); }
function setScale(bands) { setIn('scale', 'bands', {bands: bands.map(b => ({score: b.score, text: b.text}))}); }
function curPara(k) { const e = state.paras[k]; return e && e.text !== undefined ? e.text : O[k]; }
function paraEdited(k) { const e = state.paras[k]; return !!(e && e.text !== undefined); }
function flag(id) { return state.flags[id] || null; }
function isFlagged(id) { const f = flag(id); return !!(f && f.uncontradictable); }
function cmt(k) { const e = state.comments[k]; return e && e.text ? e.text : ''; }

/* ---------- sheet assembly (mirrors build_contradiction.py) ---------- */
function pointMd(p) {
  const out = ['## ' + p.id + ' — ' + p.section, ''];
  for (const line of p.lines) { out.push(line); out.push(''); }
  return out.join('\n').replace(/\s+$/, '');
}
function sheetIds(rid, omitFlagged) {
  const sh = O.sheets.find(s => s.rubric_id === rid);
  return sh.ids.filter(i => !(omitFlagged && isFlagged(i)));
}
function sheetMd(rid, omitFlagged) {
  const ids = sheetIds(rid, omitFlagged);
  if (!ids.length) return '(every point on ' + rid + ' is flagged as impossible to contradict)\n';
  const pts = ids.map(i => P0[i]), idlist = ids.join(', ');
  const head = ['# Contradiction ' + rid + ' — ' + ids[0] + '–' + ids[ids.length - 1], '',
                curPara('instruction').replace('{n}', String(ids.length)), '',
                D.scale_header, '| ---: | --- |'];
  for (const b of curScale()) head.push('| ' + b.score + ' | ' + b.text + ' |');
  head.push('', curPara('rules'), '');
  const body = pts.map(pointMd).join('\n\n');
  const tail = ['', '---', '', '**Human incident report (reference):**', '', '{{HUMAN_REPORT}}', '',
                '**Model report under evaluation:**', '', '{{MODEL_REPORT}}', '', '---', '',
                'Return strict JSON only: {"rubric_id": "' + rid + '", "items": [ {"id": "<one of ' + idlist +
                '>", "score": <0 to -1.0, one decimal place>, "quote": "<verbatim snippet from the model report ' +
                'that contradicts, or empty>", "reason": "<one sentence naming the conflict, or why there is none>"}, ... ] }'];
  return head.join('\n') + '\n' + body + '\n' + tail.join('\n') + '\n';
}

/* ---------- direct sheet overrides ----------
   Two sources of truth, exactly as in the recall editor. Until a sheet is edited as a
   document it is assembled live from the fields; the moment it carries an override that
   text IS the sheet and the field edits stop reaching it. Typing the generated text back
   drops the override. */
function sheetOverride(rid) { const e = state.sheets[rid]; return e && e.text !== undefined ? e.text : null; }
function sheetText(rid) { const o = sheetOverride(rid); return o === null ? sheetMd(rid, omitFlagged) : o; }
function setSheet(rid, text) {
  if (text === sheetMd(rid, omitFlagged)) { delete state.sheets[rid]; scheduleSave(); }
  else setIn('sheets', rid, {text: text});
}
function clearSheet(rid) { delete state.sheets[rid]; scheduleSave(); }

/* line diff (LCS) between the generated sheet and the edited one */
function lineDiff(a, b) {
  const A = a.split('\n'), B = b.split('\n'), n = A.length, m = B.length;
  const dp = []; for (let i = 0; i <= n; i++) dp.push(new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { out.push({t: ' ', s: A[i]}); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({t: '-', s: A[i]}); i++; }
    else { out.push({t: '+', s: B[j]}); j++; }
  }
  while (i < n) out.push({t: '-', s: A[i++]});
  while (j < m) out.push({t: '+', s: B[j++]});
  return out;
}
function diffHTML(gen, cur) {
  const d = lineDiff(gen, cur), CTX = 2;
  const keep = d.map((x, i) => x.t !== ' ' || d.slice(Math.max(0, i - CTX), i + CTX + 1).some(y => y.t !== ' '));
  if (!d.some(x => x.t !== ' ')) return '<div class="diff"><div class="ctx">no differences — identical to the generated sheet</div></div>';
  let h = '<div class="diff">', run = 0;
  d.forEach((x, i) => {
    if (!keep[i]) { run++; return; }
    if (run) { h += '<div class="skip">… ' + run + ' unchanged line' + (run === 1 ? '' : 's') + '</div>'; run = 0; }
    const cls = x.t === '+' ? 'add' : x.t === '-' ? 'del' : 'ctx';
    h += '<div class="' + cls + '">' + esc(x.t + ' ' + x.s) + '</div>';
  });
  if (run) h += '<div class="skip">… ' + run + ' unchanged line' + (run === 1 ? '' : 's') + '</div>';
  return h + '</div>';
}
function diffCounts(gen, cur) {
  const d = lineDiff(gen, cur);
  return {add: d.filter(x => x.t === '+').length, del: d.filter(x => x.t === '-').length};
}
/* the scale table lives in every sheet; a direct edit to it only changes that one copy */
function scaleFromText(t) {
  const lines = t.split('\n'), hi = lines.indexOf(D.scale_header);
  if (hi < 0 || !/^\|\s*-+:?\s*\|\s*-+:?\s*\|$/.test(lines[hi + 1] || '')) return null;
  const out = [];
  for (let i = hi + 2; i < lines.length; i++) {
    const m = /^\|\s*([^|]*?)\s*\|\s*(.*?)\s*\|$/.exec(lines[i]);
    if (!m) break;
    out.push({score: m[1], text: m[2]});
  }
  return out.length ? out : null;
}
function sameScale(a, b) {
  return !!a && !!b && JSON.stringify(a.map(x => [x.score, x.text])) === JSON.stringify(b.map(x => [x.score, x.text]));
}

/* ---------- export ---------- */
function exportJSON() {
  const FL = {};
  for (const id of PIDS) if (isFlagged(id)) FL[id] = flag(id).reason || '';
  const comments = {};
  for (const [k, v] of Object.entries(state.comments)) if (v.text) comments[k] = v.text;
  return JSON.stringify({
    generated: new Date().toISOString(),
    source: 'viewers/contradiction_editor.html — paste the constants back into benchmark/rubrics/build_contradiction.py',
    scale_direction: '0 is clean, -1.0 is the worst; the point text and quote are owned by the recall rubric',
    instruction: curPara('instruction'), rules: curPara('rules'),
    SCALE: curScale().map(b => [b.score, b.text]),
    flagged_uncontradictable: FL, comments: comments,
    sheet_overrides: Object.fromEntries(O.sheets.map(s => [s.rubric_id, sheetOverride(s.rubric_id)])
                                               .filter(e => e[1] !== null)),
    points: PIDS.map(id => ({id: id, rubric: P0[id].rubric, section: P0[id].section,
                             point: P0[id].point, report_quote: P0[id].quote,
                             uncontradictable: isFlagged(id), comment: cmt(id) || undefined,
                             recall_stats: S[id]})),
  }, null, 1);
}
function exportMD() { return O.sheets.map(s => sheetText(s.rubric_id)).join('\n\n\n'); }
function toast(msg) {
  let t = document.getElementById('toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#1A1A1A;color:#fff;' +
      'padding:8px 16px;border-radius:7px;font-size:12.5px;z-index:9;opacity:.95';
    document.body.appendChild(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 2200);
}
async function copy(text, label) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta);
    ta.select(); try { document.execCommand('copy'); } catch (e2) {} ta.remove();
  }
  toast(label + ' copied to clipboard (' + text.length.toLocaleString() + ' chars)');
}

/* ---------- helpers ---------- */
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])); }
function pct(v) { return v == null ? '—' : Math.round(v * 100) + '%'; }
/* severity of a band: 0 at the clean end, 1 at the worst. Colour only ever darkens away
   from 0, so nobody reads the table as "bigger is better". */
function sev(score) { const v = Math.abs(parseFloat(score)); return isFinite(v) ? Math.min(1, v) : 0; }
function sevColor(score) {
  const v = sev(score);
  if (v === 0) return 'var(--ok)';
  if (v < 0.4) return '#B98A2E';
  if (v < 0.6) return '#C7793C';
  if (v < 0.8) return '#B85B33';
  return 'var(--dang)';
}
function fit(t) { t.style.height = 'auto'; t.style.height = (t.scrollHeight + 2) + 'px'; }
function fitAll(root) { (root || document).querySelectorAll('textarea').forEach(fit); }
function bindTA(el, onInput) {
  el.addEventListener('input', () => { fit(el); onInput(el.value); });
  fit(el);
}

/* ---------- view state ---------- */
let tab = 'shared', sel = PIDS[0], sheetSel = 'R1', omitFlagged = true;
let sort = 'above0_desc', filt = 'all', q = '';
const openNotes = new Set();
const bodyEl = document.getElementById('body');

document.getElementById('built').textContent =
  PIDS.length + ' points · 6 sheets · 0 to −1.0 · never run yet · built ' + D.built +
  (D.mismatch.length ? ' · WARNING: assembled sheets differ from ' + D.mismatch.join(', ') + '.md' : '');

/* ---------- scale & rules ---------- */
function renderShared() {
  const bands = curScale();
  let h = '<div class="wrap">';
  h += '<div class="card"><h2>The anchors — one object, printed on all six sheets</h2>' +
    '<p class="why">This rubric runs from <b>0 to −1.0</b> and only ever subtracts. ' +
    '<b>0.0 is the good end</b>: a report that says nothing wrong scores 0 on every point, and so does a ' +
    'report that says nothing at all. Each band is defined by what a reader would come away believing, ' +
    'not by counting errors. Every sheet R1–R6 repeats this table verbatim, so editing it once here ' +
    'changes all six.</p>' +
    '<div class="ramp"><b>0.0</b> nothing conflicts<div class="bar"></div>' +
    'a reader is led somewhere false <b>−1.0</b></div>' +
    '<table class="scale"><tbody>';
  bands.forEach((b, i) => {
    const s = sev(b.score);
    h += '<tr><td class="sc"><input class="sc" type="text" data-band-score="' + i + '" value="' + esc(b.score) + '">' +
      '<span class="sev"><i style="width:' + Math.round(Math.max(s, 0.04) * 100) + '%;background:' + sevColor(b.score) + '"></i></span></td>' +
      '<td><textarea data-band-text="' + i + '"></textarea></td>' +
      '<td class="act"><button class="mini' + (cmt('band:' + b.score) ? ' on' : '') + '" data-band-cmt="' + i + '">note</button> ' +
      '<button class="mini dang" data-band-del="' + i + '">remove</button></td></tr>';
    const c = cmt('band:' + b.score);
    if (c || openNotes.has('band:' + i)) h += '<tr><td></td><td colspan="2"><label class="f">Comment on this band</label>' +
      '<textarea data-cmt="band:' + b.score + '"></textarea></td></tr>';
  });
  h += '</tbody></table>' +
    '<p><button class="mini" id="band-add">+ add a band</button>' +
    (scaleEdited() ? ' <button class="rev" id="scale-revert">revert the whole scale to the generated original</button>' : '') +
    '</p>' +
    '<label class="f">Comment on the scale as a whole</label><textarea data-cmt="scale"></textarea></div>';

  h += paraCard('instruction', 'Instruction paragraph',
    'Opens every sheet, and carries the one distinction the whole rubric rests on: this is not a recall check. ' +
    '<code>{n}</code> is replaced by the number of points on that sheet.');
  h += paraCard('rules', 'The rules paragraph',
    'Printed under the table on every sheet. It is what stops the rubric punishing silence: a point the report ' +
    'never touches, a claim the human report does not address, a difference of wording, a hedge — none of those ' +
    'count, and a thin report is not thereby an accurate one.');

  h += '<div class="card"><h2>Where there is most to contradict</h2>' +
    '<p class="why"><b>Recall evidence, not contradiction evidence.</b> No report has been graded for ' +
    'contradiction yet. What is known is how the same 30 points scored for recall across ' + D.n_reports +
    ' round-3 reports. A point that nearly every report states, and states fully, is a point reports are ' +
    'willing to commit to — and therefore one with the most room to say something it rules out. A point ' +
    'almost nobody states can still be contradicted, so read this as where to look first, not as a ranking ' +
    'of risk. Click a row to open that point.</p>' +
    '<table class="rank" style="width:100%;border-collapse:collapse"><tbody>' +
    '<tr><td class="n" style="width:34px"></td><td style="width:52px"></td><td style="width:58px"></td><td></td>' +
    '<td class="n hint" style="width:70px">recall mean</td><td class="n hint" style="width:70px">stated</td>' +
    '<td class="n hint" style="width:70px">full marks</td></tr>';
  D.ranked.forEach((id, i) => {
    const s = S[id], p = P0[id];
    h += '<tr data-go="' + id + '">' +
      '<td class="n" style="width:34px;color:var(--mut)">' + (i + 1) + '</td>' +
      '<td style="width:52px;font-weight:700">' + id + '</td>' +
      '<td style="width:58px;color:var(--mut)">' + p.rubric + '</td>' +
      '<td>' + esc(p.section) + (isFlagged(id) ? ' <span class="badge warn">cannot be contradicted</span>' : '') + '</td>' +
      '<td class="n">' + (s.mean == null ? '—' : s.mean.toFixed(2)) + '</td>' +
      '<td class="n" style="font-weight:700">' + pct(s.above0) + '</td>' +
      '<td class="n">' + pct(s.full) + '</td></tr>';
  });
  h += '</tbody></table></div></div>';
  bodyEl.innerHTML = h;

  bands.forEach((b, i) => {
    const t = bodyEl.querySelector('[data-band-text="' + i + '"]');
    t.value = b.text;
    bindTA(t, v => { const nb = curScale().map(x => ({score: x.score, text: x.text})); nb[i].text = v; setScale(nb); });
    const sc = bodyEl.querySelector('[data-band-score="' + i + '"]');
    sc.addEventListener('input', () => { const nb = curScale().map(x => ({score: x.score, text: x.text})); nb[i].score = sc.value; setScale(nb); });
    bodyEl.querySelector('[data-band-del="' + i + '"]').onclick = () => {
      const nb = curScale().filter((x, j) => j !== i); setScale(nb); renderShared(); };
    bodyEl.querySelector('[data-band-cmt="' + i + '"]').onclick = () => {
      const k = 'band:' + i; if (openNotes.has(k)) openNotes.delete(k); else openNotes.add(k); renderShared(); };
  });
  const add = bodyEl.querySelector('#band-add');
  if (add) add.onclick = () => { const nb = curScale().map(x => ({score: x.score, text: x.text})); nb.push({score: '0.0', text: ''}); setScale(nb); renderShared(); };
  const rv = bodyEl.querySelector('#scale-revert');
  if (rv) rv.onclick = () => { delete state.scale.bands; scheduleSave(); renderShared(); };
  wireParas(); wireComments();
  bodyEl.querySelectorAll('[data-go]').forEach(tr => tr.onclick = () => { sel = tr.dataset.go; tab = 'points'; render(); });
  fitAll(bodyEl);
}
function paraCard(k, title, why) {
  return '<div class="card"><h2>' + title + '</h2><p class="why">' + why +
    (paraEdited(k) ? ' <button class="rev" data-para-rev="' + k + '">revert to original</button>' : '') +
    '</p><textarea data-para="' + k + '" class="' + (paraEdited(k) ? 'edited' : '') + '"></textarea>' +
    '<label class="f">Comment</label><textarea data-cmt="para:' + k + '"></textarea></div>';
}
function wireParas() {
  bodyEl.querySelectorAll('[data-para]').forEach(t => {
    const k = t.dataset.para; t.value = curPara(k);
    bindTA(t, v => { if (v === O[k]) { delete state.paras[k]; scheduleSave(); } else setIn('paras', k, {text: v}); });
  });
  bodyEl.querySelectorAll('[data-para-rev]').forEach(b => b.onclick = () => { delete state.paras[b.dataset.paraRev]; scheduleSave(); renderShared(); });
}
function wireComments() {
  bodyEl.querySelectorAll('[data-cmt]').forEach(t => {
    const k = t.dataset.cmt; t.value = cmt(k); t.placeholder = 'a note to yourself…';
    bindTA(t, v => setIn('comments', k, {text: v || undefined}));
  });
}

/* ---------- points ---------- */
function listIds() {
  let ids = PIDS.slice();
  if (filt === 'flagged') ids = ids.filter(isFlagged);
  else if (filt === 'noted') ids = ids.filter(i => isFlagged(i) || cmt(i));
  else if (filt === 'stated') ids = ids.filter(i => S[i].above0 != null && S[i].above0 >= 0.8);
  if (q) { const s = q.toLowerCase();
    ids = ids.filter(i => (i + ' ' + P0[i].section + ' ' + P0[i].point + ' ' + P0[i].quote).toLowerCase().includes(s)); }
  const by = {
    above0_desc: (a, b) => (S[b].above0 || 0) - (S[a].above0 || 0),
    above0_asc: (a, b) => (S[a].above0 || 0) - (S[b].above0 || 0),
    mean_desc: (a, b) => (S[b].mean || 0) - (S[a].mean || 0),
    full_desc: (a, b) => (S[b].full || 0) - (S[a].full || 0),
    id: (a, b) => a.localeCompare(b),
  }[sort];
  return ids.sort(by);
}
function renderPoints() {
  const ids = listIds();
  if (!ids.includes(sel) && ids.length) sel = ids[0];
  let h = '<div id="layout"><aside><div class="sbtop">' +
    '<input type="text" id="q" placeholder="search 30 points…" value="' + esc(q) + '">' +
    '<select id="sort">' +
    [['above0_desc', 'most often stated first'], ['above0_asc', 'least often stated first'],
     ['mean_desc', 'highest recall mean first'], ['full_desc', 'most often full marks first'],
     ['id', 'report order (C01…C30)']].map(o =>
      '<option value="' + o[0] + '"' + (sort === o[0] ? ' selected' : '') + '>' + o[1] + '</option>').join('') +
    '</select><div class="chips">' +
    [['all', 'all'], ['stated', 'stated by ≥80%'], ['flagged', 'cannot contradict'], ['noted', 'noted']].map(f =>
      '<button data-filt="' + f[0] + '" class="' + (filt === f[0] ? 'on' : '') + '">' + f[1] + '</button>').join('') +
    '</div></div><div id="list">';
  ids.forEach(id => {
    const s = S[id], p = P0[id], a = s.above0 == null ? 0 : s.above0;
    h += '<div class="item' + (id === sel ? ' sel' : '') + '" data-id="' + id + '">' +
      '<div class="nm"><span>' + id + (isFlagged(id) ? ' <span class="badge warn">no-contra</span>' : '') +
      (cmt(id) ? ' <span class="badge">noted</span>' : '') + '</span>' +
      '<span class="d">' + pct(s.above0) + ' stated</span></div>' +
      '<div class="sec">' + p.rubric + ' · ' + esc(p.section) + '</div>' +
      '<div class="bar"><i style="width:' + Math.round(a * 100) + '%"></i></div></div>';
  });
  h += '</div></aside><main id="pmain">' + (ids.length ? pointHTML(sel) : '<div class="wrap">Nothing matches.</div>') + '</main></div>';
  bodyEl.innerHTML = h;
  bodyEl.querySelector('#q').addEventListener('input', e => { q = e.target.value; renderPoints(); bodyEl.querySelector('#q').focus(); });
  bodyEl.querySelector('#sort').onchange = e => { sort = e.target.value; renderPoints(); };
  bodyEl.querySelectorAll('[data-filt]').forEach(b => b.onclick = () => { filt = b.dataset.filt; renderPoints(); });
  bodyEl.querySelectorAll('.item').forEach(it => it.onclick = () => { sel = it.dataset.id; renderPoints(); });
  if (ids.length) wirePoint(sel);
  fitAll(bodyEl);
}
function statHTML(id) {
  const s = S[id];
  return '<div class="evlabel">Recall evidence — how this point scored in the recall rubric, over ' +
    D.n_reports + ' round-3 reports. No contradiction grades exist yet.</div><div class="stats">' +
    '<div class="stat"><div class="k">recall mean</div><div class="v">' + (s.mean == null ? '—' : s.mean.toFixed(2)) +
    '</div><div class="n">0 to 1, over ' + s.n + ' reports</div></div>' +
    '<div class="stat' + (s.above0 >= 0.8 ? ' hot' : '') + '"><div class="k">stated at all</div><div class="v">' + pct(s.above0) +
    '</div><div class="n">' + Math.round((s.above0 || 0) * s.n) + ' of ' + s.n + ' scored above 0</div></div>' +
    '<div class="stat' + (s.full >= 0.5 ? ' hot' : '') + '"><div class="k">stated in full</div><div class="v">' + pct(s.full) +
    '</div><div class="n">' + Math.round((s.full || 0) * s.n) + ' of ' + s.n + ' scored 1.0</div></div></div>';
}
function opportunityNote(id) {
  const s = S[id];
  if (s.above0 == null) return '';
  if (s.above0 >= 0.9) return '<div class="note"><b>Nearly every report commits to this.</b> ' +
    pct(s.above0) + ' say something about it, ' + pct(s.full) + ' state it in full. Reports are confident here, ' +
    'so this is where a confident wrong version is most likely to appear — the −0.7 and −0.9 anchors carry the ' +
    'weight for this point.</div>';
  if (s.above0 <= 0.25) return '<div class="note grey"><b>Rarely stated.</b> Only ' + pct(s.above0) +
    ' of reports say anything about it, so most reports will score 0 here by silence. That is the correct ' +
    'outcome, not a failure of the rubric — but check the point can be contradicted at all before keeping it.</div>';
  return '';
}
function pointHTML(id) {
  const p = P0[id], fl = flag(id);
  let h = '<div class="wrap"><div class="ptitle"><b>' + id + '</b>' +
    '<span class="badge grey">' + p.rubric + '</span><span>' + esc(p.section) + '</span>' +
    (isFlagged(id) ? '<span class="badge warn">cannot be contradicted</span>' : '') +
    (cmt(id) ? '<span class="badge">noted</span>' : '') + '</div>';
  h += statHTML(id) + opportunityNote(id);
  h += '<div class="card"><h2>The point — owned by the recall rubric</h2>' +
    '<p class="why">Not editable here. <code>build_contradiction.py</code> copies both of these lines verbatim ' +
    'out of the recall sheet so the two rubrics cannot drift apart; an edit made on this page would be ' +
    'overwritten by the next build, or worse, split the two. Reword them in ' +
    '<a href="' + esc(D.sibling_url) + '">rubric_editor.html</a> and rebuild.</p>' +
    '<label class="f">Point</label><div class="ro">' + esc(p.point) + '</div>' +
    '<label class="f">In the human report</label><div class="ro">' + esc(p.quote) + '</div>' +
    '<div class="flagbox' + (isFlagged(id) ? ' on' : '') + '"><div class="hd"><label style="font-weight:700">' +
    '<input type="checkbox" id="flagck"' + (isFlagged(id) ? ' checked' : '') + '> this point cannot meaningfully be contradicted</label></div>' +
    '<div class="hint">For a point so hedged, so broad, or so unfalsifiable that no report could conflict with it — ' +
    'it would score 0 for every report and measure nothing. The point stays in the data; it is marked, dropped ' +
    'from the assembled sheets in the preview, and listed under <code>flagged_uncontradictable</code> in the JSON ' +
    'export. It is not dropped from the recall rubric, where it may still be worth scoring.</div>' +
    '<input type="text" id="flagwhy" placeholder="why — e.g. the point is itself a hedge, so nothing can conflict with it" ' +
    'style="margin-top:7px" value="' + esc(fl && fl.reason || '') + '"></div>' +
    '<label class="f">Comment on this point</label><textarea data-cmt="' + id + '"></textarea>' +
    '</div>';
  h += '<div class="card"><h2>As the judge sees it</h2>' +
    '<p class="why">The block for this point on the contradiction sheet. Everything else on the sheet — the ' +
    'instruction, the table, the rules — is shared and edited on the first tab.</p>' +
    '<pre class="sheet">' + esc(pointMd(p)) + '</pre></div></div>';
  return h;
}
function wirePoint(id) {
  const ck = bodyEl.querySelector('#flagck'), why = bodyEl.querySelector('#flagwhy');
  ck.onchange = () => { setIn('flags', id, {uncontradictable: ck.checked || undefined, reason: why.value || undefined}); renderPoints(); };
  why.addEventListener('input', () => setIn('flags', id, {uncontradictable: ck.checked || undefined, reason: why.value || undefined}));
  wireComments();
}

/* ---------- preview: the sheet as an editable document ---------- */
function renderPreview() {
  const rid = sheetSel, omitted = O.sheets.flatMap(x => x.ids).filter(isFlagged);
  const ov = sheetOverride(rid);
  let h = '<div class="wrap"><div class="card"><h2>The sheet the judge receives — editable</h2>' +
    '<p class="why">The whole assembled sheet, as <code>build_contradiction.py</code> writes ' +
    '<code>contra_N.md</code>. Edit it here as a document, in prose. With no edits anywhere it is ' +
    'byte-identical to the file on disk.</p>' +
    '<div class="chips" style="margin-bottom:10px">' +
    O.sheets.map(x => '<button data-sheet="' + x.rubric_id + '" class="' + (sheetSel === x.rubric_id ? 'on' : '') + '">' +
      x.rubric_id + ' · ' + x.ids[0] + '–' + x.ids[x.ids.length - 1] +
      (sheetOverride(x.rubric_id) !== null ? ' ✎' : '') + '</button>').join('') +
    '</div><label class="hint"><input type="checkbox" id="omit"' + (omitFlagged ? ' checked' : '') + '> ' +
    'leave out points flagged as impossible to contradict' + (omitted.length ? ' (' + omitted.length + ' flagged: ' + omitted.join(', ') + ')' : '') +
    (ov !== null ? ' — does not affect ' + rid + ' while it is edited directly' : '') + '</label></div>' +
    '<div class="pv"><div><textarea class="doc' + (ov !== null ? ' ov' : '') + '" id="doc" spellcheck="false"></textarea></div>' +
    '<div class="side" id="side"></div></div></div>';
  bodyEl.innerHTML = h;
  const doc = bodyEl.querySelector('#doc');
  doc.value = sheetText(rid);
  fit(doc);
  doc.addEventListener('input', () => { fit(doc); setSheet(rid, doc.value); renderSide(); });
  bodyEl.querySelectorAll('[data-sheet]').forEach(b => b.onclick = () => { sheetSel = b.dataset.sheet; renderPreview(); });
  bodyEl.querySelector('#omit').onchange = e => { omitFlagged = e.target.checked; renderPreview(); };
  renderSide();
}
/* the panel beside the document: which source of truth is live, the diff, the scale warning */
function renderSide() {
  const rid = sheetSel, ov = sheetOverride(rid), gen = sheetMd(rid, omitFlagged), side = bodyEl.querySelector('#side');
  let h = '';
  if (ov === null) {
    h += '<div class="card"><h2>Tracking the fields</h2><p class="why" style="margin:0">' +
      'This sheet is assembled live from the shared anchors, the two paragraphs and the points. ' +
      'Anything you change on the other two tabs shows up here. Type in the document to take it over.</p></div>';
  } else {
    const c = diffCounts(gen, ov);
    h += '<div class="card" style="border-color:var(--accent)"><h2>Edited directly</h2>' +
      '<p class="why">' + rid + ' is now this text. <b>Edits made on the Scale &amp; rules tab and the ' +
      'Points tab will no longer appear in it.</b> The other five sheets still track the fields.</p>' +
      '<div><span class="badge ok">+' + c.add + '</span> <span class="badge dang">-' + c.del + '</span> ' +
      '<span class="hint">lines against the generated sheet</span></div>' +
      '<p style="margin:10px 0 0"><button class="mini dang" id="sheet-revert">revert ' + rid + ' to generated</button></p></div>';
    const inSheet = scaleFromText(ov), shared = curScale();
    if (!inSheet) {
      h += '<div class="warnbox"><b>No scale table found in this sheet.</b>' +
        'The judge reads the anchors from this table. Either it was deleted or its header line no longer ' +
        'reads exactly <code>' + esc(D.scale_header) + '</code>.</div>';
    } else if (!sameScale(inSheet, shared)) {
      h += '<div class="warnbox"><b>The scale table here no longer matches the shared one.</b>' +
        'The anchors are printed on all six sheets. This edit changed only ' + rid + '; the other five still ' +
        'carry the shared table (' + shared.length + ' band' + (shared.length === 1 ? '' : 's') + ', this one has ' +
        inSheet.length + '). <button class="mini" id="push-scale" style="margin-top:7px">push this table to the ' +
        'shared scale — updates the other five</button></div>';
    }
    h += '<div class="card" style="padding:0;overflow:hidden">' +
      '<div style="padding:10px 14px 6px"><h2 style="margin:0">Diff against generated</h2>' +
      '<p class="why" style="margin:2px 0 0">Red is the generated line, green is yours.</p></div>' +
      diffHTML(gen, ov) + '</div>';
  }
  side.innerHTML = h;
  const rv = side.querySelector('#sheet-revert');
  if (rv) rv.onclick = () => { clearSheet(rid); renderPreview(); };
  const ps = side.querySelector('#push-scale');
  if (ps) ps.onclick = () => {
    const bands = scaleFromText(sheetOverride(rid));
    if (!bands) return;
    setScale(bands);
    toast('Shared scale updated to ' + bands.length + ' bands — the other five sheets follow');
    renderSide();
  };
}

/* ---------- shell ---------- */
function render() {
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  bodyEl.style.overflow = tab === 'points' ? 'hidden' : 'auto';
  if (tab === 'shared') renderShared(); else if (tab === 'points') renderPoints(); else renderPreview();
}
document.querySelectorAll('.tab').forEach(b => b.onclick = () => { tab = b.dataset.tab; render(); });
document.getElementById('ex-json').onclick = () => copy(exportJSON(), 'Edited contradiction rubric JSON');
document.getElementById('ex-md').onclick = () => copy(exportMD(), 'Six markdown sheets');
document.addEventListener('keydown', e => {
  if (tab !== 'points' || e.metaKey || e.ctrlKey) return;
  const t = e.target.tagName;
  if (t === 'TEXTAREA' || t === 'INPUT' || t === 'SELECT') return;
  const ids = listIds(), i = ids.indexOf(sel);
  if (e.key === 'j' || e.key === 'ArrowDown') { if (i < ids.length - 1) { sel = ids[i + 1]; renderPoints(); e.preventDefault(); } }
  else if (e.key === 'k' || e.key === 'ArrowUp') { if (i > 0) { sel = ids[i - 1]; renderPoints(); e.preventDefault(); } }
});
window.addEventListener('beforeunload', () => { if (saveTimer) { clearTimeout(saveTimer); saveNow(); } });
render();
load();
</script>
</body></html>
'''

payload = json.dumps(DATA, ensure_ascii=False).replace("</", "<\\/")
EDITS_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(TEMPLATE.replace("__DATA__", payload))
print(f"{OUT}: {len(points)} points, 6 sheets, {len(per_report)} round-3 reports (recall evidence), "
      f"{OUT.stat().st_size/1e3:.0f} kB")
print("  edits ->", EDITS_PATH)
print("  sheets assembled from the page's own data " +
      ("MATCH" if not mismatch else "DIFFER from") + " the committed contra_1..6.md" +
      (" (" + ", ".join(mismatch) + ")" if mismatch else ""))
print("  most stated (most room to contradict):",
      ", ".join(f"{c} {stats[c]['above0']:.0%}" for c in ranked[:5]))
