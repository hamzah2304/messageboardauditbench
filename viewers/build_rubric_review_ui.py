#!/usr/bin/env python3
"""Build viewers/rubric_review.html — approve, reject or rewrite each proposed rubric change.

Reads benchmark/rubric_review/suggestions.json (S1..S7, each with a problem, the change,
and a before/after pair of rubric text) and emits one self-contained page:

- one card per suggestion, in a single reading column, with the before text muted on the
  left and the proposed replacement on the right as a real editable field;
- approve / reject / needs work per suggestion, plus a comment;
- the edit is kept separately from the proposal (after_original beside after_edited), so
  the original wording is never lost and a one-click revert is always available;
- the page autosaves to benchmark/rubric_review/decisions.json through the html-viewer's
  POST /save endpoint (localStorage mirror when the server is unreachable) — the same
  persistence mechanism as viewers/build_audit_ui.py.
"""
import json, sys, pathlib, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paths import ROOT, VIEWERS

OUT = VIEWERS / "rubric_review.html"
SUGGESTIONS = ROOT / "benchmark" / "rubric_review" / "suggestions.json"
DECISIONS = ROOT / "benchmark" / "rubric_review" / "decisions.json"


def main():
    src = json.loads(SUGGESTIONS.read_text())
    sugs = src["suggestions"]
    for s in sugs:
        for k in ("id", "title", "severity", "scope", "problem", "change", "before", "after"):
            s.setdefault(k, "")
        s.setdefault("evidence", [])
    data = {
        "decisions_path": str(DECISIONS),
        "generated": src.get("generated", ""),
        "audit_source": src.get("audit_source", ""),
        "suggestions": sugs,
        "built": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload))
    sev = {}
    for s in sugs:
        sev[s["severity"]] = sev.get(s["severity"], 0) + 1
    print(f"{OUT}: {len(sugs)} suggestions ({', '.join(f'{k} {v}' for k, v in sorted(sev.items()))}); "
          f"{OUT.stat().st_size/1e3:.1f} kB; decisions autosave to {DECISIONS}")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rubric review — MessageBoardAuditBench</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666666;--mut:#999999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok:#065F46;--warn-bg:#FEF3C7;--warn:#92400E;--dang-bg:#FEE2E2;--dang:#991B1B;--grey-bg:#ECEAE3;--grey:#555;
--serif:Palatino,"Palatino Linotype","Palatino LT STD","Book Antiqua",Georgia,serif;
--mono:SFMono-Regular,Menlo,Consolas,Monaco,"Liberation Mono",monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box}
html,body{margin:0}
body{font-family:var(--sans);background:var(--bg);color:var(--ink);font-size:13px;line-height:1.5}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}

header{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--border);padding:8px 20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
h1{color:var(--accent);font-size:16px;margin:0;white-space:nowrap}
.sub{color:var(--mut);font-size:10.5px}
.stats{display:flex;gap:5px;flex-wrap:wrap;align-items:center;margin-left:auto}
.badge{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--soft);color:var(--accent2);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.dang{background:var(--dang-bg);color:var(--dang)}.badge.grey{background:var(--grey-bg);color:var(--grey)}
#save{font-size:11px;color:var(--mut);min-width:160px;text-align:right}#save.err{color:var(--dang);font-weight:600}
#export{padding:5px 12px;border:1px solid var(--border);border-radius:7px;background:var(--card);color:var(--ink2);cursor:pointer;font-weight:600;font-size:12px;font-family:inherit}
#export:hover{background:var(--soft);border-color:var(--accent);color:var(--accent2)}

