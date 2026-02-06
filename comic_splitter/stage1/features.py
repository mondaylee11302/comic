from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class RowFeatures:
    gray: np.ndarray
    white_ratio: np.ndarray
    dark_ratio: np.ndarray
    edge_density: np.ndarray


def _smooth_1d(x: np.ndarray, k: int = 21) -> np.ndarray:
    if k <= 1:
        return x
    k = int(k) | 1  # force odd
    kernel = np.ones(k, dtype=np.float32) / float(k)
    return np.convolve(x.astype(np.float32), kernel, mode="same")


def extract_row_features(
    rgb: np.ndarray,
    white_thr: int = 245,
    dark_thr: int = 40,
    canny1: int = 40,
    canny2: int = 120,
    smooth_k: int = 21,
) -> RowFeatures:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be HxWx3")
    if rgb.dtype != np.uint8:
        rgb = rgb.astype(np.uint8)

    gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)

    white = (gray > white_thr).astype(np.float32)
    dark = (gray < dark_thr).astype(np.float32)

    edges = cv2.Canny(gray, canny1, canny2)
    edge_bin = (edges > 0).astype(np.float32)

    white_ratio = white.mean(axis=1)
    dark_ratio = dark.mean(axis=1)
    edge_density = edge_bin.mean(axis=1)

    white_ratio = _smooth_1d(white_ratio, smooth_k)
    dark_ratio = _smooth_1d(dark_ratio, smooth_k)
    edge_density = _smooth_1d(edge_density, smooth_k)

    return RowFeatures(
        gray=gray,
        white_ratio=white_ratio,
        dark_ratio=dark_ratio,
        edge_density=edge_density,
    )
