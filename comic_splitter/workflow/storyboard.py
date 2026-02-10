from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Sequence, Tuple

import cv2
import numpy as np

from comic_splitter.psd_preprocess import preprocess_psd_for_panels
from comic_splitter.stage1.splitter import Stage1Config, StructureSplitter
from comic_splitter.stage2.debug_vis import render_stage2_debug
from comic_splitter.stage2.env import load_volc_env
from comic_splitter.stage2.export import export_panel_crops
from comic_splitter.stage2.segmenter import GraphRAGSegmenter, Stage2Config
from comic_splitter.stage2.text_export import (
    build_panel_text_manifest,
    build_panel_text_rows,
    build_unified_text_panel_map,
    text_bbox_from_payload,
    write_panel_text_files,
)
from scripts.run_stage2 import build_text_panel_map_v2
from comic_splitter.workflow.runtime import AgentRetryMatrix, run_agents_with_retry

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class StoryboardPaths:
    image_path: Path
    out_dir: Path
    debug_dir: Path
    prefix: str


@dataclass
class StoryboardOptions:
    strict_ocr: bool = True
    reuse_preprocess_cache: bool = True
    force_reprocess: bool = False
    split_mode: str = "bands"  # "bands" | "stage2"
    enable_mask_inpaint: bool = False
    enable_hardline: bool = True
    strict_volc: bool = False
    debug_overlay_alpha: float = 0.0
    panel_score_thr: float = 0.12
    panel_pad: int = 6
    panel_min_area_ratio: float = 0.04
    panel_containment_thr: float = 0.88
    panel_iou_thr: float = 0.75
    panel_merge_iou_thr: float = 0.45
    panel_merge_x_overlap_thr: float = 0.82
    panel_merge_gap_px: int = 20
    panel_merge_containment_thr: float = 0.78
    panel_merge_fragment_max_area_ratio: float = 0.12
    panel_nms_iou_thr: float = 0.60
    panel_nms_containment_thr: float = 0.90
    heartbeat_interval_sec: int = 8


@dataclass
class StoryboardState:
    seg_bgr: np.ndarray | None = None
    texts_payload: List[Dict] = field(default_factory=list)
    preprocess_meta: Dict = field(default_factory=dict)
    bands: List = field(default_factory=list)
    bands_json: List[Dict] = field(default_factory=list)
    regions_json: List[Dict] = field(default_factory=list)
    s2_meta: Dict = field(default_factory=dict)
    stage2_graphs: Dict = field(default_factory=dict)
    panel_manifest: Dict = field(default_factory=dict)
    panels_payload_raw: List[Dict] = field(default_factory=list)
    panels_payload: List[Dict] = field(default_factory=list)
    mapping_v2_payload: List[Dict] = field(default_factory=list)
    mapping_payload: List[Dict] = field(default_factory=list)
    unified_items: List[Dict] = field(default_factory=list)
    txt_paths: Dict[str, str] = field(default_factory=dict)


@dataclass
class StoryboardContext:
    paths: StoryboardPaths
    options: StoryboardOptions
    state: StoryboardState
    log: Callable[[str], None]


def _run_with_heartbeat(label: str, fn, log: Callable[[str], None], interval_sec: int) -> object:
    stop_event = threading.Event()

    def _heartbeat() -> None:
        start = time.perf_counter()
        while not stop_event.wait(max(3, int(interval_sec))):
            elapsed = int(time.perf_counter() - start)
            log(f"{label} running... {elapsed}s")

    th = threading.Thread(target=_heartbeat, daemon=True)
    t0 = time.perf_counter()
    log(f"{label} start")
    th.start()
    try:
        return fn()
    finally:
        stop_event.set()
        th.join(timeout=0.2)
        log(f"{label} done in {time.perf_counter() - t0:.2f}s")


