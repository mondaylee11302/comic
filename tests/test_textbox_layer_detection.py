from __future__ import annotations

import unittest

import numpy as np

from comic_splitter.psd_preprocess import (
    TextItem,
    _build_text_union_mask,
    _detect_raster_text_layers_by_union,
    rank_bubble_layers_by_text_union,
)


class _FakeLayer:
    def __init__(self, layer_id: int, bbox: tuple[int, int, int, int], rgba: np.ndarray, kind: str = "pixel") -> None:
        self.layer_id = int(layer_id)
        self.bbox = bbox
        self._rgba = rgba
        self.kind = kind
        self.visible = True
        self.parent = None
        self.name = f"layer_{layer_id}"

    def numpy(self) -> np.ndarray:
        return self._rgba

    def composite(self) -> np.ndarray:
        return self._rgba


class _FakePsd:
    def __init__(self, width: int, height: int, layers: list[_FakeLayer]) -> None:
        self.size = (width, height)
        self._layers = layers

    def descendants(self) -> list[_FakeLayer]:
        return self._layers


def _rgba_with_alpha(alpha: np.ndarray) -> np.ndarray:
    h, w = alpha.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    return rgba


class TextboxLayerDetectionTests(unittest.TestCase):
    def test_build_text_union_mask(self) -> None:
        texts = [
            TextItem(
                text_id="t1",
                text="A",
                bbox=[10, 8, 22, 18],
                source="merged",
                conf=1.0,
                layer_id=-1,
                layer_path="",
                quad=None,
            ),
            TextItem(
                text_id="t2",
                text="B",
                bbox=[30, 20, 42, 30],
                source="merged",
                conf=1.0,
                layer_id=-1,
                layer_path="",
                quad=[[30.0, 20.0], [42.0, 20.0], [42.0, 30.0], [30.0, 30.0]],
            ),
        ]
        mask = _build_text_union_mask(texts=texts, width=64, height=40)
        self.assertEqual(int(mask[10, 12]), 255)
        self.assertEqual(int(mask[24, 34]), 255)
        self.assertEqual(int(mask[2, 2]), 0)

    def test_build_text_union_mask_connect_lines_and_expand(self) -> None:
        # Two nearby lines should be connected into one box and then expanded.
        texts = [
            TextItem(
                text_id="l1",
                text="line1",
                bbox=[20, 20, 60, 30],
                source="merged",
                conf=1.0,
                layer_id=-1,
                layer_path="",
                quad=None,
            ),
            TextItem(
                text_id="l2",
                text="line2",
                bbox=[22, 33, 62, 43],
                source="merged",
                conf=1.0,
                layer_id=-1,
                layer_path="",
                quad=None,
            ),
        ]
        mask = _build_text_union_mask(texts=texts, width=120, height=120)
        # Original gap center now should be covered because line boxes are connected and expanded.
        self.assertEqual(int(mask[31, 40]), 255)
        # Expansion grows left/top beyond original first line bbox.
        self.assertEqual(int(mask[16, 16]), 255)

    def test_detect_raster_text_layers_by_union(self) -> None:
        union_mask = np.zeros((20, 30), dtype=np.uint8)
        union_mask[:, :15] = 255

        alpha_in = np.full((20, 15), 255, dtype=np.uint8)  # 100% in union
        alpha_out = np.full((20, 15), 255, dtype=np.uint8)  # 0% in union

        layer_in = _FakeLayer(1, (0, 0, 15, 20), _rgba_with_alpha(alpha_in), kind="pixel")
        layer_out = _FakeLayer(2, (15, 0, 30, 20), _rgba_with_alpha(alpha_out), kind="pixel")
        psd = _FakePsd(width=30, height=20, layers=[layer_in, layer_out])

        picked = _detect_raster_text_layers_by_union(
            psd=psd,
            text_union_mask=union_mask,
            in_union_ratio_thr=0.85,
            alpha_thr=10,
            min_pixels=20,
            runtime_id_by_obj=None,
            exclude_layer_ids=None,
        )
        self.assertEqual(picked, [1])

    def test_rank_bubble_layers_by_text_union(self) -> None:
        union_mask = np.zeros((20, 30), dtype=np.uint8)
        union_mask[:, :18] = 255

        alpha_full = np.full((20, 20), 255, dtype=np.uint8)
        alpha_part = np.full((20, 10), 255, dtype=np.uint8)

        # layer_a: bbox [0,20], overlap ratio = 18/20 = 0.9 -> keep
        layer_a = _FakeLayer(11, (0, 0, 20, 20), _rgba_with_alpha(alpha_full), kind="pixel")
        # layer_b: bbox [20,30], overlap ratio = 0.0 -> drop
        layer_b = _FakeLayer(12, (20, 0, 30, 20), _rgba_with_alpha(alpha_part), kind="group")
        psd = _FakePsd(width=30, height=20, layers=[layer_a, layer_b])

        ranking, _ = rank_bubble_layers_by_text_union(
            psd=psd,
            text_union_mask=union_mask,
            overlap_ratio_thr=0.60,
            alpha_thr=10,
            min_pixels=20,
            exclude_layer_ids=None,
            runtime_id_by_obj=None,
        )
        self.assertEqual([r.layer_id for r in ranking], [11])
        self.assertGreaterEqual(float(ranking[0].score), 0.89)


if __name__ == "__main__":
    unittest.main()
