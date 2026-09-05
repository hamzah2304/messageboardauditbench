#!/usr/bin/env python3
"""
Build a COMBINED coverage UI (coverage_combined.html) that merges the exported
coverage-review JSONs from multiple reviewers (e.g. hasan + hamzah), shows each
comment attributed by author and colour, and lets you add/delete and re-export.

Review files: any *.json in hasan/ (or paths given as CLI args) whose top-level
looks like a coverage export (has a "comments" list and report == the human report).
Author = filename stem's first token (hasan_hackathon.json -> "hasan"); override with
name=path pairs, e.g.  python build_combined_coverage.py hamzah=reviews/hamzah.json hasan=hasan_hackathon.json

Round-trips: the combined UI's "Save JSON" exports the same shape, so re-running this
script over the latest exports re-merges everyone's edits.
"""
import re, json, sys, glob, hashlib
from pathlib import Path

HERE = Path(__file__).parent
WD = Path("/workspace/collusion/wiki-download")

# ---- discover review files ------------------------------------------------
def is_review(p):
    try:
        d = json.loads(Path(p).read_text())
        return isinstance(d, dict) and isinstance(d.get("comments"), list) and "collusion.wiki" in str(d.get("report", ""))
    except Exception:
        return False

GENERIC = {"coverage", "review", "hackathon", "combined", "export", "json", "data", "final", "v1", "v2"}
def author_of(path):
    stem = Path(path).stem
    toks = [t for t in re.split(r"[_\-.]", stem.lower()) if t and t not in GENERIC]
    return toks[0] if toks else stem.lower()

pairs = []
args = sys.argv[1:]
if args:
    for a in args:
        if "=" in a:
            name, path = a.split("=", 1)
            pairs.append((name.lower(), path))
        else:
            pairs.append((author_of(a), a))
else:
    for p in sorted(glob.glob(str(HERE / "*.json"))):
        base = Path(p).name
        if base in ("coverage_data.json", "validation_data.json"):
            continue
        if is_review(p):
            pairs.append((author_of(p), p))

# ---- merge comments -------------------------------------------------------
merged = []
authors = []
for author, path in pairs:
    if author not in authors:
        authors.append(author)
    d = json.loads(Path(path).read_text())
    for j, c in enumerate(d.get("comments", [])):
        merged.append({
            "id": f"{author}:{c.get('ts', j)}:{j}",
            "author": author,
            "s": c.get("s", -1), "e": c.get("e", -1),
            "quote": c.get("quote", ""), "type": c.get("type", "note"),
            "claim": c.get("claim"), "note": c.get("note", ""),
            "ts": c.get("ts", ""),
            "replies": c.get("replies", []),
        })
authors = sorted(set(authors))
COLORS = ["#CDE9DD", "#DCE4F5", "#F5E4CC", "#EADCF0", "#E0EFE0", "#F5DCDC"]  # per-author highlight tints
UNDER = ["#065F46", "#274456", "#92400E", "#4A3B76", "#2E7D6B", "#991B1B"]
author_slot = {a: i % len(COLORS) for i, a in enumerate(authors)}
seed_hash = hashlib.sha1(json.dumps(merged, sort_keys=True).encode()).hexdigest()[:12]

print(f"reviewers: {pairs or '(none found)'}")
print(f"authors: {authors} | merged comments: {len(merged)} | seed {seed_hash}")

# ---- assemble site HTML with inlined CSS ----------------------------------
html = (WD / "index.html").read_text()
for href, rel in [("tokens.css", "tokens.css"), ("styles.css", "styles.css"),
                  ("chrome.css", "chrome.css"), ("figures/figures.css", "figures/figures.css")]:
    css = (WD / rel).read_text()
    html = re.sub(r'<link rel="stylesheet" href="' + re.escape(href) + r'[^"]*"\s*/?>',
                  (lambda c: (lambda m: "<style>\n" + c + "\n</style>"))(css), html, count=1)
html = re.sub(r'(src="(?:figures/[^"?]+|site\.js))\?[^"]*"', r'\1"', html)

cov = json.loads((HERE / "coverage_data.json").read_text())
def neut(s):
    return s.replace("</script", "<\\/script").replace("</", "<\\/")
