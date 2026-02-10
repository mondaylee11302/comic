from __future__ import annotations

import unittest

from scripts.run_stage2 import build_text_panel_map_v2


class TextPanelMapV2Tests(unittest.TestCase):
    def test_primary_and_candidates(self) -> None:
        texts = [
            {
                "text_id": "text_001",
                "bbox": [10, 10, 90, 70],
                "quad": None,
            }
        ]
        panels = [
            {"panel_id": "panel_001", "bbox": [0, 0, 100, 100]},
            {"panel_id": "panel_002", "bbox": [80, 0, 180, 100]},
            {"panel_id": "panel_003", "bbox": [300, 300, 380, 380]},
        ]

        rows = build_text_panel_map_v2(texts, panels, top_k=3, min_score=0.1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["primary_panel_id"], "panel_001")
        self.assertGreaterEqual(len(row["candidate_panels"]), 1)
        self.assertEqual(row["method"], "overlap+center")


if __name__ == "__main__":
    unittest.main()
