from __future__ import annotations

import json
import unittest

from volc_imagex.ocr import (
    _parse_general_output,
    _parse_license_output,
    parse_ai_process_response,
)


class OCRParseTests(unittest.TestCase):
    def test_parse_general_with_confidence_and_location(self) -> None:
        raw_output = {
            "Texts": [
                {
                    "Content": "Hello OCR",
                    "Location": [[10, 20], [110, 20], [110, 50], [10, 50]],
                    "Confidence": 0.97,
                }
            ]
        }
        texts = _parse_general_output(raw_output)
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text, "Hello OCR")
        self.assertEqual(texts[0].quad, [[10.0, 20.0], [110.0, 20.0], [110.0, 50.0], [10.0, 50.0]])
        self.assertAlmostEqual(texts[0].confidence or 0.0, 0.97, places=6)

    def test_parse_license_field_map(self) -> None:
        raw_output = {
            "LicenseInfo": {
                "USCC": {
                    "Content": "91330100123456789A",
                    "Location": [[1, 2], [101, 2], [101, 22], [1, 22]],
                },
                "name": {
                    "Content": "Example Co., Ltd.",
                    "Location": [[1, 30], [180, 30], [180, 52], [1, 52]],
                },
            }
        }
        fields = _parse_license_output(raw_output)
        self.assertIn("USCC", fields)
        self.assertIn("name", fields)
        self.assertEqual(fields["USCC"].text, "91330100123456789A")
        self.assertEqual(fields["name"].text, "Example Co., Ltd.")
        self.assertEqual(fields["USCC"].quad, [[1.0, 2.0], [101.0, 2.0], [101.0, 22.0], [1.0, 22.0]])

    def test_parse_ai_process_output_as_json_string(self) -> None:
        nested_output = {
            "Texts": [
                {
                    "Content": "Escaped JSON",
                    "Location": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    "Confidence": 0.8,
                }
            ]
        }
        # Simulate Output being an escaped JSON string.
        resp = {
            "ResponseMetadata": {"RequestId": "req-test-1"},
            "Result": {
                "Output": json.dumps(json.dumps(nested_output, ensure_ascii=False), ensure_ascii=False),
            },
        }
        parsed_output, request_id = parse_ai_process_response(resp)
        self.assertEqual(request_id, "req-test-1")
        self.assertEqual(parsed_output, nested_output)


if __name__ == "__main__":
    unittest.main()
