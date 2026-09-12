"""Boundary checks; live inference proof is exported by runtime.proof."""
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from agent_tools import TOOL_SCHEMAS
from runtime import run as runtime


class RuntimeTests(unittest.TestCase):
    def test_same_case_cannot_have_two_agent_writers(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime, 'ROOT', Path(folder)):
            locks = Path(folder) / '.runtime/locks'
            locks.mkdir(parents=True)
            with (locks / ('a' * 64)).open('w') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(runtime, '_run') as invoke:
                    with self.assertRaisesRegex(ValueError, 'already investigating'):
                        runtime.run('a' * 64)
                    invoke.assert_not_called()

    def test_local_route_case_binding_and_exact_tool_surface(self):
        names = [t['name'] for t in TOOL_SCHEMAS]
        service = Mock()
        bound = Mock(metadata={'synthetic_demo': True, 'claimed_crop': 'Corn', 'asset_bundle': 'private'})
        bound.schemas.return_value = TOOL_SCHEMAS
        def launch(command, **kwargs):
            self.assertEqual(command[:4], ['openclaw', 'agent', '--local', '--agent'])
            self.assertNotIn('shell', kwargs)
            env = kwargs['env']
            self.assertEqual(env['CROP_INVESTIGATION_ID'], 'b' * 64)
            config = json.loads(Path(env['OPENCLAW_CONFIG_PATH']).read_text())
            self.assertEqual(config['models']['providers']['ollama']['baseUrl'], 'http://127.0.0.1:11434')
            self.assertEqual(config['models']['providers']['ollama']['api'], 'ollama')
            self.assertEqual(config['agents']['defaults']['model'], {'primary': 'ollama/gpt-oss:20b', 'fallbacks': []})
            self.assertEqual(config['tools'], {'allow': names, 'toolSearch': False})
            self.assertNotIn('asset_bundle', command[command.index('--message') + 1])
            json.dump({'meta': {'agentMeta': {'terminalReceipt': {'effective': {'provider': 'ollama', 'model': 'gpt-oss:20b'}, 'rerouted': False}}, 'systemPromptReport': {'tools': {'entries': [{'name': n} for n in names]}}}, 'payloads': [{'text': 'Synthetic demo: done'}]}, kwargs['stdout'])
            return Mock(returncode=0)
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime, 'ROOT', Path(folder)), patch.object(runtime, 'get_service', return_value=service), patch.object(runtime, 'bound_tools', return_value=bound), patch.object(runtime.subprocess, 'run', side_effect=launch):
            result = runtime.run('b' * 64)
            self.assertEqual(result['investigation_id'], 'b' * 64)
            self.assertEqual(service.record_action.call_args.kwargs['actor'], 'agent')

    def test_case_identifier_cannot_be_a_path(self):
        with self.assertRaisesRegex(ValueError, 'Invalid investigation ID'):
            runtime.run('../../outside')
