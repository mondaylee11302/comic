from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from httpx import Timeout

try:
    from volcenginesdkarkruntime import Ark
except Exception:  # pragma: no cover - optional runtime import safety
    Ark = None


class EmbeddingCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[np.ndarray]:
        p = self._path(key)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return np.array(data["embedding"], dtype=np.float32)

    def set(self, key: str, embedding: np.ndarray) -> None:
        p = self._path(key)
        payload = {"embedding": embedding.astype(float).tolist()}
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _image_hash(image_bgr: np.ndarray, salt: str) -> str:
    h = hashlib.sha1()
    h.update(salt.encode("utf-8"))
    h.update(str(image_bgr.shape).encode("utf-8"))
    h.update(image_bgr.tobytes())
    return h.hexdigest()


def _crop_to_data_url(image_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise ValueError("failed to encode patch as jpeg")
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _encode_jpeg_base64(image_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise ValueError("failed to encode patch as jpeg")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _resize_for_api(image_bgr: np.ndarray, max_edge: int = 768) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    m = max(h, w)
    if m <= max_edge:
        return image_bgr
    s = max_edge / float(m)
    nw = max(1, int(round(w * s)))
    nh = max(1, int(round(h * s)))
    return cv2.resize(image_bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-8:
        return v.astype(np.float32)
    return (v / n).astype(np.float32)


def local_patch_embedding(image_bgr: np.ndarray) -> np.ndarray:
    # 32-D deterministic fallback embedding: color hist + edge hist
    img = image_bgr
    if img.size == 0:
        return np.zeros((32,), dtype=np.float32)

    chans = cv2.split(img)
    feats = []
    for ch in chans:
        h = cv2.calcHist([ch], [0], None, [8], [0, 256]).reshape(-1)
        h = h / max(float(np.sum(h)), 1.0)
        feats.append(h)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(grad_x * grad_x + grad_y * grad_y)
    mag = np.clip(mag, 0, 255).astype(np.uint8)
    edge_hist = cv2.calcHist([mag], [0], None, [8], [0, 256]).reshape(-1)
    edge_hist = edge_hist / max(float(np.sum(edge_hist)), 1.0)
    feats.append(edge_hist)

    v = np.concatenate(feats, axis=0).astype(np.float32)
    return _normalize(v)


class Stage2Embedder:
    def __init__(
        self,
        api_key: str,
        model_endpoint: str,
        cache_dir: str,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        allow_local_fallback: bool = True,
        prompt_text: str = "图像内容语义表示",
        timeout_sec: float = 45.0,
    ):
        self.api_key = api_key
        self.model_endpoint = model_endpoint
        self.base_url = base_url
        self.allow_local_fallback = allow_local_fallback
        self.prompt_text = prompt_text
        self.timeout_sec = timeout_sec
        self.cache = EmbeddingCache(cache_dir)

        self._client = None
        self.backend = "local"
        if api_key and model_endpoint and Ark is not None:
            self._client = Ark(
                api_key=api_key,
                base_url=base_url,
                timeout=Timeout(timeout_sec),
            )
            self.backend = "volc_mm"

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    def embed_patch(self, image_bgr: np.ndarray) -> np.ndarray:
        salt = f"{self.backend}:{self.model_endpoint}"
        key = _image_hash(image_bgr, salt=salt)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        if self._client is None:
            if not self.allow_local_fallback:
                raise RuntimeError("volc embedding unavailable: missing api_key/model_endpoint")
            emb = local_patch_embedding(image_bgr)
            self.cache.set(key, emb)
            return emb

        prepared = _resize_for_api(image_bgr, max_edge=768)
        b64 = _encode_jpeg_base64(prepared)

        # Try formats observed in different Ark deployments.
        payloads = []
        prompt = (self.prompt_text or "").strip()
        if prompt:
            payloads.append(
                [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]
            )
        payloads.extend(
            [
                [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}],
                [{"type": "image_url", "image_url": {"url": b64}}],
                [{"type": "image_base64", "image_base64": b64}],
            ]
        )

        last_err = None
        for inp in payloads:
            for attempt in range(3):
                try:
                    resp = self._client.multimodal_embeddings.create(
                        input=inp,
                        model=self.model_endpoint,
                    )
                    emb = _normalize(np.array(resp.data.embedding, dtype=np.float32))
                    self.cache.set(key, emb)
                    return emb
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        time.sleep(0.4 * (attempt + 1))

        if not self.allow_local_fallback:
            msg = (
                "volc multimodal embedding failed after retries. "
                "Please verify VOLC_MODEL_ENDPOINT is a multimodal-embedding endpoint "
                "and supports image input. "
                f"last_error={last_err}"
            )
            raise RuntimeError(msg) from last_err

        emb = local_patch_embedding(image_bgr)
        self.cache.set(key, emb)
        return emb
