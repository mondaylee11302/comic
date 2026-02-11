from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import difflib
import io
import json
import os
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import cv2
import numpy as np
from psd_tools import PSDImage
from psd_tools.api.layers import Layer

try:
    from PIL import Image
except Exception:  # pragma: no cover - pillow is expected via psd-tools
    Image = None


@dataclass
class TextItem:
    text_id: str
    text: str
    bbox: List[int]
    source: str
    conf: float
    layer_id: int
    layer_path: str
    quad: List[List[float]] | None = None
    canvas_norm_bbox: List[float] | None = None
    geom_source: str = "bbox"
    text_source: str = "psd"
    merge_group_id: str | None = None
    merge_status: str = "single"


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
    solidity: float = 0.0
    hole_ratio: float = 0.0
    text_overlap: float = 0.0
    center_hit_ratio: float = 0.0
    white_component_quality: float = 0.0
    text_proximity_ratio: float = 0.0


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
    textbox_layer_ids: List[int]
    textbox_layer_paths: List[str]
    raster_text_layer_ids: List[int]
    raster_text_layer_paths: List[str]
    texts_merged_path: str
    textbox_ranking_path: str
    text_canvas_map_path: str
    ocr_request_id: str | None = None
    upload_latency_ms: int = 0
    ocr_latency_ms: int = 0
    ocr_input_size: Dict[str, int] | None = None
    ocr_gray_input_path: str = ""
    merge_unmatched_psd_count: int = 0
    merge_unmatched_ocr_count: int = 0
    ocr_degraded_reason: str = ""


@dataclass
class OcrExtractResult:
    texts: List[TextItem]
    status: str
    request_id: str | None
    upload_latency_ms: int
    ocr_latency_ms: int
    input_size: Dict[str, int]
    gray_image_path: str = ""
    degraded_reason: str = ""


@dataclass
class WhiteComponent:
    bbox: List[int]
    area_ratio: float
    solidity: float
    hole_ratio: float
    quality: float
    mask: np.ndarray
    x0: int
    y0: int


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(dotenv_path=root / ".env", override=False)
    except Exception:
        return


