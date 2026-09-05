#!/usr/bin/env python3
"""Approval UI for the report-grounded candidate claims in report/new_claims.json.

Every substantive highlighted comment is a candidate claim (comments == claims).
Reviewer approves/rejects (and can edit) each; the verbatim report quote is shown
as grounding, plus its coverage verdict (gap/partial => NEW rubric claim;
covered => restates an existing claim). Export JSON = approved claim objects
(with edits) + statuses, ready to feed the data-feasibility subagent pass.

Run:  cd hasan && python build_new_claims_ui.py   ->  new_claims.html
"""
import json
from pathlib import Path

ROOT = Path("/workspace/collusion")
HERE = ROOT / "messageboardauditbench/hasan"

data = json.loads((ROOT / "report/new_claims.json").read_text())
existing = json.loads((ROOT / "report/claims.json").read_text())["claims"]
exist_by_id = {c["id"]: c["claim"] for c in existing}

payload = {"meta": data["meta"], "claims": data["claims"], "existing": exist_by_id}
blob = json.dumps(payload, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Candidate Claims Review</title>
<style>
:root{
 --bg:#F4F3EE; --card:#FFFFFF; --border:#E0DDD4; --ink:#1A1A1A; --ink2:#666;
 --muted:#999; --accent:#C15F3C; --accent2:#9C4A2D; --soft:#FDF2EC; --row:#FAFAF7;
 --ok-bg:#D1FAE5; --ok-tx:#065F46; --warn-bg:#FEF3C7; --warn-tx:#92400E;
 --bad-bg:#FEE2E2; --bad-tx:#991B1B;
}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.wrap{max-width:1400px;margin:0 auto;padding:18px 26px}
h1{color:var(--accent);font-size:21px;margin:0 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 14px;max-width:1000px;line-height:1.4}
header.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0 12px;border-bottom:1px solid var(--border);
 display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.stat{font-size:13px;color:var(--ink2)}
.stat b{color:var(--ink);font-size:15px}
.pill{display:inline-block;padding:2px 9px;border-radius:11px;font-size:12px;font-weight:600}
.pill.ok{background:var(--ok-bg);color:var(--ok-tx)}
.pill.bad{background:var(--bad-bg);color:var(--bad-tx)}
.pill.pend{background:var(--warn-bg);color:var(--warn-tx)}
button{font-family:inherit;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--ink);
 border-radius:7px;padding:7px 13px;font-size:13px}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
