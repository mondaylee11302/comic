from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import difflib
import io
import json
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

import cv2
import numpy as np
from psd_tools import PSDImage
from psd_tools.api.layers import Layer

from app.shared.config import load_runtime_dotenv

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


def _load_dotenv_from_repo_root() -> None:
    load_runtime_dotenv()


def _resolve_env_float(name: str, default: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return float(default)
    try:
        val = float(raw)
    except Exception:
        return float(default)
    if val < float(min_value) or val > float(max_value):
        return float(default)
    return float(val)


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


def _bboxes_intersect(
    a: Tuple[int, int, int, int] | List[int],
    b: Tuple[int, int, int, int] | List[int],
) -> bool:
    ax1, ay1, ax2, ay2 = [int(v) for v in a]
    bx1, by1, bx2, by2 = [int(v) for v in b]
    return max(ax1, bx1) < min(ax2, bx2) and max(ay1, by1) < min(ay2, by2)


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


def _is_ocr_payload_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    keywords = (
        "payload exceeds limit after urlencode",
        "image size exceeds maximum limit",
        "http status=413",
        "413 request entity too large",
    )
    return any(k in msg for k in keywords)


def _extract_ocr_texts_from_source(
    source_bgr: np.ndarray,
    width: int,
    height: int,
    gray_png_export_path: Optional[Path] = None,
    ocr_mode: str = "pdf",
    ocr_lang: str = "zh",
    progress_hook: Optional[Callable[[str], None]] = None,
) -> OcrExtractResult:
    def _log(msg: str) -> None:
        if progress_hook is not None:
            progress_hook(msg)

    def _step_start(name: str) -> float:
        _log(f"step={name} start")
        return time.perf_counter()

    def _step_done(name: str, start_ts: float) -> None:
        elapsed_ms = int(max(0, round((time.perf_counter() - start_ts) * 1000.0)))
        _log(f"step={name} done elapsed_ms={elapsed_ms}")

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

    mode = str(ocr_mode or "").strip().lower() or str(os.getenv("VOLC_OCR_API_MODE", "pdf")).strip().lower()
    if mode not in {"pdf", "multilang"}:
        mode = "pdf"
    lang = str(ocr_lang or "").strip().lower() or str(os.getenv("VOLC_OCR_LANG", "zh")).strip().lower()
    if lang not in {"zh", "ko"}:
        lang = "zh"

    _log(f"ocr: encode input image (grayscale original png), mode={mode}, lang={lang}")
    t_encode = _step_start("ocr_encode")
    try:
        if source_bgr.ndim == 2:
            gray = source_bgr
        elif source_bgr.ndim == 3 and source_bgr.shape[2] >= 3:
            gray = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2GRAY)
        else:
            raise ValueError(f"unsupported OCR source image shape: {source_bgr.shape}")

        request_gray_base = gray
        if mode == "multilang":
            request_gray_base = _resize_for_ocr_limits(gray, max_long=2048, max_short=2048)

        png_comp_raw = str(os.getenv("OCR_GRAY_PNG_COMPRESSION", "6")).strip()
        try:
            png_comp = int(png_comp_raw)
        except Exception:
            png_comp = 6
        png_comp = int(np.clip(png_comp, 0, 9))
        ok, encoded = cv2.imencode(".png", request_gray_base, [int(cv2.IMWRITE_PNG_COMPRESSION), png_comp])
        if not ok:
            raise ValueError("failed to encode OCR original grayscale PNG input")
        original_bytes = encoded.tobytes()
        original_meta = {
            "width": int(request_gray_base.shape[1]),
            "height": int(request_gray_base.shape[0]),
            "jpeg_bytes": int(len(original_bytes)),
            "quality": 100,
            "png_compression": int(png_comp),
        }
        gray_image_path = ""
        if gray_png_export_path is not None:
            try:
                gray_png_export_path.parent.mkdir(parents=True, exist_ok=True)
                if cv2.imwrite(str(gray_png_export_path), request_gray_base):
                    gray_image_path = str(gray_png_export_path)
                    _log(f"ocr: gray input saved -> {gray_image_path}")
                else:
                    _log(f"ocr: failed to save gray input -> {gray_png_export_path}")
            except Exception as save_exc:
                _log(f"ocr: failed to save gray input: {save_exc}")
        _step_done("ocr_encode", t_encode)
    except Exception as exc:
        _step_done("ocr_encode", t_encode)
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

    t_request = _step_start("ocr_request")
    try:
        max_retries_raw = str(os.getenv("VOLC_OCR_MAX_RETRIES", "2")).strip()
        try:
            ocr_max_retries = max(1, int(max_retries_raw))
        except Exception:
            ocr_max_retries = 2
        request_meta = dict(original_meta)
        request_bytes = original_bytes
        request_gray = gray
        _log(
            "ocr: request start (mode=%s, lang=%s, grayscale original png, size=%dx%d, bytes=%d, png_comp=%d)"
            % (
                mode,
                lang,
                int(request_meta.get("width", 0)),
                int(request_meta.get("height", 0)),
                int(request_meta.get("jpeg_bytes", 0)),
                int(request_meta.get("png_compression", -1)),
            )
        )
        try:
            ocr_result = ocr_ai_process_bytes(
                file_bytes=request_bytes,
                scene="general",
                file_type=1,
                max_retries=ocr_max_retries,
                ocr_endpoint=mode,
                lang_mode=lang,
            )
        except Exception as first_exc:
            if not _is_ocr_payload_limit_error(first_exc):
                raise
            _log("ocr: original gray png exceeds OCRPdf size limit, fallback to compressed grayscale png")
            max_bytes_raw = str(os.getenv("OCR_GRAY_PNG_MAX_BYTES", str(5 * 1024 * 1024))).strip()
            try:
                fallback_max_bytes = max(256 * 1024, int(max_bytes_raw))
            except Exception:
                fallback_max_bytes = 5 * 1024 * 1024
            request_bytes, request_meta, request_gray = prepare_ocr_input_image_png(
                request_gray_base,
                max_bytes=fallback_max_bytes,
                compression_seq=(3, 6, 9),
                resize_scale_seq=(1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5),
            )
            if gray_png_export_path is not None:
                try:
                    original_path = gray_png_export_path.with_name(f"{gray_png_export_path.stem}_original.png")
                    if cv2.imwrite(str(original_path), request_gray_base):
                        _log(f"ocr: original gray saved -> {original_path}")
                    if cv2.imwrite(str(gray_png_export_path), request_gray):
                        gray_image_path = str(gray_png_export_path)
                        _log(f"ocr: fallback gray input saved -> {gray_image_path}")
                except Exception as save_exc:
                    _log(f"ocr: failed to save fallback gray input: {save_exc}")
            _log(
                "ocr: fallback request start (mode=%s, lang=%s, size=%dx%d, bytes=%d, png_comp=%d)"
                % (
                    mode,
                    lang,
                    int(request_meta.get("width", 0)),
                    int(request_meta.get("height", 0)),
                    int(request_meta.get("jpeg_bytes", 0)),
                    int(request_meta.get("png_compression", -1)),
                )
            )
            ocr_result = ocr_ai_process_bytes(
                file_bytes=request_bytes,
                scene="general",
                file_type=1,
                max_retries=ocr_max_retries,
                ocr_endpoint=mode,
                lang_mode=lang,
            )
        _log(f"ocr: response done ({ocr_result.elapsed_ms}ms), texts={len(ocr_result.texts)}")
        _step_done("ocr_request", t_request)

        t_parse = _step_start("ocr_parse")

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
        _step_done("ocr_parse", t_parse)
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
        _step_done("ocr_request", t_request)
        fail_status = "failed_input_limit" if _is_ocr_payload_limit_error(exc) else "degraded"
        return OcrExtractResult(
            texts=[],
            status=fail_status,
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
    debug_stats: Optional[Dict[str, object]] = None,
) -> Tuple[np.ndarray | None, Tuple[int, int, int, int]]:
    begin_ts = time.perf_counter()

    def _set_debug(
        *,
        decode_source: str,
        decode_elapsed_ms: int,
        decode_ok: bool,
        decode_error: str = "",
    ) -> None:
        if debug_stats is None:
            return
        debug_stats["decode_source"] = str(decode_source)
        debug_stats["decode_elapsed_ms"] = int(max(0, decode_elapsed_ms))
        debug_stats["decode_ok"] = bool(decode_ok)
        debug_stats["decode_error"] = str(decode_error or "")
        debug_stats["rgba_elapsed_ms"] = int(max(0, round((time.perf_counter() - begin_ts) * 1000.0)))

    raw_bbox = tuple(int(v) for v in layer.bbox)
    bbox = _clamp_bbox(raw_bbox, width, height)
    if bbox == (0, 0, 0, 0):
        _set_debug(decode_source="bbox_empty", decode_elapsed_ms=0, decode_ok=False)
        return None, bbox

    rgba = None
    if prefer_composite:
        t0 = time.perf_counter()
        try:
            rendered = layer.composite()
            if rendered is not None:
                rgba = np.array(rendered)
                _set_debug(
                    decode_source="composite_preferred",
                    decode_elapsed_ms=int(max(0, round((time.perf_counter() - t0) * 1000.0))),
                    decode_ok=True,
                )
        except Exception:
            rgba = None
            _set_debug(
                decode_source="composite_preferred_error",
                decode_elapsed_ms=int(max(0, round((time.perf_counter() - t0) * 1000.0))),
                decode_ok=False,
            )

    if rgba is None:
        t0 = time.perf_counter()
        try:
            rgba = layer.numpy()
            if rgba is not None:
                _set_debug(
                    decode_source="numpy",
                    decode_elapsed_ms=int(max(0, round((time.perf_counter() - t0) * 1000.0))),
                    decode_ok=True,
                )
        except Exception:
            rgba = None
            _set_debug(
                decode_source="numpy_error",
                decode_elapsed_ms=int(max(0, round((time.perf_counter() - t0) * 1000.0))),
                decode_ok=False,
            )

    # Fallback to rendered composite only if needed.
    if rgba is None and (not prefer_composite):
        t0 = time.perf_counter()
        try:
            rendered = layer.composite()
            if rendered is not None:
                rgba = np.array(rendered)
                _set_debug(
                    decode_source="composite_fallback",
                    decode_elapsed_ms=int(max(0, round((time.perf_counter() - t0) * 1000.0))),
                    decode_ok=True,
                )
        except Exception:
            rgba = None
            _set_debug(
                decode_source="composite_fallback_error",
                decode_elapsed_ms=int(max(0, round((time.perf_counter() - t0) * 1000.0))),
                decode_ok=False,
            )
    if rgba is None:
        _set_debug(decode_source="decode_none", decode_elapsed_ms=0, decode_ok=False)
        return None, bbox
    if rgba.ndim != 3 or rgba.shape[2] not in {3, 4}:
        _set_debug(decode_source="invalid_rgba_shape", decode_elapsed_ms=0, decode_ok=False)
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
        _set_debug(decode_source="target_empty", decode_elapsed_ms=0, decode_ok=False)
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

    _set_debug(
        decode_source=str(debug_stats.get("decode_source", "unknown")) if debug_stats is not None else "unknown",
        decode_elapsed_ms=int(debug_stats.get("decode_elapsed_ms", 0)) if debug_stats is not None else 0,
        decode_ok=True,
    )
    return rgba_u8, bbox


