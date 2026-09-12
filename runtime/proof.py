"""Export inspectable model/tool/Mongo proof from a real local run (read only)."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from investigations import stable_id
from server.database import get_service
from runtime.run import ROOT


def collect(run_id):
    folder = ROOT / '.runtime' / run_id
    run = json.loads((folder / 'run.json').read_text())
    output = json.loads((folder / 'stdout.json').read_text())
    database = folder / 'state/agents/main/agent/openclaw-agent.sqlite'
    messages = []
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
        for (encoded,) in connection.execute('SELECT event_json FROM transcript_events ORDER BY seq'):
            event = json.loads(encoded)
            if event.get('type') != 'message':
                continue
            message = event['message']
            # Retain tool requests/results and visible answers, omit model reasoning.
            content = message.get('content')
            if isinstance(content, list):
                message['content'] = [item for item in content if item.get('type') != 'thinking']
            messages.append(message)
    service = get_service()
    package = service.load_package(run['investigation_id'])
    calls = [item for message in messages if message.get('role') == 'assistant'
             for item in message.get('content', []) if item.get('type') == 'toolCall']
    correlations = []
    runtime_rejections = []
    for call in calls:
        action_id = stable_id(run['investigation_id'], 'action', 'tool:' + run_id + ':' + call['id'])
        action = next((a for a in package['actions'] if a['_id'] == action_id), None)
        returned = next((m for m in messages if m.get('role') == 'toolResult' and m.get('toolCallId') == call['id']), None)
        assert returned, f"Missing model result for {call['id']}"
        if action is None and returned.get('isError'):
            runtime_rejections.append({'call': call, 'result': returned})
            continue
        assert action, f"Missing audit for executed call {call['id']}"
        assert action['tool'] == call['name'] and action['actor'] == 'agent'
        assert action['result'] == returned['details']
        correlations.append({'tool_call_id': call['id'], 'tool': call['name'], 'action_id': action_id,
                             'evidence_id': action['result'].get('data', {}).get('evidence_id')})
    assert correlations, 'No genuine model tool calls in this run'
    assert messages[-1]['role'] == 'assistant', 'No model continuation after tools'
    return {'run': run, 'receipt': output['meta']['agentMeta']['terminalReceipt'],
            'exposed_tools': [t['name'] for t in output['meta']['systemPromptReport']['tools']['entries']],
            'correlations': correlations, 'runtime_rejections': runtime_rejections, 'messages': messages,
            'mongo_ping': service.store.db.client.admin.command('ping'),
            'mongo_database': service.store.db.name, 'mongo_package': package}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    os.environ.setdefault('MONGODB_URI', 'mongodb://127.0.0.1:27017')
    os.environ.setdefault('MONGODB_DATABASE', 'crop_forensics')
    encoded = json.dumps(collect(args.run_id), default=str, indent=2)
    if args.output:
        args.output.write_text(encoded + '\n')
    else:
        print(encoded)
