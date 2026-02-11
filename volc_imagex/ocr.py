from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

import requests

from volc_imagex._utils import (
    backoff_seconds,
    elapsed_ms,
    extract_request_id,
    is_retryable_error,
    summarize_error,
    validate_max_retries,
)
from volc_imagex.types import OCRResult, OCRTextBox

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://dayat1g9w13arco5.aistudio-app.com/layout-parsing"
VALID_SCENES = {"general", "license"}
VALID_DATA_TYPES = {"uri", "url", "file"}
_QUAD_KEYS = (
    "Location",
    "location",
    "Quad",
    "quad",
    "Polygon",
    "polygon",
    "Points",
    "points",
    "BBox",
    "bbox",
    "Box",
    "box",
    "block_bbox",
    "block_polygon_points",
    "coordinate",
    "coordinates",
)


class PaddleHTTPError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = int(status_code)
        body_short = (body or "").strip()
        if len(body_short) > 500:
            body_short = body_short[:500] + "..."
        super().__init__(f"paddle_ocr http status={status_code}, body={body_short}")


def _validate_scene(scene: str) -> str:
    val = (scene or "").strip().lower()
    if val not in VALID_SCENES:
        raise ValueError(f"scene must be one of {sorted(VALID_SCENES)}, got: {scene}")
    return val


def _validate_data_type(data_type: str) -> str:
    val = (data_type or "").strip().lower()
    if val not in VALID_DATA_TYPES:
        raise ValueError(f"data_type must be one of {sorted(VALID_DATA_TYPES)}, got: {data_type}")
    return val


def _validate_object_key_or_url(value: str, data_type: str) -> str:
    val = (value or "").strip()
    if not val:
        raise ValueError("object_key_or_url is required")
    if data_type == "url" and not (val.startswith("http://") or val.startswith("https://")):
        raise ValueError("data_type=url requires object_key_or_url to start with http:// or https://")
    return val


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(dotenv_path=root / ".env", override=False)
    except Exception:
        return


def _resolve_paddle_config() -> Tuple[str, str]:
    _load_dotenv_from_repo_root()
    api_url = (
        os.getenv("API_URL", "").strip()
        or os.getenv("PADDLE_OCR_API_URL", "").strip()
        or DEFAULT_API_URL
    )
    token = os.getenv("TOKEN", "").strip() or os.getenv("PADDLE_OCR_TOKEN", "").strip()
    if not token:
        raise ValueError("missing OCR token; set TOKEN in .env")
    return api_url, token


def _quad_from_bbox(x1: float, y1: float, x2: float, y2: float) -> List[List[float]]:
    return [
        [float(x1), float(y1)],
        [float(x2), float(y1)],
        [float(x2), float(y2)],
        [float(x1), float(y2)],
    ]