def _build_text_union_mask(texts: List[TextItem], width: int, height: int) -> np.ndarray:
    def _bbox_connected_with_gap(a: List[int], b: List[int], gap_x: int, gap_y: int) -> bool:
        ax1, ay1, ax2, ay2 = [int(v) for v in a]
        bx1, by1, bx2, by2 = [int(v) for v in b]
        return not (
            (ax2 + gap_x) < bx1
            or (bx2 + gap_x) < ax1
            or (ay2 + gap_y) < by1
            or (by2 + gap_y) < ay1
        )

    def _expand_bbox_scale(bbox: List[int], scale: float) -> List[int]:
        x1, y1, x2, y2 = [float(v) for v in bbox]
        bw = max(1.0, x2 - x1)
        bh = max(1.0, y2 - y1)
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        nw = bw * float(scale)
        nh = bh * float(scale)
        ex1 = int(np.floor(cx - 0.5 * nw))
        ey1 = int(np.floor(cy - 0.5 * nh))
        ex2 = int(np.ceil(cx + 0.5 * nw))
        ey2 = int(np.ceil(cy + 0.5 * nh))
        ex1 = int(np.clip(ex1, 0, width))
        ey1 = int(np.clip(ey1, 0, height))
        ex2 = int(np.clip(ex2, 0, width))
        ey2 = int(np.clip(ey2, 0, height))
        return [ex1, ey1, ex2, ey2]

    mask = np.zeros((height, width), dtype=np.uint8)
    text_boxes: List[List[int]] = []
    for t in texts:
        if t.quad and len(t.quad) == 4:
            x1, y1, x2, y2 = _bbox_from_quad(t.quad)
        else:
            x1, y1, x2, y2 = [int(v) for v in t.bbox]
        x1 = int(np.clip(x1, 0, width))
        x2 = int(np.clip(x2, 0, width))
        y1 = int(np.clip(y1, 0, height))
        y2 = int(np.clip(y2, 0, height))
        if x2 > x1 and y2 > y1:
            text_boxes.append([x1, y1, x2, y2])

    if not text_boxes:
        return mask

    text_heights = [max(1, int(b[3] - b[1])) for b in text_boxes]
    med_h = float(np.median(np.array(text_heights, dtype=np.float32)))
    gap_y = int(np.clip(round(med_h * 0.60), 2, 96))
    gap_x = int(np.clip(round(med_h * 0.40), 2, 72))

    n = len(text_boxes)
    parents = list(range(n))

    def _find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def _union(a: int, b: int) -> None:
        ra = _find(a)
        rb = _find(b)
        if ra != rb:
            parents[rb] = ra

    for i in range(n):
        bi = text_boxes[i]
        for j in range(i + 1, n):
            bj = text_boxes[j]
            if _bbox_connected_with_gap(bi, bj, gap_x=gap_x, gap_y=gap_y):
                _union(i, j)

    merged_boxes: Dict[int, List[int]] = {}
    for i, b in enumerate(text_boxes):
        r = _find(i)
        if r not in merged_boxes:
            merged_boxes[r] = [int(b[0]), int(b[1]), int(b[2]), int(b[3])]
        else:
            cur = merged_boxes[r]
            cur[0] = min(cur[0], int(b[0]))
            cur[1] = min(cur[1], int(b[1]))
            cur[2] = max(cur[2], int(b[2]))
            cur[3] = max(cur[3], int(b[3]))

    for b in merged_boxes.values():
        ex1, ey1, ex2, ey2 = _expand_bbox_scale(b, scale=1.5)
        if ex2 > ex1 and ey2 > ey1:
            mask[ey1:ey2, ex1:ex2] = 255
    return mask