embed = ("CDATA=" + neut(json.dumps(cov, ensure_ascii=False)) + ";\n"
         + "SEED=" + neut(json.dumps(merged, ensure_ascii=False)) + ";\n"
         + "AUTHORS=" + json.dumps(authors) + ";\n"
         + "ASLOT=" + json.dumps(author_slot) + ";\n"
         + "SEEDHASH=" + json.dumps(seed_hash) + ";\n")

# per-author highlight colours
hl_css = "\n".join(
    f"::highlight(cmt-{i}){{background-color:{COLORS[i]};text-decoration:underline wavy {UNDER[i]}}}"
    for i in range(len(authors))) or "::highlight(cmt-0){background-color:#CDE9DD}"
author_badge_css = "\n".join(
    f".au-{a}{{background:{COLORS[author_slot[a]]};color:{UNDER[author_slot[a]]}}}" for a in authors)

INJECT_CSS = r'''<style id="cov-style">
body{padding-right:400px !important}
#cov-side{position:fixed;top:0;right:0;bottom:0;width:388px;overflow:auto;background:#FAFAF7;border-left:1px solid #E0DDD4;z-index:9000;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:13px}
#cov-side .csh{position:sticky;top:0;background:#F4F3EE;border-bottom:1px solid #E0DDD4;padding:10px 12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#cov-side h2{font-size:14px;margin:0;color:#C15F3C}
#cov-side .counter{font-size:11px;color:#666;width:100%}
#cov-side .btn{border:1px solid #E0DDD4;background:#fff;border-radius:7px;padding:5px 10px;font-weight:600;cursor:pointer;font-size:12px;color:#666}
#cov-side .btn.save{background:#C15F3C;color:#fff;border:none}
#cov-side .tabs{display:flex;gap:6px;padding:8px 12px 0}
#cov-side .tab{padding:5px 11px;border:1px solid #E0DDD4;border-radius:7px;background:#fff;color:#666;cursor:pointer;font-weight:700;font-size:12px}
#cov-side .tab.active{background:#C15F3C;color:#fff;border-color:#C15F3C}
#cov-side .pane{padding:8px 12px}
#cov-side .filt{font-size:11px;color:#666;padding:2px 12px 6px;display:flex;gap:10px;flex-wrap:wrap}
#cov-side .filt label{cursor:pointer}
.cclaim{background:#fff;border:1px solid #E0DDD4;border-radius:8px;padding:7px 9px;margin:6px 0;cursor:pointer}
.cclaim:hover{border-color:#C15F3C}
.cclaim .top{display:flex;gap:6px;align-items:center;font-size:11px;color:#666;margin-bottom:2px}
.lvl{font-weight:800;font-size:10px;color:#fff;border-radius:4px;padding:0 5px}
.lvl.l1{background:#4A6B8A}.lvl.l2{background:#2E7D6B}.lvl.l3{background:#C15F3C}.lvl.l4{background:#7A5AA0}
.bdg{font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px}.b-ok{background:#D1FAE5;color:#065F46}.b-no{background:#FEF3C7;color:#92400E}
.cclaim .t{font-size:12px;color:#1A1A1A}
.cmt{background:#fff;border:1px solid #E0DDD4;border-left:4px solid #991B1B;border-radius:0 8px 8px 0;padding:7px 9px;margin:6px 0;font-size:12px}
.cmt.note{border-left-color:#4A6B8A}.cmt.covered{border-left-color:#065F46}
.cmt .au{font-size:10px;font-weight:800;padding:1px 6px;border-radius:4px;text-transform:uppercase}
.cmt .q{font-family:ui-monospace,Menlo,monospace;font-size:11px;background:#FAFAF7;border-radius:5px;padding:3px 6px;margin:3px 0}
.cmt .x{float:right;color:#999;cursor:pointer;font-weight:700;margin-left:6px}
.reply{margin:4px 0 0 10px;padding:4px 8px;border-left:2px solid #E0DDD4;font-size:12px}
.reply .au{font-size:9px}
.reply-add{display:flex;gap:5px;margin:6px 0 0 10px}
.reply-add input{flex:1;border:1px solid #E0DDD4;border-radius:6px;padding:4px 6px;font-size:12px;font-family:inherit}
.reply-add button{border:1px solid #E0DDD4;background:#fff;border-radius:6px;padding:4px 9px;font-size:11px;font-weight:700;color:#666;cursor:pointer}
.reply-add button:hover{border-color:#C15F3C;color:#C15F3C}
#cov-qbtn{position:absolute;z-index:9500;display:none;background:#C15F3C;color:#fff;border:none;border-radius:7px;padding:6px 11px;font-weight:700;font-size:12px;cursor:pointer;box-shadow:0 3px 12px rgba(0,0,0,.2)}
#cov-pop{position:absolute;z-index:9600;display:none;background:#fff;border:1px solid #E0DDD4;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.16);padding:10px;width:300px;font-family:system-ui}
#cov-pop select,#cov-pop textarea,#cov-pop input{width:100%;border:1px solid #E0DDD4;border-radius:6px;padding:6px;font-size:12px;margin-top:4px;font-family:inherit}
#cov-pop .r{display:flex;gap:6px;margin-top:6px}#cov-pop button{flex:1;border:none;border-radius:7px;padding:7px;font-weight:700;cursor:pointer}
#cov-pop .add{background:#C15F3C;color:#fff}#cov-pop .cancel{background:#eee;color:#555}
::highlight(cov){background-color:#FDECD9}
::highlight(act){background-color:#ffd76b}
__HLCSS__
__AUBADGE__
@media print{#cov-side,#cov-qbtn,#cov-pop{display:none!important}body{padding-right:0!important}}
</style>
'''.replace("__HLCSS__", hl_css).replace("__AUBADGE__", author_badge_css)

