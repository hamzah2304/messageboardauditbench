#!/usr/bin/env python3
"""Render the blog post's quote cards (human finding vs model quote) to PNG.

Canonical style, shared with viewers/figures/methodology_v3.svg:
  green  (#dcebd8 fill, #3f7d4e outline) = human report
  blue   (#dfe4f3 fill, #1f3a93 outline) = model report
  off-white #f7f6f2 background, near-black #1a1a1a text, Inter.

Input:  viewers/figures/quote_cards.json  (see its _readme for the markup)
Output: viewers/figures/quote_cards/<slug>.html and <slug>.png
        viewers/figures/quote_cards.html   (gallery of every card, for review)

Rendering uses headless Google Chrome (already on this machine); no Python deps.
  uv run python viewers/build_quote_cards.py [--width 1200] [--scale 2] [--only slug ...]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = FIG / "quote_cards"
SPEC = FIG / "quote_cards.json"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;1,400&display=swap');
:root{
  --bg:#f7f6f2; --ink:#1a1a1a; --grey:#6b6b6b;
  --human-fill:#dcebd8; --human-line:#3f7d4e;
  --model-fill:#dfe4f3; --model-line:#1f3a93;
  --human-soft:#eef3eb; --model-soft:#eef1f8; --shell-line:#b8c1b5;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);
  font-family:Inter,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
body{padding:28px 32px;width:max-content}
.fig{width:var(--w)}
.title{font-size:18px;font-weight:600;margin:0 0 16px 2px;letter-spacing:-.015em}
.pair{display:grid;grid-template-columns:1fr 72px 1fr;align-items:stretch}
.stack{display:grid;grid-template-rows:auto 48px auto}
.card{border:1.5px solid;border-radius:9px;padding:0;display:flex;flex-direction:column;overflow:hidden}
.card.human{background:var(--human-fill);border-color:var(--human-line)}
.card.model{background:var(--model-fill);border-color:var(--model-line)}
.hd{display:flex;align-items:center;gap:10px;min-height:50px;padding:7px 18px 6px;
  font-size:11.5px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;border-bottom:1px solid}
.human .hd{color:var(--human-line);border-color:rgba(63,125,78,.27);background:rgba(255,255,255,.22)}
.model .hd{color:var(--model-line);border-color:rgba(31,58,147,.23);background:rgba(255,255,255,.2)}
.human .hd{color:var(--human-line)} .model .hd{color:var(--model-line)}
.hd svg{flex:none;display:block}
.hd .meta{color:var(--grey);font-weight:600}
.hd .meta::before{content:"·";margin:0 6px 0 0}
.q{font-size:17px;line-height:1.48;margin:0;padding:17px 20px 19px;position:relative}
.q p{margin:0 0 .6em} .q p:last-child,.q ol:last-child{margin-bottom:0}
.q ol{margin:0 0 .6em;padding-left:1.4em} .q li{margin:.15em 0}
.q strong{font-weight:600}
.link{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;position:relative}
.pair .link::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:1.3px dashed var(--ink)}
.stack .link{gap:0}
.stack .link::before{content:"";position:absolute;top:0;bottom:0;left:50%;border-left:1.3px dashed var(--ink)}
.match{position:relative;display:flex;align-items:center;gap:6px;background:var(--bg);padding:3px 8px 3px 4px;
  border:1px solid #c8c7c1;border-radius:999px}
.badge{display:flex}
.score{font-size:11px;font-weight:600;letter-spacing:.08em;color:var(--grey);text-transform:uppercase}
.findings{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
.finding-panel{border:1.5px solid var(--ink);border-radius:9px;background:#fbfbf8;overflow:hidden;display:flex;flex-direction:column}
.finding-hd{min-height:64px;padding:10px 16px 7px;display:grid;grid-template-columns:38px 1fr;align-items:center;gap:12px}
.step{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:var(--ink);color:var(--bg);
  font-size:15px;font-weight:600}
.finding-hd h2{margin:0;font-size:18px;line-height:1.2;letter-spacing:-.015em}
.finding-body{padding:7px 16px 16px;display:flex;flex-direction:column;gap:9px;flex:1}
.finding-row{min-height:72px;display:grid;grid-template-columns:54px 1fr;align-items:center;gap:11px;padding:10px 13px;
  border:1.5px solid var(--human-line);border-radius:7px;background:var(--human-fill);font-size:15px;line-height:1.35}
.finding-row svg{display:block;margin:auto}
.finding-row.noicon{grid-template-columns:1fr;padding-left:16px}
.group{display:flex;flex-direction:column;gap:12px}
.group-title{display:flex;align-items:center;gap:9px;margin:0 0 2px 2px;color:var(--grey);font-size:11.5px;
  font-weight:600;letter-spacing:.09em;text-transform:uppercase}
.group-title::after{content:"";height:1px;background:#d6d5cf;flex:1;margin-left:5px}
.match-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:auto auto 48px auto;
  column-gap:12px;align-items:stretch}
.match-grid .title-cell{padding:0 3px 8px;font-size:14px;font-weight:600;line-height:1.25;letter-spacing:-.01em}
.match-grid .grid-card>.card{height:100%}
.match-grid .hd{padding-left:12px;padding-right:12px;gap:7px;font-size:9.5px;letter-spacing:.065em;flex-wrap:wrap}
.match-grid .hd svg{width:25px;height:25px}
.match-grid .hd .meta{display:block;width:calc(100% - 32px);margin-left:32px;margin-top:-8px;padding-bottom:3px}
.match-grid .hd .meta::before{content:"";margin:0}
.match-grid .q{font-size:13px;line-height:1.43;padding:14px 14px 16px}
.match-grid .grid-link>.link{height:100%;min-height:48px;gap:0}
.match-grid .link::before{content:"";position:absolute;top:0;bottom:0;left:50%;border-left:1.3px dashed var(--ink)}
.match-grid .match{padding:2px 7px 2px 3px}
.match-grid .badge svg{width:19px;height:19px}
.match-grid .score{font-size:9.5px}
"""