def _layer_union_overlap_stats(
    layer: Layer,
    text_union_mask: np.ndarray,
    width: int,
    height: int,
    alpha_thr: int = 10,
    prefer_composite: bool = False,
    layer_debug: Optional[Dict[str, object]] = None,
) -> Tuple[int, int, float]:
    rgba, real_bbox = _layer_rgba_and_bbox(
        layer,
        width,
        height,
        prefer_composite=prefer_composite,
        debug_stats=layer_debug,
    )
    if rgba is None:
        return 0, 0, 0.0
    alpha_bin = rgba[:, :, 3] > int(alpha_thr)
    layer_pixels = int(np.count_nonzero(alpha_bin))
    if layer_pixels <= 0:
        return 0, 0, 0.0

    lx1, ly1, lx2, ly2 = [int(v) for v in real_bbox]
    local_union = text_union_mask[ly1:ly2, lx1:lx2] > 0
    if local_union.shape != alpha_bin.shape:
        hh = min(local_union.shape[0], alpha_bin.shape[0])
        ww = min(local_union.shape[1], alpha_bin.shape[1])
        if hh <= 0 or ww <= 0:
            return layer_pixels, 0, 0.0
        local_union = local_union[:hh, :ww]
        alpha_local = alpha_bin[:hh, :ww]
    else:
        alpha_local = alpha_bin

    overlap_pixels = int(np.count_nonzero(alpha_local & local_union))
    overlap_ratio = float(np.clip(overlap_pixels / max(float(layer_pixels), 1.0), 0.0, 1.0))
    return layer_pixels, overlap_pixels, overlap_ratio


