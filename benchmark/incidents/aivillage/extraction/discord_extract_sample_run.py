"""Small real-prompt Discord extraction, serialized for the existing review UI."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
MODEL = 'gpt-6.1-sol'
EFFORT = 'high'
PROMPT = (OUT/'extraction-prompt.md').read_text()
TRANSPORT = '''
Transport instruction: preserve the extraction criteria above, but serialize the
requested Markdown content as one JSON object so the existing review UI can display it.
Use this structure (include all fields; empty lists/strings when unnecessary):
{
 "source": {"title": "...", "url": "...", "source_type": "discord", "coverage": "..."},
 "findings": [{"id": "F1", "headline": "...", "finding": "...", "notes": [],
  "subfindings": [{"id": "F1.1", "claim": "...", "notes": [],
   "source_support": [{"quote": "exact contiguous source-message quote",
    "location": "author handle, timestamp, channel/thread and message ID",
    "url": "exact supplied message permalink", "message_id": "exact supplied ID",
    "source_kind": "organizer account|community observation|agent statement|generated summary|unknown",
    "image_number": null, "image_url": null, "record_links": []}],
   "log_evidence": "not yet verified", "evidence_note": "..."}]}],
 "excluded_source_claims": [{"claim": "...", "reason": "..."}],
 "source_limits": []
}
Use separate source_support entries for quotes from separate messages. Quotes must
be verbatim contiguous substrings of the cited original message, without invented
ellipsis, spelling fixes or normalization. Preserve message URLs and IDs exactly.
No screenshot or linked-page contents have been supplied. Frozen logs have not been
provided: all log evidence stays not yet verified. No external tools are available.
Do not add a finding to meet a quota; an empty findings list is allowed.
'''


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')


def body(packet):
    title = packet['channel']['name']+' · '+packet['messages'][0]['timestamp'][:10]
    url = next(m['source_url'] for m in packet['messages'] if m['record_id'] in packet['lead_record_ids'])
    values = {
        'SOURCE_TYPE': 'discord', 'TASK_STAGE': 'extract', 'PREFILTER_MODE': 'rules_and_model',
        'PREFILTER_CONTEXT': 'Sage Discord export: 64088 records, channel and behavioral-rule prioritization, then GPT-6 Luna low-reasoning screening. Raw export preserved locally but unavailable to this model. Screening used the previous, more permissive prompt; it has not been rerun with the new evidence threshold. Selected packet is an excerpt, not a complete conversation. Neighbor messages, direct replies and available ancestors retained; other context and corrections may be missing. Source attachments and linked pages unread. Model screening rationales are intentionally not supplied as evidence.',
        'SOURCE_TITLE_AND_URL': title+'\n'+url,
        'SOURCE_TEXT': 'Supplied as original-message JSON in the user input.',
        'FROZEN_EVIDENCE_DESCRIPTION': 'AI Village text export covering April 2025 through 2026-09-20T13:05:12.097Z: chat, computer-use actions/outputs, memories, summaries and optionally reasoning traces. No screenshots. Exact logs are not supplied here; do not claim log verification.',
    }
    instructions = PROMPT
    for key, value in values.items():
        instructions = instructions.replace('{{'+key+'}}', value)
    return {'model': MODEL, 'reasoning': {'effort': EFFORT}, 'instructions': instructions+TRANSPORT,
            'input': [{'role': 'user', 'content': 'Source packet for JSON extraction:\n'+json.dumps({'title': title, 'url': url, **packet}, ensure_ascii=False)}],
            'text': {'format': {'type': 'json_object'}}, 'max_output_tokens': 12000, 'service_tier': 'default', 'store': False}


def validate(data, packet):
    messages = {m['message_id']: m for m in packet['messages']}
    issues = []
    ids = set()
    for f in data['findings']:
        if f['id'] in ids:
            issues.append('Duplicate finding ID '+f['id'])
        ids.add(f['id'])
        for sf in f['subfindings']:
            if sf['id'] in ids or not sf['id'].startswith(f['id']+'.'):
                issues.append('Invalid subfinding ID '+sf['id'])
            ids.add(sf['id'])
            if sf['log_evidence'] != 'not yet verified':
                issues.append(sf['id']+': invented log verification')
            if not sf['source_support']:
                issues.append(sf['id']+': missing source support')
            for support in sf['source_support']:
                m = messages.get(support.get('message_id'))
                if not m or support['url'] != m['source_url']:
                    issues.append(sf['id']+': unknown source ID or URL')
                elif not support['quote'] or support['quote'] not in m['text']:
                    issues.append(sf['id']+': quote is not verbatim')
                if support.get('image_number') is not None or support.get('image_url') is not None:
                    issues.append(sf['id']+': claims unseen image evidence')
    return issues


def extract(packet):
    key = packet['packet_id']
    target = OUT/(key+'.json')
    if target.exists():
        return json.loads(target.read_text())
    request = body(packet)
    dump(OUT/(key+'.request.json'), request)
    response_path = OUT/(key+'.response.json')
    if response_path.exists():
        raise RuntimeError('Raw response exists; inspect it before retrying')
    print(json.dumps({'packet': key, 'status': 'started'}), flush=True)
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'], max_retries=0, timeout=600)
    response = client.responses.create(**request)
    dump(response_path, response.model_dump(mode='json'))
    if response.status != 'completed':
        raise RuntimeError('Incomplete response '+key)
    data = json.loads(response.output_text)
    issues = validate(data, packet)
    data['run'] = {'model': MODEL, 'reasoning': {'effort': EFFORT}, 'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(), 'response_id': response.id, 'usage': response.usage.model_dump(mode='json'), 'validation_issues': issues}
    dump(target, data)
    print(json.dumps({'packet': key, 'status': 'completed', 'findings': len(data['findings']), 'validation_issues': issues}), flush=True)
    return data


if __name__ == '__main__':
    os.umask(0o077)
    load_dotenv(ROOT/'.env')
    packets = json.loads((OUT/'sample-packets.json').read_text())
    requests = [body(p) for p in packets]
    # UTF-8 bytes conservatively bound text tokens, plus overhead; 4x rates.
    upper = sum(((len(json.dumps(r, ensure_ascii=False).encode())+8192)*2e-6+12000*10e-6)*4 for r in requests)
    previous_upper = json.loads((ROOT/'runs/discord-screen-20261004/summary.json').read_text())['reserved_upper_including_failed_attempts_usd']
    previous_upper += json.loads((ROOT/'runs/discord-extraction-sample-20261004/run-plan.json').read_text())['conservative_cost_upper_usd']
    assert upper < 10 and upper+previous_upper < 100
    dump(OUT/'run-plan.json', {'model': MODEL, 'effort': EFFORT, 'calls': len(packets), 'maximum_output_tokens_per_call': 12000, 'conservative_cost_upper_usd': upper, 'prior_screening_upper_usd': previous_upper, 'combined_user_cap_usd': 100, 'pricing_url': 'https://developers.openai.com/api/docs/models/gpt-6.1-sol'})
    (OUT/'transport-instruction.txt').write_text(TRANSPORT)
    print(json.dumps({'conservative_cost_upper_usd': upper}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(extract, packets))
