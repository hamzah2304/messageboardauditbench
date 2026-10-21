/* Edits per day by wiki, log scale. Counts come from the distinct-agent analysis
   export (see its charts/METHODOLOGY.md), farm wikis from changelog revisions and
   off-farm venues from recorded edits. Off-farm venues log only the editor's IP,
   so those are exact edit counts but not agent counts. */
(function(){
  'use strict';
  var DATA = {"start":"2026-05-11","n":55,"farm":{"dse":[[13,42],[15,615],[16,58],[17,234],[18,129],[19,53],[20,20],[21,144],[22,3],[24,6],[25,5],[26,8],[27,13],[28,18],[29,2],[31,188],[36,3204],[37,1681],[38,7059],[39,608],[40,823],[41,881],[42,1007],[51,1],[52,9]],"probier":[[13,7],[15,11],[16,1],[18,5],[20,4],[21,22],[26,4],[29,4],[30,4],[36,31],[37,13],[38,648],[39,21],[40,31],[41,13],[42,191],[51,4],[52,5]],"fractal":[[13,25],[15,67],[26,2],[27,2],[36,16],[37,68],[38,42],[39,13],[40,2],[41,44],[42,260],[51,7]],"demo":[[36,2],[42,1]],"gruender":[[42,1]]},"usemod":[[0,3],[7,1],[13,2],[15,4],[16,4],[36,2]],"texteditors":[[6,8],[16,2],[38,1],[42,12]],"publictestwiki":[[0,14],[1,10],[2,14],[3,7],[5,3],[6,11],[7,12],[8,5],[10,1],[13,2],[14,4],[15,2],[16,7],[38,4]],"uncyclopedia":[[6,4],[7,13],[16,4]]};
  var NS='http://www.w3.org/2000/svg';
  function el(n,a){var e=document.createElementNS(NS,n);for(var k in a)e.setAttribute(k,a[k]);return e;}
  function hel(n,cls,txt){var e=document.createElement(n);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;}
  // plain marker, hollow marker, cross; the legend swatches read the same three.
  // The cross runs larger because an X reads smaller than a disc of equal radius.
  var R=1.2, RH=1.8, RX=3.6;
  function crossPt(cx,cy,r){
    return el('path',{'class':'pt cross',d:'M'+(cx-r)+' '+(cy-r)+'L'+(cx+r)+' '+(cy+r)+
                                          'M'+(cx-r)+' '+(cy+r)+'L'+(cx+r)+' '+(cy-r)});
  }
  // Perpendicular, not vertical: a segment can climb three decades in one day,
  // and beside such a line the vertical gap is enormous.
  function segDist(px,py,ax,ay,bx,by){
    var dx=bx-ax, dy=by-ay, L=dx*dx+dy*dy;
    var t=L ? Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/L)) : 0;
    return Math.hypot(px-(ax+t*dx), py-(ay+t*dy));
  }
  var MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function dateOf(d){var t=new Date(Date.UTC(2026,4,11)+d*86400000);return t;}
  function fmt(d){var t=dateOf(d);return t.getUTCDate()+' '+MONTHS[t.getUTCMonth()];}

  /* Colour is not here — figures.css sets --c per series class. */
  var SERIES=[
    {key:'dse',      label:'dse',              group:'farm', pts:DATA.farm.dse,      cls:'s-dse'},
    {key:'probier',  label:'probier',          group:'farm', pts:DATA.farm.probier,  cls:'s-probier',  dash:'5 3'},
    {key:'fractal',  label:'fractal',          group:'farm', pts:DATA.farm.fractal,  cls:'s-fractal',  dash:'1.5 3'},
    {key:'demo',     label:'demo',             group:'farm', pts:DATA.farm.demo,     cls:'s-demo',     dash:'7 3 2 3'},
    {key:'gruender', label:'gruender',         group:'farm', pts:DATA.farm.gruender, cls:'s-gruender', mark:'cross'},
    {key:'usemod',   label:'usemod.org',       group:'usemod', pts:DATA.usemod,      cls:'s-usemod'},
    {key:'texteditors', label:'texteditors.org', group:'usemod', pts:DATA.texteditors, cls:'s-texteditors', dash:'3 2', hollow:true},
    {key:'publictestwiki', label:'publictestwiki.com', group:'mw', pts:DATA.publictestwiki, cls:'s-publictestwiki', hollow:true},
    {key:'uncyclopedia',   label:'en.uncyclopedia.co', group:'mw', pts:DATA.uncyclopedia,   cls:'s-uncyclopedia',   dash:'3 2', hollow:true}
  ];
  // day -> edits, plus the span; used by both the line geometry and the hit test
  SERIES.forEach(function(s){
    s.have={}; s.pts.forEach(function(p){ s.have[p[0]]=p[1]; });
    s.dFirst=s.pts[0][0]; s.dLast=s.pts[s.pts.length-1][0];
  });

  function mount(container){
    if(container.getAttribute('data-mounted')) return;
    container.setAttribute('data-mounted','1');
    container.classList.add('fig-wikis');
    var cap=container.querySelector('figcaption');

    // cls is a series class, null clears. draw() re-applies it: a redraw
    // replaces the groups this marked.
    var kitems=[], focused=null;
    function focus(cls){
      focused=cls;
      if(cls) container.setAttribute('data-focus',cls); else container.removeAttribute('data-focus');
      kitems.forEach(function(it){ it.classList.toggle('on', it.getAttribute('data-series')===cls); });
      if(svg) Array.prototype.forEach.call(svg.querySelectorAll('g.series'),function(g){
        g.classList.toggle('on', !!cls && g.classList.contains(cls));
      });
    }

    var head=hel('div','head');
    var key=hel('div','key');
    // one swatch per series, drawn with the same styles as the plot
    function swatch(cls, kind, dash){
      var sv=el('svg',{viewBox:'0 0 34 12',width:34,height:12,'class':'sw series '+cls,'aria-hidden':'true'});
      if(kind==='line'){
        var ln=el('line',{x1:1,x2:33,y1:6,y2:6,'class':'ln'}); if(dash) ln.setAttribute('stroke-dasharray',dash); sv.appendChild(ln);
        sv.appendChild(el('circle',{cx:17,cy:6,r:R,'class':'pt'}));
      } else if(kind==='cross'){
        sv.appendChild(crossPt(17,6,RX));
      } else {
        sv.appendChild(el('circle',{cx:17,cy:6,r:RH,'class':'pt hollow'}));
      }
      return sv;
    }
    var groups=[
      ['ProWiki farm (GET-writable)',[
        ['dse','s-dse','line',null],['probier','s-probier','line','5 3'],['fractal','s-fractal','line','1.5 3'],['demo','s-demo','line','7 3 2 3'],['gruender','s-gruender','cross']]],
      ['UseModWiki (GET-writable)',[
        ['usemod.org','s-usemod','line',null],['texteditors.org','s-texteditors','line','3 2']]],
      ['MediaWiki (POST-only)',[
        ['publictestwiki.com','s-publictestwiki','line',null],['en.uncyclopedia.co','s-uncyclopedia','line','3 2']]]
    ];
    groups.forEach(function(g){
      var box=hel('div','kgroup');
      box.appendChild(hel('span','ktitle',g[0]));
      g[1].forEach(function(e){
        var it=hel('span','kitem'); it.appendChild(swatch(e[1],e[2],e[3])); it.appendChild(document.createTextNode(e[0]));
        it.setAttribute('data-series',e[1]);
        it.addEventListener('mouseenter',function(){focus(e[1]);});
        it.addEventListener('mouseleave',function(){focus(null);});
        kitems.push(it); box.appendChild(it);
      });
      key.appendChild(box);
    });
    head.appendChild(key);

    var plot=hel('div','plot');
    // The viewBox is sized in CSS pixels (as wide as the plot, capped at 1000) so
    // type stays 10px at every width. Under 600px: taller, tighter margins, a
    // horizontal axis title and fortnightly ticks.
    // ZB reserves room under the "1" gridline for the zeroes; without it a zero
    // would plot on top of a 1.
    var mobile=false,W=1000,H=330,M,iw,ih,ZB;
    function size(){
      var cw=plot.clientWidth||container.clientWidth||1000;
      mobile=cw<600;
      W=cw>=1000?1000:Math.max(cw,280);
      H=mobile?Math.round(Math.min(250,Math.max(190,W*0.66))):Math.round(W*0.4125); // 0.33 x 1.25
      M=mobile?{l:40,r:10,t:24,b:24}:{l:56,r:14,t:12,b:26};
      iw=W-M.l-M.r; ih=H-M.t-M.b; ZB=mobile?12:16;
      svg.setAttribute('viewBox','0 0 '+W+' '+H);
      container.classList.toggle('m',mobile);
    }
    var d0=-1, d1=DATA.n; // May 10 .. Jul 4
    var maxV=10000;
    var x=function(d){return M.l+(d-d0)/(d1-d0)*iw;};
    var y=function(v){return v>0 ? M.t+ih-ZB-(Math.log10(v)/Math.log10(maxV))*(ih-ZB) : M.t+ih-1;};
    var svg=el('svg',{viewBox:'0 0 '+W+' '+H,role:'img','aria-label':'Edits per day by wiki, 10 May to 4 July 2026, logarithmic scale. The ProWiki farm wikis (dse, probier, fractal) carry almost all edits from 24 May on, peaking at 7,059 dse edits on 18 June; the UseModWiki and MediaWiki sites never exceed fifteen edits a day.'});
    var tip=hel('div','tip');

    function draw(){
    size();
    svg.textContent='';
    [1,10,100,1000,10000].forEach(function(v){
      var yy=y(v);
      svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:yy,y2:yy,'class':'hair'}));
      var t=el('text',{x:M.l-7,y:yy+3.2,'class':'ax','text-anchor':'end'});t.textContent=v.toLocaleString();svg.appendChild(t);
    });
    // x ticks: every 7 days from May 11, plus 1 Jul (every 14 on a phone).
    var ticks=mobile?[0,14,28,42]:[0,7,14,21,28,35,42,49];
    ticks.forEach(function(d){
      var xx=x(d);
      var t=el('text',{x:xx,y:M.t+ih+15,'class':'ax','text-anchor':'middle'});t.textContent=fmt(d);svg.appendChild(t);
    });
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:M.t+ih,y2:M.t+ih,'class':'base'}));
    var yl=mobile
      ? el('text',{'class':'axlabel','text-anchor':'start',x:M.l,y:12})
      : el('text',{'class':'axlabel','text-anchor':'middle',transform:'rotate(-90 '+(M.l-42)+' '+(M.t+ih/2)+')',x:M.l-42,y:M.t+ih/2});
    yl.textContent='Edits per day (log)';svg.appendChild(yl);

    // series
    SERIES.forEach(function(s){
      var g=el('g',{'class':'series '+s.cls});
      // Days inside the span with no edits are real zeroes and belong on the
      // floor. Markers stay on real rows, so a flat run reads as nothing.
      if(s.pts.length>1){
        var pts=[];
        for(var d=s.dFirst; d<=s.dLast; d++) pts.push(x(d)+','+y(s.have[d]||0));
        g.appendChild(el('polyline',{points:pts.join(' '),'class':'ln','stroke-dasharray':s.dash||'none'}));
      }
      s.pts.forEach(function(p){
        g.appendChild(s.mark==='cross'
          ? crossPt(x(p[0]),y(p[1]),RX)
          : el('circle',{cx:x(p[0]),cy:y(p[1]),r:s.hollow?RH:R,'class':'pt'+(s.hollow?' hollow':'')}));
      });
      svg.appendChild(g);
    });

    // hover bands
    var byDay={};
    SERIES.forEach(function(s){ s.pts.forEach(function(p){ (byDay[p[0]]=byDay[p[0]]||[]).push([s.label,p[1],s.cls]); }); });
    var bw=iw/(d1-d0);
    for(var d=d0; d<d1; d++){
      (function(d){
        var b=el('rect',{x:x(d)-bw/2,y:M.t,width:bw,height:ih,'class':'band'});
        b.addEventListener('mousemove',function(ev){
          // The bands cover the series, so a line never gets its own mouseover;
          // measure to the segments instead. Cursor is px, the plot is viewBox.
          var sr=svg.getBoundingClientRect(), sc=sr.width/W;
          var vx=(ev.clientX-sr.left)/sc, vy=(ev.clientY-sr.top)/sc;
          var best=null, bd=1e9;
          SERIES.forEach(function(s){
            var dd=1e9;
            // the segments this column can reach, clipped to the series' span
            for(var a=d-1; a<=d+1; a++){
              if(a<s.dFirst||a+1>s.dLast) continue;
              dd=Math.min(dd,segDist(vx,vy,x(a),y(s.have[a]||0),x(a+1),y(s.have[a+1]||0)));
            }
            // a one-point series (gruender) has no segment; measure to the marker
            if(s.dFirst===s.dLast&&Math.abs(d-s.dFirst)<=1)
              dd=Math.min(dd,Math.hypot(vx-x(s.dFirst),vy-y(s.have[s.dFirst]||0)));
            if(dd<bd){bd=dd;best=s;}
          });
          focus(best&&bd<=8?best.cls:null);

          var rows=byDay[d];
          if(!rows){tip.style.opacity=0;return;}
          var html='<div class="d">'+fmt(d)+'</div>';
          rows.sort(function(a,b){return b[1]-a[1];}).forEach(function(r){
            html+='<div class="r '+r[2]+'"><span>'+r[0]+'</span>'+r[1].toLocaleString()+'</div>';
          });
          tip.innerHTML=html;
          var pr=plot.getBoundingClientRect();
          var l=ev.clientX-pr.left+13; if(l>pr.width-190) l=ev.clientX-pr.left-190;
          tip.style.left=Math.max(0,l)+'px'; tip.style.top=Math.max(0,ev.clientY-pr.top-8)+'px'; tip.style.opacity=1;
        });
        b.addEventListener('mouseleave',function(){tip.style.opacity=0;});
        svg.appendChild(b);
      })(d);
    }
    if(focused) focus(focused); // the groups above are new; restore the hover state
    }

    // Per plot, not per band — band-to-band would fire mouseleave and flicker.
    plot.addEventListener('mouseleave',function(){ focus(null); tip.style.opacity=0; });
    plot.appendChild(svg); plot.appendChild(tip);
    if(cap){ container.insertBefore(head,cap); container.insertBefore(plot,cap); }
    else { container.appendChild(head); container.appendChild(plot); }
    draw();

    // redraw whenever the plot's width changes (the viewBox follows it)
    var lastW=plot.clientWidth;
    function onResize(){ var w=plot.clientWidth; if(w===lastW) return; lastW=w; draw(); }
    if(window.ResizeObserver){ new ResizeObserver(onResize).observe(plot); }
    else window.addEventListener('resize',onResize);
    return {container:container};
  }

  window.Figures=window.Figures||{};
  window.Figures.wikis=mount;
  function auto(){ Array.prototype.forEach.call(document.querySelectorAll('[data-figure="wikis"]'),function(c){ if(!c.getAttribute('data-mounted')) mount(c); }); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',auto); else auto();
})();
