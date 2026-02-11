from __future__ import annotations

from typing import Optional

from volc_imagex.ocr import ocr_ai_process
from volc_imagex.types import OCRResult


def ocr_local_file(service_id: Optional[str], local_path: str, scene: str = "general") -> OCRResult:
    return ocr_ai_process(
        service_id=service_id,
        data_type="file",
        object_key_or_url=local_path,
        scene=scene,
    )
