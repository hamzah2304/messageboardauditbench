# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.11.2", "numpy==2.5.5"]
# ///
"""Plot equal-eval performance against run cost, plus a compact eval breakdown.

Run with `uv run scripts/plot_eval_results.py`. Reads the frozen trial snapshot;
scoring eligibility is preserved, while cost includes all attempted trials.
"""
from __future__ import annotations

import json
import shutil
import statistics
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/results/2026-11-16'
OUT = ROOT / 'docs/figures/eval-options'
EVALS = ['german-wiki', 'transluce', 'aivillage']
NAMES = ['German wiki', 'Transluce', 'AI Village']
MARKERS = ['^', 's', 'o']
INK, MUTED = '#172b3b', '#5c6c78'
PALETTE = ['#2364a8', '#b96927', '#208470', '#874a9d', '#ca4857', '#4d7a27',
           '#947229', '#526cc4', '#9c4c76', '#3c8fa1', '#525b68']


def aggregate(rows):
    out = []
    for model in sorted({r['model'] for r in rows}):
        for budget in (10, 30):
            group = [r for r in rows if r['model'] == model and r['budget'] == budget]
            evals = {}
            for ev in EVALS:
                rs = [r for r in group if r['benchmark'] == ev]
                assert len(rs) == 5
                valid = [r['score'] * 100 for r in rs if r['eligible']]
                assert valid
                evals[ev] = {'score': statistics.fmean(valid), 'n': len(valid),
                             'cost_usd': statistics.fmean(r['cost_usd'] for r in rs)}
            out.append({'model': model, 'label': group[0]['model_label'], 'budget': budget,
                        'score': statistics.fmean(x['score'] for x in evals.values()),
                        'cost_usd': statistics.fmean(x['cost_usd'] for x in evals.values()),
                        'evals': evals})
    return out


def style():
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'text.color': INK,
                         'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': INK,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.spines.left': False, 'axes.spines.bottom': False,
                         'svg.fonttype': 'none', 'svg.hashsalt': 'eval-results-20261116',
                         'pdf.fonttype': 42, 'savefig.facecolor': 'white'})


def save(fig, name):
    for ext in ['svg', 'png', 'pdf']:
        metadata = {'Creator': 'plot_eval_results.py'}
        if ext == 'svg':
            metadata['Date'] = None
        if ext == 'pdf':
            metadata['CreationDate'] = None
        fig.savefig(OUT / f'{name}.{ext}', dpi=180, metadata=metadata)
    svg = OUT / f'{name}.svg'
    svg.write_text('\n'.join(x.rstrip() for x in svg.read_text().splitlines())+'\n')
    plt.close(fig)


