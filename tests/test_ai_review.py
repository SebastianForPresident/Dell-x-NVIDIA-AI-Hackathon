"""The UI starts the case-bound local agent and observes service state."""
import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import mongomock
from investigations import InvestigationService
from persistence import MongoStore
from server.database import get_service
from server.main import app


class AgentAPITests(unittest.TestCase):
    def test_agent_route_observes_persisted_actions_and_legacy_route_is_inactive(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CROP_ASSET_DIR': folder}):
            service = InvestigationService(MongoStore(mongomock.MongoClient(tz_aware=True).runtime_test))
            app.dependency_overrides[get_service] = lambda: service
            try:
                with TestClient(app) as client:
                    case = client.post('/api/demo').json()
                    def invoke(key):
                        service.record_action(key, 'runtime:test', 'openclaw_run', {},
                                              {'ok': True, 'summary': 'Synthetic demo: evidence gathered.'}, actor='agent')
                    with patch('server.main.run_agent', side_effect=invoke) as runtime:
                        response = client.post(f"/api/cases/{case['id']}/investigate")
                    self.assertEqual(response.status_code, 200, response.text)
                    runtime.assert_called_once_with(case['id'])
                    self.assertEqual(response.json()['agent_run']['summary'], 'Synthetic demo: evidence gathered.')
                    self.assertEqual(client.get(f"/api/cases/{case['id']}").json()['actions'], response.json()['actions'])
                    self.assertIn(client.post(f"/api/cases/{case['id']}/ai-review").status_code, (404, 405))
                    with patch('server.main.run_agent', side_effect=RuntimeError('failed')):
                        self.assertEqual(client.post(f"/api/cases/{case['id']}/investigate").status_code, 503)
            finally:
                app.dependency_overrides.clear()
