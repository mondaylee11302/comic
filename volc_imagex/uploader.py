from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import urlparse

from volc_imagex._utils import (
    backoff_seconds,
    elapsed_ms,
    extract_request_id,
    is_retryable_error,
    summarize_error,
    validate_max_retries,
)
from volc_imagex.client import new_imagex_service, resolve_service_id
from volc_imagex.types import UploadResult

logger = logging.getLogger(__name__)


_URI_KEYS = (
    "Uri",
    "URI",
    "ImageUri",
    "ResourceUri",
    "StoreUri",
    "StoreKey",
)

_URI_LIST_KEYS = (
    "UriList",
    "ImageUriList",
    "ImageURLList",
    "StoreUriList",
    "StoreKeyList",
    "StoreKeys",
    "Results",
)

_TOS_PREFIX_RE = re.compile(r"^tos-[^/]+-i-[^/]+/?")


def _validate_service_id(service_id: Optional[str]) -> str:
    return resolve_service_id(service_id)


def _iter_dict_nodes(obj: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(obj, Mapping):
        yield obj
        for val in obj.values():
            yield from _iter_dict_nodes(val)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dict_nodes(item)


def _extract_first_uri_from_resp(resp: Mapping[str, Any]) -> str:
    if not isinstance(resp, Mapping):
        raise ValueError(f"upload response must be mapping, got {type(resp).__name__}")

    roots = []
    if isinstance(resp.get("Result"), Mapping):
        roots.append(resp["Result"])
    roots.append(resp)

    for root in roots:
        for key in _URI_KEYS:
            val = root.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for key in _URI_LIST_KEYS:
            val = root.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
                    if isinstance(item, Mapping):
                        for sub_key in _URI_KEYS:
                            sub_val = item.get(sub_key)
                            if isinstance(sub_val, str) and sub_val.strip():
                                return sub_val.strip()

    for node in _iter_dict_nodes(resp):
        for key, val in node.items():
            lk = key.lower()
            if "uri" not in lk:
                continue
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
                    if isinstance(item, Mapping):
                        for sub_key in _URI_KEYS:
                            sub_val = item.get(sub_key)
                            if isinstance(sub_val, str) and sub_val.strip():
                                return sub_val.strip()
    raise ValueError(f"failed to parse resource uri from upload response: {resp}")


def _uri_to_object_key(uri: str) -> str:
    if not uri or not uri.strip():
        raise ValueError("resource uri is empty")

    normalized = uri.strip()
    if normalized.startswith(("http://", "https://")):
        parsed = urlparse(normalized)
        normalized = parsed.path or ""

    normalized = normalized.lstrip("/")
    normalized = normalized.split("?", 1)[0]
    normalized = normalized.split("#", 1)[0]
    if not normalized:
        raise ValueError(f"invalid uri: {uri}")

    object_key = _TOS_PREFIX_RE.sub("", normalized, count=1)
    object_key = object_key.lstrip("/")
    if not object_key:
        raise ValueError(f"failed to parse object_key from uri={uri}")
    return object_key


def _call_upload_image(
    imagex_service: Any,
    service_id: str,
    local_path: str,
    upload_host: Optional[str],
    overwrite: Optional[bool],
) -> Dict[str, Any]:
    fn = imagex_service.upload_image

    # Compat for volcengine SDK style: upload_image(params_dict, [file_path])
    params: Dict[str, Any] = {"ServiceId": service_id}
    if upload_host is not None:
        params["UploadHost"] = upload_host
    if overwrite is not None:
        params["Overwrite"] = bool(overwrite)
    try:
        resp = fn(params, [local_path])
        if isinstance(resp, Mapping):
            return dict(resp)
        return {"Result": resp}
    except TypeError:
        pass

    optional_kw_list = [
        {"upload_host": upload_host, "overwrite": overwrite},
        {"upload_host": upload_host},
        {"overwrite": overwrite},
        {},
    ]
    last_type_error: Optional[TypeError] = None
    for optional_kwargs in optional_kw_list:
        opt = {k: v for k, v in optional_kwargs.items() if v is not None}
        variants = (
            lambda: fn(service_id, local_path, **opt),
            lambda: fn(service_id=service_id, file_path=local_path, **opt),
            lambda: fn(service_id=service_id, local_path=local_path, **opt),
            lambda: fn(service_id=service_id, file=local_path, **opt),
        )
        for call in variants:
            try:
                return call()
            except TypeError as exc:
                last_type_error = exc
                continue
    if last_type_error is not None:
        raise last_type_error
    raise RuntimeError("upload_image call failed unexpectedly")


def _call_upload_image_data(
    imagex_service: Any,
    service_id: str,
    image_bytes: bytes,
    upload_host: Optional[str],
) -> Dict[str, Any]:
    fn = imagex_service.upload_image_data

    # Compat for volcengine SDK style: upload_image_data(params_dict, [bytes])
    params: Dict[str, Any] = {"ServiceId": service_id}
    if upload_host is not None:
        params["UploadHost"] = upload_host
    try:
        resp = fn(params, [image_bytes])
        if isinstance(resp, Mapping):
            return dict(resp)
        return {"Result": resp}
    except TypeError:
        pass
    except Exception as exc:
        # Some SDKs raise this when second arg is bytes not list[bytes].
        if "non-bytes" not in str(exc).lower():
            raise

    optional_kw_list = [
        {"upload_host": upload_host},
        {},
    ]
    last_type_error: Optional[TypeError] = None
    for optional_kwargs in optional_kw_list:
        opt = {k: v for k, v in optional_kwargs.items() if v is not None}
        variants = (
            lambda: fn(service_id, image_bytes, **opt),
            lambda: fn(service_id=service_id, data=image_bytes, **opt),
            lambda: fn(service_id=service_id, image_data=image_bytes, **opt),
            lambda: fn(service_id=service_id, binary_data=image_bytes, **opt),
        )
        for call in variants:
            try:
                return call()
            except TypeError as exc:
                last_type_error = exc
                continue
    if last_type_error is not None:
        raise last_type_error
    raise RuntimeError("upload_image_data call failed unexpectedly")


def upload_local_file(
    service_id: Optional[str],
    local_path: str,
    upload_host: Optional[str] = None,
    overwrite: Optional[bool] = None,
    max_retries: int = 4,
) -> UploadResult:
    sid = _validate_service_id(service_id)
    retries = validate_max_retries(max_retries)

    p = Path(local_path).expanduser()
    if not p.exists() or not p.is_file():
        raise ValueError(f"local file not found: {local_path}")

    file_size = p.stat().st_size
    service = new_imagex_service()
    begin = time.perf_counter()
    last_exc: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        raw_resp: Any = None
        try:
            raw_resp = _call_upload_image(
                imagex_service=service,
                service_id=sid,
                local_path=str(p),
                upload_host=upload_host,
                overwrite=overwrite,
            )
            request_id = extract_request_id(raw_resp)
            uri = _extract_first_uri_from_resp(raw_resp)
            object_key = _uri_to_object_key(uri)
            total_ms = elapsed_ms(begin)
            logger.info(
                "upload_local_file success service_id=%s file=%s size=%d elapsed_ms=%d retries=%d request_id=%s",
                sid,
                p.name,
                file_size,
                total_ms,
                attempt - 1,
                request_id,
            )
            return UploadResult(
                uri=uri,
                object_key=object_key,
                request_id=request_id,
                elapsed_ms=total_ms,
                retries=attempt - 1,
                raw_resp=dict(raw_resp) if isinstance(raw_resp, Mapping) else {"raw": raw_resp},
            )
        except ValueError as exc:
            total_ms = elapsed_ms(begin)
            request_id = extract_request_id(raw_resp) if isinstance(raw_resp, Mapping) else None
            summary = summarize_error(exc)
            logger.error(
                "upload_local_file invalid_response service_id=%s file=%s size=%d elapsed_ms=%d retries=%d request_id=%s error=%s",
                sid,
                p.name,
                file_size,
                total_ms,
                attempt - 1,
                request_id,
                summary,
            )
            raise ValueError(
                f"upload_local_file invalid response(service_id={sid}, file={p.name}, elapsed_ms={total_ms}, "
                f"request_id={request_id}): {summary}; raw_resp={raw_resp}"
            ) from exc
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable_error(exc)
            summary = summarize_error(exc)
            total_ms = elapsed_ms(begin)
            if (not retryable) or attempt >= retries:
                logger.error(
                    "upload_local_file failed service_id=%s file=%s size=%d elapsed_ms=%d retries=%d request_id=%s error=%s",
                    sid,
                    p.name,
                    file_size,
                    total_ms,
                    attempt - 1,
                    None,
                    summary,
                )
                raise RuntimeError(
                    f"upload_local_file failed(service_id={sid}, file={p.name}, elapsed_ms={total_ms}, "
                    f"retries={attempt - 1}): {summary}"
                ) from exc

            sleep_s = backoff_seconds(attempt)
            logger.warning(
                "upload_local_file retry service_id=%s file=%s size=%d attempt=%d/%d sleep=%.1fs error=%s",
                sid,
                p.name,
                file_size,
                attempt,
                retries,
                sleep_s,
                summary,
            )
            time.sleep(sleep_s)

    raise RuntimeError(f"upload_local_file failed after retries: {last_exc}")


def upload_image_data(
    service_id: Optional[str],
    image_bytes: bytes,
    upload_host: Optional[str] = None,
    max_retries: int = 4,
) -> UploadResult:
    sid = _validate_service_id(service_id)
    retries = validate_max_retries(max_retries)
    if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) == 0:
        raise ValueError("image_bytes must be non-empty bytes")

    payload_bytes = bytes(image_bytes)
    service = new_imagex_service()
    begin = time.perf_counter()
    last_exc: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        raw_resp: Any = None
        try:
            raw_resp = _call_upload_image_data(
                imagex_service=service,
                service_id=sid,
                image_bytes=payload_bytes,
                upload_host=upload_host,
            )
            request_id = extract_request_id(raw_resp)
            uri = _extract_first_uri_from_resp(raw_resp)
            object_key = _uri_to_object_key(uri)
            total_ms = elapsed_ms(begin)
            logger.info(
                "upload_image_data success service_id=%s size=%d elapsed_ms=%d retries=%d request_id=%s",
                sid,
                len(payload_bytes),
                total_ms,
                attempt - 1,
                request_id,
            )
            return UploadResult(
                uri=uri,
                object_key=object_key,
                request_id=request_id,
                elapsed_ms=total_ms,
                retries=attempt - 1,
                raw_resp=dict(raw_resp) if isinstance(raw_resp, Mapping) else {"raw": raw_resp},
            )
        except ValueError as exc:
            total_ms = elapsed_ms(begin)
            request_id = extract_request_id(raw_resp) if isinstance(raw_resp, Mapping) else None
            summary = summarize_error(exc)
            logger.error(
                "upload_image_data invalid_response service_id=%s size=%d elapsed_ms=%d retries=%d request_id=%s error=%s",
                sid,
                len(payload_bytes),
                total_ms,
                attempt - 1,
                request_id,
                summary,
            )
            raise ValueError(
                f"upload_image_data invalid response(service_id={sid}, size={len(payload_bytes)}, elapsed_ms={total_ms}, "
                f"request_id={request_id}): {summary}; raw_resp={raw_resp}"
            ) from exc
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable_error(exc)
            summary = summarize_error(exc)
            total_ms = elapsed_ms(begin)
            if (not retryable) or attempt >= retries:
                logger.error(
                    "upload_image_data failed service_id=%s size=%d elapsed_ms=%d retries=%d request_id=%s error=%s",
                    sid,
                    len(payload_bytes),
                    total_ms,
                    attempt - 1,
                    None,
                    summary,
                )
                raise RuntimeError(
                    f"upload_image_data failed(service_id={sid}, size={len(payload_bytes)}, elapsed_ms={total_ms}, "
                    f"retries={attempt - 1}): {summary}"
                ) from exc

            sleep_s = backoff_seconds(attempt)
            logger.warning(
                "upload_image_data retry service_id=%s size=%d attempt=%d/%d sleep=%.1fs error=%s",
                sid,
                len(payload_bytes),
                attempt,
                retries,
                sleep_s,
                summary,
            )
            time.sleep(sleep_s)

    raise RuntimeError(f"upload_image_data failed after retries: {last_exc}")