def _clamp_bbox(bbox: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = int(np.clip(x1, 0, width))
    y1 = int(np.clip(y1, 0, height))
    x2 = int(np.clip(x2, 0, width))
    y2 = int(np.clip(y2, 0, height))
    if x2 <= x1 or y2 <= y1:
        return 0, 0, 0, 0
    return x1, y1, x2, y2


def _bbox_area(bbox: List[int]) -> float:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return float(max(0.0, x2 - x1) * max(0.0, y2 - y1))


def _bbox_from_quad(quad: List[List[float]]) -> List[int]:
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    return [int(np.floor(min(xs))), int(np.floor(min(ys))), int(np.ceil(max(xs))), int(np.ceil(max(ys)))]


def _quad_from_bbox(bbox: List[int]) -> List[List[float]]:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _normalize_bbox(bbox: List[int], width: int, height: int) -> List[float]:
    if width <= 0 or height <= 0:
        return [0.0, 0.0, 0.0, 0.0]
    x1, y1, x2, y2 = [float(v) for v in bbox]
    out = [x1 / width, y1 / height, x2 / width, y2 / height]
    return [float(np.clip(v, 0.0, 1.0)) for v in out]


def _resolve_geometry(text: TextItem, width: int, height: int) -> TextItem:
    quad = text.quad
    bbox = list(text.bbox)
    geom_source = text.geom_source

    if quad and len(quad) == 4:
        bbox = _bbox_from_quad(quad)
        geom_source = text.geom_source or "quad"
    else:
        if not bbox or _bbox_area(bbox) <= 0:
            bbox = [0, 0, 0, 0]
        quad = None
        geom_source = text.geom_source or "bbox"

    norm = _normalize_bbox(bbox, width=width, height=height)
    return replace(text, quad=quad, bbox=bbox, canvas_norm_bbox=norm, geom_source=geom_source)


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


def _build_runtime_layer_maps(psd: PSDImage) -> Tuple[Dict[int, int], Dict[int, Layer], Dict[int, str]]:
    runtime_id_by_obj: Dict[int, int] = {}
    layer_by_runtime_id: Dict[int, Layer] = {}
    path_by_runtime_id: Dict[int, str] = {}
    for idx, layer in enumerate(psd.descendants(), start=1):
        rid = int(idx)
        runtime_id_by_obj[id(layer)] = rid
        layer_by_runtime_id[rid] = layer
        path_by_runtime_id[rid] = _layer_path(layer)
    return runtime_id_by_obj, layer_by_runtime_id, path_by_runtime_id


def _to_bgr_from_pil(image) -> np.ndarray:
    arr = np.array(image)
    if arr.ndim == 3 and arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    if arr.ndim == 3 and arr.shape[2] == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    raise ValueError(f"Unsupported image mode from PSD composite: shape={arr.shape}")


def _extract_texts(
    psd: PSDImage,
    width: int,
    height: int,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
) -> List[TextItem]:
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
        runtime_lid = int(getattr(layer, "layer_id", -1))
        if runtime_id_by_obj is not None:
            runtime_lid = int(runtime_id_by_obj.get(id(layer), runtime_lid))

        item = TextItem(
            text_id=f"psd_{idx:03d}",
            text=text,
            bbox=[bbox[0], bbox[1], bbox[2], bbox[3]],
            source="psd_text",
            conf=1.0,
            layer_id=runtime_lid,
            layer_path=_layer_path(layer),
            quad=None,
            geom_source="psd_bbox",
            text_source="psd",
            merge_status="unmatched_psd",
        )
        out.append(_resolve_geometry(item, width=width, height=height))
    return out


def extract_psd_texts(
    psd: PSDImage,
    width: int,
    height: int,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
) -> List[TextItem]:
    return _extract_texts(psd, width, height, runtime_id_by_obj=runtime_id_by_obj)


def _resize_for_ocr_limits(image_bgr: np.ndarray, max_long: int = 3840, max_short: int = 2160) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    if h <= 0 or w <= 0:
        return image_bgr
    s = min(1.0, float(max_long) / float(max(h, w)), float(max_short) / float(min(h, w)))
    if s >= 0.9999:
        return image_bgr
    nw = max(1, int(round(w * s)))
    nh = max(1, int(round(h * s)))
    return cv2.resize(image_bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def prepare_ocr_input_image(
    image_bgr: np.ndarray,
    max_bytes: int = 10 * 1024 * 1024,
    quality_seq: Tuple[int, ...] = (85, 75, 65, 55),
) -> Tuple[bytes, Dict[str, int], np.ndarray]:
    if Image is None:
        raise RuntimeError("Pillow is required for OCR JPEG encoding")

    resized_bgr = _resize_for_ocr_limits(image_bgr)
    rgb = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    last_bytes: bytes | None = None
    last_quality = int(quality_seq[-1])
    for q in quality_seq:
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=int(q), subsampling=2, optimize=True)
        data = buf.getvalue()
        last_bytes = data
        last_quality = int(q)
        if len(data) < max_bytes:
            meta = {
                "width": int(resized_bgr.shape[1]),
                "height": int(resized_bgr.shape[0]),
                "jpeg_bytes": int(len(data)),
                "quality": int(q),
            }
            return data, meta, resized_bgr

    if last_bytes is None:
        raise ValueError("failed to encode OCR JPEG input")

    raise ValueError(
        f"OCR input exceeds 10MB after quality fallback, last_bytes={len(last_bytes)}, quality={last_quality}"
    )


def prepare_ocr_input_image_png(
    image_gray: np.ndarray,
    max_bytes: int = 10 * 1024 * 1024,
    compression_seq: Tuple[int, ...] = (3, 6, 9),
    resize_scale_seq: Tuple[float, ...] = (1.0, 0.9, 0.8, 0.7, 0.6),
) -> Tuple[bytes, Dict[str, int], np.ndarray]:
    if image_gray.ndim != 2:
        raise ValueError(f"prepare_ocr_input_image_png expects 2D grayscale image, got shape={image_gray.shape}")

    base = _resize_for_ocr_limits(image_gray)
    last_bytes: bytes | None = None
    last_comp = int(compression_seq[-1]) if compression_seq else 9
    last_scaled = base

    for scale in resize_scale_seq:
        s = float(scale)
        if s <= 0:
            continue
        if s >= 0.9999:
            scaled = base
        else:
            nw = max(1, int(round(base.shape[1] * s)))
            nh = max(1, int(round(base.shape[0] * s)))
            scaled = cv2.resize(base, (nw, nh), interpolation=cv2.INTER_AREA)
        last_scaled = scaled

        for comp in compression_seq:
            c = int(np.clip(int(comp), 0, 9))
            ok, encoded = cv2.imencode(".png", scaled, [int(cv2.IMWRITE_PNG_COMPRESSION), c])
            if not ok:
                continue
            data = encoded.tobytes()
            last_bytes = data
            last_comp = c
            if len(data) <= max_bytes:
                meta = {
                    "width": int(scaled.shape[1]),
                    "height": int(scaled.shape[0]),
                    # Keep legacy key name for downstream compatibility.
                    "jpeg_bytes": int(len(data)),
                    "quality": 100,
                    "png_compression": int(c),
                }
                return data, meta, scaled

    if last_bytes is None:
        raise ValueError("failed to encode OCR PNG input")
    raise ValueError(
        "OCR PNG input exceeds byte budget, "
        f"last_bytes={len(last_bytes)}, compression={last_comp}, size={last_scaled.shape[1]}x{last_scaled.shape[0]}"
    )


def _extract_ocr_texts_from_source(
    source_bgr: np.ndarray,
    width: int,
    height: int,
    gray_png_export_path: Optional[Path] = None,
    progress_hook: Optional[Callable[[str], None]] = None,
) -> OcrExtractResult:
    def _log(msg: str) -> None:
        if progress_hook is not None:
            progress_hook(msg)

    _load_dotenv_from_repo_root()
    enable = str(os.getenv("VOLC_OCR_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if not enable:
        return OcrExtractResult(
            texts=[],
            status="disabled",
            request_id=None,
            upload_latency_ms=0,
            ocr_latency_ms=0,
            input_size={"width": int(width), "height": int(height), "jpeg_bytes": 0, "quality": 0},
            degraded_reason="VOLC_OCR_ENABLE is disabled",
        )

    _log("ocr: encode input image (grayscale original png)")
    try:
        if source_bgr.ndim == 2:
            gray = source_bgr
        elif source_bgr.ndim == 3 and source_bgr.shape[2] >= 3:
            gray = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2GRAY)
        else:
            raise ValueError(f"unsupported OCR source image shape: {source_bgr.shape}")

        png_comp_raw = str(os.getenv("OCR_GRAY_PNG_COMPRESSION", "6")).strip()
        try:
            png_comp = int(png_comp_raw)
        except Exception:
            png_comp = 6
        png_comp = int(np.clip(png_comp, 0, 9))
        ok, encoded = cv2.imencode(".png", gray, [int(cv2.IMWRITE_PNG_COMPRESSION), png_comp])
        if not ok:
            raise ValueError("failed to encode OCR original grayscale PNG input")
        original_bytes = encoded.tobytes()
        original_meta = {
            "width": int(gray.shape[1]),
            "height": int(gray.shape[0]),
            "jpeg_bytes": int(len(original_bytes)),
            "quality": 100,
            "png_compression": int(png_comp),
        }
        gray_image_path = ""
        if gray_png_export_path is not None:
            try:
                gray_png_export_path.parent.mkdir(parents=True, exist_ok=True)
                if cv2.imwrite(str(gray_png_export_path), gray):
                    gray_image_path = str(gray_png_export_path)
                    _log(f"ocr: gray input saved -> {gray_image_path}")
                else:
                    _log(f"ocr: failed to save gray input -> {gray_png_export_path}")
            except Exception as save_exc:
                _log(f"ocr: failed to save gray input: {save_exc}")
    except Exception as exc:
        return OcrExtractResult(
            texts=[],
            status="degraded",
            request_id=None,
            upload_latency_ms=0,
            ocr_latency_ms=0,
            input_size={"width": int(width), "height": int(height), "jpeg_bytes": 0, "quality": 0},
            gray_image_path="",
            degraded_reason=f"encode grayscale input failed: {exc}",
        )

    try:
        from volc_imagex.ocr import ocr_ai_process_bytes
    except Exception as exc:
        return OcrExtractResult(
            texts=[],
            status="degraded",
            request_id=None,
            upload_latency_ms=0,
            ocr_latency_ms=0,
            input_size=original_meta,
            gray_image_path=gray_image_path,
            degraded_reason=f"volc_imagex import failed: {exc}",
        )

    try:
        max_retries_raw = str(os.getenv("VOLC_OCR_MAX_RETRIES", "2")).strip()
        try:
            ocr_max_retries = max(1, int(max_retries_raw))
        except Exception:
            ocr_max_retries = 2
        request_meta = dict(original_meta)
        _log(
            "ocr: request start (grayscale original png, size=%dx%d, bytes=%d, png_comp=%d)"
            % (
                int(request_meta.get("width", 0)),
                int(request_meta.get("height", 0)),
                int(request_meta.get("jpeg_bytes", 0)),
                int(request_meta.get("png_compression", -1)),
            )
        )
        ocr_result = ocr_ai_process_bytes(
            file_bytes=original_bytes,
            scene="general",
            file_type=1,
            max_retries=ocr_max_retries,
        )
        _log(f"ocr: response done ({ocr_result.elapsed_ms}ms), texts={len(ocr_result.texts)}")

        texts: List[TextItem] = []
        src_w = max(1.0, float(request_meta.get("width", width)))
        src_h = max(1.0, float(request_meta.get("height", height)))
        scale_x = float(width) / src_w
        scale_y = float(height) / src_h

        for idx, box in enumerate(ocr_result.texts, start=1):
            text = (box.text or "").strip()
            if not text:
                continue
            quad = [[float(p[0]) * scale_x, float(p[1]) * scale_y] for p in box.quad]
            item = TextItem(
                text_id=f"ocr_{idx:03d}",
                text=text,
                bbox=_bbox_from_quad(quad),
                source="ocr_general",
                conf=float(box.confidence) if box.confidence is not None else 0.0,
                layer_id=-1,
                layer_path="",
                quad=quad,
                geom_source="ocr_quad",
                text_source="ocr",
                merge_status="unmatched_ocr",
            )
            texts.append(_resolve_geometry(item, width=width, height=height))

        status = "ok" if texts else "ok_empty"
        return OcrExtractResult(
            texts=texts,
            status=status,
            request_id=ocr_result.request_id,
            upload_latency_ms=0,
            ocr_latency_ms=int(ocr_result.elapsed_ms),
            input_size=request_meta,
            gray_image_path=gray_image_path,
            degraded_reason="",
        )
    except Exception as exc:
        return OcrExtractResult(
            texts=[],
            status="degraded",
            request_id=None,
            upload_latency_ms=0,
            ocr_latency_ms=0,
            input_size=original_meta,
            gray_image_path=gray_image_path,
            degraded_reason=str(exc),
        )


def _normalize_text(text: str) -> str:
    return "".join(ch.lower() for ch in text if not ch.isspace())


def _text_similarity(a: str, b: str) -> float:
    na = _normalize_text(a)
    nb = _normalize_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return float(difflib.SequenceMatcher(a=na, b=nb).ratio())


def _bbox_iou(a: List[int], b: List[int]) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in a]
    bx1, by1, bx2, by2 = [float(v) for v in b]
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = _bbox_area(a) + _bbox_area(b) - inter
    if union <= 0:
        return 0.0
    return float(inter / union)


def _center_dist_norm(a: List[int], b: List[int]) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in a]
    bx1, by1, bx2, by2 = [float(v) for v in b]
    acx, acy = (ax1 + ax2) * 0.5, (ay1 + ay2) * 0.5
    bcx, bcy = (bx1 + bx2) * 0.5, (by1 + by2) * 0.5
    dist = float(np.hypot(acx - bcx, acy - bcy))
    ad = float(np.hypot(ax2 - ax1, ay2 - ay1))
    bd = float(np.hypot(bx2 - bx1, by2 - by1))
    base = max(1.0, min(ad, bd))
    return dist / base


