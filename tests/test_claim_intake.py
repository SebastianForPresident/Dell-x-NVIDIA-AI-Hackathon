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
        fields = self.client.get('/api/local-fields').json()
        self.assertEqual(len(fields), 3)
        self.assertFalse(fields[0]['synthetic'])
        self.assertFalse(fields[1]['synthetic'])
        self.assertTrue(fields[2]['synthetic'])
        self.assertEqual(self.client.get('/api/cases').json(), [])

    def test_public_evidence_claim_has_real_provenance_and_measurements(self):
        repository_assets = os.path.abspath('data/case_assets')
        with patch.dict(os.environ, {'CROP_ASSET_DIR': repository_assets}):
            body = {**self.body, 'field_id': 'dewitt-public-2025', 'loss_date': '2025-09-18'}
            response = self.client.post('/api/claims', json=body)
            self.assertEqual(response.status_code, 201, response.text)
            case = response.json()
            self.assertFalse(case['synthetic_demo'])
            tool = bound_tools(self.service, case['id'])
            rainfall = tool.invoke('check_rainfall', {}, 'real-rain')['data']['finding']
            vegetation = tool.invoke('check_vegetation_change', {}, 'real-ndvi')['data']['finding']
            self.assertEqual(rainfall['values']['rainfall_mm'], 1.3)
            self.assertEqual(rainfall['provenance']['datasets'][0]['provider'], 'NOAA NCEI')
            self.assertEqual(vegetation['values']['change'], -0.403)
            self.assertEqual(vegetation['provenance']['datasets'][0]['provider'], 'Copernicus/ESA')

    def test_same_registered_field_ignores_claim_hypotheses_when_binding_evidence(self):
        repository_assets = os.path.abspath('data/case_assets')
        with patch.dict(os.environ, {'CROP_ASSET_DIR': repository_assets}):
            truthful = {**self.body, 'field_id': 'FIELD-17', 'loss_date': '2025-09-18'}
            false_story = {**truthful, 'crop': 'Soybeans', 'cause': 'Flood',
                           'description': 'The claimant reports soybeans damaged by flooding in this field.'}
            first = self.client.post('/api/claims', json=truthful).json()
            second = self.client.post('/api/claims', json=false_story).json()
            self.assertEqual(first['field_id'], second['field_id'])
            self.assertEqual(first['boundary'], second['boundary'])
            self.assertEqual(first['documents'], second['documents'])
            first_crop = bound_tools(self.service, first['id']).invoke('check_crop_classification', {}, 'crop-a')['data']['finding']
            second_crop = bound_tools(self.service, second['id']).invoke('check_crop_classification', {}, 'crop-b')['data']['finding']
            first_rain = bound_tools(self.service, first['id']).invoke('check_rainfall', {}, 'rain-a')['data']['finding']
            second_rain = bound_tools(self.service, second['id']).invoke('check_rainfall', {}, 'rain-b')['data']['finding']
            self.assertEqual(first_crop['values'], second_crop['values'])
            self.assertEqual(first_rain['values'], second_rain['values'])
            self.assertEqual(first_crop['status'], 'supported')
            self.assertEqual(second_crop['status'], 'contradicted')
            self.assertEqual(first_rain['status'], 'supported')
            self.assertEqual(second_rain['status'], 'contradicted')

    def test_registered_evidence_checks_need_no_external_network(self):
        repository_assets = os.path.abspath('data/case_assets')
        with patch.dict(os.environ, {'CROP_ASSET_DIR': repository_assets}):
            case = self.client.post('/api/claims', json={**self.body, 'field_id': 'FIELD-17',
                                                         'loss_date': '2025-09-18'}).json()
            tools = bound_tools(self.service, case['id'])
            with patch('urllib.request.urlopen', side_effect=AssertionError('external network attempted')), \
                    patch('socket.create_connection', side_effect=AssertionError('external network attempted')):
                findings = [tools.invoke(name, {}, f'offline-{index}')['data']['finding']
                            for index, name in enumerate(('check_crop_classification', 'check_rainfall',
                                                          'check_vegetation_change', 'compare_neighboring_fields'))]
            self.assertTrue(all(finding['status'] == 'supported' for finding in findings))

    def test_registered_field_without_local_evidence_never_borrows_another_package(self):
        body = {**self.body, 'field_id': 'FIELD-KS-04', 'crop': 'Winter wheat',
                'description': 'The claimant reports drought damage on the registered Kansas field.'}
        case = self.client.post('/api/claims', json=body).json()
        self.assertEqual(case['field_id'], 'FIELD-KS-04')
        self.assertEqual(case['location'], 'Finney County, Kansas')
        self.assertEqual(len(case['boundary']['features']), 1)
        tool = bound_tools(self.service, case['id'])
        rainfall = tool.invoke('check_rainfall', {}, 'ks-rain')['data']['finding']
        crop = tool.invoke('check_crop_classification', {}, 'ks-crop')['data']['finding']
        self.assertEqual(rainfall['status'], 'unavailable')
        self.assertEqual(crop['status'], 'unavailable')
        self.assertEqual(rainfall['values'], {})

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
