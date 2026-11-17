#!/usr/bin/env python3
"""Export verified standard runs and numeric grades without publishing report text.

The local archive contains original reports and raw judge responses. This exporter
checks their hashes and grading inputs, but publishes only allowlisted numeric fields.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL_IDS = {'german-wiki': 'messageboard', 'transluce': 'urlquery', 'aivillage': 'aivillage'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_reports(rows, count=5):
    """Choose by replicate, never score; retain excluded and surplus attempts."""
    groups = {}
    for row in rows:
        row['selected'] = False
        groups.setdefault((row['benchmark'], row['model'], row['budget']), []).append(row)
    for key, group in groups.items():
        reps = [r['replicate'] for r in group]
        if len(set(reps)) != len(reps):
            raise ValueError(f'Duplicate replicate: {key}')
        valid = sorted((r for r in group if r['eligible']), key=lambda r: (r['replicate'], r['run']))
        if len(valid) < count:
            raise ValueError(f'{key}: only {len(valid)}/{count} eligible reports')
        for row in valid[:count]:
            if row['score'] is None:
                raise ValueError(f"Missing grade: {row['run']}")
            row['selected'] = True
    return rows


def numeric_grade(grade):
    """Copy numeric judgments, fixed flags and provenance; no free-form judge text."""
    fields = ('judge', 'effort', 'rubric', 'prompt_sha256', 'findings_sha256',
              'source_sha256', 'article_sha256', 'report_sha256', 'n_scored', 'n_findings',
              'score', 'score_mean', 'score_mean_unweighted', 'top_k', 'score_top_k', 'headline_weights')
    out = {k: grade[k] for k in fields if k in grade}
    out['findings'] = {}
    for key, finding in grade['findings'].items():
        if finding['status'] != 'ok':
            raise ValueError(f'Unscored finding: {key}')
        score = finding['score']
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError(f'Invalid finding score: {key}')
        out['findings'][key] = {
            'score': score, 'contradicted': bool(finding.get('contradicted', False)),
            'sub_findings': [{k: sub[k] for k in ('id', 'score', 'contradicted')}
                             for sub in finding.get('sub_findings', [])],
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True, help='Primary checkout containing runs and raw grades')
    ap.add_argument('--output', type=Path, default=ROOT/'benchmarks/results/2026-11-17')
    args = ap.parse_args()
    from slopvestigator_bench import eligibility, standard
    from slopvestigator_bench.grading import answer_key_judge as akj, findings as fj

    initial = ROOT/'benchmarks/results/2026-11-16'
    provenance = json.loads((initial/'provenance.json').read_text())
    models = {m['id']: m for m in provenance['models']}
    rates = provenance['cost_method']['rates_usd_per_million']
    baseline = {r['run'] for r in map(json.loads, (initial/'runs.jsonl').read_text().splitlines())}
    found_baseline = set()
    rows, grades = [], {b: [] for b in EVAL_IDS}
    inputs = {}
    for bench, ev in EVAL_IDS.items():
        key = akj.load_key(bench)
        findings = akj.graded_findings(key)
        heads = [f['id'] for f in findings]
        weights = akj.headline_weights(findings)
        source = akj.source_text(bench, 'full' if bench == 'transluce' else None)
        stamp = akj.stamp(bench, 'codex/gpt-6.1-sol', 'high', source, key)
        inputs[bench] = stamp
        run_root = args.archive/'runs'/('urlquery' if bench == 'transluce' else '')
        grade_root = args.archive/'benchmarks'/bench/('reports/graded' if bench == 'transluce' else 'graded-answer-key')/'judge_codex_gpt_6_1_sol_high'
        for run in sorted(run_root.glob('*_r*_*std-*')):
            if not (run/'meta.json').is_file():
                continue
            meta = json.loads((run/'meta.json').read_text())
            model = meta.get('model')
            budget, rep = meta.get('budget_min'), meta.get('replicate', 0)
            if model not in models or budget not in (10,30) or not 1 <= rep < 90:
                continue
            if meta.get('agent', meta.get('harness')) != models[model]['harness']:
                continue
            if not standard.same_condition(meta, standard.config_name(ev, budget)):
                if run.name in baseline:
                    raise ValueError(f'Baseline condition changed: {run.name}')
                continue
            if 'exit_code' not in meta:
                raise ValueError(f'Run still in progress: {run.name}')
            if run.name in baseline:
                found_baseline.add(run.name)
            verdict = eligibility.check(run)
            usage_path = run/'usage.json'
            usage = json.loads(usage_path.read_text())
            tokens = {k: usage.get(k, 0) for k in ('input_tokens_uncached','cache_read_tokens','cache_write_tokens','output_tokens')}
            rate = rates[model]
            cost = usage.get('cost_usd')
            basis = 'recorded_api' if models[model]['harness'] == 'react' else 'cli_api_equivalent'
            if cost is None:
                cost = (tokens['input_tokens_uncached']*rate['input'] + tokens['cache_read_tokens']*.1*rate['input'] + tokens['cache_write_tokens']*rate['input'] + tokens['output_tokens']*rate['output'])/1e6
                basis = 'token_estimate'
            if not math.isfinite(cost) or cost < 0:
                raise ValueError(f'Invalid cost: {run.name}')
            row = dict(benchmark=bench, run=run.name, model=model, model_label=models[model]['label'],
                       agent=models[model]['harness'], budget=budget, replicate=rep,
                       eligible=verdict.eligible, exclusion_reasons=list(verdict.reasons),
                       report_exists=(run/'report.md').is_file(), score=None,
                       cost_usd=cost, cost_basis=basis, cost_inputs=tokens,
                       usage_sha256=digest(usage_path), meta_sha256=digest(run/'meta.json'))
            if row['report_exists']:
                report = (run/'report.md').read_text()
                grade_path = grade_root/(run.name+'.json')
                grade = json.loads(grade_path.read_text())
                for name, value in {**stamp, 'report_sha256': fj.sha(report)}.items():
                    if grade.get(name) != value:
                        raise ValueError(f'{run.name}: {name} mismatch')
                if grade.get('prompt_variables', {}) != akj.report_variables(bench, meta.get('data_variant')):
                    raise ValueError(f'{run.name}: prompt variables mismatch')
                recomputed = akj.summarize(bench, copy.deepcopy(grade), heads, weights, report)
                if recomputed['unscored'] or set(grade['findings']) != set(heads):
                    raise ValueError(f'{run.name}: incomplete grade')
                for name in ('score','score_mean','n_scored','n_findings','unscored'):
                    if recomputed.get(name) != grade.get(name):
                        raise ValueError(f'{run.name}: {name} mismatch')
                row.update(score=grade['score'], grade_sha256=digest(grade_path), report_sha256=fj.sha(report))
                grades[bench].append({'run': run.name, **numeric_grade(grade)})
            rows.append(row)
    if found_baseline != baseline:
        raise ValueError(f'Missing original attempts: {sorted(baseline-found_baseline)}')
    select_reports(rows)
    if len({(r['benchmark'], r['model'], r['budget']) for r in rows}) != 66:
        raise ValueError('Expected all 66 model/eval/budget cells')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'runs.jsonl').write_text(''.join(json.dumps(r, sort_keys=True)+'\n' for r in rows))
    selection = {'rule': 'First five eligible standard-condition reports by replicate number; no score-based selection. All attempts retained for cost.',
                 'runs': [r['run'] for r in rows if r['selected']]}
    (args.output/'selection.json').write_text(json.dumps(selection, indent=2)+'\n')
    for bench, values in grades.items():
        (args.output/f'{bench}-grades.jsonl').write_text(''.join(json.dumps(g, sort_keys=True)+'\n' for g in values))
    provenance.update(trials=len(rows), eligible=sum(r['eligible'] for r in rows),
                      selected=sum(r['selected'] for r in rows), missing_reports=sum(not r['report_exists'] for r in rows),
                      source='Original standard cohort plus completed supplementary standard runs',
                      scores='First five eligible standard-condition reports per cell; equal eval weights.', grading_inputs=inputs,
                      publication='Numeric grades omit report text, judge quotes, reasons and raw responses. Original hashes refer to the local archive.')
    provenance['cost_method']['aggregation'] = 'Mean attempted-run cost within each eval, then equal mean of the three evals; all failed and excluded attempts included.'
    (args.output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(f'Exported {len(rows)} attempts, {sum(r["selected"] for r in rows)} selected reports.')


if __name__ == '__main__':
    main()
