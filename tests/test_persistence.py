import copy
import unittest
from unittest.mock import patch

import mongomock

from investigations import InvestigationService
from persistence import MongoStore


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.store = MongoStore(mongomock.MongoClient(tz_aware=True).test_cases)
        self.store.ensure_indexes()
        self.service = InvestigationService(self.store)
        self.report = {
            "claim_id": "CASE-1", "reported_cause": "Drought",
            "reported_loss_date": "2026-07-18", "field": "North",
            "synthetic_demo": True,
            "findings": [{"check": "Rainfall", "status": "inconclusive",
                          "source": "Synthetic", "detail": "Missing normals", "values": {}}],
        }

    def save(self):
        return self.service.save_package(self.report, "inputs-1", {"claimed_crop": "Corn"})

    def test_reopen_without_session_and_deduplicate(self):
        key = self.save()
        self.assertEqual(key, self.save())
        reopened = InvestigationService(self.store).load_package(key)
        self.assertEqual(reopened["report"], self.report)
        self.assertTrue(reopened["investigation"]["persistence_complete"])
        for name in ("claims", "investigations", "evidence", "reports"):
            self.assertEqual(self.store.db[name].count_documents({}), 1, name)
        self.assertEqual(len(reopened["actions"]), 2)
        self.assertTrue(all(a["actor"] == "application" for a in reopened["actions"]))

    def test_changed_evidence_preserves_history(self):
        first = self.save()
        self.report["findings"][0]["status"] = "supported"
        second = self.save()
        self.assertNotEqual(first, second)
        self.assertEqual(self.service.load_package(first)["report"]["findings"][0]["status"], "inconclusive")
        self.assertEqual(self.store.db.claims.count_documents({}), 1)

    def test_tasks_deduplicate_and_gate_ready(self):
        key = self.save()
        task = self.service.create_follow_up_task(key, "Get normals", "Missing weather normals")
        self.assertEqual(task, self.service.create_follow_up_task(key, "Get normals", "Missing weather normals"))
        self.assertEqual(self.store.db.follow_up_tasks.count_documents({}), 1)
        with self.assertRaises(ValueError):
            self.service.set_case_status(key, "READY_FOR_ADJUSTER_REVIEW", "ready")
        with self.assertRaises(ValueError):
            self.service.resolve_follow_up_task(key, task, " ")
        self.assertTrue(self.service.resolve_follow_up_task(key, task, "Adjuster obtained normals"))
        self.service.set_case_status(key, "READY_FOR_ADJUSTER_REVIEW", "Human reviewed")
        self.assertEqual(self.service.load_package(key)["investigation"]["status"], "READY_FOR_ADJUSTER_REVIEW")
        # A Streamlit rerun/save must not reset reviewed status or reopen tasks.
        self.save()
        self.assertEqual(self.service.load_package(key)["investigation"]["status"], "READY_FOR_ADJUSTER_REVIEW")

    def test_partial_save_retry(self):
        with patch.object(self.service, "save_report", side_effect=RuntimeError("Disconnected")):
            with self.assertRaises(RuntimeError):
                self.save()
        record = self.store.db.investigations.find_one()
        self.assertFalse(record["persistence_complete"])
        with self.assertRaises(ValueError):
            self.service.set_case_status(record["_id"], "READY_FOR_ADJUSTER_REVIEW", "ready")
        key = self.save()
        self.assertEqual(key, record["_id"])
        self.assertTrue(self.service.load_package(key)["investigation"]["persistence_complete"])
        self.assertEqual(self.store.db.evidence.count_documents({}), 1)

    def test_invalid_actions_and_cross_claim_report(self):
        key = self.save()
        for status in ("APPROVED", "DENIED", "garbage"):
            with self.assertRaises(ValueError):
                self.service.set_case_status(key, status, "test")
        wrong = copy.deepcopy(self.report)
        wrong["claim_id"] = "CASE-2"
        with self.assertRaises(ValueError):
            self.service.save_report(key, wrong)
        with self.assertRaises(ValueError):
            self.service.create_follow_up_task("missing", "Task", "Reason")

    def test_missing_uri_is_explicit(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "MONGODB_URI"):
                MongoStore.from_env()


if __name__ == "__main__":
    unittest.main()
