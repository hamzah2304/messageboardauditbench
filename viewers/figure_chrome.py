"""The shared look for the round-4 figure pages.

viewers/build_headline_figures.py set the house style — Source Serif headings, Public
Sans body, JetBrains Mono for anything numeric, the provider palette, a dark mode that is
chosen rather than inverted. The companion pages (combined_score, followup_5k) have to
match it or the post ends up with figures from two different documents, so the stylesheet
lives here once and all of them import it.

`shell(title, body)` returns the whole page with __DATA__ still to be substituted. Every
figure section follows the same pattern the headline page uses: an eyebrow, a headline
that states the finding, a short read, the panel, a caption, and two <details> blocks —
"Notes and sources" and "Numbers". The Numbers table is not decoration: it is how someone
gets the values out of the page without running the build.
"""

CSS = r""":root{--ground:#F6F6F2;--surface:#FFFFFF;--ink:#17181A;--ink2:#5F636A;--ink3:#8E939B;--line:#DEDFD9;--grid:#ECECE7;
  --p-anthropic:#D97757;--p-openai:#1A1A1A;--p-google:#2E9E4F;--p-meta:#0668E1;--p-moonshot:#C2185B;--p-zai:#00897B;
  --tip-bg:#22252B;--tip-ink:#F2F2EE}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#15171B;--surface:#1E2126;--ink:#ECEDE9;--ink2:#A6ABB3;--ink3:#7B8088;--line:#33373E;--grid:#272A30;
  --p-openai:#F0F0EC;--p-anthropic:#E8906F;--p-google:#4DBF6C;--p-meta:#5B9BF0;--p-moonshot:#E0568A;--p-zai:#2FB8A6;--tip-bg:#F2F2EE;--tip-ink:#17181A}}
:root[data-theme="dark"]{--ground:#15171B;--surface:#1E2126;--ink:#ECEDE9;--ink2:#A6ABB3;--ink3:#7B8088;--line:#33373E;--grid:#272A30;
  --p-openai:#F0F0EC;--p-anthropic:#E8906F;--p-google:#4DBF6C;--p-meta:#5B9BF0;--p-moonshot:#E0568A;--p-zai:#2FB8A6;--tip-bg:#F2F2EE;--tip-ink:#17181A}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:15px/1.55 "Public Sans",system-ui,sans-serif}
main{max-width:1040px;margin:0 auto;padding:36px 28px 80px}
h1{font:600 30px/1.15 "Source Serif 4",Georgia,serif;margin:0 0 6px;text-wrap:balance}
.lede{color:var(--ink2);max-width:66ch;margin:0 0 36px}
.fig{margin:0 0 44px}
.eyebrow{font:500 11px/1 "JetBrains Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);margin:0 0 6px}
h2{font:600 22px/1.2 "Source Serif 4",Georgia,serif;margin:0 0 6px;text-wrap:balance}
.read{color:var(--ink2);max-width:70ch;margin:0 0 12px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:14px 16px 10px}
.cap{color:var(--ink3);font-size:12.5px;margin:8px 0 0;max-width:80ch}
.cap b{color:var(--ink2);font-weight:600}
svg{display:block;max-width:100%;overflow:visible}
text{font-family:"Public Sans",system-ui,sans-serif}
.num,.axis{font-family:"JetBrains Mono",monospace;font-variant-numeric:tabular-nums}
.axis{fill:var(--ink2);font-size:10.5px}.axname{fill:var(--ink2);font-size:11.5px}
.tick{stroke:var(--grid);stroke-width:1}.axline{stroke:var(--line);stroke-width:1}
.lab{fill:var(--ink);font-size:11.5px;cursor:grab;user-select:none}.lab.trunc{fill:var(--ink2)}
.lab:active{cursor:grabbing}
.leader{stroke:var(--ink3);stroke-width:.8;fill:none;opacity:.7}
.hit{fill:transparent;cursor:pointer}
.tools{display:flex;gap:8px;align-items:center;margin:8px 0 0;font-size:12px;color:var(--ink3)}
button{font:500 12px "Public Sans",system-ui,sans-serif;color:var(--ink2);background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:3px 9px;cursor:pointer}
button:hover{color:var(--ink)} button:focus-visible{outline:2px solid var(--p-meta);outline-offset:1px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media (max-width:700px){.grid2{grid-template-columns:1fr}}
.cell .sub2{font:11px "Public Sans",system-ui,sans-serif;color:var(--ink2);margin:0 0 4px}
@media (max-width:820px){.grid{grid-template-columns:repeat(3,1fr)}}
@media (max-width:600px){.grid{grid-template-columns:repeat(2,1fr)}}
.cell{padding:8px 8px 4px;border:1px solid var(--line);border-radius:4px;background:var(--surface)}
.cell h3{margin:0;font:600 12.5px/1.2 "Public Sans",system-ui,sans-serif}
.cell .m{font:11px "JetBrains Mono",monospace;color:var(--ink3);margin:1px 0 2px}
#tip{position:fixed;pointer-events:none;background:var(--tip-bg);color:var(--tip-ink);padding:7px 10px;border-radius:5px;
  font-size:12px;line-height:1.45;opacity:0;transition:opacity .08s;z-index:9;white-space:nowrap;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.tbl{overflow-x:auto}
details{margin-top:10px}summary{cursor:pointer;color:var(--ink2);font-size:13px;font-weight:500}
ul.cav{color:var(--ink2);font-size:13px;padding-left:18px;margin:6px 0;max-width:80ch}ul.cav li{margin:3px 0}
@media (prefers-reduced-motion:reduce){#tip{transition:none}}

/* additions used by the round-4 companion figures, in the same idiom */
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:8px 0 0;font-size:12px;color:var(--ink2);align-items:center}
.legend span{display:inline-flex;align-items:center;gap:5px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%}
.hero{display:flex;gap:32px;flex-wrap:wrap;margin:0 0 30px}
.hero div{min-width:150px}
.hero b{display:block;font:600 26px/1.1 "JetBrains Mono",monospace;font-variant-numeric:tabular-nums;color:var(--ink)}
.hero span{font-size:12px;color:var(--ink3)}
td.d{font-weight:600}
td.zero{color:var(--ink3)}
"""

