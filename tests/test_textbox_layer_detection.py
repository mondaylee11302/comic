from __future__ import annotations

import unittest

import cv2
import numpy as np

from comic_splitter.psd_preprocess import (
    TextItem,
    WhiteComponent,
    _component_metrics,
    _component_quality,
    _score_layer_components,
)


class TextboxLayerDetectionTests(unittest.TestCase):
    def test_component_quality_metrics(self) -> None:
        mask = np.zeros((80, 120), dtype=np.uint8)
        cv2.rectangle(mask, (10, 10), (110, 70), 255, thickness=-1)
        cv2.rectangle(mask, (30, 25), (90, 55), 0, thickness=-1)
        solidity, hole_ratio = _component_metrics(mask)
        quality = _component_quality(solidity, hole_ratio)
        self.assertGreaterEqual(solidity, 0.65)
        self.assertGreater(hole_ratio, 0.0)
        self.assertLessEqual(hole_ratio, 0.35)
        self.assertGreaterEqual(quality, 0.0)

    def test_center_in_mask_scoring(self) -> None:
        mask = np.zeros((60, 100), dtype=np.uint8)
        cv2.rectangle(mask, (10, 10), (90, 50), 255, thickness=-1)
        comp = WhiteComponent(
            bbox=[100, 200, 200, 260],
            area_ratio=0.01,
            solidity=0.9,
            hole_ratio=0.1,
            quality=0.8,
            mask=mask,
            x0=100,
            y0=200,
        )
        text = TextItem(
            text_id="t1",
            text="abc",
            bbox=[120, 215, 180, 245],
            source="merged",
            conf=1.0,
            layer_id=3,
            layer_path="",
            quad=None,
            text_source="psd",
            geom_source="psd_bbox",
        )
        text_overlap, center_hit_ratio, white_quality, score, overlap_mean = _score_layer_components([comp], [text])
        self.assertGreaterEqual(text_overlap, 1.0)
        self.assertGreaterEqual(center_hit_ratio, 1.0)
        self.assertGreater(white_quality, 0.0)
        self.assertGreater(score, 0.5)
        self.assertGreater(overlap_mean, 0.2)


if __name__ == "__main__":
    unittest.main()
