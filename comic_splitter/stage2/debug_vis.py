from __future__ import annotations

import os
from typing import Dict, List

import cv2
import numpy as np

from comic_splitter.common.types import Band
from comic_splitter.stage2.types import PatchGraph


def _label_edges(labels: np.ndarray) -> np.ndarray:
    h, w = labels.shape
    edge = np.zeros((h, w), dtype=np.uint8)
    edge[:, 1:] |= (labels[:, 1:] != labels[:, :-1]).astype(np.uint8)
    edge[1:, :] |= (labels[1:, :] != labels[:-1, :]).astype(np.uint8)
    return edge


def _region_mask(graph: PatchGraph, node_ids: List[int]) -> np.ndarray:
    if graph.labels.size == 0 or not node_ids:
        return np.zeros_like(graph.labels, dtype=np.uint8)
    region_labels = np.array([graph.nodes[n].label for n in node_ids if n in graph.nodes], dtype=np.int32)
    if region_labels.size == 0:
        return np.zeros_like(graph.labels, dtype=np.uint8)
    mask = np.isin(graph.labels, region_labels).astype(np.uint8) * 255
    # Close tiny cracks created by superpixel boundaries.
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=1)
    return mask


def render_stage2_debug(
    rgb: np.ndarray,
    bands: List[Band],
    graphs: Dict[int, PatchGraph],
    regions: List[Dict],
    out_dir: str,
    prefix: str,
    overlay_alpha: float = 0.0,
    draw_patch_edges: bool = False,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    vis = rgb.copy()
    overlay = rgb.copy()

    rng = np.random.default_rng(42)
    colors = {}
    for r in regions:
        rid = (int(r["band_index"]), int(r["region_id"]))
        colors[rid] = tuple(int(v) for v in rng.integers(40, 240, size=3))

    # draw region masks and bboxes
    for r in regions:
        bi = int(r["band_index"])
        if bi not in graphs or bi >= len(bands):
            continue
        graph = graphs[bi]
        b = bands[bi]
        by1, by2 = int(b.y1), int(b.y2)
        if by2 <= by1:
            continue
        c = colors[(bi, int(r["region_id"]))]

        mask = _region_mask(graph, r["node_ids"])
        band_overlay = overlay[by1:by2]
        band_vis = vis[by1:by2]
        if overlay_alpha > 0.0:
            band_overlay[mask > 0] = c

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(band_vis, contours, -1, c, 2)

        x1, y1, x2, y2 = r["bbox"]
        cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), c, 1)

    if overlay_alpha > 0.0:
        a = float(np.clip(overlay_alpha, 0.0, 1.0))
        vis = cv2.addWeighted(overlay, a, vis, 1.0 - a, 0)

    if draw_patch_edges:
        for bi, graph in graphs.items():
            if bi >= len(bands):
                continue
            b = bands[bi]
            y1, y2 = int(b.y1), int(b.y2)
            if y2 <= y1:
                continue
            edge = _label_edges(graph.labels)
            band = vis[y1:y2]
            band[edge > 0] = (255, 255, 255)

    cv2.imwrite(os.path.join(out_dir, f"{prefix}_stage2_regions.png"), vis)
