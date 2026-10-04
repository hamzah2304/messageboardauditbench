"""Goal periods queried per run: a goal counts if a tool input names a date inside it, a <60-day date range overlapping it, or its goal id."""
import glob, json, os, re, sys
from datetime import date
os.chdir('/home/oscar_gilg18/Dev/MessageBoardAuditBench/.worktrees/claude-aivillage-pilot')
G = [json.loads(l) for l in open('data/aivillage/full-v2-noreasoning/village_goals.jsonl')]
goals = [(g['id'], date.fromisoformat(g['start_time'][:10]), date.fromisoformat((g.get('end_time') or '2026-09-21')[:10]), g['goal'][:50]) for g in G]
D = re.compile(r'(20(?:25|26))-(\d\d)-(\d\d)')
out = {}
for d in sorted(glob.glob('runs/20261004T*_aivillage-v8-40*')):
    if '_r9_' in d or not os.path.exists(f'{d}/report.md'): continue
    hit = set(); hit_main = set()
    for l in open(f'{d}/tool-events.jsonl'):
        o = json.loads(l)
        if o['event'] != 'PreToolUse': continue
        s = json.dumps(o['payload'].get('tool_input', ''))
        h = set()
        ds = []
        for y, m, dd in D.findall(s):
            try: ds.append(date(int(y), int(m), int(dd)))
            except ValueError: pass
        for x in ds:
            h |= {g[0] for g in goals if g[1] <= x < g[2] or x == g[1]}
        ds.sort()
        for a, b in zip(ds, ds[1:]):
            if 0 < (b - a).days < 60: h |= {g[0] for g in goals if g[1] < b and g[2] > a}
        h |= {g[0] for g in goals if g[0] in s or g[0][:8] in s}
        hit |= h
        if not o['payload'].get('agent_id'): hit_main |= h
    out[os.path.basename(d)] = dict(goals=len(hit), goals_main_agent=len(hit_main),
        missed=[g[3] for g in goals if g[0] not in hit])
json.dump(out, sys.stdout, indent=1)
