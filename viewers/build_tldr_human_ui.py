#!/usr/bin/env python3
"""Build viewers/tldr_grading.html — two people score TL;DRs against the story, by hand.

The existing TL;DR grade is five separate points, each scored on its own. That measures
coverage, not whether the summary reads as an account of what happened: a TL;DR can name
four points flatly and leave the reader holding nothing, and one can tell three of them
well and leave the reader holding the incident. This page collects the other measurement —
one holistic 0.0–1.0 judgement per TL;DR, made by a person with the human report's opening
in front of them — so a prompted judge can afterwards be scored against human agreement
rather than against itself.

Layout follows what the graders asked for. Left half: the TL;DR on top, the scoring
controls beneath it. Right half: the human report's opening (the published page itself,
in an iframe, truncated at “…using the internet in unintended ways.” — the last line
before the Timeline) on top, and the five points the story is made of beneath it. The
sidebar picks the report.

The rubric is not written here. It lives in benchmark/rubrics/tldr_holistic.json and is
rendered into both this page and the judge's sheet, so the humans and the model are
answering the same question in the same words.

Two graders share one file. Everything is filed under the grader's name and merged on
load, so both can work at once and the disagreements survive to be reconciled into gold
scores. Saves go to benchmark/audit/tldr_human_scores.json through the html-viewer's
POST /save endpoint, with a localStorage mirror when the server is unreachable.
"""
import html
import importlib.util
import json
import re
import sys
import pathlib
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, RUBRICS, GRADED_INPUTS, VIEWERS, CORPUS

OUT = VIEWERS / "tldr_grading.html"
DATA_DIR = VIEWERS / "data" / "tldr"
HUMAN_HTML = DATA_DIR / "_human_excerpt.html"
SAVE_PATH = ROOT / "benchmark" / "audit" / "tldr_human_scores.json"
RUBRIC_JSON = RUBRICS / "tldr_holistic.json"
BATCHES = ["round4_blind10", "round4_blind30", "round4_blind120"]
FONTS = CORPUS / "fonts"

# Where the excerpt stops: the last sentence of "Our preliminary findings", immediately
# before the Timeline. Everything a grader needs to judge a 200-word summary is above it.
CUT = "unintended ways.</p>"

# Two or three words per anchor, for the reminder beside the score buttons. The full
# wording is in tldr_holistic.json and shown on the rubric panel; these are the handle.
SCALE_SHORT = {"1.0": "tells the story", "0.8": "one gap", "0.6": "half the story",
               "0.4": "subject, not story", "0.2": "barely touching", "0.0": "nothing / wrong"}

NAMES = {"gpt_5_6_sol": "GPT-5.6 Sol", "openai_gpt_5_6_sol": "GPT-5.6 Sol",
         "openai_gpt_6_astra": "GPT-6 Astra", "gpt_5_6_luna": "GPT-5.6 Luna",
         "gpt_5_6_terra": "GPT-5.6 Terra", "gpt_6_astra": "GPT-6 Astra",
         "google_gemini_3_8_flash": "Gemini 3.8 Flash", "meta_muse_spark_1_3": "Muse Spark 1.3",
         "moonshotai_kimi_k3": "Kimi K3", "z_ai_glm_5_3": "GLM 5.3", "claude_opus_5": "Opus 5",
         "claude_opus_4_8": "Opus 4.8", "claude_sonnet_5": "Sonnet 5", "claude_haiku_4_5": "Haiku 4.5",
         "claude_fable_5_1": "Fable 5.1"}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def font_css(css):
    """Point the site's @font-face rules at the vendored files, absolutely.

    Both this page and the iframe are served from the viewer's /file endpoint, where the
    stylesheet's relative fonts/… URL resolves to nothing and the report falls back to
    Palatino.
    """
    def sub(m):
        f = FONTS / m.group(1)
        return f'url("/file?p={quote(str(f))}")' if f.exists() else 'local("no-such-font")'
    return re.sub(r'url\("fonts/([^"]+)"\)', sub, css)


def face_css():
    return font_css("\n".join(re.findall(r"@font-face[^}]*}", (CORPUS / "wiki_tokens.css").read_text())))


