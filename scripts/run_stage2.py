from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import cv2
import numpy as np
from psd_tools import PSDImage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comic_splitter.stage1.splitter import Stage1Config, StructureSplitter
from comic_splitter.stage2.segmenter import GraphRAGSegmenter, Stage2Config
from comic_splitter.stage2.env import load_volc_env
from comic_splitter.stage2.debug_vis import render_stage2_debug
from comic_splitter.stage2.export import export_panel_crops
from comic_splitter.psd_preprocess import preprocess_psd_for_panels

# Defaults: fill volc fields when you are ready to use cloud embeddings.
DEFAULT_IMAGE_PATH = ""
DEFAULT_OUTPUT_DIR = str(ROOT / "output")
DEFAULT_DEBUG_DIR = str(Path(DEFAULT_OUTPUT_DIR) / "debug")
DEFAULT_PREFIX = "page_001"


def _load_image(path: Path) -> np.ndarray:
    suf = path.suffix.lower()
    if suf in {".psd", ".psb"}:
        psd = PSDImage.open(path)
        pil_img = psd.composite()
        arr = np.array(pil_img)
        if arr.ndim == 3 and arr.shape[2] == 4:
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        if arr.ndim == 3 and arr.shape[2] == 3:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        raise ValueError(f"Unsupported PSD composite mode: shape={arr.shape}")
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to load image: {path}")
    return img


