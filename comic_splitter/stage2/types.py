from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

import numpy as np


@dataclass
class PatchNode:
    node_id: int
    label: int
    band_index: int
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2 in band coords
    area: int
    center: Tuple[float, float]  # x, y in band coords
    mean_bgr: Tuple[float, float, float]
    edge_mean: float
    non_white_ratio: float
    neighbors: Set[int] = field(default_factory=set)
    embedding: np.ndarray | None = None


@dataclass
class PatchGraph:
    band_index: int
    labels: np.ndarray  # HxW int32
    nodes: Dict[int, PatchNode]
    boundary_costs: Dict[Tuple[int, int], float]


@dataclass
class Region:
    region_id: int
    band_index: int
    node_ids: List[int]
    score: float
    reason: str
    meta: Dict = field(default_factory=dict)
