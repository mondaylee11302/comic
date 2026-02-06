from __future__ import annotations

from typing import List
import numpy as np

from comic_splitter.common.types import CutCandidate
from comic_splitter.stage1.features import RowFeatures


def detect_gutters(
    feats: RowFeatures,
    min_gap_h: int = 18,
    white_ratio_thr: float = 0.985,
    edge_density_thr: float = 0.006,
) -> List[CutCandidate]:
    white_ok = feats.white_ratio >= white_ratio_thr
    edge_ok = feats.edge_density <= edge_density_thr
    mask = white_ok & edge_ok

    candidates: List[CutCandidate] = []
    H = mask.shape[0]
    y = 0
    while y < H:
        if not mask[y]:
            y += 1
            continue
        y1 = y
        while y < H and mask[y]:
            y += 1
        y2 = y
        if (y2 - y1) >= min_gap_h:
            yc = (y1 + y2) // 2
            w = float(np.clip(feats.white_ratio[yc], 0, 1))
            e = float(
                np.clip(
                    1.0 - feats.edge_density[yc] / max(edge_density_thr, 1e-6),
                    0,
                    1,
                )
            )
            thick = float(np.clip((y2 - y1) / max(min_gap_h * 2, 1), 0, 1))
            strength = 0.5 * w + 0.3 * e + 0.2 * thick
            candidates.append(
                CutCandidate(
                    y=yc,
                    strength=strength,
                    type="gutter",
                    span=(y1, y2),
                    meta={"w": w, "e": e, "thick": thick, "y1": y1, "y2": y2},
                )
            )
    return candidates