def _parse_quad_value(location_val: Any, item: Mapping[str, Any]) -> List[List[float]]:
    if location_val is None:
        raise ValueError(f"missing Location in OCR output item: {item}")

    if isinstance(location_val, Mapping):
        corners = [
            ("LeftTop", "leftTop", "left_top"),
            ("RightTop", "rightTop", "right_top"),
            ("RightBottom", "rightBottom", "right_bottom"),
            ("LeftBottom", "leftBottom", "left_bottom"),
        ]
        points: List[List[float]] = []
        for aliases in corners:
            point = None
            for alias in aliases:
                if alias in location_val:
                    point = location_val[alias]
                    break
            if isinstance(point, Mapping):
                x = point.get("X", point.get("x"))
                y = point.get("Y", point.get("y"))
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    points.append([float(x), float(y)])
        if len(points) == 4:
            return points

        x1 = location_val.get("x1", location_val.get("left"))
        y1 = location_val.get("y1", location_val.get("top"))
        x2 = location_val.get("x2", location_val.get("right"))
        y2 = location_val.get("y2", location_val.get("bottom"))
        if all(isinstance(v, (int, float)) for v in (x1, y1, x2, y2)):
            return _quad_from_bbox(float(x1), float(y1), float(x2), float(y2))

        x = location_val.get("x")
        y = location_val.get("y")
        w = location_val.get("width", location_val.get("w"))
        h = location_val.get("height", location_val.get("h"))
        if all(isinstance(v, (int, float)) for v in (x, y, w, h)):
            return _quad_from_bbox(float(x), float(y), float(x) + float(w), float(y) + float(h))

        for key in ("points", "Points", "polygon", "Polygon", "quad", "Quad", "bbox", "BBox"):
            if key in location_val:
                return _parse_quad_value(location_val[key], item)

        raise ValueError(f"invalid Location format in OCR output item: {item}")

    if isinstance(location_val, list):
        if len(location_val) == 8 and all(isinstance(v, (int, float)) for v in location_val):
            return [
                [float(location_val[0]), float(location_val[1])],
                [float(location_val[2]), float(location_val[3])],
                [float(location_val[4]), float(location_val[5])],
                [float(location_val[6]), float(location_val[7])],
            ]
        if len(location_val) == 4 and all(isinstance(v, (int, float)) for v in location_val):
            return _quad_from_bbox(
                float(location_val[0]),
                float(location_val[1]),
                float(location_val[2]),
                float(location_val[3]),
            )
        if len(location_val) == 4 and all(isinstance(v, (list, tuple)) and len(v) >= 2 for v in location_val):
            return [[float(v[0]), float(v[1])] for v in location_val]
        raise ValueError(f"invalid Location format in OCR output item: {item}")

    raise ValueError(f"invalid Location format in OCR output item: {item}")


def _parse_quad(item: Mapping[str, Any], required: bool) -> List[List[float]]:
    location_val: Any = None
    for key in _QUAD_KEYS:
        if key in item:
            location_val = item[key]
            break
    if location_val is None:
        x1 = item.get("x1", item.get("left"))
        y1 = item.get("y1", item.get("top"))
        x2 = item.get("x2", item.get("right"))
        y2 = item.get("y2", item.get("bottom"))
        if all(isinstance(v, (int, float)) for v in (x1, y1, x2, y2)):
            return _quad_from_bbox(float(x1), float(y1), float(x2), float(y2))
        if required:
            raise ValueError(f"missing Location in OCR output item: {item}")
        return []

    return _parse_quad_value(location_val, item)


def _extract_text_value(item: Mapping[str, Any]) -> Optional[str]:
    for key in (
        "Content",
        "content",
        "Text",
        "text",
        "Value",
        "value",
        "Word",
        "word",
        "Words",
        "words",
        "OCRText",
        "ocrText",
        "block_content",
        "block_text",
    ):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_confidence(item: Mapping[str, Any]) -> Optional[float]:
    for key in ("Confidence", "confidence", "Score", "score", "Probability", "probability"):
        val = item.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return None


