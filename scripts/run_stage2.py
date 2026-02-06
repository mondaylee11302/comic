from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

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

# Defaults: fill volc fields when you are ready to use cloud embeddings.
DEFAULT_IMAGE_PATH = "/Users/lishuai/Documents/子曰文化/PSD文件例子/26-005.psd"
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

    bgr = _load_image(image_path)

    # Stage-1 split
    s1_cfg = Stage1Config(enable_hardline=not args.no_hardline)
    splitter = StructureSplitter(s1_cfg)
    bands = splitter.split(bgr, debug_out_dir=str(debug_dir), debug_prefix=prefix)

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
        s2 = segmenter.segment(bgr, bands)
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
        bgr,
        bands,
        s2["graphs"],
        regions_json,
        out_dir=str(debug_dir),
        prefix=prefix,
        overlay_alpha=float(np.clip(args.debug_overlay_alpha, 0.0, 1.0)),
    )

    panel_manifest = export_panel_crops(
        bgr,
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
    )

    print(f"image: {image_path}")
    print(f"bands: {len(bands_json)} -> {bands_path}")
    print(f"regions: {len(regions_json)} -> {regions_path}")
    print(f"panels: {panel_manifest['panel_count']} -> {panel_manifest['panel_dir']}")
    print(f"manifest: {panel_manifest['manifest_path']}")
    print(f"embedding_backend: {s2['meta'].get('embedding_backend')}")
    print(f"debug: {debug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
