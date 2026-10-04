import importlib.util
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('grade_aivillage', Path(__file__).parents[1] / 'scripts/grade_aivillage.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def finding(fid='f1', goal='a'):
    return {'id': fid, 'headline': 'Incorrect completion claim', 'finding': 'Reported completion without executing it.', 'goal_period_id': goal, 'subfindings': [{'id': fid + '.1', 'claim': 'The task did not run.', 'decision': 'keep', 'source_support': [{'quote': 'only this excerpt', 'url': 'https://example.com/' + fid, 'body_html': 'unrelated entire source'}]}]}


def judgement(job):
    return {'findings': [{'finding_id': f['id'], 'score': 0.8, 'contradicted': False, 'quote': 'did not run', 'reason': 'Covers the failure.', 'sub_findings': [{'id': s['id'], 'score': 0.75, 'contradicted': False, 'quote': 'did not run', 'reason': 'Covers the event.'} for s in f['subfindings']]} for f in job['findings']]}


def job(fid='f1'):
    fs, _ = g.normalize_findings([finding(fid)])
    req = {'model': g.MODEL, 'reasoning': {'effort': 'medium'}, 'input': 'did not run', 'instructions': 'score', 'max_output_tokens': 4000}
    return {'id': g.digest({'request': req, 'fid': fid}), 'findings': fs, 'report': 'The task did not run.', 'report_id': 'r', 'request': req}


class Client:
    def __init__(self, model=g.MODEL):
        self.model = model
        self.calls = 0
        self.with_raw_response = self
        self.responses = self
        self.current_job = None

    def with_options(self, **kwargs):
        return self

    def create(self, **kwargs):
        self.calls += 1
        body = {'model': self.model, 'status': 'completed', 'reasoning': {'effort': 'medium'}, 'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}}
        response = SimpleNamespace(model=self.model, status='completed', id='response', output_text=json.dumps(judgement(self.current_job)), model_dump=lambda **kwargs: body)
        return SimpleNamespace(parse=lambda: response, headers={'x-ratelimit-limit-tokens': '1000000', 'authorization': 'never-save'})


def test_sources_are_scoped_and_pending_subfindings_excluded():
    f = finding()
    f['sources'] = [{'id': 's1', 'source': {'url': 'https://example.com/f1', 'body_html': 'do not dump this'}}]
    f['subfindings'].append({'id': 'f1.2', 'claim': 'not approved', 'decision': 'drop_screenshot'})
    fs, excluded = g.normalize_findings([f, {**finding('f2'), 'group': 'rewrite'}])
    assert len(fs) == 1 and len(fs[0]['subfindings']) == 1
    assert 'unrelated entire source' not in json.dumps(fs)
    assert 'do not dump this' not in json.dumps(fs)
    assert excluded == [{'id': 'f2', 'reason': 'rewrite'}]


def test_groups_never_mix_goal_periods_and_limit_subfindings():
    fs, _ = g.normalize_findings([finding('f1', 'a'), finding('f2', 'b'), finding('f3', 'a')])
    groups = g.group_findings(fs, [], {}, 3, 12)
    assert [len(x['findings']) for x in groups] == [2, 1]
    assert len(g.group_findings(fs, [], {}, 3, 1)) == 3
    assert all(len({f['goal_period_id'] for f in x['findings']}) == 1 for x in groups)


def test_boundary_dates_and_multiperiod_episodes_stay_separate():
    goals = [{'id': 'a', 'start_time': '2026-01-01', 'end_time': '2026-01-10'}, {'id': 'b', 'start_time': '2026-01-10', 'end_time': '2026-01-20'}]
    f = {'id': 'f', 'behavior_dates': '2026-01-10'}
    assert g.period(f, goals, {}) == 'single:f'
    f['behavior_dates'] = '2026-01-05 to 2026-01-15'
    assert g.period(f, goals, {}) == 'single:f'


def test_cached_scores_reused_without_another_api_call(tmp_path):
    j = job()
    client = Client()
    client.current_job = j
    deadline = time.monotonic() + 10
    status, result = g.perform(client, j, tmp_path, g.Gate(), deadline)
    assert status == 'complete'
    assert result['effort'] == 'medium'
    assert g.perform(client, j, tmp_path, g.Gate(), deadline)[0] == 'cached'
    assert client.calls == 1
    headers = g.read(tmp_path / 'jobs' / j['id'] / 'headers-1.json')
    assert 'authorization' not in headers


def test_model_fallback_is_rejected_and_never_cached(tmp_path):
    j = job()
    client = Client(model='another-model')
    client.current_job = j
    with pytest.raises(ValueError, match='model differs'):
        g.perform(client, j, tmp_path, g.Gate(), time.monotonic() + 10)
    assert not (tmp_path / 'jobs' / j['id'] / 'result.json').exists()


def test_missing_or_duplicate_ids_are_rejected():
    j = job()
    value = judgement(j)
    value['findings'][0]['sub_findings'].append(value['findings'][0]['sub_findings'][0].copy())
    with pytest.raises(ValueError, match='subfinding IDs'):
        g.validate(value, j)


def test_unmatched_quote_warns_without_changing_content_score():
    j = job()
    value = judgement(j)
    value['findings'][0]['quote'] = 'absent quotation'
    checked = g.validate(value, j)
    assert checked['findings'][0]['score'] == 0.8
    assert checked['findings'][0]['quote_verified'] is False


def test_partial_run_has_no_overall_report_score(tmp_path):
    j = job()
    plan = {'jobs': [j], 'findings': j['findings'], 'reports': [{'id': 'r'}]}
    summary = g.aggregate(plan, tmp_path)
    assert summary['reports'][0]['mean_coverage'] is None
    assert summary['reports'][0]['missing_findings'] == ['f1']


def test_deadline_prevents_new_requests(tmp_path):
    j = job()
    client = Client()
    with pytest.raises(TimeoutError):
        g.perform(client, j, tmp_path, g.Gate(), time.monotonic() - 1)
    assert client.calls == 0


def test_changed_evidence_changes_only_its_group_request(tmp_path):
    report = tmp_path / 'report.md'
    report.write_text('The task did not run.')
    manifests = tmp_path / 'reports.json'
    manifests.write_text(json.dumps([{'id': 'r', 'path': str(report), 'reasoning_available': True}]))
    findings_path = tmp_path / 'findings.json'
    findings_path.write_text(json.dumps([finding('f1', 'a'), finding('f2', 'b')]))
    rubric = tmp_path / 'rubric.txt'
    rubric.write_text('Judge against one finding. {{REASONING_CONDITION}}\nAnswer format\nJSON')
    args = SimpleNamespace(expected_findings=None, findings=findings_path, reports=manifests, goals=None, goal_map=None, group_size=3, max_subfindings=12, rubric=rubric, concurrency=32, output=tmp_path / 'output')
    first = g.read(g.prepare(args))
    raw = g.read(findings_path)
    raw[0]['subfindings'][0]['source_support'][0]['quote'] = 'changed relevant excerpt'
    findings_path.write_text(json.dumps(raw))
    second = g.read(g.prepare(args))
    a = {j['goal_period']: j['id'] for j in first['jobs']}
    b = {j['goal_period']: j['id'] for j in second['jobs']}
    assert a['a'] != b['a'] and a['b'] == b['b']
    assert first['concurrency'] == 32
    assert all(j['request']['reasoning']['effort'] == 'medium' for j in second['jobs'])


def test_gate_supports_32_simultaneous_workers():
    active = peak = 0
    lock = threading.Lock()
    barrier = threading.Barrier(32)
    gate = g.Gate()
    def one(_):
        nonlocal active, peak
        gate.enter(job()['request'], time.monotonic() + 5)
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(one, range(32)))
    assert peak == 32


def test_final_rewrites_use_corrected_claims():
    f = finding()
    f.update(group="rewrite", original_finding="old unsupported wording", decided_by="reviewer")
    f['subfindings'][0].update(decision="rewrite", claim="corrected claim", original_claim="old claim")
    fs, excluded = g.normalize_findings([f])
    assert not excluded and fs[0]['subfindings'][0]['claim'] == 'corrected claim'


def test_credit_exhaustion_stops_all_future_api_attempts(tmp_path):
    class EmptyCreditClient(Client):
        def create(self, **kwargs):
            self.calls += 1
            exc = RuntimeError("billing block")
            exc.status_code = 429
            exc.code = "credit_balance_exhausted"
            raise exc
    gate = g.Gate()
    client = EmptyCreditClient()
    with pytest.raises(g.AccountBlocked, match="credit_balance_exhausted"):
        g.perform(client, job(), tmp_path, gate, time.monotonic() + 10)
    with pytest.raises(g.AccountBlocked):
        g.perform(client, job('f2'), tmp_path, gate, time.monotonic() + 10)
    assert client.calls == 1
