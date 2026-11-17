# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.11.2", "numpy==2.5.5"]
# ///
"""Plot equal-eval performance against run cost, plus a compact eval breakdown.

Run with `uv run scripts/plot_eval_results.py`. Reads the frozen trial snapshot;
the selection manifest chooses the first five eligible reports, while cost includes all attempts.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/results/2026-11-17'
OUT = ROOT / 'docs/figures/results'
EVALS = ['german-wiki', 'transluce', 'aivillage']
NAMES = ['German wiki', 'Transluce', 'AI Village']
INK, MUTED = '#172b3b', '#5c6c78'



def aggregate(rows):
    out = []
    for model in sorted({r['model'] for r in rows}):
        for budget in (10, 30):
            group = [r for r in rows if r['model'] == model and r['budget'] == budget]
            evals = {}
            for ev in EVALS:
                rs = [r for r in group if r['benchmark'] == ev]
                assert len(rs) >= 5
                valid = [r['score'] * 100 for r in rs if r['selected']]
                assert 1 <= len(valid) <= 5
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
    assert len(rows) >= 330 and len({r['run'] for r in rows}) == len(rows)
    assert all(r['cost_usd'] >= 0 for r in rows)
    summary = aggregate(rows)
    models = sorted([r for r in summary if r['budget'] == 30], key=lambda x: -x['score'])
    provenance = json.loads((DATA / 'provenance.json').read_text())
    colors = {m['id']: m['color'] for m in provenance['models']}
    by_key = {(r['model'], r['budget']): r for r in summary}
    initial = json.loads((ROOT / 'benchmarks/results/2026-11-16/summary.json').read_text())
    label_anchors = {r['model']: r for r in initial if r['budget'] == 30}
    OUT.mkdir(parents=True, exist_ok=True)
    (DATA/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')

    approved = {'model-label-gpt-6-astra': {'dx': 2.2799316164212087, 'dy': -11.699189914365206}, 'model-label-meta-muse-wonder': {'dx': 3.280309774646639, 'dy': -26.4576758242342}, 'model-label-moonshotai-kimi-k3-1-pro': {'dx': 75.88042814703704, 'dy': 5.185099581733283}, 'model-label-gpt-6-1-sol': {'dx': 0, 'dy': 0}, 'model-label-x-ai-grok-4-7': {'dx': 67.36267342191297, 'dy': 4.007328784985106}, 'model-label-claude-sonnet-5-5': {'dx': 0, 'dy': -16.19507547429771}, 'model-label-claude-opus-5': {'dx': 18.50990400321507, 'dy': -1.0498154509285769}, 'model-label-deepseek-deepseek-v4-1-flash-1017': {'dx': 5.019339247376081, 'dy': -33.91107471822329}, 'model-label-z-ai-glm-5-3': {'dx': 13.129963326711163, 'dy': 0.18611686664655736}, 'model-label-gpt-6-luna': {'dx': 0, 'dy': 0}, 'model-label-claude-haiku-5-5': {'dx': 0, 'dy': 0}}
    fig, ax = plt.subplots(figsize=(14, 8.8))
    fig.subplots_adjust(left=.09, right=.96, top=.77, bottom=.23)
    fig.text(.04, .945, 'Performance across three evals, at what cost?', fontsize=24, weight='bold')
    fig.text(.04, .895, 'Mean across German wiki, Transluce and AI Village.', fontsize=11, color=MUTED)
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
        anchor = 'left' if dx >= 0 else 'right'
        label_id = m['model'].replace('/', '-').replace('.', '-')
        shift = approved['model-label-' + label_id]
        dx += shift['dx']
        dy -= shift['dy']
        # Preserve the approved page positions when supplemental runs move the data points.
        old = label_anchors[m['model']]
        x, y = ax.transData.transform((old['cost_usd'], old['score']))
        text_position = ax.transData.inverted().transform((x+dx*fig.dpi/72, y+dy*fig.dpi/72))
        annotation = ax.annotate(m['label'], (b['cost_usd'],b['score']), xytext=text_position, textcoords='data',
                    fontsize=10, color=c, weight='bold', ha=anchor, va='center',
                    arrowprops={'arrowstyle':'-', 'color':c, 'lw':.6, 'alpha':.65}, zorder=6)
        label_id = m['model'].replace('/', '-').replace('.', '-')
        annotation.set_gid('model-label-' + label_id)
        annotation.arrow_patch.set_gid('model-leader-' + label_id)
    save(fig, 'performance-vs-cost')

    # Restore the original option 1: individual 30-minute runs and their mean,
    # with one panel per eval. Counts remain in the downloadable data.
    order = sorted(provenance['models'], key=lambda m: ['codex', 'claude', 'react'].index(m['harness']))
    fig, axes = plt.subplots(1, 3, figsize=(16, 8.5), sharey=True)
    fig.subplots_adjust(left=.205, right=.97, top=.77, bottom=.20, wspace=.14)
    fig.text(.035, .945, 'How do models compare after 30 minutes?', fontsize=23, weight='bold')
    fig.text(.035, .89, 'Small dots: individual runs · Diamonds: mean', fontsize=11, color=MUTED)
    for ax, ev, name in zip(axes, EVALS, NAMES):
        ax.set_title(name, loc='left', fontsize=15, weight='bold', pad=16)
        ax.set_xlim(0, 100)
        ax.set_ylim(len(order)-.5, -.5)
        ax.set_yticks([])
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.grid(axis='x', color='#e3e9ed', linewidth=.8)
        ax.set_axisbelow(True)
        ax.set_xlabel('Eval score (0–100)', labelpad=12)
        for boundary in [2.5, 5.5]:
            ax.axhline(boundary, color='#d7dfe5', lw=.8)
        for i, m in enumerate(order):
            values = [r['score']*100 for r in rows if r['model']==m['id'] and r['benchmark']==ev and r['budget']==30 and r['selected']]
            jitter = [0] if len(values)==1 else [(.26*k/(len(values)-1))-.13 for k in range(len(values))]
            c = colors[m['id']]
            ax.scatter(values, [i+j for j in jitter], s=25, c=c, alpha=.48, zorder=3)
            ax.scatter(statistics.fmean(values), i, s=78, marker='D', c=c, edgecolors='white', linewidths=.8, zorder=4)
    for i, m in enumerate(order):
        fig.text(.19, .77-(i+.5)*(.77-.20)/len(order), m['label'], ha='right', va='center', fontsize=10.5, color=colors[m['id']])
    save(fig, 'eval-breakdown')
    print('Wrote two figures in SVG, PNG and PDF, plus 22 model-budget summaries.')


if __name__ == '__main__':
    main()
