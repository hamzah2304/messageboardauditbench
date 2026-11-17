#!/usr/bin/env python3
"""Recompute the public results from numeric finding grades, without raw reports or API calls."""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(snapshot):
    from slopvestigator_bench.grading import answer_key_judge as akj

    rows = list(map(json.loads, (snapshot/'runs.jsonl').read_text().splitlines()))
    provenance = json.loads((snapshot/'provenance.json').read_text())
    selection = json.loads((snapshot/'selection.json').read_text())
    assert len(rows) == provenance['trials'] == len({r['run'] for r in rows})
    assert set(selection['runs']) == {r['run'] for r in rows if r['selected']}
    assert len(selection['runs']) == 330
    models = {m['id'] for m in provenance['models']}
    assert len(models) == 11
    expected_cells = {(m,b,e) for m in models for b in (10,30) for e in ('german-wiki','transluce','aivillage')}
    assert {(r['model'],r['budget'],r['benchmark']) for r in rows} == expected_cells
    row_keys = {'benchmark','run','model','model_label','agent','budget','replicate','eligible',
                'exclusion_reasons','report_exists','score','cost_usd','cost_basis','cost_inputs',
                'usage_sha256','meta_sha256','grade_sha256','report_sha256','selected'}
    grade_keys = {'run','judge','effort','rubric','prompt_sha256','findings_sha256','source_sha256',
                  'article_sha256','report_sha256','n_scored','n_findings','score','score_mean',
                  'score_mean_unweighted','top_k','score_top_k','headline_weights','findings'}
    for row in rows:
        assert set(row) <= row_keys
        assert math.isfinite(row['cost_usd']) and row['cost_usd'] >= 0
        assert row['cost_basis'] in {'recorded_api','cli_api_equivalent','token_estimate'}
        assert set(row['cost_inputs']) == {'input_tokens_uncached','cache_read_tokens','cache_write_tokens','output_tokens'}
        assert all(math.isfinite(v) and v >= 0 for v in row['cost_inputs'].values())
        if row['selected']:
            assert row['eligible'] and row['report_exists'] and math.isfinite(row['score']) and 0 <= row['score'] <= 1
        for k,v in row.items():
            if k.endswith('_sha256'):
                assert re.fullmatch('[0-9a-f]{64}',v)
    by_run = {r['run']:r for r in rows}
    for bench in ('german-wiki','transluce','aivillage'):
        key = akj.load_key(bench)
        findings = akj.graded_findings(key)
        heads = {f['id'] for f in findings}
        weights = akj.headline_weights(findings)
        # The Transluce article is an archived, untracked input. Check its recorded
        # fingerprint across grades without requiring that private archive in a clone.
        source = None if bench == 'transluce' else akj.source_text(bench)
        stamp = akj.stamp(bench, provenance['judge'], provenance['effort'], source, key)
        if bench == 'transluce':
            stamp['article_sha256'] = provenance['grading_inputs'][bench]['article_sha256']
        assert stamp == provenance['grading_inputs'][bench]
        grades = list(map(json.loads, (snapshot/provenance['grade_exports'][bench]).read_text().splitlines()))
        assert {g['run'] for g in grades} == {r['run'] for r in rows if r['benchmark']==bench and r['report_exists']}
        for grade in grades:
            assert set(grade) <= grade_keys
            assert grade['n_scored'] == grade['n_findings'] == len(heads)
            for k,v in grade.items():
                if k.endswith('_sha256'):
                    assert re.fullmatch('[0-9a-f]{64}',v)
            row = by_run[grade['run']]
            assert all(grade[k] == v for k,v in stamp.items())
            assert row['report_sha256'] == grade['report_sha256']
            assert set(grade['findings']) == heads
            assert grade['headline_weights'] == weights
            for finding in findings:
                f = grade['findings'][finding['id']]
                assert set(f) == {'score','contradicted','sub_findings'}
                assert math.isfinite(f['score']) and 0 <= f['score'] <= 1
                subs = f['sub_findings']
                assert len(subs) == len(finding['subfindings'])
                assert {s['id'] for s in subs} == {s['id'] for s in finding['subfindings']}
                assert all(set(s)=={'id','score','contradicted'} and math.isfinite(s['score']) and 0 <= s['score'] <= 1 for s in subs)
            scores = {h:f['score'] for h,f in grade['findings'].items()}
            if bench == 'aivillage':
                score = round(sum(sorted(scores.values(),reverse=True)[:20])/20,3)
            else:
                score = round(sum(v*weights.get(h,1) for h,v in scores.items())/sum(weights.get(h,1) for h in scores),3)
            assert score == grade['score'] == row['score'], row['run']
    summary = json.loads((snapshot/'summary.json').read_text())
    assert len(summary) == 22
    assert {(s['model'],s['budget']) for s in summary} == {(m,b) for m in models for b in (10,30)}
    for item in summary:
        means, costs = [], []
        for bench in ('german-wiki','transluce','aivillage'):
            attempts = [r for r in rows if (r['model'],r['budget'],r['benchmark'])==(item['model'],item['budget'],bench)]
            eligible = sorted((r for r in attempts if r['eligible']),key=lambda r:r['replicate'])
            selected = [r for r in attempts if r['selected']]
            assert len(selected)==5 and {r['run'] for r in selected} == {r['run'] for r in eligible[:5]}
            assert len({r['replicate'] for r in attempts})==len(attempts)
            score = statistics.fmean(r['score']*100 for r in selected)
            cost = statistics.fmean(r['cost_usd'] for r in attempts)
            assert math.isclose(score,item['evals'][bench]['score'],abs_tol=1e-10)
            assert math.isclose(cost,item['evals'][bench]['cost_usd'],abs_tol=1e-10)
            means.append(score)
            costs.append(cost)
        assert math.isclose(statistics.fmean(means),item['score'],abs_tol=1e-10)
        assert math.isclose(statistics.fmean(costs),item['cost_usd'],abs_tol=1e-10)
    print(f'Verified {len(rows)} attempted runs, 330 selected reports, all finding scores and 22 model/budget means.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot',type=Path,default=ROOT/'benchmarks/results/2026-11-17')
    verify(ap.parse_args().snapshot)
