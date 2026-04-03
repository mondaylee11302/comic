from __future__ import annotations

import os
from dataclasses import dataclass

from app.shared.config import load_runtime_dotenv


@dataclass
class VolcEnv:
    api_key: str
    model_endpoint: str
    base_url: str
    prompt_text: str


def load_volc_env() -> VolcEnv:
    load_runtime_dotenv()
    base_url = os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
    # Accept users pasting the full endpoint path from curl examples.
    if base_url.endswith("/embeddings/multimodal"):
        base_url = base_url[: -len("/embeddings/multimodal")]
    base_url = base_url.rstrip("/")

    return VolcEnv(
        api_key=os.getenv("VOLC_API_KEY", ""),
        model_endpoint=os.getenv("VOLC_MODEL_ENDPOINT", ""),
        base_url=base_url,
        prompt_text=os.getenv("VOLC_MM_PROMPT_TEXT", "图像内容语义表示"),
    )
