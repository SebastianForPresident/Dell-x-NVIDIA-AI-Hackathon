"""Launch the real local OpenClaw agent with case-bound, allowlisted tools."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
from server.database import get_service
from server.integration import bound_tools, demo

ROOT = Path(__file__).resolve().parents[1]


def _run(investigation_id, first=False):
    service = get_service()
    bound = bound_tools(service, investigation_id)
    run_id = uuid4().hex
    folder = ROOT / '.runtime' / run_id
    workspace = folder / 'workspace'
    workspace.mkdir(parents=True)
    instructions = '''You are a crop insurance evidence investigator. AI does the detective work; the human adjuster makes the decision.
Use only the provided validated evidence tools. Never approve, deny, calculate payouts, invent measurements, or make final insurance decisions.
If synthetic_demo is true, begin your final response with "Synthetic demo:" and identify measurements as synthetic. Choose relevant evidence tools autonomously based on the claim and results.
'''
    if first:
        instructions += 'For this initial investigation milestone, establish whether the field actually contains the claimed crop by choosing and executing just one relevant evidence check, then explain its returned result and stop. Do not complete the full investigation yet.\n'
    else:
        instructions += 'Investigate all four evidence categories, save the report, then request READY_FOR_ADJUSTER_REVIEW if supported. Missing or conflicting evidence requires a follow-up task and NEEDS_EVIDENCE. Business gates are authoritative. Choose your own tool order. Saving a report does not change the workflow status. Do not stop until you have used the workflow status tool to request READY_FOR_ADJUSTER_REVIEW, or created the required follow-up for NEEDS_EVIDENCE.\n'
    (workspace / 'AGENTS.md').write_text(instructions)
    names = [s['name'] for s in bound.schemas()]
    config = {
        'models': {'providers': {'ollama': {'baseUrl': 'http://127.0.0.1:11434', 'apiKey': 'ollama-local', 'api': 'ollama', 'models': [{'id': 'gpt-oss:20b', 'name': 'gpt-oss:20b', 'reasoning': True, 'input': ['text'], 'contextWindow': 32768, 'maxTokens': 4096, 'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}},
        'agents': {'defaults': {'workspace': str(workspace), 'model': {'primary': 'ollama/gpt-oss:20b', 'fallbacks': []}, 'skipBootstrap': True}},
        'memory': {'search': {'enabled': False}},
        'tools': {'allow': names, 'toolSearch': False},
        'skills': {'allowBundled': []},
        'plugins': {'allow': ['crop-forensics', 'ollama'], 'load': {'paths': [str(ROOT / 'runtime/openclaw')]}, 'slots': {'memory': 'none'}, 'entries': {'crop-forensics': {'enabled': True}}},
        'gateway': {'mode': 'local'}
    }
    config_path = folder / 'openclaw.json'
    config_path.write_text(json.dumps(config, indent=2))
    env = {**os.environ, 'OPENCLAW_CONFIG_PATH': str(config_path), 'OPENCLAW_STATE_DIR': str(folder / 'state'), 'CROP_INVESTIGATION_ID': investigation_id, 'CROP_RUN_ID': run_id}
    claim = {key: value for key, value in bound.metadata.items() if key not in {'asset_bundle', 'demo_run'}}
    message = 'Investigate this claim.\nClaim context: ' + json.dumps(claim)
    command = ['openclaw', 'agent', '--local', '--agent', 'main', '--session-id', run_id, '--message', message, '--thinking', 'low', '--timeout', '600', '--json']
    (folder / 'run.json').write_text(json.dumps({'run_id': run_id, 'investigation_id': investigation_id, 'command': command}, indent=2))
    print(json.dumps({'run_id': run_id, 'investigation_id': investigation_id, 'artifacts': str(folder)}), flush=True)
    with (folder / 'stdout.json').open('w') as stdout, (folder / 'stderr.log').open('w') as stderr:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, timeout=660)
    if result.returncode:
        raise RuntimeError(f'OpenClaw failed; see {folder}/stderr.log')
    output = json.loads((folder / 'stdout.json').read_text())
    receipt = output['meta']['agentMeta']['terminalReceipt']
    if receipt['effective']['provider'] != 'ollama' or receipt['effective']['model'] != 'gpt-oss:20b' or receipt.get('rerouted'):
        raise RuntimeError('Unexpected inference route in OpenClaw receipt')
    exposed = {item['name'] for item in output['meta']['systemPromptReport']['tools']['entries']}
    if exposed != set(names):
        raise RuntimeError('Unexpected model tool surface')
    summary = '\n'.join(item.get('text', '') for item in output['payloads'])
    service.record_action(investigation_id, 'runtime:' + run_id, 'openclaw_run', {},
                          {'ok': True, 'run_id': run_id, 'receipt': receipt, 'summary': summary}, actor='agent')
    return {'run_id': run_id, 'investigation_id': investigation_id, 'artifacts': str(folder)}


def run(investigation_id, first=False):
    # Shared by CLI and API processes; never run two agent writers on one case.
    import re
    if not re.fullmatch(r'[a-f0-9]{64}', investigation_id):
        raise ValueError('Invalid investigation ID')
    locks = ROOT / '.runtime' / 'locks'
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / investigation_id).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('An agent is already investigating this case') from exc
        try:
            return _run(investigation_id, first)
        except (subprocess.SubprocessError, OSError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError('Local OpenClaw run failed; inspect .runtime logs') from exc


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case')
    parser.add_argument('--first', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('MONGODB_URI', 'mongodb://127.0.0.1:27017')
    os.environ.setdefault('MONGODB_DATABASE', 'crop_forensics')
    key = args.case or demo(get_service(), fresh=True).investigation_id
    print(json.dumps(run(key, args.first)))
