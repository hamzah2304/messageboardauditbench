"""Publication selection is score-independent and never exports judge free text."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('export_eval_results', Path(__file__).parents[1]/'scripts/export_eval_results.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_selection_keeps_failed_attempts_and_ignores_score():
    rows = [dict(benchmark='wiki', model='test', budget=30, replicate=i, run=str(i),
                 eligible=i != 1, score=.1 if i < 7 else 1., cost_usd=i) for i in range(1,8)]
    export.select_reports(rows)
    assert [r['replicate'] for r in rows if r['selected']] == [2,3,4,5,6]
    assert len(rows) == 7
    assert sum(r['cost_usd'] for r in rows) == 28


def test_selection_rejects_missing_or_duplicate_reports():
    row = dict(benchmark='wiki', model='test', budget=30, replicate=1, run='one', eligible=True, score=.5)
    with pytest.raises(ValueError, match='only 1/5'):
        export.select_reports([row])
    with pytest.raises(ValueError, match='Duplicate replicate'):
        export.select_reports([row.copy(), row.copy()])


def test_numeric_export_drops_all_free_text():
    grade = {'judge': 'codex/test', 'score': .5, 'raw': 'private raw response', 'run': '/private/path',
             'findings': {'F1': {'status':'ok', 'score': .5, 'contradicted':False, 'quote':'private quote',
                                 'reason':'private reason', 'usage':{'token':'private token'},
                                 'sub_findings':[{'id':'F1a','score':.25,'contradicted':False,'quote':'private sub quote'}]}}}
    result = export.numeric_grade(grade)
    assert result == {'judge':'codex/test', 'score':.5, 'findings':{'F1':{'score':.5,'contradicted':False,
                      'sub_findings':[{'id':'F1a','score':.25,'contradicted':False}]}}}
    grade['findings']['F1']['status'] = 'error'
    with pytest.raises(ValueError, match='Unscored'):
        export.numeric_grade(grade)


def test_public_verifier_rejects_extra_text_and_duplicate_summary(tmp_path, monkeypatch):
    import json

    from slopvestigator_bench.grading import answer_key_judge as akj

    spec = importlib.util.spec_from_file_location('verify_eval_results', Path(__file__).parents[1]/'scripts/verify_eval_results.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    stamp = {'judge':'test','effort':'high','rubric':'answer-key','prompt_sha256':'0'*64,'findings_sha256':'0'*64}
    findings = [{'id':f'F{i}','subfindings':[]} for i in range(20)]
    monkeypatch.setattr(akj,'load_key',lambda _: {})
    monkeypatch.setattr(akj,'graded_findings',lambda _:findings)
    monkeypatch.setattr(akj,'headline_weights',lambda _: {})
    monkeypatch.setattr(akj,'source_text',lambda *_:None)
    monkeypatch.setattr(akj,'stamp',lambda *_:dict(stamp))
    models = [f'model-{i}' for i in range(11)]
    evals = ('german-wiki','transluce','aivillage')
    rows, summary = [], []
    for model in models:
        for budget in (10,30):
            summary.append({'model':model,'budget':budget,'score':50.,'cost_usd':1.,
                            'evals':{e:{'score':50.,'cost_usd':1.} for e in evals}})
            for bench in evals:
                for rep in range(1,6):
                    rows.append({'run':f'{model}-{budget}-{bench}-{rep}','model':model,'budget':budget,
                                 'benchmark':bench,'replicate':rep,'eligible':True,'selected':True,
                                 'report_exists':True,'score':.5,'report_sha256':'0'*64,'cost_usd':1.,
                                 'cost_basis':'recorded_api','cost_inputs':dict.fromkeys(
                                     ('input_tokens_uncached','cache_read_tokens','cache_write_tokens','output_tokens'),0)})
    (tmp_path/'runs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (tmp_path/'selection.json').write_text(json.dumps({'runs':[r['run'] for r in rows]}))
    (tmp_path/'provenance.json').write_text(json.dumps({'trials':330,'models':[{'id':m} for m in models],
                                                     'grade_exports':{e:f'{e}-grades.jsonl' for e in evals},
                                                     'judge':'test','effort':'high','grading_inputs':{e:({**stamp, 'article_sha256':'0'*64} if e=='transluce' else stamp) for e in evals}}))
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    for bench in evals:
        bench_stamp = {**stamp, 'article_sha256':'0'*64} if bench=='transluce' else stamp
        grades = [{**bench_stamp,'run':r['run'],'report_sha256':'0'*64,'n_scored':20,'n_findings':20,
                   'headline_weights':{},'score':.5,'findings':{
                       f['id']:{'score':.5,'contradicted':False,'sub_findings':[]} for f in findings}}
                  for r in rows if r['benchmark']==bench]
        (tmp_path/f'{bench}-grades.jsonl').write_text(''.join(json.dumps(g)+'\n' for g in grades))
    verifier.verify(tmp_path)
    path = tmp_path/'german-wiki-grades.jsonl'
    original = path.read_text()
    grades = list(map(json.loads,original.splitlines()))
    grades[0]['raw'] = 'private judge output'
    path.write_text(''.join(json.dumps(g)+'\n' for g in grades))
    with pytest.raises(AssertionError):
        verifier.verify(tmp_path)
    path.write_text(original)
    summary[0] = summary[1]
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(AssertionError):
        verifier.verify(tmp_path)
