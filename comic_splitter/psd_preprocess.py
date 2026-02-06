from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import cv2
import numpy as np
from psd_tools import PSDImage
from psd_tools.api.layers import Layer


@dataclass
class TextItem:
    text_id: str
    text: str
    bbox: List[int]
    source: str
    conf: float
    layer_id: int
    layer_path: str


@dataclass
class BubbleLayerScore:
    layer_id: int
    layer_path: str
    kind: str
    component_count: int
    bubble_area_ratio: float
    r_bubble: float
    r_text: float
    score: float


@dataclass
class PsdPreprocessResult:
    source_bgr: np.ndarray
    clean_bgr: np.ndarray
    texts: List[TextItem]
    bubble_ranking: List[BubbleLayerScore]
    bubble_layer_id: int | None
    bubble_layer_path: str | None
    removed_layer_ids: List[int]
    removed_layer_paths: List[str]
    art_clean_path: str
    texts_path: str
    bubble_ranking_path: str
    ocr_status: str
    text_backend: str


def _clamp_bbox(bbox: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = int(np.clip(x1, 0, width))
    y1 = int(np.clip(y1, 0, height))
    x2 = int(np.clip(x2, 0, width))
    y2 = int(np.clip(y2, 0, height))
    if x2 <= x1 or y2 <= y1:
        return 0, 0, 0, 0
    return x1, y1, x2, y2


def _layer_path(layer: Layer) -> str:
    parts: List[str] = []
    cur = layer
    while hasattr(cur, "parent") and cur.parent is not None:
        lid = int(getattr(cur, "layer_id", -1))
        name = str(getattr(cur, "name", "") or "")
        parts.append(f"{name}#{lid}")
        parent = cur.parent
        if isinstance(parent, PSDImage):
            break
        cur = parent
    return "/".join(reversed(parts))


def _iter_ancestor_groups(layer: Layer) -> Iterable[Layer]:
    cur = layer
    while hasattr(cur, "parent") and cur.parent is not None:
        parent = cur.parent
        if isinstance(parent, PSDImage):
            return
        if getattr(parent, "kind", "") == "group":
            yield parent
        cur = parent


def _to_bgr_from_pil(image) -> np.ndarray:
    arr = np.array(image)
    if arr.ndim == 3 and arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    if arr.ndim == 3 and arr.shape[2] == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    raise ValueError(f"Unsupported image mode from PSD composite: shape={arr.shape}")


def _extract_texts(psd: PSDImage, width: int, height: int) -> List[TextItem]:
    out: List[TextItem] = []
    idx = 0
    for layer in psd.descendants():
        kind = str(getattr(layer, "kind", ""))
        if kind not in {"type", "text"}:
            continue
        bbox = _clamp_bbox(layer.bbox, width, height)
        if bbox == (0, 0, 0, 0):
            continue
        raw_text = str(getattr(layer, "text", "") or "")
        text = raw_text.replace("\r", "\n").strip()
        if not text:
            continue
        idx += 1
        out.append(
            TextItem(
                text_id=f"text_{idx:03d}",
                text=text,
                bbox=[bbox[0], bbox[1], bbox[2], bbox[3]],
                source="psd_text",
                conf=1.0,
                layer_id=int(getattr(layer, "layer_id", -1)),
                layer_path=_layer_path(layer),
            )
        )
    return out


def extract_psd_texts(psd: PSDImage, width: int, height: int) -> List[TextItem]:
    return _extract_texts(psd, width, height)


def _layer_rgba_and_bbox(layer: Layer, width: int, height: int) -> Tuple[np.ndarray | None, Tuple[int, int, int, int]]:
    bbox = _clamp_bbox(layer.bbox, width, height)
    if bbox == (0, 0, 0, 0):
        return None, bbox
    try:
        rgba = layer.numpy()
    except Exception:
        rgba = None
    if rgba is None:
        return None, bbox
    if rgba.ndim != 3 or rgba.shape[2] not in {3, 4}:
        return None, bbox
    if rgba.shape[2] == 3:
        alpha = np.full((rgba.shape[0], rgba.shape[1], 1), 255, dtype=np.uint8)
        rgba = np.concatenate([rgba.astype(np.uint8), alpha], axis=2)
    else:
        rgba = rgba.astype(np.uint8)
    return rgba, bbox


def _extract_components_from_rgba(
    rgba: np.ndarray,
    bbox: Tuple[int, int, int, int],
    canvas_area: int,
    min_component_area_ratio: float,
    white_v_thr: int,
    white_s_thr: int,
    alpha_thr: int,
) -> List[Dict]:
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]
    near_white = (v >= white_v_thr) & (s <= white_s_thr)
    mask = (alpha > alpha_thr) & near_white
    mask_u8 = (mask.astype(np.uint8) * 255)
    if mask_u8.size == 0:
        return []
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel, iterations=1)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    min_area = max(1, int(canvas_area * min_component_area_ratio))
    x0, y0, _, _ = bbox
    comps: List[Dict] = []
    for cid in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[cid]]
        if area < min_area or w <= 1 or h <= 1:
            continue
        comps.append(
            {
                "bbox": [x0 + x, y0 + y, x0 + x + w, y0 + y + h],
                "area": int(area),
            }
        )
    return comps