HUMAN_SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Human report — opening</title>
<style>%s</style>
<style>
body{padding:0 16px}
.frame{display:block;max-width:none;padding:0}
.main{max-width:none}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
</style></head>
<body><div class="frame"><div class="main">%s</div></div></body></html>
"""


def truncate_html(doc, cut):
    """Cut the article after `cut` and close whatever is still open.

    A plain string slice leaves unbalanced tags, which a browser closes wherever it likes;
    tracking the open elements and emitting the closers keeps the excerpt a well-formed
    subtree of the published page.
    """
    i = doc.find(cut)
    if i < 0:
        raise SystemExit(f"cut point not found in the article: {cut!r}")
    head = doc[:i + len(cut)]
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}
    stack = []
    for m in re.finditer(r"<(/?)([a-zA-Z][\w-]*)\b[^>]*?(/?)>", head):
        close, tag, selfclose = m.group(1), m.group(2).lower(), m.group(3)
        if tag in void or selfclose:
            continue
        if close:
            if tag in stack:
                while stack and stack.pop() != tag:
                    pass
        else:
            stack.append(tag)
    return head + "".join(f"</{t}>" for t in reversed(stack))


def write_human_html():
    w = load(ROOT / "scripts" / "wiki_report.py", "wiki_report")
    doc = truncate_html(w.article_html(), CUT)
    doc = re.sub(r'(<input(?=[^>]*\bclass="[^"]*\bex-toggle\b)(?![^>]*\bchecked\b)[^>]*?)/?>',
                 r'\1 checked>', doc)
    doc = re.sub(r"<details(?![^>]*\bopen\b)", "<details open", doc)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HUMAN_HTML.write_text(HUMAN_SHELL % (font_css(w.css()), doc))
    return doc


# The suffixes matter: __served-<model> is a run that asked for one model and got another
# (opus-5 served as opus-4.8), and __p<hash> disambiguates two prompt ids in one cell.
# Dropping either would silently lose six of the 112 reports.
KEY = re.compile(r"^r4b(\d+)__([a-z]+)__(.+?)__rep(\d+)"
                 r"(?:__served-([a-z0-9-]+))?(?:__p[0-9a-f]+)?$")


def reports():
    """Every round-4 report, with its TL;DR pulled out the way the judge pulls it."""
    ex = load(ROOT / "scripts" / "extract_tldr.py", "extract_tldr")
    out = []
    for batch in BATCHES:
        d = GRADED_INPUTS / batch
        meta = {}
        idx = d / "_index.jsonl"
        if idx.exists():
            for line in idx.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    meta[r.get("graded_input", "")] = r
        for p in sorted(d.glob("*.md")):
            m = KEY.match(p.stem)
            if not m:
                continue
            budget, scaffold, model, rep = int(m.group(1)), m.group(2), m.group(3), int(m.group(4))
            served = m.group(5)
            text = p.read_text()
            tldr, how = ex.extract(text)
            slug = re.sub(r"[^0-9a-zA-Z]+", "_", model).strip("_")
            r = meta.get(p.name, {})
            out.append({
                "key": p.stem, "budget": budget, "scaffold": scaffold, "rep": rep,
                "model": NAMES.get(slug, model), "slug": slug, "served": served,
                "label": f"{NAMES.get(slug, model)} · {budget}m · rep{rep}",
                "tldr": tldr, "how": how, "words": len(tldr.split()),
                "report_words": r.get("report_words"), "path": str(p),
            })
    return out


def core30(rows):
    """Thirty reports both graders do, so every one of them is double-scored.

    Gold scores need two independent reads of the same TL;DR; a split sample would give
    sixty singly-graded items and no way to measure agreement. Spread ten across each
    budget and rotate the model order per budget so the thirty are not the same ten models
    three times over.
    """
    picked, per_budget = [], 10
    for bi, budget in enumerate(sorted({r["budget"] for r in rows})):
        cell = {}
        for r in sorted((x for x in rows if x["budget"] == budget), key=lambda x: (x["model"], x["rep"])):
            cell.setdefault(r["model"], []).append(r)
        models = sorted(cell)
        models = models[bi % len(models):] + models[:bi % len(models)]
        i = 0
        while len(picked) < per_budget * (bi + 1) and any(cell[m] for m in models):
            m = models[i % len(models)]
            if cell[m]:
                picked.append(cell[m].pop((bi + i // len(models)) % len(cell[m]))["key"])
            i += 1
    return picked


def main():
    write_human_html()
    rub = json.loads(RUBRIC_JSON.read_text())
    tldr_sheet = json.loads((RUBRICS / "tldr_1.json").read_text())
    by = {c["id"]: c for c in tldr_sheet["claims"]}
    points = [{"id": i, "section": by[i]["section"], "claim": by[i]["claim"],
               "quote": by[i].get("report_quote") or "", "note": by[i].get("note") or ""}
              for i in rub["point_ids"]]
    rows = reports()
    core = core30(rows)
    core_set = set(core)
    for r in rows:
        r["core"] = r["key"] in core_set
    rows.sort(key=lambda r: (not r["core"], r["budget"], r["model"], r["rep"]))
    scale = [{"v": v, "short": SCALE_SHORT.get(v, v), "full": t} for v, t in rub["scale"]]

    data = {"save_path": str(SAVE_PATH), "human_html": str(HUMAN_HTML),
            "rubric": {"title": rub["title"], "intro": rub["intro"], "scale": scale,
                       "guidance": rub["guidance"], "points_intro": rub["points_intro"]},
            "points": points, "reports": rows, "core": core, "target": len(core)}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = DATA_DIR / "_grading.json"
    payload.write_text(json.dumps(data, ensure_ascii=False))
    OUT.write_text(PAGE.replace("__CSS__", CSS).replace("__JS__", JS)
                       .replace("__FACES__", face_css())
                       .replace("__DATA__", json.dumps({"payload": str(payload)})))
    n_core = sum(r["core"] for r in rows)
    print(f"wrote {OUT}  —  {len(rows)} reports ({n_core} in the core set), "
          f"{len(points)} points, saving to {SAVE_PATH}")
    print("  budgets: " + ", ".join(f"{b}m={sum(r['budget'] == b for r in rows)}"
                                    for b in sorted({r['budget'] for r in rows})))
    print("  core by budget: " + ", ".join(
        f"{b}m={sum(1 for r in rows if r['core'] and r['budget'] == b)}"
        for b in sorted({r['budget'] for r in rows})))
    print(f"  human excerpt {HUMAN_HTML.stat().st_size/1e3:.0f} kB, payload "
          f"{payload.stat().st_size/1e3:.0f} kB")


CSS = r"""
__FACES__
:root{--bg:#F4F3EE;--card:#FFF;--bd:#E0DDD4;--ink:#1A1A1A;--sec:#666;--mut:#999;
--acc:#C15F3C;--acch:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;
--okbg:#D1FAE5;--okfg:#065F46;--wabg:#FEF3C7;--wafg:#92400E;--dabg:#FEE2E2;--dafg:#991B1B}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px;
display:flex;flex-direction:column;overflow:hidden}
button{font:inherit;cursor:pointer}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--acc)}

