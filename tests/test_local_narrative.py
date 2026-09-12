import io
import json
import unittest
from unittest.mock import patch

from local_narrative import analyze_structured_case, check_local_model


class LocalInferenceTests(unittest.TestCase):
    def test_probe_uses_only_openshell_route(self):
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": "LOCAL_MODEL_READY"}}]}).encode())
        with patch("local_narrative.urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(check_local_model(), "LOCAL_MODEL_READY")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://inference.local/v1/chat/completions")
        self.assertEqual(request.get_method(), "POST")

    def test_structured_review_uses_case_data_and_requires_all_sections(self):
        case = {
            "id": "SYNTHETIC-1", "crop": "Corn", "cause": "Drought",
            "loss_date": "2026-07-18", "location": "Demo county", "synthetic_demo": True,
            "weather_series": [{"date": "2026-07-18", "rainfall": 1, "normal": 3}],
            "ndvi_series": [{"date": "2026-08-12", "ndvi": 0.44}],
            "report": {"findings": [{"check": "Precipitation", "status": "supported", "source": "Synthetic CSV"}]},
        }
        answer = {key: f"{key} summary" for key in ("weather", "vegetation", "crop", "neighbors", "overall")}
        with patch("local_narrative._local_chat", return_value=json.dumps(answer)) as chat:
            self.assertEqual(analyze_structured_case(case), answer)
        payload = json.loads(chat.call_args.args[1])
        self.assertEqual(payload["weather_series"], case["weather_series"])
        self.assertEqual(payload["measured_findings"], case["report"]["findings"])
        with patch("local_narrative._local_chat", return_value='{"overall":"Not enough data"}'):
            with self.assertRaisesRegex(ValueError, "five evidence summaries"):
                analyze_structured_case(case)


if __name__ == "__main__":
    unittest.main()
