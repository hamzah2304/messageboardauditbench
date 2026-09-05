#!/usr/bin/env python3
"""Claim-by-claim matching UI -> matching.html.
For each claim: the human-report snippet vs the BEST model snippet (highest rubric
score across all graded reports), with bad / neutral / good buttons + notes,
saved to JSON. Built from rubrics_all.json + graded_{blind,context}_*.json.
"""
import json
from pathlib import Path

ROOT = Path("/workspace/collusion")
HERE = ROOT / "messageboardauditbench/hasan"
RUB = json.loads((ROOT / "report/rubrics/rubrics_all.json").read_text())

def pretty(m):
    m = m.replace("claude_", "").replace("codex_", "").replace("_", "-")
    for a, b in [("gpt-5-6-terra","GPT-5.6 Terra"),("gpt-5-6-luna","GPT-5.6 Luna"),("gpt-5-6-sol","GPT-5.6 Sol"),
                 ("opus-5","Opus 5"),("sonnet-5","Sonnet 5"),("haiku-4-5","Haiku 4.5"),("fable-5-1","Fable 5.1"),
                 ("google-gemini-3-8-flash","Gemini 3.8 Flash"),("moonshotai-kimi-k3","Kimi K3"),("z-ai-glm-5-3","GLM 5.3")]:
        if m == a: return b
    return m

# gather all graded batch reports: key -> (cond, model, scores)
graded = []
for p in sorted((ROOT / "report/rubrics").glob("graded_*.json")):
    stem = p.stem[len("graded_"):]
    if stem.startswith("blind_"): cond, model = "blind", stem[len("blind_"):]
    elif stem.startswith("context_"): cond, model = "context", stem[len("context_"):]
    else: continue
    graded.append((cond, model, json.loads(p.read_text())["scores"]))

claims = []
for rub in RUB["rubrics"]:
    for cl in rub["claims"]:
        cid = cl["id"]
        # best entry: highest score, preferring one that has a non-empty quote
        best = None
        for cond, model, scores in graded:
            s = scores.get(cid)
            if not s or s.get("score") is None: continue
            cand = (s["score"], 1 if s.get("quote") else 0, cond, model, s)
            if best is None or cand[:2] > best[:2]:
                best = cand
        b = None
        if best:
            b = {"score": best[0], "cond": best[2], "model": pretty(best[3]),
                 "quote": best[4].get("quote", ""), "reason": best[4].get("reason", "")}
        claims.append({"id": cid, "section": cl["section"], "grading_mode": cl["grading_mode"],
                       "claim": cl["claim"], "human": cl["report_quote"], "best": b})

