from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse


def _first_env(*names: str) -> str:
    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            return val
    return ""


def _read_keys_from_volc_config(config_path: Optional[str] = None) -> Tuple[str, str]:
    path = Path(config_path or "~/.volc/config").expanduser()
    if not path.exists():
        return "", ""

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return "", ""

    section_names = ["default", "volc", "credentials"]
    key_names_ak = ["access_key", "accesskey", "ak", "VOLC_ACCESSKEY", "VOLC_ACCESS_KEY"]
    key_names_sk = ["secret_key", "secretkey", "sk", "VOLC_SECRETKEY", "VOLC_SECRET_KEY"]

    for section in section_names:
        if section not in parser:
            continue
        sec = parser[section]
        ak = next((sec.get(k, "") for k in key_names_ak if sec.get(k, "")), "")
        sk = next((sec.get(k, "") for k in key_names_sk if sec.get(k, "")), "")
        if ak and sk:
            return ak.strip(), sk.strip()
    return "", ""


def _normalize_host_and_scheme(host_or_url: str) -> Tuple[str, str]:
    raw = (host_or_url or "").strip()
    if not raw:
        return "", ""
    if "://" not in raw:
        return raw.strip("/"), ""

    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path or "").strip().strip("/")
    if "/" in host:
        host = host.split("/", 1)[0]
    scheme = (parsed.scheme or "").strip().lower()
    return host, scheme


def new_imagex_service(
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    allow_config_fallback: bool = True,
    region: Optional[str] = None,
    api_host: Optional[str] = None,
    api_scheme: Optional[str] = None,
):
    """
    Build and return volcengine ImagexService.
    Priority:
    1) explicit args
    2) environment: VOLC_ACCESSKEY or VOLC_ACCESS_KEY,
       VOLC_SECRETKEY or VOLC_SECRET_KEY
    3) ~/.volc/config (optional)
    """
    try:
        from volcengine.imagex.v2.imagex_service import ImagexService
    except Exception as exc:
        raise RuntimeError(
            "volcengine SDK not available. Install `volcengine-python-sdk` first."
        ) from exc

    ak = (access_key or _first_env("VOLC_ACCESSKEY", "VOLC_ACCESS_KEY")).strip()
    sk = (secret_key or _first_env("VOLC_SECRETKEY", "VOLC_SECRET_KEY")).strip()

    if (not ak or not sk) and allow_config_fallback:
        cfg_ak, cfg_sk = _read_keys_from_volc_config()
        ak = ak or cfg_ak
        sk = sk or cfg_sk

    if not ak or not sk:
        raise ValueError(
            "missing access key/secret key. Please set VOLC_ACCESSKEY (or VOLC_ACCESS_KEY) "
            "and VOLC_SECRETKEY (or VOLC_SECRET_KEY)."
        )

    imagex_region = (region or _first_env("VOLC_IMAGEX_REGION", "VOLC_OCR_REGION")).strip()
    service = ImagexService(region=imagex_region) if imagex_region else ImagexService()
    service.set_ak(ak)
    service.set_sk(sk)

    raw_host = (api_host or _first_env("VOLC_IMAGEX_API_HOST", "VOLC_OCR_API_HOST", "VOLC_IMAGEX_HOST", "VOLC_OCR_HOST")).strip()
    host, scheme_from_host = _normalize_host_and_scheme(raw_host)
    if host:
        service.set_host(host)

    scheme = (api_scheme or _first_env("VOLC_IMAGEX_API_SCHEME", "VOLC_OCR_API_SCHEME")).strip().lower()
    if not scheme and scheme_from_host:
        scheme = scheme_from_host
    if scheme in {"http", "https"}:
        service.set_scheme(scheme)
    return service


def resolve_service_id(service_id: Optional[str]) -> str:
    sid = (service_id or "").strip()
    if sid:
        return sid

    sid = os.getenv("VOLC_OCR_SERVICE_ID", "").strip()
    if sid:
        return sid

    sid = os.getenv("VOLC_IMAGEX_SERVICE_ID", "").strip()
    if sid:
        return sid

    raise ValueError(
        "service_id is required. pass service_id explicitly or set VOLC_OCR_SERVICE_ID."
    )