/* ---------- header ---------- */
header{flex:0 0 auto;display:flex;align-items:center;gap:14px;padding:10px 18px;
background:var(--card);border-bottom:1px solid var(--bd)}
header h1{margin:0;font-size:15px;color:var(--acc);font-weight:600;white-space:nowrap}
header .spacer{flex:1}
.tab{background:transparent;border:1px solid var(--bd);border-radius:6px;padding:4px 10px;
font-size:12px;color:var(--sec)}
.tab:hover{border-color:var(--acc);color:var(--acc)}
.tab.on{background:var(--acc);border-color:var(--acc);color:#fff}
#prog{font-size:12px;color:var(--sec);white-space:nowrap}
#prog b{color:var(--ink)}
#save{font-size:11px;color:var(--mut);min-width:170px;text-align:right}
#save.err{color:var(--dafg);font-weight:600}

/* ---------- sidebar ---------- */
#wrap{flex:1;display:flex;min-height:0}
aside{flex:0 0 268px;background:var(--card);border-right:1px solid var(--bd);
display:flex;flex-direction:column;min-height:0}
aside.hidden{display:none}
#search{margin:10px;padding:6px 8px;border:1px solid var(--bd);border-radius:6px;font:inherit;font-size:13px}
#search:focus{outline:none;border-color:var(--acc)}
.chips{display:flex;flex-wrap:wrap;gap:4px;padding:0 10px 8px}
.chip{border:1px solid var(--bd);background:transparent;border-radius:99px;padding:2px 9px;
font-size:11px;color:var(--sec)}
.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
#list{flex:1;overflow-y:auto;padding-bottom:24px}
.grouphd{position:sticky;top:0;background:var(--card);padding:7px 12px 4px;font-size:11px;
letter-spacing:.06em;text-transform:uppercase;color:var(--mut);border-bottom:1px solid var(--bd);z-index:2}
.item{display:flex;align-items:baseline;gap:7px;padding:6px 12px;border-bottom:1px solid #F0EEE8;
cursor:pointer;font-size:13px}
.item:hover{background:var(--row)}
.item.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--acc)}
.item .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .bd{font-size:11px;color:var(--mut);white-space:nowrap}
.item .sc{font-variant-numeric:tabular-nums;font-size:12px;font-weight:600;color:var(--acc);min-width:22px;text-align:right}
.item .sc.none{color:#D9D5CC;font-weight:400}
.item .dot{width:6px;height:6px;border-radius:50%;background:transparent;flex:0 0 auto}
.item .dot.other{background:#C9C4B8}

/* ---------- the two halves ---------- */
main{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px;min-width:0;min-height:0}
.col{display:flex;flex-direction:column;min-height:0;gap:12px}
.pane{background:var(--card);border:1px solid var(--bd);border-radius:8px;min-height:0;
display:flex;flex-direction:column}
.pane > h2{margin:0;padding:9px 14px;border-bottom:1px solid var(--bd);font-size:11px;
letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:600;
display:flex;align-items:center;gap:8px;flex:0 0 auto}
.pane > h2 .r{margin-left:auto;text-transform:none;letter-spacing:0;font-weight:400;font-size:11px}
.body{overflow:auto;padding:14px 18px;flex:1}
.top{flex:1 1 auto}
.bot{flex:0 0 auto;max-height:46%}

/* the TL;DR itself, set the way the report sets it */
#tldr{font-family:"et-book",Palatino,"Palatino Linotype",Georgia,serif;font-size:17px;
line-height:1.62;white-space:pre-wrap;color:var(--ink);max-width:62ch}
#tldr .empty{font-family:system-ui,sans-serif;font-size:13px;color:var(--mut)}
#meta{font-size:12px;color:var(--sec);margin:0 0 12px;padding-bottom:10px;border-bottom:1px solid var(--bd);
display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.badge{border-radius:99px;padding:1px 8px;font-size:11px;background:var(--soft);color:var(--acch)}
.badge.g{background:var(--okbg);color:var(--okfg)}
.badge.n{background:#F0EEE8;color:var(--sec)}

/* ---------- scoring ---------- */
#scorebody{padding:12px 16px 14px}
.scaleline{font-size:11px;color:var(--mut);margin:0 0 8px}
.scaleline b{color:var(--sec);font-weight:600}
.btns{display:flex;gap:5px;flex-wrap:wrap}
.sbtn{flex:1 1 0;min-width:44px;border:1px solid var(--bd);background:#fff;border-radius:6px;
padding:7px 0 5px;text-align:center;font-variant-numeric:tabular-nums;font-size:14px;color:var(--ink);
line-height:1.15}
.sbtn small{display:block;font-size:9px;color:var(--mut);margin-top:2px;height:11px;overflow:hidden}
.sbtn:hover{border-color:var(--acc);color:var(--acc)}
.sbtn.on{background:var(--acc);border-color:var(--acc);color:#fff}
.sbtn.on small{color:#F7DCD0}
#note{width:100%;margin-top:10px;min-height:56px;resize:vertical;border:1px solid var(--bd);
border-radius:6px;padding:7px 9px;font:inherit;font-size:13px;background:var(--row)}
#note:focus{outline:none;border-color:var(--acc);background:#fff}
.foot{display:flex;align-items:center;gap:8px;margin-top:9px}
.foot .hint{font-size:11px;color:var(--mut);margin-left:auto;text-align:right}
.other{margin-top:9px;font-size:12px;color:var(--sec);background:var(--row);border:1px solid var(--bd);
border-radius:6px;padding:7px 9px}
.other b{color:var(--ink)}
.other.dis{background:var(--wabg);border-color:#E9D8A6;color:var(--wafg)}

/* ---------- human report + points ---------- */
#hframe{border:0;width:100%;height:100%;flex:1;background:#fff;border-radius:0 0 8px 8px}
#points{list-style:none;margin:0;padding:0}
#points li{padding:9px 0;border-bottom:1px solid #F0EEE8}
#points li:last-child{border-bottom:0}
#points .cl{font-weight:600}
#points .id{font-size:11px;color:var(--acc);margin-right:6px;font-variant-numeric:tabular-nums}
#points .q{display:block;margin-top:3px;font-family:"et-book",Palatino,Georgia,serif;font-size:14px;
color:var(--sec);padding-left:10px;border-left:2px solid var(--bd)}
#points .nt{display:block;margin-top:4px;font-size:12px;color:var(--mut)}
.lede{font-size:12px;color:var(--sec);margin:0 0 10px}

/* ---------- rubric overlay ---------- */
#veil{position:fixed;inset:0;background:rgba(26,26,26,.42);display:none;z-index:40;
align-items:center;justify-content:center;padding:28px}
#veil.on{display:flex}
#modal{background:var(--card);border:1px solid var(--bd);border-radius:10px;max-width:820px;
width:100%;max-height:100%;overflow:auto;padding:24px 28px}
#modal h2{margin:0 0 4px;color:var(--acc);font-size:19px}
#modal p{line-height:1.55;color:var(--ink)}
#modal table{border-collapse:collapse;width:100%;margin:14px 0}
#modal th,#modal td{border-bottom:1px solid var(--bd);padding:7px 9px;text-align:left;
vertical-align:top;font-size:13px;line-height:1.5}
#modal th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}
#modal td.v{font-variant-numeric:tabular-nums;font-weight:600;color:var(--acc);width:52px}
#modal ul{padding-left:18px;line-height:1.55}
#modal li{margin-bottom:7px}
#modal .close{margin-top:16px;background:var(--acc);color:#fff;border:0;border-radius:6px;padding:8px 18px}
#modal .close:hover{background:var(--acch)}
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TL;DR grading</title>
<style>__CSS__</style></head>
<body>
<header>
  <h1>TL;DR grading</h1>
  <button class="tab" id="side-btn" title="hide the report list">&#9776;</button>
  <button class="tab" id="who-btn" title="whose scores these are filed under">who are you?</button>
  <button class="tab" id="rub-btn" title="the rubric in full">the rubric</button>
  <span class="spacer"></span>
  <span id="prog"></span>
  <div id="save">loading&hellip;</div>