#layout{display:grid;grid-template-columns:170px minmax(0,1fr);gap:0;align-items:start}
#rail{position:sticky;top:52px;padding:16px 8px 16px 20px;display:flex;flex-direction:column;gap:3px}
#rail .rl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.jump{display:flex;gap:7px;align-items:center;padding:4px 8px;border-radius:7px;border:1px solid transparent;background:transparent;cursor:pointer;font-family:inherit;font-size:11.5px;color:var(--ink2);text-align:left;width:100%}
.jump:hover{background:var(--card);border-color:var(--border)}
.jump.sel{background:var(--soft);border-color:var(--accent);color:var(--accent2);font-weight:600}
.jump .dot{width:9px;height:9px;border-radius:50%;background:var(--grey-bg);border:1px solid #D5D2C9;flex:none}
.jump .dot.approve{background:#34A87A;border-color:#2A8A63}
.jump .dot.reject{background:#D9534F;border-color:#B34340}
.jump .dot.needs{background:#E4A93A;border-color:#C08B26}
.jump .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#rail .hint{font-size:10px;color:var(--mut);margin-top:10px;line-height:1.6}
kbd{background:var(--soft);border:1px solid var(--border);border-radius:4px;padding:0 4px;font-size:10px;font-family:inherit}

#col{max-width:1000px;margin:0 auto;padding:18px 20px 50vh;display:flex;flex-direction:column;gap:16px}
.intro{color:var(--ink2);font-size:12.5px;max-width:70ch}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px 20px 18px;scroll-margin-top:64px}
.card.focus{border-color:var(--accent);box-shadow:0 0 0 2px var(--soft)}
.card .hd{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.card h2{margin:0;font-size:16px;color:var(--ink);font-family:var(--serif);font-weight:700;line-height:1.3;flex:1 1 320px}
.scope{font-family:var(--mono);font-size:11px;color:var(--ink2);background:var(--row);border:1px solid var(--border);border-radius:5px;padding:1px 6px;margin-top:6px;display:inline-block;word-break:break-word}
.evi{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 0}
.evi .e{font-size:11px;background:var(--soft);color:var(--accent2);border-radius:6px;padding:2px 8px;line-height:1.5}
.evi .lab{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;align-self:center;margin-right:2px}
.prose{font-family:var(--serif);font-size:14.5px;line-height:1.62;color:var(--ink);margin:12px 0 0;max-width:74ch}
.prose.q{color:var(--ink2)}
.plab{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin:14px 0 -6px;font-family:var(--sans)}

.diff{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}
@media (max-width:1000px){.diff{grid-template-columns:1fr}#layout{grid-template-columns:1fr}
#rail{position:sticky;top:48px;flex-direction:row;overflow-x:auto;padding:6px 12px;background:var(--bg);border-bottom:1px solid var(--border);z-index:15}
#rail .rl,#rail .hint{display:none}.jump{width:auto;flex:none}}
.side{display:flex;flex-direction:column;min-width:0}
.side .sl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;display:flex;gap:8px;align-items:center}
.side .sl .rev{margin-left:auto;font-size:10.5px;color:var(--accent);cursor:pointer;text-transform:none;letter-spacing:0;font-weight:600;background:none;border:0;font-family:inherit;padding:0}
.side .sl .rev:hover{text-decoration:underline}
.side .sl .ed{color:var(--warn);text-transform:none;letter-spacing:0;font-weight:600}
.before{background:var(--row);border:1px solid var(--border);border-radius:8px;padding:10px 12px;white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--mono);font-size:12px;line-height:1.65;color:var(--ink2);flex:1;min-height:60px}
.before.none{font-family:var(--sans);font-style:italic;color:var(--mut);white-space:normal}
textarea.after{background:#FFFDF8;border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-family:var(--mono);font-size:12px;line-height:1.65;color:var(--ink);width:100%;resize:vertical;min-height:60px;overflow:hidden}
textarea.after.edited{border-color:#E5CB7A;background:#FFFCF2}
textarea:focus{outline:2px solid var(--soft);border-color:var(--accent)}

.acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:16px;padding-top:12px;border-top:1px solid var(--border)}
.vb{padding:6px 14px;border:1px solid var(--border);border-radius:7px;background:transparent;cursor:pointer;font-size:12.5px;font-weight:600;color:var(--ink2);font-family:inherit}
.vb:hover{background:var(--row)}
.vb .k{font-size:10px;color:var(--mut);font-weight:400;margin-right:5px}
.vb.on.ok{background:var(--ok-bg);color:var(--ok);border-color:#9AD6BC}
.vb.on.dang{background:var(--dang-bg);color:var(--dang);border-color:#F0A6A6}
.vb.on.warn{background:var(--warn-bg);color:var(--warn);border-color:#E5CB7A}
.vb.on .k{color:inherit;opacity:.6}
.stamp{margin-left:auto;font-size:11px;color:var(--mut)}
textarea.cmt{width:100%;margin-top:10px;min-height:52px;border:1px solid var(--border);border-radius:7px;padding:8px 10px;font-family:var(--sans);font-size:12.5px;line-height:1.55;resize:vertical;background:#fff}
</style></head><body>
<header>
  <div><h1>Rubric review</h1><div class="sub" id="built"></div></div>
  <div class="stats" id="stats"></div>
  <button id="export" title="copy every decision to the clipboard as plain text">Copy decisions</button>
  <div id="save">loading&hellip;</div>
</header>
<div id="layout">
  <nav id="rail"></nav>
  <div id="col"></div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const DEC_PATH = D.decisions_path, LS_KEY = 'rubric_review:' + DEC_PATH;
const SUGS = D.suggestions, SBY = Object.fromEntries(SUGS.map(s => [s.id, s]));
const STATUSES = [
  {v: 'approve', l: 'Approve', k: 'a', c: 'ok'},
  {v: 'reject', l: 'Reject', k: 'r', c: 'dang'},
  {v: 'needs', l: 'Needs work', k: 'n', c: 'warn'},
];
const SLAB = {approve: 'APPROVED', reject: 'REJECTED', needs: 'NEEDS WORK'};
const SEVC = {high: 'dang', medium: 'warn', low: 'grey'};

let state = {version: 1, updated_at: null, decisions: {}};
let focus = SUGS.length ? SUGS[0].id : null;

/* ---------- persistence (same mechanism as viewers/build_audit_ui.py) ---------- */
function fileURL(p) { return '/file?p=' + encodeURIComponent(p); }
function dec(id) { return state.decisions[id] || null; }
function blank(e) { return !e.status && !e.comment && (e.after_edited || '') === (e.after_original || ''); }
function setDec(id, patch) {
  const s = SBY[id], cur = state.decisions[id] || {after_original: s.after, after_edited: s.after};
  const e = Object.assign({}, cur, patch, {after_original: s.after, updated_at: new Date().toISOString()});
  for (const k of Object.keys(e)) if (e[k] === null || e[k] === false) delete e[k];
  if (e.after_edited == null) e.after_edited = s.after;
  if (blank(e)) delete state.decisions[id]; else state.decisions[id] = e;
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
    const r = await fetch('/save?p=' + encodeURIComponent(DEC_PATH), {method: 'POST', body});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    setStatus('saved to disk ' + new Date().toLocaleTimeString());
  } catch (e) { setStatus('NOT on disk (browser copy kept): ' + e.message, true); }
}
function merge(a, b) {
  const out = {version: 1, updated_at: null, decisions: {}};
  for (const src of [a, b]) { if (!src) continue;
    for (const [k, e] of Object.entries(src.decisions || {})) { const cur = out.decisions[k]; if (!cur || (e.updated_at || '') > (cur.updated_at || '')) out.decisions[k] = e; } }
  return out;
}
function sameContent(a, b) { const s = x => JSON.stringify(x.decisions || {}); return s(a) === s(b); }
async function load() {
  let server = null, local = null;
  try { const r = await fetch(fileURL(DEC_PATH)); if (r.ok) server = await r.json(); } catch (e) {}
  try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) {}
  state = merge(server, local);
  const n = Object.keys(state.decisions).length;
  if (server === null && local === null) setStatus('no saved decisions yet');
  else if (local && !sameContent(state, server || {})) scheduleSave();
  else setStatus('loaded ' + n + ' saved decisions (' + (server ? 'from disk' : 'browser copy only') + ')', !server);
}

/* ---------- helpers ---------- */
function el(tag, cls, text) { const x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; }
function finalText(id) { const e = dec(id); return e && e.after_edited != null ? e.after_edited : SBY[id].after; }
function isEdited(id) { return finalText(id) !== SBY[id].after; }
function grow(ta) { ta.style.height = 'auto'; ta.style.height = Math.max(60, ta.scrollHeight + 2) + 'px'; }

/* ---------- header ---------- */
function renderStats() {
  const box = document.getElementById('stats'); box.replaceChildren();
  const counts = {}; let decided = 0, edited = 0;
  for (const s of SUGS) { const e = dec(s.id); if (e && e.status) { decided++; counts[e.status] = (counts[e.status] || 0) + 1; } if (isEdited(s.id)) edited++; }
  box.appendChild(el('span', 'badge', decided + '/' + SUGS.length + ' decided'));
  for (const o of STATUSES) if (counts[o.v]) box.appendChild(el('span', 'badge ' + o.c, o.l + ' ' + counts[o.v]));
  if (edited) box.appendChild(el('span', 'badge grey', edited + ' edited'));
}

/* ---------- jump rail ---------- */
function renderRail() {
  const rail = document.getElementById('rail'); rail.replaceChildren();
  rail.appendChild(el('div', 'rl', 'Suggestions'));
  for (const s of SUGS) {
    const e = dec(s.id);
    const b = el('button', 'jump' + (s.id === focus ? ' sel' : ''));
    b.appendChild(el('span', 'dot' + (e && e.status ? ' ' + e.status : '')));
    b.appendChild(el('span', 't', s.id + ' · ' + s.title));
    b.title = s.title + (e && e.status ? ' — ' + SLAB[e.status] : '');
    b.onclick = () => { focus = s.id; jump(s.id); render(); };
    rail.appendChild(b);
  }
  const h = el('div', 'hint'); h.innerHTML =
    '<kbd>j</kbd>/<kbd>k</kbd> move · <kbd>a</kbd>/<kbd>r</kbd>/<kbd>n</kbd> approve / reject / needs work · <kbd>Esc</kbd> leave a text box';
  rail.appendChild(h);
}
function jump(id) { const c = document.getElementById('c-' + id); if (c) c.scrollIntoView({behavior: 'smooth', block: 'start'}); }

/* ---------- one suggestion ---------- */
function cardFor(s) {
  const e = dec(s.id) || {};
  const card = el('div', 'card' + (s.id === focus ? ' focus' : '')); card.id = 'c-' + s.id; card.dataset.id = s.id;
  card.onmousedown = () => { if (focus !== s.id) { focus = s.id; render(); } };

  const hd = el('div', 'hd');
  hd.appendChild(el('span', 'badge grey', s.id));
  hd.appendChild(el('h2', '', s.title));
  hd.appendChild(el('span', 'badge ' + (SEVC[s.severity] || 'grey'), s.severity));
  card.appendChild(hd);
  if (s.scope) card.appendChild(el('div', 'scope', s.scope));

  if (s.evidence && s.evidence.length) {
    const ev = el('div', 'evi'); ev.appendChild(el('span', 'lab', 'evidence'));
    for (const x of s.evidence) ev.appendChild(el('span', 'e', x));
    card.appendChild(ev);
  }
  if (s.problem) card.appendChild(el('div', 'prose', s.problem));
  if (s.change) { card.appendChild(el('div', 'plab', 'Proposed change')); card.appendChild(el('div', 'prose q', s.change)); }

  const diff = el('div', 'diff');
  const L = el('div', 'side'); const ll = el('div', 'sl'); ll.appendChild(el('span', '', 'Current')); L.appendChild(ll);
  if (s.before) L.appendChild(el('div', 'before', s.before));
  else L.appendChild(el('div', 'before none', 'Nothing to replace — this suggestion changes no rubric text.'));
  diff.appendChild(L);

  const R = el('div', 'side'); const rl = el('div', 'sl'); rl.appendChild(el('span', '', 'Proposed — edit freely'));
  if (isEdited(s.id)) {
    rl.appendChild(el('span', 'ed', 'edited'));
    const rev = el('button', 'rev', 'revert to the proposal');
    rev.onclick = () => { setDec(s.id, {after_edited: s.after}); render(); };
    rl.appendChild(rev);
  }
  R.appendChild(rl);
  const ta = el('textarea', 'after' + (isEdited(s.id) ? ' edited' : ''));
  ta.value = finalText(s.id);
  ta.placeholder = s.after ? '' : 'No text change proposed — write one here if you want to make this concrete.';
  ta.oninput = () => { grow(ta); const was = isEdited(s.id); setDec(s.id, {after_edited: ta.value}); if (isEdited(s.id) !== was) render(); else { renderStats(); } };
  R.appendChild(ta); diff.appendChild(R);
  card.appendChild(el('div', 'plab', 'Rubric text'));
  card.appendChild(diff);

  const acts = el('div', 'acts');
  for (const o of STATUSES) {
    const b = el('button', 'vb ' + o.c + (e.status === o.v ? ' on' : ''));
    b.appendChild(el('span', 'k', o.k)); b.appendChild(document.createTextNode(o.l));
    b.onclick = () => { focus = s.id; setDec(s.id, {status: e.status === o.v ? null : o.v}); render(); };
    acts.appendChild(b);
  }
  acts.appendChild(el('span', 'stamp', e.updated_at ? 'decided ' + new Date(e.updated_at).toLocaleString() : 'not decided yet'));
  card.appendChild(acts);

  const cm = el('textarea', 'cmt'); cm.value = e.comment || '';
  cm.placeholder = 'Comment — why this is right or wrong, what you would want instead…';
  cm.oninput = () => setDec(s.id, {comment: cm.value});
  card.appendChild(cm);
  return card;
}

function render() {
  const col = document.getElementById('col');
  const active = document.activeElement, ak = active && active.tagName === 'TEXTAREA'
    ? [active.closest('.card').dataset.id, active.className.split(' ')[0], active.selectionStart] : null;
  col.replaceChildren();
  const intro = el('div', 'intro', 'Seven changes to the grading rubric, proposed from the audit of '
    + D.audit_source + '. Approve, reject or mark each as needing work; rewrite the proposed text in place. '
    + 'Everything autosaves, and the original wording is kept beside your edit.');
  col.appendChild(intro);
  for (const s of SUGS) col.appendChild(cardFor(s));
  for (const ta of col.querySelectorAll('textarea.after')) grow(ta);
  if (ak) { const c = document.getElementById('c-' + ak[0]); const t = c && c.querySelector('textarea.' + ak[1]);
    if (t) { t.focus(); try { t.setSelectionRange(ak[2], ak[2]); } catch (e) {} } }
  renderRail(); renderStats();
}

/* ---------- export ---------- */
function exportText() {
  const out = ['Rubric review — ' + SUGS.length + ' suggestions from ' + D.audit_source,
               'exported ' + new Date().toLocaleString(), ''];
  for (const s of SUGS) {
    const e = dec(s.id) || {};
    out.push('=== ' + s.id + ' — ' + s.title);
    out.push('severity: ' + s.severity + '   scope: ' + s.scope);
    out.push('status: ' + (e.status ? SLAB[e.status] : 'UNDECIDED') + (isEdited(s.id) ? '   (text edited)' : ''));
    const txt = finalText(s.id);
    out.push(txt ? 'text:\n' + txt : 'text: (none)');
    if (e.comment) out.push('comment: ' + e.comment);
    out.push('');
  }
  return out.join('\n');
}
document.getElementById('export').onclick = async () => {
  const btn = document.getElementById('export'), text = exportText();
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch (err) {
    const t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select();
    try { ok = document.execCommand('copy'); } catch (e2) {}
    t.remove();
  }
  btn.textContent = ok ? 'Copied ✓' : 'Copy failed';
  setTimeout(() => { btn.textContent = 'Copy decisions'; }, 1600);
};

/* ---------- keyboard ---------- */
function move(d) {
  const i = SUGS.findIndex(s => s.id === focus);
  const j = Math.max(0, Math.min(SUGS.length - 1, (i < 0 ? 0 : i) + d));
  focus = SUGS[j].id; render(); jump(focus);
}
document.addEventListener('keydown', ev => {
  const t = ev.target, inBox = t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT');
  if (ev.key === 'Escape') { if (inBox) t.blur(); return; }
  if (inBox || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  if (ev.key === 'j') { ev.preventDefault(); move(1); return; }
  if (ev.key === 'k') { ev.preventDefault(); move(-1); return; }
  const o = STATUSES.find(x => x.k === ev.key);
  if (o && focus) { ev.preventDefault(); const e = dec(focus) || {}; setDec(focus, {status: e.status === o.v ? null : o.v}); render(); }
});

document.getElementById('built').textContent = SUGS.length + ' suggestions · from ' + D.audit_source + ' · built ' + D.built;
load().then(render);
</script></body></html>
'''


if __name__ == "__main__":
    main()
