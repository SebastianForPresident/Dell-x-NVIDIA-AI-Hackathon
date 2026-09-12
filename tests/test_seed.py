import unittest

from server.seed import demo_cases


class SeedDataTests(unittest.TestCase):
    def test_demo_cases_are_explicitly_synthetic_and_reviewable(self):
        cases = demo_cases()
        self.assertEqual(len(cases), 3)
        self.assertEqual(len({case["id"] for case in cases}), 3)
        self.assertTrue(all(case["synthetic_demo"] for case in cases))
        self.assertTrue(all(case["report"]["synthetic_demo"] for case in cases))
        self.assertTrue(all(len(case["report"]["findings"]) == 4 for case in cases))
        self.assertTrue(any(case["status"] == "Needs review" for case in cases))


if __name__ == "__main__":
    unittest.main()
