from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import cv2

try:
    from volcenginesdkarkruntime import Ark
except Exception:  # pragma: no cover - optional runtime import safety
    Ark = None
try:
    from httpx import Timeout
except Exception:  # pragma: no cover
    Timeout = None

DEFAULT_DOUBAO_18_MM_MODEL = "doubao-seed-1-8-251228"


STORYBOARD_SYSTEM_PROMPT = """\
你是资深漫画导演与分镜编剧。你的任务是基于条漫单格画面和选中文字，生成一份可直接给导演/编剧使用的单格分镜脚本。

规则：
- 必须保留全部选中文字，不得删减。
- 用中文撰写，输出格式为结构化的纯文本（Markdown），不需要 JSON。
- 语言简洁可执行，避免冗长。
"""

STORYBOARD_USER_TEMPLATE = """\
请根据条漫分镜画面和以下文字，生成单格分镜脚本。
用户目标：{user_goal}

## 选中文字
{input_texts_plain}

## 输出格式
请按以下结构输出纯文本（Markdown），不要输出 JSON：

**【画面信息】**
- 景别 / 构图：
- 角色：
- 场景 / 氛围：
- 镜头运动：

**【对话 / 台词】**
（按角色绑定，格式：《角色特征》：文字内容）

**【导演指令】**
- 动作 / 表情：
- 情绪节奏：
- 声音：
"""


@dataclass
class ScriptAgentConfig:
    api_key: str = ""
    model_endpoint: str = DEFAULT_DOUBAO_18_MM_MODEL
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    temperature: float = 0.35
    max_tokens: int = 2400
    allow_local_fallback: bool = True
    enforce_doubao_18: bool = True
    request_timeout_sec: float = 120.0
    model_retries: int = 1
    retry_sleep_sec: float = 1.2
    heartbeat_interval_sec: int = 8


def _looks_like_doubao_18_model(model_name: str) -> bool:
    v = str(model_name or "").strip().lower()
    if not v:
        return False
    if v.startswith("ep-"):
        # Endpoint id created in Ark console; assume user bound it to doubao1.8.
        return True
    tokens = ("doubao", "seed", "1-8")
    if all(t in v for t in tokens):
        return True
    if "doubao" in v and "1.8" in v:
        return True
    return False


def read_panel_text_jsonl(path: str | Path) -> List[Dict]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"text file not found: {p}")
    out: List[Dict] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        row = json.loads(ln)
        if isinstance(row, Mapping):
            out.append(dict(row))
    return out


def select_text_rows(
    all_rows: Sequence[Mapping],
    selected_text_ids: Optional[Sequence[str]] = None,
    selected_texts: Optional[Sequence[str]] = None,
) -> List[Dict]:
    ids = {str(x).strip() for x in (selected_text_ids or []) if str(x).strip()}
    texts = [str(x).strip() for x in (selected_texts or []) if str(x).strip()]

    rows = [dict(r) for r in all_rows]
    if not ids and not texts:
        return rows

    selected: List[Dict] = []
    for r in rows:
        tid = str(r.get("text_id", "")).strip()
        txt = str(r.get("text", "")).strip()
        if ids and tid in ids:
            selected.append(r)
            continue
        if texts and any(t in txt for t in texts):
            selected.append(r)
    return selected


def encode_image_data_url(image_path: str | Path) -> str:
    p = Path(image_path).expanduser()
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"failed to read image: {p}")
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise ValueError(f"failed to encode image: {p}")
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _flatten_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, Mapping):
                txt = c.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts)
    return str(content)


def _extract_json_payload(text: str) -> Dict:
    raw = text.strip()
    if not raw:
        raise ValueError("empty response text")

    if raw.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.S)
        if m:
            raw = m.group(1).strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, Mapping):
            return dict(obj)
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(raw[start : end + 1])
        if isinstance(obj, Mapping):
            return dict(obj)
    raise ValueError("failed to parse JSON from model output")