def _detect_raster_text_layers_by_union(
    psd: PSDImage,
    text_union_mask: np.ndarray,
    in_union_ratio_thr: float = 0.85,
    alpha_thr: int = 10,
    min_pixels: int = 20,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
    exclude_layer_ids: Optional[set[int]] = None,
    exclude_text_layer_ids: Optional[set[int]] = None,
    exclude_raster_text_layer_ids: Optional[set[int]] = None,
    debug_log: Optional[Callable[[str], None]] = None,
    slow_rgba_thr_ms: int = 300,
) -> List[int]:
    def _dlog(msg: str) -> None:
        if debug_log is not None:
            debug_log(msg)

    if text_union_mask.size == 0 or int(np.count_nonzero(text_union_mask)) <= 0:
        return []

    width, height = [int(v) for v in psd.size]
    union_points = cv2.findNonZero((text_union_mask > 0).astype(np.uint8))
    if union_points is None:
        return []
    ux, uy, uw, uh = cv2.boundingRect(union_points)
    text_union_bbox = (
        int(ux),
        int(uy),
        int(ux + uw),
        int(uy + uh),
    )

    excluded_text = set(exclude_text_layer_ids or set())
    excluded_raster = set(exclude_raster_text_layer_ids or set())
    excluded_generic = set(exclude_layer_ids or set()) - excluded_text - excluded_raster
    excluded = set(excluded_text | excluded_raster | excluded_generic)

    _dlog(
        "detect_text_layers config: text_union_bbox=%s threshold=%.2f alpha_thr=%d min_pixels=%d "
        "exclude_text=%d exclude_raster=%d exclude_generic=%d"
        % (
            [int(v) for v in text_union_bbox],
            float(in_union_ratio_thr),
            int(alpha_thr),
            int(min_pixels),
            len(excluded_text),
            len(excluded_raster),
            len(excluded_generic),
        )
    )

    scored: List[Tuple[float, int]] = []
    for layer in psd.descendants():
        lid = int(getattr(layer, "layer_id", -1))
        if runtime_id_by_obj is not None:
            lid = int(runtime_id_by_obj.get(id(layer), lid))
        layer_name = str(getattr(layer, "name", "") or "")
        kind = str(getattr(layer, "kind", ""))
        layer_bbox = _clamp_bbox(tuple(int(v) for v in layer.bbox), width, height)
        excluded_by_text = lid in excluded_text
        excluded_by_raster = lid in excluded_raster
        excluded_by_generic = lid in excluded_generic

        if lid in excluded:
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=%s excluded_by_raster_text=%s decision=rejected reason=excluded"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    str(bool(excluded_by_text)).lower(),
                    str(bool(excluded_by_raster)).lower(),
                )
            )
            continue
        if not bool(getattr(layer, "visible", True)):
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false decision=rejected reason=not_visible"
                % (lid, json.dumps(layer_name, ensure_ascii=False), kind or "unknown", [int(v) for v in layer_bbox])
            )
            continue
        if kind == "group":
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false decision=rejected reason=group_skip"
                % (lid, json.dumps(layer_name, ensure_ascii=False), kind or "unknown", [int(v) for v in layer_bbox])
            )
            continue
        if layer_bbox == (0, 0, 0, 0):
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false decision=rejected reason=empty_bbox"
                % (lid, json.dumps(layer_name, ensure_ascii=False), kind or "unknown", [int(v) for v in layer_bbox])
            )
            continue
        if not _bboxes_intersect(layer_bbox, text_union_bbox):
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false decision=rejected reason=bbox_no_intersect"
                % (lid, json.dumps(layer_name, ensure_ascii=False), kind or "unknown", [int(v) for v in layer_bbox])
            )
            continue
        layer_debug: Dict[str, object] = {}
        layer_pixels, overlap_pixels, overlap_ratio = _layer_union_overlap_stats(
            layer=layer,
            text_union_mask=text_union_mask,
            width=width,
            height=height,
            alpha_thr=alpha_thr,
            prefer_composite=False,
            layer_debug=layer_debug,
        )
        rgba_elapsed_ms = int(layer_debug.get("rgba_elapsed_ms", 0) or 0)
        decode_source = str(layer_debug.get("decode_source", "unknown") or "unknown")
        slow_flag = rgba_elapsed_ms >= int(max(0, slow_rgba_thr_ms))

        if layer_pixels < int(min_pixels):
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false rgba_elapsed_ms=%d decode_source=%s "
                "layer_pixels=%d overlap_pixels=%d overlap_ratio=%.4f slow=%s decision=rejected reason=min_pixels"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    rgba_elapsed_ms,
                    decode_source,
                    int(layer_pixels),
                    int(overlap_pixels),
                    float(overlap_ratio),
                    str(bool(slow_flag)).lower(),
                )
            )
            continue
        if overlap_ratio >= float(in_union_ratio_thr):
            scored.append((overlap_ratio, lid))
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false rgba_elapsed_ms=%d decode_source=%s "
                "layer_pixels=%d overlap_pixels=%d overlap_ratio=%.4f slow=%s decision=accepted reason=ratio_pass"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    rgba_elapsed_ms,
                    decode_source,
                    int(layer_pixels),
                    int(overlap_pixels),
                    float(overlap_ratio),
                    str(bool(slow_flag)).lower(),
                )
            )
        else:
            _dlog(
                "detect_text_layer layer_id=%d layer_name=%s kind=%s layer_bbox=%s "
                "excluded_by_text_layer=false excluded_by_raster_text=false rgba_elapsed_ms=%d decode_source=%s "
                "layer_pixels=%d overlap_pixels=%d overlap_ratio=%.4f slow=%s decision=rejected reason=ratio_below_thr"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    rgba_elapsed_ms,
                    decode_source,
                    int(layer_pixels),
                    int(overlap_pixels),
                    float(overlap_ratio),
                    str(bool(slow_flag)).lower(),
                )
            )
    scored.sort(key=lambda x: x[0], reverse=True)
    return [int(lid) for _, lid in scored]


