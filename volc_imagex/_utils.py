from __future__ import annotations

import ast
import os
import time
from typing import Any, Mapping, Optional

try:  # pragma: no cover - optional import
    from requests import exceptions as requests_exc
except Exception:  # pragma: no cover - optional import
    requests_exc = None


_RETRYABLE_TEXTS = (
    "bad gateway",
    "gateway timeout",
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
    "service unavailable",
    "201007",
    "502",
    "503",
    "504",
    "5xx",
)

_NON_RETRYABLE_TEXTS = (
    "invalid parameter",
    "missing required",
    "bad request",
    "unauthorized",
    "forbidden",
    "not found",
    "invalid scene",
    "invalid datatype",
)


def validate_max_retries(max_retries: int) -> int:
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")
    return max_retries


def backoff_seconds(attempt_no: int) -> float:
    return min(0.5 * (2 ** (attempt_no - 1)), 4.0)


def elapsed_ms(start_ts: float) -> int:
    return int((time.perf_counter() - start_ts) * 1000)


def extract_request_id(resp: Any) -> Optional[str]:
    if not isinstance(resp, Mapping):
        return None
    paths = [
        ("ResponseMetadata", "RequestId"),
        ("ResponseMetadata", "RequestID"),
        ("Metadata", "RequestId"),
        ("RequestId",),
        ("RequestID",),
        ("request_id",),
    ]
    for path in paths:
        cur: Any = resp
        ok = True
        for key in path:
            if not isinstance(cur, Mapping) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and cur:
            return str(cur)
    return None


def extract_status_code(exc: BaseException) -> Optional[int]:
    for key in ("status_code", "status", "http_status"):
        val = getattr(exc, key, None)
        if isinstance(val, int):
            return val
    response = getattr(exc, "response", None)
    if response is not None:
        val = getattr(response, "status_code", None)
        if isinstance(val, int):
            return val
    return None


def is_retryable_error(exc: BaseException) -> bool:
    if isinstance(exc, ValueError):
        return False

    status_code = extract_status_code(exc)
    if status_code is not None:
        if 500 <= status_code <= 599:
            return True
        if 400 <= status_code <= 499:
            return False

    retryable_types = [TimeoutError, ConnectionError]
    if requests_exc is not None:
        retryable_types.extend(
            [
                requests_exc.Timeout,
                requests_exc.ConnectionError,
                requests_exc.ReadTimeout,
                requests_exc.ConnectTimeout,
            ]
        )

    if isinstance(exc, tuple(retryable_types)):
        return True

    err_text = str(exc).lower()
    if any(token in err_text for token in _RETRYABLE_TEXTS):
        return True
    if any(token in err_text for token in _NON_RETRYABLE_TEXTS):
        return False
    return False


def summarize_error(exc: BaseException, max_len: int = 240) -> str:
    raw = f"{exc.__class__.__name__}: {exc}".replace("\n", " ").strip()

    # Decode payloads rendered as bytes literals, e.g. "Exception: b'{...}'".
    text = raw
    marker = ": b'"
    marker2 = ': b"'
    idx = raw.find(marker)
    if idx < 0:
        idx = raw.find(marker2)
    if idx >= 0:
        prefix = raw[: idx + 2]
        lit = raw[idx + 2 :].strip()
        try:
            decoded = ast.literal_eval(lit)
            if isinstance(decoded, (bytes, bytearray)):
                text = f"{prefix}{decoded.decode('utf-8', errors='replace')}"
        except Exception:
            text = raw

    env_len = os.getenv("VOLC_ERROR_SUMMARY_MAX_LEN", "").strip()
    if env_len:
        try:
            parsed = int(env_len)
            if parsed <= 0:
                return text
            max_len = parsed
        except Exception:
            pass

    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
