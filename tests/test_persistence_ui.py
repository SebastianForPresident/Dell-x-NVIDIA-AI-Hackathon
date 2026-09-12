import unittest
from unittest.mock import patch

import mongomock
from streamlit.testing.v1 import AppTest

from investigations import InvestigationService
from persistence import MongoStore


class PersistenceUITests(unittest.TestCase):
    def test_demo_save_and_reopen_in_fresh_session(self):
        service = InvestigationService(MongoStore(mongomock.MongoClient().ui_test))
        with patch("persistence_ui.get_service", return_value=service):
            app = AppTest.from_file("../app.py").run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            next(b for b in app.button if b.label == "Save evidence package to MongoDB").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(service.store.db.reports.count_documents({}), 1)
            # A different session has no working report cache or remembered selection.
            reopened = AppTest.from_file("../app.py").run(timeout=30)
            reopened.radio[0].set_value("Upload case files").run()
            self.assertEqual(len(reopened.exception), 0)
            self.assertTrue(any(s.label == "Saved investigation" for s in reopened.selectbox))

    def test_offline_preview_survives(self):
        with patch("persistence_ui.get_service", side_effect=RuntimeError("offline")):
            app = AppTest.from_file("../app.py").run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("Persistence unavailable" in warning.value for warning in app.warning))
            self.assertTrue(any(s.value == "Evidence package" for s in app.subheader))


if __name__ == "__main__":
    unittest.main()

