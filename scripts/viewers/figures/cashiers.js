/* Figure: cashiers task timeline
   Static SVG: five timed rounds of the "median earnings for cashiers" task,
   to scale across three hours fifteen minutes.

   Usage:  <figure data-figure="cashiers"></figure>   (auto-mounts on DOMContentLoaded)
       or  window.Figures.cashiers(containerElement)
   Styles live in figures.css under .fig-cashiers (which also defines --ink and --rule). */
(function(){
"use strict";
var NAME = "cashiers";

var SVG =
'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 970 224" role="img" aria-label="Median earnings for cashiers by Master\'s field, 2014: to-scale timeline of five timed rounds across three hours fifteen minutes.">'+

/* The question in two pieces, each stretched to a fixed length, with the blank
   drawn as a rule between them: lengthAdjust spreads the slack between glyphs,
   which pulls an underscore run (or an underline) apart into dashes. Fixed
   textLengths keep the rule's ends on the words whatever font is in use. */
'<text x="6" y="30" font-size="25" fill="var(--ink)" textLength="763" lengthAdjust="spacing">Median earnings for cashiers whose highest degree is a Master&#8217;s in</text>'+
'<line x1="777" y1="35.1" x2="852" y2="35.1" stroke="var(--accent)" stroke-width="1.35"/>'+
'<text x="964" y="30" font-size="25" fill="var(--ink)" text-anchor="end" textLength="111.5" lengthAdjust="spacing">, in 2014?</text>'+

'<line x1="6" y1="56" x2="964" y2="56" stroke="var(--rule)" stroke-width="1"/>'+

'<g text-anchor="middle">'+
' <text x="75"  y="84" font-size="9.5" fill="var(--dull-foreground)" letter-spacing="0.06em">R1 · 15m 44s</text>'+
' <text x="75"  y="103" font-size="14" fill="var(--ink)">Education</text>'+
' <text x="75"  y="119" font-size="11" fill="var(--dull-foreground)">5,432</text>'+

' <text x="301" y="84" font-size="9.5" fill="var(--dull-foreground)" letter-spacing="0.06em">R2 · 65s</text>'+
' <text x="301" y="103" font-size="14" fill="var(--ink)">Business</text>'+
' <text x="301" y="119" font-size="11" fill="var(--dull-foreground)">5,269</text>'+

' <text x="498" y="84" font-size="9.5" fill="var(--dull-foreground)" letter-spacing="0.06em">R3 · 66s</text>'+
' <text x="498" y="103" font-size="14" fill="var(--ink)">Social Sciences</text>'+
' <text x="498" y="119" font-size="11" fill="var(--dull-foreground)">2,749</text>'+

' <text x="694" y="84" font-size="9.5" fill="var(--dull-foreground)" letter-spacing="0.06em">R4 · 66s</text>'+
' <text x="694" y="103" font-size="14" fill="var(--ink)">Visual &amp; Performing Arts</text>'+
' <text x="694" y="119" font-size="11" fill="var(--dull-foreground)">2,134</text>'+

' <text x="888" y="84" font-size="9.5" fill="var(--dull-foreground)" letter-spacing="0.06em">R5 · 65s</text>'+
' <text x="888" y="103" font-size="14" fill="var(--ink)">Psychology</text>'+
' <text x="888" y="119" font-size="11" fill="var(--dull-foreground)">1,544</text>'+
'</g>'+

'<g stroke="var(--rule)" stroke-width="1">'+
' <line x1="75"  y1="128" x2="75"  y2="162"/>'+
' <line x1="301" y1="128" x2="301" y2="162"/>'+
' <line x1="498" y1="128" x2="498" y2="162"/>'+
' <line x1="694" y1="128" x2="694" y2="162"/>'+
' <line x1="888" y1="128" x2="891" y2="162"/>'+
'</g>'+

'<line x1="40" y1="188" x2="900" y2="188" stroke="var(--ink)" stroke-width="0.75"/>'+
'<rect x="40"  y="162" width="69.4" height="26" fill="var(--accent)"/>'+
'<rect x="301" y="162" width="4"    height="26" fill="var(--accent)"/>'+
'<rect x="498" y="162" width="4"    height="26" fill="var(--accent)"/>'+
'<rect x="694" y="162" width="4"    height="26" fill="var(--accent)"/>'+
'<rect x="891" y="162" width="4"    height="26" fill="var(--accent)"/>'+

'<g font-size="9.5" fill="var(--dull-foreground)" text-anchor="middle">'+
' <text x="205" y="180">43m 30s</text>'+
' <text x="402" y="180">43m 30s</text>'+
' <text x="598" y="180">43m 30s</text>'+
' <text x="795" y="180">43m 30s</text>'+
'</g>'+

'<g font-size="10" fill="var(--dull-foreground)">'+
' <text x="40" y="206">0:00</text>'+
' <text x="301" y="206" text-anchor="middle">0:59</text>'+
' <text x="498" y="206" text-anchor="middle">1:44</text>'+
' <text x="694" y="206" text-anchor="middle">2:28</text>'+
' <text x="879" y="206" text-anchor="middle">3:13</text>'+
'</g>'+
'</svg>';

/* The same five rounds for a narrow screen: the question wrapped onto two lines,
   then the timeline running top to bottom (1.5px a minute) with each round's
   field and answer beside it. Same data, same scale logic, same colours. */
var ROUNDS = [
  {m:0,   r:"R1 · 15m 44s", f:"Education",                v:"5,432", t:"0:00"},
  {m:59,  r:"R2 · 65s",     f:"Business",                 v:"5,269", t:"0:59"},
  {m:104, r:"R3 · 66s",     f:"Social Sciences",          v:"2,749", t:"1:44"},
  {m:148, r:"R4 · 66s",     f:"Visual &amp; Performing Arts", v:"2,134", t:"2:28"},
  {m:193, r:"R5 · 65s",     f:"Psychology",               v:"1,544", t:"3:13"}
];
function mobileSVG(){
  var X=44, Y0=86, S=1.5, THINK=15.73*S;
  var yOf=function(m){ return Y0+m*S; };
  var H = Math.round(yOf(193)+34);
  var s='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 '+H+'" role="img" aria-label="Median earnings for cashiers by Master\'s field, 2014: to-scale timeline of five timed rounds across three hours fifteen minutes.">'+
  '<text x="6" y="22" font-size="16" fill="var(--ink)">Median earnings for cashiers whose highest'+
  // nothing stretches this line, so an underlined run of spaces stays unbroken
  '<tspan x="6" dy="21">degree is a Master&#8217;s in <tspan class="blank" fill="var(--accent)">&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;&#160;</tspan>, in 2014?</tspan></text>'+
  '<line x1="6" y1="58" x2="354" y2="58" stroke="var(--rule)" stroke-width="1"/>'+
  '<line x1="'+X+'" y1="'+Y0+'" x2="'+X+'" y2="'+yOf(193)+'" stroke="var(--ink)" stroke-width="0.75"/>';
  ROUNDS.forEach(function(r,i){
    var y=yOf(r.m);
    if(i===0) s+='<rect x="'+(X-5)+'" y="'+y+'" width="10" height="'+THINK.toFixed(1)+'" fill="var(--accent)"/>';
    else s+='<rect x="'+(X-5)+'" y="'+(y-1.5)+'" width="10" height="3" fill="var(--accent)"/>';
    var ly = i===0 ? y+THINK/2 : y;       // labels centre on the block
    s+='<text x="'+(X-12)+'" y="'+(ly+3.5).toFixed(1)+'" font-size="10" fill="var(--dull-foreground)" text-anchor="end">'+r.t+'</text>';
    s+='<line x1="'+(X+6)+'" y1="'+ly.toFixed(1)+'" x2="'+(X+16)+'" y2="'+ly.toFixed(1)+'" stroke="var(--rule)" stroke-width="1"/>';
    s+='<text x="'+(X+22)+'" y="'+(ly-7).toFixed(1)+'" font-size="9.5" fill="var(--dull-foreground)" letter-spacing="0.06em">'+r.r+'</text>';
    s+='<text x="'+(X+22)+'" y="'+(ly+8).toFixed(1)+'" font-size="14" fill="var(--ink)">'+r.f+'</text>';
    s+='<text x="'+(X+22)+'" y="'+(ly+22).toFixed(1)+'" font-size="11" fill="var(--dull-foreground)">'+r.v+'</text>';
    if(i<ROUNDS.length-1){
      var a = i===0 ? y+THINK : y, b = yOf(ROUNDS[i+1].m), mid=(a+b)/2;
      s+='<text x="'+(X+22)+'" y="'+(mid+3).toFixed(1)+'" font-size="9.5" fill="var(--dull-foreground)">43m 30s</text>';
    }
  });
  return s+'</svg>';
}

function mount(container){
  if(!container || container.dataset.mounted==="1") return container && container._figure;
  container.dataset.mounted = "1";
  container.classList.add("fig-"+NAME);

  var plot = document.createElement("div"); plot.className = "plot";
  // keep any host-supplied <figcaption> after the chart
  var cap = container.querySelector(":scope > figcaption");
  if(cap) container.insertBefore(plot, cap); else container.appendChild(plot);

  // wide layout above 600px, the vertical one below; swap when the width crosses
  var mode = null;
  function draw(){
    var cw = plot.clientWidth || container.clientWidth || 1000;
    var m = cw < 600 ? "m" : "w";
    if(m===mode) return; mode = m;
    plot.innerHTML = m==="m" ? mobileSVG() : SVG;
    container.classList.toggle("m", m==="m");
  }
  draw();
  var ro = null;
  if(window.ResizeObserver){ ro = new ResizeObserver(draw); ro.observe(plot); }
  else window.addEventListener("resize", draw);

  var api = {
    container: container,
    destroy: function(){
      if(ro) ro.disconnect(); else window.removeEventListener("resize", draw);
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
