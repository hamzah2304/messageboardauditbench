#!/usr/bin/env python3
"""Build viewers/pswap_reader.html — read the provider-swap reports against their grades.

The swapped corpus is the experiment that decides whether OpenAI models are protecting
OpenAI or holding an epistemic line about attribution generally: the data is identical
except that OpenAI becomes Anthropic and Azure becomes AWS. The aggregate says the swap
changes nothing. This page is for checking that by reading, because a cluster mean over
four findings cannot show you *how* a report declines to name an actor, and the judge's
one-line reason only summarises it.

Reports are grouped by whether the model's own lab is the one the data names, since that
is the comparison the page exists to serve. The six attribution findings are pinned above
the other thirty-two, each with its score and the judge's reasoning, and selecting one
highlights the passage the judge scored from — or says plainly that it quoted nothing,
which for these findings is usually the whole story.
"""
import html
import json
import os
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import CLAIMS, GRADED, GRADED_INPUTS, RUBRICS, VIEWERS

OUT = VIEWERS / "pswap_reader.html"
DATA_DIR = VIEWERS / "data" / "pswap"
JUDGE = os.getenv("JUDGE", "claude-fable-5-1")
GDIR = GRADED / f"judge_{re.sub(r'[^0-9a-zA-Z]+', '_', JUDGE).strip('_')}" / "v2" / "variant_anthropic"
DIRS = ["pswap_b10", "pswap_b30"]
ATTRIB = ["N07", "N08", "N09", "N10", "N37", "N38"]
NAMES = {"gpt-5.6-sol": "GPT-5.6 Sol", "gpt-5.6-luna": "GPT-5.6 Luna",
         "gpt-5.6-terra": "GPT-5.6 Terra", "gpt-6-astra": "GPT-6 Astra",
         "google/gemini-3.8-flash": "Gemini 3.8 Flash", "meta/muse-spark-1.3": "Muse Spark 1.3",
         "moonshotai/kimi-k3": "Kimi K3", "z-ai/glm-5.3": "GLM 5.3",
         "claude-opus-5": "Opus 5", "claude-opus-4-8": "Opus 4.8",
         "claude-sonnet-5": "Sonnet 5", "claude-haiku-4-5": "Haiku 4.5"}
OPENAI = {"GPT-5.6 Sol", "GPT-5.6 Luna", "GPT-5.6 Terra", "GPT-6 Astra"}
ANTH = {"Opus 5", "Opus 4.8", "Sonnet 5", "Haiku 4.5"}
# The data names Anthropic, so an Anthropic model is being asked to name its own lab.
GROUP = {**{m: "own lab named" for m in ANTH},
         **{m: "other lab named" for m in OPENAI}}

TRANS = {"’": "'", "‘": "'", "“": '"', "”": '"',
         "—": "-", "–": "-", " ": " "}


def norm(s):
    """Lower-case, fold quotes and dashes, collapse whitespace, drop markdown emphasis."""
    out, prev_space = [], True
    for ch in s:
        c = TRANS.get(ch, ch).lower()
        if c in "*`_":
            continue
        if c.isspace():
            if prev_space:
                continue
            c, prev_space = " ", True
        else:
            prev_space = False
        out.append(c)
    return "".join(out)


def sanitise(v):
    return re.sub(r"[^0-9a-zA-Z]+", "_", v).strip("_")