INJECT_HTML = r'''<div id="cov-side">
  <div class="csh"><h2>Coverage &mdash; combined</h2>
    <button class="btn" id="cov-copy">Copy JSON</button><button class="btn save" id="cov-save">Save JSON</button>
    <button class="btn" id="cov-reset" title="Reset to the merged file set">Reset</button>
    <span class="counter" id="cov-counter"></span></div>
  <div class="tabs"><button class="tab active" data-tab="claims">Claims</button><button class="tab" data-tab="comments">Comments <span id="cov-cc"></span></button></div>
  <div class="filt" id="cov-filt"></div>
  <div class="pane" id="cov-claims"></div>
  <div class="pane" id="cov-comments" style="display:none"></div>
</div>
<button id="cov-qbtn">&#65291; Comment</button>
<div id="cov-pop">
  <div style="font-weight:700;font-size:12px">New comment</div>
  <div class="q" style="font-family:ui-monospace,Menlo,monospace;font-size:11px;background:#FAFAF7;border-radius:5px;padding:4px 6px;max-height:80px;overflow:auto" id="cov-pop-q"></div>
  <input id="cov-pop-author" placeholder="your name (author)">
  <select id="cov-pop-type"><option value="gap">&#9888; Gap &mdash; not covered by any claim</option><option value="note">Note</option><option value="covered">&#10003; Confirm covered</option></select>
  <select id="cov-pop-claim"></select>
  <textarea id="cov-pop-note" rows="2" placeholder="Note..."></textarea>
  <div class="r"><button class="cancel" id="cov-pop-cancel">Cancel</button><button class="add" id="cov-pop-add">Add</button></div>
</div>
<script>
__EMBED__
(function(){
var LS="coverage_combined_"+SEEDHASH;
var C; try{C=JSON.parse(localStorage.getItem(LS))}catch(e){}
if(!C||!C.comments){C={comments:JSON.parse(JSON.stringify(SEED))};}   // fresh seed when the merged set changes
var hidden={}; // author -> hidden?
var ROOT=document.querySelector('article.essay')||document.querySelector('.main')||document.body;
var supportsHL=(typeof Highlight!=="undefined"&&CSS&&CSS.highlights);
var nodes=[],starts=[],FULL="";
(function walk(n){for(var c=n.firstChild;c;c=c.nextSibling){if(c.nodeType===3){starts.push(FULL.length);nodes.push(c);FULL+=c.nodeValue;}else if(c.nodeType===1){var tg=c.tagName;if(tg==='SCRIPT'||tg==='STYLE')continue;walk(c);}}})(ROOT);
var nodeIdx=new Map();nodes.forEach(function(n,i){nodeIdx.set(n,i);});
function locate(off){var lo=0,hi=nodes.length-1,ans=0;while(lo<=hi){var m=(lo+hi)>>1;if(starts[m]<=off){ans=m;lo=m+1;}else hi=m-1;}return [nodes[ans],off-starts[ans]];}
function rangeFor(s,e){var a=locate(s),b=locate(e);var r=document.createRange();try{r.setStart(a[0],Math.min(a[1],a[0].nodeValue.length));r.setEnd(b[0],Math.min(b[1],b[0].nodeValue.length));}catch(err){return null;}return r;}
function norm(s){return s.replace(/\s+/g," ").trim();}
var NFULL=FULL.replace(/\s+/g," ");
var rawOf=[];(function(){var j=0,ps=false;for(var k=0;k<FULL.length;k++){var ch=FULL[k];if(/\s/.test(ch)){if(!ps){rawOf[j]=k;j++;ps=true;}}else{rawOf[j]=k;j++;ps=false;}}rawOf[j]=FULL.length;})();
function findRaw(anchor){if(!anchor)return -1;var p=FULL.indexOf(anchor);if(p>=0)return [p,p+anchor.length];var na=norm(anchor);if(!na)return -1;var q=NFULL.indexOf(na);if(q<0)return -1;var s=rawOf[q],e=rawOf[Math.min(q+na.length,rawOf.length-1)];return (s!=null&&e!=null&&e>s)?[s,e]:-1;}
CDATA.claims.forEach(function(c){var r=c.located?findRaw(c.anchor):-1;if(r&&r!==-1){c._s=r[0];c._e=r[1];}else{c._s=-1;c._e=-1;c.located=false;}});
var covHL,actHL;
function paintCov(){if(!supportsHL)return;covHL=new Highlight();CDATA.claims.forEach(function(c){if(c._s>=0){var r=rangeFor(c._s,c._e);if(r)covHL.add(r);}});CSS.highlights.set('cov',covHL);}
function paintCmt(){if(!supportsHL)return;
  var slots={}; for(var a in ASLOT){slots[ASLOT[a]]=new Highlight();}
  C.comments.forEach(function(m){ if(m.s>=0 && !hidden[m.author]){var r=rangeFor(m.s,m.e); if(r){var sl=(ASLOT[m.author]!=null?ASLOT[m.author]:0); if(!slots[sl])slots[sl]=new Highlight(); slots[sl].add(r);}}});
  for(var sl in slots){CSS.highlights.set('cmt-'+sl,slots[sl]);}
}
function flash(s,e){if(!supportsHL)return;actHL=new Highlight();var r=rangeFor(s,e);if(r)actHL.add(r);CSS.highlights.set('act',actHL);setTimeout(function(){CSS.highlights.delete('act');},1600);}
function scrollTo(s,e){var r=rangeFor(s,e);if(!r)return;var el=r.startContainer.parentElement;if(el)el.scrollIntoView({block:'center',behavior:'smooth'});flash(s,e);}
paintCov();paintCmt();
function esc(s){return (s||"").replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function save(){try{localStorage.setItem(LS,JSON.stringify(C))}catch(e){}}
function renderClaims(){
  var loc=CDATA.claims.filter(function(c){return c.located}).length;
  document.getElementById('cov-counter').textContent=CDATA.claims.length+" claims · "+loc+" located · "+C.comments.length+" comments";
  document.getElementById('cov-claims').innerHTML=CDATA.claims.map(function(c,i){
    return '<div class="cclaim" data-i="'+i+'"><div class="top"><span class="lvl l'+c.level+'">L'+c.level+'</span><b>'+c.id+'</b><span>· '+esc(c.section)+'</span>'
      +(c.located?'<span class="bdg b-ok">in report</span>':'<span class="bdg b-no">not located</span>')+'</div><div class="t">'+esc(c.claim)+'</div></div>';}).join('');
  [].forEach.call(document.querySelectorAll('.cclaim'),function(el){el.onclick=function(){var c=CDATA.claims[+el.dataset.i];if(c._s>=0)scrollTo(c._s,c._e);};});
}
function renderFilt(){
  var auths={}; C.comments.forEach(function(m){auths[m.author]=(auths[m.author]||0)+1;});
  var ks=Object.keys(auths).sort();
  document.getElementById('cov-filt').innerHTML = ks.length? ('Show: '+ks.map(function(a){return '<label><input type="checkbox" data-au="'+a+'" '+(hidden[a]?'':'checked')+'> <span class="au au-'+a+'" style="padding:0 5px;border-radius:4px">'+esc(a)+'</span> '+auths[a]+'</label>';}).join('')) : '';
  [].forEach.call(document.querySelectorAll('#cov-filt input'),function(x){x.onchange=function(){hidden[x.dataset.au]=!x.checked;paintCmt();renderComments();};});
}
function renderComments(){
  document.getElementById('cov-cc').textContent="("+C.comments.length+")";
  var items=C.comments.map(function(m,i){return {m:m,i:i};}).filter(function(o){return !hidden[o.m.author];})
    .sort(function(a,b){return (a.m.s||0)-(b.m.s||0);});
  document.getElementById('cov-comments').innerHTML=items.map(function(o){var m=o.m;
    return '<div class="cmt '+m.type+'"><span class="x" data-del="'+o.i+'">✕</span>'
      +'<span class="au au-'+m.author+'">'+esc(m.author)+'</span> '
      +'<b>'+(m.type==='gap'?'⚠ GAP':m.type==='covered'?'✓ COVERED':'NOTE')+'</b>'+(m.claim?' · '+m.claim:'')
      +'<div class="q" data-jump="'+o.i+'" style="cursor:pointer">'+esc((m.quote||'').slice(0,220))+'</div>'
      +(m.note?'<div>'+esc(m.note)+'</div>':'')
      +(m.replies||[]).map(function(rp,ri){return '<div class="reply"><span class="x" data-delr="'+o.i+'|'+ri+'">✕</span><span class="au au-'+(rp.author||'me')+'">'+esc(rp.author||'me')+'</span> '+esc(rp.text||'')+'</div>';}).join('')
      +'<div class="reply-add"><input data-rin="'+o.i+'" placeholder="reply..."><button data-rep="'+o.i+'">Reply</button></div>'
      +'</div>';}).join('')
    ||'<div style="color:#999">No comments. Select text in the report to add one.</div>';
  [].forEach.call(document.querySelectorAll('[data-del]'),function(x){x.onclick=function(){if(confirm('Delete this comment (and its replies)?')){C.comments.splice(+x.dataset.del,1);save();paintCmt();renderFilt();renderComments();renderClaims();}};});
  [].forEach.call(document.querySelectorAll('[data-jump]'),function(x){x.onclick=function(){var m=C.comments[+x.dataset.jump];if(m.s>=0)scrollTo(m.s,m.e);};});
  [].forEach.call(document.querySelectorAll('[data-delr]'),function(x){x.onclick=function(){var p=x.dataset.delr.split('|');C.comments[+p[0]].replies.splice(+p[1],1);save();renderComments();};});
  [].forEach.call(document.querySelectorAll('[data-rep]'),function(b){b.onclick=function(){var i=+b.dataset.rep;var inp=document.querySelector('[data-rin="'+i+'"]');var txt=(inp.value||'').trim();if(!txt)return;var au=(localStorage.getItem('cov_author')||'me');if(!C.comments[i].replies)C.comments[i].replies=[];C.comments[i].replies.push({author:au,text:txt,ts:new Date().toISOString()});save();renderComments();};});
}
document.getElementById('cov-pop-claim').innerHTML='<option value="">(optional) link a claim...</option>'+CDATA.claims.map(function(c){return '<option value="'+c.id+'">'+c.id+' — '+esc(c.claim.slice(0,46))+'</option>';}).join('');
[].forEach.call(document.querySelectorAll('#cov-side .tab'),function(t){t.onclick=function(){document.querySelectorAll('#cov-side .tab').forEach(function(x){x.classList.remove('active')});t.classList.add('active');document.getElementById('cov-claims').style.display=t.dataset.tab==='claims'?'':'none';document.getElementById('cov-comments').style.display=t.dataset.tab==='comments'?'':'none';};});
var SEL=null,qbtn=document.getElementById('cov-qbtn'),pop=document.getElementById('cov-pop');
function offOf(node,o){var i=nodeIdx.get(node);return i==null?-1:starts[i]+o;}
document.addEventListener('mouseup',function(ev){
  if(ev.target.closest&&ev.target.closest('#cov-side'))return;
  setTimeout(function(){var s=window.getSelection();if(!s||s.isCollapsed||s.rangeCount===0){qbtn.style.display='none';return;}
    var r=s.getRangeAt(0);if(!ROOT.contains(r.startContainer)||!ROOT.contains(r.endContainer)){qbtn.style.display='none';return;}
    var a=offOf(r.startContainer,r.startOffset),b=offOf(r.endContainer,r.endOffset);if(a<0||b<0||b<=a){qbtn.style.display='none';return;}
    SEL={s:a,e:b,quote:s.toString()};var rc=r.getBoundingClientRect();qbtn.style.left=(rc.left+window.scrollX)+"px";qbtn.style.top=(rc.bottom+window.scrollY+6)+"px";qbtn.style.display='block';},10);
});
qbtn.onclick=function(){if(!SEL)return;document.getElementById('cov-pop-q').textContent=SEL.quote.slice(0,400);
  document.getElementById('cov-pop-author').value=localStorage.getItem('cov_author')||'';
  document.getElementById('cov-pop-type').value='gap';document.getElementById('cov-pop-claim').value='';document.getElementById('cov-pop-note').value='';
  pop.style.left=qbtn.style.left;pop.style.top=qbtn.style.top;pop.style.display='block';qbtn.style.display='none';document.getElementById('cov-pop-author').focus();};
document.getElementById('cov-pop-cancel').onclick=function(){pop.style.display='none';};
document.getElementById('cov-pop-add').onclick=function(){if(!SEL)return;
  var au=(document.getElementById('cov-pop-author').value||'me').trim().toLowerCase(); localStorage.setItem('cov_author',au);
  C.comments.push({id:au+':'+Date.now(),author:au,s:SEL.s,e:SEL.e,quote:SEL.quote,type:document.getElementById('cov-pop-type').value,claim:document.getElementById('cov-pop-claim').value||null,note:document.getElementById('cov-pop-note').value||"",ts:new Date().toISOString()});
  save();paintCmt();renderFilt();renderComments();renderClaims();pop.style.display='none';document.querySelector('#cov-side .tab[data-tab=comments]').click();};
document.addEventListener('mousedown',function(e){if(!pop.contains(e.target)&&e.target!==qbtn)pop.style.display='none';});
document.getElementById('cov-reset').onclick=function(){if(confirm('Discard local edits and reset to the merged file set?')){C={comments:JSON.parse(JSON.stringify(SEED))};hidden={};save();paintCmt();renderFilt();renderComments();renderClaims();}};
function exportObj(){return {saved_at:new Date().toISOString(),report:"human collusion.wiki report",n_claims:CDATA.claims.length,located:CDATA.claims.filter(function(c){return c.located}).length,authors:AUTHORS,comments:C.comments};}
document.getElementById('cov-save').onclick=function(){var b=new Blob([JSON.stringify(exportObj(),null,1)],{type:"application/json"});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download="coverage_combined.json";a.click();};
document.getElementById('cov-copy').onclick=function(){navigator.clipboard&&navigator.clipboard.writeText(JSON.stringify(exportObj(),null,1));this.textContent="Copied";var t=this;setTimeout(function(){t.textContent="Copy JSON"},1200);};
renderClaims();renderFilt();renderComments();save();
})();
</script>
'''.replace("__EMBED__", embed)

html = html.replace("</head>", INJECT_CSS + "</head>", 1)
html = html.replace("</body>", INJECT_HTML + "</body>", 1)
(HERE / "coverage_combined.html").write_text(html)
print("wrote coverage_combined.html bytes:", len(html))
