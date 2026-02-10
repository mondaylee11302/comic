from __future__ import annotations

import unittest

from comic_splitter.stage2.text_export import (
    build_panel_text_rows,
    build_unified_text_panel_map,
    to_panel_rel_bbox,
)


class PanelTextExportTests(unittest.TestCase):
    def test_panel_rel_bbox_normal(self) -> None:
        rel = to_panel_rel_bbox([110, 210, 150, 250], [100, 200, 300, 400])
        self.assertEqual(rel, [10, 10, 50, 50])

    def test_panel_rel_bbox_clamped(self) -> None:
        rel = to_panel_rel_bbox([80, 180, 130, 230], [100, 200, 300, 400])
        self.assertEqual(rel, [0, 0, 30, 30])

    def test_panel_rel_bbox_empty(self) -> None:
        rel = to_panel_rel_bbox([0, 0, 50, 50], [100, 200, 300, 400])
        self.assertEqual(rel, [0, 0, 0, 0])

    def test_primary_assignment_and_reading_order(self) -> None:
        texts_payload = [
            {"text_id": "t1", "text": "A", "bbox": [120, 220, 150, 250], "quad": None},
            {"text_id": "t2", "text": "B", "bbox": [110, 205, 130, 215], "quad": None},
            {"text_id": "t3", "text": "C", "bbox": [310, 210, 330, 230], "quad": None},
        ]
        panels_payload_raw = [
            {"panel_id": "panel_001", "bbox": [100, 200, 200, 300]},
            {"panel_id": "panel_002", "bbox": [300, 200, 400, 300]},
        ]
        mapping_v2_payload = [
            {
                "text_id": "t1",
                "primary_panel_id": "panel_001",
                "assignment_score": 0.95,
                "candidate_panels": [
                    {"panel_id": "panel_001", "score": 0.95},
                    {"panel_id": "panel_002", "score": 0.45},
                ],
            },
            {
                "text_id": "t2",
                "primary_panel_id": "panel_001",
                "assignment_score": 0.98,
                "candidate_panels": [{"panel_id": "panel_001", "score": 0.98}],
            },
            {
                "text_id": "t3",
                "primary_panel_id": "panel_002",
                "assignment_score": 0.93,
                "candidate_panels": [{"panel_id": "panel_002", "score": 0.93}],
            },
        ]

        unified = build_unified_text_panel_map(texts_payload, mapping_v2_payload, panels_payload_raw)
        rows_by_panel = build_panel_text_rows(unified)

        panel1_rows = rows_by_panel["panel_001"]
        self.assertEqual([row["text_id"] for row in panel1_rows], ["t2", "t1"])

        panel2_rows = rows_by_panel["panel_002"]
        self.assertEqual([row["text_id"] for row in panel2_rows], ["t3"])
        self.assertFalse(any(row["text_id"] == "t1" for row in panel2_rows))


if __name__ == "__main__":
    unittest.main()
