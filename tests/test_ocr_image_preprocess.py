from __future__ import annotations

import unittest

import numpy as np

from comic_splitter.psd_preprocess import prepare_ocr_input_image


class OCRImagePreprocessTests(unittest.TestCase):
    def test_resize_and_quality(self) -> None:
        np.random.seed(1)
        img = (np.random.rand(3000, 5000, 3) * 255).astype(np.uint8)
        data, meta, resized = prepare_ocr_input_image(img)
        self.assertLessEqual(int(meta["width"]), 3840)
        self.assertLessEqual(min(int(meta["width"]), int(meta["height"])), 2160)
        self.assertLess(int(meta["jpeg_bytes"]), 10 * 1024 * 1024)
        self.assertIn(int(meta["quality"]), (85, 75, 65, 55))
        self.assertEqual(resized.shape[1], int(meta["width"]))
        self.assertTrue(len(data) > 0)

    def test_raise_when_too_small_budget(self) -> None:
        np.random.seed(2)
        img = (np.random.rand(1200, 1800, 3) * 255).astype(np.uint8)
        with self.assertRaises(ValueError):
            prepare_ocr_input_image(img, max_bytes=3000)


if __name__ == "__main__":
    unittest.main()
