from __future__ import annotations

import unittest

from comic_splitter.psd_preprocess import TextItem, _resolve_geometry


class GeometryContractTests(unittest.TestCase):
    def test_quad_has_priority_over_bbox(self) -> None:
        item = TextItem(
            text_id="t1",
            text="hello",
            bbox=[0, 0, 1, 1],
            source="test",
            conf=1.0,
            layer_id=-1,
            layer_path="",
            quad=[[10, 20], [110, 20], [110, 60], [10, 60]],
            geom_source="ocr_quad",
        )
        out = _resolve_geometry(item, width=200, height=100)
        self.assertEqual(out.bbox, [10, 20, 110, 60])
        self.assertAlmostEqual(out.canvas_norm_bbox[0], 0.05)
        self.assertAlmostEqual(out.canvas_norm_bbox[3], 0.60)

    def test_bbox_fallback_and_norm_clip(self) -> None:
        item = TextItem(
            text_id="t2",
            text="hello",
            bbox=[-10, -20, 210, 120],
            source="test",
            conf=1.0,
            layer_id=-1,
            layer_path="",
            quad=None,
            geom_source="psd_bbox",
        )
        out = _resolve_geometry(item, width=200, height=100)
        self.assertEqual(out.bbox, [-10, -20, 210, 120])
        self.assertEqual(out.canvas_norm_bbox, [0.0, 0.0, 1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
