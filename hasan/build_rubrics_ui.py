#!/usr/bin/env python3
"""Combined Rubrics + Feasibility UI: report/rubrics/rubrics_all.json -> rubrics.html.
Browse the six 5-claim accuracy rubrics; each claim shows its grading mode + 0/1/2
scale AND the dump feasibility evidence (verdict, fact-check, queries, corrections)
that the rubric's ground truth was built from. Read-only.

Run:  cd hasan && python build_rubrics_ui.py
"""
import json
from pathlib import Path

ROOT = Path("/workspace/collusion")
HERE = ROOT / "messageboardauditbench/hasan"
R = json.loads((ROOT / "report/rubrics/rubrics_all.json").read_text())

flat = []
for rub in R["rubrics"]:
    for c in rub["claims"]:
        flat.append({**c, "rubric_id": rub["rubric_id"]})
# the actual markdown judge sheets the grader reads (rubric_N.md)
md = {f"R{i}": (ROOT / f"report/rubrics/rubric_{i}.md").read_text() for i in range(1, R["n_rubrics"] + 1)}
payload = {"scale": R["grading_scale"], "modes": R["modes"], "claims": flat,
           "n_rubrics": R["n_rubrics"], "md": md}
blob = json.dumps(payload, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Rubrics &amp; Feasibility</title>
<style>
:root{
 --bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--muted:#999;
 --accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;
 --ok-bg:#D1FAE5;--ok-tx:#065F46;--warn-bg:#FEF3C7;--warn-tx:#92400E;--bad-bg:#FEE2E2;--bad-tx:#991B1B;
}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.wrap{max-width:1400px;margin:0 auto;padding:18px 26px}
h1{color:var(--accent);font-size:21px;margin:0 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 12px;max-width:1050px;line-height:1.45}
header.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 10px;border-radius:11px;font-size:12.5px;font-weight:600}
.pill.d{background:var(--ok-bg);color:var(--ok-tx)}.pill.p{background:var(--warn-bg);color:var(--warn-tx)}.pill.n{background:var(--bad-bg);color:var(--bad-tx)}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:7px;overflow:hidden}
.seg button{border:none;border-right:1px solid var(--border);padding:6px 10px;background:var(--card);cursor:pointer;font:inherit;font-size:13px}
.seg button:last-child{border-right:none}.seg button.on{background:var(--accent);color:#fff}
.layout{display:grid;grid-template-columns:330px 1fr;gap:18px;margin-top:14px}
.list{border:1px solid var(--border);border-radius:8px;background:var(--card);overflow:hidden;align-self:start;max-height:calc(100vh - 150px);overflow-y:auto}
.rhead{background:var(--soft);color:var(--accent2);font-weight:700;font-size:12px;padding:6px 12px;border-bottom:1px solid var(--border);position:sticky;top:0}
.li{padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px}
.li:hover{background:var(--row)}.li.active{background:var(--soft)}.li.hidden{display:none}
.li .id{font-weight:600;color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:12px;min-width:34px}
.li .lbl{color:var(--ink2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vdot{width:10px;height:10px;border-radius:50%;flex:none}.vd{background:#10B981}.vp{background:#F59E0B}.vn{background:#EF4444}
.mchip{font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:4px;letter-spacing:.02em}
.m-ra{background:#DCFCE7;color:#065F46}.m-rc{background:#FEF3C7;color:#92400E}.m-ca{background:#FEE2E2;color:#991B1B}
.card{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:20px 22px}
.rbadge{display:inline-block;background:#333;color:#fff;border-radius:6px;padding:2px 9px;font-size:11px;font-weight:700}
.lvbadge{display:inline-block;padding:2px 9px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;margin-left:6px}
.lv1{background:#8A8F98}.lv2{background:#4F9D8C}.lv3{background:#6C6EF0}.lv4{background:#C15F3C}
.tag{display:inline-block;background:var(--soft);color:var(--accent2);border-radius:6px;padding:2px 9px;font-size:12px;font-weight:600;margin-left:6px}
.vbadge,.mbadge{display:inline-block;padding:2px 11px;border-radius:6px;font-size:12px;font-weight:700;margin-left:6px}
.callout{border-left:3px solid var(--accent);background:var(--soft);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;line-height:1.5}
.callout.mode{border-color:#6C6EF0;background:#EEF0FF;color:#2b2c66}
.claimtext{font-size:17px;line-height:1.45;margin:13px 0 4px;font-weight:500}
.field{margin-top:15px}.field .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px}
.field .v{font-size:14px;line-height:1.5}
.quote{border-left:3px solid var(--accent);background:var(--soft);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;font-style:italic;color:#3a2a22}
.corr{border-left:3px solid #F59E0B;background:var(--warn-bg);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;color:#5b4300}
table.fx{width:100%;border-collapse:collapse;font-size:12.5px}
table.fx td{border-bottom:1px solid var(--border);padding:5px 8px;vertical-align:top}
table.fx td.tok{font-family:ui-monospace,Menlo,monospace;font-weight:600}
table.fx td.q{font-family:ui-monospace,Menlo,monospace;color:var(--ink2);font-size:11.5px}
.st{font-weight:700;font-size:11px;padding:1px 7px;border-radius:9px;white-space:nowrap}
.st.ok{background:var(--ok-bg);color:var(--ok-tx)}.st.no{background:var(--bad-bg);color:var(--bad-tx)}.st.mid{background:var(--warn-bg);color:var(--warn-tx)}
.ev{border:1px solid var(--border);border-radius:7px;padding:9px 11px;margin-top:8px;background:var(--row)}
.ev .file{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--accent);font-weight:600}
.ev .q{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--ink2);white-space:pre-wrap;margin:3px 0}
.ev .r{font-size:12.5px;line-height:1.45;white-space:pre-wrap}
table.scale{width:100%;border-collapse:collapse;font-size:13px;margin-top:2px}
table.scale td{border:1px solid var(--border);padding:7px 10px;vertical-align:top}
table.scale td.s{font-weight:800;text-align:center;width:34px;font-size:15px}
.s2{background:#ECFDF5}.s1{background:#FFFBEB}.s0{background:#FEF2F2}
.meta{font-size:12px;color:var(--ink2);margin-top:3px}.mono{font-family:ui-monospace,Menlo,monospace}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
kbd{background:#fff;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 5px;font-size:11px;font-family:ui-monospace,monospace}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
.mdsheet{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:20px 26px;margin-bottom:16px;max-width:900px}
.mdsheet h1{font-size:19px;color:var(--accent);margin:0 0 10px;border:none}
.mdsheet h2{font-size:14.5px;color:var(--ink);margin:18px 0 6px;font-family:ui-monospace,Menlo,monospace}
.mdsheet p{font-size:13.5px;line-height:1.55;margin:7px 0}
.mdsheet ul{margin:6px 0 6px 4px;padding-left:18px}
.mdsheet li{font-size:13px;line-height:1.5;margin:2px 0}
.mdsheet code{background:var(--soft);color:var(--accent2);padding:1px 5px;border-radius:4px;font-size:12px}
.mdsheet strong{color:var(--ink)}
.mdsheet hr{border:none;border-top:1px solid var(--border);margin:14px 0}
.mdsheet .raw{white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--ink2)}
</style>

<div class="wrap">
 <h1>Rubrics &amp; Feasibility</h1>
 <p class="sub" id="sub"></p>
 <header class="bar">
  <span class="seg" id="viewtog">
   <button data-v="cards" class="on">Rubric cards</button>
   <button data-v="md">Grading&nbsp;.md</button>
  </span>
  <span class="pill d">Derivable <b id="c-d">0</b></span>
  <span class="pill p">Partial <b id="c-p">0</b></span>
  <span class="pill n">Not derivable <b id="c-n">0</b></span>
  <span class="seg" id="rubfilter">
   <button data-r="all" class="on">All rubrics</button>
   <button data-r="R1">R1</button><button data-r="R2">R2</button><button data-r="R3">R3</button>
   <button data-r="R4">R4</button><button data-r="R5">R5</button><button data-r="R6">R6</button>
  </span>
  <button id="copymd" style="display:none">Copy .md</button>
  <span class="hint"><kbd>j</kbd>/<kbd>k</kbd> move</span>
 </header>
 <div class="layout" id="cardsview"><div class="list" id="list"></div><div class="card" id="detail"></div></div>
 <div id="mdview" style="display:none;margin-top:14px"></div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const CL=D.claims; let cur=0, rub='all';
const VER={derivable:['d','vd','#065F46','#D1FAE5'],partial:['p','vp','#92400E','#FEF3C7'],not_derivable:['n','vn','#991B1B','#FEE2E2']};
const MODEC={recall_accuracy:['m-ra','recall_accuracy','#065F46','#DCFCE7'],recall_calibrated:['m-rc','recall_calibrated','#92400E','#FEF3C7'],calibration:['m-ca','calibration','#991B1B','#FEE2E2']};
const MSHORT={recall_accuracy:'RECALL',recall_calibrated:'CALIB.',calibration:'TRAP'};
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
document.getElementById('sub').textContent=`Six accuracy rubrics × 5 claims. Each item shows its grading mode + 0/1/2 scale and the dump feasibility evidence behind it. derivable = report can establish it; not-derivable = calibration trap (asserting it from the dump is an over-claim).`;
function vis(c){return rub==='all'||c.rubric_id===rub;}
function counts(){const t={derivable:0,partial:0,not_derivable:0};CL.forEach(c=>t[c.ground_truth.verdict]++);
 document.getElementById('c-d').textContent=t.derivable;document.getElementById('c-p').textContent=t.partial;document.getElementById('c-n').textContent=t.not_derivable;}
function stCls(s){s=(s||'').toLowerCase();if(/(confirm|ok|pass|present|true|match|yes)/.test(s))return'ok';if(/(not found|contradict|missing|absent|fail|unsupported|false)/.test(s))return'no';return'mid';}
function renderList(){
 const el=document.getElementById('list');el.innerHTML='';let lastR=null;
 CL.forEach((c,i)=>{
  if(!vis(c))return;
  if(c.rubric_id!==lastR){lastR=c.rubric_id;const h=document.createElement('div');h.className='rhead';h.textContent=c.rubric_id+' · '+c.claim_ids_label;el.appendChild(h);}
  const v=VER[c.ground_truth.verdict],m=MODEC[c.grading_mode];
  const d=document.createElement('div');d.className='li'+(i===cur?' active':'');
  d.innerHTML=`<span class="vdot ${v[1]}"></span><span class="id">${c.id}</span><span class="mchip ${m[0]}">${MSHORT[c.grading_mode]}</span><span class="lbl">${esc(c.section)}</span>`;
  d.onclick=()=>{cur=i;render();};el.appendChild(d);
 });
}
function render(){
 counts();
 // annotate rubric label once
 const ids={};CL.forEach(c=>{(ids[c.rubric_id]=ids[c.rubric_id]||[]).push(c.id);});
 CL.forEach(c=>c.claim_ids_label=ids[c.rubric_id][0]+'–'+ids[c.rubric_id][ids[c.rubric_id].length-1].replace('C',''));
 renderList();
 const c=CL[cur],v=VER[c.ground_truth.verdict],m=MODEC[c.grading_mode],g=c.ground_truth;
 const fx=(g.fact_check||[]).map(f=>`<tr><td class="tok">${esc(f.token)}</td><td><span class="st ${stCls(f.status)}">${esc(f.status)}</span></td><td class="q">${esc(f.detail||'')}</td></tr>`).join('');
 const ev=(g.evidence||[]).map(e=>`<div class="ev"><div class="file">${esc(e.file)}</div><div class="q">${esc(e.query)}</div><div class="r">${esc(e.result)}</div></div>`).join('');
 const maps=(c.maps_to||[]).join(', ');
 const scale=['2','1','0'].map(k=>`<tr class="s${k}"><td class="s">${k}</td><td>${esc(c.scoring[k])}</td></tr>`).join('');
 document.getElementById('detail').innerHTML=
  `<div><span class="rbadge">${c.rubric_id}</span><span class="lvbadge lv${c.level}">L${c.level}</span><span class="tag">${esc(c.section)}</span>`+
   `<span class="vbadge" style="color:${v[2]};background:${v[3]}">${g.verdict.replace('_',' ')}${g.confidence!=null?' · conf '+g.confidence:''}</span>`+
   `<span style="float:right" class="mono">${c.id} · #${c.report_order}</span></div>`+
  `<div class="meta">${c.coverage==='covered'?'covered — restates '+maps:(c.coverage==='gap'?'gap — new claim ('+(c.proposed_id||'')+')':'partial — refines '+maps+' ('+(c.proposed_id||'')+')')}</div>`+
  `<div class="claimtext">${esc(c.claim)}</div>`+
  `<div class="field"><div class="k">Grading mode: <span class="mbadge" style="color:${m[2]};background:${m[3]}">${c.grading_mode}</span></div><div class="callout mode">${esc(c.mode_guidance)}</div></div>`+
  `<div class="field"><div class="k">Report quote (grounding)</div><div class="quote">&ldquo;${esc(c.report_quote)}&rdquo;</div></div>`+
  (g.corrections?`<div class="field"><div class="k">Correction from the dump</div><div class="corr">${esc(g.corrections)}</div></div>`:'')+
  (g.notes?`<div class="field"><div class="k">Feasibility notes (ground truth)</div><div class="v">${esc(g.notes)}</div></div>`:'')+
  (fx?`<div class="field"><div class="k">Fact-check (verbatim tokens)</div><table class="fx">${fx}</table></div>`:'')+
  (ev?`<div class="field"><div class="k">Evidence — queries actually run</div>${ev}</div>`:'')+
  `<div class="field"><div class="k">Accuracy scale (max 2)</div><table class="scale">${scale}</table></div>`+
  (c.trap?`<div class="field"><div class="k">Trap</div><div class="callout">${esc(c.trap)}</div></div>`:'');
}
function nextVis(from,dir){let i=from;for(let n=0;n<CL.length;n++){i+=dir;if(i<0||i>=CL.length)return from;if(vis(CL[i]))return i;}return from;}

// ---- markdown judge-sheet view ----
let view='cards';
function mdToHtml(md){
 const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
 const inline=s=>esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
 const out=[]; let inList=false;
 for(let line of md.split('\n')){
  if(/^---\s*$/.test(line)){ if(inList){out.push('</ul>');inList=false;} out.push('<hr>'); continue; }
  if(/^#\s+/.test(line)){ if(inList){out.push('</ul>');inList=false;} out.push('<h1>'+inline(line.replace(/^#\s+/,''))+'</h1>'); continue; }
  if(/^##\s+/.test(line)){ if(inList){out.push('</ul>');inList=false;} out.push('<h2>'+inline(line.replace(/^##\s+/,''))+'</h2>'); continue; }
  if(/^-\s+/.test(line)){ if(!inList){out.push('<ul>');inList=true;} out.push('<li>'+inline(line.replace(/^-\s+/,''))+'</li>'); continue; }
  if(inList){out.push('</ul>');inList=false;}
  if(line.trim()==='') continue;
  out.push('<p>'+inline(line)+'</p>');
 }
 if(inList)out.push('</ul>');
 return out.join('');
}
function renderMd(){
 const ids=rub==='all'?Object.keys(D.md):[rub];
 document.getElementById('mdview').innerHTML=ids.map(r=>'<div class="mdsheet">'+mdToHtml(D.md[r])+'</div>').join('');
}
function currentMdText(){ const ids=rub==='all'?Object.keys(D.md):[rub]; return ids.map(r=>D.md[r]).join('\n\n\n'); }
function applyView(){
 const md=view==='md';
 document.getElementById('cardsview').style.display=md?'none':'grid';
 document.getElementById('mdview').style.display=md?'block':'none';
 document.getElementById('copymd').style.display=md?'inline-block':'none';
 if(md)renderMd();
}
document.querySelectorAll('#viewtog button').forEach(b=>b.onclick=()=>{
 view=b.dataset.v;document.querySelectorAll('#viewtog button').forEach(x=>x.classList.toggle('on',x===b));applyView();
});
document.getElementById('copymd').onclick=async()=>{
 try{ await navigator.clipboard.writeText(currentMdText());
   const b=document.getElementById('copymd');b.textContent='Copied!';setTimeout(()=>b.textContent='Copy .md',1200);
 }catch(e){ alert('Copy failed'); }
};
document.querySelectorAll('#rubfilter button').forEach(b=>b.onclick=()=>{
 rub=b.dataset.r;document.querySelectorAll('#rubfilter button').forEach(x=>x.classList.toggle('on',x===b));
 if(!vis(CL[cur])){const nx=nextVis(-1,1);if(nx>=0)cur=nx;}
 if(view==='md')renderMd(); else render();
});
document.addEventListener('keydown',e=>{
 if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
 if(e.key==='j'||e.key==='ArrowDown'){cur=nextVis(cur,1);render();e.preventDefault();}
 else if(e.key==='k'||e.key==='ArrowUp'){cur=nextVis(cur,-1);render();e.preventDefault();}
});
render();
</script>
"""
html = HTML.replace("__DATA__", blob)
(HERE / "rubrics.html").write_text(html)
print("wrote", HERE / "rubrics.html", f"({len(html)} bytes, {len(flat)} claims across {R['n_rubrics']} rubrics)")