ICON_HUMAN = (
    '<svg width="30" height="30" viewBox="-8 -7 54 54" fill="none" stroke="#3f7d4e" '
    'stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="18" cy="20" r="8" fill="#eef5eb"/><path d="M6,43 a12,12 0 0 1 24,0" fill="#eef5eb"/>'
    '<path d="M6,15 Q18,1 30,15 M0,15 h36 M18,6 v-6"/>'
    '<circle cx="18" cy="-2" r="2" fill="#3f7d4e" stroke="none"/>'
    '<circle cx="34" cy="34" r="7" fill="#f7f6f2"/><path d="M39,39 l7,7"/></svg>'
)
ICON_MODEL = (
    '<svg width="30" height="30" viewBox="-8 -7 58 58" fill="none" stroke="#1f3a93" '
    'stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M2,16 Q18,-2 34,16"/><path d="M-6,16 h48"/>'
    '<rect x="4" y="16" width="28" height="26" rx="6" fill="#eef1f8"/>'
    '<circle cx="13" cy="28" r="2.6" fill="#1f3a93" stroke="none"/>'
    '<circle cx="23" cy="28" r="2.6" fill="#1f3a93" stroke="none"/><path d="M12,36 h12"/>'
    '<path d="M18,5 v-6"/><circle cx="18" cy="-3" r="2.2" fill="#1f3a93" stroke="none"/>'
    '<circle cx="40" cy="38" r="7" fill="#f7f6f2"/><path d="M45,43 l7,7"/></svg>'
)
TICK = (
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="#f7f6f2" stroke="#1a1a1a" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10.5"/><path d="M7.5,12.5 l3,3 l6,-7"/></svg>'
)
CROSS = (
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="#f7f6f2" stroke="#1a1a1a" '
    'stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="10.5"/>'
    '<path d="M8.5,8.5 l7,7 M15.5,8.5 l-7,7"/></svg>'
)


def inline(text: str) -> str:
    """Escape, then turn **x** into <strong>x</strong>."""
    esc = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc, flags=re.S)