</header>
<div id="wrap">
  <aside id="side">
    <input id="search" type="search" placeholder="filter by model&hellip;" autocomplete="off">
    <div class="chips" id="chips"></div>
    <div id="list"></div>
  </aside>
  <main>
    <div class="col">
      <section class="pane top">
        <h2>the model&rsquo;s TL;DR<span class="r" id="tldr-r"></span></h2>
        <div class="body"><div id="meta"></div><div id="tldr"></div></div>
      </section>
      <section class="pane bot">
        <h2>your score<span class="r" id="score-r"></span></h2>
        <div class="body" id="scorebody">
          <p class="scaleline" id="scaleline"></p>
          <div class="btns" id="btns"></div>
          <textarea id="note" placeholder="what the reader would come away with; what is missing or wrong (optional)"></textarea>
          <div class="foot">
            <button class="tab" id="clear">clear</button>
            <button class="tab" id="next">save &amp; next &rarr;</button>
            <span class="hint">0&ndash;9 sets 0.0&ndash;0.9 &middot; = sets 1.0 &middot; j / k moves</span>
          </div>
          <div id="other"></div>
        </div>
      </section>
    </div>
    <div class="col">
      <section class="pane top">
        <h2>the human report &mdash; the opening<span class="r">through &ldquo;&hellip;in unintended ways.&rdquo;</span></h2>
        <iframe id="hframe" title="the human incident report, opening section"></iframe>
      </section>
      <section class="pane bot">
        <h2>the story, in five points</h2>
        <div class="body"><p class="lede" id="pts-lede"></p><ul id="points"></ul></div>
      </section>
    </div>
  </main>
