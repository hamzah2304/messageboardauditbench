#!/usr/bin/env python3
"""Raw-vs-verbatim data-variant comparison UI -> variants.html.
Shows each claim's feasibility verdict on the stripped public dump vs Oscar's
verbatim (augmented) variant, highlighting the claims whose verdict flipped and
why, with the verbatim evidence. Built from report/feasibility_compare.json +
report/feasibility_verbatim.json.
"""
import json
from pathlib import Path

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)


comp = {c["id"]: c for c in json.loads((FEASIBILITY / "feasibility_compare.json").read_text())["claims"]}
vb = json.loads((FEASIBILITY / "feasibility_verbatim.json").read_text())
raw_counts = json.loads((FEASIBILITY / "feasibility_compare.json").read_text())["raw_verdicts"]
vb_counts = vb["verdicts"]
claims = []
for c in vb["claims"]:
    claims.append({**c, "raw_verdict": comp[c["id"]]["raw_verdict"], "flipped": comp[c["id"]]["flipped"]})
payload = {"claims": claims, "raw_counts": raw_counts, "vb_counts": vb_counts,
           "n_flipped": sum(1 for c in claims if c["flipped"])}
blob = json.dumps(payload, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Data Variant Feasibility</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--muted:#999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;--ok-bg:#D1FAE5;--ok-tx:#065F46;--warn-bg:#FEF3C7;--warn-tx:#92400E;--bad-bg:#FEE2E2;--bad-tx:#991B1B;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.wrap{max-width:1400px;margin:0 auto;padding:18px 26px}
h1{color:var(--accent);font-size:21px;margin:0 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 12px;max-width:1050px;line-height:1.45}
header.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.cmp{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink2)}
.cmp b{color:var(--ink)}
.bars{display:flex;gap:3px}
.bseg{height:14px;border-radius:3px}
.bd{background:#10B981}.bp{background:#F59E0B}.bn{background:#EF4444}
.flipchip{background:#EEF0FF;color:#2b2c66;font-weight:700;border-radius:11px;padding:2px 10px;font-size:12.5px}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:7px;overflow:hidden}
.seg button{border:none;border-right:1px solid var(--border);padding:6px 11px;background:var(--card);cursor:pointer;font:inherit;font-size:13px}
.seg button:last-child{border-right:none}.seg button.on{background:var(--accent);color:#fff}
.layout{display:grid;grid-template-columns:340px 1fr;gap:18px;margin-top:14px}
.list{border:1px solid var(--border);border-radius:8px;background:var(--card);overflow:hidden;align-self:start;max-height:calc(100vh - 155px);overflow-y:auto}
.li{padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px}
.li:last-child{border-bottom:none}.li:hover{background:var(--row)}.li.active{background:var(--soft)}.li.hidden{display:none}
.li .id{font-weight:600;color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:12px;min-width:34px}
.li .lbl{color:var(--ink2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dots{display:flex;align-items:center;gap:3px}
.vdot{width:10px;height:10px;border-radius:50%;flex:none}.vd{background:#10B981}.vp{background:#F59E0B}.vn{background:#EF4444}
.arr{color:var(--muted);font-size:11px}
.flag{font-size:9.5px;font-weight:800;color:#2b2c66;background:#E0E3FF;border-radius:4px;padding:1px 5px}
.card{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:20px 22px}
.lvbadge{display:inline-block;padding:2px 9px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;margin-left:6px}
.lv1{background:#8A8F98}.lv2{background:#4F9D8C}.lv3{background:#6C6EF0}.lv4{background:#C15F3C}
.tag{display:inline-block;background:var(--soft);color:var(--accent2);border-radius:6px;padding:2px 9px;font-size:12px;font-weight:600;margin-left:6px}
.vbadge{display:inline-block;padding:2px 11px;border-radius:6px;font-size:12.5px;font-weight:700}
.transition{display:flex;align-items:center;gap:12px;margin:16px 0 4px}
.transition .lab{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.transition .big{font-size:20px;color:var(--muted)}
.claimtext{font-size:16px;line-height:1.45;margin:6px 0 4px;font-weight:500}
.field{margin-top:15px}.field .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px}
.field .v{font-size:14px;line-height:1.5}
.callout{border-left:3px solid #6C6EF0;background:#EEF0FF;padding:9px 12px;border-radius:0 6px 6px 0;font-size:13.5px;line-height:1.5;color:#2b2c66}
.quote{border-left:3px solid var(--accent);background:var(--soft);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;font-style:italic;color:#3a2a22}
.corr{border-left:3px solid #F59E0B;background:var(--warn-bg);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;color:#5b4300}
table.fx{width:100%;border-collapse:collapse;font-size:12.5px}
table.fx td{border-bottom:1px solid var(--border);padding:5px 8px;vertical-align:top}
table.fx td.tok{font-family:ui-monospace,Menlo,monospace;font-weight:600}
.st{font-weight:700;font-size:11px;padding:1px 7px;border-radius:9px;white-space:nowrap}
.st.ok{background:var(--ok-bg);color:var(--ok-tx)}.st.no{background:var(--bad-bg);color:var(--bad-tx)}.st.mid{background:var(--warn-bg);color:var(--warn-tx)}
.ev{border:1px solid var(--border);border-radius:7px;padding:9px 11px;margin-top:8px;background:var(--row)}
.ev .file{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--accent);font-weight:600}
.ev .q{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--ink2);white-space:pre-wrap;margin:3px 0}
.ev .r{font-size:12.5px;line-height:1.45;white-space:pre-wrap}
.mono{font-family:ui-monospace,Menlo,monospace}.hint{color:var(--muted);font-size:12px;margin-left:auto}
kbd{background:#fff;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 5px;font-size:11px;font-family:ui-monospace,monospace}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--accent)}
</style>

<div class="wrap">
 <h1>Data Variant Feasibility &mdash; stripped dump vs verbatim</h1>
 <p class="sub" id="sub"></p>
 <header class="bar">
  <span class="cmp">raw <span class="bars" id="bar-raw"></span></span>
  <span class="cmp">verbatim <span class="bars" id="bar-vb"></span></span>
  <span class="flipchip" id="flipn"></span>
  <span class="seg" id="filter">
   <button data-f="all" class="on">All</button>
   <button data-f="flipped">Flipped</button>
   <button data-f="derivable">Derivable</button>
   <button data-f="partial">Partial</button>
   <button data-f="not_derivable">Not&nbsp;deriv.</button>
  </span>
  <span class="hint"><kbd>j</kbd>/<kbd>k</kbd> move</span>
 </header>
 <div class="layout"><div class="list" id="list"></div><div class="card" id="detail"></div></div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const CL=D.claims; let cur=0, filter='all';
const V={derivable:['vd','#065F46','#D1FAE5','derivable'],partial:['vp','#92400E','#FEF3C7','partial'],not_derivable:['vn','#991B1B','#FEE2E2','not derivable']};
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
document.getElementById('sub').textContent=`Each approved claim's dump-feasibility on the stripped public dump vs Oscar's verbatim variant (public dump + only what the report prints verbatim). ${D.n_flipped} claims flip to derivable on verbatim; C14/C15 stay not-derivable by design.`;
function bars(el,counts){const t=counts.derivable+ (counts.partial||0)+(counts.not_derivable||0);
 const seg=(n,c)=>n?`<span class="bseg ${c}" style="width:${Math.max(10,n/t*150)}px" title="${n}"></span>`:'';
 document.getElementById(el).innerHTML=seg(counts.derivable||0,'bd')+seg(counts.partial||0,'bp')+seg(counts.not_derivable||0,'bn')+`<b style="margin-left:6px">${counts.derivable||0}/${counts.partial||0}/${counts.not_derivable||0}</b>`;}
function vis(c){return filter==='all'||(filter==='flipped'&&c.flipped)||c.verbatim_verdict===filter;}
function renderList(){const el=document.getElementById('list');el.innerHTML='';
 CL.forEach((c,i)=>{const rv=V[c.raw_verdict],vv=V[c.verbatim_verdict];
  const d=document.createElement('div');d.className='li'+(i===cur?' active':'')+(vis(c)?'':' hidden');
  const dots=c.flipped?`<span class="vdot ${rv[0]}"></span><span class="arr">→</span><span class="vdot ${vv[0]}"></span>`:`<span class="vdot ${vv[0]}"></span>`;
  d.innerHTML=`<span class="dots">${dots}</span><span class="id">${c.id}</span>${c.flipped?'<span class="flag">FLIP</span>':''}<span class="lbl">${esc(c.section)}</span>`;
  d.onclick=()=>{cur=i;render();};el.appendChild(d);});}
function stCls(s){s=(s||'').toLowerCase();if(/(confirm|ok|pass|present|true|match|yes)/.test(s))return'ok';if(/(not found|contradict|missing|absent|fail|unsupported|false)/.test(s))return'no';return'mid';}
function badge(v){const x=V[v];return `<span class="vbadge" style="color:${x[1]};background:${x[2]}">${x[3]}</span>`;}
function render(){
 bars('bar-raw',D.raw_counts);bars('bar-vb',D.vb_counts);
 document.getElementById('flipn').textContent=`${D.n_flipped} flipped →`;
 renderList();const c=CL[cur];
 const fx=(c.fact_check||[]).map(f=>`<tr><td class="tok">${esc(f.token)}</td><td><span class="st ${stCls(f.status)}">${esc(f.status)}</span></td><td class="mono" style="color:#666;font-size:11.5px">${esc(f.query||f.detail||'')}</td></tr>`).join('');
 const ev=(c.evidence||[]).map(e=>`<div class="ev"><div class="file">${esc(e.file)}</div><div class="q">${esc(e.query)}</div><div class="r">${esc(e.result)}</div></div>`).join('');
 document.getElementById('detail').innerHTML=
  `<div><span class="lvbadge lv${c.level}">L${c.level}</span><span class="tag">${esc(c.section)}</span>`+
   (c.flipped?'<span class="tag" style="background:#E0E3FF;color:#2b2c66">verdict flipped</span>':'<span class="tag">unchanged</span>')+
   `<span style="float:right" class="mono">${c.id} · #${c.report_order}</span></div>`+
  `<div class="claimtext">${esc(c.claim)}</div>`+
  `<div class="transition"><div><div class="lab">stripped dump</div>${badge(c.raw_verdict)}</div>`+
   `<div class="big">→</div><div><div class="lab">verbatim variant</div>${badge(c.verbatim_verdict)}${c.confidence!=null?' <span class="mono" style="color:#666">conf '+c.confidence+'</span>':''}</div></div>`+
  (c.change_reason?`<div class="field"><div class="k">Why it ${c.flipped?'changed':'stayed'}</div><div class="callout">${esc(c.change_reason)}</div></div>`:'')+
  `<div class="field"><div class="k">Report quote</div><div class="quote">&ldquo;${esc(c.report_quote)}&rdquo;</div></div>`+
  (c.corrected_values?`<div class="field"><div class="k">Value on the verbatim variant</div><div class="corr">${esc(c.corrected_values)}</div></div>`:'')+
  (c.feas_notes?`<div class="field"><div class="k">Notes</div><div class="v">${esc(c.feas_notes)}</div></div>`:'')+
  (fx?`<div class="field"><div class="k">Fact-check on verbatim</div><table class="fx">${fx}</table></div>`:'')+
  (ev?`<div class="field"><div class="k">Evidence — queries run on dump_verbatim/</div>${ev}</div>`:'');
}
function nextVis(from,dir){let i=from;for(let n=0;n<CL.length;n++){i+=dir;if(i<0||i>=CL.length)return from;if(vis(CL[i]))return i;}return from;}
document.querySelectorAll('#filter button').forEach(b=>b.onclick=()=>{filter=b.dataset.f;
 document.querySelectorAll('#filter button').forEach(x=>x.classList.toggle('on',x===b));
 if(!vis(CL[cur])){const nx=nextVis(-1,1);if(nx>=0)cur=nx;}render();});
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
 if(e.key==='j'||e.key==='ArrowDown'){cur=nextVis(cur,1);render();e.preventDefault();}
 else if(e.key==='k'||e.key==='ArrowUp'){cur=nextVis(cur,-1);render();e.preventDefault();}});
render();
</script>
"""
html = HTML.replace("__DATA__", blob)
(VIEWERS / "variants.html").write_text(html)
print("wrote", VIEWERS / "variants.html", f"({len(html)} bytes)")
