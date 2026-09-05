#!/usr/bin/env python3
"""
Merge GPT-5.6 Sol snippet extractions into validation_data.json and regenerate validation.html.
Model-generic: renders one panel per model in MODELS.

Reads:  ../report/claims.json, ../reports/<stem>.scores.json, snippets/{human,<key>}.json
Writes: validation_data.json  and  validation.html
"""
import json
from pathlib import Path

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)
LEGACY = _pl.Path(__file__).resolve().parent

HERE = Path(__file__).parent

# key, display title, scores-file stem in ../reports/
MODELS = [
    ("gpt",   "GPT-5.6 Sol",      "gpt_5_6_sol"),
    ("opus",  "Claude Opus 5",    "opus_5"),
    ("haiku", "Claude Haiku 4.5", "haiku"),
    ("luna",  "GPT-5.6 Luna",     "luna"),
]

claims = json.loads((CLAIMS / "claims.json").read_text())["claims"]


def load_snip(name):
    p = SNIPPETS / f"{name}.json"
    return json.loads(p.read_text()).get("claims", {}) if p.exists() else {}


def load_scores(stem):
    p = ROOT / "reports" / f"{stem}.scores.json"
    return json.loads(p.read_text()).get("scores", {}) if p.exists() else {}


HUMAN = load_snip("human")
SNIP = {k: load_snip(k) for k, _, _ in MODELS}
SCORE = {k: load_scores(stem) for k, _, stem in MODELS}


def field(snip, cid, key):
    r = snip.get(cid) or {}
    if not r.get("present", False):
        return ""
    return (r.get(key) or "").strip()


emb = {"claims": [], "reports": {k: {"title": t} for k, t, _ in MODELS},
       "source": "snippets + prefill scores from GPT-5.6 Sol"}
for c in claims:
    cid = c["id"]
    entry = {"id": cid, "level": c["level"], "section": c["section"], "derivable": c["derivable"],
             "stratum": c["stratum"], "claim": c["claim"], "reference": c["dump_check"], "trap": c.get("trap", ""),
             "human": {"context": field(HUMAN, cid, "context") or field(HUMAN, cid, "quote"),
                       "highlight": field(HUMAN, cid, "highlight") or field(HUMAN, cid, "quote")},
             "models": {}}
    for k, _, _ in MODELS:
        pf = (SCORE[k].get(cid) or {}).get("score", 0)
        entry["models"][k] = {
            "context": field(SNIP[k], cid, "context") or field(SNIP[k], cid, "quote"),
            "highlight": field(SNIP[k], cid, "highlight") or field(SNIP[k], cid, "quote"),
            "present": bool((SNIP[k].get(cid) or {}).get("present")),
            "prefill": pf,
        }
    emb["claims"].append(entry)

