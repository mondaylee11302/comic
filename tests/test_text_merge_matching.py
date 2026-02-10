from __future__ import annotations

import unittest

from comic_splitter.psd_preprocess import TextItem, _resolve_geometry, merge_text_items


def _t(
    text_id: str,
    text: str,
    bbox: list[int],
    quad: list[list[float]] | None,
    text_source: str,
    layer_id: int,
) -> TextItem:
    return TextItem(
        text_id=text_id,
        text=text,
        bbox=bbox,
        source=text_source,
        conf=1.0,
        layer_id=layer_id,
        layer_path="",
        quad=quad,
        geom_source="ocr_quad" if quad else "psd_bbox",
        text_source=text_source,
    )


class TextMergeMatchingTests(unittest.TestCase):
    def test_bipartite_matching_and_conflict_policy(self) -> None:
        psd = [
            _resolve_geometry(_t("psd_1", "Hello World", [10, 10, 110, 60], None, "psd", 1), 400, 400),
            _resolve_geometry(_t("psd_2", "Another", [200, 50, 320, 100], None, "psd", 2), 400, 400),
        ]
        ocr = [
            _resolve_geometry(
                _t("ocr_1", "hello world", [12, 12, 108, 58], [[12, 12], [108, 12], [108, 58], [12, 58]], "ocr", -1),
                400,
                400,
            ),
            _resolve_geometry(
                _t("ocr_2", "noise", [250, 200, 320, 240], [[250, 200], [320, 200], [320, 240], [250, 240]], "ocr", -1),
                400,
                400,
            ),
        ]
        merged, stats = merge_text_items(psd, ocr, width=400, height=400)
        self.assertEqual(stats["merge_unmatched_psd_count"], 1)
        self.assertEqual(stats["merge_unmatched_ocr_count"], 1)

        first = next(x for x in merged if x.merge_status == "matched")
        self.assertEqual(first.text, "Hello World")  # PSD text wins
        self.assertIsNotNone(first.quad)  # OCR geometry wins


if __name__ == "__main__":
    unittest.main()