def rank_bubble_layers_by_text_union(
    psd: PSDImage,
    text_union_mask: np.ndarray,
    overlap_ratio_thr: float = 0.35,
    alpha_thr: int = 10,
    min_pixels: int = 20,
    exclude_layer_ids: Optional[set[int]] = None,
    runtime_id_by_obj: Optional[Dict[int, int]] = None,
    debug_log: Optional[Callable[[str], None]] = None,
    slow_rgba_thr_ms: int = 300,
    slow_topn: int = 10,
) -> Tuple[List[BubbleLayerScore], Dict[int, str]]:
    def _dlog(msg: str) -> None:
        if debug_log is not None:
            debug_log(msg)

    width, height = [int(v) for v in psd.size]
    canvas_area = max(1.0, float(width * height))
    excluded = set(exclude_layer_ids or set())
    ranking: List[BubbleLayerScore] = []
    layer_path_by_id: Dict[int, str] = {}
    layers_total = 0
    layers_evaluated = 0
    layers_accepted = 0
    rgba_elapsed_sum_ms = 0
    max_rgba_elapsed_ms = 0
    top_rows: List[Tuple[int, int, str, str, float]] = []

    _dlog(
        "rank_textbox_layers config: threshold=%.2f alpha_thr=%d min_pixels=%d excluded=%d"
        % (float(overlap_ratio_thr), int(alpha_thr), int(min_pixels), len(excluded))
    )

    for layer in psd.descendants():
        layers_total += 1
        lid = int(getattr(layer, "layer_id", -1))
        if runtime_id_by_obj is not None:
            lid = int(runtime_id_by_obj.get(id(layer), lid))
        kind = str(getattr(layer, "kind", ""))
        layer_name = str(getattr(layer, "name", "") or "")
        layer_path = _layer_path(layer)
        layer_path_by_id[lid] = layer_path
        layer_bbox = _clamp_bbox(tuple(int(v) for v in layer.bbox), width, height)

        if lid in excluded:
            _dlog(
                "rank_textbox_layer layer_id=%d layer_name=%s layer_path=%s kind=%s layer_bbox=%s "
                "excluded=true visible=%s decision=rejected reason=excluded"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    json.dumps(layer_path, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    str(bool(getattr(layer, "visible", True))).lower(),
                )
            )
            continue
        if not bool(getattr(layer, "visible", True)):
            _dlog(
                "rank_textbox_layer layer_id=%d layer_name=%s layer_path=%s kind=%s layer_bbox=%s "
                "excluded=false visible=false decision=rejected reason=not_visible"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    json.dumps(layer_path, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                )
            )
            continue

        layer_debug: Dict[str, object] = {}
        layer_pixels, overlap_pixels, overlap_ratio = _layer_union_overlap_stats(
            layer=layer,
            text_union_mask=text_union_mask,
            width=width,
            height=height,
            alpha_thr=alpha_thr,
            # Group may carry multi-layer dialog bubble content.
            prefer_composite=(kind == "group"),
            layer_debug=layer_debug,
        )
        layers_evaluated += 1
        rgba_elapsed_ms = int(layer_debug.get("rgba_elapsed_ms", 0) or 0)
        decode_source = str(layer_debug.get("decode_source", "unknown") or "unknown")
        slow_flag = rgba_elapsed_ms >= int(max(0, slow_rgba_thr_ms))
        rgba_elapsed_sum_ms += rgba_elapsed_ms
        max_rgba_elapsed_ms = max(max_rgba_elapsed_ms, rgba_elapsed_ms)
        top_rows.append((rgba_elapsed_ms, lid, layer_path, decode_source, float(overlap_ratio)))

        if layer_pixels < int(min_pixels):
            _dlog(
                "rank_textbox_layer layer_id=%d layer_name=%s layer_path=%s kind=%s layer_bbox=%s "
                "excluded=false visible=true rgba_elapsed_ms=%d decode_source=%s "
                "layer_pixels=%d overlap_pixels=%d overlap_ratio=%.4f bubble_area_ratio=%.6f slow=%s "
                "decision=rejected reason=min_pixels"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    json.dumps(layer_path, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    int(rgba_elapsed_ms),
                    decode_source,
                    int(layer_pixels),
                    int(overlap_pixels),
                    float(overlap_ratio),
                    float(layer_pixels / canvas_area),
                    str(bool(slow_flag)).lower(),
                )
            )
            continue
        if overlap_ratio < float(overlap_ratio_thr):
            _dlog(
                "rank_textbox_layer layer_id=%d layer_name=%s layer_path=%s kind=%s layer_bbox=%s "
                "excluded=false visible=true rgba_elapsed_ms=%d decode_source=%s "
                "layer_pixels=%d overlap_pixels=%d overlap_ratio=%.4f bubble_area_ratio=%.6f slow=%s "
                "decision=rejected reason=rejected_below_thr"
                % (
                    lid,
                    json.dumps(layer_name, ensure_ascii=False),
                    json.dumps(layer_path, ensure_ascii=False),
                    kind or "unknown",
                    [int(v) for v in layer_bbox],
                    int(rgba_elapsed_ms),
                    decode_source,
                    int(layer_pixels),
                    int(overlap_pixels),
                    float(overlap_ratio),
                    float(layer_pixels / canvas_area),
                    str(bool(slow_flag)).lower(),
                )
            )
            continue

        bubble_area_ratio = float(layer_pixels / canvas_area)
        ranking.append(
            BubbleLayerScore(
                layer_id=lid,
                layer_path=layer_path_by_id[lid],
                kind=kind or "pixel",
                component_count=1,
                bubble_area_ratio=bubble_area_ratio,
                r_bubble=overlap_ratio,
                r_text=overlap_ratio,
                score=overlap_ratio,
                solidity=float(np.clip(overlap_pixels / max(float(layer_pixels), 1.0), 0.0, 1.0)),
                hole_ratio=0.0,
                text_overlap=overlap_ratio,
                center_hit_ratio=0.0,
                white_component_quality=0.0,
                text_proximity_ratio=overlap_ratio,
            )
        )
        layers_accepted += 1
        _dlog(
            "rank_textbox_layer layer_id=%d layer_name=%s layer_path=%s kind=%s layer_bbox=%s "
            "excluded=false visible=true rgba_elapsed_ms=%d decode_source=%s "
            "layer_pixels=%d overlap_pixels=%d overlap_ratio=%.4f bubble_area_ratio=%.6f slow=%s "
            "decision=accepted reason=ratio_pass"
            % (
                lid,
                json.dumps(layer_name, ensure_ascii=False),
                json.dumps(layer_path, ensure_ascii=False),
                kind or "unknown",
                [int(v) for v in layer_bbox],
                int(rgba_elapsed_ms),
                decode_source,
                int(layer_pixels),
                int(overlap_pixels),
                float(overlap_ratio),
                float(bubble_area_ratio),
                str(bool(slow_flag)).lower(),
            )
        )

    ranking.sort(
        key=lambda x: (
            x.score,
            x.text_proximity_ratio,
            -x.bubble_area_ratio,
        ),
        reverse=True,
    )

    avg_rgba_elapsed_ms = float(rgba_elapsed_sum_ms / max(1, layers_evaluated))
    _dlog(
        "rank_textbox_layers summary: layers_total=%d layers_evaluated=%d layers_accepted=%d "
        "sum_rgba_elapsed_ms=%d avg_rgba_elapsed_ms=%.1f max_rgba_elapsed_ms=%d"
        % (
            int(layers_total),
            int(layers_evaluated),
            int(layers_accepted),
            int(rgba_elapsed_sum_ms),
            float(avg_rgba_elapsed_ms),
            int(max_rgba_elapsed_ms),
        )
    )
    top_rows.sort(key=lambda x: x[0], reverse=True)
    for idx, (ms, lid, path, src, ratio) in enumerate(top_rows[: max(0, int(slow_topn))], start=1):
        _dlog(
            "rank_textbox_layers top_slow rank=%d layer_id=%d rgba_elapsed_ms=%d decode_source=%s overlap_ratio=%.4f layer_path=%s"
            % (int(idx), int(lid), int(ms), src, float(ratio), json.dumps(path, ensure_ascii=False))
        )
    return ranking, layer_path_by_id


