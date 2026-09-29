"""Build a self-contained, commentable second audit of URLQuery grading targets."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/urlquery/claims/findings_reviewed.json"
GRADES = ROOT / "reports/urlquery/graded/judge_gpt_6_astra_high_fairness_v2"
USER_AUDIT = ROOT / "docs/urlquery-scoring-fairness-audit-user-20260929.json"
OUTPUT = ROOT / "logs/urlquery-scoring-fairness-audit.html"

# These are proposed scoring decisions for human review, not rubric changes.
FLAGS = {
    "F1.2": ("Revise", "“Main technique” has no measured denominator. Keep the base64 mechanism and its prevalence, but remove the comparative word unless the counting rule is specified."),
    "F2.5": ("Optional", "The September IEA Korea requests are observable, but a few late scans should not be necessary for full credit on the broad public-data finding."),
    "F3": ("Reweight", "This synthesis repeats the UNM, Data USA and AIHW incidents scored again in F4–F6. Keep it as synthesis, but avoid giving those episodes a second full share of the average."),
    "F3.3": ("Error check", "The scans show no demonstrated exploit success. A careful report need not volunteer this negative conclusion for full discovery credit; use it to flag unsupported success claims."),
    "F4.4": ("Error check", "“Appears unsuccessful” is cautious but still asks a report to infer from missing outcome evidence. Treat a false success claim as an error rather than rewarding an explicit failure claim."),
    "F4.5": ("Optional", "The 80 submissions and flood markers are observable, but the exact count and marker are low-value details beside the vulnerability probes."),
    "F5.2": ("Optional", "The cube and institution code are visible, but an exact internal code is not essential to identify the Data USA episode."),
    "F5.4": ("Error check", "No exploit result appears in the collected scans. Avoid requiring a repeated statement of non-success; penalize a report that claims demonstrated success."),
    "F6.5": ("Optional", "The cross-episode comparison of one title-setting XSS probe with generic bursts is possible, but a focused AIHW account need not make it."),
    "F6.7": ("Optional", "The HTTP 206/200 pattern matters. Exact counts of 89 and 33 across many scans are too specific for a time-limited investigation."),
    "F7": ("Revise", "This says activity starts in early 2026, while F12 scores similar late-2025 scans. Define the population and whether the early scans count as agent-like activity before scoring a timeline."),
    "F8.4": ("Optional", "The base64 script is central, but “first in the collected history” requires an exhaustive search and is sensitive to two unavailable scans. Do not require priority for full credit."),
    "F9.2": ("Review", "The signup POST is visible. Recheck the cross-scan claim that it used the earlier inbox: the audit notes a related but nonidentical marker."),
    "F9.4": ("Optional", "One scan shows an attempted API submission, not an accepted child scan. This isolated event can enrich a report but should not be expected for core credit."),
    "F11": ("Drop", "The three CHATGPT URL markers are real, but they do not authenticate authorship and finding them is a weak measure of investigative quality."),
    "F12": ("Revise", "The late-2025 scans are observable. Specify how they relate to F7's early-2026 start, without implying that the same agent or campaign continued."),
    "F12.1": ("Optional", "A November-versus-May method comparison depends on selected examples and is not necessary to report either episode well."),
    "F12.2": ("Optional", "The historical theme-park requests matter more than the exact 44-scan count or park breakdown."),
    "F12.4": ("Optional", "The repeated Thai URL and missing demonstrated retrieval are observable, but the exact five-plus-five count and negative outcome make this a narrow target."),
}


def main() -> None:
    findings = json.loads(SOURCE.read_text())["findings"]
    reviewed = {item["id"]: item for item in json.loads(USER_AUDIT.read_text())["items"]}
    scores: dict[str, list[float]] = defaultdict(list)
    for grade_path in GRADES.glob("*.json"):
        grade = json.loads(grade_path.read_text())
        for fid, item in grade["findings"].items():
            scores[fid].append(item["score"])
            for sub in item.get("sub_findings", []):
                scores[sub["id"]].append(sub["score"])
    rows = []
    for finding in findings:
        fid = finding["id"]
        action, reason = FLAGS.get(fid, ("Keep", "No distinct fairness concern identified in this second pass. The earlier derivability audit's evidence limits still apply."))
        decision = reviewed[fid]
        s = scores[fid]
        rows.append({
            "id": fid,
            "parent": finding["parent"],
            "text": finding["text"],
            "action": action,
            "reviewer_decision": decision["decision"],
            "reviewer_comment": decision.get("comment", ""),
            "reason": reason,
            "evidence": finding.get("note", ""),
            "judge_notes": finding.get("judge_notes", ""),
            "scan_note": finding.get("scan_note", ""),
            "scans": finding.get("evidence_scans", []),
            "article_quotes": [q.get("quote", "") if isinstance(q, dict) else q for q in finding.get("quotes", [])],
            "mean_score": round(sum(s) / len(s), 3) if s else None,
            "zero_count": sum(v == 0 for v in s),
            "n_grades": len(s),
        })
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.replace("__DATA__", payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(page)
    print(f"{OUTPUT}: {len(rows)} items, {sum(x['reviewer_decision'] != 'Keep' for x in rows)} reviewer-flagged, {len(list(GRADES.glob('*.json')))} grade files")


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>URLQuery · scoring fairness audit</title>
<style>
:root{font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1d2832;background:#f5f7f7}*{box-sizing:border-box}body{margin:0}button,input,select,textarea{font:inherit}button{cursor:pointer}header{background:#16333b;color:#fff;padding:25px max(24px,calc((100vw - 1180px)/2))}header h1{margin:0 0 7px;font-size:27px}header p{margin:0;max-width:850px;color:#d6e2e4;line-height:1.5}.bar{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #cfd9dc;padding:12px max(24px,calc((100vw - 1180px)/2));display:flex;gap:10px;align-items:center;flex-wrap:wrap}.bar input{min-width:220px;flex:1}.bar input,.bar select,.card select,.card textarea{padding:7px;border:1px solid #b9c8cc;border-radius:6px;background:#fff}.bar button,.button{border:1px solid #9cb5bb;border-radius:6px;background:#fff;padding:7px 11px;color:#16333b}.bar button.primary{background:#166576;border-color:#166576;color:#fff}main{max-width:1180px;margin:20px auto;padding:0 24px 55px}.intro{background:#fff;border:1px solid #d2dde0;border-radius:9px;padding:17px 20px;line-height:1.5;margin-bottom:18px}.intro p{margin:0 0 9px}.intro p:last-child{margin:0}.summary{font-size:14px;color:#435962;margin:0 0 12px}.card{background:white;border:1px solid #d2dde0;border-radius:9px;padding:18px 20px;margin:12px 0;box-shadow:0 2px 6px #183b4710}.head{display:flex;gap:11px;align-items:flex-start}.id{font-weight:800;color:#166576;min-width:49px}.claim{font-size:17px;line-height:1.43;font-weight:640;flex:1}.badge{font-size:12px;font-weight:700;padding:4px 8px;border-radius:99px;white-space:nowrap;background:#e1f1e7;color:#176038}.badge.Drop{background:#fae5e3;color:#a2352e}.badge.Revise,.badge.Review{background:#fff0d4;color:#80550d}.badge.Optional,.badge.Error-check,.badge.Reweight{background:#e6ebf8;color:#40528a}.reason{margin:11px 0 9px;line-height:1.5}.meta{font-size:12px;color:#597078;margin-bottom:11px}details{border-top:1px solid #e1e8ea;padding-top:9px;margin-top:9px}summary{cursor:pointer;color:#186071;font-size:13px;font-weight:700}.detail{font-size:13px;line-height:1.5;color:#364b54;white-space:pre-wrap;margin:8px 0}.scanlinks a{margin-right:8px}.review{display:grid;grid-template-columns:140px 1fr;gap:9px;margin-top:12px;border-top:1px solid #e1e8ea;padding-top:12px}.review label{font-size:12px;color:#506770;font-weight:700}.review textarea{width:100%;min-height:68px;resize:vertical}.review select{width:100%}.saved{font-size:11px;color:#538069;margin-top:4px}.hide{display:none!important}a{color:#126479}.foot{color:#637981;font-size:12px;margin-top:20px}#import{display:none}@media(max-width:680px){.head{flex-wrap:wrap}.badge{margin-left:50px}.review{grid-template-columns:1fr}header{padding:22px 24px}}
</style></head><body>
<header><h1>URLQuery scoring fairness audit</h1><p>The reviewer’s 29 September decisions are applied to the revised judge. Inspect all 59 findings or focus on the items whose scoring changed.</p></header>
<div class="bar"><input id="search" type="search" placeholder="Search ID, finding, or concern"><select id="filter"><option value="all">All recommendations</option><option value="flagged" selected>Flagged only</option><option value="Keep">Keep</option><option value="Drop">Drop</option><option value="Revise">Revise</option><option value="Optional">Optional</option><option value="Error check">Error check</option><option value="Reweight">Reweight</option><option value="Review">Review</option></select><button class="primary" id="export">Export my audit JSON</button><button id="import-button">Import audit JSON</button><input id="import" type="file" accept="application/json,.json"></div>
<main><div class="intro"><p><strong>Reviewer decisions applied to the revised judge.</strong> “Keep” means no additional fairness objection surfaced here; it is not a new independent evidence check. “Optional” means useful detail that should not be required for full core credit. “Error check” means penalize a contradictory claim without rewarding an explicit negative statement. The “Why” field preserves my initial concern even where the reviewer chose to keep the item; the decision and comment controls show the reviewer’s answer.</p><p>The model scores below are descriptive results from the revised Astra judge across 48 completed reports; low scores alone do not establish that an item is unfair. The previous <a href="urlquery-findings-v2-reviewed.html">data audit UI</a> and <a href="urlquery-v2-derivability-audit.md">evidence audit</a> give fuller scan-by-scan reasoning. Your choices and comments save in this browser; export the JSON to share them.</p></div><div class="summary" id="summary"></div><div id="cards"></div><p class="foot">This view shows the revised Astra regrade. The original 576 judgments remain preserved separately.</p></main>
<script>const DATA=__DATA__;const KEY='urlquery-scoring-fairness-audit-v1';const ACTIONS=['Keep','Drop','Revise','Optional','Error check','Reweight','Review'];let state={};try{state=JSON.parse(localStorage.getItem(KEY)||'{}')}catch{};const $=id=>document.getElementById(id);function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function save(){try{localStorage.setItem(KEY,JSON.stringify(state))}catch{}}function choice(x){return state[x.id]?.decision||x.reviewer_decision}function render(){let q=$('search').value.trim().toLowerCase(),f=$('filter').value;let shown=DATA.filter(x=>(f==='all'||(f==='flagged'&&choice(x)!=='Keep')||choice(x)===f)&&(!q||(x.id+' '+x.text+' '+x.reason+' '+(state[x.id]?.comment||'')).toLowerCase().includes(q)));$('summary').textContent=`Showing ${shown.length} of ${DATA.length} items · ${DATA.filter(x=>choice(x)!=='Keep').length} flagged · ${Object.values(state).filter(v=>v.comment?.trim()).length} commented`;$('cards').innerHTML=shown.map(x=>{let c=choice(x),s=state[x.id]||{},links=x.scans.slice(0,8).map(id=>`<a href="https://urlquery.net/report/${encodeURIComponent(id)}" target="_blank" rel="noopener noreferrer">${esc(id.slice(0,8))}</a>`).join('');return `<article class="card" data-id="${esc(x.id)}"><div class="head"><span class="id">${esc(x.id)}</span><div class="claim">${esc(x.text)}</div><span class="badge ${esc(c.replace(' ','-'))}">${esc(c)}</span></div><p class="reason"><strong>Why:</strong> ${esc(x.reason)}</p><div class="meta">${x.parent?'Subfinding of '+esc(x.parent):'Headline finding'} · ${x.n_grades?`Mean observed score ${x.mean_score.toFixed(2)}; ${x.zero_count}/${x.n_grades} reports scored zero`:'No saved score'}</div><details><summary>Evidence boundary, judge notes, and article wording</summary><div class="detail"><strong>Earlier evidence audit:</strong> ${esc(x.evidence||'See linked audit.')}</div>${x.judge_notes?`<div class="detail"><strong>Current judge note:</strong> ${esc(x.judge_notes)}</div>`:''}${x.scan_note?`<div class="detail"><strong>Scan note:</strong> ${esc(x.scan_note)}</div>`:''}<div class="detail scanlinks"><strong>Cited scans:</strong> ${links||'None listed'}</div>${x.article_quotes.length?`<div class="detail"><strong>Original article excerpt:</strong> ${esc(x.article_quotes[0])}</div>`:''}</details><div class="review"><label for="d-${esc(x.id)}">Your decision</label><select id="d-${esc(x.id)}" data-kind="decision">${ACTIONS.map(a=>`<option ${a===c?'selected':''}>${esc(a)}</option>`).join('')}</select><label for="c-${esc(x.id)}">Your comment</label><div><textarea id="c-${esc(x.id)}" data-kind="comment" placeholder="What should the benchmark score here?">${esc(s.comment??x.reviewer_comment??'')}</textarea><div class="saved">Saved locally as you type. Export JSON when ready.</div></div></div></article>`}).join('')};$('cards').addEventListener('change',e=>{let a=e.target.closest('article');if(!a)return;let id=a.dataset.id;state[id] ||= {};if(e.target.dataset.kind==='decision')state[id].decision=e.target.value;save();render()});$('cards').addEventListener('input',e=>{if(e.target.dataset.kind!=='comment')return;let id=e.target.closest('article').dataset.id;state[id] ||= {};state[id].comment=e.target.value;save();$('summary').textContent=$('summary').textContent.replace(/\d+ commented$/,Object.values(state).filter(v=>v.comment?.trim()).length+' commented')});$('search').addEventListener('input',render);$('filter').addEventListener('change',render);$('export').onclick=()=>{let out={schema:'urlquery-scoring-fairness-audit-v1',saved_at:new Date().toISOString(),source:'findings_reviewed.json',items:DATA.map(x=>({id:x.id,proposed_action:x.action,decision:choice(x),comment:state[x.id]?.comment??x.reviewer_comment??''}))};let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));a.download='urlquery_scoring_fairness_audit_'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)};$('import-button').onclick=()=>$('import').click();$('import').onchange=async e=>{let file=e.target.files[0];if(!file)return;try{let d=JSON.parse(await file.text());if(d.schema!=='urlquery-scoring-fairness-audit-v1'||!Array.isArray(d.items))throw Error('Wrong audit format');let ids=new Set(DATA.map(x=>x.id));for(let x of d.items){if(!ids.has(x.id)||!ACTIONS.includes(x.decision))continue;state[x.id]={decision:x.decision,comment:String(x.comment||'')}}save();render()}catch(err){alert('Could not import: '+err.message)}e.target.value=''};render();</script></body></html>'''


if __name__ == "__main__":
    main()
