from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from comic_splitter.common.types import Band
from comic_splitter.stage2.embedding import Stage2Embedder
from comic_splitter.stage2.grow import GrowConfig, grow_regions
from comic_splitter.stage2.patch_graph import build_patch_graph
from comic_splitter.stage2.types import PatchGraph


@dataclass
class Stage2Config:
    # patch graph / slic
    target_patch_area: int = 60_000
    min_nodes: int = 20
    max_nodes: int = 120
    slic_compactness: float = 12.0
    slic_sigma: float = 1.0

    # growth
    max_seeds_per_band: int = 8
    sem_thr: float = 0.50
    vis_thr: float = 0.58
    boundary_hard_thr: float = 0.46
    frontier_keep_topk: int = 24
    min_region_ratio: float = 0.03
    max_region_ratio: float = 0.72
    merge_sem_thr: float = 0.78
    merge_boundary_thr: float = 0.30
    min_region_nodes: int = 3
    min_region_area_ratio: float = 0.015

    # embedding backend (volc multimodal)
    volc_api_key: str = ""
    volc_model_endpoint: str = ""
    volc_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volc_prompt_text: str = "图像内容语义表示"
    volc_timeout_sec: float = 45.0
    allow_local_fallback: bool = True
    embedding_cache_dir: str = ".cache/stage2_embeddings"
    verbose: bool = True


class GraphRAGSegmenter:
    def __init__(self, cfg: Stage2Config):
        self.cfg = cfg
        self.embedder = Stage2Embedder(
            api_key=cfg.volc_api_key,
            model_endpoint=cfg.volc_model_endpoint,
            base_url=cfg.volc_base_url,
            cache_dir=cfg.embedding_cache_dir,
            allow_local_fallback=cfg.allow_local_fallback,
            prompt_text=cfg.volc_prompt_text,
            timeout_sec=cfg.volc_timeout_sec,
        )

    def close(self) -> None:
        self.embedder.close()

    def _embed_graph_nodes(self, band_bgr: np.ndarray, graph: PatchGraph, band_index: int) -> None:
        h, w = band_bgr.shape[:2]
        node_items = list(graph.nodes.items())
        total = len(node_items)
        for idx, (nid, node) in enumerate(node_items, start=1):
            x1, y1, x2, y2 = node.bbox
            pad = 2
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(w, x2 + pad)
            y2 = min(h, y2 + pad)
            crop = band_bgr[y1:y2, x1:x2]
            node.embedding = self.embedder.embed_patch(crop)
            if self.cfg.verbose and (idx == 1 or idx % 10 == 0 or idx == total):
                print(f"[stage2] band {band_index}: embedding {idx}/{total}", flush=True)

    def segment(self, rgb: np.ndarray, bands: List[Band]) -> Dict:
        all_regions = []
        graphs = {}
        for bi, band in enumerate(bands):
            y1, y2 = int(band.y1), int(band.y2)
            if y2 <= y1:
                continue
            band_bgr = rgb[y1:y2]
            graph = build_patch_graph(
                band_bgr,
                band_index=bi,
                target_patch_area=self.cfg.target_patch_area,
                min_nodes=self.cfg.min_nodes,
                max_nodes=self.cfg.max_nodes,
                slic_compactness=self.cfg.slic_compactness,
                slic_sigma=self.cfg.slic_sigma,
            )
            if self.cfg.verbose:
                print(f"[stage2] band {bi}: nodes={len(graph.nodes)}", flush=True)
            self._embed_graph_nodes(band_bgr, graph, band_index=bi)
            grow_cfg = GrowConfig(
                max_seeds_per_band=self.cfg.max_seeds_per_band,
                sem_thr=self.cfg.sem_thr,
                vis_thr=self.cfg.vis_thr,
                boundary_hard_thr=self.cfg.boundary_hard_thr,
                frontier_keep_topk=self.cfg.frontier_keep_topk,
                min_region_ratio=self.cfg.min_region_ratio,
                max_region_ratio=self.cfg.max_region_ratio,
                merge_sem_thr=self.cfg.merge_sem_thr,
                merge_boundary_thr=self.cfg.merge_boundary_thr,
                min_region_nodes=self.cfg.min_region_nodes,
                min_region_area_ratio=self.cfg.min_region_area_ratio,
            )
            regions = grow_regions(graph, grow_cfg)
            if self.cfg.verbose:
                print(f"[stage2] band {bi}: regions={len(regions)}", flush=True)
            graphs[bi] = graph

            for r in regions:
                xs = []
                ys = []
                total_area = 0
                for nid in r.node_ids:
                    n = graph.nodes[nid]
                    x1n, y1n, x2n, y2n = n.bbox
                    xs.extend([x1n, x2n])
                    ys.extend([y1n, y2n])
                    total_area += int(n.area)
                if not xs:
                    continue
                gx1, gx2 = int(min(xs)), int(max(xs))
                gy1, gy2 = int(min(ys)) + y1, int(max(ys)) + y1
                band_area = max(1, (y2 - y1) * band_bgr.shape[1])
                area_ratio = float(total_area / band_area)
                r.score = float(np.clip(0.65 * area_ratio + 0.35 * min(len(r.node_ids) / 8.0, 1.0), 0.0, 1.0))
                r.meta = {
                    **r.meta,
                    "band_y1": y1,
                    "band_y2": y2,
                    "area_ratio": area_ratio,
                    "bbox": [gx1, gy1, gx2, gy2],
                }
                all_regions.append(r)

        out_regions = []
        for r in all_regions:
            out_regions.append(
                {
                    "band_index": r.band_index,
                    "region_id": r.region_id,
                    "node_ids": r.node_ids,
                    "score": r.score,
                    "reason": r.reason,
                    "bbox": r.meta.get("bbox", [0, 0, 0, 0]),
                    "meta": r.meta,
                }
            )

        return {
            "regions": out_regions,
            "meta": {
                "embedding_backend": self.embedder.backend,
                "volc_model_endpoint": self.cfg.volc_model_endpoint,
                "band_count": len(bands),
            },
            "graphs": graphs,
        }
