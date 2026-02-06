from __future__ import annotations

from typing import List
import numpy as np

from comic_splitter.common.types import CutCandidate
from comic_splitter.stage1.features import RowFeatures


def detect_black_bars(
    feats: RowFeatures,
    min_bar_h: int = 24,
    dark_ratio_thr: float = 0.90,
    edge_density_max: float = 0.03,
) -> List[CutCandidate]:
    dark_ok = feats.dark_ratio >= dark_ratio_thr
    edge_ok = feats.edge_density <= edge_density_max
    mask = dark_ok & edge_ok

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
        if (y2 - y1) >= min_bar_h:
            yc = (y1 + y2) // 2
            d = float(np.clip(feats.dark_ratio[yc], 0, 1))
            e = float(np.clip(feats.edge_density[yc], 0, 1))
            thick = float(np.clip((y2 - y1) / max(min_bar_h * 2, 1), 0, 1))
            strength = 0.7 * d + 0.3 * thick
            candidates.append(
                CutCandidate(
                    y=yc,
                    strength=strength,
                    type="black_bar",
                    span=(y1, y2),
                    meta={"d": d, "e": e, "thick": thick, "y1": y1, "y2": y2},
                )
            )
    return candidates
