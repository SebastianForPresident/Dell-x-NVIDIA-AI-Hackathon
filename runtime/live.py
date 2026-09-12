"""Ephemeral display snapshots; MongoDB remains the evidence source of truth."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def stream_path(case_id):
    if not re.fullmatch(r'[a-f0-9]{64}', case_id):
        raise ValueError('Invalid investigation ID')
    return ROOT / '.runtime' / 'streams' / (case_id + '.json')


def read_snapshot(case_id):
    try:
        return json.loads(stream_path(case_id).read_text())
    except FileNotFoundError:
        return {'state': 'idle', 'text': '', 'tools': []}


def write_snapshot(case_id, snapshot):
    path = stream_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot))
    temporary.replace(path)