def _iter_dict_nodes(obj: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        yield obj
        for val in obj.values():
            yield from _iter_dict_nodes(val)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dict_nodes(item)


def _find_general_items(raw_output: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    priority_keys = {
        "texts",
        "textlist",
        "textsinfo",
        "generalinfo",
        "items",
        "lines",
        "ocrtexts",
    }

    for node in _iter_dict_nodes(raw_output):
        for k, v in node.items():
            if not isinstance(v, list):
                continue
            if k.lower() in priority_keys and all(isinstance(i, Mapping) for i in v):
                return [dict(i) for i in v]

    for node in _iter_dict_nodes(raw_output):
        for key in _QUAD_KEYS:
            val = node.get(key)
            if isinstance(val, list) and val and all(isinstance(i, Mapping) for i in val):
                if any(_extract_text_value(i) for i in val):
                    return [dict(i) for i in val]
    return []


def _parse_general_output(raw_output: Mapping[str, Any]) -> List[OCRTextBox]:
    texts: List[OCRTextBox] = []
    seen: set[tuple[str, tuple[tuple[float, float], ...]]] = set()
    primary_items = _find_general_items(raw_output)
    fallback_items = [dict(node) for node in _iter_dict_nodes(raw_output)] if primary_items else []
    item_groups: List[List[Mapping[str, Any]]] = []
    if primary_items:
        item_groups.append(primary_items)
    if fallback_items:
        item_groups.append(fallback_items)

    if not item_groups:
        item_groups.append([dict(node) for node in _iter_dict_nodes(raw_output)])

    for items in item_groups:
        for item in items:
            text = _extract_text_value(item)
            if not text:
                continue
            try:
                quad = _parse_quad(item, required=True)
            except ValueError:
                continue
            confidence = _extract_confidence(item)
            key = (text, tuple((float(p[0]), float(p[1])) for p in quad))
            if key in seen:
                continue
            seen.add(key)
            texts.append(OCRTextBox(text=text, quad=quad, confidence=confidence))
    return texts


def _parse_fields_from_mapping(raw_map: Mapping[str, Any]) -> Dict[str, OCRTextBox]:
    fields: Dict[str, OCRTextBox] = {}
    for field_name, value in raw_map.items():
        if isinstance(value, Mapping):
            text = _extract_text_value(value)
            if text is None:
                nested_value = value.get("Value")
                if isinstance(nested_value, Mapping):
                    text = _extract_text_value(nested_value)
                    value = nested_value
            if text is None:
                continue

            quad = []
            if any(k in value for k in ("Location", "location", "Quad", "quad", "Polygon", "polygon", "Points", "points")):
                quad = _parse_quad(value, required=False)
            fields[str(field_name)] = OCRTextBox(
                text=text,
                quad=quad,
                confidence=_extract_confidence(value),
            )
        elif isinstance(value, str) and value.strip():
            fields[str(field_name)] = OCRTextBox(text=value.strip(), quad=[], confidence=None)
    return fields


def _parse_fields_from_list(items: List[Any]) -> Dict[str, OCRTextBox]:
    fields: Dict[str, OCRTextBox] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        name = None
        for name_key in ("Name", "Field", "Key", "Label", "Title"):
            if isinstance(item.get(name_key), str) and item[name_key].strip():
                name = item[name_key].strip()
                break
        if not name:
            continue
        text = _extract_text_value(item)
        if not text:
            continue
        quad = []
        if any(k in item for k in ("Location", "location", "Quad", "quad", "Polygon", "polygon", "Points", "points")):
            quad = _parse_quad(item, required=False)
        fields[name] = OCRTextBox(text=text, quad=quad, confidence=_extract_confidence(item))
    return fields


def _parse_license_output(raw_output: Mapping[str, Any]) -> Dict[str, OCRTextBox]:
    preferred_keys = (
        "Fields",
        "FieldMap",
        "LicenseInfo",
        "LicenseFields",
        "Data",
        "Result",
    )
    for key in preferred_keys:
        val = raw_output.get(key)
        if isinstance(val, Mapping):
            parsed = _parse_fields_from_mapping(val)
            if parsed:
                return parsed
        if isinstance(val, list):
            parsed = _parse_fields_from_list(val)
            if parsed:
                return parsed

    for node in _iter_dict_nodes(raw_output):
        parsed = _parse_fields_from_mapping(node)
        if parsed:
            return parsed
    return {}


def parse_result_output_value(output_value: Any) -> Dict[str, Any]:
    parsed = output_value
    for _ in range(2):
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        else:
            break
    if isinstance(parsed, list):
        return {"items": parsed}
    if not isinstance(parsed, Mapping):
        raise ValueError(f"parsed OCR output must be dict/list, got {type(parsed).__name__}")
    return dict(parsed)


def parse_ai_process_response(resp: Mapping[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    if not isinstance(resp, Mapping):
        raise ValueError(f"ai_process response must be mapping, got {type(resp).__name__}")
    request_id = extract_request_id(resp)

    # Backward compatibility: old veImageX AIProcess response format.
    result = resp.get("Result")
    if isinstance(result, Mapping):
        if "Output" not in result:
            raise ValueError(f"missing Result.Output in ai_process response: {resp}")
        raw_output = result["Output"]
        parsed_output = parse_result_output_value(raw_output)
        return parsed_output, request_id

    # Paddle layout-parsing response format.
    paddle_result = resp.get("result")
    if isinstance(paddle_result, list):
        return {"items": paddle_result}, request_id
    if isinstance(paddle_result, Mapping):
        return dict(paddle_result), request_id
    raise ValueError(f"missing result in paddle OCR response: {resp}")


def _ocr_ai_process_bytes_internal(
    *,
    file_bytes: bytes,
    file_type: int,
    scene: str,
    max_retries: int,
    api_url: str,
    token: str,
    data_type_label: str,
) -> OCRResult:
    sc = _validate_scene(scene)
    retries = validate_max_retries(max_retries)
    if int(file_type) not in {0, 1}:
        raise ValueError(f"file_type must be 0(pdf) or 1(image), got: {file_type}")
    if not file_bytes:
        raise ValueError("OCR input is empty")

    payload = {
        "file": base64.b64encode(file_bytes).decode("ascii"),
        "fileType": int(file_type),
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    begin = time.perf_counter()
    last_exc: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        resp: Any = None
        request_id: Optional[str] = None
        parsed_output: Optional[Dict[str, Any]] = None
        try:
            http_resp = requests.post(api_url, json=payload, headers=headers, timeout=120)
            if http_resp.status_code != 200:
                raise PaddleHTTPError(http_resp.status_code, http_resp.text)
            resp = http_resp.json()
            parsed_output, request_id = parse_ai_process_response(resp)
            request_id = (
                request_id
                or http_resp.headers.get("x-request-id")
                or http_resp.headers.get("X-Request-Id")
                or http_resp.headers.get("x-bce-request-id")
            )
            if sc == "general":
                texts = _parse_general_output(parsed_output)
                fields = {}
            else:
                fields = _parse_license_output(parsed_output)
                texts = []

            total_ms = elapsed_ms(begin)
            logger.info(
                "ocr_ai_process success scene=%s data_type=%s elapsed_ms=%d retries=%d request_id=%s",
                sc,
                data_type_label,
                total_ms,
                attempt - 1,
                request_id,
            )
            return OCRResult(
                scene=sc,
                texts=texts,
                fields=fields,
                raw_output=parsed_output,
                request_id=request_id,
                elapsed_ms=total_ms,
                retries=attempt - 1,
                raw_resp=dict(resp) if isinstance(resp, Mapping) else {"raw": resp, "request_id": request_id},
            )
        except ValueError as exc:
            total_ms = elapsed_ms(begin)
            request_id = request_id or (extract_request_id(resp) if isinstance(resp, Mapping) else None)
            summary = summarize_error(exc)
            logger.error(
                "ocr_ai_process invalid_response scene=%s data_type=%s elapsed_ms=%d retries=%d request_id=%s error=%s",
                sc,
                data_type_label,
                total_ms,
                attempt - 1,
                request_id,
                summary,
            )
            raise ValueError(
                f"ocr_ai_process invalid response(scene={sc}, data_type={data_type_label}, elapsed_ms={total_ms}, "
                f"request_id={request_id}): {summary}; raw_output={parsed_output}"
            ) from exc
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable_error(exc)
            summary = summarize_error(exc)
            total_ms = elapsed_ms(begin)
            if (not retryable) or attempt >= retries:
                logger.error(
                    "ocr_ai_process failed scene=%s data_type=%s elapsed_ms=%d retries=%d request_id=%s error=%s",
                    sc,
                    data_type_label,
                    total_ms,
                    attempt - 1,
                    None,
                    summary,
                )
                raise RuntimeError(
                    f"ocr_ai_process failed(scene={sc}, data_type={data_type_label}, "
                    f"elapsed_ms={total_ms}, retries={attempt - 1}): {summary}"
                ) from exc

            sleep_s = backoff_seconds(attempt)
            logger.warning(
                "ocr_ai_process retry scene=%s data_type=%s attempt=%d/%d sleep=%.1fs error=%s",
                sc,
                data_type_label,
                attempt,
                retries,
                sleep_s,
                summary,
            )
            time.sleep(sleep_s)

    raise RuntimeError(f"ocr_ai_process failed after retries: {last_exc}")


def ocr_ai_process_bytes(
    file_bytes: bytes,
    scene: str = "general",
    file_type: int = 1,
    max_retries: int = 4,
) -> OCRResult:
    api_url, token = _resolve_paddle_config()
    return _ocr_ai_process_bytes_internal(
        file_bytes=file_bytes,
        file_type=int(file_type),
        scene=scene,
        max_retries=max_retries,
        api_url=api_url,
        token=token,
        data_type_label="bytes",
    )


def ocr_ai_process(
    service_id: Optional[str],
    data_type: str,
    object_key_or_url: str,
    scene: str = "general",
    model_id: str = "default",
    max_retries: int = 4,
) -> OCRResult:
    _ = service_id
    _ = model_id
    dt = _validate_data_type(data_type)
    obj_or_url = _validate_object_key_or_url(object_key_or_url, dt)

    file_bytes: bytes
    file_type = 1
    if dt == "file":
        local_path = Path(obj_or_url).expanduser()
        if not local_path.exists() or not local_path.is_file():
            raise ValueError(f"local file not found: {obj_or_url}")
        file_bytes = local_path.read_bytes()
        if local_path.suffix.lower() == ".pdf":
            file_type = 0
    elif dt == "url":
        parsed = urlparse(obj_or_url)
        if parsed.path.lower().endswith(".pdf"):
            file_type = 0
        dl_resp = requests.get(obj_or_url, timeout=60)
        if dl_resp.status_code != 200:
            raise PaddleHTTPError(dl_resp.status_code, dl_resp.text)
        file_bytes = dl_resp.content
    else:  # dt == "uri"
        possible_local = Path(obj_or_url).expanduser()
        if possible_local.exists() and possible_local.is_file():
            file_bytes = possible_local.read_bytes()
            if possible_local.suffix.lower() == ".pdf":
                file_type = 0
        elif obj_or_url.startswith(("http://", "https://")):
            parsed = urlparse(obj_or_url)
            if parsed.path.lower().endswith(".pdf"):
                file_type = 0
            dl_resp = requests.get(obj_or_url, timeout=60)
            if dl_resp.status_code != 200:
                raise PaddleHTTPError(dl_resp.status_code, dl_resp.text)
            file_bytes = dl_resp.content
        else:
            public_domain = os.getenv("VOLC_OCR_PUBLIC_DOMAIN", "").strip()
            if not public_domain:
                raise ValueError(
                    "data_type=uri requires a local path/url or VOLC_OCR_PUBLIC_DOMAIN to convert object key into URL"
                )
            url = f"https://{public_domain.strip('/')}/{obj_or_url.lstrip('/')}"
            dl_resp = requests.get(url, timeout=60)
            if dl_resp.status_code != 200:
                raise PaddleHTTPError(dl_resp.status_code, dl_resp.text)
            file_bytes = dl_resp.content

    api_url, token = _resolve_paddle_config()
    return _ocr_ai_process_bytes_internal(
        file_bytes=file_bytes,
        file_type=file_type,
        scene=scene,
        max_retries=max_retries,
        api_url=api_url,
        token=token,
        data_type_label=dt,
    )
