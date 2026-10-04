"""Discord findings extraction over every screened conversation, with the
request of the 10-conversation run except medium reasoning effort (runs/discord-extraction-failures-20261004).

    uv run --no-project --with openai --with python-dotenv python run.py [status]

Resumes from this folder: a saved <packet>.json is never paid for again, and a
saved completed raw response is parsed instead of re-requested. Failed packets
are rows in failures.jsonl, not crashes. No new call starts once spend passes
CEILING_USD.
"""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CEILING_USD = 80.0
WORKERS = 24
# USD per token: uncached input, cache write, cached input, output.
RATES = (2e-6, 2.5e-6, 0.1e-6, 10e-6)

# Build requests with the sample run's own code so the two runs are comparable.
spec = importlib.util.spec_from_file_location('sample_run', ROOT/'runs/discord-extraction-failures-20261004/run.py')
sample = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sample)
assert sample.PROMPT == (OUT/'extraction-prompt.md').read_text()
sample.EFFORT = 'medium'  # the only change from the 10-conversation run's request
lock = threading.Lock()
spent = 0.0


def cost(usage):
    details = usage.get('input_tokens_details') or {}
    cached, write = details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)
    return ((usage['input_tokens']-cached-write)*RATES[0] + write*RATES[1] + cached*RATES[2]
            + usage['output_tokens']*RATES[3])


def fail(key, kind, detail):
    with lock:
        with (OUT/'failures.jsonl').open('a') as f:
            f.write(json.dumps({'packet': key, 'class': kind, 'detail': str(detail)[:500]})+'\n')
    return None


def extract(packet, client):
    global spent
    key = packet['packet_id']
    target, raw = OUT/(key+'.json'), OUT/(key+'.response.json')
    if target.exists():
        return json.loads(target.read_text())
    if raw.exists():
        response = json.loads(raw.read_text())
    else:
        with lock:
            if spent >= CEILING_USD:
                return fail(key, 'spend_ceiling', f'spent {spent:.2f}')
        request = sample.body(packet)
        sample.dump(OUT/(key+'.request.json'), request)
        try:
            response = client.responses.create(**request).model_dump(mode='json')
        except Exception as exc:  # noqa: BLE001 - a failed packet is a row, not a crash
            return fail(key, 'transient', repr(exc))
        sample.dump(raw, response)
        with lock:
            spent += cost(response['usage'])
    if response['status'] != 'completed':
        return fail(key, 'truncated', response.get('incomplete_details'))
    try:
        text = ''.join(c['text'] for o in response['output'] if o['type'] == 'message' for c in o['content'] if c['type'] == 'output_text')
        data = json.loads(text)
        issues = sample.validate(data, packet)
    except Exception as exc:  # noqa: BLE001
        return fail(key, 'malformed', repr(exc))
    data['run'] = {'model': sample.MODEL, 'reasoning': {'effort': sample.EFFORT},
                   'prompt_sha256': hashlib.sha256(sample.PROMPT.encode()).hexdigest(),
                   'response_id': response['id'], 'usage': response['usage'], 'validation_issues': issues}
    sample.dump(target, data)
    return data


def status(packets):
    done = [json.loads(p.read_text()) for p in (OUT/(k['packet_id']+'.json') for k in packets) if p.exists()]
    failures = {}
    if (OUT/'failures.jsonl').exists():
        for line in (OUT/'failures.jsonl').read_text().splitlines():
            row = json.loads(line)
            failures[row['packet']] = row['class']
    done_ids = {p['packet_id'] for p in packets if (OUT/(p['packet_id']+'.json')).exists()}
    open_failures = {k: v for k, v in failures.items() if k not in done_ids}
    return {'packets': len(packets), 'done': len(done), 'with_findings': sum(bool(d['findings']) for d in done),
            'findings': sum(len(d['findings']) for d in done),
            'validation_issues': sum(len(d['run']['validation_issues']) for d in done),
            'unresolved_failures': open_failures and {c: list(open_failures.values()).count(c) for c in set(open_failures.values())},
            'cost_usd': round(sum(cost(d['run']['usage']) for d in done), 2), 'ceiling_usd': CEILING_USD,
            'next': 'complete' if len(done) == len(packets) else 'resume (rerun run.py)'}


if __name__ == '__main__':
    packets = [json.loads(line) for line in (OUT/'packets.jsonl').read_text().splitlines()]
    if sys.argv[1:] == ['status']:
        print(json.dumps(status(packets), indent=2))
        raise SystemExit
    os.umask(0o077)
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT/'.env')
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'], max_retries=5, timeout=900)
    spent = status(packets)['cost_usd']
    (OUT/'failures.jsonl').unlink(missing_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, _ in enumerate(pool.map(lambda p: extract(p, client), packets)):
            if i % 50 == 0:
                print(json.dumps({'reached': i, 'spent_usd': round(spent, 2)}), flush=True)
    final = status(packets)
    sample.dump(OUT/'summary.json', final)
    print(json.dumps(final, indent=2))
    raise SystemExit(0 if final['next'] == 'complete' else 2)
