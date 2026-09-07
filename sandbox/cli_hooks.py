#!/usr/bin/env python3
"""Observational hooks for the normal subscription CLIs.

Existing time/report feedback is preserved. Telemetry commands emit no output
and neither permit nor deny tools. Unsupported lifecycle events are omitted.
"""
import argparse
import json


def hook_config(agent: str, path: str = '/telemetry/events.jsonl') -> dict:
    def recorder(event):
        return {'type': 'command', 'command': f'python3 /sandbox/tool_telemetry.py --event {event} --path {path}'}

    hooks = {
        'PreToolUse': [{'hooks': [recorder('PreToolUse')]}],
        'PostToolUse': [{'hooks': [recorder('PostToolUse'),
            {'type': 'command', 'command': '/sandbox/time_left.sh'},
            {'type': 'command', 'command': 'python3 /sandbox/report_length.py --hook PostToolUse'}]}],
        'Stop': [{'hooks': [{'type': 'command', 'command': 'python3 /sandbox/runtime_policy.py --hook Stop'}]}],
    }
    if agent == 'claude':
        hooks['PostToolUseFailure'] = [{'hooks': [recorder('PostToolUseFailure')]}]
    return {'hooks': hooks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('agent', choices=('claude', 'codex'))
    args = parser.parse_args()
    print(json.dumps(hook_config(args.agent)))
