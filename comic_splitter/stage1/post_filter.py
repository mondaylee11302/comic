from __future__ import annotations

from typing import List
import numpy as np

from comic_splitter.common.types import CutCandidate
from comic_splitter.stage1.features import RowFeatures


def _window_stats(gray: np.ndarray, edge: np.ndarray, y1: int, y2: int) -> tuple[float, float]:
    if y2 <= y1:
        return 0.0, 0.0
    g = gray[y1:y2]
    e = edge[y1:y2]
    return float(np.mean(g)), float(np.mean(e))


def apply_content_difference_filter(
    candidates: List[CutCandidate],
    feats: RowFeatures,
    window_h: int = 64,
    gray_diff_thr: float = 0.02,
    edge_diff_thr: float = 0.002,
    min_scale: float = 0.4,
) -> List[CutCandidate]:
    """
    Reduce strength when content above/below cut looks too similar.
    gray_diff_thr and edge_diff_thr are relative ratios to [0, 255] and [0,1].
    """
    if not candidates:
        return candidates

    H = feats.gray.shape[0]
    gray = feats.gray.astype(np.float32)
    edge = feats.edge_density.astype(np.float32)

    out: List[CutCandidate] = []
    for c in candidates:
        y = int(c.y)
        y1a = max(0, y - window_h)
        y2a = max(0, y)
        y1b = min(H, y)
        y2b = min(H, y + window_h)

        g1, e1 = _window_stats(gray, edge, y1a, y2a)
        g2, e2 = _window_stats(gray, edge, y1b, y2b)

        gdiff = abs(g1 - g2) / 255.0
        ediff = abs(e1 - e2)

        if gdiff < gray_diff_thr and ediff < edge_diff_thr:
            scale = min_scale + (gdiff / max(gray_diff_thr, 1e-6)) * (1.0 - min_scale)
            scale = float(np.clip(scale, min_scale, 1.0))
            c.strength = float(np.clip(c.strength * scale, 0.0, 1.0))
            c.meta = {
                **c.meta,
                "content_diff": {
                    "gdiff": float(gdiff),
                    "ediff": float(ediff),
                    "scale": float(scale),
                },
            }
        out.append(c)
    return out
