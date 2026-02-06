from __future__ import annotations

from typing import List, Tuple
import numpy as np
import cv2

from comic_splitter.common.types import CutCandidate
from comic_splitter.stage1.features import RowFeatures


def _detect_lines_lsd(gray: np.ndarray) -> List[Tuple[int, int, int, int]]:
    try:
        lsd = cv2.createLineSegmentDetector(0)
    except Exception:
        return []
    lines, _, _, _ = lsd.detect(gray)
    if lines is None:
        return []
    out: List[Tuple[int, int, int, int]] = []
    for ln in lines:
        x1, y1, x2, y2 = ln[0]
        out.append((int(x1), int(y1), int(x2), int(y2)))
    return out


def _detect_lines_hough(edges: np.ndarray) -> List[Tuple[int, int, int, int]]:
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=80,
        minLineLength=80,
        maxLineGap=10,
    )
    if lines is None:
        return []
    out: List[Tuple[int, int, int, int]] = []
    for ln in lines:
        x1, y1, x2, y2 = ln[0]
        out.append((int(x1), int(y1), int(x2), int(y2)))
    return out


def detect_hard_lines(
    feats: RowFeatures,
    min_len_ratio: float = 0.35,
    density_thr: float = 0.12,
    min_run_h: int = 10,
    angle_bins: int = 18,
    dom_thr: float = 0.45,
    y_bin_h: int = 24,
    conc_thr: float = 0.22,
    long_len_ratio: float = 0.60,
    band_h: int = 18,
    canny1: int = 60,
    canny2: int = 160,
) -> List[CutCandidate]:
    gray = feats.gray
    H, W = gray.shape[:2]

    lines = _detect_lines_lsd(gray)
    if not lines:
        edges = cv2.Canny(gray, canny1, canny2)
        lines = _detect_lines_hough(edges)

    if not lines:
        return []

    min_len = max(30.0, min_len_ratio * float(W))
    density = np.zeros((H,), dtype=np.float32)
    angles: List[float] = []
    mid_ys: List[float] = []
    lengths: List[float] = []

    for x1, y1, x2, y2 in lines:
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < min_len:
            continue
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        theta = float(np.arctan2(dy, dx))
        if theta < 0:
            theta += np.pi
        angles.append(theta)
        mid_ys.append(0.5 * (y1 + y2))
        lengths.append(length)

        # distribute length along the line's y-span
        if y1 == y2:
            ys = np.array([y1], dtype=np.int32)
        else:
            steps = int(abs(y2 - y1)) + 1
            ys = np.linspace(y1, y2, num=steps, dtype=np.int32)
        if ys.size == 0:
            continue
        add = length / float(ys.size)
        ys = np.clip(ys, 0, H - 1)
        density[ys] += add

    if not angles:
        return []

    angles_arr = np.array(angles, dtype=np.float32)
    lengths_arr = np.array(lengths, dtype=np.float32)
    mid_ys_arr = np.array(mid_ys, dtype=np.float32)

    # orientation dominance
    ang_hist, ang_edges = np.histogram(angles_arr, bins=angle_bins, range=(0.0, np.pi))
    ang_sum = int(np.sum(ang_hist))
    dominance = float(np.max(ang_hist) / max(ang_sum, 1))
    dom_bin = int(np.argmax(ang_hist))

    # y-band concentration
    y_bins = max(1, int(np.ceil(H / max(y_bin_h, 1))))
    y_hist, y_edges = np.histogram(mid_ys_arr, bins=y_bins, range=(0.0, float(H)))
    y_sum = int(np.sum(y_hist))
    concentration = float(np.max(y_hist) / max(y_sum, 1))

    max_len = float(np.max(lengths_arr)) if lengths_arr.size else 0.0
    long_len = max_len >= (long_len_ratio * float(W))

    if long_len:
        if not (dominance >= dom_thr or concentration >= conc_thr):
            return []
    else:
        if not (dominance >= dom_thr and concentration >= conc_thr):
            return []

    density = density / max(float(W), 1.0)

    mask = density >= density_thr
    candidates: List[CutCandidate] = []
    y = 0
    while y < H:
        if not mask[y]:
            y += 1
            continue
        y1 = y
        while y < H and mask[y]:
            y += 1
        y2 = y
        if (y2 - y1) >= min_run_h:
            # pick dominant-angle lines within this span
            in_span = (mid_ys_arr >= y1) & (mid_ys_arr <= y2)
            if np.any(in_span):
                span_angles = angles_arr[in_span]
                span_lengths = lengths_arr[in_span]
                span_mids = mid_ys_arr[in_span]
                span_bins = np.floor(
                    (span_angles / np.pi) * float(angle_bins)
                ).astype(np.int32)
                span_bins = np.clip(span_bins, 0, angle_bins - 1)
                dom_mask = span_bins == dom_bin
                if np.any(dom_mask):
                    span_lengths = span_lengths[dom_mask]
                    span_mids = span_mids[dom_mask]
            else:
                span_lengths = lengths_arr
                span_mids = mid_ys_arr

            if span_mids.size > 0:
                order = np.argsort(span_mids)
                mids_sorted = span_mids[order]
                w_sorted = span_lengths[order]
                cumsum = np.cumsum(w_sorted)
                mid_weight = 0.5 * cumsum[-1]
                idx = int(np.searchsorted(cumsum, mid_weight))
                yc = int(np.clip(mids_sorted[min(idx, mids_sorted.size - 1)], 0, H - 1))
            else:
                yc = (y1 + y2) // 2

            span_half = max(2, int(band_h // 2))
            s1 = int(np.clip(yc - span_half, 0, H))
            s2 = int(np.clip(yc + span_half, 0, H))
            if s2 <= s1:
                s1, s2 = y1, y2

            d = float(np.clip(density[yc] / max(density_thr, 1e-6), 0, 1))
            strength = float(np.clip(0.6 * d + 0.2 * dominance + 0.2 * concentration, 0, 1))
            candidates.append(
                CutCandidate(
                    y=yc,
                    strength=strength,
                    type="hard_line",
                    span=(s1, s2),
                    meta={
                        "density": float(density[yc]),
                        "y1": y1,
                        "y2": y2,
                        "dominance": dominance,
                        "concentration": concentration,
                        "max_len": max_len,
                    },
                )
            )
    return candidates