</div>
<div id="veil"><div id="modal"></div></div>
<script>const BOOT = __DATA__;</script>
<script>__JS__</script>
</body></html>
"""
JS = r"""
'use strict';
const fileURL = p => '/file?p=' + encodeURIComponent(p);
const el = (t, c, txt) => { const e = document.createElement(t); if (c) e.className = c;
  if (txt != null) e.textContent = txt; return e; };
const fmt = v => v == null ? '' : v.toFixed(1);

let D = null, SAVE_PATH = '', LS_KEY = '', ME = '';
let sel = null, filters = {budget: new Set(), set: 'core'}, q = '';
let sbHidden = false;

/* ---------- state: two graders, one file ----------
   Everything is filed under the grader's name and merged on load, so both people can work
   at the same time on the same reports without either overwriting the other. */
let state = {version: 1, updated_at: null, graders: {}};
const bkt = who => (state.graders && state.graders[who]) || null;
const mkBkt = who => { const b = bkt(who) || (state.graders[who] = {scores: {}});
  b.scores = b.scores || {}; return b; };
const graders = () => Object.keys(state.graders).sort();
function entry(who, key) { const b = bkt(who); return (b && b.scores[key]) || null; }
function mine(key) { return ME ? entry(ME, key) : null; }
function others(key) { const out = [];
  for (const w of graders()) { if (w === ME) continue; const e = entry(w, key);
    if (e && e.score != null) out.push([w, e.score]); } return out; }

/* ---------- saving ---------- */
let timer = null;
function setStatus(t, err) { const e = document.getElementById('save');
  e.textContent = t; e.className = err ? 'err' : ''; }
function scheduleSave() { clearTimeout(timer); setStatus('unsaved…');
  timer = setTimeout(saveNow, 500); }
