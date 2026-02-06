from __future__ import annotations

from typing import Dict, Tuple

import cv2
import numpy as np
from skimage.segmentation import slic

from comic_splitter.stage2.types import PatchGraph, PatchNode


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _gradient_map(gray: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    p = float(np.percentile(mag, 99.0))
    if p < 1e-6:
        p = 1.0
    return np.clip(mag / p, 0.0, 1.0).astype(np.float32)


def _scan_adjacency(
    labels: np.ndarray,
    grad: np.ndarray,
) -> Tuple[Dict[Tuple[int, int], int], Dict[Tuple[int, int], float]]:
    cnt: Dict[Tuple[int, int], int] = {}
    acc: Dict[Tuple[int, int], float] = {}

    # horizontal boundaries
    la = labels[:, :-1]
    lb = labels[:, 1:]
    diff = la != lb
    ys, xs = np.where(diff)
    for y, x in zip(ys.tolist(), xs.tolist()):
        k = _pair_key(int(la[y, x]), int(lb[y, x]))
        cnt[k] = cnt.get(k, 0) + 1
        acc[k] = acc.get(k, 0.0) + float(grad[y, x]) + float(grad[y, x + 1])

    # vertical boundaries
    la = labels[:-1, :]
    lb = labels[1:, :]
    diff = la != lb
    ys, xs = np.where(diff)
    for y, x in zip(ys.tolist(), xs.tolist()):
        k = _pair_key(int(la[y, x]), int(lb[y, x]))
        cnt[k] = cnt.get(k, 0) + 1
        acc[k] = acc.get(k, 0.0) + float(grad[y, x]) + float(grad[y + 1, x])

    costs = {}
    for k, c in cnt.items():
        costs[k] = float(acc[k] / max(2 * c, 1))
    return cnt, costs


def build_patch_graph(
    band_bgr: np.ndarray,
    band_index: int,
    target_patch_area: int = 60_000,
    min_nodes: int = 20,
    max_nodes: int = 120,
    slic_compactness: float = 12.0,
    slic_sigma: float = 1.0,
) -> PatchGraph:
    h, w = band_bgr.shape[:2]
    band_area = max(1, h * w)

    n_segments = int(np.clip(band_area / max(target_patch_area, 1), min_nodes, max_nodes))
    rgb = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2RGB)
    labels = slic(
        rgb,
        n_segments=n_segments,
        compactness=slic_compactness,
        sigma=slic_sigma,
        start_label=0,
        enforce_connectivity=True,
    ).astype(np.int32)

    uniq = np.unique(labels)
    # Keep node budget stable by re-running once with tighter segment count.
    if uniq.size > max_nodes:
        scale = max_nodes / float(uniq.size)
        n2 = max(min_nodes, int(n_segments * scale * 0.9))
        labels = slic(
            rgb,
            n_segments=n2,
            compactness=slic_compactness,
            sigma=slic_sigma,
            start_label=0,
            enforce_connectivity=True,
        ).astype(np.int32)
        uniq = np.unique(labels)

    gray = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2GRAY)
    grad = _gradient_map(gray)

    # approximate non-white map
    non_white_map = (gray < 245).astype(np.float32)

    nodes: Dict[int, PatchNode] = {}
    for i, lab in enumerate(uniq.tolist()):
        ys, xs = np.where(labels == lab)
        if ys.size == 0:
            continue
        y1, y2 = int(np.min(ys)), int(np.max(ys)) + 1
        x1, x2 = int(np.min(xs)), int(np.max(xs)) + 1
        area = int(ys.size)
        center = (float(np.mean(xs)), float(np.mean(ys)))
        mean_bgr = tuple(float(v) for v in np.mean(band_bgr[ys, xs], axis=0))
        edge_mean = float(np.mean(grad[ys, xs]))
        non_white_ratio = float(np.mean(non_white_map[ys, xs]))
        nodes[i] = PatchNode(
            node_id=i,
            label=int(lab),
            band_index=band_index,
            bbox=(x1, y1, x2, y2),
            area=area,
            center=center,
            mean_bgr=mean_bgr,
            edge_mean=edge_mean,
            non_white_ratio=non_white_ratio,
        )

    cnt, costs = _scan_adjacency(labels, grad)

    # Map label-pairs to node-id pairs
    lab_to_node = {n.label: nid for nid, n in nodes.items()}
    boundary_costs: Dict[Tuple[int, int], float] = {}
    for (la, lb), _ in cnt.items():
        if la not in lab_to_node or lb not in lab_to_node:
            continue
        a = lab_to_node[la]
        b = lab_to_node[lb]
        k = _pair_key(a, b)
        boundary_costs[k] = float(costs[(la, lb)])
        nodes[a].neighbors.add(b)
        nodes[b].neighbors.add(a)

    return PatchGraph(
        band_index=band_index,
        labels=labels,
        nodes=nodes,
        boundary_costs=boundary_costs,
    )