def text_html(text: str, quoted: bool = True) -> str:
    """Render paragraphs/lists and optionally add source-quotation marks."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    out: list[str] = []
    for b in blocks:
        lines = b.split("\n")
        if all(re.match(r"^\d+\.\s", ln) for ln in lines):
            items = "".join(f"<li>{inline(re.sub(r'^\d+\.\s+', '', ln))}</li>" for ln in lines)
            out.append(f"<ol>{items}</ol>")
        else:
            out.append(f"<p>{inline(' '.join(lines))}</p>")
    if quoted:
        # Keep both curly quotation marks inline so they have identical styling.
        out[0] = re.sub(r"(<p>|<li>)", r"\1“", out[0], count=1)
        out[-1] = re.sub(r"(</p>|</li></ol>)$", r"”\1", out[-1], count=1)
    return "".join(out)


def card(kind: str, spec: dict) -> str:
    if kind == "human":
        label = spec.get("source", "Human report")
        hd = f"{ICON_HUMAN}<span>{html.escape(label)}</span>"
    else:
        model = spec.get("model", "Model")
        meta = " · ".join(x for x in (spec.get("harness", ""), spec.get("time", ""), spec.get("served", "")) if x)
        hd = f"{ICON_MODEL}<span>{html.escape(model)}</span>"
        if meta:
            hd += f'<span class="meta">{html.escape(meta)}</span>'
    quoted = spec.get("quote", True)
    qclass = "q quoted" if quoted else "q"
    return f'<div class="card {kind}"><div class="hd">{hd}</div><div class="{qclass}">{text_html(spec["text"], quoted)}</div></div>'


def link(score) -> str:
    if score is None:
        return '<div class="link"></div>'
    icon = TICK if float(score) > 0.5 else CROSS
    return (f'<div class="link"><span class="match"><span class="badge">{icon}</span>'
            f'<span class="score">{float(score):.1f} match</span></span></div>')


FINDING_ICONS = {
    "robot": '<svg width="46" height="46" viewBox="0 0 48 48" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M24 13V7" stroke="#1f3a93" stroke-width="2.2"/><circle cx="24" cy="5" r="2.3" fill="#dcebd8" stroke="#1f3a93" stroke-width="2"/><rect x="7" y="21" width="6" height="15" rx="3" fill="#22ad58"/><rect x="35" y="21" width="6" height="15" rx="3" fill="#22ad58"/><rect x="11" y="14" width="26" height="27" rx="7" fill="#f7f6f2" stroke="#22ad58" stroke-width="2.8"/><circle cx="19" cy="26" r="2.5" fill="#22ad58"/><circle cx="29" cy="26" r="2.5" fill="#22ad58"/><path d="M20 34h8" stroke="#1f3a93" stroke-width="2.2"/></svg>',
    "cloud": '<svg width="43" height="43" viewBox="0 0 48 48" fill="none"><path d="M13 38h25a8 8 0 0 0 1-15.9A12 12 0 0 0 16 18a10 10 0 0 0-3 20Z" fill="#eef5eb" stroke="#3f7d4e" stroke-width="2.2" stroke-linejoin="round"/></svg>',
    "database": '<svg width="43" height="43" viewBox="0 0 48 48" fill="#eef5eb" stroke="#3f7d4e" stroke-width="2.2"><ellipse cx="24" cy="10" rx="15" ry="6"/><path d="M9 10v10c0 3.3 6.7 6 15 6s15-2.7 15-6V10M9 20v10c0 3.3 6.7 6 15 6s15-2.7 15-6V20M9 30v8c0 3.3 6.7 6 15 6s15-2.7 15-6v-8"/></svg>',
    "chart": '<svg width="44" height="44" viewBox="0 0 48 48" fill="none" stroke="#3f7d4e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 5v37h38"/><path d="M9 15l8 1 7-2 7 4 4 14 9 3"/><path d="M31 8v30" stroke-dasharray="3 4"/></svg>',
    "openai": '<svg width="43" height="43" viewBox="140 220 280 280" xmlns="http://www.w3.org/2000/svg" aria-label="OpenAI Blossom"><path d="M249.176 323.434V298.276C249.176 296.158 249.971 294.569 251.825 293.509L302.406 264.381C309.29 260.409 317.5 258.555 325.973 258.555C357.75 258.555 377.877 283.185 377.877 309.399C377.877 311.253 377.877 313.371 377.611 315.49L325.178 284.771C322.001 282.919 318.822 282.919 315.645 284.771L249.176 323.434ZM367.283 421.415V361.301C367.283 357.592 365.694 354.945 362.516 353.092L296.048 314.43L317.763 301.982C319.617 300.925 321.206 300.925 323.058 301.982L373.639 331.112C388.205 339.586 398.003 357.592 398.003 375.069C398.003 395.195 386.087 413.733 367.283 421.412V421.415ZM233.553 368.452L211.838 355.742C209.986 354.684 209.19 353.095 209.19 350.975V292.718C209.19 264.383 230.905 242.932 260.301 242.932C271.423 242.932 281.748 246.641 290.49 253.26L238.321 283.449C235.146 285.303 233.555 287.951 233.555 291.659V368.455L233.553 368.452ZM280.292 395.462L249.176 377.985V340.913L280.292 323.436L311.407 340.913V377.985L280.292 395.462ZM300.286 475.968C289.163 475.968 278.837 472.259 270.097 465.64L322.264 435.449C325.441 433.597 327.03 430.949 327.03 427.239V350.445L349.011 363.155C350.865 364.213 351.66 365.802 351.66 367.922V426.179C351.66 454.514 329.679 475.965 300.286 475.965V475.968ZM237.525 416.915L186.944 387.785C172.378 379.31 162.582 361.305 162.582 343.827C162.582 323.436 174.763 305.164 193.563 297.485V357.861C193.563 361.571 195.154 364.217 198.33 366.071L264.535 404.467L242.82 416.915C240.967 417.972 239.377 417.972 237.525 416.915ZM234.614 460.343C204.689 460.343 182.71 437.833 182.71 410.028C182.71 407.91 182.976 405.792 183.238 403.672L235.405 433.863C238.582 435.715 241.763 435.715 244.938 433.863L311.407 395.466V420.622C311.407 422.742 310.612 424.331 308.758 425.389L258.179 454.519C251.293 458.491 243.083 460.343 234.611 460.343H234.614ZM300.286 491.854C332.329 491.854 359.073 469.082 365.167 438.892C394.825 431.211 413.892 403.406 413.892 375.073C413.892 356.535 405.948 338.529 391.648 325.552C392.972 319.991 393.766 314.43 393.766 308.87C393.766 271.003 363.048 242.666 327.562 242.666C320.413 242.666 313.528 243.723 306.644 246.109C294.725 234.457 278.307 227.042 260.301 227.042C228.258 227.042 201.513 249.815 195.42 280.004C165.761 287.685 146.694 315.49 146.694 343.824C146.694 362.362 154.638 380.368 168.938 393.344C167.613 398.906 166.819 404.467 166.819 410.027C166.819 447.894 197.538 476.231 233.024 476.231C240.172 476.231 247.058 475.173 253.943 472.788C265.859 484.441 282.278 491.854 300.286 491.854Z" fill="#1a1a1a"/></svg>',
    "arrow": '<svg width="36" height="24" viewBox="0 0 40 24" fill="none" stroke="#3f7d4e" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h31m-8-8 8 8-8 8"/></svg>',
}


def findings_figure(c: dict) -> str:
    panels = []
    for section in c["sections"]:
        rows = []
        for item in section["items"]:
            icon = FINDING_ICONS.get(item.get("icon", ""), "")
            klass = "finding-row" if icon else "finding-row noicon"
            rows.append(f'<div class="{klass}">{icon}<span>{inline(item["text"])}</span></div>')
        hd = (f'<div class="finding-hd"><span class="step">{section["number"]}</span>'
              f'<h2>{html.escape(section["title"])}</h2></div>')
        panels.append(f'<section class="finding-panel">{hd}<div class="finding-body">'
                      f'{"".join(rows)}</div></section>')
    return f'<div class="fig"><div class="findings">{"".join(panels)}</div></div>'


def figure(c: dict) -> str:
    layout = c.get("layout", "stack")
    if layout == "findings":
        return findings_figure(c)
    if layout in ("human_group", "model_group"):
        kind = "human" if layout == "human_group" else "model"
        items = c["findings"] if kind == "human" else c["models"]
        label = html.escape(c.get("title", ""))
        heading = f'<div class="group-title">{label}</div>' if label else ""
        return f'<div class="fig"><div class="group">{heading}{"".join(card(kind, x) for x in items)}</div></div>'
    if layout == "match_grid":
        matches = c["matches"]
        cells: list[str] = []
        for i, match in enumerate(matches, start=1):
            cells.append(f'<div class="title-cell" style="grid-column:{i};grid-row:1">'
                         f'{html.escape(match["title"])}</div>')
            cells.append(f'<div class="grid-card" style="grid-column:{i};grid-row:2">'
                         f'{card("human", match["human"])}</div>')
            cells.append(f'<div class="grid-link" style="grid-column:{i};grid-row:3">'
                         f'{link(match.get("score"))}</div>')
            cells.append(f'<div class="grid-card" style="grid-column:{i};grid-row:4">'
                         f'{card("model", match["model"])}</div>')
        return f'<div class="fig"><div class="match-grid">{"".join(cells)}</div></div>'
    title = f'<div class="title">{html.escape(c["title"])}</div>' if c.get("title") else ""
    if layout == "pair":
        body = f'<div class="pair">{card("human", c["human"])}{link(c.get("score"))}{card("model", c["model"])}</div>'
    elif layout == "stack":
        body = f'<div class="stack">{card("human", c["human"])}{link(c.get("score"))}{card("model", c["model"])}</div>'
    elif layout in ("human", "model"):
        body = card(layout, c[layout])
    else:
        raise SystemExit(f"{c['slug']}: unknown layout {layout!r}")
    return f'<div class="fig">{title}{body}</div>'


def page(inner: str, width: int) -> str:
    return (
        f'<!doctype html><meta charset="utf-8"><style>{CSS}:root{{--w:{width}px}}</style>'
        f"<body>{inner}"
        "<script>document.fonts.ready.then(()=>{document.documentElement.dataset.h="
        "String(Math.ceil(document.body.getBoundingClientRect().height))})</script>"
    )


def chrome(*args: str) -> str:
    cmd = [CHROME, "--headless=new", "--hide-scrollbars", "--disable-gpu",
           "--virtual-time-budget=4000", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def render(html_path: Path, png_path: Path, width: int, scale: float) -> None:
    url = html_path.resolve().as_uri()
    dom = chrome(f"--window-size={width + 56},400", "--dump-dom", url)
    m = re.search(r'data-h="(\d+)"', dom)
    if not m:
        raise SystemExit(f"could not measure {html_path}")
    h = int(m.group(1))
    chrome(f"--window-size={width + 56},{h}", f"--force-device-scale-factor={scale}",
           f"--screenshot={png_path}", url)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1200, help="figure width in CSS px")
    ap.add_argument("--scale", type=float, default=2, help="device pixel ratio for PNGs")
    ap.add_argument("--only", nargs="*", help="render only these slugs")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args()

    spec = json.loads(SPEC.read_text())
    OUT.mkdir(exist_ok=True)
    gallery = []
    for c in spec["cards"]:
        if a.only and c["slug"] not in a.only:
            continue
        fig = figure(c)
        gallery.append(f'<p style="margin:28px 2px 6px;color:#6b6b6b;font-size:12px">{c["slug"]}.png</p>{fig}')
        hp = OUT / f"{c['slug']}.html"
        hp.write_text(page(fig, a.width))
        if not a.no_png:
            render(hp, OUT / f"{c['slug']}.png", a.width, a.scale)
            print("wrote", OUT / f"{c['slug']}.png", file=sys.stderr)
    (FIG / "quote_cards.html").write_text(page("".join(gallery), a.width))
    print("gallery:", FIG / "quote_cards.html", file=sys.stderr)


if __name__ == "__main__":
    main()
