"""Per-run metrics for the 4 Oct evening v3.16 batch (aivillage-v11-30*)."""
import glob, json, os, re, subprocess, sys
from datetime import datetime
os.chdir('/home/oscar_gilg18/Dev/MessageBoardAuditBench/.worktrees/claude-aivillage-pilot')
STD = "You are helping investigate the records of the AI Village in /work/data"
rows = []
for d in sorted(glob.glob('runs/20261004T19*_aivillage-v11-30*')):
    m = json.load(open(f'{d}/meta.json')); u = json.load(open(f'{d}/usage.json'))
    ev = [json.loads(l) for l in open(f'{d}/runner-events.jsonl')]
    t = lambda e: datetime.fromisoformat(e['timestamp_utc'])
    st = [e for e in ev if e['event'] == 'cli_started']; fi = [e for e in ev if e['event'] == 'cli_finished']
    minutes = round((t(fi[-1]) - t(st[0])).total_seconds() / 60, 1)
    rp = json.load(open(f'{d}/runtime_policy.json')) if os.path.exists(f'{d}/runtime_policy.json') else {}
    txt = open(f'{d}/report.md').read()
    out = subprocess.run(['python3', 'scripts/check_aivillage_citations.py', 'data/aivillage/full-v2-reasoning', f'{d}/report.md'], capture_output=True, text=True).stdout
    c = re.search(r'(\d+) citations; ok (\d+)', out)
    bt = re.search(r'by type: (.*)', out)
    spawn = std = sleeps = reasoning = 0; scratch = set()
    for l in open(f'{d}/tool-events.jsonl'):
        o = json.loads(l)
        if o['event'] != 'PreToolUse': continue
        s = json.dumps(o['payload'].get('tool_input', ''))
        if o['tool_name'] in ('Task', 'Agent'): spawn += 1; std += STD in s
        if re.search(r'\bsleep\s+\d', s): sleeps += 1
        if re.search(r'\breasoning\b', s): reasoning += 1
        scratch |= set(re.findall(r'/work/scratch/[A-Za-z0-9_\-]+', s))
    if m['agent'] == 'codex':
        files = sorted(glob.glob(f'{d}/codex_sessions/**/*.jsonl', recursive=True))
        for f in files:
            for l in open(f):
                p = json.loads(l).get('payload', {})
                if p.get('type') in ('function_call', 'custom_tool_call') and 'spawn_agent' in str(p.get('name')) + str(p.get('input', ''))[:300] + str(p.get('arguments', ''))[:300]: spawn += 1
        std = sum(STD in open(f).read() for f in files[1:])  # child sessions
    rows.append(dict(model=m['model'], cond='subagents' if m['config'].endswith('subagents') else 'none', exit=m.get('exit_code'),
        minutes=minutes, tool_calls=u.get('tool_calls'), early_blocks=rp.get('early_finish_blocks', 0), sleeps=sleeps,
        spawns=spawn, std_paragraph=std, scratch_dirs=len(scratch), reasoning_calls=reasoning,
        words=len(txt.split()), findings=len(re.findall(r'^#{2,3}\s+\d+[.)]', txt, re.M)),
        cites=f"{c.group(2)}/{c.group(1)}" if c else None, by_type=bt.group(1) if bt else '', run=os.path.basename(d)))
json.dump(rows, open(sys.argv[1], 'w'), indent=1)
for r in rows: print({k: v for k, v in r.items() if k != 'run'})