def build_clean_art(
    psd: PSDImage,
    remove_layer_ids: List[int],
    layer_by_runtime_id: Optional[Dict[int, Layer]] = None,
) -> np.ndarray:
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
    alpha_thr: int = 10,
    enable_mask_inpaint: bool = False,
    ocr_mode: str = "pdf",
    ocr_lang: str = "zh",
    progress_hook: Optional[Callable[[str], None]] = None,
) -> PsdPreprocessResult:
    def _log(msg: str) -> None:
        if progress_hook is not None:
            progress_hook(msg)

    def _step_start(name: str) -> float:
        _log(f"step={name} start")
        return time.perf_counter()

    def _step_done(name: str, start_ts: float) -> None:
        elapsed_ms = int(max(0, round((time.perf_counter() - start_ts) * 1000.0)))
        _log(f"step={name} done elapsed_ms={elapsed_ms}")

    _ = enable_mask_inpaint

    _load_dotenv_from_repo_root()
    raster_text_in_union_ratio_thr = _resolve_env_float(
        "PREPROCESS_RASTER_TEXT_IN_UNION_RATIO_THR",
        default=0.85,
        min_value=0.0,
        max_value=1.0,
    )
    textbox_overlap_ratio_thr = _resolve_env_float(
        "PREPROCESS_TEXTBOX_OVERLAP_RATIO_THR",
        default=0.35,
        min_value=0.0,
        max_value=1.0,
    )

    t_step = _step_start("open_psd")
    psd = PSDImage.open(image_path)
    width, height = [int(v) for v in psd.size]
    out_dir.mkdir(parents=True, exist_ok=True)
    ocr_gray_input_path = out_dir / f"{prefix}_ocr_gray_input.png"
    runtime_id_by_obj, layer_by_runtime_id, layer_path_by_runtime_id = _build_runtime_layer_maps(psd)
    _step_done("open_psd", t_step)
    _log(f"psd opened: size={width}x{height}")

    t_step = _step_start("compose_source_image")
    source_bgr = _to_bgr_from_pil(psd.composite())
    _step_done("compose_source_image", t_step)

    t_step = _step_start("extract_psd_texts")
    psd_texts = extract_psd_texts(psd, width, height, runtime_id_by_obj=runtime_id_by_obj)
    _step_done("extract_psd_texts", t_step)
    _log(f"psd texts done: count={len(psd_texts)}")

    t_step = _step_start("ocr_total")
    ocr_result = _extract_ocr_texts_from_source(
        source_bgr,
        width=width,
        height=height,
        gray_png_export_path=ocr_gray_input_path,
        ocr_mode=ocr_mode,
        ocr_lang=ocr_lang,
        progress_hook=progress_hook,
    )
    _step_done("ocr_total", t_step)
    _log(
        "ocr done: status=%s, texts=%d, upload_ms=%d, ocr_ms=%d"
        % (ocr_result.status, len(ocr_result.texts), int(ocr_result.upload_latency_ms), int(ocr_result.ocr_latency_ms))
    )

    t_step = _step_start("merge_texts")
    merged_texts, merge_stats = merge_text_items(psd_texts, ocr_result.texts, width=width, height=height)
    _step_done("merge_texts", t_step)
    _log(
        "merge texts done: merged=%d, unmatched_psd=%d, unmatched_ocr=%d"
        % (
            len(merged_texts),
            int(merge_stats.get("merge_unmatched_psd_count", 0)),
            int(merge_stats.get("merge_unmatched_ocr_count", 0)),
        )
    )

    text_layer_ids = {int(t.layer_id) for t in psd_texts if int(t.layer_id) >= 0}
    t_step = _step_start("build_text_union_mask")
    text_union_mask = _build_text_union_mask(merged_texts, width=width, height=height)
    text_union_pixels = int(np.count_nonzero(text_union_mask))
    text_union_ratio = float(text_union_pixels / max(float(width * height), 1.0))
    _step_done("build_text_union_mask", t_step)
    _log(f"text union built: pixels={text_union_pixels}, area_ratio={text_union_ratio:.4f}")

    t_step = _step_start("detect_raster_text_layers")
    raster_text_layer_ids = _detect_raster_text_layers_by_union(
        psd=psd,
        text_union_mask=text_union_mask,
        in_union_ratio_thr=raster_text_in_union_ratio_thr,
        alpha_thr=alpha_thr,
        min_pixels=20,
        runtime_id_by_obj=runtime_id_by_obj,
        exclude_layer_ids=set(text_layer_ids),
        exclude_text_layer_ids=set(text_layer_ids),
        exclude_raster_text_layer_ids=set(),
        debug_log=_log,
        slow_rgba_thr_ms=300,
    )
    _step_done("detect_raster_text_layers", t_step)
    _log(
        "raster text layers done (>=%d%% in text union): count=%d"
        % (int(round(raster_text_in_union_ratio_thr * 100.0)), len(raster_text_layer_ids))
    )

    _log(
        "rank_textbox_layers formula: text_union_source=merged_psd_ocr candidate_scope=include_group "
        "exclude_before_compute=true ratio_formula=overlap_pixels/candidate_pixels threshold=%.4f"
        % float(textbox_overlap_ratio_thr)
    )
    t_step = _step_start("rank_textbox_layers")
    ranking, layer_path_by_id = rank_bubble_layers_by_text_union(
        psd=psd,
        text_union_mask=text_union_mask,
        overlap_ratio_thr=textbox_overlap_ratio_thr,
        alpha_thr=alpha_thr,
        min_pixels=20,
        exclude_layer_ids=set(text_layer_ids) | set(raster_text_layer_ids),
        runtime_id_by_obj=runtime_id_by_obj,
        debug_log=_log,
        slow_rgba_thr_ms=300,
        slow_topn=10,
    )
    _step_done("rank_textbox_layers", t_step)
    _log(
        "textbox ranking done (>=%d%% overlap): candidates=%d"
        % (int(round(textbox_overlap_ratio_thr * 100.0)), len(ranking))
    )

    textbox_layer_ids = [int(r.layer_id) for r in ranking]
    bubble_layer_id: int | None = int(textbox_layer_ids[0]) if textbox_layer_ids else None
    bubble_layer_path: str | None = (
        layer_path_by_runtime_id.get(bubble_layer_id, layer_path_by_id.get(bubble_layer_id, None))
        if bubble_layer_id is not None
        else None
    )
    _log(f"textbox layers selected: count={len(textbox_layer_ids)}")

    remove_ids = sorted(set(text_layer_ids | set(raster_text_layer_ids) | set(textbox_layer_ids)))
    t_step = _step_start("build_clean_art")
    _log(f"build clean art: remove_layers={len(remove_ids)}")
    clean_bgr = build_clean_art(
        psd=psd,
        remove_layer_ids=remove_ids,
        layer_by_runtime_id=layer_by_runtime_id,
    )
    _step_done("build_clean_art", t_step)
    _log("clean art done")

    art_clean_path = out_dir / f"{prefix}_art_clean.png"
    texts_path = out_dir / f"{prefix}_texts.json"
    texts_merged_path = out_dir / f"{prefix}_texts_merged.json"
    text_canvas_map_path = out_dir / f"{prefix}_text_canvas_map.json"
    textbox_rank_path = out_dir / f"{prefix}_textbox_layer_ranking.json"
    bubble_rank_path = out_dir / f"{prefix}_bubble_layer_ranking.json"

    t_step = _step_start("write_outputs")
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
    _step_done("write_outputs", t_step)
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
