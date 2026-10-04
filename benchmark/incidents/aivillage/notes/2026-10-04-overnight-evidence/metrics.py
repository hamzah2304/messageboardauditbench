"""Per-run metrics for the 4 Oct AI Village v8-40 batch. Usage: metrics.py > metrics.json"""
import glob, json, os, re, subprocess, sys
from datetime import datetime
ROOT = '/home/oscar_gilg18/Dev/MessageBoardAuditBench/.worktrees/claude-aivillage-pilot'
os.chdir(ROOT)
rows = []
for d in sorted(glob.glob('runs/20261004T0[6-9]*_aivillage-v8-40*') + glob.glob('runs/20261004T1*_aivillage-v8-40*')):
    if '_r9_' in d: continue
    m = json.load(open(f'{d}/meta.json'))
    if 'agent' not in m or not os.path.exists(f'{d}/transcript.jsonl'):
        print('skip (no agent run):', d, file=sys.stderr); continue
    u = json.load(open(f'{d}/usage.json')) if os.path.exists(f'{d}/usage.json') else {}
    ev = [json.loads(l) for l in open(f'{d}/runner-events.jsonl')] if os.path.exists(f'{d}/runner-events.jsonl') else []
    t = lambda e: datetime.fromisoformat(e['timestamp_utc'])
    st = [e for e in ev if e['event'] == 'cli_started']; fi = [e for e in ev if e['event'] == 'cli_finished']
    minutes = round((t(fi[-1]) - t(st[0])).total_seconds() / 60, 1) if st and fi else None
    rp = json.load(open(f'{d}/runtime_policy.json')) if os.path.exists(f'{d}/runtime_policy.json') else {}
    rep = f'{d}/report.md'
    words = findings = None; cit = {}
    if os.path.exists(rep):
        txt = open(rep).read(); words = len(txt.split())
        findings = len(re.findall(r'^#{2,3}\s+\d+[.)]', txt, re.M))
        out = subprocess.run(['python3', 'scripts/check_aivillage_citations.py', 'data/aivillage/full-v2-noreasoning', rep], capture_output=True, text=True).stdout
        mm = re.search(r'(\d+) citations; ok (\d+), id missing (\d+), quote not found (\d+), no quote (\d+)', out)
        if mm: cit = dict(zip(['total', 'ok', 'id_missing', 'quote_not_found', 'no_quote'], map(int, mm.groups())))
        bt = re.search(r'by type: (.*)', out); cit['by_type'] = bt.group(1) if bt else ''
    # subagent use: actual calls, not mentions in tool definitions
    sub = 0
    if m['agent'] == 'claude':
        for l in open(f'{d}/transcript.jsonl'):
            try: o = json.loads(l)
            except Exception: continue
            msg = o.get('message') or {}
            for b in (msg.get('content') or []) if isinstance(msg.get('content'), list) else []:
                if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') in ('Task', 'Agent'): sub += 1
    else:
        for f in glob.glob(f'{d}/codex_sessions/**/*.jsonl', recursive=True):
            for l in open(f):
                p = json.loads(l).get('payload', {})
                if p.get('type') in ('function_call', 'custom_tool_call'):
                    if p.get('name') == 'spawn_agent' or 'spawn_agent(' in str(p.get('input', '')) or 'spawn_agent' in str(p.get('arguments', '')): sub += 1
    rows.append(dict(run=os.path.basename(d), agent=m['agent'], model=m['model'], config=m['config'], effort=m['effort'],
        rep=m['replicate'], exit=m.get('exit_code'), minutes=minutes, tool_calls=u.get('tool_calls'),
        early_stop_blocks=rp.get('early_finish_blocks', 0), words=words, findings=findings, citations=cit, subagent_calls=sub,
        peak_context=u.get('peak_context_tokens'), cost_usd=u.get('cost_usd')))
json.dump(rows, sys.stdout, indent=1)