def main():
    style()
    rows = [json.loads(s) for s in (DATA/'runs.jsonl').read_text().splitlines()]
    assert len(rows) == 330 and len({r['run'] for r in rows}) == 330
    assert all(r['cost_usd'] >= 0 for r in rows)
    summary = aggregate(rows)
    models = sorted([r for r in summary if r['budget'] == 30], key=lambda x: -x['score'])
    colors = {m['model']: PALETTE[i] for i, m in enumerate(models)}
    by_key = {(r['model'], r['budget']): r for r in summary}
    OUT.mkdir(parents=True, exist_ok=True)
    (DATA/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    for name in ['runs.jsonl', 'summary.json', 'provenance.json']:
        shutil.copyfile(DATA/name, OUT/name)

    fig, ax = plt.subplots(figsize=(14, 8.8))
    fig.subplots_adjust(left=.09, right=.96, top=.77, bottom=.23)
    fig.text(.04, .945, 'Performance across three evals, at what cost?', fontsize=24, weight='bold')
    fig.text(.04, .895, 'Each point averages German wiki, Transluce and AI Village equally. Lines connect the two time budgets.', fontsize=11, color=MUTED)
    legend = [Line2D([], [], marker='o', ls='', markerfacecolor='white', markeredgecolor=INK,
                     markersize=9, label='10 minutes'),
              Line2D([], [], marker='o', ls='', color=INK, markersize=9, label='30 minutes')]
    fig.legend(handles=legend, loc='upper left', bbox_to_anchor=(.033, .865), ncol=2, frameon=False)
    ax.set_xscale('log')
    ax.set_xlim(.065, 49)
    ax.set_ylim(15, 57)
    ax.set_xticks([.1, .25, .5, 1, 2, 5, 10, 25])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:g}'))
    ax.tick_params(which='minor', bottom=False)
    ax.set_yticks([20, 30, 40, 50])
    ax.grid(True, color='#e3e9ed', linewidth=.8)
    ax.set_axisbelow(True)
    ax.set_ylabel('Mean eval score (0–100)', labelpad=10)
    ax.set_xlabel('Mean cost per run · USD, log scale', labelpad=13)
    # Label only the 30-minute endpoints; model colors and lines identify the 10-minute points.
    offsets = {'gpt-6-astra': (-18, 25), 'meta/muse-wonder': (10, 0),
               'moonshotai/kimi-k3.1-pro': (12, 8), 'gpt-6.1-sol': (-8, 18),
               'x-ai/grok-4.7': (12, -5), 'claude-sonnet-5-5': (-5, 15),
               'claude-opus-5': (12, -14), 'z-ai/glm-5.3': (-6, -20),
               'deepseek/deepseek-v4.1-flash-1017': (-8, 18),
               'gpt-6-luna': (12, -3), 'claude-haiku-5-5': (12, -3)}
    for m in models:
        a, b = by_key[m['model'], 10], by_key[m['model'], 30]
        c = colors[m['model']]
        ax.plot([a['cost_usd'],b['cost_usd']], [a['score'],b['score']], c=c, alpha=.4, lw=1.5)
        ax.scatter(a['cost_usd'], a['score'], s=78, facecolors='white', edgecolors=c, linewidths=2, zorder=4)
        ax.scatter(b['cost_usd'], b['score'], s=90, c=c, edgecolors='white', linewidths=.8, zorder=5)
        dx, dy = offsets[m['model']]
        ax.annotate(m['label'], (b['cost_usd'],b['score']), xytext=(dx,dy), textcoords='offset points',
                    fontsize=10, color=c, weight='bold', ha='left' if dx >= 0 else 'right', va='center',
                    arrowprops={'arrowstyle':'-', 'color':c, 'lw':.6, 'alpha':.65}, zorder=6)
    fig.text(.04, .12, 'Cost: recorded ReAct API spend; Claude Code API-equivalent cost; Codex token-based estimate. Subscription cash spend is not shown.', fontsize=9, color=MUTED)
    fig.text(.04, .075, 'Mean cost includes all attempts and excludes grading. Scores retain the existing report exclusions. Different model scaffolds remain confounded.', fontsize=9, color=MUTED)
    fig.text(.04, .035, 'An equal-weight average of three rubric scores, not accuracy. Five trials per eval and budget; judge: GPT-6.1 Sol, high effort.', fontsize=9, color=MUTED)
    save(fig, 'performance-vs-cost')

    fig, ax = plt.subplots(figsize=(13, 10.5))
    fig.subplots_adjust(left=.24, right=.96, top=.79, bottom=.19)
    fig.text(.04, .95, 'The average, and the three evals behind it', fontsize=23, weight='bold')
    fig.text(.04, .905, 'One row per model. Large diamonds are the equal-eval mean; small shapes are the individual eval means.', fontsize=11, color=MUTED)
    handles = [Line2D([],[],marker='D',color=INK,ls='',markersize=8,label='Overall mean')]
    handles += [Line2D([],[],marker=mark,color=MUTED,ls='',markersize=6,label=name) for mark,name in zip(MARKERS,NAMES)]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.033,.875), frameon=False, ncol=4, fontsize=10)
    ax.set_xlim(0, 85)
    ax.set_ylim(len(models)-.45, -.65)
    ax.set_xticks(range(0, 81, 10))
    ax.set_yticks([])
    ax.grid(axis='x', color='#e3e9ed', linewidth=.8)
    ax.set_axisbelow(True)
    ax.set_xlabel('Eval score (0–100)', labelpad=12)
    for i,m in enumerate(models):
        c=colors[m['model']]
        ax.text(-.04, i, m['label'], transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=10.5, color=c, weight='bold')
        ax.axhline(i+.5, color='#eff2f4', lw=.7)
        for budget, shift in [(10,-.22),(30,.22)]:
            r = by_key[m['model'], budget]
            y = i + shift
            ax.text(-.008,y,str(budget),transform=ax.get_yaxis_transform(),ha='right',va='center',fontsize=7.5,color=MUTED)
            xs=[r['evals'][ev]['score'] for ev in EVALS]
            ax.plot([min(xs),max(xs)],[y+.10,y+.10],c='#dde3e8',lw=1,zorder=1)
            for x,mark in zip(xs,MARKERS):
                ax.scatter(x,y+.10,s=30,marker=mark,facecolors='white' if budget==10 else '#788995',
                           edgecolors='#788995',linewidths=1,zorder=3)
            ax.scatter(r['score'],y-.10,s=85,marker='D',facecolors='white' if budget==10 else c,
                       edgecolors=c,linewidths=1.7,zorder=4)
    fig.text(.04,.095,'Open marks / upper line: 10 minutes. Filled marks / lower line: 30 minutes. Models are ordered by their 30-minute overall mean.',fontsize=9,color=MUTED)
    fig.text(.04,.05,'Small points show eval averages, not individual trials or uncertainty. Report exclusions and scaffold differences are documented with the data.',fontsize=9,color=MUTED)
    save(fig, 'eval-breakdown')
    print('Wrote two figures in SVG, PNG and PDF, plus 22 model-budget summaries.')


if __name__ == '__main__':
    main()
