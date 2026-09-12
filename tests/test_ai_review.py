"""Qwen wording is attached to the authoritative investigation record."""

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


class AIReviewTests(unittest.TestCase):
    def test_review_is_persisted_alongside_original_findings(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CROP_ASSET_DIR": folder}):
            service = InvestigationService(MongoStore(mongomock.MongoClient(tz_aware=True).review_test))
            app.dependency_overrides[get_service] = lambda: service
            try:
                with TestClient(app) as client:
                    case = client.post("/api/demo").json()
                    for _ in range(6):
                        case = client.post(f"/api/cases/{case['id']}/demo-step").json()
                    self.assertTrue(case["report_saved"])
                    measured = case["report"]
                    review = {key: f"{key} note" for key in ("weather", "vegetation", "crop", "neighbors", "overall")}
                    with patch("server.main.analyze_structured_case", return_value=review) as model:
                        response = client.post(f"/api/cases/{case['id']}/ai-review")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["ai_review"], review)
                    self.assertEqual(model.call_args.args[0]["weather_series"], case["weather_series"])
                    reopened = client.get(f"/api/cases/{case['id']}").json()
                    self.assertEqual(reopened["ai_review"], review)
                    self.assertEqual(reopened["report"], measured)
                    self.assertIn("weather note", client.get(f"/api/cases/{case['id']}/report.md").text)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
