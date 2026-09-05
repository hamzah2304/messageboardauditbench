#!/usr/bin/env python3
"""Rubric scoreboard UI -> scoreboard.html.
27 claims x 4 model reports, each cell the GPT-5.6 Sol rubric score (0/0.5/1) with
the judge's quote + reason on click. Built from report/rubrics/graded_*.json +
rubrics_all.json.
"""
import json
from pathlib import Path

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from paths import (ROOT, HUMAN_REPORT, CLAIMS, FEASIBILITY, RUBRICS, GRADED,
                   GRADED_INPUTS, PROMPTS, SNIPPETS, VIEWERS, VIEWER_DATA, ENV_FILE)


RUB = json.loads((RUBRICS / "rubrics_all.json").read_text())

def nice(stem):  # bl_opus_5_s3 -> "Opus 5 · s3"
    s = stem[3:] if stem.startswith("bl_") else stem
    m, _, sess = s.rpartition("_s")
    name = (m.replace("_", " ").replace("gpt 5 6 ", "GPT-5.6 ").replace("opus 5", "Opus 5")
             .replace("sonnet 5", "Sonnet 5").replace("haiku 4 5", "Haiku 4.5")
             .replace("sol", "Sol").replace("luna", "Luna").strip())
    name = name[0].upper() + name[1:] if name and name[0].islower() else name
    return f"{name} · s{sess}" if sess else name

gp = sorted(GRADED.glob("graded_bl_*.json"))
# ignore the s1 batch (ran on raw_stripped / medium effort / older prompt); keep s3.
gp = [p for p in gp if not p.stem.endswith("_s1")]
graded = {p.stem[len("graded_"):]: json.loads(p.read_text()) for p in gp}
# order columns by accuracy desc
REPORTS = sorted(graded, key=lambda k: -graded[k]["accuracy"])
TITLES = {k: nice(k[len("bl_"):] if k.startswith("bl_") else k) for k in REPORTS}

claims = []
for rub in RUB["rubrics"]:
    for c in rub["claims"]:
        row = {"id": c["id"], "rubric_id": rub["rubric_id"], "section": c["section"],
               "grading_mode": c["grading_mode"], "claim": c["claim"], "report_quote": c["report_quote"],
               "scores": {}}
        for k in REPORTS:
            s = graded[k]["scores"].get(c["id"], {})
            row["scores"][k] = {"score": s.get("score"), "quote": s.get("quote", ""), "reason": s.get("reason", "")}
        claims.append(row)

summary = {k: {"title": TITLES[k], "accuracy": graded[k]["accuracy"], "total": graded[k]["total"],
               "max": graded[k]["max"], "by_mode": graded[k].get("by_mode", {})} for k in REPORTS}