def main():
    claims = {c["id"]: c for c in json.loads((CLAIMS / "claims_v2.json").read_text())["claims"]}
    # the swapped sheets carry the rewritten wording the judge actually applied
    swapped = {}
    for i in range(1, 9):
        p = RUBRICS / "anthropic" / f"v2_{i}.json"
        if p.exists():
            for c in json.loads(p.read_text())["claims"]:
                swapped[c["id"]] = c

    reports = []
    for d in DIRS:
        folder = GRADED_INPUTS / d
        rows = {}
        idx = folder / "_index.jsonl"
        if idx.exists():
            for line in idx.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    rows[r["graded_input"]] = r
        for path in sorted(folder.glob("*.md")):
            key = sanitise(path.stem)
            gp = GDIR / f"graded_{key}.json"
            if not gp.exists():
                continue
            g = json.loads(gp.read_text())
            if g.get("max") != 38:
                continue
            row = rows.get(path.name, {})
            model = NAMES.get(str(row.get("model")), str(row.get("model")))
            text = path.read_text()
            reports.append({
                "key": key, "model": model, "group": GROUP.get(model, "neutral"),
                "budget": row.get("budget_min"), "agent": row.get("agent"),
                "prompt": row.get("prompt_id"), "words": len(text.split()),
                "text": text, "scores": g["scores"],
                "attrib": round(sum(g["scores"][i]["score"] for i in ATTRIB) / len(ATTRIB), 3),
                "overall": round(sum(v["score"] for v in g["scores"].values()) / 38, 3),
            })
    if not reports:
        raise SystemExit(f"no graded twin reports under {GDIR}")
    reports.sort(key=lambda r: (r["group"], r["model"], r["budget"]))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for r in reports:
        (DATA_DIR / f"{r['key']}.json").write_text(json.dumps(
            {"text": r.pop("text"), "scores": r["scores"]}, ensure_ascii=False))
        r.pop("scores")

    order = ATTRIB + [c for c in sorted(claims) if c not in ATTRIB]
    data = {
        "dir": str(DATA_DIR), "judge": JUDGE, "attrib": ATTRIB, "order": order,
        "claims": {cid: {"id": cid, "section": claims[cid]["section"],
                         "original": claims[cid]["claim"],
                         "swapped": (swapped.get(cid) or {}).get("claim", "")}
                   for cid in claims},
        "reports": reports,
    }
    payload = DATA_DIR / "_index.json"
    payload.write_text(json.dumps(data, ensure_ascii=False))
    OUT.write_text(PAGE.replace("__BOOT__", json.dumps({"payload": str(payload)}))
                       .replace("__CSS__", CSS).replace("__JS__", JS))
    from collections import Counter
    print(f"wrote {OUT} — {len(reports)} twin reports, judge {JUDGE}")
    print("  " + ", ".join(f"{k}: {v}" for k, v in Counter(r["group"] for r in reports).items()))
    print(f"  payload {payload.stat().st_size/1e3:.0f} kB + {len(reports)} report files")
    print(f"  swapped claim wording available: {len(swapped)}/38")