def merge_text_items(
    psd_texts: List[TextItem],
    ocr_texts: List[TextItem],
    width: int,
    height: int,
) -> Tuple[List[TextItem], Dict[str, int]]:
    if not psd_texts and not ocr_texts:
        return [], {"merge_unmatched_psd_count": 0, "merge_unmatched_ocr_count": 0}

    edges: List[Tuple[float, int, int]] = []
    for pi, pt in enumerate(psd_texts):
        for oi, ot in enumerate(ocr_texts):
            iou = _bbox_iou(pt.bbox, ot.bbox)
            center_norm = _center_dist_norm(pt.bbox, ot.bbox)
            if not (iou >= 0.35 or center_norm <= 0.25):
                continue

            geom_score = max(iou, max(0.0, 1.0 - center_norm))
            text_score = _text_similarity(pt.text, ot.text)
            strong_text = text_score >= 0.999
            weak_text = text_score >= 0.65 and geom_score >= 0.70
            if not (strong_text or weak_text):
                continue

            w = 0.7 * geom_score + 0.3 * text_score
            edges.append((float(w), pi, oi))

    edges.sort(key=lambda x: x[0], reverse=True)

    used_psd: set[int] = set()
    used_ocr: set[int] = set()
    pairs: List[Tuple[int, int]] = []
    for _, pi, oi in edges:
        if pi in used_psd or oi in used_ocr:
            continue
        used_psd.add(pi)
        used_ocr.add(oi)
        pairs.append((pi, oi))

    merged: List[TextItem] = []
    merge_idx = 0
    for pi, oi in pairs:
        merge_idx += 1
        pt = psd_texts[pi]
        ot = ocr_texts[oi]
        quad = ot.quad if ot.quad else pt.quad
        bbox = _bbox_from_quad(quad) if quad else list(pt.bbox)
        item = TextItem(
            text_id=f"merged_{merge_idx:03d}",
            text=pt.text,
            bbox=bbox,
            source="merged",
            conf=max(float(pt.conf), float(ot.conf)),
            layer_id=int(pt.layer_id),
            layer_path=pt.layer_path,
            quad=quad,
            geom_source="ocr_quad" if ot.quad else "psd_bbox",
            text_source="psd",
            merge_group_id=f"m_{merge_idx:03d}",
            merge_status="matched",
        )
        merged.append(_resolve_geometry(item, width=width, height=height))

    for pi, pt in enumerate(psd_texts):
        if pi in used_psd:
            continue
        merged.append(
            _resolve_geometry(
                replace(
                    pt,
                    merge_group_id=None,
                    merge_status="unmatched_psd",
                    text_source="psd",
                    geom_source=pt.geom_source or "psd_bbox",
                ),
                width=width,
                height=height,
            )
        )

    for oi, ot in enumerate(ocr_texts):
        if oi in used_ocr:
            continue
        merged.append(
            _resolve_geometry(
                replace(
                    ot,
                    merge_group_id=None,
                    merge_status="unmatched_ocr",
                    text_source="ocr",
                    geom_source=ot.geom_source or "ocr_quad",
                ),
                width=width,
                height=height,
            )
        )

    merged.sort(key=lambda t: (int(t.bbox[1]), int(t.bbox[0]), t.text_id))
    for idx, t in enumerate(merged, start=1):
        t.text_id = f"text_{idx:03d}"

    return merged, {
        "merge_unmatched_psd_count": int(len(psd_texts) - len(used_psd)),
        "merge_unmatched_ocr_count": int(len(ocr_texts) - len(used_ocr)),
    }


def _layer_rgba_and_bbox(
    layer: Layer,
    width: int,
    height: int,
    prefer_composite: bool = False,
) -> Tuple[np.ndarray | None, Tuple[int, int, int, int]]:
    raw_bbox = tuple(int(v) for v in layer.bbox)
    bbox = _clamp_bbox(raw_bbox, width, height)
    if bbox == (0, 0, 0, 0):
        return None, bbox

    rgba = None
    if prefer_composite:
        try:
            rendered = layer.composite()
            if rendered is not None:
                rgba = np.array(rendered)
        except Exception:
            rgba = None

    if rgba is None:
        try:
            rgba = layer.numpy()
        except Exception:
            rgba = None

    # Fallback to rendered composite only if needed.
    if rgba is None and (not prefer_composite):
        try:
            rendered = layer.composite()
            if rendered is not None:
                rgba = np.array(rendered)
        except Exception:
            rgba = None
    if rgba is None:
        return None, bbox
    if rgba.ndim != 3 or rgba.shape[2] not in {3, 4}:
        return None, bbox

    if np.issubdtype(rgba.dtype, np.floating):
        max_val = float(np.nanmax(rgba)) if rgba.size > 0 else 0.0
        if max_val <= 1.5:
            rgba_u8 = np.clip(rgba * 255.0, 0.0, 255.0).round().astype(np.uint8)
        else:
            rgba_u8 = np.clip(rgba, 0.0, 255.0).round().astype(np.uint8)
    else:
        rgba_u8 = np.clip(rgba, 0, 255).astype(np.uint8)

    if rgba_u8.shape[2] == 3:
        alpha = np.full((rgba_u8.shape[0], rgba_u8.shape[1], 1), 255, dtype=np.uint8)
        rgba_u8 = np.concatenate([rgba_u8, alpha], axis=2)

    target_w = max(0, int(bbox[2] - bbox[0]))
    target_h = max(0, int(bbox[3] - bbox[1]))
    if target_w <= 0 or target_h <= 0:
        return None, bbox

    if rgba_u8.shape[0] != target_h or rgba_u8.shape[1] != target_w:
        raw_x1, raw_y1, _, _ = raw_bbox
        off_x = max(0, int(bbox[0] - raw_x1))
        off_y = max(0, int(bbox[1] - raw_y1))
        off_x2 = min(int(rgba_u8.shape[1]), off_x + target_w)
        off_y2 = min(int(rgba_u8.shape[0]), off_y + target_h)
        cropped = rgba_u8[off_y:off_y2, off_x:off_x2]

        if cropped.shape[0] != target_h or cropped.shape[1] != target_w:
            canvas = np.zeros((target_h, target_w, 4), dtype=np.uint8)
            hh = min(target_h, int(cropped.shape[0]))
            ww = min(target_w, int(cropped.shape[1]))
            if hh > 0 and ww > 0:
                canvas[:hh, :ww, :] = cropped[:hh, :ww, :]
            rgba_u8 = canvas
        else:
            rgba_u8 = cropped

    return rgba_u8, bbox


