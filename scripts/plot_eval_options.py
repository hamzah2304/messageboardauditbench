# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.11.2", "numpy==2.5.5"]
# ///
"""Render three alternatives from the frozen, current-answer-key result snapshot.

Run: uv run scripts/plot_eval_options.py
The snapshot retains excluded trials; plots average eligible reports only.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/results/2026-11-16'
OUT = ROOT / 'docs/figures/eval-options'
BENCHES = ['german-wiki', 'transluce', 'aivillage']
TITLES = ['German wiki', 'Transluce', 'AI Village']
COLORS = {'codex': '#2563a6', 'claude': '#b76b36', 'react': '#237b65'}
HARNESS = {'codex': 'Codex', 'claude': 'Claude Code', 'react': 'ReAct'}
INK = '#172b3b'
GRAY = '#607180'


def load():
    rows = [json.loads(s) for s in (DATA / 'runs.jsonl').read_text().splitlines()]
    meta = json.loads((DATA / 'provenance.json').read_text())
    models = sorted(meta['models'], key=lambda m: ['codex', 'claude', 'react'].index(m['harness']))
    assert len(rows) == 330
    assert len({(r['benchmark'], r['model'], r['budget'], r['replicate']) for r in rows}) == 330
    for r in rows:
        assert r['score'] is None or 0 <= r['score'] <= 1
        assert not r['eligible'] or r['score'] is not None
    cells = {}
    for bench in BENCHES:
        for m in models:
            for budget in (10, 30):
                group = [r for r in rows if (r['benchmark'], r['model'], r['budget']) == (bench, m['id'], budget)]
                assert len(group) == 5
                values = [r['score'] * 100 for r in group if r['eligible']]
                cells[bench, m['id'], budget] = (np.array(values), np.mean(values))
    return models, cells


def setup():
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'text.color': INK,
                         'axes.labelcolor': GRAY, 'xtick.color': GRAY, 'ytick.color': INK,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.spines.left': False, 'axes.spines.bottom': False,
                         'svg.fonttype': 'none', 'pdf.fonttype': 42, 'savefig.facecolor': 'white'})


def frame(title, subtitle, models):
    fig, axes = plt.subplots(1, 3, figsize=(17.5, 9), sharey=True)
    fig.subplots_adjust(left=.19, right=.90, top=.78, bottom=.22, wspace=.36)
    fig.text(.035, .95, title, fontsize=22, weight='bold')
    fig.text(.035, .90, subtitle, fontsize=11, color=GRAY)
    for ax, title in zip(axes, TITLES):
        ax.set_title(title, loc='left', fontsize=15, weight='bold', pad=18)
        ax.set_ylim(len(models)-.5, -.5)
        ax.set_yticks([])
        ax.tick_params(axis='y', length=0, pad=12)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.xaxis.grid(True, color='#e4e9ed', linewidth=.7)
        ax.set_axisbelow(True)
        ax.set_xlabel('Answer-key score (0–100)', labelpad=11)
        for y in [2.5, 5.5]:
            ax.axhline(y, color='#d4dde3', linewidth=.8)
    for y, m in enumerate(models):
        fig.text(.175, .78 - (y+.5)*(.78-.22)/len(models), m['label'],
                 ha='right', va='center', fontsize=10.5)
    handles = [Line2D([], [], marker='s', ls='', color=COLORS[h], label=HARNESS[h], markersize=7)
               for h in ['codex', 'claude', 'react']]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.03, .875), frameon=False,
               ncol=3, fontsize=10)
    return fig, axes


def footer(fig, extra):
    fig.text(.035, .12, extra, fontsize=10, color=GRAY)
    fig.text(.035, .075, 'Means use eligible reports only. Models use their listed scaffold; model and scaffold effects are not separated.', fontsize=9, color=GRAY)
    fig.text(.035, .035, 'Judge: GPT-6.1 Sol · high effort · answer-key rubric. Scores have different meanings across benchmarks; compare models within a panel.', fontsize=9, color=GRAY)


def save(fig, name, stage):
    folder = OUT / stage
    folder.mkdir(parents=True, exist_ok=True)
    for ext in ['svg', 'png', 'pdf']:
        fig.savefig(folder / f'{name}.{ext}', dpi=170, metadata={'Creator': 'plot_eval_options.py'})
    svg = folder / f'{name}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)


def render(stage):
    setup()
    models, cells = load()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ['runs.jsonl', 'provenance.json']:
        shutil.copyfile(DATA / name, OUT / name)
    fig, axes = frame('How do models compare after 30 minutes?',
                      '30-minute runs · Small dots show individual eligible runs; diamonds show the mean. No confidence interval is implied.', models)
    for ax, bench in zip(axes, BENCHES):
        for y, m in enumerate(models):
            values, mean = cells[bench, m['id'], 30]
            c = COLORS[m['harness']]
            ax.scatter(values, y + np.linspace(-.13, .13, len(values)), s=23, alpha=.55, c=c, zorder=3)
            ax.scatter([mean], [y], s=75, marker='D', c=c, edgecolors='white', linewidths=.8, zorder=4)
            ax.text(104, y, f'{len(values)}/5' + (' *' if len(values) < 5 else ''), va='center',
                    fontsize=9, color='#9a4b20' if len(values) < 5 else GRAY,
                    weight='bold' if len(values) < 5 else 'normal')
        ax.text(104, -.80, 'Eligible', fontsize=8, color=GRAY)
    footer(fig, '* Fewer than five eligible runs. Opus 5 on German wiki uses only 2/5 runs; the other three are excluded. All exclusions remain in the data.')
    save(fig, '01-runs', stage)

    fig, axes = frame('The complete evaluation at a glance',
                      'Mean score above; eligible runs out of five below. Compare models within each benchmark. This view does not show run-to-run variation.', models)
    cmap = LinearSegmentedColormap.from_list('scores', ['#f3f7f8', '#b5d9d8', '#458b96', '#123e5b'])
    for ax, bench in zip(axes, BENCHES):
        values = np.array([[cells[bench, m['id'], b][1] for b in [10, 30]] for m in models])
        ax.grid(False)
        ax.imshow(values, cmap=cmap, vmin=0, vmax=100, aspect='auto', extent=(-.5, 1.5, len(models)-.5, -.5))
        ax.set_xlim(-.5, 1.5)
        ax.set_xticks([0, 1], ['10 min', '30 min'])
        ax.set_xlabel('Time budget', labelpad=11)
        for y, m in enumerate(models):
            for x, budget in enumerate([10, 30]):
                v, mean = cells[bench, m['id'], budget]
                ax.text(x, y-.09, f'{mean:.1f}', ha='center', va='center', weight='bold', fontsize=12, color='white' if mean > 58 else INK)
                ax.text(x, y+.24, f'{len(v)}/5' + (' *' if len(v) < 5 else ''), ha='center', va='center', fontsize=9, color='white' if mean > 58 else GRAY)
                if len(v) < 5:
                    ax.add_patch(Rectangle((x-.46,y-.45),.92,.9,fill=False,
                                           edgecolor='#694024',linewidth=1.5,linestyle='--'))
        ax.set_yticks(np.arange(-.5, len(models), 1), minor=True)
        ax.grid(which='minor', axis='y', color='white', linewidth=2)
        ax.axvline(.5, color='white', linewidth=3)
    footer(fig, '* Dashed outline: fewer than five eligible runs. Color runs from 0 to 100 in every panel; different rubrics prevent cross-benchmark ranking.')
    save(fig, '02-heatmap', stage)

    fig, axes = frame('What changes with a longer time budget?',
                      '○ 10-minute mean   ◆ 30-minute mean · Separate run groups, not paired trials. Changes are descriptive; no significance test is shown.', models)
    for ax, bench in zip(axes, BENCHES):
        for y, m in enumerate(models):
            va, a = cells[bench, m['id'], 10]
            vb, b = cells[bench, m['id'], 30]
            c = COLORS[m['harness']]
            ax.plot([a,b], [y-.06,y+.06], color=c, lw=1.2, alpha=.5)
            ax.scatter([a],[y-.06], s=52, facecolors='white', edgecolors=c, linewidths=1.5, zorder=3)
            ax.scatter([b],[y+.06], s=46, marker='D', c=c, zorder=4)
            ax.text(102, y, f'{b-a:+.1f}', va='center', fontsize=8.5, color=GRAY)
            ax.text(124, y, f'{len(va)}→{len(vb)}' + ('*' if min(len(va),len(vb)) < 5 else ''),
                    va='center', fontsize=8.5, color='#9a4b20' if min(len(va),len(vb)) < 5 else GRAY)
        ax.text(102, -.80, 'Δ points', fontsize=8, color=GRAY)
        ax.text(124, -.80, 'n₁₀→n₃₀', fontsize=8, color=GRAY)
    footer(fig, 'Δ = 30-minute mean − 10-minute mean; 0 means no change in the averages. n = eligible runs (out of five at each budget); * flags exclusions.')
    save(fig, '03-time', stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['draft', 'refined'], default='refined')
    render(parser.parse_args().stage)