def _select_panel_for_text(text_bbox: List[int], panels: List[Dict]) -> Tuple[str | None, str]:
    tx1, ty1, tx2, ty2 = [int(v) for v in text_bbox]
    tcx = (tx1 + tx2) * 0.5
    tcy = (ty1 + ty2) * 0.5

    best_id = None
    best_distance = float("inf")
    best_iou = -1.0
    t_area = max(1.0, float((tx2 - tx1) * (ty2 - ty1)))
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage1 + stage2 graph-rag segmentation")
    parser.add_argument("--image", default=DEFAULT_IMAGE_PATH, help="Input image path")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--debug-dir", default=DEFAULT_DEBUG_DIR, help="Debug output directory")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Output file prefix")
    parser.add_argument("--no-hardline", action="store_true", help="Disable stage1 hardline")
    parser.add_argument(
        "--debug-overlay-alpha",
        type=float,
        default=0.0,
        help="Debug region overlay alpha in [0,1], default 0 (no color tint)",
    )
    parser.add_argument(
        "--strict-volc",
        action="store_true",
        help="Fail if volc api key or model endpoint is missing/unavailable",
    )
    parser.add_argument(
        "--no-psd-clean",
        action="store_true",
        help="Disable PSD clean-art preprocessing (text/bubble removal)",
    )
    parser.add_argument(
        "--panel-score-thr",
        type=float,
        default=0.12,
        help="Minimum region score to export panel crop",
    )
    parser.add_argument(
        "--panel-pad",
        type=int,
        default=6,
        help="Padding (pixels) around exported panel bbox",
    )
    parser.add_argument(
        "--export-mask",
        action="store_true",
        help="Also export transparent mask panel png files",
    )
    parser.add_argument(
        "--panel-min-area-ratio",
        type=float,
        default=0.04,
        help="Minimum area ratio for primary panel selection",
    )
    parser.add_argument(
        "--panel-containment-thr",
        type=float,
        default=0.88,
        help="Drop region if mostly contained by a larger one",
    )
    parser.add_argument(
        "--panel-iou-thr",
        type=float,
        default=0.75,
        help="Drop region if heavily overlapping lower-priority panel",
    )
    parser.add_argument(
        "--panel-merge-iou-thr",
        type=float,
        default=0.45,
        help="Merge fragmented regions when IoU exceeds this threshold",
    )
    parser.add_argument(
        "--panel-merge-x-overlap-thr",
        type=float,
        default=0.82,
        help="Merge fragmented regions when x-overlap is high",
    )
    parser.add_argument(
        "--panel-merge-gap-px",
        type=int,
        default=20,
        help="Max vertical gap (px) to merge fragmented regions",
    )
    parser.add_argument(
        "--panel-merge-containment-thr",
        type=float,
        default=0.78,
        help="Merge fragmented regions when containment is high",
    )
    parser.add_argument(
        "--panel-merge-fragment-max-area-ratio",
        type=float,
        default=0.12,
        help="Only apply gap-based merge when at least one region is this small",
    )
    parser.add_argument(
        "--panel-nms-iou-thr",
        type=float,
        default=0.60,
        help="Final dedup IoU threshold",
    )
    parser.add_argument(
        "--panel-nms-containment-thr",
        type=float,
        default=0.90,
        help="Final dedup containment threshold",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.image:
        raise ValueError("Please set DEFAULT_IMAGE_PATH in scripts/run_stage2.py or pass --image")

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    out_dir = Path(args.out_dir)
    debug_dir = Path(args.debug_dir)
    prefix = args.prefix or image_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    is_psd = image_path.suffix.lower() in {".psd", ".psb"}
    source_bgr = _load_image(image_path)
    seg_bgr = source_bgr
    texts_payload: List[Dict] = []
    preprocess_meta: Dict = {}
    if is_psd and not args.no_psd_clean:
        pp = preprocess_psd_for_panels(
            image_path=image_path,
            out_dir=out_dir,
            prefix=prefix,
        )
        seg_bgr = pp.clean_bgr
        source_bgr = pp.source_bgr
        texts_payload = [asdict(t) for t in pp.texts]
        preprocess_meta = {
            "enabled": True,
            "bubble_layer_id": pp.bubble_layer_id,
            "bubble_layer_path": pp.bubble_layer_path,
            "bubble_selected": pp.bubble_layer_id is not None,
            "removed_layer_ids": pp.removed_layer_ids,
            "removed_layer_paths": pp.removed_layer_paths,
            "art_clean_path": pp.art_clean_path,
            "texts_path": pp.texts_path,
            "bubble_ranking_path": pp.bubble_ranking_path,
            "ocr_status": pp.ocr_status,
            "text_backend": pp.text_backend,
        }
    else:
        preprocess_meta = {
            "enabled": False,
            "reason": "input_not_psd_or_disabled",
        }

    # Stage-1 split
    s1_cfg = Stage1Config(enable_hardline=not args.no_hardline)
    splitter = StructureSplitter(s1_cfg)
    bands = splitter.split(seg_bgr, debug_out_dir=str(debug_dir), debug_prefix=prefix)

    # Stage-2 graph-rag
    env = load_volc_env()
    s2_cfg = Stage2Config(
        volc_api_key=env.api_key,
        volc_model_endpoint=env.model_endpoint,
        volc_base_url=env.base_url,
        volc_prompt_text=env.prompt_text,
        allow_local_fallback=not args.strict_volc,
        embedding_cache_dir=str(ROOT / ".cache" / "stage2_embeddings"),
        verbose=True,
    )
    segmenter = GraphRAGSegmenter(s2_cfg)
    try:
        s2 = segmenter.segment(seg_bgr, bands)
    finally:
        segmenter.close()

    if args.strict_volc and s2["meta"].get("embedding_backend") != "volc_mm":
        raise RuntimeError("strict volc mode enabled, but embedding backend is not volc_mm")

    bands_json = [asdict(b) for b in bands]
    regions_json = s2["regions"]

    bands_path = out_dir / f"{prefix}_bands.json"
    regions_path = out_dir / f"{prefix}_regions_stage2.json"

    bands_path.write_text(json.dumps(bands_json, ensure_ascii=False, indent=2), encoding="utf-8")
    regions_path.write_text(
        json.dumps({"regions": regions_json, "meta": s2["meta"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    render_stage2_debug(
        seg_bgr,
        bands,
        s2["graphs"],
        regions_json,
        out_dir=str(debug_dir),
        prefix=prefix,
        overlay_alpha=float(np.clip(args.debug_overlay_alpha, 0.0, 1.0)),
    )

    panel_manifest = export_panel_crops(
        source_bgr,
        bands,
        s2["graphs"],
        regions_json,
        out_dir=str(out_dir),
        prefix=prefix,
        score_thr=float(args.panel_score_thr),
        pad=max(0, int(args.panel_pad)),
        export_mask=bool(args.export_mask),
        min_area_ratio=float(args.panel_min_area_ratio),
        containment_thr=float(args.panel_containment_thr),
        iou_thr=float(args.panel_iou_thr),
        merge_iou_thr=float(args.panel_merge_iou_thr),
        merge_x_overlap_thr=float(args.panel_merge_x_overlap_thr),
        merge_gap_px=max(0, int(args.panel_merge_gap_px)),
        merge_containment_thr=float(args.panel_merge_containment_thr),
        merge_fragment_max_area_ratio=float(args.panel_merge_fragment_max_area_ratio),
        nms_iou_thr=float(args.panel_nms_iou_thr),
        nms_containment_thr=float(args.panel_nms_containment_thr),
    )

    panels_payload_raw = panel_manifest.get("panels", [])
    panels_payload = [
        {
            "panel_id": p.get("panel_id"),
            "bbox": p.get("bbox", [0, 0, 0, 0]),
            "score": p.get("score", 0.0),
            "source_region_id": p.get("region_id"),
        }
        for p in panels_payload_raw
    ]
    panels_json_path = out_dir / f"{prefix}_panels.json"
    panels_json_path.write_text(
        json.dumps(panels_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mapping_payload: List[Dict] = []
    for t in texts_payload:
        panel_id, method = _select_panel_for_text(t.get("bbox", [0, 0, 0, 0]), panels_payload_raw)
        mapping_payload.append(
            {
                "text_id": t.get("text_id"),
                "panel_id": panel_id,
                "method": method,
            }
        )
    mapping_json_path = out_dir / f"{prefix}_mapping.json"
    mapping_json_path.write_text(
        json.dumps(mapping_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    pipeline_meta_path = out_dir / f"{prefix}_pipeline_meta.json"
    pipeline_meta = {
        "image": str(image_path),
        "is_psd": bool(is_psd),
        "preprocess": preprocess_meta,
        "stage2_meta": s2["meta"],
        "bands_count": len(bands_json),
        "regions_count": len(regions_json),
        "panel_count": panel_manifest["panel_count"],
        "text_count": len(texts_payload),
    }
    pipeline_meta_path.write_text(
        json.dumps(pipeline_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"image: {image_path}")
    print(f"bands: {len(bands_json)} -> {bands_path}")
    print(f"regions: {len(regions_json)} -> {regions_path}")
    print(f"panels: {panel_manifest['panel_count']} -> {panel_manifest['panel_dir']}")
    print(f"panels_json: {panels_json_path}")
    print(f"mapping_json: {mapping_json_path}")
    print(f"pipeline_meta: {pipeline_meta_path}")
    if preprocess_meta.get("enabled"):
        print(f"art_clean: {preprocess_meta.get('art_clean_path')}")
        print(f"texts_json: {preprocess_meta.get('texts_path')}")
        print(f"bubble_ranking: {preprocess_meta.get('bubble_ranking_path')}")
    print(f"manifest: {panel_manifest['manifest_path']}")
    print(f"embedding_backend: {s2['meta'].get('embedding_backend')}")
    print(f"debug: {debug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