def _component_metrics(comp_mask: np.ndarray) -> Tuple[float, float]:
    area = float(np.count_nonzero(comp_mask))
    if area <= 1.0:
        return 0.0, 1.0

    contours, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0, 1.0
    cnt = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    hull_area = float(max(cv2.contourArea(hull), 1.0))
    solidity = float(area / hull_area)

    closed = cv2.morphologyEx(comp_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    hole_pixels = max(0.0, float(np.count_nonzero(closed)) - area)
    hole_ratio = float(hole_pixels / max(area, 1.0))
    return solidity, hole_ratio


def _component_quality(solidity: float, hole_ratio: float, flatness: float = 0.5) -> float:
    solidity_score = float(np.clip((solidity - 0.35) / 0.55, 0.0, 1.0))
    hole_score = 1.0 - float(np.clip(abs(hole_ratio - 0.15) / 0.45, 0.0, 1.0))
    flatness_score = float(np.clip(flatness, 0.0, 1.0))
    return float(np.clip(0.45 * solidity_score + 0.25 * hole_score + 0.30 * flatness_score, 0.0, 1.0))


def _extract_white_components_from_rgba(
    rgba: np.ndarray,
    bbox: Tuple[int, int, int, int],
    canvas_area: int,
    white_v_thr: int,
    white_s_thr: int,
    alpha_thr: int,
    min_area_ratio: float = 0.001,
    max_area_ratio: float = 0.5,
) -> List[WhiteComponent]:
    _ = white_v_thr
    _ = white_s_thr
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    mask = (alpha > alpha_thr).astype(np.uint8) * 255
    if mask.size == 0:
        return []

    # Color-agnostic component extraction from rendered layer alpha.
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_mid = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_mid, iterations=1)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    x0, y0, _, _ = bbox
    out: List[WhiteComponent] = []
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    for cid in range(1, n):
        x, y, w, h, area = [int(v) for v in stats[cid]]
        if area <= 0 or w <= 1 or h <= 1:
            continue
        ratio = float(area / max(canvas_area, 1))
        if ratio < min_area_ratio or ratio > max_area_ratio:
            continue

        comp_mask = ((labels[y : y + h, x : x + w] == cid).astype(np.uint8) * 255)
        solidity, hole_ratio = _component_metrics(comp_mask)
        if solidity < 0.25 or hole_ratio > 0.85:
            continue

        # Flatness helps keep dialog/textbox layers while remaining color-agnostic.
        roi_gray = gray[y : y + h, x : x + w]
        vals = roi_gray[comp_mask > 0]
        if vals.size > 16:
            std = float(np.std(vals))
            flatness = float(np.clip(1.0 - (std / 80.0), 0.0, 1.0))
        else:
            flatness = 0.0
        quality = _component_quality(solidity, hole_ratio, flatness)

        out.append(
            WhiteComponent(
                bbox=[x0 + x, y0 + y, x0 + x + w, y0 + y + h],
                area_ratio=ratio,
                solidity=solidity,
                hole_ratio=hole_ratio,
                quality=quality,
                mask=comp_mask,
                x0=x0 + x,
                y0=y0 + y,
            )
        )
    return out


def _intersection_ratio(text_bbox: List[int], comp_bbox: List[int]) -> float:
    tx1, ty1, tx2, ty2 = [int(v) for v in text_bbox]
    cx1, cy1, cx2, cy2 = [int(v) for v in comp_bbox]
    ix1 = max(tx1, cx1)
    iy1 = max(ty1, cy1)
    ix2 = min(tx2, cx2)
    iy2 = min(ty2, cy2)
    inter = float(max(0, ix2 - ix1) * max(0, iy2 - iy1))
    t_area = max(1.0, _bbox_area(text_bbox))
    return float(inter / t_area)


def _point_in_component(px: int, py: int, comp: WhiteComponent) -> bool:
    if px < comp.x0 or py < comp.y0:
        return False
    h, w = comp.mask.shape[:2]
    lx = px - comp.x0
    ly = py - comp.y0
    if lx < 0 or ly < 0 or lx >= w or ly >= h:
        return False
    return bool(comp.mask[ly, lx] > 0)


def _bbox_intersects(a: List[int], b: List[int]) -> bool:
    ax1, ay1, ax2, ay2 = [int(v) for v in a]
    bx1, by1, bx2, by2 = [int(v) for v in b]
    return max(ax1, bx1) < min(ax2, bx2) and max(ay1, by1) < min(ay2, by2)


def _build_text_focus_boxes(texts: List[TextItem], width: int, height: int) -> List[List[int]]:
    boxes: List[List[int]] = []
    for t in texts:
        x1, y1, x2, y2 = [int(v) for v in t.bbox]
        tw = max(1, x2 - x1)
        th = max(1, y2 - y1)
        pad_x = int(np.clip(0.8 * tw + 16, 12, 140))
        pad_y = int(np.clip(1.2 * th + 20, 16, 220))
        ex1 = int(np.clip(x1 - pad_x, 0, width))
        ey1 = int(np.clip(y1 - pad_y, 0, height))
        ex2 = int(np.clip(x2 + pad_x, 0, width))
        ey2 = int(np.clip(y2 + pad_y, 0, height))
        if ex2 > ex1 and ey2 > ey1:
            boxes.append([ex1, ey1, ex2, ey2])
    return boxes


