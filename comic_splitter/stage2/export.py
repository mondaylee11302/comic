from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np

from comic_splitter.common.types import Band
from comic_splitter.stage2.types import PatchGraph


def _region_mask_band(graph: PatchGraph, node_ids: List[int]) -> np.ndarray:
    if graph.labels.size == 0 or not node_ids:
        return np.zeros_like(graph.labels, dtype=np.uint8)
    labels = [graph.nodes[n].label for n in node_ids if n in graph.nodes]
    if not labels:
        return np.zeros_like(graph.labels, dtype=np.uint8)
    mask = np.isin(graph.labels, np.array(labels, dtype=np.int32)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def _sorted_regions(regions: List[Dict]) -> List[Dict]:
    def key_fn(r: Dict) -> tuple:
        x1, y1, _, _ = r.get("bbox", [0, 0, 0, 0])
        return (int(y1), int(x1))

    return sorted(regions, key=key_fn)


def _bbox_area(b: List[int]) -> float:
    x1, y1, x2, y2 = [int(v) for v in b]
    return float(max(0, x2 - x1) * max(0, y2 - y1))


def _intersection(a: List[int], b: List[int]) -> float:
    ax1, ay1, ax2, ay2 = [int(v) for v in a]
    bx1, by1, bx2, by2 = [int(v) for v in b]
    x1 = max(ax1, bx1)
    y1 = max(ay1, by1)
    x2 = min(ax2, bx2)
    y2 = min(ay2, by2)
    return float(max(0, x2 - x1) * max(0, y2 - y1))


def _iou(a: List[int], b: List[int]) -> float:
    inter = _intersection(a, b)
    if inter <= 0:
        return 0.0
    union = _bbox_area(a) + _bbox_area(b) - inter
    return float(inter / max(union, 1.0))


def _containment(inner: List[int], outer: List[int]) -> float:
    inter = _intersection(inner, outer)
    return float(inter / max(_bbox_area(inner), 1.0))


def _select_primary_regions(
    regions: List[Dict],
    min_area_ratio: float,
    containment_thr: float,
    iou_thr: float,
) -> List[Dict]:
    # Keep the major panel regions and drop child/sub-overlapping regions.
    grouped: Dict[int, List[Dict]] = {}
    for r in regions:
        bi = int(r.get("band_index", -1))
        grouped.setdefault(bi, []).append(r)

    kept_all: List[Dict] = []
    for _, group in grouped.items():
        candidates = []
        for r in group:
            area_ratio = float(r.get("meta", {}).get("area_ratio", 0.0))
            if area_ratio < min_area_ratio:
                continue
            candidates.append(r)

        candidates.sort(
            key=lambda r: (
                _bbox_area(r.get("bbox", [0, 0, 0, 0])),
                float(r.get("score", 0.0)),
            ),
            reverse=True,
        )

        kept: List[Dict] = []
        for c in candidates:
            cb = c.get("bbox", [0, 0, 0, 0])
            drop = False
            for k in kept:
                kb = k.get("bbox", [0, 0, 0, 0])
                if _containment(cb, kb) >= containment_thr:
                    drop = True
                    break
                if _iou(cb, kb) >= iou_thr and float(c.get("score", 0.0)) <= float(k.get("score", 0.0)):
                    drop = True
                    break
            if not drop:
                kept.append(c)
        kept_all.extend(kept)

    return _sorted_regions(kept_all)


def export_panel_crops(
    rgb: np.ndarray,
    bands: List[Band],
    graphs: Dict[int, PatchGraph],
    regions: List[Dict],
    out_dir: str,
    prefix: str,
    score_thr: float = 0.12,
    pad: int = 6,
    export_mask: bool = False,
    min_area_ratio: float = 0.04,
    containment_thr: float = 0.88,
    iou_thr: float = 0.75,
) -> Dict:
    out_path = Path(out_dir)
    panel_dir = out_path / f"{prefix}_panels"
    panel_dir.mkdir(parents=True, exist_ok=True)

    h, w = rgb.shape[:2]
    exported = []

    primary_regions = _select_primary_regions(
        regions,
        min_area_ratio=min_area_ratio,
        containment_thr=containment_thr,
        iou_thr=iou_thr,
    )
    ordered = _sorted_regions(primary_regions)
    panel_idx = 0
    for r in ordered:
        score = float(r.get("score", 0.0))
        if score < score_thr:
            continue

        band_idx = int(r.get("band_index", -1))
        if band_idx not in graphs or not (0 <= band_idx < len(bands)):
            continue

        x1, y1, x2, y2 = [int(v) for v in r.get("bbox", [0, 0, 0, 0])]
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)
        if x2 <= x1 or y2 <= y1:
            continue

        panel_idx += 1
        panel_name = f"panel_{panel_idx:03d}"

        crop = rgb[y1:y2, x1:x2]
        bbox_path = panel_dir / f"{panel_name}_bbox.jpg"
        cv2.imwrite(str(bbox_path), crop)

        mask_path = None
        if export_mask:
            graph = graphs[band_idx]
            band = bands[band_idx]
            by1, by2 = int(band.y1), int(band.y2)
            mask_band = _region_mask_band(graph, r.get("node_ids", []))

            gy1 = max(y1, by1)
            gy2 = min(y2, by2)
            if gy2 > gy1:
                mask_crop = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
                sy1 = gy1 - by1
                sy2 = gy2 - by1
                dx1 = max(0, x1)
                dx2 = min(mask_band.shape[1], x2)
                if dx2 > dx1:
                    src = mask_band[sy1:sy2, dx1:dx2]
                    ty1 = gy1 - y1
                    ty2 = gy2 - y1
                    tx1 = dx1 - x1
                    tx2 = dx2 - x1
                    mask_crop[ty1:ty2, tx1:tx2] = src
                rgba = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
                rgba[:, :, 3] = mask_crop
                mask_path = panel_dir / f"{panel_name}_mask.png"
                cv2.imwrite(str(mask_path), rgba)

        exported.append(
            {
                "panel_id": panel_name,
                "region_id": int(r.get("region_id", -1)),
                "band_index": band_idx,
                "score": score,
                "bbox": [x1, y1, x2, y2],
                "bbox_path": str(bbox_path),
                "mask_path": str(mask_path) if mask_path is not None else None,
            }
        )

    manifest = {
        "panel_count": len(exported),
        "source_region_count": len(regions),
        "primary_region_count": len(primary_regions),
        "panel_dir": str(panel_dir),
        "score_thr": float(score_thr),
        "pad": int(pad),
        "export_mask": bool(export_mask),
        "min_area_ratio": float(min_area_ratio),
        "containment_thr": float(containment_thr),
        "iou_thr": float(iou_thr),
        "panels": exported,
    }
    manifest_path = out_path / f"{prefix}_panels_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest
