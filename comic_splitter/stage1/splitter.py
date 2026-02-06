from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from comic_splitter.stage1.features import extract_row_features
from comic_splitter.stage1.detectors.gutter import detect_gutters
from comic_splitter.stage1.detectors.blackbar import detect_black_bars
from comic_splitter.stage1.detectors.hardline import detect_hard_lines
from comic_splitter.stage1.fusion import _merge_candidates, build_bands
from comic_splitter.stage1.post_filter import apply_content_difference_filter
from comic_splitter.stage1.band_post_filter import refine_low_content_bands
from comic_splitter.stage1.debug_vis import render_debug
from comic_splitter.common.types import Band, CutCandidate


@dataclass
class Stage1Config:
    # row features
    white_thr: int = 245
    dark_thr: int = 40
    canny1: int = 40
    canny2: int = 120
    smooth_k: int = 21

    # gutter
    min_gap_h: int = 18
    white_ratio_thr: float = 0.985
    edge_density_thr: float = 0.006

    # black bar
    min_bar_h: int = 24
    dark_ratio_thr: float = 0.90
    edge_density_max: float = 0.03

    # hard line
    enable_hardline: bool = True
    hard_min_len_ratio: float = 0.35
    hard_density_thr: float = 0.12
    hard_min_run_h: int = 10
    hard_angle_bins: int = 18
    hard_dom_thr: float = 0.45
    hard_y_bin_h: int = 24
    hard_conc_thr: float = 0.22
    hard_long_len_ratio: float = 0.60
    hard_band_h: int = 18
    hard_canny1: int = 60
    hard_canny2: int = 160

    # fusion/bands
    merge_dist: int = 25
    min_band_h: int = 180
    fallback_chunk_h: int = 2600
    black_bar_band_min_h: int = 24
    black_bar_band_base_score: float = 0.6
    black_bar_edge_penalty_thr: float = 0.02
    black_bar_edge_penalty_score: float = 0.45
    black_bar_merge_dist: int = 8

    # post-filter
    enable_content_diff_filter: bool = True
    content_window_h: int = 64
    content_gray_diff_thr: float = 0.02
    content_edge_diff_thr: float = 0.002
    content_min_scale: float = 0.4

    # band post-filter
    enable_band_refine: bool = True
    band_small_ratio: float = 0.85
    band_edge_small_ratio: float = 1.4
    band_content_thr: float = 0.17
    band_edge_norm_ref: float = 0.02
    band_edge_pos_boost: float = 1.25


class StructureSplitter:
    def __init__(self, cfg: Stage1Config):
        self.cfg = cfg

    def split(
        self,
        rgb,
        debug_out_dir: Optional[str] = None,
        debug_prefix: Optional[str] = None,
    ) -> List[Band]:
        H = rgb.shape[0]
        feats = extract_row_features(
            rgb,
            white_thr=self.cfg.white_thr,
            dark_thr=self.cfg.dark_thr,
            canny1=self.cfg.canny1,
            canny2=self.cfg.canny2,
            smooth_k=self.cfg.smooth_k,
        )

        cands: List[CutCandidate] = []
        cands += detect_gutters(
            feats,
            min_gap_h=self.cfg.min_gap_h,
            white_ratio_thr=self.cfg.white_ratio_thr,
            edge_density_thr=self.cfg.edge_density_thr,
        )
        cands += detect_black_bars(
            feats,
            min_bar_h=self.cfg.min_bar_h,
            dark_ratio_thr=self.cfg.dark_ratio_thr,
            edge_density_max=self.cfg.edge_density_max,
        )
        if self.cfg.enable_hardline:
            cands += detect_hard_lines(
                feats,
                min_len_ratio=self.cfg.hard_min_len_ratio,
                density_thr=self.cfg.hard_density_thr,
                min_run_h=self.cfg.hard_min_run_h,
                angle_bins=self.cfg.hard_angle_bins,
                dom_thr=self.cfg.hard_dom_thr,
                y_bin_h=self.cfg.hard_y_bin_h,
                conc_thr=self.cfg.hard_conc_thr,
                long_len_ratio=self.cfg.hard_long_len_ratio,
                band_h=self.cfg.hard_band_h,
                canny1=self.cfg.hard_canny1,
                canny2=self.cfg.hard_canny2,
            )

        cands = _merge_candidates(cands, merge_dist=self.cfg.merge_dist)
        if self.cfg.enable_content_diff_filter:
            cands = apply_content_difference_filter(
                cands,
                feats,
                window_h=self.cfg.content_window_h,
                gray_diff_thr=self.cfg.content_gray_diff_thr,
                edge_diff_thr=self.cfg.content_edge_diff_thr,
                min_scale=self.cfg.content_min_scale,
            )
        bands = build_bands(
            H,
            cands,
            min_band_h=self.cfg.min_band_h,
            fallback_chunk_h=self.cfg.fallback_chunk_h,
            black_bar_band_min_h=self.cfg.black_bar_band_min_h,
            black_bar_band_base_score=self.cfg.black_bar_band_base_score,
            black_bar_edge_penalty_thr=self.cfg.black_bar_edge_penalty_thr,
            black_bar_edge_penalty_score=self.cfg.black_bar_edge_penalty_score,
            black_bar_merge_dist=self.cfg.black_bar_merge_dist,
        )
        if self.cfg.enable_band_refine:
            bands = refine_low_content_bands(
                bands,
                feats,
                min_band_h=self.cfg.min_band_h,
                small_ratio=self.cfg.band_small_ratio,
                edge_small_ratio=self.cfg.band_edge_small_ratio,
                content_thr=self.cfg.band_content_thr,
                edge_norm_ref=self.cfg.band_edge_norm_ref,
                edge_pos_boost=self.cfg.band_edge_pos_boost,
            )

        if debug_out_dir is not None and debug_prefix is not None:
            render_debug(rgb, feats, cands, bands, debug_out_dir, debug_prefix)

        return bands
