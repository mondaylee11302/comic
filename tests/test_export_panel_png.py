from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from comic_splitter.common.types import Band
from comic_splitter.stage2.export import export_panel_crops
from comic_splitter.stage2.types import PatchGraph


class ExportPanelPngTests(unittest.TestCase):
    def _build_inputs(self):
        rgb = np.full((120, 120, 3), 255, dtype=np.uint8)
        bands = [Band(y1=0, y2=120, score=1.0, reason="test")]
        graphs = {
            0: PatchGraph(
                band_index=0,
                labels=np.zeros((120, 120), dtype=np.int32),
                nodes={},
                boundary_costs={},
            )
        }
        regions = [
            {
                "region_id": 1,
                "band_index": 0,
                "node_ids": [],
                "score": 0.99,
                "bbox": [10, 10, 80, 80],
                "meta": {"area_ratio": 0.2},
            }
        ]
        return rgb, bands, graphs, regions

    def test_default_ext_is_jpg(self) -> None:
        rgb, bands, graphs, regions = self._build_inputs()
        with tempfile.TemporaryDirectory() as td:
            result = export_panel_crops(
                rgb=rgb,
                bands=bands,
                graphs=graphs,
                regions=regions,
                out_dir=td,
                prefix="case_default",
            )
            panel = result["panels"][0]
            self.assertTrue(str(panel["bbox_path"]).endswith("_bbox.jpg"))
            self.assertEqual(result.get("image_ext"), "jpg")
            self.assertTrue(Path(panel["bbox_path"]).exists())

    def test_png_ext(self) -> None:
        rgb, bands, graphs, regions = self._build_inputs()
        with tempfile.TemporaryDirectory() as td:
            result = export_panel_crops(
                rgb=rgb,
                bands=bands,
                graphs=graphs,
                regions=regions,
                out_dir=td,
                prefix="case_png",
                image_ext="png",
            )
            panel = result["panels"][0]
            self.assertTrue(str(panel["bbox_path"]).endswith(".png"))
            self.assertFalse(str(panel["bbox_path"]).endswith("_bbox.jpg"))
            self.assertEqual(result.get("image_ext"), "png")
            self.assertTrue(Path(panel["bbox_path"]).exists())


if __name__ == "__main__":
    unittest.main()