def _build_text_proximity_mask(texts: List[TextItem], width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    for t in texts:
        x1, y1, x2, y2 = [int(v) for v in t.bbox]
        tw = max(1, x2 - x1)
        th = max(1, y2 - y1)
        pad_x = int(np.clip(0.6 * tw + 8, 8, 80))
        pad_y = int(np.clip(0.9 * th + 8, 8, 120))
        ex1 = int(np.clip(x1 - pad_x, 0, width))
        ey1 = int(np.clip(y1 - pad_y, 0, height))
        ex2 = int(np.clip(x2 + pad_x, 0, width))
        ey2 = int(np.clip(y2 + pad_y, 0, height))
        if ex2 > ex1 and ey2 > ey1:
            mask[ey1:ey2, ex1:ex2] = 255
    return mask


def _component_text_proximity(comp: WhiteComponent, text_mask: np.ndarray | None) -> float:
    if text_mask is None:
        return 0.0
    h, w = comp.mask.shape[:2]
    y1, y2 = int(comp.y0), int(comp.y0 + h)
    x1, x2 = int(comp.x0), int(comp.x0 + w)
    if y1 < 0 or x1 < 0 or y2 > text_mask.shape[0] or x2 > text_mask.shape[1]:
        return 0.0
    local = text_mask[y1:y2, x1:x2]
    comp_bin = comp.mask > 0
    area = float(np.count_nonzero(comp_bin))
    if area <= 0:
        return 0.0
    hit = float(np.count_nonzero(comp_bin & (local > 0)))
    return float(np.clip(hit / area, 0.0, 1.0))


def _score_layer_components(
    components: List[WhiteComponent],
    texts: List[TextItem],
    text_mask: np.ndarray | None = None,
) -> Tuple[float, float, float, float, float]:
    if not components:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    white_quality = float(np.mean([c.quality for c in components]))
    comp_areas = [max(1.0, float(np.count_nonzero(c.mask > 0))) for c in components]
    comp_prox = [_component_text_proximity(c, text_mask) for c in components]
    area_sum = max(1.0, float(sum(comp_areas)))
    text_proximity_ratio = float(sum(a * p for a, p in zip(comp_areas, comp_prox)) / area_sum)

    if not texts:
        score = float(np.clip(0.2 * white_quality, 0.0, 1.0))
        return 0.0, 0.0, white_quality, score, 0.0

    overlap_hits = 0
    center_hits = 0
    matched_hits = 0
    overlap_sum = 0.0
    for t in texts:
        tx1, ty1, tx2, ty2 = [int(v) for v in t.bbox]
        cx = int(round((tx1 + tx2) * 0.5))
        cy = int(round((ty1 + ty2) * 0.5))

        max_overlap = 0.0
        center_hit = False
        for comp in components:
            ov = _intersection_ratio(t.bbox, comp.bbox)
            if ov > max_overlap:
                max_overlap = ov
            if _point_in_component(cx, cy, comp):
                center_hit = True
            if center_hit and ov >= 0.08:
                # Component surrounds text center and intersects text bbox.
                tx_area = max(1.0, _bbox_area(t.bbox))
                comp_area = max(1.0, _bbox_area(comp.bbox))
                area_ratio = float(np.clip(comp_area / tx_area, 1.0, 60.0))
                enclosure = float(np.clip(1.0 - abs(np.log(area_ratio / 6.0)) / 2.0, 0.0, 1.0))
                if 0.45 * float(center_hit) + 0.35 * float(np.clip(max_overlap / 0.5, 0.0, 1.0)) + 0.20 * enclosure >= 0.40:
                    matched_hits += 1
                    break

        if max_overlap >= 0.2:
            overlap_hits += 1
        if center_hit:
            center_hits += 1
        overlap_sum += max_overlap

    n = float(max(len(texts), 1))
    text_overlap = float(overlap_hits / n)
    center_hit_ratio = float(center_hits / n)
    text_match_ratio = float(matched_hits / n)
    overlap_mean = float(overlap_sum / n)
    score = float(
        np.clip(
            0.42 * text_match_ratio
            + 0.22 * center_hit_ratio
            + 0.13 * text_overlap
            + 0.10 * white_quality
            + 0.13 * text_proximity_ratio,
            0.0,
            1.0,
        )
    )
    return text_overlap, center_hit_ratio, white_quality, score, overlap_mean


def _collect_text_stats_for_layer(
    layer_box: List[int],
    texts: List[TextItem],
) -> Tuple[int, int, float, float, float]:
    overlap_count = 0
    center_hits = 0
    iou_max = 0.0

    lx1, ly1, lx2, ly2 = [int(v) for v in layer_box]
    for t in texts:
        tb = t.bbox
        if _bbox_intersects(layer_box, tb):
            overlap_count += 1
        iou_max = max(iou_max, _bbox_iou(layer_box, tb))

        tx1, ty1, tx2, ty2 = [int(v) for v in tb]
        cx = int(round((tx1 + tx2) * 0.5))
        cy = int(round((ty1 + ty2) * 0.5))
        if lx1 <= cx < lx2 and ly1 <= cy < ly2:
            center_hits += 1

    n_total = float(max(len(texts), 1))
    overlap_ratio = float(overlap_count / n_total)
    center_ratio = float(center_hits / n_total)
    return overlap_count, center_hits, iou_max, overlap_ratio, center_ratio


def _collect_anchor_group_ids(
    psd: PSDImage,
    layer_ids: List[int],
    layer_by_runtime_id: Optional[Dict[int, Layer]] = None,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
) -> set[int]:
    if not layer_ids:
        return set()
    if layer_by_runtime_id is None:
        layer_by_runtime_id = {int(getattr(layer, "layer_id", -1)): layer for layer in psd.descendants()}
    out: set[int] = set()
    for lid in layer_ids:
        layer = layer_by_runtime_id.get(int(lid))
        if layer is None:
            continue
        for g in _iter_ancestor_groups(layer):
            gid = int(getattr(g, "layer_id", -1))
            if runtime_id_by_obj is not None:
                gid = int(runtime_id_by_obj.get(id(g), gid))
            out.add(gid)
    return out


def _detect_raster_text_layers(
    psd: PSDImage,
    texts: List[TextItem],
    alpha_thr: int = 10,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
) -> List[int]:
    if not texts:
        return []

    width, height = [int(v) for v in psd.size]
    canvas_area = max(1.0, float(width * height))
    text_mask = _build_text_proximity_mask(texts=texts, width=width, height=height)

    scored: List[Tuple[float, int]] = []
    for layer in psd.descendants():
        lid = int(getattr(layer, "layer_id", -1))
        if runtime_id_by_obj is not None:
            lid = int(runtime_id_by_obj.get(id(layer), lid))
        if not bool(getattr(layer, "visible", True)):
            continue
        if str(getattr(layer, "kind", "")) == "group":
            continue

        bbox = _clamp_bbox(layer.bbox, width, height)
        if bbox == (0, 0, 0, 0):
            continue
        layer_box = [bbox[0], bbox[1], bbox[2], bbox[3]]
        bbox_area_ratio = float(_bbox_area(layer_box) / canvas_area)
        if bbox_area_ratio > 0.08:
            continue

        overlap_count, center_hits, iou_max, _, _ = _collect_text_stats_for_layer(layer_box, texts)
        if center_hits < 2 and overlap_count < 3:
            continue

        rgba, real_bbox = _layer_rgba_and_bbox(layer, width, height, prefer_composite=False)
        if rgba is None:
            continue

        alpha_bin = rgba[:, :, 3] > int(alpha_thr)
        nz = int(np.count_nonzero(alpha_bin))
        if nz <= 20:
            continue

        alpha_area_ratio = float(nz / canvas_area)
        if alpha_area_ratio > 0.015:
            continue

        local_area = max(1.0, float(alpha_bin.shape[0] * alpha_bin.shape[1]))
        fill_ratio = float(nz / local_area)
        if fill_ratio < 0.05 or fill_ratio > 0.60:
            continue

        lx1, ly1, lx2, ly2 = [int(v) for v in real_bbox]
        local_text_mask = text_mask[ly1:ly2, lx1:lx2] > 0
        if local_text_mask.shape != alpha_bin.shape:
            hh = min(local_text_mask.shape[0], alpha_bin.shape[0])
            ww = min(local_text_mask.shape[1], alpha_bin.shape[1])
            if hh <= 0 or ww <= 0:
                continue
            local_text_mask = local_text_mask[:hh, :ww]
            alpha_local = alpha_bin[:hh, :ww]
        else:
            alpha_local = alpha_bin

        text_hit_ratio = float(np.count_nonzero(alpha_local & local_text_mask) / max(float(np.count_nonzero(alpha_local)), 1.0))
        if text_hit_ratio < 0.82:
            continue

        iou_score = float(np.clip(iou_max / 0.20, 0.0, 1.0))
        center_score = float(np.clip(center_hits / 4.0, 0.0, 1.0))
        fill_score = float(np.clip(1.0 - abs(fill_ratio - 0.26) / 0.26, 0.0, 1.0))
        score = float(np.clip(0.45 * text_hit_ratio + 0.25 * iou_score + 0.20 * center_score + 0.10 * fill_score, 0.0, 1.0))

        if score >= 0.72 or (text_hit_ratio >= 0.95 and iou_max >= 0.12):
            scored.append((score, lid))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [int(lid) for _, lid in scored]


def rank_bubble_layers(
    psd: PSDImage,
    texts: List[TextItem],
    min_component_area_ratio: float = 0.001,
    white_v_thr: int = 230,
    white_s_thr: int = 50,
    alpha_thr: int = 10,
    exclude_layer_ids: Optional[set[int]] = None,
    text_anchor_group_ids: Optional[set[int]] = None,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
) -> Tuple[List[BubbleLayerScore], Dict[int, str]]:
    _ = white_v_thr
    _ = white_s_thr

    width, height = [int(v) for v in psd.size]
    canvas_area = max(1.0, float(width * height))

    ranking: List[BubbleLayerScore] = []
    layer_path_by_id: Dict[int, str] = {}

    text_layer_ids = {int(t.layer_id) for t in texts if int(t.layer_id) >= 0}
    excluded = set(exclude_layer_ids or set()) | text_layer_ids
    text_mask = _build_text_proximity_mask(texts=texts, width=width, height=height) if texts else None

    for layer in psd.descendants():
        lid = int(getattr(layer, "layer_id", -1))
        if runtime_id_by_obj is not None:
            lid = int(runtime_id_by_obj.get(id(layer), lid))
        kind = str(getattr(layer, "kind", ""))
        layer_path_by_id[lid] = _layer_path(layer)

        if not bool(getattr(layer, "visible", True)):
            continue
        if kind == "group":
            continue
        if lid in excluded:
            continue

        bbox = _clamp_bbox(layer.bbox, width, height)
        if bbox == (0, 0, 0, 0):
            continue
        layer_box = [bbox[0], bbox[1], bbox[2], bbox[3]]

        bbox_area = _bbox_area(layer_box)
        if bbox_area <= 0:
            continue
        bbox_area_ratio = float(bbox_area / canvas_area)
        if bbox_area_ratio > 0.75:
            continue

        overlap_count, center_hits, iou_max, overlap_ratio, center_ratio = _collect_text_stats_for_layer(layer_box, texts)
        if overlap_count <= 0 and center_hits <= 0:
            continue
        if center_hits < 6 and overlap_ratio < 0.18:
            continue
        if bbox_area_ratio > 0.35 and center_ratio < 0.30:
            continue

        anc_ids = set()
        for g in _iter_ancestor_groups(layer):
            gid = int(getattr(g, "layer_id", -1))
            if runtime_id_by_obj is not None:
                gid = int(runtime_id_by_obj.get(id(g), gid))
            anc_ids.add(gid)
        if text_anchor_group_ids and (not (anc_ids & text_anchor_group_ids)) and center_hits < 12:
            continue

        rgba, real_bbox = _layer_rgba_and_bbox(layer, width, height, prefer_composite=False)
        if rgba is None:
            continue

        alpha_bin = rgba[:, :, 3] > int(alpha_thr)
        nz = int(np.count_nonzero(alpha_bin))
        if nz < 40:
            continue

        bubble_area_ratio = float(nz / canvas_area)
        if bubble_area_ratio < max(0.003, float(min_component_area_ratio) * 0.8):
            continue
        if bubble_area_ratio > 0.62:
            continue

        local_area = max(1.0, float(alpha_bin.shape[0] * alpha_bin.shape[1]))
        fill_ratio = float(nz / local_area)
        if fill_ratio < 0.03:
            continue

        text_proximity_ratio = 0.0
        if text_mask is not None:
            lx1, ly1, lx2, ly2 = [int(v) for v in real_bbox]
            local_text_mask = text_mask[ly1:ly2, lx1:lx2] > 0
            if local_text_mask.shape != alpha_bin.shape:
                hh = min(local_text_mask.shape[0], alpha_bin.shape[0])
                ww = min(local_text_mask.shape[1], alpha_bin.shape[1])
                if hh <= 0 or ww <= 0:
                    continue
                local_text_mask = local_text_mask[:hh, :ww]
                alpha_local = alpha_bin[:hh, :ww]
            else:
                alpha_local = alpha_bin
            text_hit = float(np.count_nonzero(alpha_local & local_text_mask))
            text_proximity_ratio = float(np.clip(text_hit / max(float(np.count_nonzero(alpha_local)), 1.0), 0.0, 1.0))

        if text_proximity_ratio < 0.10 and center_hits < 6:
            continue

        gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
        vals = gray[alpha_bin]
        if vals.size > 16:
            std = float(np.std(vals))
            flatness = float(np.clip(1.0 - (std / 90.0), 0.0, 1.0))
        else:
            flatness = 0.0

        fill_score = float(np.clip(1.0 - abs(fill_ratio - 0.32) / 0.32, 0.0, 1.0))
        overlap_score = float(np.clip(overlap_ratio / 0.40, 0.0, 1.0))
        center_score = float(np.clip(center_ratio / 0.40, 0.0, 1.0))
        area_penalty = float(np.clip((bubble_area_ratio - 0.40) / 0.20, 0.0, 1.0))

        group_bonus = 0.16 if (text_anchor_group_ids and (anc_ids & text_anchor_group_ids)) else 0.0

        score = float(
            np.clip(
                0.34 * text_proximity_ratio
                + 0.24 * center_score
                + 0.16 * overlap_score
                + 0.14 * fill_score
                + 0.12 * flatness
                + group_bonus
                - 0.22 * area_penalty,
                0.0,
                1.0,
            )
        )
        if score < 0.18:
            continue

        comp_count = 1
        ranking.append(
            BubbleLayerScore(
                layer_id=lid,
                layer_path=layer_path_by_id[lid],
                kind=kind or "pixel",
                component_count=comp_count,
                bubble_area_ratio=bubble_area_ratio,
                r_bubble=overlap_ratio,
                r_text=center_ratio,
                score=score,
                solidity=fill_ratio,
                hole_ratio=float(np.clip(1.0 - fill_ratio, 0.0, 1.0)),
                text_overlap=overlap_ratio,
                center_hit_ratio=center_ratio,
                white_component_quality=flatness,
                text_proximity_ratio=text_proximity_ratio,
            )
        )

    ranking.sort(
        key=lambda x: (
            x.score,
            x.text_proximity_ratio,
            x.center_hit_ratio,
            x.text_overlap,
            -x.bubble_area_ratio,
        ),
        reverse=True,
    )
    return ranking, layer_path_by_id


def _build_ancestor_map(psd: PSDImage, runtime_id_by_obj: Optional[Dict[int, int]] = None) -> Dict[int, set[int]]:
    ancestors: Dict[int, set[int]] = {}
    for layer in psd.descendants():
        lid = int(getattr(layer, "layer_id", -1))
        if runtime_id_by_obj is not None:
            lid = int(runtime_id_by_obj.get(id(layer), lid))
        cur = layer
        anc: set[int] = set()
        while hasattr(cur, "parent") and cur.parent is not None:
            parent = cur.parent
            if isinstance(parent, PSDImage):
                break
            pid = int(getattr(parent, "layer_id", -1))
            if runtime_id_by_obj is not None:
                pid = int(runtime_id_by_obj.get(id(parent), pid))
            anc.add(pid)
            cur = parent
        ancestors[lid] = anc
    return ancestors


def _select_textbox_layers(
    psd: PSDImage,
    ranking: List[BubbleLayerScore],
    threshold: float = 0.42,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
) -> List[int]:
    ancestors = _build_ancestor_map(psd, runtime_id_by_obj=runtime_id_by_obj)
    selected: List[int] = []

    candidates: List[Tuple[float, BubbleLayerScore]] = []
    score_floor = max(0.18, float(threshold) - 0.20)

    for item in ranking:
        if item.bubble_area_ratio < 0.006:
            continue
        if item.bubble_area_ratio > 0.62:
            continue
        if item.score < score_floor:
            continue
        if item.text_proximity_ratio < 0.20 and not (
            item.text_proximity_ratio >= 0.14 and item.center_hit_ratio >= 0.45 and item.score >= 0.70
        ):
            continue
        if item.center_hit_ratio < 0.04:
            continue
        if item.bubble_area_ratio > 0.45 and item.center_hit_ratio < 0.10:
            continue

        priority = float(
            0.62 * item.score
            + 0.18 * item.text_proximity_ratio
            + 0.10 * item.center_hit_ratio
            + 0.06 * item.text_overlap
            + 0.04 * item.white_component_quality
            - 0.10 * item.bubble_area_ratio
        )
        if priority < 0.22:
            continue
        candidates.append((priority, item))

    candidates.sort(key=lambda x: x[0], reverse=True)

    for _, item in candidates:
        lid = int(item.layer_id)
        conflict = False
        for sid in selected:
            anc_l = ancestors.get(lid, set())
            anc_s = ancestors.get(sid, set())
            if sid in anc_l or lid in anc_s:
                conflict = True
                break
        if conflict:
            continue
        selected.append(lid)
        if len(selected) >= 16:
            break

    return selected


def _mask_from_text_quads(image_shape: Tuple[int, int], texts: List[TextItem]) -> np.ndarray:
    h, w = image_shape
    mask = np.zeros((h, w), dtype=np.uint8)
    for t in texts:
        if t.layer_id >= 0:
            continue

        quad = t.quad if t.quad else _quad_from_bbox(t.bbox)
        pts = np.array([[int(round(p[0])), int(round(p[1]))] for p in quad], dtype=np.int32)
        if pts.shape == (4, 2):
            cv2.fillPoly(mask, [pts], 255)

        x1, y1, x2, y2 = [int(v) for v in t.bbox]
        tw = max(1, x2 - x1)
        th = max(1, y2 - y1)
        pad_x = int(np.clip(0.14 * tw + 2, 2, 10))
        pad_y = int(np.clip(0.20 * th + 2, 2, 14))
        ex1 = int(np.clip(x1 - pad_x, 0, w))
        ey1 = int(np.clip(y1 - pad_y, 0, h))
        ex2 = int(np.clip(x2 + pad_x, 0, w))
        ey2 = int(np.clip(y2 + pad_y, 0, h))
        if ex2 > ex1 and ey2 > ey1:
            cv2.rectangle(mask, (ex1, ey1), (ex2, ey2), 255, thickness=-1)

    if np.count_nonzero(mask) > 0:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
    return mask


def _inpaint_mask_components(image_bgr: np.ndarray, mask: np.ndarray, radius: int = 3) -> np.ndarray:
    if np.count_nonzero(mask) == 0:
        return image_bgr

    out = image_bgr.copy()
    bin_mask = (mask > 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bin_mask, connectivity=8)
    if n <= 1:
        return cv2.inpaint(out, (bin_mask * 255).astype(np.uint8), radius, cv2.INPAINT_TELEA)

    pad = max(4, int(radius) * 3)
    h, w = out.shape[:2]
    for cid in range(1, n):
        x, y, ww, hh, area = [int(v) for v in stats[cid]]
        if area <= 0 or ww <= 0 or hh <= 0:
            continue
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + ww + pad)
        y2 = min(h, y + hh + pad)
        roi = out[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        roi_mask = ((labels[y1:y2, x1:x2] == cid).astype(np.uint8) * 255)
        out[y1:y2, x1:x2] = cv2.inpaint(roi, roi_mask, radius, cv2.INPAINT_TELEA)
    return out


def _mask_from_removed_layers(
    psd: PSDImage,
    remove_layer_ids: List[int],
    image_shape: Tuple[int, int],
    alpha_thr: int = 10,
    layer_by_runtime_id: Optional[Dict[int, Layer]] = None,
) -> np.ndarray:
    h, w = image_shape
    mask = np.zeros((h, w), dtype=np.uint8)
    if not remove_layer_ids:
        return mask

    if layer_by_runtime_id is None:
        layer_by_runtime_id = {int(getattr(layer, "layer_id", -1)): layer for layer in psd.descendants()}
    for lid in sorted(set(remove_layer_ids)):
        layer = layer_by_runtime_id.get(int(lid))
        if layer is None:
            continue
        if str(getattr(layer, "kind", "")) == "group":
            continue

        rgba, bbox = _layer_rgba_and_bbox(layer, w, h, prefer_composite=False)
        if rgba is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        if x2 <= x1 or y2 <= y1:
            continue

        alpha_bin = (rgba[:, :, 3] > int(alpha_thr)).astype(np.uint8) * 255
        hh = min(alpha_bin.shape[0], y2 - y1)
        ww = min(alpha_bin.shape[1], x2 - x1)
        if hh <= 0 or ww <= 0:
            continue

        cur = mask[y1 : y1 + hh, x1 : x1 + ww]
        mask[y1 : y1 + hh, x1 : x1 + ww] = np.maximum(cur, alpha_bin[:hh, :ww])

    if np.count_nonzero(mask) > 0:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    return mask


def build_clean_art(
    psd: PSDImage,
    remove_layer_ids: List[int],
    enable_mask_inpaint: bool = False,
    inpaint_texts: Optional[List[TextItem]] = None,
    source_bgr: Optional[np.ndarray] = None,
    layer_by_runtime_id: Optional[Dict[int, Layer]] = None,
) -> np.ndarray:
    _ = enable_mask_inpaint
    _ = inpaint_texts
    _ = source_bgr

    # Strict mode: remove/hide target layers, then composite. No inpaint.
    if layer_by_runtime_id is None:
        layer_by_runtime_id = {int(getattr(layer, "layer_id", -1)): layer for layer in psd.descendants()}
    visible_backup: Dict[int, bool] = {}
    for lid in sorted(set(remove_layer_ids)):
        layer = layer_by_runtime_id.get(lid)
        if layer is None:
            continue
        visible_backup[lid] = bool(getattr(layer, "visible", True))
        layer.visible = False

    try:
        clean_bgr = _to_bgr_from_pil(psd.composite())
    finally:
        for lid, vis in visible_backup.items():
            layer = layer_by_runtime_id.get(lid)
            if layer is not None:
                layer.visible = bool(vis)
    return clean_bgr


def _serialize_text_canvas_map(texts: List[TextItem]) -> List[Dict]:
    payload: List[Dict] = []
    for t in texts:
        payload.append(
            {
                "text_id": t.text_id,
                "text": t.text,
                "quad": t.quad,
                "bbox": t.bbox,
                "canvas_norm_bbox": t.canvas_norm_bbox,
                "layer_id": t.layer_id,
                "layer_path": t.layer_path,
                "text_source": t.text_source,
                "geom_source": t.geom_source,
                "merge_group_id": t.merge_group_id,
                "merge_status": t.merge_status,
                "confidence": t.conf,
            }
        )
    return payload


def ocr_fallback(image_or_layers) -> List[TextItem]:
    # Backward compatible fallback hook; real OCR is handled in _extract_ocr_texts_from_source.
    _ = image_or_layers
    return []


def preprocess_psd_for_panels(
    image_path: Path,
    out_dir: Path,
    prefix: str,
    min_component_area_ratio: float = 0.001,
    white_v_thr: int = 230,
    white_s_thr: int = 50,
    alpha_thr: int = 10,
    min_components: int = 2,
    min_r_bubble: float = 0.30,
    min_bubble_area_ratio: float = 0.02,
    enable_mask_inpaint: bool = False,
    progress_hook: Optional[Callable[[str], None]] = None,
) -> PsdPreprocessResult:
    def _log(msg: str) -> None:
        if progress_hook is not None:
            progress_hook(msg)

    _ = min_components
    _ = min_r_bubble
    _ = min_bubble_area_ratio
    _ = enable_mask_inpaint

    _log("open psd")
    psd = PSDImage.open(image_path)
    width, height = [int(v) for v in psd.size]
    out_dir.mkdir(parents=True, exist_ok=True)
    ocr_gray_input_path = out_dir / f"{prefix}_ocr_gray_input.png"
    runtime_id_by_obj, layer_by_runtime_id, layer_path_by_runtime_id = _build_runtime_layer_maps(psd)
    _log(f"psd opened: size={width}x{height}")

    _log("compose source image")
    source_bgr = _to_bgr_from_pil(psd.composite())
    _log("extract psd texts")
    psd_texts = extract_psd_texts(psd, width, height, runtime_id_by_obj=runtime_id_by_obj)
    _log(f"psd texts done: count={len(psd_texts)}")
    ocr_result = _extract_ocr_texts_from_source(
        source_bgr,
        width=width,
        height=height,
        gray_png_export_path=ocr_gray_input_path,
        progress_hook=progress_hook,
    )
    _log(
        "ocr done: status=%s, texts=%d, upload_ms=%d, ocr_ms=%d"
        % (ocr_result.status, len(ocr_result.texts), int(ocr_result.upload_latency_ms), int(ocr_result.ocr_latency_ms))
    )

    merged_texts, merge_stats = merge_text_items(psd_texts, ocr_result.texts, width=width, height=height)
    _log(
        "merge texts done: merged=%d, unmatched_psd=%d, unmatched_ocr=%d"
        % (
            len(merged_texts),
            int(merge_stats.get("merge_unmatched_psd_count", 0)),
            int(merge_stats.get("merge_unmatched_ocr_count", 0)),
        )
    )

    text_layer_ids = {int(t.layer_id) for t in psd_texts if int(t.layer_id) >= 0}
    _log("detect raster text layers")
    raster_text_layer_ids = _detect_raster_text_layers(
        psd=psd,
        texts=merged_texts,
        alpha_thr=alpha_thr,
        runtime_id_by_obj=runtime_id_by_obj,
    )
    anchor_group_ids = _collect_anchor_group_ids(
        psd=psd,
        layer_ids=raster_text_layer_ids,
        layer_by_runtime_id=layer_by_runtime_id,
        runtime_id_by_obj=runtime_id_by_obj,
    )
    _log(f"raster text layers done: count={len(raster_text_layer_ids)}")

    _log("rank bubble/textbox layers")
    ranking, layer_path_by_id = rank_bubble_layers(
        psd=psd,
        texts=merged_texts,
        min_component_area_ratio=min_component_area_ratio,
        white_v_thr=white_v_thr,
        white_s_thr=white_s_thr,
        alpha_thr=alpha_thr,
        exclude_layer_ids=set(raster_text_layer_ids),
        text_anchor_group_ids=anchor_group_ids,
        runtime_id_by_obj=runtime_id_by_obj,
    )
    _log(f"layer ranking done: candidates={len(ranking)}")

    textbox_layer_ids = _select_textbox_layers(
        psd=psd,
        ranking=ranking,
        threshold=0.30,
        runtime_id_by_obj=runtime_id_by_obj,
    )
    bubble_layer_id: int | None = int(textbox_layer_ids[0]) if textbox_layer_ids else None
    bubble_layer_path: str | None = (
        layer_path_by_runtime_id.get(bubble_layer_id, layer_path_by_id.get(bubble_layer_id, None))
        if bubble_layer_id is not None
        else None
    )
    _log(f"textbox layers selected: count={len(textbox_layer_ids)}")

    remove_ids = sorted(set(text_layer_ids | set(raster_text_layer_ids) | set(textbox_layer_ids)))
    _log(f"build clean art: remove_layers={len(remove_ids)}")
    clean_bgr = build_clean_art(
        psd=psd,
        remove_layer_ids=remove_ids,
        layer_by_runtime_id=layer_by_runtime_id,
    )
    _log("clean art done")

    art_clean_path = out_dir / f"{prefix}_art_clean.png"
    texts_path = out_dir / f"{prefix}_texts.json"
    texts_merged_path = out_dir / f"{prefix}_texts_merged.json"
    text_canvas_map_path = out_dir / f"{prefix}_text_canvas_map.json"
    textbox_rank_path = out_dir / f"{prefix}_textbox_layer_ranking.json"
    bubble_rank_path = out_dir / f"{prefix}_bubble_layer_ranking.json"

    _log("write preprocess outputs")
    cv2.imwrite(str(art_clean_path), clean_bgr)

    # Keep legacy output name; now it points to merged text results.
    merged_payload = [asdict(t) for t in merged_texts]
    texts_path.write_text(json.dumps(merged_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    texts_merged_path.write_text(json.dumps(merged_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    text_canvas_map_path.write_text(
        json.dumps(_serialize_text_canvas_map(merged_texts), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ranking_payload = [asdict(r) for r in ranking]
    textbox_rank_path.write_text(json.dumps(ranking_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep legacy output name for compatibility.
    bubble_rank_path.write_text(json.dumps(ranking_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("write preprocess outputs done")

    removed_paths = [layer_path_by_runtime_id.get(lid, f"layer#{lid}") for lid in remove_ids]

    if ocr_result.status in {"ok", "ok_empty"}:
        ocr_status = ocr_result.status
    elif ocr_result.status == "disabled":
        ocr_status = "disabled"
    elif ocr_result.status == "failed_input_limit":
        ocr_status = "failed_input_limit"
    else:
        ocr_status = "degraded"

    return PsdPreprocessResult(
        source_bgr=source_bgr,
        clean_bgr=clean_bgr,
        texts=merged_texts,
        bubble_ranking=ranking,
        bubble_layer_id=bubble_layer_id,
        bubble_layer_path=bubble_layer_path,
        removed_layer_ids=remove_ids,
        removed_layer_paths=removed_paths,
        art_clean_path=str(art_clean_path),
        texts_path=str(texts_path),
        bubble_ranking_path=str(bubble_rank_path),
        ocr_status=ocr_status,
        text_backend="psd+ocr_merge",
        textbox_layer_ids=sorted(textbox_layer_ids),
        textbox_layer_paths=[layer_path_by_runtime_id.get(lid, f"layer#{lid}") for lid in sorted(textbox_layer_ids)],
        raster_text_layer_ids=sorted(raster_text_layer_ids),
        raster_text_layer_paths=[
            layer_path_by_runtime_id.get(lid, f"layer#{lid}") for lid in sorted(raster_text_layer_ids)
        ],
        texts_merged_path=str(texts_merged_path),
        textbox_ranking_path=str(textbox_rank_path),
        text_canvas_map_path=str(text_canvas_map_path),
        ocr_request_id=ocr_result.request_id,
        upload_latency_ms=int(ocr_result.upload_latency_ms),
        ocr_latency_ms=int(ocr_result.ocr_latency_ms),
        ocr_input_size=dict(ocr_result.input_size),
        ocr_gray_input_path=str(ocr_result.gray_image_path or ""),
        merge_unmatched_psd_count=int(merge_stats.get("merge_unmatched_psd_count", 0)),
        merge_unmatched_ocr_count=int(merge_stats.get("merge_unmatched_ocr_count", 0)),
        ocr_degraded_reason=ocr_result.degraded_reason,
    )
