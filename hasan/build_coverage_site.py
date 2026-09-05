#!/usr/bin/env python3
"""Build coverage.html from the real collusion.wiki HTML (inlined CSS) + a coverage/comment layer."""
import re, json
from pathlib import Path

HERE = Path(__file__).parent
WD = Path("/workspace/collusion/wiki-download")
html = (WD / "index.html").read_text()

# inline the site stylesheets (function replacement so CSS \-escapes aren't treated as regex refs)
for href, rel in [("tokens.css", "tokens.css"), ("styles.css", "styles.css"),
                  ("chrome.css", "chrome.css"), ("figures/figures.css", "figures/figures.css")]:
    css = (WD / rel).read_text()
    html = re.sub(r'<link rel="stylesheet" href="' + re.escape(href) + r'[^"]*"\s*/?>',
                  (lambda c: (lambda m: "<style>\n" + c + "\n</style>"))(css), html, count=1)
# drop ?v= cache-busters so figure/site scripts load relative from hasan/
html = re.sub(r'(src="(?:figures/[^"?]+|site\.js))\?[^"]*"', r'\1"', html)

cov = json.loads((HERE / "coverage_data.json").read_text())
embed = "CDATA=" + json.dumps(cov, ensure_ascii=False).replace("</script", "<\\/script").replace("</", "<\\/") + ";"

INJECT_CSS = r'''<style id="cov-style">
body{padding-right:390px !important}
#cov-side{position:fixed;top:0;right:0;bottom:0;width:378px;overflow:auto;background:#FAFAF7;border-left:1px solid #E0DDD4;z-index:9000;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:13px}
#cov-side .csh{position:sticky;top:0;background:#F4F3EE;border-bottom:1px solid #E0DDD4;padding:10px 12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#cov-side h2{font-size:14px;margin:0;color:#C15F3C}
#cov-side .counter{font-size:11px;color:#666;width:100%}
#cov-side .btn{border:1px solid #E0DDD4;background:#fff;border-radius:7px;padding:5px 10px;font-weight:600;cursor:pointer;font-size:12px;color:#666}
#cov-side .btn.save{background:#C15F3C;color:#fff;border:none}
#cov-side .tabs{display:flex;gap:6px;padding:8px 12px 0}
#cov-side .tab{padding:5px 11px;border:1px solid #E0DDD4;border-radius:7px;background:#fff;color:#666;cursor:pointer;font-weight:700;font-size:12px}
#cov-side .tab.active{background:#C15F3C;color:#fff;border-color:#C15F3C}
#cov-side .pane{padding:8px 12px}
.cclaim{background:#fff;border:1px solid #E0DDD4;border-radius:8px;padding:7px 9px;margin:6px 0;cursor:pointer}
.cclaim:hover{border-color:#C15F3C}
.cclaim .top{display:flex;gap:6px;align-items:center;font-size:11px;color:#666;margin-bottom:2px}
.lvl{font-weight:800;font-size:10px;color:#fff;border-radius:4px;padding:0 5px}
.lvl.l1{background:#4A6B8A}.lvl.l2{background:#2E7D6B}.lvl.l3{background:#C15F3C}.lvl.l4{background:#7A5AA0}
.bdg{font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px}.b-ok{background:#D1FAE5;color:#065F46}.b-no{background:#FEF3C7;color:#92400E}
.cclaim .t{font-size:12px;color:#1A1A1A}
.cmt{background:#fff;border:1px solid #E0DDD4;border-left:4px solid #991B1B;border-radius:0 8px 8px 0;padding:7px 9px;margin:6px 0;font-size:12px}
.cmt.note{border-left-color:#4A6B8A}.cmt.covered{border-left-color:#065F46}
.cmt .q{font-family:ui-monospace,Menlo,monospace;font-size:11px;background:#FAFAF7;border-radius:5px;padding:3px 6px;margin:3px 0}
.cmt .x{float:right;color:#999;cursor:pointer;font-weight:700}
#cov-qbtn{position:absolute;z-index:9500;display:none;background:#C15F3C;color:#fff;border:none;border-radius:7px;padding:6px 11px;font-weight:700;font-size:12px;cursor:pointer;box-shadow:0 3px 12px rgba(0,0,0,.2)}
#cov-pop{position:absolute;z-index:9600;display:none;background:#fff;border:1px solid #E0DDD4;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.16);padding:10px;width:300px;font-family:system-ui}
#cov-pop select,#cov-pop textarea{width:100%;border:1px solid #E0DDD4;border-radius:6px;padding:6px;font-size:12px;margin-top:4px;font-family:inherit}
#cov-pop .r{display:flex;gap:6px;margin-top:6px}#cov-pop button{flex:1;border:none;border-radius:7px;padding:7px;font-weight:700;cursor:pointer}
#cov-pop .add{background:#C15F3C;color:#fff}#cov-pop .cancel{background:#eee;color:#555}
::highlight(cov){background-color:#FDECD9}
::highlight(act){background-color:#ffd76b}
::highlight(cmt){background-color:#CDE9DD;text-decoration:underline wavy #065F46}
@media print{#cov-side,#cov-qbtn,#cov-pop{display:none!important}body{padding-right:0!important}}
</style>
'''

