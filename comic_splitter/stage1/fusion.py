from __future__ import annotations

from typing import List, Tuple, Dict
import numpy as np

from comic_splitter.common.types import CutCandidate, Band

_PRIORITY = {"black_bar": 3, "gutter": 2, "hard_line": 1}


def _merge_candidates(cands: List[CutCandidate], merge_dist: int = 25) -> List[CutCandidate]:
    if not cands:
        return []
    cands = sorted(cands, key=lambda c: c.y)
    merged: List[CutCandidate] = []
    cur = cands[0]
    for nxt in cands[1:]:
        if abs(nxt.y - cur.y) <= merge_dist:
            # merge spans
            y1 = min(cur.span[0], nxt.span[0])
            y2 = max(cur.span[1], nxt.span[1])
            cur.span = (y1, y2)
            # keep strongest strength
            cur.strength = max(cur.strength, nxt.strength)
            # keep higher priority type
            if _PRIORITY.get(nxt.type, 0) > _PRIORITY.get(cur.type, 0):
                cur.type = nxt.type
            # merge meta lightly
            cur.meta = {**cur.meta, **{f"merged_{nxt.type}": True}}
        else:
            merged.append(cur)
            cur = nxt
    merged.append(cur)
    return merged


def _band_score_reason(
    band: Tuple[int, int],
    candidates: List[CutCandidate],
) -> Tuple[float, str, dict]:
    y1, y2 = band
    if not candidates:
        return 0.2, "fallback_chunk", {}

    # nearest cut above and below
    above = [c for c in candidates if c.y <= y1]
    below = [c for c in candidates if c.y >= y2]
    near = []
    if above:
        near.append(max(above, key=lambda c: c.y))
    if below:
        near.append(min(below, key=lambda c: c.y))
    if not near:
        # cuts inside band
        inside = [c for c in candidates if y1 <= c.y <= y2]
        near = inside

    if not near:
        return 0.3, "structure", {}

    score = float(np.clip(np.mean([c.strength for c in near]), 0, 1))
    # dominant type by priority
    dom = max(near, key=lambda c: _PRIORITY.get(c.type, 0))
    meta = {"cut_types": [c.type for c in near], "cut_ys": [c.y for c in near]}
    return score, dom.type, meta


def _merge_spans(
    spans: List[Dict],
    merge_dist: int,
) -> List[Dict]:
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: s["y1"])
    merged: List[Dict] = []
    cur = dict(spans[0])
    for nxt in spans[1:]:
        if nxt["y1"] <= cur["y2"] + merge_dist:
            cur["y2"] = max(cur["y2"], nxt["y2"])
            cur["strength"] = max(cur.get("strength", 0.0), nxt.get("strength", 0.0))
            cur_edge = cur.get("edge")
            nxt_edge = nxt.get("edge")
            if cur_edge is None:
                cur["edge"] = nxt_edge
            elif nxt_edge is not None:
                cur["edge"] = max(cur_edge, nxt_edge)
        else:
            merged.append(cur)
            cur = dict(nxt)
    merged.append(cur)
    return merged


def _extract_black_bar_spans(
    candidates: List[CutCandidate],
    min_h: int,
    merge_dist: int,
) -> List[Dict]:
    spans: List[Dict] = []
    for c in candidates:
        if c.type != "black_bar":
            continue
        y1, y2 = int(c.span[0]), int(c.span[1])
        if (y2 - y1) < min_h:
            continue
        spans.append(
            {
                "y1": y1,
                "y2": y2,
                "strength": float(c.strength),
                "edge": c.meta.get("e"),
            }
        )
    return _merge_spans(spans, merge_dist=merge_dist)


def _bands_for_interval(
    y1: int,
    y2: int,
    candidates: List[CutCandidate],
    min_band_h: int,
) -> List[Tuple[int, int]]:
    if y2 - y1 <= 0:
        return []
    cuts = [c.y for c in candidates if y1 < c.y < y2]
    cuts = sorted(set(cuts))
    cuts = [y1] + cuts + [y2]

    raw: List[Tuple[int, int]] = []
    for i in range(len(cuts) - 1):
        a, b = cuts[i], cuts[i + 1]
        if b - a <= 0:
            continue
        raw.append((a, b))

    if not raw:
        return []

    merged: List[Tuple[int, int]] = []
    i = 0
    while i < len(raw):
        a, b = raw[i]
        if (b - a) >= min_band_h or len(raw) == 1:
            merged.append((a, b))
            i += 1
            continue
        if i == 0:
            na, nb = raw[i + 1]
            raw[i + 1] = (a, nb)
        elif i == len(raw) - 1:
            pa, pb = merged[-1]
            merged[-1] = (pa, b)
        else:
            left_h = merged[-1][1] - merged[-1][0]
            right_h = raw[i + 1][1] - raw[i + 1][0]
            if right_h >= left_h:
                na, nb = raw[i + 1]
                raw[i + 1] = (a, nb)
            else:
                pa, pb = merged[-1]
                merged[-1] = (pa, b)
        i += 1
    return merged


def build_bands(
    H: int,
    candidates: List[CutCandidate],
    min_band_h: int = 180,
    fallback_chunk_h: int = 2600,
    black_bar_band_min_h: int = 24,
    black_bar_band_base_score: float = 0.6,
    black_bar_edge_penalty_thr: float = 0.02,
    black_bar_edge_penalty_score: float = 0.45,
    black_bar_merge_dist: int = 8,
) -> List[Band]:
    if not candidates:
        bands = []
        y = 0
        while y < H:
            y2 = min(H, y + fallback_chunk_h)
            bands.append(Band(y1=y, y2=y2, score=0.2, reason="fallback_chunk"))
            y = y2
        return bands

    bar_spans = _extract_black_bar_spans(
        candidates,
        min_h=black_bar_band_min_h,
        merge_dist=black_bar_merge_dist,
    )

    edge_cands: List[CutCandidate] = []
    for b in bar_spans:
        for yy in (b["y1"], b["y2"]):
            edge_cands.append(
                CutCandidate(
                    y=int(yy),
                    strength=max(0.8, float(b.get("strength", 0.0))),
                    type="black_bar",
                    span=(int(b["y1"]), int(b["y2"])),
                    meta={"edge_cut": True},
                )
            )

    all_cands = candidates + edge_cands

    bands: List[Band] = []
    cur_y = 0
    for b in bar_spans:
        y1 = int(np.clip(b["y1"], 0, H))
        y2 = int(np.clip(b["y2"], 0, H))
        if y1 > cur_y:
            merged = _bands_for_interval(cur_y, y1, all_cands, min_band_h)
            for (a, c) in merged:
                score, reason, meta = _band_score_reason((a, c), all_cands)
                bands.append(Band(y1=a, y2=c, score=score, reason=reason, meta=meta))
        if y2 > y1:
            score = float(np.clip(black_bar_band_base_score + 0.4 * b.get("strength", 0.0), 0, 1))
            edge = b.get("edge")
            if edge is not None and float(edge) >= black_bar_edge_penalty_thr:
                score = min(score, black_bar_edge_penalty_score)
            bands.append(
                Band(
                    y1=y1,
                    y2=y2,
                    score=score,
                    reason="black_bar_band",
                    meta={"edge": edge, "strength": b.get("strength", 0.0)},
                )
            )
        cur_y = max(cur_y, y2)

    if cur_y < H:
        merged = _bands_for_interval(cur_y, H, all_cands, min_band_h)
        for (a, c) in merged:
            score, reason, meta = _band_score_reason((a, c), all_cands)
            bands.append(Band(y1=a, y2=c, score=score, reason=reason, meta=meta))

    return bands
