from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UploadResult:
    uri: str
    object_key: str
    request_id: Optional[str] = None
    elapsed_ms: int = 0
    retries: int = 0
    raw_resp: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OCRTextBox:
    text: str
    quad: List[List[float]]
    confidence: Optional[float] = None


@dataclass
class OCRResult:
    scene: str
    texts: List[OCRTextBox] = field(default_factory=list)
    fields: Dict[str, OCRTextBox] = field(default_factory=dict)
    raw_output: Dict[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None
    elapsed_ms: int = 0
    retries: int = 0
    raw_resp: Dict[str, Any] = field(default_factory=dict)
