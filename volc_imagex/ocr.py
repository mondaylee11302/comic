from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from volc_imagex._utils import (
    backoff_seconds,
    elapsed_ms,
    extract_request_id,
    is_retryable_error,
    summarize_error,
    validate_max_retries,
)
from volc_imagex.client import new_imagex_service, resolve_service_id
from volc_imagex.types import OCRResult, OCRTextBox

logger = logging.getLogger(__name__)

VALID_SCENES = {"general", "license"}
VALID_DATA_TYPES = {"uri", "url"}


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


def _validate_service_id(service_id: Optional[str]) -> str:
    return resolve_service_id(service_id)


def _validate_object_key_or_url(value: str, data_type: str) -> str:
    val = (value or "").strip()
    if not val:
        raise ValueError("object_key_or_url is required")
    if data_type == "url" and not (val.startswith("http://") or val.startswith("https://")):
        raise ValueError("data_type=url requires object_key_or_url to start with http:// or https://")
    return val


def _parse_quad(item: Mapping[str, Any], required: bool) -> List[List[float]]:
    location_val = None
    for key in ("Location", "location", "Quad", "quad", "Polygon", "polygon", "Points", "points"):
        if key in item:
            location_val = item[key]
            break
    if location_val is None:
        if required:
            raise ValueError(f"missing Location in OCR output item: {item}")
        return []

    if isinstance(location_val, list):
        if len(location_val) == 8 and all(isinstance(v, (int, float)) for v in location_val):
            return [
                [float(location_val[0]), float(location_val[1])],
                [float(location_val[2]), float(location_val[3])],
                [float(location_val[4]), float(location_val[5])],
                [float(location_val[6]), float(location_val[7])],
            ]
        if len(location_val) == 4 and all(isinstance(v, (list, tuple)) and len(v) >= 2 for v in location_val):
            return [[float(p[0]), float(p[1])] for p in location_val]
        raise ValueError(f"invalid Location format in OCR output item: {item}")

    if isinstance(location_val, Mapping):
        # Some providers return dict form with fixed corner names.
        corner_names = [
            ("LeftTop", "leftTop", "left_top"),
            ("RightTop", "rightTop", "right_top"),
            ("RightBottom", "rightBottom", "right_bottom"),
            ("LeftBottom", "leftBottom", "left_bottom"),
        ]
        points: List[List[float]] = []
        for aliases in corner_names:
            point = None
            for alias in aliases:
                if alias in location_val:
                    point = location_val[alias]
                    break
            if not isinstance(point, Mapping):
                raise ValueError(f"invalid Location format in OCR output item: {item}")
            x = point.get("X", point.get("x"))
            y = point.get("Y", point.get("y"))
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise ValueError(f"invalid Location format in OCR output item: {item}")
            points.append([float(x), float(y)])
        return points

    raise ValueError(f"invalid Location format in OCR output item: {item}")


def _extract_text_value(item: Mapping[str, Any]) -> Optional[str]:
    for key in ("Content", "Text", "Value", "Word", "Words"):
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
        for v in node.values():
            if isinstance(v, list) and v and all(isinstance(i, Mapping) for i in v):
                if any(_extract_text_value(i) for i in v):
                    return [dict(i) for i in v]
    return []


def _parse_general_output(raw_output: Mapping[str, Any]) -> List[OCRTextBox]:
    items = _find_general_items(raw_output)
    if not items:
        return []

    texts: List[OCRTextBox] = []
    for item in items:
        text = _extract_text_value(item)
        if not text:
            continue
        quad = _parse_quad(item, required=True)
        confidence = _extract_confidence(item)
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

    result = resp.get("Result")
    if not isinstance(result, Mapping):
        raise ValueError(f"missing Result in ai_process response: {resp}")

    if "Output" not in result:
        raise ValueError(f"missing Result.Output in ai_process response: {resp}")

    raw_output = result["Output"]
    parsed_output = parse_result_output_value(raw_output)
    return parsed_output, request_id


def ocr_ai_process(
    service_id: Optional[str],
    data_type: str,
    object_key_or_url: str,
    scene: str = "general",
    model_id: str = "default",
    max_retries: int = 4,
) -> OCRResult:
    sid = _validate_service_id(service_id)
    dt = _validate_data_type(data_type)
    sc = _validate_scene(scene)
    obj_or_url = _validate_object_key_or_url(object_key_or_url, dt)
    retries = validate_max_retries(max_retries)
    mdl = (model_id or "default").strip() or "default"

    workflow_parameter = {
        "Input": {"ObjectKey": obj_or_url, "DataType": dt},
        "OCRParam": {"ModelId": mdl, "Scene": sc},
    }
    body = {
        "ServiceId": sid,
        "WorkflowTemplateId": "system_workflow_image_ocr",
        "WorkflowParameter": json.dumps(workflow_parameter, ensure_ascii=False),
    }

    service = new_imagex_service()
    begin = time.perf_counter()
    last_exc: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        resp: Any = None
        request_id: Optional[str] = None
        parsed_output: Optional[Dict[str, Any]] = None
        try:
            resp = service.ai_process(query={}, body=body)
            parsed_output, request_id = parse_ai_process_response(resp)
            if sc == "general":
                texts = _parse_general_output(parsed_output)
                fields = {}
            else:
                fields = _parse_license_output(parsed_output)
                texts = []

            total_ms = elapsed_ms(begin)
            logger.info(
                "ocr_ai_process success service_id=%s scene=%s data_type=%s elapsed_ms=%d retries=%d request_id=%s",
                sid,
                sc,
                dt,
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
                raw_resp=dict(resp) if isinstance(resp, Mapping) else {"raw": resp},
            )
        except ValueError as exc:
            total_ms = elapsed_ms(begin)
            request_id = request_id or (extract_request_id(resp) if isinstance(resp, Mapping) else None)
            summary = summarize_error(exc)
            logger.error(
                "ocr_ai_process invalid_response service_id=%s scene=%s data_type=%s elapsed_ms=%d retries=%d request_id=%s error=%s",
                sid,
                sc,
                dt,
                total_ms,
                attempt - 1,
                request_id,
                summary,
            )
            raise ValueError(
                f"ocr_ai_process invalid response(service_id={sid}, scene={sc}, data_type={dt}, elapsed_ms={total_ms}, "
                f"request_id={request_id}): {summary}; raw_output={parsed_output}"
            ) from exc
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable_error(exc)
            summary = summarize_error(exc)
            total_ms = elapsed_ms(begin)
            if (not retryable) or attempt >= retries:
                logger.error(
                    "ocr_ai_process failed service_id=%s scene=%s data_type=%s elapsed_ms=%d retries=%d request_id=%s error=%s",
                    sid,
                    sc,
                    dt,
                    total_ms,
                    attempt - 1,
                    None,
                    summary,
                )
                raise RuntimeError(
                    f"ocr_ai_process failed(service_id={sid}, scene={sc}, data_type={dt}, "
                    f"elapsed_ms={total_ms}, retries={attempt - 1}): {summary}"
                ) from exc

            sleep_s = backoff_seconds(attempt)
            logger.warning(
                "ocr_ai_process retry service_id=%s scene=%s data_type=%s attempt=%d/%d sleep=%.1fs error=%s",
                sid,
                sc,
                dt,
                attempt,
                retries,
                sleep_s,
                summary,
            )
            time.sleep(sleep_s)

    raise RuntimeError(f"ocr_ai_process failed after retries: {last_exc}")