def _bbox_area(b: Sequence[int]) -> float:
    x1, y1, x2, y2 = [int(v) for v in b]
    return float(max(0, x2 - x1) * max(0, y2 - y1))


def _select_panel_for_text_v1(text_bbox: List[int], panels: List[Mapping]) -> Tuple[str | None, str]:
    best_id = None
    best_distance = float("inf")
    best_iou = -1.0
    t_area = max(1.0, _bbox_area(text_bbox))
    tx1, ty1, tx2, ty2 = [int(v) for v in text_bbox]
    tcx = (tx1 + tx2) * 0.5
    tcy = (ty1 + ty2) * 0.5

    for p in panels:
        px1, py1, px2, py2 = [int(v) for v in p.get("bbox", [0, 0, 0, 0])]
        ix1 = max(tx1, px1)
        iy1 = max(ty1, py1)
        ix2 = min(tx2, px2)
        iy2 = min(ty2, py2)
        inter = float(max(0, ix2 - ix1) * max(0, iy2 - iy1))
        iou_like = inter / t_area
        pcx = (px1 + px2) * 0.5
        pcy = (py1 + py2) * 0.5
        dist = float((pcx - tcx) ** 2 + (pcy - tcy) ** 2)
        if dist < best_distance or (dist == best_distance and iou_like > best_iou):
            best_distance = dist
            best_iou = iou_like
            best_id = str(p.get("panel_id"))
    return best_id, "nearest_center"