blob = json.dumps({"claims": claims}, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/")

HTML = r"""<title>Claim Matching</title>
<style>
:root{--bg:#F4F3EE;--card:#FFFFFF;--border:#E0DDD4;--ink:#1A1A1A;--ink2:#666;--muted:#999;--accent:#C15F3C;--accent2:#9C4A2D;--soft:#FDF2EC;--row:#FAFAF7;
 --bad-bg:#FEE2E2;--bad-tx:#991B1B;--warn-bg:#FEF3C7;--warn-tx:#92400E;--ok-bg:#D1FAE5;--ok-tx:#065F46;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);margin:0}
.wrap{max-width:1400px;margin:0 auto;padding:18px 26px}
h1{color:var(--accent);font-size:21px;margin:0 0 2px}
.sub{color:var(--ink2);font-size:13px;margin:0 0 12px}
header.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 10px;border-radius:11px;font-size:12.5px;font-weight:600}
.pill.bad{background:var(--bad-bg);color:var(--bad-tx)}.pill.neu{background:var(--warn-bg);color:var(--warn-tx)}.pill.good{background:var(--ok-bg);color:var(--ok-tx)}.pill.pend{background:#EDECE6;color:#666}
button{font-family:inherit;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--ink);border-radius:7px;padding:7px 13px;font-size:13px}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.layout{display:grid;grid-template-columns:280px 1fr;gap:18px;margin-top:14px}
.list{border:1px solid var(--border);border-radius:8px;background:var(--card);overflow:hidden;align-self:start;max-height:calc(100vh - 150px);overflow-y:auto}
.li{padding:8px 12px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px}
.li:last-child{border-bottom:none}.li:hover{background:var(--row)}.li.active{background:var(--soft)}
.li .id{font-weight:600;color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:12px;min-width:34px}
.li .lbl{color:var(--ink2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{width:10px;height:10px;border-radius:50%;flex:none;background:#D5D2C9}
.dot.bad{background:#EF4444}.dot.neu{background:#F59E0B}.dot.good{background:#10B981}
.card{border:1px solid var(--border);border-radius:8px;background:var(--card);padding:22px 24px}
.tag{display:inline-block;background:var(--soft);color:var(--accent2);border-radius:6px;padding:2px 9px;font-size:12px;font-weight:600;margin-left:6px}
.claimtext{font-size:18px;line-height:1.45;margin:12px 0 18px;font-weight:600}
.snip{margin:14px 0}
.snip .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:5px}
.snip .box{padding:12px 15px;border-radius:8px;font-size:14.5px;line-height:1.55}
.human{border-left:4px solid var(--accent);background:var(--soft);color:#3a2a22}
.modelbox{border-left:4px solid #6C6EF0;background:#EEF0FF;color:#22223a}
.byline{font-size:12px;color:var(--ink2);margin-top:6px}
.byline b{color:var(--ink)}
.reason{font-size:12.5px;color:var(--ink2);margin-top:7px;font-style:italic}
.rate{display:flex;gap:12px;margin-top:22px}
.rate button{flex:1;padding:16px;font-size:16px;font-weight:700;border-width:2px}
.rate .bad{border-color:#EF4444;color:#991B1B}.rate .bad.on{background:#EF4444;color:#fff}
.rate .neu{border-color:#F59E0B;color:#92400E}.rate .neu.on{background:#F59E0B;color:#fff}
.rate .good{border-color:#10B981;color:#065F46}.rate .good.on{background:#10B981;color:#fff}
textarea{width:100%;margin-top:14px;border:1px solid var(--border);border-radius:7px;padding:9px;font:inherit;font-size:13px;resize:vertical;min-height:48px}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
kbd{background:#fff;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 5px;font-size:11px;font-family:ui-monospace,monospace}
.nav{display:flex;gap:8px;margin-top:16px;align-items:center}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#D5D2C9;border-radius:3px}
</style>
<div class="wrap">
 <h1>Claim Matching — human vs best model</h1>
 <p class="sub" id="sub"></p>
 <header class="bar">
  <span class="pill bad">Bad <b id="c-bad">0</b></span>
  <span class="pill neu">Neutral <b id="c-neu">0</b></span>
  <span class="pill good">Good <b id="c-good">0</b></span>
  <span class="pill pend">Left <b id="c-pend">0</b></span>
  <button class="primary" id="save">Save JSON</button>
  <span class="hint"><kbd>1</kbd> bad <kbd>2</kbd> neutral <kbd>3</kbd> good · <kbd>j</kbd>/<kbd>k</kbd> move</span>
 </header>
 <div class="layout"><div class="list" id="list"></div><div class="card" id="detail"></div></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const CL=JSON.parse(document.getElementById('data').textContent).claims;
const LS='claim_matching_v1'; let S={}; try{S=JSON.parse(localStorage.getItem(LS))||{}}catch(e){S={}}
let cur=0;
function st(id){if(!S[id])S[id]={rating:null,note:''};return S[id];}
function persist(){try{localStorage.setItem(LS,JSON.stringify(S))}catch(e){}}
function esc(s){return (s==null?'':(''+s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
document.getElementById('sub').textContent=`${CL.length} claims. For each, does the best model snippet match the human snippet? Rate bad / neutral / good.`;
function counts(){let b=0,n=0,g=0;for(const c of CL){const r=st(c.id).rating;if(r==='bad')b++;else if(r==='neutral')n++;else if(r==='good')g++;}
 c_bad.textContent=b;c_neu.textContent=n;c_good.textContent=g;c_pend.textContent=CL.length-b-n-g;}
function renderList(){const el=document.getElementById('list');el.innerHTML='';
 CL.forEach((c,i)=>{const r=st(c.id).rating;const d=document.createElement('div');d.className='li'+(i===cur?' active':'');
  d.innerHTML=`<span class="dot ${r==='bad'?'bad':r==='neutral'?'neu':r==='good'?'good':''}"></span><span class="id">${c.id}</span><span class="lbl">${esc(c.section)}</span>`;
  d.onclick=()=>{cur=i;render()};el.appendChild(d);});}
function render(){counts();renderList();const c=CL[cur],s=st(c.id);
 const best=c.best;
 const model=best?`<div class="byline">best: <b>${esc(best.model)}</b> · ${best.cond} · rubric score <b>${best.score}</b></div>`+(best.reason?`<div class="reason">judge: ${esc(best.reason)}</div>`:''):'';
 const modelsnip=best&&best.quote?esc(best.quote):(best?'<span style="color:#999">(model scored '+best.score+' but cited no snippet)</span>':'<span style="color:#999">no model snippet</span>');
 document.getElementById('detail').innerHTML=
  `<div><span class="tag">${esc(c.section)}</span><span class="tag">${esc(c.grading_mode)}</span><span style="float:right;font-family:ui-monospace">${c.id} · ${cur+1}/${CL.length}</span></div>`+
  `<div class="claimtext">${esc(c.claim)}</div>`+
  `<div class="snip"><div class="k">Human report snippet</div><div class="box human">“${esc(c.human)}”</div></div>`+
  `<div class="snip"><div class="k">Best model snippet</div><div class="box modelbox">${modelsnip}</div>${model}</div>`+
  `<div class="rate">`+
   `<button class="bad${s.rating==='bad'?' on':''}" id="rbad">✕ Bad</button>`+
   `<button class="neu${s.rating==='neutral'?' on':''}" id="rneu">～ Neutral</button>`+
   `<button class="good${s.rating==='good'?' on':''}" id="rgood">✓ Good</button>`+
  `</div>`+
  `<textarea id="note" placeholder="note (optional)">${esc(s.note||'')}</textarea>`+
  `<div class="nav"><button id="prev">← Prev</button><button id="next">Next →</button></div>`;
 const set=v=>{s.rating=s.rating===v?null:v;persist();render();};
 rbad.onclick=()=>set('bad');rneu.onclick=()=>set('neutral');rgood.onclick=()=>set('good');
 note.oninput=e=>{s.note=e.target.value;persist();};
 prev.onclick=()=>{cur=Math.max(0,cur-1);render()};next.onclick=()=>{cur=Math.min(CL.length-1,cur+1);render()};
}
document.addEventListener('keydown',e=>{if(e.target.tagName==='TEXTAREA')return;
 const s=st(CL[cur].id);
 if(e.key==='1'){s.rating=s.rating==='bad'?null:'bad';persist();render();}
 else if(e.key==='2'){s.rating=s.rating==='neutral'?null:'neutral';persist();render();}
 else if(e.key==='3'){s.rating=s.rating==='good'?null:'good';persist();render();}
 else if(e.key==='j'||e.key==='ArrowDown'){cur=Math.min(CL.length-1,cur+1);render();e.preventDefault();}
 else if(e.key==='k'||e.key==='ArrowUp'){cur=Math.max(0,cur-1);render();e.preventDefault();}});
document.getElementById('save').onclick=()=>{
 const out={saved_at:new Date().toISOString(),ratings:CL.map(c=>({id:c.id,section:c.section,rating:st(c.id).rating,note:st(c.id).note||'',
   best_model:c.best&&c.best.model,best_score:c.best&&c.best.score,best_quote:c.best&&c.best.quote,human:c.human}))};
 const bl=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});const a=document.createElement('a');
 a.href=URL.createObjectURL(bl);a.download='claim_matching.json';a.click();};
render();
</script>
"""
(HERE / "matching.html").write_text(HTML.replace("__DATA__", blob))
print("wrote", HERE / "matching.html", f"({len(claims)} claims)")
