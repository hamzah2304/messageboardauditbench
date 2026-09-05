#!/usr/bin/env python3
"""Blind vs Context scoreboard -> scoreboard_batch.html.
Grades from report/rubrics/graded_{blind,context}_*.json. A summary table compares
each model's accuracy under the blind vs context prompt (+delta); a condition
toggle shows the 30-claim x model matrix, click a cell for the judge's reason.
"""
import json
from pathlib import Path

ROOT = Path("/workspace/collusion")
HERE = ROOT / "messageboardauditbench/hasan"
RUB = json.loads((ROOT / "report/rubrics/rubrics_all.json").read_text())

def pretty(model):
    m = model.replace("claude_", "").replace("codex_", "").replace("_", "-")
    for a, b in [("gpt-5-6-terra", "GPT-5.6 Terra"), ("gpt-5-6-luna", "GPT-5.6 Luna"),
                 ("gpt-5-6-sol", "GPT-5.6 Sol"), ("opus-5", "Opus 5"), ("sonnet-5", "Sonnet 5"),
                 ("haiku-4-5", "Haiku 4.5"), ("fable-5-1", "Fable 5.1"),
                 ("google-gemini-3-8-flash", "Gemini 3.8 Flash"),
                 ("moonshotai-kimi-k3", "Kimi K3"), ("z-ai-glm-5-3", "GLM 5.3")]:
        if m == a: return b
    return m

graded = {}   # (cond, model) -> data
for p in sorted((ROOT / "report/rubrics").glob("graded_*.json")):
    stem = p.stem[len("graded_"):]
    if stem.startswith("blind_"): cond, model = "blind", stem[len("blind_"):]
    elif stem.startswith("context_"): cond, model = "context", stem[len("context_"):]
    else: continue
    graded[(cond, model)] = json.loads(p.read_text())

models = sorted({m for (_, m) in graded}, key=lambda m: -(graded.get(("context", m), graded.get(("blind", m), {})).get("accuracy", 0)))
rows = []
for m in models:
    b = graded.get(("blind", m)); c = graded.get(("context", m))
    rows.append({"model": m, "name": pretty(m),
                 "blind": b["accuracy"] if b else None, "context": c["accuracy"] if c else None,
                 "delta": (round(c["accuracy"] - b["accuracy"], 3) if (b and c) else None)})

# per-claim matrix data per condition
claims = []
for rub in RUB["rubrics"]:
    for cl in rub["claims"]:
        claims.append({"id": cl["id"], "rubric_id": rub["rubric_id"], "section": cl["section"],
                       "grading_mode": cl["grading_mode"], "claim": cl["claim"], "report_quote": cl["report_quote"]})
matrix = {cond: {m: graded[(cond, m)]["scores"] if (cond, m) in graded else {} for m in models} for cond in ("blind", "context")}

payload = {"rows": rows, "models": models, "names": {m: pretty(m) for m in models},
           "claims": claims, "matrix": matrix, "grader": next(iter(graded.values()))["grader"] if graded else "?"}
