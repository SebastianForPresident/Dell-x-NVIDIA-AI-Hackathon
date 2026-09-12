"""Real deterministic GIS against small, explicitly synthetic Illinois fixtures."""

import csv
from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mongomock
import numpy as np
import rasterio
from rasterio.transform import from_origin

from agent_assets import CaseAssets
from agent_tools import AgentTools
from investigations import InvestigationService
from persistence import MongoStore


class AgentToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = InvestigationService(MongoStore(mongomock.MongoClient().agent_test))
        self.metadata = {"claim_id": "DEWITT-SYNTHETIC-1", "reported_cause": "Drought",
                         "reported_loss_date": "2026-07-18", "field": "Synthetic corn field",
                         "claimed_crop": "Corn", "synthetic_demo": True,
                         "location": "DeWitt County, Illinois (synthetic fixture)"}
        def field(x):
            return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [
                [[x, 40.15], [x + .005, 40.15], [x + .005, 40.155], [x, 40.155], [x, 40.15]]]}}
        (self.root / "boundary.json").write_text(json.dumps({"type": "FeatureCollection",
                                                            "features": [field(-88.90), field(-88.89)]}))
        with (self.root / "weather.csv").open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["date", "precipitation", "normal_precipitation"])
            for offset in range(30):
                writer.writerow([(date(2026, 7, 18) - timedelta(days=offset)).isoformat(), 1, 3])
        profile = {"driver": "GTiff", "height": 30, "width": 30, "count": 2,
                   "dtype": "float32", "crs": "EPSG:4326", "transform": from_origin(-88.91, 40.17, .001, .001)}
        for name, nir in (("before.tif", .7), ("after.tif", .25)):
            with rasterio.open(self.root / name, "w", **profile) as dataset:
                dataset.write(np.full((30, 30), .1, dtype="float32"), 1)
                dataset.write(np.full((30, 30), nir, dtype="float32"), 2)
        with rasterio.open(self.root / "crop.tif", "w", **{**profile, "count": 1, "dtype": "uint8"}) as dataset:
            dataset.write(np.ones((30, 30), dtype="uint8"), 1)
        self.assets = CaseAssets(self.root, boundary="boundary.json", weather="weather.csv", crop="crop.tif",
                                 before="before.tif", after="after.tif", before_date="2026-05-30", after_date="2026-08-12")
        self.tools = AgentTools.start(self.service, self.metadata, self.assets)

    def call(self, name, arguments=None, call_id=None):
        return self.tools.invoke(name, arguments or {}, call_id or name)

    def all_evidence(self):
        # Deliberately not the UI's fixed order; each handler is independently callable.
        for name in ("check_vegetation_change", "check_rainfall", "compare_neighboring_fields", "check_crop_classification"):
            result = self.call(name)
            self.assertTrue(result["ok"], result)

    def test_complete_drought_workflow_and_audit(self):
        self.assertEqual(self.call("get_claim")["data"]["status"], "NEW")
        self.all_evidence()
        rainfall = self.call("check_rainfall")["data"]["finding"]["values"]
        self.assertEqual(rainfall["rainfall_mm"], 30)
        self.assertEqual(rainfall["normal_mm"], 90)
        saved = self.call("save_investigation_report")
        self.assertTrue(saved["ok"], saved)
        result = self.call("set_case_status", {"status": "READY_FOR_ADJUSTER_REVIEW", "reason": "All checks support review"})
        self.assertTrue(result["ok"], result)
        package = self.service.load_package(self.tools.investigation_id)
        self.assertEqual(package["investigation"]["status"], "READY_FOR_ADJUSTER_REVIEW")
        self.assertEqual(len(package["evidence"]), 4)
        self.assertEqual(len(package["actions"]), 7)
        self.assertTrue(all(a["actor"] == "agent" for a in package["actions"]))
        self.assertTrue(package["report"]["synthetic_demo"])
        json.dumps(result, allow_nan=False)

    def test_retry_replays_and_does_not_duplicate(self):
        first = self.call("check_rainfall")
        with patch("agent_tools.weather_finding", side_effect=AssertionError("Must not recompute")):
            self.assertEqual(first, self.call("check_rainfall"))
        # New call ID can recompute but must still deduplicate identical evidence.
        self.call("check_rainfall", call_id="second")
        package = self.service.load_package(self.tools.investigation_id)
        self.assertEqual(len(package["evidence"]), 1)
        self.assertEqual(len(package["actions"]), 2)
        conflict = self.call("get_claim", call_id="check_rainfall")
        self.assertEqual(conflict["error"]["code"], "CALL_ID_CONFLICT")

    def test_invalid_input_is_audited_without_evidence(self):
        for i, (name, args) in enumerate([
            ("check_rainfall", {"path": "../../secrets"}), ("exec", {}),
            ("set_case_status", {"status": "APPROVED", "reason": "No"}),
            ("create_follow_up_task", {"title": " ", "reason": "missing"}),
            ("check_crop_classification", {"expected_crop": "Corn"}),
        ]):
            self.assertFalse(self.call(name, args, f"invalid-{i}")["ok"])
        package = self.service.load_package(self.tools.investigation_id)
        self.assertEqual(len(package["actions"]), 5)
        self.assertEqual(len(package["evidence"]), 0)
        self.assertEqual(package["investigation"]["status"], "NEW")

    def test_missing_evidence_and_follow_up(self):
        self.tools = AgentTools.start(self.service, self.metadata, replace(self.assets, weather=None))
        result = self.call("check_rainfall")
        self.assertEqual(result["data"]["finding"]["status"], "unavailable")
        args = {"title": "Request rainfall", "reason": "Missing weather CSV"}
        first = self.call("create_follow_up_task", args, "task-1")
        self.assertTrue(first["ok"], first)
        second = self.call("create_follow_up_task", args, "task-2")
        self.assertEqual(first["data"]["task_id"], second["data"]["task_id"])
        package = self.service.load_package(self.tools.investigation_id)
        self.assertEqual(len(package["tasks"]), 1)
        self.assertEqual(package["investigation"]["status"], "NEEDS_EVIDENCE")
        self.all_evidence()
        self.assertTrue(self.call("save_investigation_report")["ok"])
        self.assertFalse(self.call("set_case_status", {"status": "READY_FOR_ADJUSTER_REVIEW", "reason": "try"})["ok"])

    def test_report_and_transition_gates(self):
        self.assertFalse(self.call("save_investigation_report")["ok"])
        self.assertFalse(self.call("set_case_status", {"status": "READY_FOR_ADJUSTER_REVIEW", "reason": "try"})["ok"])
        self.assertTrue(self.call("set_case_status", {"status": "NEEDS_EVIDENCE", "reason": "missing"}, "needs")["ok"])
        self.assertTrue(self.call("set_case_status", {"status": "INVESTIGATING", "reason": "resume"}, "resume")["ok"])

    def test_conflict_blocks_ready_without_open_tasks(self):
        self.tools = AgentTools.start(self.service, {**self.metadata, "claimed_crop": "Soybeans"}, self.assets)
        self.all_evidence()
        self.assertTrue(self.call("save_investigation_report")["ok"])
        self.assertFalse(self.call("set_case_status", {"status": "READY_FOR_ADJUSTER_REVIEW", "reason": "try"})["ok"])

    def test_asset_change_and_path_escape(self):
        with self.assertRaises(ValueError):
            replace(self.assets, boundary=str(Path(__file__).resolve()))
        (self.root / "weather.csv").write_text("changed")
        result = self.call("check_rainfall")
        self.assertFalse(result["ok"])
        self.assertIn("assets changed", result["error"]["message"])

    def test_execution_error_is_visible_and_audited(self):
        with patch("agent_tools.crop_finding", side_effect=RuntimeError("Raster read failed")):
            result = self.call("check_crop_classification")
        self.assertFalse(result["ok"])
        self.assertIn("Raster read failed", result["error"]["message"])
        package = self.service.load_package(self.tools.investigation_id)
        self.assertEqual(package["actions"][0]["result"], result)
        self.assertEqual(package["evidence"], [])

    def test_nan_weather_rejected_and_schema_is_isolated(self):
        (self.root / "weather.csv").write_text("date,precipitation,normal_precipitation\n2026-07-18,nan,3\n")
        self.tools = AgentTools.start(self.service, self.metadata, self.assets)
        self.assertFalse(self.call("check_rainfall")["ok"])
        schemas = self.tools.schemas()
        schemas[0]["name"] = "exec"
        self.assertEqual(self.tools.schemas()[0]["name"], "get_claim")


if __name__ == "__main__":
    unittest.main()
