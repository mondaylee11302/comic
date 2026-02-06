from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import numpy as np

from comic_splitter.stage2.types import PatchGraph, Region


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _color_sim(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    da = np.array(a, dtype=np.float32)
    db = np.array(b, dtype=np.float32)
    d = float(np.linalg.norm(da - db))
    return float(np.clip(1.0 - d / (255.0 * np.sqrt(3.0)), 0.0, 1.0))


@dataclass
class GrowConfig:
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


def grow_regions(graph: PatchGraph, cfg: GrowConfig) -> List[Region]:
    node_ids = sorted(graph.nodes.keys())
    if not node_ids:
        return []

    total_area = float(sum(graph.nodes[n].area for n in node_ids))
    min_area = max(1.0, cfg.min_region_ratio * total_area)
    max_area = max(1.0, cfg.max_region_ratio * total_area)

    # seed score: salient structure without over-prioritizing pure background
    ranked = sorted(
        node_ids,
        key=lambda n: (
            0.45 * graph.nodes[n].edge_mean
            + 0.45 * graph.nodes[n].non_white_ratio
            + 0.10 * min(graph.nodes[n].area / max(total_area, 1.0) * 10.0, 1.0)
        ),
        reverse=True,
    )
    seeds = ranked[: cfg.max_seeds_per_band]

    assigned: Dict[int, int] = {}
    regions: List[Set[int]] = []

    def region_embedding(region_nodes: Set[int]) -> np.ndarray:
        embs = [graph.nodes[n].embedding for n in region_nodes if graph.nodes[n].embedding is not None]
        if not embs:
            return np.zeros((32,), dtype=np.float32)
        v = np.mean(np.stack(embs, axis=0), axis=0)
        n = float(np.linalg.norm(v))
        return (v / n).astype(np.float32) if n > 1e-8 else v.astype(np.float32)

    for seed in seeds:
        if seed in assigned:
            continue
        reg = {seed}
        reg_area = float(graph.nodes[seed].area)
        emb = region_embedding(reg)

        frontier = set(graph.nodes[seed].neighbors)
        while frontier:
            cand_scores = []
            for c in frontier:
                if c in assigned or c in reg:
                    continue
                # best boundary edge from region to c
                bc = 1.0
                vis = 0.0
                for rn in reg:
                    if c in graph.nodes[rn].neighbors:
                        bc = min(bc, graph.boundary_costs.get(_pair_key(c, rn), 1.0))
                        vis = max(vis, _color_sim(graph.nodes[c].mean_bgr, graph.nodes[rn].mean_bgr))

                sem = _cos(graph.nodes[c].embedding, emb) if graph.nodes[c].embedding is not None else 0.0
                if bc > cfg.boundary_hard_thr:
                    continue
                if sem < cfg.sem_thr and vis < cfg.vis_thr:
                    continue

                score = 0.55 * sem + 0.30 * vis - 0.35 * bc
                cand_scores.append((score, c))

            if not cand_scores:
                break
            cand_scores.sort(reverse=True)
            picked = [c for _, c in cand_scores[: cfg.frontier_keep_topk]]
            changed = False
            for c in picked:
                if c in assigned or c in reg:
                    continue
                c_area = float(graph.nodes[c].area)
                if reg_area + c_area > max_area:
                    continue
                reg.add(c)
                reg_area += c_area
                changed = True
                emb = region_embedding(reg)
                frontier.update(graph.nodes[c].neighbors)
            if not changed:
                break
            frontier = {x for x in frontier if x not in reg and x not in assigned}

        # keep only meaningful regions from seeds
        if reg_area >= min_area:
            rid = len(regions)
            regions.append(reg)
            for n in reg:
                assigned[n] = rid

    # Any unassigned node: attach to nearest region by boundary, else new region.
    for n in node_ids:
        if n in assigned:
            continue
        best_r = None
        best_bc = 1.0
        for rid, reg in enumerate(regions):
            for rn in reg:
                if n in graph.nodes[rn].neighbors:
                    bc = graph.boundary_costs.get(_pair_key(n, rn), 1.0)
                    if bc < best_bc:
                        best_bc = bc
                        best_r = rid
        if best_r is not None and best_bc <= cfg.boundary_hard_thr:
            regions[best_r].add(n)
            assigned[n] = best_r
        else:
            rid = len(regions)
            regions.append({n})
            assigned[n] = rid

    # Region merge pass: semantically close + no strong boundary in between.
    changed = True
    while changed and len(regions) > 1:
        changed = False
        i = 0
        while i < len(regions):
            if not regions[i]:
                i += 1
                continue
            emb_i = region_embedding(regions[i])
            j = i + 1
            while j < len(regions):
                if not regions[j]:
                    j += 1
                    continue
                # adjacency + min boundary between two regions
                min_bc = 1.0
                adjacent = False
                for a in regions[i]:
                    for b in regions[j]:
                        if b in graph.nodes[a].neighbors:
                            adjacent = True
                            min_bc = min(min_bc, graph.boundary_costs.get(_pair_key(a, b), 1.0))
                if not adjacent:
                    j += 1
                    continue

                emb_j = region_embedding(regions[j])
                sem = _cos(emb_i, emb_j)
                if sem >= cfg.merge_sem_thr and min_bc <= cfg.merge_boundary_thr:
                    regions[i].update(regions[j])
                    regions[j].clear()
                    changed = True
                j += 1
            i += 1

        regions = [r for r in regions if r]

    # Absorb tiny fragments to reduce crack-like fragmentation.
    total_area = float(sum(graph.nodes[n].area for n in node_ids))
    min_region_area = max(1.0, total_area * cfg.min_region_area_ratio)
    changed = True
    while changed and len(regions) > 1:
        changed = False
        for i in range(len(regions)):
            if i >= len(regions):
                break
            if not regions[i]:
                continue
            reg_i = regions[i]
            area_i = float(sum(graph.nodes[n].area for n in reg_i))
            if len(reg_i) >= cfg.min_region_nodes and area_i >= min_region_area:
                continue

            best_j = None
            best_cost = 1.0
            for j in range(len(regions)):
                if i == j or not regions[j]:
                    continue
                # neighbor region with weakest boundary barrier
                min_bc = 1.0
                adjacent = False
                for a in reg_i:
                    for b in regions[j]:
                        if b in graph.nodes[a].neighbors:
                            adjacent = True
                            min_bc = min(min_bc, graph.boundary_costs.get(_pair_key(a, b), 1.0))
                if adjacent and min_bc < best_cost:
                    best_cost = min_bc
                    best_j = j

            if best_j is not None:
                regions[best_j].update(reg_i)
                regions[i].clear()
                changed = True
                break

        if changed:
            regions = [r for r in regions if r]

    out: List[Region] = []
    for rid, reg in enumerate(regions):
        out.append(
            Region(
                region_id=rid,
                band_index=graph.band_index,
                node_ids=sorted(reg),
                score=1.0,
                reason="graph_rag_region",
                meta={"node_count": len(reg)},
            )
        )
    return out
