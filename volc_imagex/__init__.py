from volc_imagex.client import new_imagex_service
from volc_imagex.ocr import ocr_ai_process
from volc_imagex.pipeline import ocr_local_file
from volc_imagex.types import OCRResult, OCRTextBox, UploadResult
from volc_imagex.uploader import upload_image_data, upload_local_file

__all__ = [
    "new_imagex_service",
    "upload_local_file",
    "upload_image_data",
    "ocr_ai_process",
    "ocr_local_file",
    "UploadResult",
    "OCRTextBox",
    "OCRResult",
]
