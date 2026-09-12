import io
import json
import unittest
from unittest.mock import patch

from local_narrative import check_local_model


class LocalInferenceTests(unittest.TestCase):
    def test_probe_uses_only_openshell_route(self):
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": "LOCAL_MODEL_READY"}}]}).encode())
        with patch("local_narrative.urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(check_local_model(), "LOCAL_MODEL_READY")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://inference.local/v1/chat/completions")
        self.assertEqual(request.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
