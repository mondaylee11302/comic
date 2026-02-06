from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np

from comic_splitter.common.types import Band
from comic_splitter.stage1.features import RowFeatures


def _slice_mean(x: np.ndarray, y1: int, y2: int) -> float:
    if y2 <= y1:
        return 0.0
    return float(np.mean(x[y1:y2]))


def _band_content_score(
    band: Band,
    feats: RowFeatures,
    edge_norm_ref: float,
) -> Tuple[float, Dict[str, float]]:
    y1 = max(0, int(band.y1))
    y2 = min(int(feats.gray.shape[0]), int(band.y2))
    if y2 <= y1:
        return 0.0, {"non_white": 0.0, "edge_mean": 0.0}

    non_white = float(np.clip(1.0 - _slice_mean(feats.white_ratio, y1, y2), 0.0, 1.0))
    edge_mean = float(np.clip(_slice_mean(feats.edge_density, y1, y2), 0.0, 1.0))
    edge_norm = float(np.clip(edge_mean / max(edge_norm_ref, 1e-6), 0.0, 1.0))

    # Content is mainly non-white area plus structural edges.
    score = float(np.clip(0.6 * non_white + 0.4 * edge_norm, 0.0, 1.0))
    return score, {"non_white": non_white, "edge_mean": edge_mean}


def refine_low_content_bands(
    bands: List[Band],
    feats: RowFeatures,
    min_band_h: int,
    small_ratio: float = 0.85,
    edge_small_ratio: float = 1.4,
    content_thr: float = 0.17,
    edge_norm_ref: float = 0.02,
    edge_pos_boost: float = 1.25,
) -> List[Band]:
    if len(bands) <= 1:
        return bands

    out = [Band(y1=b.y1, y2=b.y2, score=b.score, reason=b.reason, meta=dict(b.meta)) for b in bands]
    small_h = max(1, int(min_band_h * small_ratio))
    edge_small_h = max(small_h, int(min_band_h * edge_small_ratio))
    i = 0

    while i < len(out):
        cur = out[i]
        if cur.reason == "black_bar_band":
            i += 1
            continue
        cur_h = int(cur.y2 - cur.y1)
        height_limit = edge_small_h if i == 0 or i == len(out) - 1 else small_h
        if cur_h >= height_limit:
            i += 1
            continue

        cur_score, cur_info = _band_content_score(cur, feats, edge_norm_ref=edge_norm_ref)
        thr = content_thr * (edge_pos_boost if i == 0 or i == len(out) - 1 else 1.0)
        if cur_score >= thr:
            i += 1
            continue

        left_ok = i > 0 and out[i - 1].reason != "black_bar_band"
        right_ok = i < len(out) - 1 and out[i + 1].reason != "black_bar_band"
        if not left_ok and not right_ok:
            i += 1
            continue

        if left_ok and right_ok:
            left_score, _ = _band_content_score(out[i - 1], feats, edge_norm_ref=edge_norm_ref)
            right_score, _ = _band_content_score(out[i + 1], feats, edge_norm_ref=edge_norm_ref)
            left_h = max(1, int(out[i - 1].y2 - out[i - 1].y1))
            right_h = max(1, int(out[i + 1].y2 - out[i + 1].y1))
            left_rank = left_score + 0.15 * float(np.clip(left_h / max(min_band_h, 1), 0.0, 1.0))
            right_rank = right_score + 0.15 * float(np.clip(right_h / max(min_band_h, 1), 0.0, 1.0))
            tgt_idx = i - 1 if left_rank >= right_rank else i + 1
        elif left_ok:
            tgt_idx = i - 1
        else:
            tgt_idx = i + 1

        src = out[i]
        tgt = out[tgt_idx]
        merged = Band(
            y1=min(int(src.y1), int(tgt.y1)),
            y2=max(int(src.y2), int(tgt.y2)),
            score=max(float(src.score), float(tgt.score)),
            reason=tgt.reason,
            meta={
                **dict(tgt.meta),
                "merged_low_content": {
                    "y1": int(src.y1),
                    "y2": int(src.y2),
                    "content_score": float(cur_score),
                    "threshold": float(thr),
                    "non_white": float(cur_info["non_white"]),
                    "edge_mean": float(cur_info["edge_mean"]),
                },
            },
        )

        out[tgt_idx] = merged
        del out[i]
        i = max(0, i - 1)

    out = sorted(out, key=lambda b: b.y1)
    return out