def _score_candidate(components: List[Dict], texts: List[TextItem], canvas_area: int) -> Tuple[float, float, float, float]:
    if not components:
        return 0.0, 0.0, 0.0, 0.0
    comp_count = len(components)
    bubble_area_ratio = float(np.clip(sum(int(c["area"]) for c in components) / max(canvas_area, 1), 0.0, 1.0))
    if not texts:
        return bubble_area_ratio, 0.0, 0.0, 0.0

    text_hit_ids = set()
    bubble_hit = 0
    for comp in components:
        x1, y1, x2, y2 = [int(v) for v in comp["bbox"]]
        comp_hit = False
        for t in texts:
            tx1, ty1, tx2, ty2 = [int(v) for v in t.bbox]
            cx = (tx1 + tx2) * 0.5
            cy = (ty1 + ty2) * 0.5
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                text_hit_ids.add(t.text_id)
                comp_hit = True
        if comp_hit:
            bubble_hit += 1

    r_bubble = float(bubble_hit / max(comp_count, 1))
    r_text = float(len(text_hit_ids) / max(len(texts), 1))
    score = float(np.clip(0.8 * r_bubble + 0.2 * r_text, 0.0, 1.0))
    return bubble_area_ratio, r_bubble, r_text, score


def ocr_fallback(image_or_layers) -> List[TextItem]:
    # Placeholder: OCR backend intentionally not wired yet.
    # Keep interface stable so PaddleOCR/VolcOCR can be plugged in later.
    _ = image_or_layers
    return []


def rank_bubble_layers(
    psd: PSDImage,
    texts: List[TextItem],
    min_component_area_ratio: float = 0.002,
    white_v_thr: int = 230,
    white_s_thr: int = 50,
    alpha_thr: int = 10,
) -> Tuple[List[BubbleLayerScore], Dict[int, str]]:
    width, height = [int(v) for v in psd.size]
    canvas_area = width * height
    layer_by_id: Dict[int, Layer] = {}
    layer_kind: Dict[int, str] = {}
    layer_path_by_id: Dict[int, str] = {}
    layer_components: Dict[int, List[Dict]] = {}
    group_components: Dict[int, List[Dict]] = {}
    text_layer_ids = {int(t.layer_id) for t in texts}

    for layer in psd.descendants():
        lid = int(getattr(layer, "layer_id", -1))
        layer_by_id[lid] = layer
        layer_kind[lid] = str(getattr(layer, "kind", ""))
        layer_path_by_id[lid] = _layer_path(layer)
        if not bool(getattr(layer, "visible", True)):
            continue
        if lid in text_layer_ids:
            continue
        if str(getattr(layer, "kind", "")) == "group":
            continue

        rgba, bbox = _layer_rgba_and_bbox(layer, width, height)
        if rgba is None:
            continue
        comps = _extract_components_from_rgba(
            rgba,
            bbox,
            canvas_area=canvas_area,
            min_component_area_ratio=min_component_area_ratio,
            white_v_thr=white_v_thr,
            white_s_thr=white_s_thr,
            alpha_thr=alpha_thr,
        )
        if not comps:
            continue
        layer_components[lid] = comps
        for g in _iter_ancestor_groups(layer):
            gid = int(getattr(g, "layer_id", -1))
            group_components.setdefault(gid, []).extend(comps)
            layer_by_id[gid] = g
            layer_kind[gid] = str(getattr(g, "kind", ""))
            layer_path_by_id[gid] = _layer_path(g)

    ranking: List[BubbleLayerScore] = []
    for lid, comps in layer_components.items():
        area_ratio, r_bubble, r_text, score = _score_candidate(comps, texts, canvas_area)
        ranking.append(
            BubbleLayerScore(
                layer_id=lid,
                layer_path=layer_path_by_id.get(lid, f"layer#{lid}"),
                kind=layer_kind.get(lid, "unknown"),
                component_count=len(comps),
                bubble_area_ratio=area_ratio,
                r_bubble=r_bubble,
                r_text=r_text,
                score=score,
            )
        )
    for gid, comps in group_components.items():
        area_ratio, r_bubble, r_text, score = _score_candidate(comps, texts, canvas_area)
        ranking.append(
            BubbleLayerScore(
                layer_id=gid,
                layer_path=layer_path_by_id.get(gid, f"layer#{gid}"),
                kind=layer_kind.get(gid, "group"),
                component_count=len(comps),
                bubble_area_ratio=area_ratio,
                r_bubble=r_bubble,
                r_text=r_text,
                score=score,
            )
        )
    ranking.sort(
        key=lambda x: (
            x.score,
            x.r_bubble,
            x.component_count,
            x.bubble_area_ratio,
        ),
        reverse=True,
    )
    return ranking, layer_path_by_id


