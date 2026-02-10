from __future__ import annotations

from typing import Optional

from volc_imagex.ocr import ocr_ai_process
from volc_imagex.types import OCRResult
from volc_imagex.uploader import upload_local_file


def ocr_local_file(service_id: Optional[str], local_path: str, scene: str = "general") -> OCRResult:
    upload_result = upload_local_file(service_id=service_id, local_path=local_path)
    return ocr_ai_process(
        service_id=service_id,
        data_type="uri",
        object_key_or_url=upload_result.object_key,
        scene=scene,
    )