CSS = r"""
:root{--bg:#F4F3EE;--card:#FFF;--bd:#E0DDD4;--ink:#1A1A1A;--sec:#666;--mut:#999;
--acc:#C15F3C;--acch:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;
--ok:#D1FAE5;--okf:#065F46;--warn:#FEF3C7;--warnf:#92400E;--dang:#FEE2E2;--dangf:#991B1B}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);display:flex;flex-direction:column;
overflow:hidden;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px}
button{font:inherit;cursor:pointer}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--acc)}
header{flex:0 0 auto;display:flex;align-items:center;gap:12px;padding:9px 16px;
background:var(--card);border-bottom:1px solid var(--bd)}
header h1{margin:0;font-size:15px;color:var(--acc);font-weight:600;white-space:nowrap}
header .sp{flex:1}
header .note{font-size:12px;color:var(--sec)}
.tab{background:transparent;border:1px solid var(--bd);border-radius:6px;padding:3px 10px;
font-size:12px;color:var(--sec)}
.tab:hover{border-color:var(--acc);color:var(--acc)}
.tab.on{background:var(--acc);border-color:var(--acc);color:#fff}
#wrap{flex:1;display:flex;min-height:0}
aside{flex:0 0 268px;background:var(--card);border-right:1px solid var(--bd);
display:flex;flex-direction:column;min-height:0}
#list{flex:1;overflow-y:auto;padding-bottom:20px}
.ghd{position:sticky;top:0;background:var(--card);padding:7px 12px 4px;font-size:11px;
letter-spacing:.05em;text-transform:uppercase;color:var(--mut);border-bottom:1px solid var(--bd);z-index:2}
.item{display:grid;grid-template-columns:1fr auto;gap:1px 8px;padding:6px 12px;
border-bottom:1px solid #F0EEE8;cursor:pointer;font-size:13px}
.item:hover{background:var(--row)}
.item.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--acc)}
.item .m{font-weight:500}
.item .s{font-variant-numeric:tabular-nums;font-weight:600;color:var(--acc);text-align:right}
.item .b{grid-column:1;font-size:11px;color:var(--mut)}
main{flex:1;display:grid;grid-template-columns:1fr 400px;min-width:0;min-height:0}
.pane{min-height:0;display:flex;flex-direction:column;border-right:1px solid var(--bd)}
.pane:last-child{border-right:0}
.ph{flex:0 0 auto;padding:8px 16px;border-bottom:1px solid var(--bd);background:var(--card);
font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);font-weight:600;
display:flex;gap:8px;align-items:center}
.ph .r{margin-left:auto;text-transform:none;letter-spacing:0;font-weight:400}
.body{flex:1;overflow:auto;padding:18px 26px}
#doc{max-width:74ch;line-height:1.6}
#doc h1,#doc h2,#doc h3{color:var(--acc);margin:1.3em 0 .4em;line-height:1.25}
#doc h1{font-size:20px}#doc h2{font-size:16px}#doc h3{font-size:14px}
#doc p,#doc li{margin:0 0 .6em}
#doc code{background:var(--row);border:1px solid var(--bd);border-radius:3px;padding:0 3px;font-size:12.5px}
#doc pre{background:var(--row);border:1px solid var(--bd);border-radius:6px;padding:10px;overflow:auto}
#doc table{border-collapse:collapse;font-size:13px}#doc td,#doc th{border:1px solid var(--bd);padding:3px 7px}
mark{background:#FBE3D6;border-radius:3px;padding:0 2px;color:inherit;
box-shadow:0 0 0 2px #F3BF9C inset}
.claim{border-bottom:1px solid #F0EEE8;padding:9px 14px;cursor:pointer}
.claim:hover{background:var(--row)}
.claim.sel{background:var(--soft);box-shadow:inset 3px 0 0 var(--acc)}
.claim.pin{background:#FCFBF7}
.claim.pin.sel{background:var(--soft)}
.chead{display:flex;gap:8px;align-items:baseline}
.chead .id{font-size:11px;color:var(--acc);font-variant-numeric:tabular-nums;font-weight:600}
.chead .sec{font-size:11px;color:var(--mut)}
.chead .sc{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700;font-size:14px}
.sc.hi{color:var(--okf)}.sc.mid{color:var(--warnf)}.sc.lo{color:var(--dangf)}
.ctext{font-size:12.5px;margin-top:3px;line-height:1.45}
.creason{font-size:12px;color:var(--sec);margin-top:5px;line-height:1.45}
.cquote{font-size:12px;margin-top:5px;padding-left:9px;border-left:2px solid var(--acc);color:var(--ink)}
.noq{font-size:12px;margin-top:5px;color:var(--dangf);background:var(--dang);border-radius:4px;padding:3px 7px;display:inline-block}
.chips{display:flex;flex-wrap:wrap;gap:4px;padding:8px 10px}
.chip{border:1px solid var(--bd);background:transparent;border-radius:99px;padding:2px 9px;font-size:11px;color:var(--sec)}
.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
.meta{display:flex;flex-wrap:wrap;gap:6px;padding:0 0 12px;margin-bottom:12px;border-bottom:1px solid var(--bd)}
.badge{border-radius:99px;padding:1px 8px;font-size:11px;background:var(--soft);color:var(--acch)}
.badge.n{background:#F0EEE8;color:var(--sec)}
.badge.g{background:var(--ok);color:var(--okf)}
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Provider-swap reports</title>
<style>__CSS__</style></head>
<body>
<header>
  <h1>Provider-swap reports</h1>
  <span class="note">the data is identical except OpenAI&rarr;Anthropic and Azure&rarr;AWS</span>
  <span class="sp"></span>
  <button class="tab" id="wording">show original wording</button>
  <span class="note" id="stat"></span>
</header>
<div id="wrap">
  <aside>
    <div class="chips" id="chips"></div>
    <div id="list"></div>
  </aside>
  <main>
    <section class="pane">
      <div class="ph">the report<span class="r" id="rkey"></span></div>
      <div class="body"><div class="meta" id="meta"></div><div id="doc"></div></div>
    </section>
    <section class="pane">
      <div class="ph">findings<span class="r">attribution six pinned</span></div>
      <div class="body" style="padding:0"><div id="claims"></div></div>
    </section>
  </main>
</div>
<script>const BOOT = __BOOT__;</script>
<script>__JS__</script>
</body></html>
"""
JS = r"""
'use strict';
const fileURL = p => '/file?p=' + encodeURIComponent(p);
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c;
  if (x != null) e.textContent = x; return e; };
let D = null, sel = null, selClaim = null, cache = {}, cur = null;
let filters = new Set(), showOriginal = false;

const TRANS = {'’': "'", '‘': "'", '“': '"', '”': '"',
               '—': '-', '–': '-', ' ': ' '};
/* Same folding the builder documents: quotes, dashes, markdown emphasis and runs of
   whitespace all differ between what a judge copied and what the file holds. */
function norm(s) {
  let out = '', prevSpace = true;
  for (const ch of s) {
    let c = (TRANS[ch] || ch).toLowerCase();
    if ('*`_'.includes(c)) continue;
    if (/\s/.test(c)) { if (prevSpace) continue; c = ' '; prevSpace = true; }
    else prevSpace = false;
    out += c;
  }
  return out;
}

/* --- a small markdown renderer: headings, lists, code, emphasis, tables left as text --- */
function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function inline(s) {
  return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<i>$2</i>');
}
function render(md) {
  const out = []; let inCode = false, list = null;
  for (const raw of md.split('\n')) {
    if (raw.trim().startsWith('```')) {
      if (inCode) { out.push('</pre>'); inCode = false; }
      else { if (list) { out.push(`</${list}>`); list = null; } out.push('<pre>'); inCode = true; }
      continue;
    }
    if (inCode) { out.push(esc(raw)); continue; }
    const h = raw.match(/^(#{1,6})\s+(.*)$/);
    if (h) { if (list) { out.push(`</${list}>`); list = null; }
      out.push(`<h${Math.min(h[1].length, 3)}>${inline(h[2])}</h${Math.min(h[1].length, 3)}>`); continue; }
    const li = raw.match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
    if (li) { const want = /^\d/.test(li[1]) ? 'ol' : 'ul';
      if (list !== want) { if (list) out.push(`</${list}>`); out.push(`<${want}>`); list = want; }
      out.push(`<li>${inline(li[2])}</li>`); continue; }
    if (list) { out.push(`</${list}>`); list = null; }
    if (raw.trim()) out.push(`<p>${inline(raw)}</p>`);
  }
  if (list) out.push(`</${list}>`);
  if (inCode) out.push('</pre>');
  return out.join('\n');
}

/* --- highlight the judge's quote inside the rendered document --- */
function clearMarks() {
  document.querySelectorAll('#doc mark').forEach(m => {
    const t = document.createTextNode(m.textContent);
    m.parentNode.replaceChild(t, m);
  });
}
function highlight(quote) {
  clearMarks();
  if (!quote || !quote.trim()) return false;
  const want = norm(quote).trim();
  if (want.length < 8) return false;
  const walker = document.createTreeWalker(document.getElementById('doc'), NodeFilter.SHOW_TEXT);
  const nodes = []; let n;
  while ((n = walker.nextNode())) nodes.push(n);
  /* the judge quotes across element boundaries, so match on the concatenated text and
     then map the hit back onto whichever nodes it spans */
  let flat = '', map = [];
  nodes.forEach((node, i) => {
    const t = norm(node.nodeValue);
    for (let k = 0; k < t.length; k++) map.push([i, k]);
    flat += t;
  });
  const at = flat.indexOf(want);
  if (at < 0) return false;
  const first = map[at], last = map[at + want.length - 1];
  for (let i = first[0]; i <= last[0]; i++) {
    const node = nodes[i];
    const mark = document.createElement('mark');
    node.parentNode.replaceChild(mark, node);
    mark.appendChild(node);
  }
  const m = document.querySelector('#doc mark');
  if (m) m.scrollIntoView({block: 'center', behavior: 'smooth'});
  return true;
}

/* --- sidebar --- */
function visible() {
  return D.reports.filter(r => !filters.size || filters.has(r.group));
}
function paintChips() {
  const box = document.getElementById('chips'); box.replaceChildren();
  [...new Set(D.reports.map(r => r.group))].sort().forEach(g => {
    const c = el('button', 'chip' + (filters.has(g) ? ' on' : ''), g);
    c.onclick = () => { filters.has(g) ? filters.delete(g) : filters.add(g);
      paintChips(); paintList(); };
    box.append(c);
  });
}
function paintList() {
  const box = document.getElementById('list'); box.replaceChildren();
  let group = null;
  visible().forEach(r => {
    if (r.group !== group) { group = r.group; box.append(el('div', 'ghd', group)); }
    const it = el('div', 'item' + (sel === r.key ? ' sel' : ''));
    it.append(el('span', 'm', r.model), el('span', 's', r.attrib.toFixed(2)),
              el('span', 'b', `${r.budget}m · ${r.agent} · overall ${r.overall.toFixed(2)}`));
    it.onclick = () => { sel = r.key; paintList(); open(r); };
    box.append(it);
  });
}

/* --- the report and its findings --- */
async function open(r) {
  cur = r;
  document.getElementById('rkey').textContent = r.key;
  if (!cache[r.key]) {
    const res = await fetch(fileURL(D.dir + '/' + r.key + '.json'));
    cache[r.key] = await res.json();
  }
  const meta = document.getElementById('meta'); meta.replaceChildren();
  meta.append(el('span', 'badge', r.model), el('span', 'badge n', r.budget + ' min'),
              el('span', 'badge n', r.agent), el('span', 'badge n', r.words + ' words'),
              el('span', r.group === 'own lab named' ? 'badge g' : 'badge n', r.group),
              el('span', 'badge n', 'attribution ' + r.attrib.toFixed(2)));
  document.getElementById('doc').innerHTML = render(cache[r.key].text);
  selClaim = null;
  paintClaims();
}
function scoreClass(v) { return v >= 0.7 ? 'hi' : v >= 0.4 ? 'mid' : 'lo'; }
function paintClaims() {
  const box = document.getElementById('claims'); box.replaceChildren();
  if (!cur) return;
  const S = cache[cur.key].scores;
  D.order.forEach(cid => {
    const c = D.claims[cid], v = S[cid];
    const pin = D.attrib.includes(cid);
    const div = el('div', 'claim' + (pin ? ' pin' : '') + (selClaim === cid ? ' sel' : ''));
    const h = el('div', 'chead');
    h.append(el('span', 'id', cid), el('span', 'sec', c.section),
             el('span', 'sc ' + scoreClass(v.score), v.score.toFixed(1)));
    div.append(h);
    div.append(el('div', 'ctext', showOriginal ? c.original : (c.swapped || c.original)));
    if (selClaim === cid) {
      if (v.quote && v.quote.trim()) div.append(el('div', 'cquote', '“' + v.quote + '”'));
      else div.append(el('div', 'noq', 'the judge quoted nothing from the report'));
      if (v.reason) div.append(el('div', 'creason', v.reason));
    }
    div.onclick = () => {
      selClaim = selClaim === cid ? null : cid;
      paintClaims();
      if (selClaim) {
        const ok = highlight(v.quote);
        if (!ok) clearMarks();
      } else clearMarks();
    };
    box.append(div);
    if (pin && cid === D.attrib[D.attrib.length - 1]) {
      const sep = el('div', 'ghd', 'the other 32 findings'); box.append(sep);
    }
  });
}

async function boot() {
  D = await (await fetch(fileURL(BOOT.payload))).json();
  document.getElementById('stat').textContent =
    `${D.reports.length} reports · judge ${D.judge}`;
  document.getElementById('wording').onclick = () => {
    showOriginal = !showOriginal;
    document.getElementById('wording').textContent =
      showOriginal ? 'show swapped wording' : 'show original wording';
    document.getElementById('wording').classList.toggle('on', showOriginal);
    paintClaims();
  };
  paintChips(); paintList();
  if (D.reports.length) { sel = D.reports[0].key; paintList(); open(D.reports[0]); }
  addEventListener('keydown', ev => {
    if (ev.target.tagName === 'INPUT') return;
    const rows = visible(); const i = rows.findIndex(r => r.key === sel);
    if (ev.key === 'j' || ev.key === 'ArrowDown') { ev.preventDefault();
      const r = rows[Math.min(rows.length - 1, i + 1)]; sel = r.key; paintList(); open(r); }
    if (ev.key === 'k' || ev.key === 'ArrowUp') { ev.preventDefault();
      const r = rows[Math.max(0, i - 1)]; sel = r.key; paintList(); open(r); }
  });
}
boot();
"""


if __name__ == "__main__":
    main()