def _build_messages(
    panel_image_path: str,
    selected_rows: Sequence[Mapping],
    user_goal: str,
) -> Tuple[List[Dict], List[Dict]]:
    # Build a simple numbered list of texts for the prompt
    lines = []
    for i, r in enumerate(selected_rows, start=1):
        txt = str(r.get("text", "")).strip()
        if txt:
            lines.append(f"{i}. {txt}")
    input_texts_plain = "\n".join(lines) if lines else "(\u65e0\u6587\u5b57)"

    user_text = STORYBOARD_USER_TEMPLATE.format(
        user_goal=user_goal or "\u4fdd\u7559\u539f\u6587\u8bed\u4e49\u5e76\u589e\u5f3a\u620f\u5267\u6027",
        input_texts_plain=input_texts_plain,
    )

    system_text = STORYBOARD_SYSTEM_PROMPT

    text_only_messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]

    data_url = encode_image_data_url(panel_image_path)
    multimodal_messages = [
        {"role": "system", "content": system_text},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    return multimodal_messages, text_only_messages


def _local_fallback_script(selected_rows: Sequence[Mapping], user_goal: str) -> Dict:
    """Generate a plain-text fallback script without calling LLM."""
    lines = [str(r.get("text", "")).strip() for r in selected_rows if str(r.get("text", "")).strip()]
    text_block = "\n".join(f"\u300a\u672a\u77e5\u89d2\u8272{i+1}\u300b\uff1a{t}" for i, t in enumerate(lines))
    md = (
        "**\u3010\u753b\u9762\u4fe1\u606f\u3011**\n"
        "- \u666f\u522b / \u6784\u56fe\uff1a\u4e2d\u666f\n"
        "- \u89d2\u8272\uff1a\u3010\u4e0d\u786e\u5b9a\u00b7\u65e0\u56fe\u50cf\u5206\u6790\u3011\n"
        "- \u573a\u666f / \u6c1b\u56f4\uff1a\u3010\u4e0d\u786e\u5b9a\u3011\n"
        "- \u955c\u5934\u8fd0\u52a8\uff1a\u3010\u4e0d\u786e\u5b9a\u3011\n\n"
        "**\u3010\u5bf9\u8bdd / \u53f0\u8bcd\u3011**\n"
        f"{text_block or '(\u65e0\u6587\u5b57)'}\n\n"
        "**\u3010\u5bfc\u6f14\u6307\u4ee4\u3011**\n"
        "- \u52a8\u4f5c / \u8868\u60c5\uff1a\u89d2\u8272\u4fdd\u6301\u53d9\u8ff0\u59ff\u6001\n"
        f"- \u60c5\u7eea\u8282\u594f\uff1a\u514b\u5236\u4e2d\u7684\u7d27\u5f20 | \u7528\u6237\u76ee\u6807\uff1a{user_goal or '\u65e0'}\n"
        "- \u58f0\u97f3\uff1a\u80cc\u666f\u622a\u65ad\u5c45"
    )
    return {
        "script_text": md,
        "meta": {"backend": "local_fallback"},
    }


def _run_with_heartbeat(
    label: str,
    fn,
    hook: Optional[Callable[[str], None]],
    interval_sec: int,
):
    if hook is None:
        return fn()
    stop_event = threading.Event()

    def _heartbeat() -> None:
        start = time.perf_counter()
        while not stop_event.wait(max(3, int(interval_sec))):
            elapsed = int(time.perf_counter() - start)
            hook(f"{label} running... {elapsed}s")

    th = threading.Thread(target=_heartbeat, daemon=True)
    t0 = time.perf_counter()
    hook(f"{label} start")
    th.start()
    try:
        return fn()
    finally:
        stop_event.set()
        th.join(timeout=0.2)
        hook(f"{label} done in {time.perf_counter() - t0:.2f}s")


def generate_panel_script(
    panel_image_path: str,
    selected_rows: Sequence[Mapping],
    user_goal: str,
    cfg: ScriptAgentConfig,
    verbose_hook: Optional[Callable[[str], None]] = None,
) -> Dict:
    if not selected_rows:
        raise ValueError("selected_rows is empty; please select at least one text row")

    model_name = str(cfg.model_endpoint or "").strip()
    if bool(cfg.enforce_doubao_18) and not _looks_like_doubao_18_model(model_name):
        raise ValueError(
            "script agent requires Doubao 1.8 multimodal model. "
            f"got model_endpoint={model_name!r}"
        )
    can_use_model = bool(cfg.api_key and cfg.model_endpoint and Ark is not None)
    attempt_errors: List[str] = []
    if can_use_model:
        if verbose_hook is not None:
            verbose_hook(
                f"model init: endpoint={model_name}, base_url={cfg.base_url}, "
                f"timeout={cfg.request_timeout_sec}s, retries={cfg.model_retries}"
            )
        multimodal_messages, text_only_messages = _build_messages(
            panel_image_path=panel_image_path,
            selected_rows=selected_rows,
            user_goal=user_goal,
        )
        client_kwargs = {"api_key": cfg.api_key, "base_url": cfg.base_url}
        if Timeout is not None:
            client_kwargs["timeout"] = Timeout(float(cfg.request_timeout_sec))
        client = Ark(**client_kwargs)
        try:
            # Prefer multimodal; fallback to text-only for non-vision endpoints.
            for mode, messages in (("multimodal", multimodal_messages), ("text_only", text_only_messages)):
                for attempt in range(1, max(1, int(cfg.model_retries)) + 1):
                    label = f"ark_chat mode={mode} attempt={attempt}/{max(1, int(cfg.model_retries))}"
                    try:
                        resp = _run_with_heartbeat(
                            label=label,
                            fn=lambda: client.chat.completions.create(
                                model=model_name,
                                messages=messages,
                                temperature=float(cfg.temperature),
                                max_tokens=int(cfg.max_tokens),
                            ),
                            hook=verbose_hook,
                            interval_sec=int(cfg.heartbeat_interval_sec),
                        )
                        content = _flatten_content(resp.choices[0].message.content)
                        # Return plain text directly — no JSON parsing needed
                        obj = {
                            "script_text": content.strip(),
                            "meta": {"backend": "ark_chat", "model_endpoint": model_name},
                        }
                        if verbose_hook is not None:
                            verbose_hook(f"{label} success")
                        return obj
                    except Exception as exc:
                        err = f"{mode}#{attempt}: {exc.__class__.__name__}: {exc}"
                        attempt_errors.append(err)
                        if verbose_hook is not None:
                            verbose_hook(f"{label} failed: {exc.__class__.__name__}: {exc}")
                        if attempt < max(1, int(cfg.model_retries)):
                            time.sleep(max(0.0, float(cfg.retry_sleep_sec)))
                # next mode after retries exhausted
        finally:
            try:
                client.close()
            except Exception:
                pass
    else:
        reason_parts = []
        if not cfg.api_key:
            reason_parts.append("missing_api_key")
        if not cfg.model_endpoint:
            reason_parts.append("missing_model_endpoint")
        if Ark is None:
            reason_parts.append("ark_sdk_unavailable")
        attempt_errors.append("init: " + ",".join(reason_parts))

    if not cfg.allow_local_fallback:
        detail = "; ".join(attempt_errors) if attempt_errors else "unknown_error"
        raise RuntimeError(f"script model unavailable and local fallback is disabled: {detail}")
    out = _local_fallback_script(selected_rows=selected_rows, user_goal=user_goal)
    out.setdefault("meta", {})
    out["meta"]["fallback_reason"] = "; ".join(attempt_errors) if attempt_errors else "unknown_error"
    return out
