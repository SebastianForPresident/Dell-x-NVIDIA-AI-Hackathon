import os
import tempfile
import unittest
from unittest.mock import patch
import mongomock
from fastapi.testclient import TestClient
from investigations import InvestigationService
from persistence import MongoStore
from server.database import get_service
from server.integration import bound_tools
from server.main import app


class ClaimIntakeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'CROP_ASSET_DIR': self.folder.name})
        self.env.start()
        self.service = InvestigationService(MongoStore(mongomock.MongoClient(tz_aware=True).intake))
        app.dependency_overrides[get_service] = lambda: self.service
        self.client = TestClient(app)
        self.body = {'farm': 'My farm', 'description': 'The farmer reports drought damage to corn.',
                     'field_id': 'dewitt-demo-field', 'cause': 'Drought', 'crop': 'Corn', 'loss_date': '2026-07-18'}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.env.stop()
        self.folder.cleanup()

    def test_catalog_and_listing_do_not_seed_claims(self):
        self.assertEqual(len(self.client.get('/api/local-fields').json()), 1)
        self.assertEqual(self.client.get('/api/cases').json(), [])

    def test_written_claim_binds_local_assets_without_running_tools(self):
        response = self.client.post('/api/claims', json=self.body)
        self.assertEqual(response.status_code, 201, response.text)
        case = response.json()
        self.assertEqual(case['claim_description'], self.body['description'])
        self.assertEqual(case['status'], 'NEW')
        self.assertEqual(case['origin'], 'intake')
        self.assertTrue(case['synthetic_demo'])
        self.assertEqual(case['actions'], [])
        self.assertEqual(len(case['documents']), 5)
        tool = bound_tools(self.service, case['id'])
        self.assertEqual(tool.invoke('check_crop_classification', {}, 'check')['data']['finding']['values']['class'], 'Corn')

    def test_unregistered_field_does_not_borrow_synthetic_evidence(self):
        body = {**self.body, 'field_id': 'unregistered', 'location': 'Another county'}
        case = self.client.post('/api/claims', json=body).json()
        self.assertFalse(case['synthetic_demo'])
        self.assertEqual(case['documents'], [])
        tool = bound_tools(self.service, case['id'])
        self.assertEqual(tool.invoke('check_rainfall', {}, 'rain')['data']['finding']['status'], 'unavailable')
        self.assertFalse(tool.invoke('set_case_status', {'status': 'READY_FOR_ADJUSTER_REVIEW', 'reason': 'test'}, 'ready')['ok'])

    def test_untrusted_field_and_uncovered_dates_are_not_silently_matched(self):
        self.assertEqual(self.client.post('/api/claims', json={**self.body, 'field_id': '../../outside'}).status_code, 422)
        case = self.client.post('/api/claims', json={**self.body, 'loss_date': '2025-07-18'}).json()
        finding = bound_tools(self.service, case['id']).invoke('check_rainfall', {}, 'rain')['data']['finding']
        self.assertNotEqual(finding['status'], 'supported')