blob = json.dumps(payload, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Blind vs Context</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--muted:#999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.wrap{max-width:1400px;margin:0 auto;padding:18px 26px}
h1{color:var(--accent);font-size:21px;margin:0 0 2px}h2{font-size:15px;margin:22px 0 8px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 14px}
table{border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.sumt{width:auto;min-width:560px}
th,td{padding:7px 12px;border-bottom:1px solid var(--border);text-align:left}
th{background:var(--row);font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink2)}
td.name{font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.barcell{position:relative;min-width:150px}
.bar{height:16px;border-radius:3px;background:var(--accent);opacity:.85}
.bar.ctx{background:#6C6EF0}
.delta.up{color:#065F46;font-weight:700}.delta.down{color:#991B1B;font-weight:700}.delta.zero{color:#999}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:7px;overflow:hidden;margin-left:10px}
.seg button{border:none;border-right:1px solid var(--border);padding:5px 12px;background:var(--card);cursor:pointer;font:inherit;font-size:13px}
.seg button:last-child{border-right:none}.seg button.on{background:var(--accent);color:#fff}
.mwrap{overflow-x:auto;border:1px solid var(--border);border-radius:8px;background:var(--card)}
table.mx{border:none;border-radius:0;min-width:100%}
table.mx th.mh{writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap;font-size:10.5px;padding:8px 4px;max-height:120px}
td.id{font-family:ui-monospace,Menlo,monospace;font-weight:600;color:var(--accent);white-space:nowrap}
td.sec{color:var(--ink2);max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr.rubhead td{background:var(--soft);color:var(--accent2);font-weight:700;font-size:11px}
td.cell{text-align:center;cursor:pointer;font-weight:700;width:42px}
.s1{background:#D1FAE5;color:#065F46}.s05{background:#FEF3C7;color:#92400E}.s0{background:#FEE2E2;color:#991B1B}.sna{color:#ccc}
td.cell.sel{outline:2px solid var(--accent);outline-offset:-2px}
.mchip{font-size:9px;font-weight:700;padding:1px 4px;border-radius:3px;margin-left:5px}.m-ra{background:#DCFCE7;color:#065F46}.m-rc{background:#FEF3C7;color:#92400E}
.detail{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:16px;margin-top:14px}
.detail .k{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:10px 0 3px}
.claim{font-size:15px;font-weight:600;line-height:1.4}
.quote{border-left:3px solid var(--accent);background:var(--soft);padding:7px 11px;border-radius:0 6px 6px 0;font-size:13px;font-style:italic;color:#3a2a22}
.reason{font-size:13.5px;line-height:1.5}.rq{border-left:3px solid var(--border);padding:6px 11px;font-size:12.5px;color:var(--ink2);font-style:italic}
.mono{font-family:ui-monospace,Menlo,monospace}
::-webkit-scrollbar{height:8px;width:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
</style>
<div class="wrap">
 <h1>Blind vs Context</h1>
 <p class="sub" id="sub"></p>
 <h2>Accuracy by model</h2>
 <table class="sumt" id="sumt"></table>
 <h2 style="display:inline-block">Per-claim<span id="condlabel"></span></h2>
 <span class="seg" id="condtog"><button data-c="context" class="on">Context</button><button data-c="blind">Blind</button></span>
 <div class="mwrap"><table class="mx" id="mx"></table></div>
 <div class="detail" id="detail"><div class="k">Click a score cell</div><div class="reason">Each cell is the judge's 0/0.5/1 rubric score. Click for its quote + reason.</div></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const M=D.models, NM=D.names, CL=D.claims; let cond='context';
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function sc(v){return v===1?'s1':v===0.5?'s05':v===0?'s0':'sna';}
function fmt(v){return v==null?'–':(v===1?'1':v===0?'0':v.toFixed(1));}
document.getElementById('sub').textContent=`${M.length} models, blind vs context prompt (both raw_stripped data, high effort, 20-min budget), 30 claims each, graded by ${D.grader}.`;

function sumTable(){
 const mx=Math.max(...D.rows.flatMap(r=>[r.blind||0,r.context||0]),0.01);
 let h='<tr><th>model</th><th>blind</th><th>context</th><th>Δ ctx−blind</th></tr>';
 D.rows.forEach(r=>{
  const bb=r.blind==null?'':`<div class="bar" style="width:${Math.round(r.blind/mx*140)}px"></div>`;
  const cb=r.context==null?'':`<div class="bar ctx" style="width:${Math.round(r.context/mx*140)}px"></div>`;
  const d=r.delta; const dc=d==null?'':(d>0?'up':d<0?'down':'zero'); const ds=d==null?'–':(d>0?'+':'')+d.toFixed(2);
  h+=`<tr><td class="name">${esc(r.name)}</td>`+
     `<td class="barcell"><span class="num">${r.blind==null?'–':r.blind.toFixed(2)}</span> ${bb}</td>`+
     `<td class="barcell"><span class="num">${r.context==null?'–':r.context.toFixed(2)}</span> ${cb}</td>`+
     `<td class="delta ${dc}">${ds}</td></tr>`;
 });
 document.getElementById('sumt').innerHTML=h;
}
let sel=null;
function matrix(){
 document.getElementById('condlabel').textContent=' · '+cond;
 const cols=M.filter(m=>D.matrix[cond][m] && Object.keys(D.matrix[cond][m]).length);
 let h='<tr><th>claim</th><th>section</th>'+cols.map(m=>`<th class="mh">${esc(NM[m])}</th>`).join('')+'</tr>';
 let lastR=null;
 CL.forEach((c,i)=>{
  if(c.rubric_id!==lastR){lastR=c.rubric_id;h+=`<tr class="rubhead"><td colspan="${2+cols.length}">${c.rubric_id}</td></tr>`;}
  const chip=c.grading_mode==='recall_accuracy'?'<span class="mchip m-ra">RA</span>':'<span class="mchip m-rc">RC</span>';
  h+=`<tr><td class="id">${c.id}${chip}</td><td class="sec" title="${esc(c.claim)}">${esc(c.section)}</td>`+
     cols.map(m=>{const v=(D.matrix[cond][m][c.id]||{}).score;return `<td class="cell ${sc(v)}" data-i="${i}" data-m="${m}">${fmt(v)}</td>`;}).join('')+'</tr>';
 });
 document.getElementById('mx').innerHTML=h;
 document.querySelectorAll('#mx td.cell').forEach(td=>td.onclick=()=>showCell(+td.dataset.i,td.dataset.m,td));
}
function showCell(i,m,td){
 if(sel)sel.classList.remove('sel');sel=td;td.classList.add('sel');
 const c=CL[i],s=D.matrix[cond][m][c.id]||{};
 document.getElementById('detail').innerHTML=
  `<div class="k">${esc(NM[m])} · ${cond} · ${c.id} <span class="mono" style="color:#999">${c.grading_mode}</span></div>`+
  `<div style="font-size:30px;font-weight:800" class="${sc(s.score)}" >${fmt(s.score)}<span style="font-size:14px;color:#999"> / 1</span></div>`+
  `<div class="k">Claim</div><div class="claim">${esc(c.claim)}</div>`+
  `<div class="k">Human report says</div><div class="quote">“${esc(c.report_quote)}”</div>`+
  `<div class="k">Judge's reason</div><div class="reason">${esc(s.reason)||'—'}</div>`+
  (s.quote?`<div class="k">Quote scored on</div><div class="rq">“${esc(s.quote)}”</div>`:'');
}
document.querySelectorAll('#condtog button').forEach(b=>b.onclick=()=>{cond=b.dataset.c;
 document.querySelectorAll('#condtog button').forEach(x=>x.classList.toggle('on',x===b));matrix();});
sumTable();matrix();
</script>
"""
html = HTML.replace("__DATA__", blob)
(HERE / "scoreboard_batch.html").write_text(html)
print("wrote", HERE / "scoreboard_batch.html", f"({len(html)} bytes; {len(rows)} models)")
