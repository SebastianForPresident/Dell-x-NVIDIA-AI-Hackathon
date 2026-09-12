"""The local model review is saved without replacing measured evidence."""

import unittest
from unittest.mock import patch

import mongomock

from server.main import get_markdown_report, review_case_with_qwen
from server.seed import demo_cases


class AIReviewTests(unittest.TestCase):
    def test_review_is_persisted_alongside_original_findings(self):
        collection = mongomock.MongoClient().demo.cases
        original = demo_cases()[0]
        collection.insert_one(original)
        review = {key: f"{key} note" for key in ("weather", "vegetation", "crop", "neighbors", "overall")}
        with patch("server.main.cases", collection), \
             patch("server.main.case_document", side_effect=lambda case_id: collection.find_one({"id": case_id}, {"_id": 0})), \
             patch("server.main.analyze_structured_case", return_value=review) as model:
            self.assertEqual(review_case_with_qwen(original["id"]), {"ai_review": review})
            self.assertIn("weather note", get_markdown_report(original["id"]).body.decode())
        self.assertEqual(collection.find_one({"id": original["id"]})["ai_review"], review)
        self.assertEqual(collection.find_one({"id": original["id"]})["report"], original["report"])
        self.assertEqual(model.call_args.args[0]["weather_series"], original["weather_series"])


if __name__ == "__main__":
    unittest.main()