button.primary:hover{background:var(--accent2)}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:7px;overflow:hidden}
.seg button{border:none;border-radius:0;border-right:1px solid var(--border);padding:6px 11px;background:var(--card)}
.seg button:last-child{border-right:none}
.seg button.on{background:var(--accent);color:#fff}
.layout{display:grid;grid-template-columns:320px 1fr;gap:18px;margin-top:14px}
.list{border:1px solid var(--border);border-radius:8px;background:var(--card);overflow:hidden;align-self:start;max-height:calc(100vh - 150px);overflow-y:auto}
.li{padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px}
.li:last-child{border-bottom:none}
.li:hover{background:var(--row)}
.li.active{background:var(--soft)}
.li.hidden{display:none}
.li .id{font-weight:600;color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:12px;min-width:34px}
.li .lbl{color:var(--ink2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.li .cov{font-size:10px;font-weight:700;padding:1px 5px;border-radius:4px;letter-spacing:.03em}
.cov.gap{background:#DBEAFE;color:#1E40AF}.cov.partial{background:var(--warn-bg);color:var(--warn-tx)}.cov.covered{background:#EDECE6;color:#666}
.dot{width:9px;height:9px;border-radius:50%;flex:none;background:#D5D2C9}
.dot.ok{background:#10B981}.dot.bad{background:#EF4444}
.card{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:20px 22px}
.lvbadge{display:inline-block;padding:2px 9px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;letter-spacing:.02em}
.lv1{background:#8A8F98}.lv2{background:#4F9D8C}.lv3{background:#6C6EF0}.lv4{background:#C15F3C}
.tag{display:inline-block;background:var(--soft);color:var(--accent2);border-radius:6px;padding:2px 9px;font-size:12px;font-weight:600;margin-left:6px}
.covbig{display:inline-block;padding:2px 10px;border-radius:6px;font-size:12px;font-weight:700;margin-left:6px}
.derv{font-size:12px;color:var(--ink2);margin-left:6px}
.claimtext{font-size:17px;line-height:1.45;margin:14px 0 4px;font-weight:500}
.claimtext[contenteditable=true]{outline:2px solid var(--accent);border-radius:6px;padding:6px 8px;background:#fff}
.edited{font-size:11px;color:var(--warn-tx);background:var(--warn-bg);padding:1px 7px;border-radius:9px;margin-left:8px}
.field{margin-top:14px}
.field .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:3px}
.field .v{font-size:14px;line-height:1.5;color:var(--ink)}
.quote{border-left:3px solid var(--accent);background:var(--soft);padding:9px 13px;border-radius:0 6px 6px 0;
 font-size:14px;line-height:1.5;color:#3a2a22;font-style:italic}
.refines{font-size:13px;color:var(--ink2);background:var(--row);border:1px solid var(--border);border-radius:6px;padding:8px 11px;line-height:1.5}
.refines code{color:var(--accent);font-weight:600}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.actions{display:flex;gap:10px;margin-top:20px;align-items:center;flex-wrap:wrap}
button.approve{border-color:#10B981;color:#065F46;font-weight:600}
button.approve.on{background:#10B981;color:#fff}
button.reject{border-color:#EF4444;color:#991B1B;font-weight:600}
button.reject.on{background:#EF4444;color:#fff}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
kbd{background:#fff;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 5px;font-size:11px;font-family:ui-monospace,monospace}
.src{font-size:12px;color:var(--ink2);margin-top:16px;padding-top:12px;border-top:1px dashed var(--border)}
textarea.note{width:100%;margin-top:6px;border:1px solid var(--border);border-radius:6px;padding:8px;font:inherit;font-size:13px;resize:vertical;min-height:46px}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
</style>

<div class="wrap">
 <h1>Candidate Claims Review</h1>
 <p class="sub" id="subtitle"></p>
 <header class="bar">
  <span class="stat">Showing <b id="s-shown">0</b>/<b id="s-total">0</b></span>
  <span class="pill ok">Approved <b id="s-ok">0</b></span>
  <span class="pill bad">Rejected <b id="s-bad">0</b></span>
  <span class="pill pend">Pending <b id="s-pend">0</b></span>
  <span class="seg" id="filter">
   <button data-f="all" class="on">All</button>
   <button data-f="new">New only</button>
   <button data-f="covered">Covered</button>
  </span>
  <button id="allok">Approve all</button>
  <button id="allno">Reject all</button>
  <button class="primary" id="save">Save approved JSON</button>
  <button id="copy">Copy JSON</button>
  <span class="hint"><kbd>j</kbd>/<kbd>k</kbd> move &nbsp; <kbd>a</kbd> approve &nbsp; <kbd>r</kbd> reject</span>
 </header>
 <div class="layout">
  <div class="list" id="list"></div>
  <div class="card" id="detail"></div>
 </div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const P = JSON.parse(document.getElementById('data').textContent);
const CLAIMS = P.claims, EXIST = P.existing, META = P.meta;
const LS = 'candclaims_review_v2';
let S = {};    // id -> {status, claim, note}
try{ S = JSON.parse(localStorage.getItem(LS)) || {}; }catch(e){ S = {}; }
let cur = 0, editing = false, filter = 'all';

const isNew = c => c.coverage !== 'covered';
function st(id){ if(!S[id]) S[id]={status:null, claim:null, note:''}; return S[id]; }
function persist(){ try{ localStorage.setItem(LS, JSON.stringify(S)); }catch(e){} }
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
document.getElementById('subtitle').textContent = META.purpose;
document.getElementById('s-total').textContent = CLAIMS.length;

function visible(c){ return filter==='all' || (filter==='new'&&isNew(c)) || (filter==='covered'&&!isNew(c)); }
function covLabel(c){
 if(c.coverage==='gap') return 'GAP &middot; new claim';
 if(c.coverage==='partial') return 'PARTIAL &middot; refines '+(c.maps_to||[]).join(', ');
 return 'COVERED by '+(c.maps_to||[]).join(', ');
}
function counts(){
 let ok=0,bad=0,shown=0;
 for(const c of CLAIMS){const s=st(c.id).status; if(s==='approved')ok++; else if(s==='rejected')bad++; if(visible(c))shown++;}
 document.getElementById('s-ok').textContent=ok;
 document.getElementById('s-bad').textContent=bad;
 document.getElementById('s-pend').textContent=CLAIMS.length-ok-bad;
 document.getElementById('s-shown').textContent=shown;
}
function renderList(){
 const el=document.getElementById('list'); el.innerHTML='';
 CLAIMS.forEach((c,i)=>{
  const s=st(c.id).status;
  const d=document.createElement('div'); d.className='li'+(i===cur?' active':'')+(visible(c)?'':' hidden');
  d.innerHTML='<span class="dot '+(s==='approved'?'ok':s==='rejected'?'bad':'')+'"></span>'+
    '<span class="id">'+c.id+'</span>'+
    '<span class="cov '+c.coverage+'">'+(c.coverage==='covered'?'COV':c.coverage.toUpperCase().slice(0,4))+'</span>'+
    '<span class="lbl">'+esc(c.section)+'</span>';
  d.onclick=()=>{cur=i;editing=false;render();};
  el.appendChild(d);
 });
}
function render(){
 counts(); renderList();
 const c=CLAIMS[cur], s=st(c.id);
 const shownClaim = s.claim!=null ? s.claim : c.claim;
 const covColors={gap:['#DBEAFE','#1E40AF'],partial:['#FEF3C7','#92400E'],covered:['#EDECE6','#666']}[c.coverage];
 const rid = c.proposed_id ? '<span class="tag mono">would add '+c.proposed_id+'</span>' : '';
 const mapsLinks = (c.maps_to||[]).map(id=>'<code>'+id+'</code>'+(EXIST[id]?' — '+esc(EXIST[id]):'')).join('<br>');
 const d=document.getElementById('detail');
 d.innerHTML=
  '<div><span class="lvbadge lv'+c.level+'">L'+c.level+'</span>'+
   '<span class="tag">'+esc(c.section)+'</span>'+
   '<span class="covbig" style="background:'+covColors[0]+';color:'+covColors[1]+'">'+covLabel(c)+'</span>'+
   rid+
   '<span style="float:right" class="mono">'+c.id+' &middot; #'+c.report_order+'</span></div>'+
  '<div class="derv">level '+c.level+' &middot; '+esc(c.stratum)+' &middot; derivable: <b>'+esc(c.derivable)+'</b></div>'+
  '<div class="claimtext" id="ct" '+(editing?'contenteditable="true"':'')+'>'+esc(shownClaim)+'</div>'+
   (s.claim!=null?'<span class="edited">edited</span>':'')+
   ' <button id="editbtn" style="padding:3px 9px;font-size:12px">'+(editing?'Done':'Edit text')+'</button>'+
  '<div class="field"><div class="k">Verbatim report quote (grounding)</div><div class="quote">&ldquo;'+esc(c.report_quote)+'&rdquo;</div></div>'+
  (mapsLinks?'<div class="field"><div class="k">'+(c.coverage==='covered'?'Restates existing rubric claim':'Refines existing rubric claim(s)')+'</div><div class="refines">'+mapsLinks+'</div></div>':'')+
  '<div class="field"><div class="k">Where in the dump / how checkable</div><div class="v">'+esc(c.dump_check)+'</div></div>'+
  '<div class="field"><div class="k">Suggested task prompt</div><div class="v">'+esc(c.prompt)+'</div></div>'+
  (c.trap?'<div class="field"><div class="k">Grader trap</div><div class="v">'+esc(c.trap)+'</div></div>':'')+
  '<div class="field"><div class="k">Reviewer note (optional)</div><textarea class="note" id="note" placeholder="e.g. tighten wording, wrong level, merge...">'+esc(s.note||'')+'</textarea></div>'+
  '<div class="actions">'+
   '<button class="approve'+(s.status==='approved'?' on':'')+'" id="ap">&#10003; Approve</button>'+
   '<button class="reject'+(s.status==='rejected'?' on':'')+'" id="rj">&#10007; Reject</button>'+
   '<span class="hint">'+(cur+1)+' / '+CLAIMS.length+'</span>'+
  '</div>'+
  '<div class="src">Source: '+esc(c.source)+'</div>';

 document.getElementById('ap').onclick=()=>{ s.status = s.status==='approved'?null:'approved'; persist(); render(); };
 document.getElementById('rj').onclick=()=>{ s.status = s.status==='rejected'?null:'rejected'; persist(); render(); };
 document.getElementById('note').oninput=(e)=>{ s.note=e.target.value; persist(); };
 document.getElementById('editbtn').onclick=()=>{
   if(editing){ const t=document.getElementById('ct').innerText.trim();
     s.claim = (t===c.claim? null : t); persist(); }
   editing=!editing; render();
   if(editing){ const ct=document.getElementById('ct'); ct.focus();
     const r=document.createRange(); r.selectNodeContents(ct); r.collapse(false);
     const sel=getSelection(); sel.removeAllRanges(); sel.addRange(r); }
 };
}

function nextVisible(from,dir){
 let i=from;
 for(let n=0;n<CLAIMS.length;n++){ i+=dir; if(i<0||i>=CLAIMS.length) return from; if(visible(CLAIMS[i])) return i; }
 return from;
}
document.querySelectorAll('#filter button').forEach(b=>b.onclick=()=>{
 filter=b.dataset.f;
 document.querySelectorAll('#filter button').forEach(x=>x.classList.toggle('on',x===b));
 if(!visible(CLAIMS[cur])){ const nx=nextVisible(-1,1); if(nx>=0)cur=nx; }
 editing=false; render();
});
document.addEventListener('keydown',(e)=>{
 if(editing || e.target.tagName==='TEXTAREA') return;
 if(e.key==='j'||e.key==='ArrowDown'){cur=nextVisible(cur,1);render();e.preventDefault();}
 else if(e.key==='k'||e.key==='ArrowUp'){cur=nextVisible(cur,-1);render();e.preventDefault();}
 else if(e.key==='a'){const s=st(CLAIMS[cur].id);s.status=s.status==='approved'?null:'approved';persist();render();}
 else if(e.key==='r'){const s=st(CLAIMS[cur].id);s.status=s.status==='rejected'?null:'rejected';persist();render();}
});

function buildExport(){
 const approved=[], rejected=[], statuses={};
 for(const c of CLAIMS){
   const s=st(c.id); statuses[c.id]={status:s.status, edited:s.claim!=null, note:s.note||''};
   if(s.status==='approved'){ const o=Object.assign({},c); if(s.claim!=null)o.claim=s.claim;
     if(s.note) o.review_note=s.note; approved.push(o); }
   else if(s.status==='rejected') rejected.push(c.id);
 }
 return {saved_at:new Date().toISOString(),
   n_approved:approved.length,
   n_approved_new:approved.filter(x=>x.coverage!=='covered').length,
   n_approved_covered:approved.filter(x=>x.coverage==='covered').length,
   note:"Approved report-grounded candidate claims, ready for the data-feasibility subagent pass.",
   approved, rejected, statuses};
}
function setAll(v){ const scope=CLAIMS.filter(visible);
 for(const c of scope) st(c.id).status=v; persist(); render(); }
document.getElementById('allok').onclick=()=>setAll('approved');
document.getElementById('allno').onclick=()=>{ if(confirm('Reject all '+CLAIMS.filter(visible).length+' shown candidates?')) setAll('rejected'); };
document.getElementById('save').onclick=()=>{
 const blob=new Blob([JSON.stringify(buildExport(),null,1)],{type:'application/json'});
 const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
 a.download='new_claims_approved.json'; a.click();
};
document.getElementById('copy').onclick=async()=>{
 try{ await navigator.clipboard.writeText(JSON.stringify(buildExport(),null,1));
   const b=document.getElementById('copy'); b.textContent='Copied!'; setTimeout(()=>b.textContent='Copy JSON',1200);
 }catch(e){ alert('Copy failed; use Save.'); }
};
render();
</script>
"""

html = HTML.replace("__DATA__", blob)
(HERE / "new_claims.html").write_text(html)
print("wrote", HERE / "new_claims.html", f"({len(html)} bytes, {len(data['claims'])} candidates)")
