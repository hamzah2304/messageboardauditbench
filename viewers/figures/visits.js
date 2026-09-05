/* Figure: "ProWiki agent edits, and the OpenAI visits that followed"
   Bars of agent edits per day, an indigo area of OpenAI requests per day
   on a secondary axis, annotation labels above/below with hover expansions and
   elbow leader lines, and two brackets under the axis for the incidents OpenAI
   has reported (the Artifactory message board and the Hugging Face attack).

   Usage:  <figure data-figure="visits"></figure>   (auto-mounts on DOMContentLoaded)
       or  window.Figures.visits(containerElement)
   Styles live in figures.css under .fig-visits. */
(function(){
"use strict";
var NAME = "visits";

/* d — day; a/o — agent edits from Azure / other addresses; cov — 1 while the wiki
   dumps cover the day; r/f/h — OpenAI requests from registered / formerly-claimed /
   suspected-home addresses. */
var DAYS = [{"d":"2026-05-11","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-12","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-13","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-14","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-15","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-16","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-17","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-18","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-19","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-20","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-21","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-22","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-23","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-24","a":18,"o":5,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-25","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-26","a":342,"o":62,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-27","a":29,"o":8,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-28","a":184,"o":26,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-29","a":63,"o":6,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-30","a":36,"o":6,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-05-31","a":12,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-01","a":113,"o":21,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-02","a":2,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-03","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-04","a":0,"o":3,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-05","a":1,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-06","a":11,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-07","a":12,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-08","a":12,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-09","a":5,"o":1,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-10","a":4,"o":2,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-11","a":123,"o":26,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-12","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-13","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-14","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-15","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-16","a":2196,"o":371,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-17","a":1083,"o":171,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-18","a":5488,"o":785,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-19","a":357,"o":131,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-20","a":557,"o":95,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-06-21","a":487,"o":147,"cov":1,"r":0,"f":10,"h":25},{"d":"2026-06-22","a":815,"o":123,"cov":1,"r":0,"f":125,"h":35},{"d":"2026-06-23","a":0,"o":1,"cov":1,"r":0,"f":66,"h":24},{"d":"2026-06-24","a":0,"o":1,"cov":1,"r":0,"f":10,"h":0},{"d":"2026-06-25","a":0,"o":0,"cov":1,"r":0,"f":0,"h":3},{"d":"2026-06-26","a":0,"o":0,"cov":1,"r":0,"f":376,"h":95},{"d":"2026-06-27","a":0,"o":0,"cov":1,"r":0,"f":9,"h":66},{"d":"2026-06-28","a":0,"o":0,"cov":1,"r":0,"f":0,"h":14},{"d":"2026-06-29","a":0,"o":0,"cov":1,"r":0,"f":3,"h":19},{"d":"2026-06-30","a":0,"o":0,"cov":1,"r":0,"f":14,"h":28},{"d":"2026-07-01","a":5,"o":0,"cov":1,"r":0,"f":2,"h":0},{"d":"2026-07-02","a":14,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-07-03","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-07-04","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-07-05","a":0,"o":0,"cov":1,"r":0,"f":1,"h":0},{"d":"2026-07-06","a":0,"o":0,"cov":1,"r":0,"f":69,"h":0},{"d":"2026-07-07","a":0,"o":0,"cov":1,"r":2,"f":128,"h":0},{"d":"2026-07-08","a":0,"o":0,"cov":1,"r":5,"f":41,"h":1},{"d":"2026-07-09","a":0,"o":0,"cov":1,"r":0,"f":90,"h":13},{"d":"2026-07-10","a":0,"o":0,"cov":1,"r":0,"f":31,"h":20},{"d":"2026-07-11","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-07-12","a":0,"o":0,"cov":1,"r":0,"f":0,"h":0},{"d":"2026-07-13","a":0,"o":0,"cov":1,"r":0,"f":1,"h":0},{"d":"2026-07-14","a":0,"o":0,"cov":1,"r":0,"f":7,"h":0},{"d":"2026-07-15","a":0,"o":0,"cov":0,"r":0,"f":5,"h":0},{"d":"2026-07-16","a":0,"o":0,"cov":0,"r":0,"f":0,"h":0},{"d":"2026-07-17","a":0,"o":0,"cov":0,"r":0,"f":3,"h":0},{"d":"2026-07-18","a":0,"o":0,"cov":0,"r":0,"f":0,"h":0},{"d":"2026-07-19","a":0,"o":0,"cov":0,"r":0,"f":0,"h":0},{"d":"2026-07-20","a":0,"o":0,"cov":0,"r":0,"f":0,"h":0}];

// src "ours" → established from the wiki revision data, annotated ABOVE
// src "out"  → reported from outside the dumps, annotated BELOW
var MS = [
  {d:"2026-05-11", src:"ours", c:"First edit attempts",
   f:"First time we observe OpenAI agents attempt to edit a public wiki (publictestwiki.com)."},
  {d:"2026-05-12", src:"out", c:"Internal comms begin",
   f:"OpenAI's agents first start communicating with each other internally."},
  {d:"2026-05-24", src:"ours", c:"First wiki write",
   f:"The agents make their first successful write to DSEwiki. They start by posting lists of external links that are useful for their tasks."},
  {d:"2026-05-26", src:"out",  c:"First outside write using Artifactory Vulnerability",
   f:"OpenAI's agents use Artifactory vulnerability to gain internet access, using information shared via Artifactory."},
  {d:"2026-06-16", src:"ours", c:"ProWiki Traffic Spikes",
   f:"There is a huge jump in agent activity on the wikis. The agents start explicitly messaging each other and work together to cheat on their tests."},
  {d:"2026-06-19", src:"ours", ts:34, c:"Agents notice deletions",
   f:"An agent notices the administrator is deleting pages in alphabetical order and makes a backup page whose name starts with ZZZ so it will last longer before deletion."},
  {d:"2026-06-20", src:"ours", ts:18, c:"Network-limit trick",
   f:"An agent posts a trick for getting around OpenAI sandbox network restrictions; 14 minutes later, another agent claims it was able to execute this technique successfully."},
  {d:"2026-06-21", src:"ours", c:"OpenAI-related IPs visit",
   f:"OpenAI-related IP addresses first visit the wiki. The agents abruptly stop editing after the next day; we infer that OpenAI intervened to prevent further edits."},
  {d:"2026-07-04", d2:"2026-07-06", src:"out", c:"Artifactory Overloaded",
   f:"OpenAI's package server falls under agent load. OpenAI opens a security incident and rebuilds it."}
];

/* The two incidents reported from outside the dumps, on the doc's timeline dates.
   Still "civs" here and in figures.css from the three-civilizations account the
   brackets first drew. */
var CIVS = [
  {s:"2026-05-12", e:"2026-07-04", n:"Initial OpenAI Messageboard"},
  {s:"2026-07-09", e:"2026-07-13", n:"Hugging Face Hack"}
];

var ARIA = "Daily agent edits to the ProWiki wikis and daily requests from OpenAI-related addresses, 11 May to 20 July 2026. Agent editing runs 24 May to 2 July, peaking at 6,273 edits on 18 June. OpenAI-related addresses first visit on 21 June, the editing stops after 22 June, and the requests continue in bursts to the right edge of the window and beyond it, peaking at 471 requests on 26 June. Two brackets below the axis mark the Artifactory message board, 12 May to 4 July, and the Hugging Face attack, 9 to 13 July.";

var NS = "http://www.w3.org/2000/svg";
function el(n,a){ var e=document.createElementNS(NS,n);
  if(a) for(var k in a) e.setAttribute(k,a[k]); return e; }
function fmt(d){ return new Date(d+"T00:00:00Z")
  .toLocaleDateString("en-GB",{day:"numeric",month:"short",timeZone:"UTC"}); }
function n(v){ return v.toLocaleString(); }

function mount(container){
  if(!container || container.dataset.mounted==="1") return container && container._figure;
  container.dataset.mounted = "1";
  container.classList.add("fig-"+NAME);

  // ── DOM ────────────────────────────────────────────────────────────────
  var tl = document.createElement("div"); tl.className = "tl";
  var above = document.createElement("div"); above.className = "lanes";
  var plot = document.createElement("div"); plot.className = "plot";
  var svg = el("svg",{viewBox:"0 0 1000 300",role:"img","aria-label":ARIA});
  var tip = document.createElement("div"); tip.className = "tip";
  plot.appendChild(svg); plot.appendChild(tip);
  var civs = document.createElement("div"); civs.className = "civs";
  var below = document.createElement("div"); below.className = "lanes below";
  var outside = document.createElement("div"); outside.className = "outside";
  var olab = document.createElement("div"); olab.className = "outside-label"; olab.textContent = "Hugging Face incident";
  // On a phone the annotations become numbered markers on the chart and these
  // two lists under it (hidden on wider screens, where the labels spread out).
  var listOurs = document.createElement("ol"); listOurs.className = "evlist";
  var listOut = document.createElement("ol"); listOut.className = "evlist";
  outside.appendChild(civs); outside.appendChild(below); outside.appendChild(listOut); outside.appendChild(olab);
  var newbox = document.createElement("div"); newbox.className = "newbox";
  var ilab = document.createElement("div"); ilab.className = "newbox-label"; ilab.textContent = "Wiki incident (new)";
  // axis titles as an HTML row above the markers (mobile only; the SVG carries
  // them rotated beside the axes on wider screens)
  var axt = document.createElement("div"); axt.className = "axt";
  axt.innerHTML = '<span class="l">AI Agent Wiki Edits per day</span><span class="r">OpenAI Employee Traffic per day</span>';
  newbox.appendChild(axt); newbox.appendChild(above); newbox.appendChild(plot); newbox.appendChild(listOurs); newbox.appendChild(ilab);
  tl.appendChild(newbox); tl.appendChild(outside);
  // keep any host-supplied <figcaption> after the chart
  var cap = container.querySelector(":scope > figcaption");
  if(cap) container.insertBefore(tl, cap); else container.appendChild(tl);

  // ── geometry ───────────────────────────────────────────────────────────
  var days = DAYS, N = days.length;
  var E = function(r){ return r.a + r.o; };           // edits that day
  var V = function(r){ return r.r + r.f + r.h; };     // OpenAI requests that day
  var maxE = Math.max.apply(null, days.map(E));       // 6,273 edits, 18 Jun
  // Requests get their own axis on a round 0–1,000 domain. The two quantities are
  // an order of magnitude apart, so a shared axis would flatten the requests to
  // nothing; a domain a bit over twice the 471-request peak keeps them reading as
  // the secondary series against the edit bars without squashing them flat.
  var maxR = 1000;
  var idx = function(d){ for(var i=0;i<N;i++) if(days[i].d===d) return i; return -1; };

  // The SVG's coordinate space is sized in CSS pixels: the viewBox is as wide as
  // the plot (capped at 1000), so type stays 10px at every width instead of
  // shrinking with the column. Under 600px ("mobile") the chart is taller, the
  // margins tighter, the axis titles run horizontally above the axes, and the
  // annotation labels collapse to numbered markers keyed to a list below.
  var mobile=false, W=1000, H=300, M, iw, ih, bw, gap;
  function size(){
    var cw = plot.clientWidth || container.clientWidth || 1000;
    mobile = cw < 600;
    W = cw >= 1000 ? 1000 : Math.max(cw, 280);
    H = mobile ? Math.round(Math.min(240, Math.max(180, W*0.62))) : Math.round(W*0.3);
    M = mobile ? {l:36, r:42, t:10, b:24} : {l:62, r:68, t:14, b:26};
    iw=W-M.l-M.r; ih=H-M.t-M.b;
    bw = iw/N; gap = Math.min(1.6, bw*0.14);
    svg.setAttribute("viewBox","0 0 "+W+" "+H);
    tl.classList.toggle("m", mobile);
  }
  var yE = function(v){ return M.t+ih - (v/maxE)*ih; };
  var yV = function(v){ return M.t+ih - (v/maxR)*ih; };
  // Horizontal position as a fraction of the SVG's own width, so HTML labels
  // stay locked to the plot at any container width. The margins are constant
  // pixels and change at the mobile breakpoint, so the fraction moves with the
  // width too — every caller has to read it after the redraw it belongs to.
  var fracOf = function(i){ return (M.l + (i+0.5)*bw) / W; };
  var xOf = function(i){ return M.l + (i+0.5)*bw; };
  var STEM = {above:60, below:20}, STEM_M = {above:30, below:14}, LANE_GAP = 2, PAD = 5;

  function drawChart(){
    size();
    svg.textContent="";

    // ── left axis: edits per day ─────────────────────────────────────────
    [2000,4000,6000].forEach(function(v){
      var y = yE(v);
      svg.appendChild(el("line",{x1:M.l,x2:W-M.r,y1:y,y2:y,"class":"hair"}));
      var t = el("text",{x:M.l-7,y:y+3.2,"class":"ax","text-anchor":"end"});
      t.textContent = v>=1000 ? (v/1000)+"k" : v; svg.appendChild(t);
    });

    // ── right axis: total OpenAI-linked requests per day, one area ──────────
    var tot = days.map(function(r){ return V(r); });
    if(tot.some(function(v){ return v>0; })){
      var pts = days.map(function(r,i){ return xOf(i)+","+yV(tot[i]); });
      for(var i=N-1;i>=0;i--) pts.push(xOf(i)+","+yV(0));
      svg.appendChild(el("polygon",{points:pts.join(" "), fill:"var(--v2)","fill-opacity":.85}));
      svg.appendChild(el("polyline",{
        points: days.map(function(r,i){ return xOf(i)+","+yV(tot[i]); }).join(" "),
        fill:"none", stroke:"var(--v1)", "stroke-width":1, "stroke-opacity":.75}));
    }

    [250,500,750,1000].forEach(function(v){
      var y = yV(v);
      var t = el("text",{x:W-M.r+7,y:y+3.2,"class":"axr","text-anchor":"start"});
      t.textContent = v.toLocaleString(); svg.appendChild(t);
      svg.appendChild(el("line",{x1:W-M.r,x2:W-M.r+4,y1:y,y2:y,
        stroke:"var(--v1)","stroke-width":1,"stroke-opacity":.5}));
    });

    // Rules through the plot only for events the wiki data actually witnesses.
    // The outside-the-dumps events fall where there are no bars, so a rule there
    // marks nothing — their leader line from below reaches the axis instead.
    MS.filter(function(m){ return m.src==="ours"; }).forEach(function(m){
      var i = idx(m.d); if(i<0 || (!E(days[i]) && !V(days[i]))) return;
      // on a phone the rule runs to the top edge, meeting the marker's leader
      svg.appendChild(el("line",{x1:xOf(i),x2:xOf(i),y1:mobile?0:M.t,y2:M.t+ih,
        "class":"evrule",stroke:"var(--accent)"}));
    });

    // ── edits, drawn over the request areas ──────────────────────────────
    // Slightly translucent so the request areas behind them stay readable where
    // the two series overlap on 21–22 Jun.
    days.forEach(function(r,i){
      var tot=E(r); if(!tot) return;
      var h = Math.max(M.t+ih-yE(tot), 1);
      svg.appendChild(el("rect",{x:M.l+i*bw+gap/2, y:M.t+ih-h,
        width:Math.max(bw-gap,1), height:h, fill:"var(--vivid-foreground)",
        "fill-opacity":.78}));
    });

    svg.appendChild(el("line",{x1:M.l,x2:W-M.r,y1:M.t+ih,y2:M.t+ih,"class":"base"}));

    if(!mobile){
      var yl = el("text",{"class":"axlabel","text-anchor":"middle",
        transform:"rotate(-90 "+(M.l-42)+" "+(M.t+ih/2)+")", x:M.l-42, y:M.t+ih/2});
      yl.textContent = "AI Agent Wiki Edits per day"; svg.appendChild(yl);
      var yr = el("text",{"class":"axlabel r","text-anchor":"middle",
        transform:"rotate(90 "+(W-M.r+48)+" "+(M.t+ih/2)+")", x:W-M.r+48, y:M.t+ih/2});
      yr.textContent = "OpenAI Employee Traffic per day"; svg.appendChild(yr);
    }

    var every = mobile ? 14 : 7;
    days.forEach(function(r,i){
      if(i%every) return;
      var t = el("text",{x:xOf(i), y:M.t+ih+15, "class":"ax","text-anchor":"middle"});
      t.textContent = fmt(r.d);
      svg.appendChild(t);
    });

    days.forEach(function(r,i){
      var b = el("rect",{x:M.l+i*bw, y:M.t, width:bw, height:ih, "class":"band"});
      b.addEventListener("mousemove",function(e){ showTip(e,r); });
      b.addEventListener("mouseleave",function(){ tip.style.opacity=0; });
      svg.appendChild(b);
    });
  }

  function buildLabels(){
    above.textContent=""; below.textContent="";
    listOurs.textContent=""; listOut.textContent="";
    var count = 0;
    MS.forEach(function(m){
      var i=idx(m.d); if(i<0) return;
      // Numbers are only shown on a phone, where the outside-the-dumps box is
      // hidden, so only the wiki-witnessed events are counted (MS is in date
      // order, so the numbers read left to right).
      var n = m.src==="ours" ? ++count : 0;
      var host = m.src==="ours" ? above : below;
      var d = document.createElement("div");
      d.className = "lab "+m.src;
      d.tabIndex = 0;
      d.dataset.i = i;
      d.dataset.n = n;
      if(m.ts) d.dataset.ts = m.ts;
      var dt = fmt(m.d)+(m.d2?" &ndash; "+fmt(m.d2):"");
      d.innerHTML = '<span class="dt">'+dt+'</span>'+
                    '<span class="cond">'+m.c+'</span>'+
                    '<span class="full">'+m.f+'</span>';
      d.addEventListener("mouseenter",function(){ tl.classList.add("focusing"); placeFull(d); });
      d.addEventListener("mouseleave",function(){ tl.classList.remove("focusing"); });
      d.addEventListener("focus",function(){ tl.classList.add("focusing"); placeFull(d); });
      d.addEventListener("blur",function(){ tl.classList.remove("focusing"); });
      host.appendChild(d);

      // the list row behind marker n (mobile only, see figures.css)
      var li = document.createElement("li");
      li.className = "ev "+m.src;
      li.dataset.n = n;
      li.innerHTML = '<span class="n">'+n+'</span><span class="dt">'+dt+'</span>'+
                     '<span class="cond">'+m.c+'</span>'+
                     '<span class="full">'+m.f+'</span>';
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "evbtn"; btn.setAttribute("aria-expanded","false");
      btn.setAttribute("aria-label", "More about: "+m.c.replace(/<[^>]+>/g,""));
      li.appendChild(btn);
      var toggle = function(){
        var open = !li.classList.contains("open");
        li.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open));
      };
      li.addEventListener("click", toggle);
      (m.src==="ours" ? listOurs : listOut).appendChild(li);
      // tapping the marker opens its row
      d.addEventListener("click",function(){
        if(!mobile) return;
        if(!li.classList.contains("open")) toggle();
        li.scrollIntoView({block:"nearest", behavior:"smooth"});
      });
    });
    layout();
  }

  /* The full note opens as a popover above its label (figures.css). Centre it on
     the label, then slide it sideways just enough to stay inside the lane, so a
     label at either edge of the chart does not push the note out of the column. */
  function placeFull(d){
    var full = d.querySelector(".full"); if(!full || mobile) return;
    var tw = d.parentNode.clientWidth || 1;
    var pw = Math.min(268, tw);
    full.style.width = pw+"px";
    var labLeft = d._x - d._w/2;                       // label's left edge in lane coords
    var pl = Math.max(0, Math.min(d._x - pw/2, tw - pw));
    full.style.left = (pl - labLeft)+"px";
  }

  /* Push a row of labels apart so none overlap, keeping each as close to its
     own date as the space allows: seed at the target, sweep right enforcing a
     minimum separation, sweep back left, then clamp to the container. */
  function spread(row, avail, gap){
    var n = row.length; if(!n) return;
    var sep = function(a,b){ return a._w/2 + gap + b._w/2; };
    row.forEach(function(d){ d._x = d._t; });
    var i;
    // 1. sweep right, opening up the minimum separation
    for(i=1;i<n;i++)
      row[i]._x = Math.max(row[i]._x, row[i-1]._x + sep(row[i-1],row[i]));
    // 2. pull the block back inside the right edge, carrying the separation
    //    with it. Clamping each label independently lets the clamp undo step 1
    //    and re-collide the last pair.
    row[n-1]._x = Math.min(row[n-1]._x, avail - row[n-1]._w/2);
    for(i=n-2;i>=0;i--)
      row[i]._x = Math.min(row[i]._x, row[i+1]._x - sep(row[i],row[i+1]));
    // 3. same again off the left edge, for the case where step 2 overshot
    row[0]._x = Math.max(row[0]._x, row[0]._w/2);
    for(i=1;i<n;i++)
      row[i]._x = Math.max(row[i]._x, row[i-1]._x + sep(row[i-1],row[i]));
  }

  /* Labels are spread horizontally rather than stacked over their date, and an
     elbow leader runs from each label to the day it describes — a vertical stub
     out of the label, a diagonal across, then a stub into the plot. Dense
     clusters therefore fan out sideways instead of building a tall tower. */
  function layout(){
    [["above",above],["below",below]].forEach(function(pair){
      var which = pair[0], host = pair[1];
      var labs = Array.prototype.filter.call(host.children,
        function(e){ return e.classList.contains("lab"); });
      if(!labs.length) return;
      var wpx = host.clientWidth || 1;

      labs.forEach(function(d){
        d.style.left = "0px"; d.style.top = d.style.bottom = "";
        var b = d.getBoundingClientRect();
        // the target is read from the day, not cached: drawChart() has just
        // re-derived the margins for this width, and they move the fraction
        d._w = b.width; d._h = b.height; d._t = fracOf(+d.dataset.i)*wpx;
      });

      var sorted = labs.slice().sort(function(a,b){ return a._t-b._t; });
      var need = sorted.reduce(function(s,d){ return s+d._w+PAD; },0);
      var rows = need <= wpx ? 1 : 2;
      sorted.forEach(function(d,i){ d._row = rows===1 ? 0 : i%2; });
      for(var r=0;r<rows;r++) spread(sorted.filter(function(d){ return d._row===r; }), wpx, PAD);

      var rowH = [];
      sorted.forEach(function(d){ rowH[d._row] = Math.max(rowH[d._row]||0, d._h); });
      var stem = mobile ? STEM_M : STEM;
      var off = []; var run = stem[which];
      for(var q=0;q<rows;q++){ off[q] = run; run += rowH[q] + LANE_GAP; }
      host.style.height = run + "px";

      var sv = host.querySelector("svg.leads");
      if(!sv){ sv = document.createElementNS(NS,"svg"); sv.setAttribute("class","leads");
               host.insertBefore(sv, host.firstChild); }
      sv.setAttribute("viewBox","0 0 "+wpx+" "+run);
      sv.setAttribute("width",wpx); sv.setAttribute("height",run);
      sv.textContent = "";

      // A CONSTANT stub is what keeps leaders from crossing: `spread` preserves
      // date order, so label order and target order are both monotonic, and
      // equal-geometry leaders then fan out without ever intersecting.
      var STUB = 6;
      labs.forEach(function(d){
        var o = off[d._row];
        d.style.left = d._x+"px";
        if(which==="above"){ d.style.bottom = o+"px"; d.style.top = ""; }
        else               { d.style.top    = o+"px"; d.style.bottom = ""; }

        var edge = which==="above" ? run-o : o;          // label edge facing plot
        var endY = which==="above" ? run : 0;            // the plot boundary
        var dir  = which==="above" ? 1 : -1;
        // The plot-end stub is per label (data-ts): a longer rise means this
        // leader's diagonal starts higher, so leaders converging on the same
        // cluster sit at visibly different heights instead of stacking up.
        var tstub = which==="below" ? 7 : Math.min(+(d.dataset.ts || STUB), stem[which] - STUB - 12);
        var pts = [
          [d._x, edge],
          [d._x, edge + dir*STUB],
          [d._t, endY - dir*tstub],
          [d._t, endY]
        ].map(function(p){ return p.join(","); }).join(" ");
        var pl = document.createElementNS(NS,"polyline");
        pl.setAttribute("points",pts);
        pl.setAttribute("class","lead");
        pl.setAttribute("stroke",getComputedStyle(d).color);
        sv.appendChild(pl);
      });
    });
    renderCivs();
  }

  /* The brackets get one shared treatment — a bar under the axis with its span
     and name — so colour stays free to mean provenance. The Hugging Face bracket
     is only days wide, so its name can't sit centred under it. A name that
     overflows its bracket drops to the next depth rather than sliding sideways,
     so the stem is always a straight vertical down from the period it names. */
  function renderCivs(){
    var host = civs;
    var wpx = host.clientWidth || 1;
    host.textContent = "";
    var sv = document.createElementNS(NS,"svg");
    sv.setAttribute("class","civleads");
    host.appendChild(sv);

    var BAR_Y = 4, DEPTHS = [8, 22, 36], SEP = 10;
    var taken = [];
    var maxDepth = DEPTHS[0];

    CIVS.forEach(function(c){
      var i = idx(c.s), j = idx(c.e); if(i<0||j<0) return;
      var x1 = fracOf(i)*wpx, x2 = fracOf(j)*wpx, mid = (x1+x2)/2;

      var bar = document.createElement("div");
      bar.className = "civbar";
      bar.style.left = x1+"px"; bar.style.width = Math.max(x2-x1,2)+"px";
      host.appendChild(bar);

      var lab = document.createElement("div");
      lab.className = "civlab";
      lab.textContent = c.n;
      host.appendChild(lab);
      var w = lab.getBoundingClientRect().width;
      var left = Math.max(0, Math.min(wpx-w, mid - w/2));

      var d = 0;
      while(taken[d] && taken[d].some(function(p){ return left < p[1]+SEP && p[0] < left+w+SEP; })) d++;
      (taken[d] = taken[d] || []).push([left, left+w]);
      var y = DEPTHS[Math.min(d, DEPTHS.length-1)];
      maxDepth = Math.max(maxDepth, y);

      lab.style.left = left+"px";
      lab.style.top  = y+"px";

      if(w > (x2-x1) || d > 0){          // needs a stem to tie it to its bracket
        var pl = document.createElementNS(NS,"polyline");
        pl.setAttribute("points", mid+","+BAR_Y+" "+mid+","+y);
        pl.setAttribute("class","civlead");
        sv.appendChild(pl);
      }
    });

    var hh = maxDepth + 20;
    host.style.height = hh+"px";
    sv.setAttribute("viewBox","0 0 "+wpx+" "+hh);
    sv.setAttribute("width",wpx); sv.setAttribute("height",hh);
  }

  function showTip(ev,r){
    var e = E(r), v = V(r);
    if(!e && !v && r.cov){ tip.style.opacity=0; return; }
    var html = '<div class="d">'+new Date(r.d+"T00:00:00Z").toLocaleDateString("en-GB",
        {day:"numeric",month:"long",timeZone:"UTC"})+'</div>';
    if(e) html +=
      '<div class="r"><span>Edits &middot; Azure</span>'+n(r.a)+'</div>'+
      '<div class="r"><span>Edits &middot; other</span>'+n(r.o)+'</div>'+
      '<div class="r tot"><span>Edits</span>'+n(e)+'</div>';
    else if(!r.cov) html += '<div class="r"><span>Edits</span>no dump coverage</div>';
    else html += '<div class="r"><span>Edits</span>0</div>';
    if(v){
      html += '<div class="sec"></div>';
      html += '<div class="r tot"><span>OpenAI requests</span>'+n(v)+'</div>';
    }
    tip.innerHTML = html;
    var pr = plot.getBoundingClientRect();
    var l = ev.clientX-pr.left+13;
    if(l > pr.width-190) l = ev.clientX-pr.left-190;
    tip.style.left = Math.max(0,l)+"px";
    // sit above the pointer so the bar or area being read is not covered; fall back to
    // below only when there is no room above
    var y = ev.clientY-pr.top, th = tip.offsetHeight || 60;
    tip.style.top = (y - th - 14 >= 0 ? y - th - 14 : y + 18) + "px";
    tip.style.opacity = 1;
  }

  // ── go ─────────────────────────────────────────────────────────────────
  drawChart();
  buildLabels();

  // Redraw the chart (its viewBox follows the plot width) and re-run the HTML
  // label layout whenever the container's width changes.
  var lastW = container.clientWidth, ro = null;
  function onResize(){
    var w = container.clientWidth;
    if(w===lastW) return; lastW = w; drawChart(); layout();
  }
  if(window.ResizeObserver){ ro = new ResizeObserver(onResize); ro.observe(container); }
  else window.addEventListener("resize", layout);
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(layout);

  var api = {
    container: container,
    layout: layout,
    destroy: function(){
      if(ro) ro.disconnect(); else window.removeEventListener("resize", layout);
      if(tl.parentNode) tl.parentNode.removeChild(tl);
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
