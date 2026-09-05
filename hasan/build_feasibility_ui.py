#!/usr/bin/env python3
"""Feasibility review UI: report/feasibility.json -> feasibility.html.
Shows each approved candidate claim with its dump-feasibility verdict
(derivable / partial / not_derivable), can_be_met, per-token fact-check,
and the concrete queries/evidence the subagents ran. Read-only review.

Run:  cd hasan && python build_feasibility_ui.py
"""
import json
from pathlib import Path

ROOT = Path("/workspace/collusion")
HERE = ROOT / "messageboardauditbench/hasan"
data = json.loads((ROOT / "report/feasibility.json").read_text())
blob = json.dumps(data, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Claim Feasibility</title>
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
.sub{color:var(--ink2);font-size:13px;margin:0 0 14px}
header.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 10px;border-radius:11px;font-size:12.5px;font-weight:600}
.pill.d{background:var(--ok-bg);color:var(--ok-tx)}
.pill.p{background:var(--warn-bg);color:var(--warn-tx)}
.pill.n{background:var(--bad-bg);color:var(--bad-tx)}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:7px;overflow:hidden}
.seg button{border:none;border-right:1px solid var(--border);padding:6px 11px;background:var(--card);cursor:pointer;font:inherit;font-size:13px}
.seg button:last-child{border-right:none}.seg button.on{background:var(--accent);color:#fff}
.layout{display:grid;grid-template-columns:320px 1fr;gap:18px;margin-top:14px}
.list{border:1px solid var(--border);border-radius:8px;background:var(--card);overflow:hidden;align-self:start;max-height:calc(100vh - 150px);overflow-y:auto}
.li{padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px}
.li:last-child{border-bottom:none}.li:hover{background:var(--row)}.li.active{background:var(--soft)}.li.hidden{display:none}
.li .id{font-weight:600;color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:12px;min-width:34px}
.li .lbl{color:var(--ink2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vdot{width:10px;height:10px;border-radius:50%;flex:none}
.vd{background:#10B981}.vp{background:#F59E0B}.vn{background:#EF4444}
.card{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:20px 22px}
.lvbadge{display:inline-block;padding:2px 9px;border-radius:6px;font-size:11px;font-weight:700;color:#fff}
.lv1{background:#8A8F98}.lv2{background:#4F9D8C}.lv3{background:#6C6EF0}.lv4{background:#C15F3C}
.tag{display:inline-block;background:var(--soft);color:var(--accent2);border-radius:6px;padding:2px 9px;font-size:12px;font-weight:600;margin-left:6px}
.vbadge{display:inline-block;padding:2px 11px;border-radius:6px;font-size:12.5px;font-weight:700;margin-left:6px}
.claimtext{font-size:17px;line-height:1.45;margin:14px 0 4px;font-weight:500}
.field{margin-top:15px}
.field .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px}
.field .v{font-size:14px;line-height:1.5}
.quote{border-left:3px solid var(--accent);background:var(--soft);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;font-style:italic;color:#3a2a22}
.corr{border-left:3px solid #F59E0B;background:var(--warn-bg);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;color:#5b4300}
table.fx{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:2px}
table.fx td{border-bottom:1px solid var(--border);padding:5px 8px;vertical-align:top}
table.fx td.tok{font-family:ui-monospace,Menlo,monospace;font-weight:600;white-space:nowrap}
table.fx td.q{font-family:ui-monospace,Menlo,monospace;color:var(--ink2);font-size:11.5px}
.st{font-weight:700;font-size:11px;padding:1px 7px;border-radius:9px;white-space:nowrap}
.st.ok{background:var(--ok-bg);color:var(--ok-tx)}.st.no{background:var(--bad-bg);color:var(--bad-tx)}.st.mid{background:var(--warn-bg);color:var(--warn-tx)}
.ev{border:1px solid var(--border);border-radius:7px;padding:9px 11px;margin-top:8px;background:var(--row)}
.ev .file{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--accent);font-weight:600}
.ev .q{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--ink2);white-space:pre-wrap;margin:3px 0}
.ev .r{font-size:12.5px;line-height:1.45;white-space:pre-wrap}
.meta{font-size:12px;color:var(--ink2);margin-top:2px}
.mono{font-family:ui-monospace,Menlo,monospace}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
kbd{background:#fff;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 5px;font-size:11px;font-family:ui-monospace,monospace}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
</style>

<div class="wrap">
 <h1>Claim Feasibility &mdash; can the dump support each claim?</h1>
 <p class="sub" id="sub"></p>
 <header class="bar">
  <span class="pill d">Derivable <b id="c-d">0</b></span>
  <span class="pill p">Partial <b id="c-p">0</b></span>
  <span class="pill n">Not derivable <b id="c-n">0</b></span>
  <span class="seg" id="filter">
   <button data-f="all" class="on">All</button>
   <button data-f="derivable">Derivable</button>
   <button data-f="partial">Partial</button>
   <button data-f="not_derivable">Not&nbsp;derivable</button>
  </span>
  <span class="hint"><kbd>j</kbd>/<kbd>k</kbd> move</span>
 </header>
 <div class="layout"><div class="list" id="list"></div><div class="card" id="detail"></div></div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const CL=D.claims; let cur=0, filter='all';
const VC={derivable:['d','vd','#065F46','#D1FAE5'],partial:['p','vp','#92400E','#FEF3C7'],not_derivable:['n','vn','#991B1B','#FEE2E2']};
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
document.getElementById('sub').textContent=`${CL.length} approved candidates checked against /workspace/collusion/dump/  ·  derivable = a report can establish it from the dump; not-derivable = needs data outside the dump (kept as calibration items).`;
function vis(c){return filter==='all'||c.verdict===filter;}
function counts(){
 const t={derivable:0,partial:0,not_derivable:0}; CL.forEach(c=>t[c.verdict]!=null&&t[c.verdict]++);
 document.getElementById('c-d').textContent=t.derivable;document.getElementById('c-p').textContent=t.partial;document.getElementById('c-n').textContent=t.not_derivable;
}
function stCls(s){s=(s||'').toLowerCase(); if(/(confirm|ok|pass|present|true|match|yes)/.test(s))return'ok'; if(/(not found|contradict|missing|absent|fail|no\b|false|unsupported)/.test(s))return'no'; return'mid';}
function renderList(){
 const el=document.getElementById('list');el.innerHTML='';
 CL.forEach((c,i)=>{const v=VC[c.verdict]||VC.partial;
  const d=document.createElement('div');d.className='li'+(i===cur?' active':'')+(vis(c)?'':' hidden');
  d.innerHTML=`<span class="vdot ${v[1]}"></span><span class="id">${c.id}</span><span class="lbl">${esc(c.section)}</span>`;
  d.onclick=()=>{cur=i;render();};el.appendChild(d);});
}
function render(){
 counts();renderList();const c=CL[cur];const v=VC[c.verdict]||VC.partial;
 const fx=(c.fact_check||[]).map(f=>`<tr><td class="tok">${esc(f.token)}</td><td><span class="st ${stCls(f.status)}">${esc(f.status)}</span></td><td class="q">${esc(f.query||f.detail||'')}</td></tr>`).join('');
 const ev=(c.evidence||[]).map(e=>`<div class="ev"><div class="file">${esc(e.file)}</div><div class="q">${esc(e.query)}</div><div class="r">${esc(e.result)}</div></div>`).join('');
 const maps=(c.maps_to||[]).join(', ');
 document.getElementById('detail').innerHTML=
  `<div><span class="lvbadge lv${c.level}">L${c.level}</span><span class="tag">${esc(c.section)}</span>`+
   `<span class="vbadge" style="color:${v[2]};background:${v[3]}">${c.verdict.replace('_',' ')}</span>`+
   `<span class="tag">can be met: ${esc(c.can_be_met)}</span>`+
   (c.confidence!=null?`<span class="tag">conf ${c.confidence}</span>`:'')+
   `<span style="float:right" class="mono">${c.id} · #${c.report_order}</span></div>`+
  `<div class="meta">${c.coverage==='covered'?'covered — restates '+maps:(c.coverage==='gap'?'gap — new claim ('+(c.proposed_id||'')+')':'partial — refines '+maps+' ('+(c.proposed_id||'')+')')}</div>`+
  `<div class="claimtext">${esc(c.claim)}</div>`+
  `<div class="field"><div class="k">Report quote</div><div class="quote">&ldquo;${esc(c.report_quote)}&rdquo;</div></div>`+
  (c.corrected_values?`<div class="field"><div class="k">Correction from the dump</div><div class="corr">${esc(c.corrected_values)}</div></div>`:'')+
  (c.feas_notes?`<div class="field"><div class="k">Feasibility notes</div><div class="v">${esc(c.feas_notes)}</div></div>`:'')+
  (fx?`<div class="field"><div class="k">Fact-check (verbatim tokens)</div><table class="fx">${fx}</table></div>`:'')+
  (ev?`<div class="field"><div class="k">Evidence — queries actually run</div>${ev}</div>`:'');
}
function nextVis(from,dir){let i=from;for(let n=0;n<CL.length;n++){i+=dir;if(i<0||i>=CL.length)return from;if(vis(CL[i]))return i;}return from;}
document.querySelectorAll('#filter button').forEach(b=>b.onclick=()=>{
 filter=b.dataset.f;document.querySelectorAll('#filter button').forEach(x=>x.classList.toggle('on',x===b));
 if(!vis(CL[cur])){const nx=nextVis(-1,1);if(nx>=0)cur=nx;}render();
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
(HERE / "feasibility.html").write_text(html)
print("wrote", HERE / "feasibility.html", f"({len(html)} bytes)")