async function saveNow() {
  state.updated_at = new Date().toISOString();
  const body = JSON.stringify({version: 1, updated_at: state.updated_at, graders: state.graders}, null, 1);
  try { localStorage.setItem(LS_KEY, body); } catch (e) {}
  try {
    const r = await fetch('/save?p=' + encodeURIComponent(SAVE_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error(await r.text());
    setStatus('saved to disk ' + new Date().toLocaleTimeString());
  } catch (e) { setStatus('BROWSER ONLY — not saved to disk', true); }
}
/* Later timestamp wins, per grader per report, so a browser copy that is behind the file
   cannot resurrect a score the other grader has already revised. */
function mergeInto(dst, src) {
  for (const w of Object.keys((src && src.graders) || {})) {
    const b = dst.graders[w] = dst.graders[w] || {scores: {}};
    for (const [k, v] of Object.entries(src.graders[w].scores || {})) {
      const cur = b.scores[k];
      if (!cur || (v.at || '') >= (cur.at || '')) b.scores[k] = v;
    }
  }
  if ((src || {}).updated_at && (src.updated_at > (dst.updated_at || ''))) dst.updated_at = src.updated_at;
  return dst;
}
function countAll(st) { let n = 0;
  for (const w of Object.keys(st.graders || {})) n += Object.keys(st.graders[w].scores || {}).length;
  return n; }
async function loadState() {
  let server = null, local = null;
  try { const r = await fetch(fileURL(SAVE_PATH)); if (r.ok) server = await r.json(); } catch (e) {}
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = {version: 1, updated_at: null, graders: {}};
  if (server) mergeInto(state, server);
  if (local) mergeInto(state, local);
  const n = countAll(state);
  if (!server && !local) setStatus('no scores yet');
  else setStatus('loaded ' + n + ' score' + (n === 1 ? '' : 's') +
                 (server ? ' from disk' : ' — browser copy only'), !server);
}

/* ---------- who ---------- */
function paintWho() { const b = document.getElementById('who-btn');
  b.textContent = ME ? 'grader: ' + ME : 'who are you?'; b.classList.toggle('on', !ME); }
function askWho() {
  const n = (prompt('Your name — scores are filed under it so two graders can share one file.',
                    ME || '') || '').trim();
  if (!n) return;
  ME = n; try { localStorage.setItem('tldr_grading:who', n); } catch (e) {}
  paintWho(); paintList(); paintReport();
}

/* ---------- the rubric panel ---------- */
function rubricModal() {
  const m = document.getElementById('modal'); m.innerHTML = '';
  m.appendChild(el('h2', null, D.rubric.title));
  D.rubric.intro.forEach(p => m.appendChild(el('p', null, p)));
  const t = el('table'); const hd = el('tr');
  hd.appendChild(el('th', null, 'Score')); hd.appendChild(el('th', null, 'The TL;DR…'));
  t.appendChild(hd);
  D.rubric.scale.forEach(s => { const tr = el('tr');
    tr.appendChild(el('td', 'v', s.v)); tr.appendChild(el('td', null, s.full)); t.appendChild(tr); });
  m.appendChild(t);
  const ul = el('ul');
  D.rubric.guidance.forEach(g => { const li = el('li');
    li.innerHTML = g.replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); ul.appendChild(li); });
  m.appendChild(ul);
  m.appendChild(el('p', null, D.rubric.points_intro));
  const pl = el('ul');
  D.points.forEach(p => { const li = el('li');
    li.appendChild(el('b', null, p.claim));
    if (p.note) li.appendChild(el('span', null, ' — ' + p.note));
    pl.appendChild(li); });
  m.appendChild(pl);
  const c = el('button', 'close', 'got it'); c.onclick = closeModal; m.appendChild(c);
  document.getElementById('veil').classList.add('on');
}
function closeModal() { document.getElementById('veil').classList.remove('on'); }

/* ---------- sidebar ---------- */
function visible() {
  const s = q.toLowerCase();
  return D.reports.filter(r =>
    (!filters.budget.size || filters.budget.has(r.budget)) &&
    (!s || (r.model + ' ' + r.key).toLowerCase().includes(s)));
}
function paintChips() {
  const box = document.getElementById('chips'); box.innerHTML = '';
  const budgets = [...new Set(D.reports.map(r => r.budget))].sort((a, b) => a - b);
  budgets.forEach(b => {
    const c = el('button', 'chip' + (filters.budget.has(b) ? ' on' : ''), b + ' min');
    c.onclick = () => { filters.budget.has(b) ? filters.budget.delete(b) : filters.budget.add(b);
      paintChips(); paintList(); };
    box.appendChild(c);
  });
}
function paintList() {
  const box = document.getElementById('list'); box.innerHTML = '';
  const rows = visible();
  for (const [flag, title] of [[true, 'the shared set of ' + D.target], [false, 'everything else']]) {
    const group = rows.filter(r => r.core === flag);
    if (!group.length) continue;
    const done = group.filter(r => mine(r.key) && mine(r.key).score != null).length;
    box.appendChild(el('div', 'grouphd', title + ' — ' + done + '/' + group.length));
    group.forEach(r => {
      const e = mine(r.key), it = el('div', 'item' + (sel === r.key ? ' sel' : ''));
      it.appendChild(el('span', 'dot' + (others(r.key).length ? ' other' : '')));
      it.appendChild(el('span', 'nm', r.model));
      it.appendChild(el('span', 'bd', r.budget + 'm·r' + r.rep));
      it.appendChild(el('span', 'sc' + (e && e.score != null ? '' : ' none'),
                        e && e.score != null ? fmt(e.score) : '–'));
      it.onclick = () => { sel = r.key; paintList(); paintReport(); };
      box.appendChild(it);
    });
  }
  paintProgress();
}
function paintProgress() {
  const core = D.reports.filter(r => r.core);
  const done = core.filter(r => mine(r.key) && mine(r.key).score != null).length;
  const all = D.reports.filter(r => mine(r.key) && mine(r.key).score != null).length;
  document.getElementById('prog').innerHTML = ME
    ? '<b>' + done + '</b>/' + D.target + ' of the shared set &middot; ' + all + ' in all'
    : 'name yourself to start scoring';
}

/* ---------- the report ---------- */
function paintReport() {
  const r = D.reports.find(x => x.key === sel);
  const meta = document.getElementById('meta'), t = document.getElementById('tldr');
  if (!r) { meta.textContent = ''; t.innerHTML = '<span class="empty">pick a report on the left.</span>';
    document.getElementById('btns').innerHTML = ''; document.getElementById('other').innerHTML = '';
    return; }
  meta.innerHTML = '';
  meta.appendChild(el('span', 'badge', r.model));
  meta.appendChild(el('span', 'badge n', r.budget + ' min'));
  meta.appendChild(el('span', 'badge n', 'rep ' + r.rep));
  meta.appendChild(el('span', 'badge n', r.scaffold));
  if (r.served) meta.appendChild(el('span', 'badge n', 'served as ' + r.served));
  if (r.core) meta.appendChild(el('span', 'badge g', 'shared set'));
  meta.appendChild(el('span', 'badge n', r.words + ' words'));
  if (r.how !== 'heading') meta.appendChild(el('span', 'badge n', 'no TL;DR heading — opening prose'));
  t.textContent = r.tldr;
  document.getElementById('tldr-r').textContent = r.key;
  document.querySelector('#tldr').parentElement.scrollTop = 0;
  paintScore(r);
}
function paintScore(r) {
  const e = mine(r.key);
  document.getElementById('scaleline').innerHTML = D.rubric.scale
    .map(s => '<b>' + s.v + '</b> ' + s.short).join(' &nbsp;&middot;&nbsp; ');
  const box = document.getElementById('btns'); box.innerHTML = '';
  const shorts = {}; D.rubric.scale.forEach(s => shorts[s.v] = s.short);
  for (let i = 0; i <= 10; i++) {
    const v = i / 10, key = v.toFixed(1);
    const b = el('button', 'sbtn' + (e && e.score != null && Math.abs(e.score - v) < 1e-9 ? ' on' : ''), key);
    b.appendChild(el('small', null, shorts[key] || ''));
    b.onclick = () => setScore(v);
    box.appendChild(b);
  }
  document.getElementById('note').value = (e && e.note) || '';
  document.getElementById('score-r').textContent = ME ? '' : 'name yourself first';
  const o = document.getElementById('other'); o.innerHTML = '';
  const ot = others(r.key);
  if (ot.length) {
    const gap = e && e.score != null ? Math.max(...ot.map(x => Math.abs(x[1] - e.score))) : 0;
    const d = el('div', 'other' + (gap >= 0.3 ? ' dis' : ''));
    d.innerHTML = ot.map(x => '<b>' + x[0] + '</b> gave ' + fmt(x[1])).join(' &middot; ') +
      (gap >= 0.3 ? ' &mdash; ' + gap.toFixed(1) + ' apart from you' : '');
    o.appendChild(d);
  }
}
function setScore(v) {
  if (!ME) { askWho(); if (!ME) return; }
  const b = mkBkt(ME), cur = b.scores[sel] || {};
  b.scores[sel] = {score: v, note: document.getElementById('note').value.trim(),
                   at: new Date().toISOString()};
  if (cur.note && !b.scores[sel].note) b.scores[sel].note = cur.note;
  scheduleSave(); paintList(); paintScore(D.reports.find(x => x.key === sel));
}
function saveNote() {
  if (!ME || !sel) return;
  const b = mkBkt(ME), cur = b.scores[sel] || {};
  const n = document.getElementById('note').value.trim();
  if ((cur.note || '') === n) return;
  b.scores[sel] = {score: cur.score != null ? cur.score : null, note: n, at: new Date().toISOString()};
  scheduleSave(); paintList();
}
function clearScore() {
  if (!ME || !sel) return;
  const b = mkBkt(ME); delete b.scores[sel];
  document.getElementById('note').value = '';
  scheduleSave(); paintList(); paintScore(D.reports.find(x => x.key === sel));
}
function move(d) {
  const rows = visible(); if (!rows.length) return;
  let i = rows.findIndex(r => r.key === sel);
  i = i < 0 ? 0 : Math.min(rows.length - 1, Math.max(0, i + d));
  sel = rows[i].key; paintList(); paintReport();
  const n = document.querySelector('.item.sel'); if (n) n.scrollIntoView({block: 'nearest'});
}

/* ---------- the five points ---------- */
function paintPoints() {
  document.getElementById('pts-lede').textContent = D.rubric.points_intro;
  const ul = document.getElementById('points'); ul.innerHTML = '';
  D.points.forEach(p => {
    const li = el('li');
    const h = el('div', 'cl'); h.appendChild(el('span', 'id', p.id));
    h.appendChild(document.createTextNode(p.claim)); li.appendChild(h);
    if (p.quote) li.appendChild(el('span', 'q', '“' + p.quote + '”'));
    if (p.note) li.appendChild(el('span', 'nt', p.note));
    ul.appendChild(li);
  });
}

/* ---------- boot ---------- */
function applySidebar() { document.getElementById('side').classList.toggle('hidden', sbHidden); }
async function boot() {
  const r = await fetch(fileURL(BOOT.payload));
  D = await r.json();
  SAVE_PATH = D.save_path; LS_KEY = 'tldr_grading:' + SAVE_PATH;
  try { ME = localStorage.getItem('tldr_grading:who') || ''; } catch (e) { ME = ''; }
  try { sbHidden = localStorage.getItem('tldr_grading:sidebar') === '1'; } catch (e) {}
  document.getElementById('hframe').src = fileURL(D.human_html);
  await loadState();
  paintWho(); applySidebar(); paintChips(); paintPoints();
  sel = (D.reports.find(x => x.core) || D.reports[0] || {}).key || null;
  paintList(); paintReport();
  let seen = false; try { seen = localStorage.getItem('tldr_grading:seen') === '1'; } catch (e) {}
  if (!seen) { rubricModal(); try { localStorage.setItem('tldr_grading:seen', '1'); } catch (e) {} }

  document.getElementById('who-btn').onclick = askWho;
  document.getElementById('rub-btn').onclick = rubricModal;
  document.getElementById('side-btn').onclick = () => { sbHidden = !sbHidden;
    try { localStorage.setItem('tldr_grading:sidebar', sbHidden ? '1' : '0'); } catch (e) {}
    applySidebar(); };
  document.getElementById('veil').onclick = ev => { if (ev.target.id === 'veil') closeModal(); };
  document.getElementById('search').oninput = ev => { q = ev.target.value; paintList(); };
  document.getElementById('note').onblur = saveNote;
  document.getElementById('clear').onclick = clearScore;
  document.getElementById('next').onclick = () => { saveNote(); move(1); };
  addEventListener('keydown', ev => {
    if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA') {
      if (ev.key === 'Escape') ev.target.blur();
      return;
    }
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (ev.key === 'Escape') { closeModal(); return; }
    if (ev.key === 'j' || ev.key === 'ArrowDown') { ev.preventDefault(); move(1); }
    else if (ev.key === 'k' || ev.key === 'ArrowUp') { ev.preventDefault(); move(-1); }
    else if (ev.key >= '0' && ev.key <= '9') { setScore(Number(ev.key) / 10); }
    else if (ev.key === '=' || ev.key === '+') { setScore(1.0); }
    else if (ev.key === 'Enter') { move(1); }
    else if (ev.key === '?') { rubricModal(); }
  });
  addEventListener('beforeunload', () => { if (timer) { clearTimeout(timer); saveNow(); } });
}
boot();
"""


if __name__ == "__main__":
    main()