payload = {"reports": REPORTS, "summary": summary, "claims": claims, "grader": graded[REPORTS[0]]["grader"]}
blob = json.dumps(payload, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Rubric Scoreboard</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--muted:#999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.wrap{max-width:1400px;margin:0 auto;padding:18px 26px}
h1{color:var(--accent);font-size:21px;margin:0 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 14px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.rc{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:12px 16px;min-width:190px}
.rc .t{font-weight:700;font-size:14px;margin-bottom:4px}
.rc .acc{font-size:26px;font-weight:800;color:var(--accent)}
.rc .sm{font-size:12px;color:var(--ink2);margin-top:3px}
.rc .bar{height:7px;border-radius:4px;background:#EDECE6;margin-top:7px;overflow:hidden}
.rc .bar span{display:block;height:100%;background:var(--accent)}
.layout{display:grid;grid-template-columns:1fr 380px;gap:18px}
.tblwrap{border:1px solid var(--border);border-radius:8px;background:var(--card);overflow:hidden}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--border);text-align:left}
th{background:var(--row);position:sticky;top:0;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink2);z-index:2}
tr.rubhead td{background:var(--soft);color:var(--accent2);font-weight:700;font-size:11px}
td.id{font-family:ui-monospace,Menlo,monospace;font-weight:600;color:var(--accent);white-space:nowrap}
td.sec{color:var(--ink2);max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
td.cell{text-align:center;cursor:pointer;font-weight:700;width:70px}
.s1{background:#D1FAE5;color:#065F46}.s05{background:#FEF3C7;color:#92400E}.s0{background:#FEE2E2;color:#991B1B}.sna{color:#bbb}
td.cell.sel{outline:2px solid var(--accent);outline-offset:-2px}
tr:hover td:not(.cell){background:var(--row)}
.mchip{font-size:9px;font-weight:700;padding:1px 4px;border-radius:3px;margin-left:5px}
.m-ra{background:#DCFCE7;color:#065F46}.m-rc{background:#FEF3C7;color:#92400E}
.detail{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:18px;align-self:start;position:sticky;top:14px}
.detail .k{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:12px 0 3px}
.detail .claim{font-size:15px;font-weight:600;line-height:1.4}
.quote{border-left:3px solid var(--accent);background:var(--soft);padding:7px 11px;border-radius:0 6px 6px 0;font-size:13px;font-style:italic;color:#3a2a22}
.scorebig{font-size:34px;font-weight:800}
.reason{font-size:13.5px;line-height:1.5}
.rq{border-left:3px solid var(--border);padding:6px 11px;font-size:12.5px;color:var(--ink2);font-style:italic}
.mono{font-family:ui-monospace,Menlo,monospace}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
</style>

<div class="wrap">
 <h1>Rubric Scoreboard</h1>
 <p class="sub" id="sub"></p>
 <div class="cards" id="cards"></div>
 <div class="layout">
  <div class="tblwrap"><table id="tbl"></table></div>
  <div class="detail" id="detail"><div class="k">Click a score cell</div><div class="reason">Each cell is GPT-5.6 Sol's 0–1 rubric score for that claim in that report. Click one to see the judge's quote and reason.</div></div>
 </div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const RE=D.reports, SU=D.summary, CL=D.claims;
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function sc(v){return v===1?'s1':v===0.5?'s05':v===0?'s0':'sna';}
function fmt(v){return v==null?'–':(v===1?'1':v===0?'0':v.toFixed(1));}
document.getElementById('sub').textContent=`27 claims × ${RE.length} reports, graded by ${D.grader} (0 / 0.5 / 1 per claim). recall_accuracy = derivable claim; recall_calibrated = solid part + hedged inference.`;

document.getElementById('cards').innerHTML=RE.map(k=>{const s=SU[k];const pct=Math.round(s.accuracy*100);
 return `<div class="rc"><div class="t">${esc(s.title)}</div><div class="acc">${s.accuracy.toFixed(2)}</div>`+
  `<div class="sm">${s.total} / ${s.max} · ra ${(s.by_mode.recall_accuracy??0).toFixed(2)} · rc ${(s.by_mode.recall_calibrated??0).toFixed(2)}</div>`+
  `<div class="bar"><span style="width:${pct}%"></span></div></div>`;}).join('');

let sel=null;
function buildTable(){
 let h='<tr><th>claim</th><th>section</th>'+RE.map(k=>'<th style="text-align:center">'+esc(SU[k].title.replace('Claude ','').replace('GPT-5.6 ',''))+'</th>').join('')+'</tr>';
 let lastR=null;
 CL.forEach((c,i)=>{
  if(c.rubric_id!==lastR){lastR=c.rubric_id;h+=`<tr class="rubhead"><td colspan="${2+RE.length}">${c.rubric_id}</td></tr>`;}
  const mchip=c.grading_mode==='recall_accuracy'?'<span class="mchip m-ra">RA</span>':'<span class="mchip m-rc">RC</span>';
  h+=`<tr><td class="id">${c.id}${mchip}</td><td class="sec" title="${esc(c.claim)}">${esc(c.section)}</td>`+
   RE.map(k=>{const v=c.scores[k].score;return `<td class="cell ${sc(v)}" data-i="${i}" data-k="${k}">${fmt(v)}</td>`;}).join('')+'</tr>';
 });
 document.getElementById('tbl').innerHTML=h;
 document.querySelectorAll('td.cell').forEach(td=>td.onclick=()=>showCell(+td.dataset.i, td.dataset.k, td));
}
function showCell(i,k,td){
 if(sel)sel.classList.remove('sel'); sel=td; td.classList.add('sel');
 const c=CL[i], s=c.scores[k];
 document.getElementById('detail').innerHTML=
  `<div class="k">${esc(SU[k].title)} · ${c.id} <span class="mono" style="color:#999">${c.rubric_id} · ${c.grading_mode}</span></div>`+
  `<div class="scorebig ${sc(s.score)}" style="background:none;padding:0">${fmt(s.score)}<span style="font-size:15px;color:#999"> / 1</span></div>`+
  `<div class="k">Claim</div><div class="claim">${esc(c.claim)}</div>`+
  `<div class="k">Human report says</div><div class="quote">“${esc(c.report_quote)}”</div>`+
  `<div class="k">Judge's reason</div><div class="reason">${esc(s.reason)||'<span style=color:#999>—</span>'}</div>`+
  (s.quote?`<div class="k">Quote it scored on (from ${esc(SU[k].title)})</div><div class="rq">“${esc(s.quote)}”</div>`:'');
}
buildTable();
</script>
"""
html = HTML.replace("__DATA__", blob)
(VIEWERS / "scoreboard.html").write_text(html)
print("wrote", VIEWERS / "scoreboard.html", f"({len(html)} bytes)")