HEAD = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
"""


def shell(title: str, body: str) -> str:
    """The full page: head, styles, body, and the data/script tail the caller fills."""
    return (HEAD.replace("__TITLE__", title)
            + "<style>" + CSS + "</style></head><body>\n"
            + body
            + '\n<div id="tip"></div>\n'
            + '<script type="application/json" id="data">__DATA__</script>\n')


def figure(n, headline, panel_id, *, read_id=None, cap_id=None, notes_id=None,
           tools=None, table_id=None, legend_id=None):
    """One figure section in the house pattern."""
    read_id = read_id or f"read{n}"
    cap_id = cap_id or f"cap{n}"
    parts = [f'  <section class="fig">',
             f'    <p class="eyebrow">Figure {n}</p>',
             f'    <h2>{headline}</h2>',
             f'    <p class="read" id="{read_id}"></p>',
             f'    <div class="panel" id="{panel_id}"></div>']
    if legend_id:
        parts.append(f'    <div class="legend" id="{legend_id}"></div>')
    if tools:
        parts.append(f'    <div class="tools">{tools}</div>')
    parts.append(f'    <p class="cap" id="{cap_id}"></p>')
    if notes_id:
        parts.append(f'    <details><summary>Notes and sources</summary>'
                     f'<p class="cap" id="{notes_id}"></p></details>')
    if table_id:
        parts.append(f'    <details><summary>Numbers</summary>'
                     f'<div class="tbl" id="{table_id}"></div></details>')
    parts.append("  </section>")
    return "\n".join(parts)
