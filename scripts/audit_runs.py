#!/usr/bin/env python3
"""Audit saved runs without model calls; retains failures and unknown usage.

Usage: .venv/bin/python scripts/audit_runs.py --runs ../messageboardauditbench/runs --out /tmp/audit.json
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from messageboard_audit_bench.audit import corpus_audit, trajectory_metrics
from messageboard_audit_bench.transcripts import parse
from messageboard_audit_bench.usage import summarize


def refusal_signals(path: Path) -> int:
    """Count explicit provider refusal events, not ordinary textual mentions."""
    count = 0
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("subtype") == "model_refusal_no_fallback":
            count += 1
        message = event.get("message")
        if isinstance(message, dict) and message.get("stop_reason") == "refusal":
            count += 1
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--data', type=Path)
    args = ap.parse_args()
    rows = []
    grouped = defaultdict(Counter)
    totals = Counter()
    for directory in sorted(args.runs.iterdir()):
        if not (directory/'meta.json').exists() or not (directory/'transcript.jsonl').exists():
            continue
        meta = json.loads((directory/'meta.json').read_text())
        agent = meta['agent']
        try:
            parsed = parse(agent, directory/'transcript.jsonl')
            metrics = trajectory_metrics(parsed.messages)
            usage = summarize(directory, agent)
            row = {'run': directory.name, 'agent': agent, 'model': meta.get('model_served', meta.get('model')),
                   'exit_code': meta.get('exit_code'), 'wall_seconds': meta.get('wall_seconds'),
                   'budget_min': meta.get('budget_min'), 'metrics': metrics, 'usage': usage,
                   'conversion': parsed.extra.get('transcript_diagnostics')}
            row['provider_refusal_signals'] = refusal_signals(directory / 'transcript.jsonl')
            rows.append(row)
            key = agent+':'+str(row['model'])
            grouped[key].update(metrics['tool_calls_by_type'])
            totals['tool_calls'] += metrics['tool_calls']
            totals['tool_errors_excluding_empty_searches'] += metrics['tool_error_count']
            totals['empty_search_exit_1'] += metrics['empty_search_exit_1']
            totals['provider_refusal_signals'] += row['provider_refusal_signals']
            totals['time_feedback_messages'] += metrics['time_feedback_messages']
        except Exception as e:
            rows.append({'run': directory.name, 'audit_error': str(e)})
    output = {
        'runs': rows,
        'tool_calls_by_model': dict(grouped),
        'trajectory_totals': dict(totals),
        'scope_note': 'Only immediate run directories are included; archived nested failed attempts are intentionally excluded.',
    }
    if args.data:
        output['corpus'] = corpus_audit(args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False)+'\n')
    print(f'{len(rows)} runs audited; {sum("audit_error" in r for r in rows)} errors; {args.out}')

if __name__ == '__main__':
    main()