(LEGACY / "validation_data.json").write_text(json.dumps(emb, ensure_ascii=False))
raw = (LEGACY / "validation_data.json").read_text()
embed = "VDATA=" + raw.replace("</script", "<\\/script").replace("</", "<\\/") + ";"

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim Validation</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--mut:#999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;
--miss:#991B1B;--miss-bg:#FEE2E2;--part:#92400E;--part-bg:#FEF3C7;--full:#065F46;--full-bg:#D1FAE5;--blue:#4A6B8A;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0;font-size:14px;line-height:1.5}
.wrap{max-width:1250px;margin:0 auto;padding:16px 24px 60px}
header{position:sticky;top:0;background:var(--bg);z-index:10;padding:12px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{color:var(--accent);font-size:18px;margin:0}
.nav-btn{border:1px solid var(--border);background:var(--card);border-radius:8px;padding:6px 12px;font-size:15px;cursor:pointer;font-weight:700}
.nav-btn:hover{border-color:var(--accent);color:var(--accent)}
.prog{font-weight:700;font-variant-numeric:tabular-nums}
.counter{font-size:12px;color:var(--ink2)}
.spacer{flex:1}
.save{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:7px 14px;font-weight:700;cursor:pointer}
.save:hover{background:var(--accent2)}
.ghost{background:var(--card);color:var(--ink2);border:1px solid var(--border);border-radius:8px;padding:7px 12px;font-weight:600;cursor:pointer}
.claim-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin:16px 0}
.cc-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin-bottom:8px}
.lvl{font-weight:800;font-size:11px;color:#fff;border-radius:5px;padding:1px 7px}
.lvl.l1{background:#4A6B8A}.lvl.l2{background:#2E7D6B}.lvl.l3{background:var(--accent)}.lvl.l4{background:#7A5AA0}
.tag{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;font-weight:700}
.t-yes{background:var(--full-bg);color:var(--full)}.t-partly{background:var(--part-bg);color:var(--part)}.t-no{background:var(--miss-bg);color:var(--miss)}
.claim-txt{font-size:16px;font-weight:700;margin:4px 0 10px}
.ref{background:var(--soft);border-radius:8px;padding:10px 12px;font-size:13px;margin:8px 0}
.ref b{color:var(--accent2)}
.auto{font-size:11px;color:var(--mut);margin:6px 0 2px}
.quote{background:var(--row);border-left:3px solid var(--border);border-radius:0 6px 6px 0;padding:8px 12px;font-size:13px;white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;max-height:260px;overflow:auto;margin-top:4px}
mark{background:#ffe08a;color:#3a2c00;padding:0 1px;border-radius:2px}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
@media(max-width:920px){.panels{grid-template-columns:1fr}}
.panel{border:1px solid var(--border);border-radius:10px;padding:13px;background:var(--card)}
.model-tag{font-size:11px;font-weight:700;color:#fff;padding:2px 8px;border-radius:5px}
.mt-gpt{background:#2E7D6B}.mt-opus{background:var(--accent)}.mt-haiku{background:#7A5AA0}.mt-luna{background:#4A6B8A}
.btns{display:flex;gap:8px;margin:8px 0}
.vb{flex:1;border:2px solid var(--border);background:var(--card);border-radius:8px;padding:8px 0;font-weight:800;font-size:12px;cursor:pointer;color:var(--ink2)}
.vb:hover{border-color:var(--ink2)}
.vb.miss.on{background:var(--miss-bg);border-color:var(--miss);color:var(--miss)}
.vb.part.on{background:var(--part-bg);border-color:var(--part);color:var(--part)}
.vb.full.on{background:var(--full-bg);border-color:var(--full);color:var(--full)}
.noquote{color:var(--mut);font-style:italic;font-size:13px;padding:8px 0}
textarea{width:100%;border:1px solid var(--border);border-radius:8px;padding:8px;font-family:inherit;font-size:13px;resize:vertical;min-height:44px;margin-top:8px}
.badge-val{font-size:11px;font-weight:700;padding:1px 7px;border-radius:5px;background:var(--full-bg);color:var(--full);margin-left:6px}
.badge-un{font-size:11px;font-weight:700;padding:1px 7px;border-radius:5px;background:#eee;color:#888;margin-left:6px}
.badge-abs{font-size:11px;font-weight:700;padding:1px 7px;border-radius:5px;background:var(--miss-bg);color:var(--miss);margin-left:6px}
.jump{border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px}
.hint{font-size:11px;color:var(--mut)}
.legend{font-size:11px;color:var(--ink2);display:flex;gap:12px}
.dot{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:middle;margin-right:4px}
.interest{display:flex;align-items:stretch;gap:12px;margin:22px 0 6px;padding-top:16px;border-top:1px solid var(--border)}
.interest .il{font-size:14px;color:var(--ink2);font-weight:700;align-self:center;flex:none}
.ib{flex:1;border:3px solid var(--border);background:var(--card);border-radius:12px;padding:20px 16px;font-size:19px;font-weight:800;color:var(--ink2);cursor:pointer}
.ib:hover{border-color:var(--ink2)}
.ib.int.on{background:#EDE7F6;border-color:#5B4B8A;color:#4A3B76}
.ib.neu.on{background:#eee;border-color:#888;color:#555}
.ib.not.on{background:#F1E4E0;border-color:#9C4A2D;color:#9C4A2D}
</style></head>
<body>
<header>
  <h1>Claim Validation</h1>
  <button class="nav-btn" id="prev">&larr;</button>
  <span class="prog" id="prog">1 / 68</span>
  <button class="nav-btn" id="next">&rarr;</button>
  <select class="jump" id="jump"></select>
  <span class="counter" id="counter"></span>
  <span class="spacer"></span>
  <span class="legend"><span><span class="dot" style="background:var(--miss)"></span>miss</span><span><span class="dot" style="background:var(--part)"></span>partial</span><span><span class="dot" style="background:var(--full)"></span>full</span></span>
  <button class="ghost" id="copy">Copy JSON</button>
  <button class="save" id="save">Save JSON</button>
</header>
<div class="wrap">
  <div class="claim-card">
    <div class="cc-head" id="cchead"></div>
    <div class="claim-txt" id="claimtxt"></div>
    <div class="ref" id="ref"></div>
    <div id="humanwrap"></div>
  </div>
  <div class="panels" id="panels"></div>
  <div class="interest" id="interest"></div>
  <p class="hint">&larr;/&rarr; navigate &middot; 1/2/3 interest (not/neutral/interesting). Snippets &amp; prefill scores by GPT-5.6 Sol. Autosaves locally; Save JSON to export.</p>
</div>
<script>
__EMBED__
var MKEYS=Object.keys(VDATA.reports);
var LS="claimval_v3";
var V={}; try{V=JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){V={}}
VDATA.claims.forEach(function(c){
  if(!V[c.id]) V[c.id]={};
  if(!V[c.id].models) V[c.id].models={};
  MKEYS.forEach(function(m){ if(!V[c.id].models[m]) V[c.id].models[m]={score:c.models[m].prefill,note:"",validated:false,auto:c.models[m].prefill}; });
  if(V[c.id].interest===undefined) V[c.id].interest=null;
});
var i=0;
function esc(s){return (s||"").replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]});}
function hl(text,phrase){var h=esc(text||"");if(!phrase)return h;var p=esc(phrase).trim();if(p.length<3)return h;
  var re;try{re=new RegExp('('+p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','g');}catch(e){return h;}return h.replace(re,'<mark>$1</mark>');}
function save(){try{localStorage.setItem(LS,JSON.stringify(V))}catch(e){}}
function counts(){var v=0,t=VDATA.claims.length*MKEYS.length,ic=0;VDATA.claims.forEach(function(c){MKEYS.forEach(function(m){if(V[c.id].models[m].validated)v++});if(V[c.id].interest==='interesting')ic++;});return v+" / "+t+" validated · "+ic+" interesting";}
function label(s){return s===0?"MISS":s===1?"PARTIAL":s===2?"FULL":"—";}
function interestBar(c){var v=V[c.id].interest;
  return '<span class="il">Interest:</span>'
   +'<button class="ib not'+(v==='not'?' on':'')+'" data-int="not">Not interesting</button>'
   +'<button class="ib neu'+(v==='neutral'?' on':'')+'" data-int="neutral">Neutral</button>'
   +'<button class="ib int'+(v==='interesting'?' on':'')+'" data-int="interesting">★ Interesting</button>';}
function panel(m,c){
  var st=V[c.id].models[m]; var md=c.models[m]; var q=md.context;
  var badge = st.validated?'<span class="badge-val">validated</span>':'<span class="badge-un">auto: '+label(st.auto)+'</span>';
  var abs = (!md.present)?'<span class="badge-abs">not found</span>':'';
  var qhtml = q ? '<div class="quote">'+hl(q,md.highlight)+'</div>' : '<div class="noquote">GPT-5.6 Sol found no passage for this claim in this report.</div>';
  return '<div class="panel"><div class="cc-head" style="margin:0 0 6px"><span class="model-tag mt-'+m+'">'+VDATA.reports[m].title+'</span>'+badge+abs+'</div>'
    + qhtml
    + '<div class="btns">'
    + '<button class="vb miss'+(st.score===0?" on":"")+'" data-m="'+m+'" data-s="0">Miss</button>'
    + '<button class="vb part'+(st.score===1?" on":"")+'" data-m="'+m+'" data-s="1">Partial</button>'
    + '<button class="vb full'+(st.score===2?" on":"")+'" data-m="'+m+'" data-s="2">Full</button>'
    + '</div>'
    + '<textarea data-note="'+m+'" placeholder="Notes on '+VDATA.reports[m].title+'...">'+esc(st.note)+'</textarea></div>';
}
function render(){
  var c=VDATA.claims[i];
  document.getElementById('prog').textContent=(i+1)+" / "+VDATA.claims.length;
  document.getElementById('counter').textContent=counts();
  document.getElementById('jump').value=String(i);
  var strat=c.stratum.replace('_',' ');
  document.getElementById('cchead').innerHTML='<span class="lvl l'+c.level+'">L'+c.level+'</span><b>'+c.id+'</b><span>&middot; '+esc(c.section)+'</span><span class="tag t-'+c.derivable+'">derivable: '+c.derivable+'</span><span>&middot; '+strat+'</span>';
  document.getElementById('claimtxt').textContent=c.claim;
  document.getElementById('ref').innerHTML='<b>Verified reference (dump):</b> '+esc(c.reference)+(c.trap?'<br><b>Grader trap:</b> '+esc(c.trap):'');
  document.getElementById('humanwrap').innerHTML = c.human.context ? '<div class="auto">Human report passage:</div><div class="quote">'+hl(c.human.context,c.human.highlight)+'</div>' : '<div class="auto">Human report passage: <i>none found by GPT-5.6 Sol.</i></div>';
  document.getElementById('panels').innerHTML=MKEYS.map(function(m){return panel(m,c);}).join('');
  document.getElementById('interest').innerHTML=interestBar(c);
  wire();
}
function wire(){
  [].forEach.call(document.querySelectorAll('.vb'),function(b){b.onclick=function(){
    var c=VDATA.claims[i],m=b.dataset.m,s=+b.dataset.s; V[c.id].models[m].score=s; V[c.id].models[m].validated=true; save(); render();};});
  [].forEach.call(document.querySelectorAll('textarea[data-note]'),function(t){t.oninput=function(){
    var c=VDATA.claims[i]; V[c.id].models[t.dataset.note].note=t.value; V[c.id].models[t.dataset.note].validated=true; save();
    document.getElementById('counter').textContent=counts();};});
  [].forEach.call(document.querySelectorAll('.ib'),function(b){b.onclick=function(){
    var c=VDATA.claims[i]; V[c.id].interest=(V[c.id].interest===b.dataset.int?null:b.dataset.int); save(); render();};});
}
function setInterest(v){var c=VDATA.claims[i];V[c.id].interest=(V[c.id].interest===v?null:v);save();render();}
function go(d){i=(i+d+VDATA.claims.length)%VDATA.claims.length;render();}
document.getElementById('prev').onclick=function(){go(-1)};
document.getElementById('next').onclick=function(){go(1)};
var jsel=document.getElementById('jump');
VDATA.claims.forEach(function(c,idx){var o=document.createElement('option');o.value=idx;o.textContent=c.id+" (L"+c.level+") "+c.section;jsel.appendChild(o);});
jsel.onchange=function(){i=+jsel.value;render()};
document.addEventListener('keydown',function(e){
  if(/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))return;
  if(e.key==='ArrowLeft')go(-1); else if(e.key==='ArrowRight')go(1);
  else if(e.key==='1')setInterest('not');else if(e.key==='2')setInterest('neutral');else if(e.key==='3')setInterest('interesting');
});
function exportObj(){
  var out={validated_at:new Date().toISOString(),n_claims:VDATA.claims.length,models:MKEYS,verdicts:[]};
  VDATA.claims.forEach(function(c){var row={id:c.id,level:c.level,section:c.section,claim:c.claim,interest:V[c.id].interest,models:{}};
    MKEYS.forEach(function(m){var st=V[c.id].models[m];row.models[m]={score:st.score,auto:st.auto,note:st.note,validated:st.validated};});
    out.verdicts.push(row);});
  return out;
}
document.getElementById('save').onclick=function(){
  var blob=new Blob([JSON.stringify(exportObj(),null,1)],{type:"application/json"});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download="claim_validation.json";a.click();};
document.getElementById('copy').onclick=function(){navigator.clipboard&&navigator.clipboard.writeText(JSON.stringify(exportObj(),null,1));this.textContent="Copied";var t=this;setTimeout(function(){t.textContent="Copy JSON"},1200);};
render();
</script>
</body></html>'''

HTML = HTML.replace("__EMBED__", embed)
(VIEWERS / "validation.html").write_text(HTML)
print("wrote validation_data.json and validation.html for models:", [k for k, _, _ in MODELS])
print("literal </script> count:", HTML.count("</script>"))
