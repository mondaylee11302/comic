from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from comic_splitter.script_agent import (
    ScriptAgentConfig,
    _looks_like_doubao_18_model,
    generate_panel_script,
    read_panel_text_jsonl,
    select_text_rows,
)


class ScriptAgentTests(unittest.TestCase):
    def test_model_name_guard(self) -> None:
        self.assertTrue(_looks_like_doubao_18_model("doubao-seed-1-8-251228"))
        self.assertTrue(_looks_like_doubao_18_model("ep-20260210123456-abcde"))
        self.assertFalse(_looks_like_doubao_18_model("doubao-seed-1-6-xxxx"))

    def test_select_rows_by_id_and_text(self) -> None:
        rows = [
            {"text_id": "text_001", "text": "第一句"},
            {"text_id": "text_002", "text": "第二句"},
            {"text_id": "text_003", "text": "第三句"},
        ]
        by_id = select_text_rows(rows, selected_text_ids=["text_002"])
        self.assertEqual(len(by_id), 1)
        self.assertEqual(by_id[0]["text_id"], "text_002")

        by_text = select_text_rows(rows, selected_texts=["第三"])
        self.assertEqual(len(by_text), 1)
        self.assertEqual(by_text[0]["text_id"], "text_003")

    def test_read_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "panel_001.txt"
            p.write_text(
                json.dumps({"text_id": "text_001", "text": "A"}, ensure_ascii=False) + "\n"
                + json.dumps({"text_id": "text_002", "text": "B"}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            rows = read_panel_text_jsonl(p)
            self.assertEqual(len(rows), 2)

    def test_local_fallback_generation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            img = np.full((64, 64, 3), 255, dtype=np.uint8)
            image_path = Path(td) / "panel_001.png"
            cv2.imwrite(str(image_path), img)

            selected_rows = [
                {"text_id": "text_001", "text": "你好"},
                {"text_id": "text_002", "text": "世界"},
            ]
            cfg = ScriptAgentConfig(
                api_key="",
                model_endpoint="doubao-seed-1-8-251228",
                allow_local_fallback=True,
                enforce_doubao_18=True,
            )
            result = generate_panel_script(
                panel_image_path=str(image_path),
                selected_rows=selected_rows,
                user_goal="测试",
                cfg=cfg,
            )
            self.assertIn("dialogue", result)
            self.assertGreaterEqual(len(result["dialogue"]), 2)
            self.assertEqual(result.get("meta", {}).get("backend"), "local_fallback")


if __name__ == "__main__":
    unittest.main()