INJECT_HTML = r'''<div id="cov-side">
  <div class="csh"><h2>__TITLE__</h2>
    <button class="btn" id="cov-copy">Copy JSON</button><button class="btn save" id="cov-save">Save JSON</button>
    <span class="counter" id="cov-counter"></span></div>
  <div class="tabs"><button class="tab active" data-tab="claims">Claims (chronological)</button><button class="tab" data-tab="comments">Comments <span id="cov-cc"></span></button></div>
  <div class="pane" id="cov-claims"></div>
  <div class="pane" id="cov-comments" style="display:none"></div>
</div>
<button id="cov-qbtn">&#65291; Comment</button>
<div id="cov-pop">
  <div style="font-weight:700;font-size:12px">New comment</div>
  <div class="q" style="font-family:ui-monospace,Menlo,monospace;font-size:11px;background:#FAFAF7;border-radius:5px;padding:4px 6px;max-height:80px;overflow:auto" id="cov-pop-q"></div>
  <select id="cov-pop-type"><option value="gap">&#9888; Gap &mdash; not covered by any claim</option><option value="note">Note</option><option value="covered">&#10003; Confirm covered</option></select>
  <select id="cov-pop-claim"></select>
  <textarea id="cov-pop-note" rows="2" placeholder="Note..."></textarea>
  <div class="r"><button class="cancel" id="cov-pop-cancel">Cancel</button><button class="add" id="cov-pop-add">Add</button></div>
</div>
<script>
__EMBED__
(function(){
var LS="__LS_KEY__"; var C={}; try{C=JSON.parse(localStorage.getItem(LS)||"{}")}catch(e){}; if(!C.comments)C.comments=[];
var ROOT=document.querySelector('article.essay')||document.querySelector('.main')||document.body;
var supportsHL=(typeof Highlight!=="undefined"&&CSS&&CSS.highlights);
var nodes=[],starts=[],FULL="";
(function walk(n){for(var c=n.firstChild;c;c=c.nextSibling){if(c.nodeType===3){starts.push(FULL.length);nodes.push(c);FULL+=c.nodeValue;}else if(c.nodeType===1){var tg=c.tagName;if(tg==='SCRIPT'||tg==='STYLE')continue;walk(c);}}})(ROOT);
var nodeIdx=new Map();nodes.forEach(function(n,i){nodeIdx.set(n,i);});
function locate(off){var lo=0,hi=nodes.length-1,ans=0;while(lo<=hi){var m=(lo+hi)>>1;if(starts[m]<=off){ans=m;lo=m+1;}else hi=m-1;}return [nodes[ans],off-starts[ans]];}
function rangeFor(s,e){var a=locate(s),b=locate(e);var r=document.createRange();try{r.setStart(a[0],Math.min(a[1],a[0].nodeValue.length));r.setEnd(b[0],Math.min(b[1],b[0].nodeValue.length));}catch(err){return null;}return r;}
function norm(s){return s.replace(/\s+/g," ").trim();}
var NFULL=FULL.replace(/\s+/g," ");
var rawOf=[];(function(){var j=0,prevSpace=false;for(var k=0;k<FULL.length;k++){var ch=FULL[k];if(/\s/.test(ch)){if(!prevSpace){rawOf[j]=k;j++;prevSpace=true;}}else{rawOf[j]=k;j++;prevSpace=false;}}rawOf[j]=FULL.length;})();
function findRaw(anchor){if(!anchor)return -1;var p=FULL.indexOf(anchor);if(p>=0)return [p,p+anchor.length];var na=norm(anchor);if(!na)return -1;var q=NFULL.indexOf(na);if(q<0)return -1;var s=rawOf[q],e=rawOf[Math.min(q+na.length,rawOf.length-1)];return (s!=null&&e!=null&&e>s)?[s,e]:-1;}
CDATA.claims.forEach(function(c){var r=c.located?findRaw(c.anchor):-1;if(r&&r!==-1){c._s=r[0];c._e=r[1];}else{c._s=-1;c._e=-1;c.located=false;}});
var covHL,cmtHL,actHL;
function paintCov(){if(!supportsHL)return;covHL=new Highlight();CDATA.claims.forEach(function(c){if(c._s>=0){var r=rangeFor(c._s,c._e);if(r)covHL.add(r);}});CSS.highlights.set('cov',covHL);}
function paintCmt(){if(!supportsHL)return;cmtHL=new Highlight();C.comments.forEach(function(m){if(m.s>=0){var r=rangeFor(m.s,m.e);if(r)cmtHL.add(r);}});CSS.highlights.set('cmt',cmtHL);}
function flash(s,e){if(!supportsHL)return;actHL=new Highlight();var r=rangeFor(s,e);if(r)actHL.add(r);CSS.highlights.set('act',actHL);setTimeout(function(){CSS.highlights.delete('act');},1600);}
function scrollTo(s,e){var r=rangeFor(s,e);if(!r)return;var el=r.startContainer.parentElement;if(el)el.scrollIntoView({block:'center',behavior:'smooth'});flash(s,e);}
paintCov();paintCmt();
function esc(s){return (s||"").replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function save(){try{localStorage.setItem(LS,JSON.stringify(C))}catch(e){}}
function renderClaims(){
  var loc=CDATA.claims.filter(function(c){return c.located}).length;
  document.getElementById('cov-counter').textContent=CDATA.claims.length+" claims · "+loc+" located · "+(CDATA.claims.length-loc)+" not located";
  document.getElementById('cov-claims').innerHTML=CDATA.claims.map(function(c,i){
    return '<div class="cclaim" data-i="'+i+'"><div class="top"><span class="lvl l'+c.level+'">L'+c.level+'</span><b>'+c.id+'</b><span>· '+esc(c.section)+'</span>'
      +(c.located?'<span class="bdg b-ok">in report</span>':'<span class="bdg b-no">not located</span>')+'</div><div class="t">'+esc(c.claim)+'</div></div>';}).join('');
  [].forEach.call(document.querySelectorAll('.cclaim'),function(el){el.onclick=function(){var c=CDATA.claims[+el.dataset.i];if(c._s>=0)scrollTo(c._s,c._e);};});
}
document.getElementById('cov-pop-claim').innerHTML='<option value="">(optional) link a claim...</option>'+CDATA.claims.map(function(c){return '<option value="'+c.id+'">'+c.id+' — '+esc(c.claim.slice(0,46))+'</option>';}).join('');
function renderComments(){
  document.getElementById('cov-cc').textContent="("+C.comments.length+")";
  document.getElementById('cov-comments').innerHTML=C.comments.map(function(m,i){return '<div class="cmt '+m.type+'"><span class="x" data-del="'+i+'">✕</span><b>'+(m.type==='gap'?'⚠ GAP':m.type==='covered'?'✓ COVERED':'NOTE')+'</b>'+(m.claim?' · '+m.claim:'')+'<div class="q" data-jump="'+i+'" style="cursor:pointer">'+esc(m.quote.slice(0,220))+'</div>'+(m.note?'<div>'+esc(m.note)+'</div>':'')+'</div>';}).join('')||'<div style="color:#999">Select text in the report, then click the Comment button.</div>';
  [].forEach.call(document.querySelectorAll('[data-del]'),function(x){x.onclick=function(){C.comments.splice(+x.dataset.del,1);save();paintCmt();renderComments();};});
  [].forEach.call(document.querySelectorAll('[data-jump]'),function(x){x.onclick=function(){var m=C.comments[+x.dataset.jump];if(m.s>=0)scrollTo(m.s,m.e);};});
}
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
qbtn.onclick=function(){if(!SEL)return;document.getElementById('cov-pop-q').textContent=SEL.quote.slice(0,400);document.getElementById('cov-pop-type').value='gap';document.getElementById('cov-pop-claim').value='';document.getElementById('cov-pop-note').value='';pop.style.left=qbtn.style.left;pop.style.top=qbtn.style.top;pop.style.display='block';qbtn.style.display='none';document.getElementById('cov-pop-note').focus();};
document.getElementById('cov-pop-cancel').onclick=function(){pop.style.display='none';};
document.getElementById('cov-pop-add').onclick=function(){if(!SEL)return;C.comments.push({s:SEL.s,e:SEL.e,quote:SEL.quote,type:document.getElementById('cov-pop-type').value,claim:document.getElementById('cov-pop-claim').value||null,note:document.getElementById('cov-pop-note').value||"",ts:new Date().toISOString()});save();paintCmt();renderComments();pop.style.display='none';document.querySelector('#cov-side .tab[data-tab=comments]').click();};
document.addEventListener('mousedown',function(e){if(!pop.contains(e.target)&&e.target!==qbtn)pop.style.display='none';});
function exportObj(){return {saved_at:new Date().toISOString(),reviewer:"__REVIEWER__",report:"human collusion.wiki report",n_claims:CDATA.claims.length,located:CDATA.claims.filter(function(c){return c.located}).length,unlocated_claims:CDATA.claims.filter(function(c){return !c.located}).map(function(c){return c.id}),comments:C.comments};}
document.getElementById('cov-save').onclick=function(){var b=new Blob([JSON.stringify(exportObj(),null,1)],{type:"application/json"});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download="__DOWNLOAD__";a.click();};
document.getElementById('cov-copy').onclick=function(){navigator.clipboard&&navigator.clipboard.writeText(JSON.stringify(exportObj(),null,1));this.textContent="Copied";var t=this;setTimeout(function(){t.textContent="Copy JSON"},1200);};
renderClaims();renderComments();
})();
</script>
'''
INJECT_HTML = INJECT_HTML.replace("__EMBED__", embed)
html = html.replace("</head>", INJECT_CSS + "</head>", 1)

def write_review(name, title, ls_key, reviewer, download):
    inject = (INJECT_HTML
        .replace("__TITLE__", title)
        .replace("__LS_KEY__", ls_key)
        .replace("__REVIEWER__", reviewer)
        .replace("__DOWNLOAD__", download))
    out = html.replace("</body>", inject + "</body>", 1)
    (HERE / name).write_text(out)
    print(f"wrote {name} bytes:", len(out))

write_review("coverage.html", "Rubric Coverage", "coverage_site_v1", "hasan", "coverage_review.json")
write_review("coverage_hamzah.html", "Rubric Coverage (Hamzah)", "coverage_site_hamzah_v1", "hamzah", "coverage_review_hamzah.json")
print("remaining stylesheet links:", len(re.findall(r'<link rel="stylesheet"', html)))
print("</script> count (site has figure scripts too):", html.count("</script>"))