def build_clean_art(psd: PSDImage, bubble_layer_id: int | None, text_layer_ids: List[int]) -> np.ndarray:
    remove_ids = sorted(set(text_layer_ids + ([bubble_layer_id] if bubble_layer_id is not None else [])))
    layer_by_id = {int(getattr(layer, "layer_id", -1)): layer for layer in psd.descendants()}
    visible_backup: Dict[int, bool] = {}
    for lid in remove_ids:
        layer = layer_by_id.get(lid)
        if layer is None:
            continue
        visible_backup[lid] = bool(getattr(layer, "visible", True))
        layer.visible = False
    try:
        clean_bgr = _to_bgr_from_pil(psd.composite())
    finally:
        for lid, vis in visible_backup.items():
            layer = layer_by_id.get(lid)
            if layer is not None:
                layer.visible = bool(vis)
    return clean_bgr


def preprocess_psd_for_panels(
    image_path: Path,
    out_dir: Path,
    prefix: str,
    min_component_area_ratio: float = 0.002,
    white_v_thr: int = 230,
    white_s_thr: int = 50,
    alpha_thr: int = 10,
    min_components: int = 2,
    min_r_bubble: float = 0.30,
    min_bubble_area_ratio: float = 0.02,
) -> PsdPreprocessResult:
    psd = PSDImage.open(image_path)
    width, height = [int(v) for v in psd.size]

    source_bgr = _to_bgr_from_pil(psd.composite())
    texts = extract_psd_texts(psd, width, height)
    ocr_status = "not_needed"
    text_backend = "psd_text"
    if not texts:
        texts = ocr_fallback(source_bgr)
        ocr_status = "not_enabled"
        text_backend = "ocr_placeholder"
    text_layer_ids = {int(t.layer_id) for t in texts}
    ranking, layer_path_by_id = rank_bubble_layers(
        psd=psd,
        texts=texts,
        min_component_area_ratio=min_component_area_ratio,
        white_v_thr=white_v_thr,
        white_s_thr=white_s_thr,
        alpha_thr=alpha_thr,
    )

    bubble_layer_id: int | None = None
    bubble_layer_path: str | None = None
    for item in ranking:
        cond_primary = item.r_bubble >= min_r_bubble and item.component_count >= min_components
        cond_fallback = item.bubble_area_ratio >= min_bubble_area_ratio and item.r_text >= 0.2
        if cond_primary or cond_fallback:
            bubble_layer_id = int(item.layer_id)
            bubble_layer_path = item.layer_path
            break

    clean_bgr = build_clean_art(
        psd=psd,
        bubble_layer_id=bubble_layer_id,
        text_layer_ids=sorted(text_layer_ids),
    )
    remove_ids = sorted(set(text_layer_ids | ({bubble_layer_id} if bubble_layer_id is not None else set())))

    out_dir.mkdir(parents=True, exist_ok=True)
    art_clean_path = out_dir / f"{prefix}_art_clean.png"
    texts_path = out_dir / f"{prefix}_texts.json"
    bubble_rank_path = out_dir / f"{prefix}_bubble_layer_ranking.json"
    cv2.imwrite(str(art_clean_path), clean_bgr)
    texts_path.write_text(
        json.dumps([asdict(t) for t in texts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bubble_rank_path.write_text(
        json.dumps([asdict(r) for r in ranking], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    removed_paths = [layer_path_by_id.get(lid, f"layer#{lid}") for lid in remove_ids]
    return PsdPreprocessResult(
        source_bgr=source_bgr,
        clean_bgr=clean_bgr,
        texts=texts,
        bubble_ranking=ranking,
        bubble_layer_id=bubble_layer_id,
        bubble_layer_path=bubble_layer_path,
        removed_layer_ids=remove_ids,
        removed_layer_paths=removed_paths,
        art_clean_path=str(art_clean_path),
        texts_path=str(texts_path),
        bubble_ranking_path=str(bubble_rank_path),
        ocr_status=ocr_status,
        text_backend=text_backend,
    )
