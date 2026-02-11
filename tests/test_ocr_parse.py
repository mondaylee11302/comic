from __future__ import annotations

import json
import unittest

from volc_imagex.ocr import (
    _filter_multilang_ocr_infos,
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

    def test_parse_paddle_pruned_result_block_content_and_bbox(self) -> None:
        raw_output = {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "parsing_res_list": [
                            {
                                "block_label": "paragraph_title",
                                "block_content": "HELLO OCR 123\nTEST TEXT",
                                "block_bbox": [48, 66, 572, 234],
                            }
                        ]
                    }
                }
            ]
        }
        texts = _parse_general_output(raw_output)
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text, "HELLO OCR 123\nTEST TEXT")
        self.assertEqual(texts[0].quad, [[48.0, 66.0], [572.0, 66.0], [572.0, 234.0], [48.0, 234.0]])

    def test_parse_volc_data_detail_string(self) -> None:
        volc_detail = [
            {
                "page_id": 0,
                "textblocks": [
                    {
                        "text": "Article 2: Active region PIC experiment",
                        "label": "para",
                        "box": {"x0": 172, "y0": 175, "x1": 591, "y1": 207},
                    }
                ],
            }
        ]
        resp = {
            "code": 10000,
            "request_id": "req-volc-1",
            "data": {
                "markdown": "Article 2: Active region PIC experiment",
                "detail": json.dumps(volc_detail, ensure_ascii=False),
            },
        }
        parsed_output, request_id = parse_ai_process_response(resp)
        self.assertEqual(request_id, "req-volc-1")
        self.assertIn("detail", parsed_output)
        self.assertIsInstance(parsed_output["detail"], list)
        self.assertEqual(parsed_output["detail"][0]["page_id"], 0)

    def test_parse_general_volc_textblocks_box_dict(self) -> None:
        raw_output = {
            "detail": [
                {
                    "page_id": 0,
                    "textblocks": [
                        {
                            "text": "Volc OCR paragraph",
                            "label": "para",
                            "box": {"x0": 12, "y0": 34, "x1": 156, "y1": 78},
                        }
                    ],
                }
            ]
        }
        texts = _parse_general_output(raw_output)
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text, "Volc OCR paragraph")
        self.assertEqual(texts[0].quad, [[12.0, 34.0], [156.0, 34.0], [156.0, 78.0], [12.0, 78.0]])

    def test_parse_general_multilang_ocr_infos(self) -> None:
        raw_output = {
            "ocr_infos": [
                {
                    "lang": "ko",
                    "prob": "0.984",
                    "rect": [[10, 20], [100, 20], [100, 45], [10, 45]],
                    "text": "안녕하세요",
                }
            ]
        }
        texts = _parse_general_output(raw_output)
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].text, "안녕하세요")
        self.assertEqual(texts[0].quad, [[10.0, 20.0], [100.0, 20.0], [100.0, 45.0], [10.0, 45.0]])
        self.assertAlmostEqual(texts[0].confidence or 0.0, 0.984, places=6)

    def test_filter_multilang_zh_keeps_not_lang(self) -> None:
        parsed = {
            "ocr_infos": [
                {"lang": "zh", "text": "中文"},
                {"lang": "ko", "text": "한국어"},
                {"lang": "not_lang", "text": "123"},
            ]
        }
        out = _filter_multilang_ocr_infos(parsed, "zh")
        infos = out.get("ocr_infos", [])
        self.assertEqual(len(infos), 2)
        langs = [str(x.get("lang")) for x in infos]
        self.assertEqual(langs, ["zh", "not_lang"])


if __name__ == "__main__":
    unittest.main()
