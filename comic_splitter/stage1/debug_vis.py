from __future__ import annotations

import os
import json
from typing import List
import cv2
import numpy as np

from comic_splitter.common.types import CutCandidate, Band
from comic_splitter.stage1.features import RowFeatures


_COLOR = {
    "gutter": (0, 255, 0),
    "black_bar": (0, 0, 255),
    "black_bar_band": (0, 165, 255),
    "hard_line": (255, 0, 0),
    "structure": (255, 255, 0),
}


def _plot_1d_curve(x: np.ndarray, width: int = 800, height: int = 200) -> np.ndarray:
    x = x.astype(np.float32)
    if x.size == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)
    vmin, vmax = float(np.min(x)), float(np.max(x))
    if vmax - vmin < 1e-6:
        vmax = vmin + 1e-6
    xs = np.linspace(0, x.size - 1, num=width)
    ys = np.interp(xs, np.arange(x.size), x)
    ys = (ys - vmin) / (vmax - vmin)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    pts = []
    for i in range(width):
        yy = int((1.0 - ys[i]) * (height - 1))
        pts.append((i, yy))
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], (255, 255, 255), 1)
    return img


def render_debug(
    rgb: np.ndarray,
    feats: RowFeatures,
    candidates: List[CutCandidate],
    bands: List[Band],
    out_dir: str,
    prefix: str,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    vis = rgb.copy()
    H, W = vis.shape[:2]

    # bands overlay
    overlay = vis.copy()
    for b in bands:
        y1, y2 = int(b.y1), int(b.y2)
        color = _COLOR.get(b.reason, (255, 255, 0))
        cv2.rectangle(overlay, (0, y1), (W - 1, y2 - 1), color, -1)
        if b.reason == "black_bar_band":
            cv2.rectangle(vis, (0, y1), (W - 1, y2 - 1), color, 2)
    vis = cv2.addWeighted(overlay, 0.12, vis, 0.88, 0)

    # candidate lines
    for c in candidates:
        y = int(c.y)
        color = _COLOR.get(c.type, (255, 255, 255))
        cv2.line(vis, (0, y), (W - 1, y), color, 2)

    cv2.imwrite(os.path.join(out_dir, f"{prefix}_cuts.png"), vis)

    # curves
    w = _plot_1d_curve(feats.white_ratio)
    e = _plot_1d_curve(feats.edge_density)
    d = _plot_1d_curve(feats.dark_ratio)
    curves = np.vstack([w, e, d])
    cv2.imwrite(os.path.join(out_dir, f"{prefix}_curves.png"), curves)

    # hardline stats
    hard_stats = None
    for c in candidates:
        if c.type == "hard_line" and "dominance" in c.meta and "concentration" in c.meta:
            hard_stats = {
                "dominance": c.meta.get("dominance"),
                "concentration": c.meta.get("concentration"),
                "max_len": c.meta.get("max_len"),
            }
            break
    if hard_stats is not None:
        with open(os.path.join(out_dir, f"{prefix}_hardline.json"), "w", encoding="utf-8") as f:
            json.dump(hard_stats, f, ensure_ascii=False, indent=2)
