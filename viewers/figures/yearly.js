/* Figure: "Yearly edits to the dse wiki, 2001–2026"
   Page revisions per year on a log scale, with hover tooltips.

   Usage:  <figure data-figure="yearly"></figure>   (auto-mounts on DOMContentLoaded)
       or  window.Figures.yearly(containerElement)
   Styles live in figures.css under .fig-yearly. */
(function(){
"use strict";
var NAME = "yearly";

/* Page revisions per year in the dse wiki, counted from every revision in the
   5,450 RCS histories of the page dump (site/content/extract.py), dated by the
   wiki's own save timestamp (TS) and falling back to the RCS check-in date.
   Recounted 2026-09-02; an earlier version of this figure undercounted the
   pre-2026 years by roughly 30x. */
var YEARS = [
  {y:2001,n:1697},
  {y:2002,n:3769},
  {y:2003,n:2410},
  {y:2004,n:1391},
  {y:2005,n:549},
  {y:2006,n:286},
  {y:2007,n:107},
  {y:2008,n:33},
  {y:2009,n:46},
  {y:2010,n:20},
  {y:2011,n:24},
  {y:2012,n:67},
  {y:2013,n:9},
  {y:2014,n:3},
  {y:2015,n:2},
  {y:2016,n:15},
  {y:2017,n:1},
  {y:2018,n:6},
  {y:2019,n:0},
  {y:2020,n:1},
  {y:2021,n:1},
  {y:2022,n:2},
  {y:2023,n:0},
  {y:2024,n:0},
  {y:2025,n:0},
  {y:2026,n:12894}
];

var ARIA = "Page revisions per year in the dse wiki, 2001 to 2026, on one logarithmic scale. The wiki records 1,697 revisions in 2001, peaks at 3,769 in 2002, declines through the 2000s to a few dozen a year by 2008, and to single digits from 2013 to 2023, with no revisions at all in 2019, 2023, 2024 and 2025. In 2026 it records 12,894, more than the 10,439 of the previous twenty-five years combined. Years with no revisions have no bar.";

var NS = "http://www.w3.org/2000/svg";
function el(n,a){ var e=document.createElementNS(NS,n);
  if(a) for(var k in a) e.setAttribute(k,a[k]); return e; }

function mount(container){
  if(!container || container.dataset.mounted==="1") return container && container._figure;
  container.dataset.mounted = "1";
  container.classList.add("fig-"+NAME);

  // ── DOM ────────────────────────────────────────────────────────────────
  var plot = document.createElement("div"); plot.className = "plot";
  var svg = el("svg",{viewBox:"0 0 1000 300",role:"img","aria-label":ARIA});
  var tip = document.createElement("div"); tip.className = "tip";
  plot.appendChild(svg); plot.appendChild(tip);
  // keep any host-supplied <figcaption> after the chart
  var cap = container.querySelector(":scope > figcaption");
  if(cap) container.insertBefore(plot, cap); else container.appendChild(plot);

  // ── geometry ───────────────────────────────────────────────────────────
  // The SVG's coordinate space is sized in CSS pixels: the viewBox is as wide
  // as the plot (capped at 1000), so type stays 10px at every width instead of
  // shrinking with the column. Under 600px the chart is taller, the margins
  // tighter and the axis title runs horizontally above the axis.
  var N = YEARS.length;
  var mobile=false, W=1000, H=300, M, iw, ih, bw, gap;
  function size(){
    var cw = plot.clientWidth || container.clientWidth || 1000;
    mobile = cw < 600;
    W = cw >= 1000 ? 1000 : Math.max(cw, 280);
    H = mobile ? Math.round(Math.min(230, Math.max(170, W*0.6))) : Math.round(W*0.3);
    M = mobile ? {l:44, r:10, t:24, b:24} : {l:66, r:20, t:14, b:26};
    iw=W-M.l-M.r; ih=H-M.t-M.b;
    bw = iw/N; gap = Math.min(4, bw*0.18);
    svg.setAttribute("viewBox","0 0 "+W+" "+H);
    container.classList.toggle("m", mobile);
  }
  // Log axis: 141× between the busiest human year and 2026 flattens every early
  // year to nothing on a linear scale. Decades from 1, with the domain carried
  // past 10,000 so the 2026 bar clears its own gridline. Years with no revisions
  // draw no bar — zero has no place on a log axis, and the gaps say it plainly.
  var maxY = 20000;
  var L = Math.log10(maxY);
  var yOf = function(v){ return M.t+ih - (Math.log10(v)/L)*ih; };
  var xOf = function(i){ return M.l + (i+0.5)*bw; };

  function drawChart(){
    size();
    svg.textContent="";

    [1,10,100,1000,10000].forEach(function(v){
      var y = yOf(v);
      svg.appendChild(el("line",{x1:M.l,x2:W-M.r,y1:y,y2:y,"class":"hair"}));
      var t = el("text",{x:M.l-7,y:y+3.2,"class":"ax","text-anchor":"end"});
      t.textContent = v.toLocaleString(); svg.appendChild(t);
    });

    YEARS.forEach(function(r,i){
      if(!r.n) return;
      var h = Math.max(M.t+ih-yOf(r.n), 1);
      svg.appendChild(el("rect",{x:M.l+i*bw+gap/2, y:M.t+ih-h,
        width:Math.max(bw-gap,1), height:h, fill:"var(--vivid-foreground)"}));
    });

    svg.appendChild(el("line",{x1:M.l,x2:W-M.r,y1:M.t+ih,y2:M.t+ih,"class":"base"}));

    var yl = mobile
      ? el("text",{"class":"axlabel","text-anchor":"start", x:M.l, y:12})
      : el("text",{"class":"axlabel","text-anchor":"middle",
          transform:"rotate(-90 "+(M.l-46)+" "+(M.t+ih/2)+")", x:M.l-46, y:M.t+ih/2});
    yl.textContent = "Page revisions per year"; svg.appendChild(yl);

    YEARS.forEach(function(r,i){
      // every fifth year, plus the two ends; 2025 would collide with 2026
      if(r.y === 2025) return;
      if(r.y % 5 && r.y !== 2001 && r.y !== 2026) return;
      var t = el("text",{x:xOf(i), y:M.t+ih+15, "class":"ax","text-anchor":"middle"});
      t.textContent = r.y; svg.appendChild(t);
    });

    YEARS.forEach(function(r,i){
      var b = el("rect",{x:M.l+i*bw, y:M.t, width:bw, height:ih, "class":"band"});
      b.addEventListener("mousemove",function(e){ showTip(e,r); });
      b.addEventListener("mouseleave",function(){ tip.style.opacity=0; });
      svg.appendChild(b);
    });
  }

  function showTip(ev,r){
    tip.innerHTML = '<div class="d">'+r.y+'</div>'+
      '<div class="r"><span>Revisions</span>'+r.n.toLocaleString()+'</div>';
    var pr = plot.getBoundingClientRect();
    var l = ev.clientX-pr.left+13;
    if(l > pr.width-150) l = ev.clientX-pr.left-150;
    tip.style.left = Math.max(0,l)+"px";
    tip.style.top = Math.max(0, ev.clientY-pr.top-8)+"px";
    tip.style.opacity = 1;
  }

  drawChart();

  // Redraw whenever the plot's width changes (the viewBox follows it).
  var lastW = plot.clientWidth, ro = null;
  function onResize(){
    var w = plot.clientWidth;
    if(w===lastW) return; lastW = w; drawChart();
  }
  if(window.ResizeObserver){ ro = new ResizeObserver(onResize); ro.observe(plot); }
  else window.addEventListener("resize", onResize);

  var api = {
    container: container,
    destroy: function(){
      if(ro) ro.disconnect(); else window.removeEventListener("resize", onResize);
      if(plot.parentNode) plot.parentNode.removeChild(plot);
      container.classList.remove("fig-"+NAME);
      delete container.dataset.mounted; delete container._figure;
    }
  };
  container._figure = api;
  return api;
}

window.Figures = window.Figures || {};
window.Figures[NAME] = mount;

function auto(){
  var nodes = document.querySelectorAll('[data-figure="'+NAME+'"]');
  for(var i=0;i<nodes.length;i++) if(nodes[i].dataset.mounted!=="1") mount(nodes[i]);
}
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", auto);
else auto();
})();
