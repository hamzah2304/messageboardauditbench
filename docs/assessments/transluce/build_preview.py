"""Render this assessment for the repository's existing local HTML viewer.

Run from the worktree: .venv/bin/python docs/assessments/transluce/build_preview.py
Then: python scripts/html_viewer.py 8790
"""

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE / "assessment.md"
REPORT_ID = "transluce-benchmark-assessment-2026-09-26"

SHELL = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f4ef;--paper:#fffefa;--ink:#252c32;--muted:#59636c;--line:#dcded9;--accent:#266b61;--soft:#e6f0eb}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,sans-serif}
a{color:var(--accent);text-underline-offset:3px}button{cursor:pointer;font:inherit;font-size:13px;border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink);padding:7px 12px}
button:hover{border-color:var(--accent)}button:disabled{opacity:.45;cursor:default}
.top{padding:18px 30px;border-bottom:1px solid var(--line);display:flex;gap:20px;justify-content:space-between;font-size:13px;color:var(--muted)}
.top span{letter-spacing:.08em;text-transform:uppercase;font-weight:650}
.layout{display:grid;grid-template-columns:minmax(0,900px) 310px;gap:42px;max-width:1320px;margin:auto;padding:40px 30px 90px}
article{min-width:0}h1{font:600 clamp(30px,3.3vw,44px)/1.17 Georgia,serif;letter-spacing:-.025em;margin:0 0 18px;max-width:850px}
h2{font:600 27px/1.3 Georgia,serif;letter-spacing:-.01em;margin:45px 0 16px;padding-top:13px;border-top:1px solid var(--line)}
h3{font-size:18px;margin-top:30px}p{margin:15px 0}article>p:first-of-type{font-size:13px;color:var(--muted)}
strong{font-weight:650}li{margin-bottom:14px}code{font:12px/1.6 ui-monospace,Menlo,monospace;overflow-wrap:anywhere;background:#eaece6;border-radius:3px;padding:2px 4px}
pre{overflow:auto;padding:18px;background:#eaece6;border-radius:8px}pre code{padding:0}
.tablewrap{overflow:auto;margin:22px 0;border:1px solid var(--line);border-radius:8px;background:var(--paper)}
table{border-collapse:collapse;width:100%;min-width:610px;font-size:13px;line-height:1.55}th,td{text-align:left;vertical-align:top;padding:12px 14px;border-bottom:1px solid var(--line)}
th{background:var(--soft);font-weight:650}tr:last-child td{border:0}td:first-child{min-width:155px}td a{overflow-wrap:anywhere}
aside{align-self:start;position:sticky;top:20px;max-height:94vh;overflow:auto;font-size:13px}
.panel{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:18px}.panel h2{font:650 15px/1.4 system-ui;margin:0 0 10px;border:0;padding:0}
.small{font-size:12px;color:var(--muted)}nav a{display:block;margin:7px 0;text-decoration:none;line-height:1.5}
textarea,input{font:14px/1.5 system-ui;width:100%;border:1px solid var(--line);padding:9px;border-radius:5px;margin:5px 0;background:white;color:var(--ink)}
textarea{resize:vertical;min-height:95px}.selected{font-size:12px;border-left:3px solid var(--accent);padding-left:9px;max-height:100px;overflow:auto;margin:10px 0;color:var(--muted);white-space:pre-wrap}
.comment{border-top:1px solid var(--line);padding:12px 0;overflow-wrap:anywhere}.comment p{white-space:pre-wrap;margin:6px 0}.comment button{font-size:11px;padding:4px 7px}
.reply{background:var(--soft);padding:10px;border-radius:7px;margin-top:10px}.notice{max-width:1260px;margin:20px auto 0;padding:14px 20px;background:var(--soft);border-radius:8px;font-size:14px}
.flash{background:#fff1b8;transition:background 1s}.actions{display:flex;gap:7px;flex-wrap:wrap}#status{min-height:2em;margin-top:9px}
@media(max-width:1000px){.layout{grid-template-columns:minmax(0,1fr);padding:26px 20px;gap:25px}aside{position:static;max-height:none}article{max-width:850px}.top{padding:15px 20px}table{min-width:560px}}
@media print{aside,.top{display:none}.layout{display:block;padding:0}body{background:white}.tablewrap{overflow:visible}table{min-width:0}h2{break-after:avoid}}
</style></head><body>
<header class="top"><span>Research assessment</span><a href="__SOURCE__">Markdown source</a></header>
__NOTICE__
<div class="layout"><article id="report">__BODY__</article>
<aside><div class="panel"><h2>In this assessment</h2><nav>__TOC__</nav></div>
<div class="panel"><h2>Leave a comment</h2><p class="small">Select text in the assessment, then add a note. Comments save locally to this worktree.</p>
<div id="quote" class="selected">No text selected</div><label class="small" for="author">Name</label><input id="author" value="Oscar" autocomplete="name">
<label class="small" for="note">Comment</label><textarea id="note" placeholder="Your note…"></textarea>
<div class="actions"><button id="save" disabled>Save comment</button><button id="export">Export JSON</button></div>
<div id="status" class="small" role="status">Loading saved comments…</div><div id="comments"></div></div></aside></div>
<script id="meta" type="application/json">__META__</script>
<script id="seed" type="application/json">__SEED__</script>
<script>
const M=JSON.parse(document.getElementById('meta').textContent), KEY=M.report_id+':'+M.report_sha256;
const seed=JSON.parse(document.getElementById('seed').textContent);
const $=id=>document.getElementById(id), report=$('report');let comments=[],selection=null,ready=false;
const matches=d=>d&&d.report_id===M.report_id&&d.report_sha256===M.report_sha256&&Array.isArray(d.comments);
function payload(){return {...M,comments,saved_at:new Date().toISOString()};}
function render(){
 $('comments').replaceChildren();
 for(const c of comments){
  const box=document.createElement('div');box.className='comment';
  const author=document.createElement('strong');author.textContent=c.author;
  const q=document.createElement('div');q.className='selected';q.textContent=c.quote;
  const note=document.createElement('p');note.textContent=c.note;
  const jump=document.createElement('button');jump.textContent='Show passage';jump.onclick=()=>{const el=$(c.anchor);if(el){el.scrollIntoView({block:'center'});el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),1800);}};
  box.append(author,q,note,jump);
  for(const r of c.replies||[]){const reply=document.createElement('div');reply.className='reply';const name=document.createElement('strong');name.textContent=r.author;const text=document.createElement('p');text.textContent=r.text;reply.append(name,text);if(r.link?.startsWith('/')&&!r.link.startsWith('//')){const a=document.createElement('a');a.href=r.link;a.textContent='Read follow-up';reply.append(a);}box.append(reply);}
  $('comments').append(box);
 }
}
async function persist(){
 const d=payload();let local=false;try{localStorage.setItem(KEY,JSON.stringify(d));local=true;}catch(e){}
 try{const r=await fetch('/save?p='+encodeURIComponent(M.save_path),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d,null,2)});if(!r.ok)throw Error();$('status').textContent='Saved to worktree · '+comments.length+' comments';}
 catch(e){$('status').textContent=local?'Saved in this browser only; export JSON as backup.':'Could not save; export JSON before closing.';}
}
document.addEventListener('selectionchange',()=>{
 const s=getSelection();if(!s||s.isCollapsed||!report.contains(s.anchorNode)||!report.contains(s.focusNode))return;
 const node=s.anchorNode.nodeType===1?s.anchorNode:s.anchorNode.parentElement;
 const block=node.closest('[data-block]');if(!block)return;
 selection={quote:s.toString(),anchor:block.id};$('quote').textContent=selection.quote;update();
});
function update(){$('save').disabled=!ready||!selection||!$('note').value.trim();}
$('note').oninput=update;
$('save').onclick=async()=>{if(!selection||!$('note').value.trim())return;comments.push({id:crypto.randomUUID(),...selection,author:$('author').value.trim()||'Oscar',note:$('note').value.trim(),ts:new Date().toISOString()});$('note').value='';selection=null;$('quote').textContent='No text selected';update();render();await persist();};
$('export').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(payload(),null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=M.report_id+'-comments.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
(async()=>{
 let local=null,remote=null;try{const d=JSON.parse(localStorage.getItem(KEY));if(matches(d))local=d;}catch(e){}
 try{const r=await fetch('/file?p='+encodeURIComponent(M.save_path));if(r.ok){const d=await r.json();if(matches(d))remote=d;}}catch(e){}
 const byId=new Map();for(const d of [matches(seed)?seed:null,remote,local])for(const c of d?.comments||[]){const old=byId.get(c.id);const replies=new Map();for(const r of [...old?.replies||[],...c.replies||[]])replies.set(r.id||r.author+':'+r.text,r);byId.set(c.id,{...old,...c,replies:Array.from(replies.values())});}
 comments=Array.from(byId.values());render();ready=true;update();$('status').textContent=comments.length+' saved comments';
})();
</script></body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output-name", default="transluce_assessment")
    parser.add_argument("--report-id", default=REPORT_ID)
    parser.add_argument("--title", default="Transluce benchmark assessment")
    parser.add_argument("--notice", default="", help="Plain-text provenance notice above the unmodified report")
    parser.add_argument("--comments", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", args.output_name):
        parser.error("output-name must contain lowercase letters, digits or underscores")
    source_path = args.source.resolve()
    source = source_path.read_text()
    # Reports can quote adversarial records: never load remote images or HTML.
    body = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image").render(source)

    def local_link(match):
        href = match.group(1)
        if not re.match(r"https?://|#|mailto:", href):
            path = (source_path.parent / href).resolve()
            if path.is_file() and ROOT in path.parents:
                pages = {HERE / "assessment.md": "transluce_assessment", HERE / "data_preparation.md": "transluce_data_preparation"}
                if path in pages:
                    return f'href="/{pages[path]}.html"'
                return 'href="/file?p=' + quote(str(path), safe="") + '"'
        return match.group(0)

    body = re.sub(r'href="([^"]+)"', local_link, body)
    toc = []
    index = 0

    def block(match):
        nonlocal index
        index += 1
        tag, content = match.groups()
        anchor = f"p-{index}"
        if tag == "h2":
            toc.append(f'<a href="#{anchor}">{content}</a>')
        return f'<{tag} id="{anchor}" data-block="1">{content}</{tag}>'

    body = re.sub(r"<(h[123]|p|li|td)>(.*?)</\1>", block, body, flags=re.S)
    body = body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
    metadata = {
        "report_id": args.report_id,
        "report_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "save_path": str(ROOT / "viewers/data" / (args.output_name.replace("_", "-") + "-review.json")),
    }
    seed = json.loads(args.comments.read_text()) if args.comments else None
    if seed and (seed["report_sha256"] != metadata["report_sha256"] or seed["report_id"] != metadata["report_id"]):
        raise ValueError("Comment export does not match the selected source snapshot")
    output = ROOT / "viewers" / (args.output_name + ".html")
    result = SHELL.replace("__BODY__", body).replace("__TOC__", "".join(toc))
    result = result.replace("__SOURCE__", html.escape("/file?p=" + quote(str(source_path), safe="")))
    result = result.replace("__META__", json.dumps(metadata).replace("<", "\\u003c"))
    result = result.replace("__SEED__", json.dumps(seed).replace("<", "\\u003c"))
    result = result.replace("__TITLE__", html.escape(args.title))
    notice = '<div class="notice">The <a href="/transluce_data_preparation.html">data-preparation follow-up</a> incorporates your comments and supersedes this assessment’s effort and report-length proposals. Replies are in the comment panel below.</div>' if args.report_id == REPORT_ID else ""
    if args.notice:
        notice += '<div class="notice">' + html.escape(args.notice) + '</div>'
    result = result.replace("__NOTICE__", notice)
    output.write_text(result)
    print(f"Rendered {output}; {len(toc)} navigation entries; {len(source.split())} source words")


if __name__ == "__main__":
    main()