def _file_signature(path: Path) -> Dict[str, object]:
    p = path.expanduser().resolve()
    st = p.stat()
    return {
        "path": str(p),
        "size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def _load_preprocess_cache(
    cache_path: Path,
    image_path: Path,
    prefix: str,
    enable_mask_inpaint: bool,
) -> Tuple[np.ndarray, List[Dict], Dict] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if payload.get("source_signature", {}) != _file_signature(image_path):
        return None

    expected_cfg = {"enable_mask_inpaint": bool(enable_mask_inpaint)}
    if payload.get("config_signature", {}) != expected_cfg:
        return None

    preprocess_meta = payload.get("preprocess_meta", {})
    art_clean_path = Path(str(preprocess_meta.get("art_clean_path", ""))).expanduser()
    texts_path = Path(str(preprocess_meta.get("texts_merged_path", ""))).expanduser()
    if not art_clean_path.exists():
        art_clean_path = cache_path.parent / f"{prefix}_art_clean.png"
    if not texts_path.exists():
        texts_path = cache_path.parent / f"{prefix}_texts_merged.json"
    if not art_clean_path.exists() or not texts_path.exists():
        return None

    seg_bgr = cv2.imread(str(art_clean_path), cv2.IMREAD_COLOR)
    if seg_bgr is None:
        return None
    try:
        texts_payload = json.loads(texts_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(texts_payload, list):
        return None
    return seg_bgr, texts_payload, preprocess_meta


def _save_preprocess_cache(
    cache_path: Path,
    image_path: Path,
    preprocess_meta: Dict,
    enable_mask_inpaint: bool,
) -> None:
    payload = {
        "source_signature": _file_signature(image_path),
        "config_signature": {"enable_mask_inpaint": bool(enable_mask_inpaint)},
        "preprocess_meta": preprocess_meta,
        "created_at": int(time.time()),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _export_band_panels(
    rgb: np.ndarray,
    bands: List,
    out_dir: Path,
    prefix: str,
    pad: int,
    image_ext: str = "png",
) -> Dict:
    panel_dir = out_dir / f"{prefix}_panels"
    panel_dir.mkdir(parents=True, exist_ok=True)

    h, w = rgb.shape[:2]
    ext = str(image_ext or "png").strip().lower().lstrip(".") or "png"
    exported: List[Dict] = []
    for i, b in enumerate(bands, start=1):
        y1 = max(0, int(b.y1) - int(pad))
        y2 = min(h, int(b.y2) + int(pad))
        if y2 <= y1:
            continue
        panel_id = f"panel_{i:03d}"
        bbox = [0, y1, int(w), y2]
        crop = rgb[y1:y2, 0:w]
        image_path = panel_dir / f"{panel_id}.{ext}"
        cv2.imwrite(str(image_path), crop)
        exported.append(
            {
                "panel_id": panel_id,
                "region_id": -1,
                "band_index": int(i - 1),
                "score": float(getattr(b, "score", 0.0)),
                "bbox": bbox,
                "bbox_path": str(image_path),
                "mask_path": None,
            }
        )

    manifest = {
        "panel_count": len(exported),
        "source_region_count": len(bands),
        "primary_region_count": len(bands),
        "merged_region_count": len(bands),
        "dedup_region_count": len(exported),
        "panel_dir": str(panel_dir),
        "score_thr": None,
        "pad": int(pad),
        "export_mask": False,
        "min_area_ratio": None,
        "containment_thr": None,
        "iou_thr": None,
        "merge_iou_thr": None,
        "merge_x_overlap_thr": None,
        "merge_gap_px": None,
        "merge_containment_thr": None,
        "merge_fragment_max_area_ratio": None,
        "nms_iou_thr": None,
        "nms_containment_thr": None,
        "image_ext": ext,
        "split_mode": "bands",
        "panels": exported,
    }
    manifest_path = out_dir / f"{prefix}_panels_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


class WorkflowAgent:
    name = "workflow_agent"

    def run(self, ctx: StoryboardContext) -> None:
        raise NotImplementedError


class PreprocessAgent(WorkflowAgent):
    name = "preprocess_agent"

    def run(self, ctx: StoryboardContext) -> None:
        paths, opts = ctx.paths, ctx.options
        cache_path = paths.out_dir / f"{paths.prefix}_preprocess_cache_meta.json"
        cache_loaded = False

        can_try_cache = bool(opts.reuse_preprocess_cache) and not bool(opts.force_reprocess)
        if can_try_cache:
            cached = _load_preprocess_cache(
                cache_path=cache_path,
                image_path=paths.image_path,
                prefix=paths.prefix,
                enable_mask_inpaint=opts.enable_mask_inpaint,
            )
            if cached is not None:
                ctx.state.seg_bgr, ctx.state.texts_payload, ctx.state.preprocess_meta = cached
                cache_loaded = True
                ctx.log("preprocess cache hit, skip preprocess_psd_for_panels")
            else:
                ctx.log("preprocess cache miss, run preprocess_psd_for_panels")

        if not cache_loaded:
            pp = _run_with_heartbeat(
                "preprocess_psd_for_panels",
                lambda: preprocess_psd_for_panels(
                    image_path=paths.image_path,
                    out_dir=paths.out_dir,
                    prefix=paths.prefix,
                    enable_mask_inpaint=bool(opts.enable_mask_inpaint),
                    progress_hook=lambda msg: ctx.log(f"preprocess: {msg}"),
                ),
                log=ctx.log,
                interval_sec=opts.heartbeat_interval_sec,
            )
            ctx.log(f"ocr_status={pp.ocr_status}, ocr_request_id={pp.ocr_request_id}")
            if bool(opts.strict_ocr) and pp.ocr_status not in {"ok", "ok_empty"}:
                raise RuntimeError(
                    f"OCR required but unavailable, status={pp.ocr_status}, reason={pp.ocr_degraded_reason or '<empty>'}"
                )

            ctx.state.seg_bgr = pp.clean_bgr
            ctx.state.texts_payload = [asdict(t) for t in pp.texts]
            ctx.state.preprocess_meta = {
                "enabled": True,
                "bubble_layer_id": pp.bubble_layer_id,
                "bubble_layer_path": pp.bubble_layer_path,
                "bubble_selected": pp.bubble_layer_id is not None,
                "textbox_layer_ids": pp.textbox_layer_ids,
                "textbox_layer_paths": pp.textbox_layer_paths,
                "textbox_layer_count": len(pp.textbox_layer_ids),
                "raster_text_layer_ids": pp.raster_text_layer_ids,
                "raster_text_layer_paths": pp.raster_text_layer_paths,
                "raster_text_layer_count": len(pp.raster_text_layer_ids),
                "removed_layer_ids": pp.removed_layer_ids,
                "removed_layer_paths": pp.removed_layer_paths,
                "art_clean_path": pp.art_clean_path,
                "texts_path": pp.texts_path,
                "texts_merged_path": pp.texts_merged_path,
                "text_canvas_map_path": pp.text_canvas_map_path,
                "bubble_ranking_path": pp.bubble_ranking_path,
                "textbox_ranking_path": pp.textbox_ranking_path,
                "ocr_status": pp.ocr_status,
                "ocr_request_id": pp.ocr_request_id,
                "ocr_degraded_reason": pp.ocr_degraded_reason,
                "upload_latency_ms": pp.upload_latency_ms,
                "ocr_latency_ms": pp.ocr_latency_ms,
                "ocr_input_size": pp.ocr_input_size,
                "merge_unmatched_psd_count": pp.merge_unmatched_psd_count,
                "merge_unmatched_ocr_count": pp.merge_unmatched_ocr_count,
                "text_backend": pp.text_backend,
            }
            if bool(opts.reuse_preprocess_cache):
                _save_preprocess_cache(
                    cache_path=cache_path,
                    image_path=paths.image_path,
                    preprocess_meta=ctx.state.preprocess_meta,
                    enable_mask_inpaint=opts.enable_mask_inpaint,
                )
                ctx.log(f"preprocess cache saved: {cache_path}")
        else:
            ctx.log(
                "cached preprocess meta: ocr_status=%s, request_id=%s"
                % (
                    str(ctx.state.preprocess_meta.get("ocr_status", "")),
                    str(ctx.state.preprocess_meta.get("ocr_request_id", "")),
                )
            )
            if bool(opts.strict_ocr) and str(ctx.state.preprocess_meta.get("ocr_status", "")) not in {"ok", "ok_empty"}:
                raise RuntimeError(
                    "OCR required but cached preprocess is not ok: "
                    f"status={ctx.state.preprocess_meta.get('ocr_status')}, "
                    f"reason={ctx.state.preprocess_meta.get('ocr_degraded_reason') or '<empty>'}"
                )
        ctx.log(f"text_count={len(ctx.state.texts_payload)}")


class SplitAgent(WorkflowAgent):
    name = "split_agent"

    def run(self, ctx: StoryboardContext) -> None:
        if ctx.state.seg_bgr is None:
            raise RuntimeError("split_agent requires preprocessed image")
        paths, opts = ctx.paths, ctx.options

        ctx.log("stage1 split start")
        splitter = StructureSplitter(Stage1Config(enable_hardline=bool(opts.enable_hardline)))
        bands = splitter.split(ctx.state.seg_bgr, debug_out_dir=str(paths.debug_dir), debug_prefix=paths.prefix)
        ctx.state.bands = bands
        ctx.state.bands_json = [asdict(b) for b in bands]
        ctx.log(f"stage1 split done, bands={len(bands)}")

        use_stage2 = str(opts.split_mode).strip().lower() == "stage2"
        ctx.state.regions_json = []
        ctx.state.s2_meta = {"embedding_backend": "skipped_band_split", "band_count": len(bands), "split_mode": "bands"}
        ctx.state.stage2_graphs = {}

        if use_stage2:
            ctx.log("load volc env")
            env = load_volc_env()
            s2_cfg = Stage2Config(
                volc_api_key=env.api_key,
                volc_model_endpoint=env.model_endpoint,
                volc_base_url=env.base_url,
                volc_prompt_text=env.prompt_text,
                allow_local_fallback=not bool(opts.strict_volc),
                embedding_cache_dir=str(REPO_ROOT / ".cache" / "stage2_embeddings"),
                verbose=True,
            )
            segmenter = GraphRAGSegmenter(s2_cfg)
            try:
                s2 = _run_with_heartbeat(
                    "stage2.segment",
                    lambda: segmenter.segment(ctx.state.seg_bgr, bands),
                    log=ctx.log,
                    interval_sec=opts.heartbeat_interval_sec,
                )
            finally:
                segmenter.close()
            ctx.log(f"stage2 done, regions={len(s2['regions'])}, embedding_backend={s2['meta'].get('embedding_backend')}")
            if bool(opts.strict_volc) and s2["meta"].get("embedding_backend") != "volc_mm":
                raise RuntimeError("strict volc mode enabled, but embedding backend is not volc_mm")
            ctx.state.regions_json = s2["regions"]
            ctx.state.s2_meta = dict(s2["meta"])
            ctx.state.stage2_graphs = dict(s2["graphs"])
        else:
            ctx.log("split_mode=bands, skip stage2 graph-rag")

        bands_path = paths.out_dir / f"{paths.prefix}_bands.json"
        regions_path = paths.out_dir / f"{paths.prefix}_regions_stage2.json"
        bands_path.write_text(json.dumps(ctx.state.bands_json, ensure_ascii=False, indent=2), encoding="utf-8")
        regions_path.write_text(
            json.dumps({"regions": ctx.state.regions_json, "meta": ctx.state.s2_meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if use_stage2:
            render_stage2_debug(
                ctx.state.seg_bgr,
                bands,
                ctx.state.stage2_graphs,
                ctx.state.regions_json,
                out_dir=str(paths.debug_dir),
                prefix=paths.prefix,
                overlay_alpha=float(np.clip(opts.debug_overlay_alpha, 0.0, 1.0)),
            )
            ctx.state.panel_manifest = _run_with_heartbeat(
                "export_panel_crops",
                lambda: export_panel_crops(
                    ctx.state.seg_bgr,
                    bands,
                    ctx.state.stage2_graphs,
                    ctx.state.regions_json,
                    out_dir=str(paths.out_dir),
                    prefix=paths.prefix,
                    score_thr=float(opts.panel_score_thr),
                    pad=max(0, int(opts.panel_pad)),
                    export_mask=False,
                    min_area_ratio=float(opts.panel_min_area_ratio),
                    containment_thr=float(opts.panel_containment_thr),
                    iou_thr=float(opts.panel_iou_thr),
                    merge_iou_thr=float(opts.panel_merge_iou_thr),
                    merge_x_overlap_thr=float(opts.panel_merge_x_overlap_thr),
                    merge_gap_px=max(0, int(opts.panel_merge_gap_px)),
                    merge_containment_thr=float(opts.panel_merge_containment_thr),
                    merge_fragment_max_area_ratio=float(opts.panel_merge_fragment_max_area_ratio),
                    nms_iou_thr=float(opts.panel_nms_iou_thr),
                    nms_containment_thr=float(opts.panel_nms_containment_thr),
                    image_ext="png",
                ),
                log=ctx.log,
                interval_sec=opts.heartbeat_interval_sec,
            )
        else:
            ctx.state.panel_manifest = _run_with_heartbeat(
                "export_band_panels",
                lambda: _export_band_panels(
                    ctx.state.seg_bgr,
                    bands,
                    out_dir=paths.out_dir,
                    prefix=paths.prefix,
                    pad=max(0, int(opts.panel_pad)),
                    image_ext="png",
                ),
                log=ctx.log,
                interval_sec=opts.heartbeat_interval_sec,
            )
        ctx.log(f"panel_count={ctx.state.panel_manifest['panel_count']}")


class TextPackagingAgent(WorkflowAgent):
    name = "text_packaging_agent"

    def run(self, ctx: StoryboardContext) -> None:
        paths = ctx.paths
        panel_manifest = ctx.state.panel_manifest
        ctx.state.panels_payload_raw = panel_manifest.get("panels", [])
        ctx.state.panels_payload = [
            {
                "panel_id": p.get("panel_id"),
                "bbox": p.get("bbox", [0, 0, 0, 0]),
                "score": p.get("score", 0.0),
                "source_region_id": p.get("region_id"),
            }
            for p in ctx.state.panels_payload_raw
        ]
        panels_json_path = paths.out_dir / f"{paths.prefix}_panels.json"
        panels_json_path.write_text(json.dumps(ctx.state.panels_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        ctx.state.mapping_v2_payload = build_text_panel_map_v2(
            texts_payload=ctx.state.texts_payload,
            panels_payload_raw=ctx.state.panels_payload_raw,
        )
        mapping_v2_path = paths.out_dir / f"{paths.prefix}_text_panel_map_v2.json"
        mapping_v2_path.write_text(json.dumps(ctx.state.mapping_v2_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        ctx.state.mapping_payload = []
        for t in ctx.state.texts_payload:
            text_bbox = text_bbox_from_payload(t)
            panel_id, method = _select_panel_for_text_v1(text_bbox, ctx.state.panels_payload_raw)
            ctx.state.mapping_payload.append({"text_id": t.get("text_id"), "panel_id": panel_id, "method": method})
        mapping_json_path = paths.out_dir / f"{paths.prefix}_mapping.json"
        mapping_json_path.write_text(json.dumps(ctx.state.mapping_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        ctx.state.unified_items = build_unified_text_panel_map(
            texts_payload=ctx.state.texts_payload,
            mapping_v2_payload=ctx.state.mapping_v2_payload,
            panels_payload_raw=ctx.state.panels_payload_raw,
        )
        unified_map_path = paths.out_dir / f"{paths.prefix}_text_panel_unified_map.json"
        unified_map_path.write_text(
            json.dumps(
                {
                    "image": str(paths.image_path),
                    "panel_dir": panel_manifest.get("panel_dir"),
                    "text_backend": ctx.state.preprocess_meta.get("text_backend", "psd+ocr_merge"),
                    "items": ctx.state.unified_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        rows_by_panel = build_panel_text_rows(ctx.state.unified_items)
        ctx.state.txt_paths = write_panel_text_files(
            panels_payload_raw=ctx.state.panels_payload_raw,
            rows_by_panel=rows_by_panel,
            panel_dir=panel_manifest.get("panel_dir", str(paths.out_dir / f"{paths.prefix}_panels")),
        )
        panel_text_manifest = build_panel_text_manifest(
            panels_payload_raw=ctx.state.panels_payload_raw,
            txt_paths=ctx.state.txt_paths,
            rows_by_panel=rows_by_panel,
        )
        panel_text_manifest_path = paths.out_dir / f"{paths.prefix}_panel_text_manifest.json"
        panel_text_manifest_path.write_text(json.dumps(panel_text_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        for p in panel_manifest.get("panels", []):
            pid = str(p.get("panel_id"))
            p["txt_path"] = ctx.state.txt_paths.get(pid, "")
        manifest_path = Path(panel_manifest.get("manifest_path", paths.out_dir / f"{paths.prefix}_panels_manifest.json"))
        manifest_payload = dict(panel_manifest)
        manifest_payload.pop("manifest_path", None)
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        pipeline_meta_path = paths.out_dir / f"{paths.prefix}_pipeline_meta.json"
        pipeline_meta = {
            "image": str(paths.image_path),
            "is_psd": True,
            "preprocess": ctx.state.preprocess_meta,
            "stage2_meta": ctx.state.s2_meta,
            "split_mode": "stage2" if str(ctx.options.split_mode).strip().lower() == "stage2" else "bands",
            "bands_count": len(ctx.state.bands_json),
            "regions_count": len(ctx.state.regions_json),
            "panel_count": panel_manifest["panel_count"],
            "text_count": len(ctx.state.texts_payload),
            "upload_latency_ms": ctx.state.preprocess_meta.get("upload_latency_ms", 0),
            "ocr_latency_ms": ctx.state.preprocess_meta.get("ocr_latency_ms", 0),
            "ocr_input_size": ctx.state.preprocess_meta.get("ocr_input_size", {}),
            "ocr_degraded_reason": ctx.state.preprocess_meta.get("ocr_degraded_reason", ""),
            "merge_unmatched_psd_count": ctx.state.preprocess_meta.get("merge_unmatched_psd_count", 0),
            "merge_unmatched_ocr_count": ctx.state.preprocess_meta.get("merge_unmatched_ocr_count", 0),
            "textbox_layer_count": ctx.state.preprocess_meta.get("textbox_layer_count", 0),
            "text_panel_unified_map_path": str(unified_map_path),
            "panel_text_manifest_path": str(panel_text_manifest_path),
        }
        pipeline_meta_path.write_text(json.dumps(pipeline_meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"image: {paths.image_path}")
        print(f"art_clean: {ctx.state.preprocess_meta.get('art_clean_path')}")
        print(f"bands: {len(ctx.state.bands_json)} -> {paths.out_dir / f'{paths.prefix}_bands.json'}")
        print(f"regions: {len(ctx.state.regions_json)} -> {paths.out_dir / f'{paths.prefix}_regions_stage2.json'}")
        print(f"panels: {panel_manifest['panel_count']} -> {panel_manifest['panel_dir']}")
        print(f"panels_json: {panels_json_path}")
        print(f"mapping_json: {mapping_json_path}")
        print(f"text_panel_map_v2: {mapping_v2_path}")
        print(f"text_panel_unified_map: {unified_map_path}")
        print(f"panel_text_manifest: {panel_text_manifest_path}")
        print(f"pipeline_meta: {pipeline_meta_path}")
        print(f"text_canvas_map: {ctx.state.preprocess_meta.get('text_canvas_map_path')}")
        print(f"manifest: {manifest_path}")
        print(f"embedding_backend: {ctx.state.s2_meta.get('embedding_backend')}")
        print(f"debug: {paths.debug_dir}")


class StoryboardWorkflow:
    def __init__(
        self,
        paths: StoryboardPaths,
        options: StoryboardOptions,
        log: Callable[[str], None],
        retry_matrix: AgentRetryMatrix | None = None,
    ) -> None:
        self.ctx = StoryboardContext(paths=paths, options=options, state=StoryboardState(), log=log)
        self.agents: List[WorkflowAgent] = [PreprocessAgent(), SplitAgent(), TextPackagingAgent()]
        self.retry_matrix = retry_matrix or AgentRetryMatrix()

    def run(self) -> StoryboardState:
        self.ctx.paths.out_dir.mkdir(parents=True, exist_ok=True)
        self.ctx.paths.debug_dir.mkdir(parents=True, exist_ok=True)
        self.ctx.log(f"image={self.ctx.paths.image_path}")
        self.ctx.log(f"out_dir={self.ctx.paths.out_dir}")
        self.ctx.log(f"debug_dir={self.ctx.paths.debug_dir}")
        self.ctx.log(f"strict_ocr={self.ctx.options.strict_ocr}")
        self.ctx.log(f"split_mode={self.ctx.options.split_mode}")
        self.ctx.log(
            "reuse_preprocess_cache=%s, force_reprocess=%s"
            % (self.ctx.options.reuse_preprocess_cache, self.ctx.options.force_reprocess)
        )
        run_agents_with_retry(
            agents=self.agents,
            run_one=lambda a: a.run(self.ctx),
            log=self.ctx.log,
            retry=self.retry_matrix,
        )
        return self.ctx.state
