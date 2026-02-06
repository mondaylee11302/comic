from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class CutCandidate:
    y: int
    strength: float
    type: str  # 'gutter' | 'black_bar' | 'hard_line'
    span: Tuple[int, int]  # (y1, y2)
    meta: Dict = field(default_factory=dict)


@dataclass
class Band:
    y1: int
    y2: int
    score: float
    reason: str  # dominant cut type or fallback
    meta: Dict = field(default_factory=dict)
