import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import mongomock

from investigations import InvestigationService
from persistence import MongoStore
from server.database import get_service
from server.integration import bound_tools
from server.main import app


class UnifiedAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"CROP_ASSET_DIR": self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = InvestigationService(MongoStore(mongomock.MongoClient(tz_aware=True).unified_test))
        app.dependency_overrides[get_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def demo(self):
        response = self.client.post("/api/demo")
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def finish(self, case):
        for _ in range(6):
            response = self.client.post(f"/api/cases/{case['id']}/demo-step")
            self.assertEqual(response.status_code, 200, response.text)
            case = response.json()
        return case

    def test_demo_end_to_end_no_parallel_cases(self):
        self.service.store.db.cases.insert_one({"id": "LEGACY-NY"})
        self.assertEqual(self.client.get("/api/cases").json(), [])
        case = self.demo()
        self.assertEqual(case["status"], "NEW")
        self.assertEqual(case["location"], "DeWitt County, Illinois")
        self.assertTrue(case["synthetic_demo"])
        self.assertEqual(self.demo()["id"], case["id"])
        case = self.finish(case)
        self.assertEqual(case["status"], "READY_FOR_ADJUSTER_REVIEW")
        self.assertTrue(case["report_saved"])
        self.assertEqual(len(case["evidence"]), 4)
        self.assertEqual(len(case["actions"]), 6)
        self.assertTrue(all(a["actor"] == "demo" for a in case["actions"]))
        self.assertEqual(len(case["ndvi_series"]), 2)
        self.assertEqual(len(case["weather_series"]), 30)
        self.assertEqual(self.service.store.db.cases.count_documents({}), 1)
        self.assertEqual(self.service.store.db.investigations.count_documents({}), 1)
        self.assertEqual(self.client.get(f"/api/cases/{case['id']}/report.md").status_code, 200)

    def test_agent_and_api_share_record_after_reopen(self):
        case = self.demo()
        reopened = InvestigationService(self.service.store)
        tools = bound_tools(reopened, case["id"])
        self.assertTrue(tools.invoke("check_rainfall", {}, "actual-runtime-call")["ok"])
        result = self.client.get(f"/api/cases/{case['id']}").json()
        self.assertEqual(result["status"], "INVESTIGATING")
        self.assertEqual(result["evidence"][0]["finding"]["check"], "Precipitation")
        self.assertEqual(result["actions"][0]["actor"], "agent")

    def test_reset_preserves_previous_investigation(self):
        original = self.finish(self.demo())
        fresh = self.client.post("/api/demo/reset").json()
        self.assertNotEqual(original["id"], fresh["id"])
        self.assertEqual(fresh["status"], "NEW")
        self.assertEqual(self.client.get(f"/api/cases/{original['id']}").json()["status"], "READY_FOR_ADJUSTER_REVIEW")
        self.assertEqual(self.demo()["id"], fresh["id"])

    def test_followup_blocks_ready_and_human_resolves(self):
        case = self.finish(self.demo())
        url = f"/api/cases/{case['id']}"
        response = self.client.post(url + "/tasks", json={"title": "Check source", "reason": "Human review requested"})
        self.assertEqual(response.status_code, 201)
        task = response.json()["tasks"][0]
        self.assertEqual(response.json()["status"], "NEEDS_EVIDENCE")
        self.assertEqual(self.client.post(url + "/demo-step").status_code, 422)
        self.assertEqual(self.client.post(url + f"/tasks/{task['_id']}/resolve", json={"resolution": " "}).status_code, 422)
        resolved = self.client.post(url + f"/tasks/{task['_id']}/resolve", json={"resolution": "Reviewed original source"})
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()["tasks"][0]["status"], "RESOLVED")
        # API selects a new retry key after human resolution changes task state.
        self.assertEqual(self.client.post(url + "/demo-step").status_code, 200)
        self.assertEqual(self.client.get(url).json()["status"], "READY_FOR_ADJUSTER_REVIEW")

    def test_no_claim_decision_or_legacy_inference_api(self):
        case = self.demo()
        for suffix in ("approve", "deny", "payout", "narrative", "claim-suggestions"):
            # With built static assets, the GET-only SPA fallback can produce 405.
            self.assertIn(self.client.post(f"/api/cases/{case['id']}/{suffix}").status_code, (404, 405))
        self.assertIn(self.client.post("/api/runtime/check-model").status_code, (404, 405))
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertFalse(any(any(word in path for word in ("approve", "deny", "payout", "narrative", "check-model")) for path in paths))
        self.assertEqual(self.client.get(f"/api/cases/{case['id']}/report.md").status_code, 409)
        self.assertEqual(self.client.get("/api/cases/missing").status_code, 404)
        self.assertEqual(self.client.post(f"/api/cases/{case['id']}/tasks", json={"title":"t", "reason":"r", "payout":5}).status_code, 422)

    def test_upload_retains_assets_and_uses_service(self):
        original = self.demo()
        assets = bound_tools(self.service, original["id"]).assets
        files = {name: (filename, assets.path(kind).read_bytes(), mime) for name, kind, filename, mime in (
            ("boundary", "boundary", "field.geojson", "application/json"),
            ("weather", "weather", "weather.csv", "text/csv"),
            ("crop_layer", "crop", "crop.tif", "image/tiff"),
            ("before_image", "before", "before.tif", "image/tiff"),
            ("after_image", "after", "after.tif", "image/tiff"))}
        response = self.client.post("/api/cases/analyze", files=files, data={
            "claim_id": "UPLOAD-SYNTHETIC", "farm": "Upload Farm", "location": "DeWitt County, Illinois",
            "cause": "Drought", "crop": "Corn", "loss_date": "2026-07-18", "before_date": "2026-05-30",
            "after_date": "2026-08-12", "synthetic_demo": "true"})
        self.assertEqual(response.status_code, 201, response.text)
        case = response.json()
        self.assertEqual(case["status"], "READY_FOR_ADJUSTER_REVIEW")
        self.assertTrue(bound_tools(self.service, case["id"]).assets.path("before").exists())
        self.assertEqual(self.service.store.db.cases.count_documents({}), 0)


if __name__ == "__main__":
    unittest.main()
