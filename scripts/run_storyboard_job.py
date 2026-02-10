from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comic_splitter.workflow import (
    AgentRetryMatrix,
    StoryboardOptions,
    StoryboardPaths,
    StoryboardWorkflow,
    load_storyboard_config,
)

# Edit only these constants for local runs.
PSD_PATH = "/Users/lishuai/Documents/子曰文化/PSD文件例子/162-001.psd"
OUT_DIR = str(ROOT / "output")
DEBUG_DIR = str(Path(OUT_DIR) / "debug")
PREFIX = "storyboard_001"

# Workflow behavior.
STRICT_OCR = True
REUSE_PREPROCESS_CACHE = True
FORCE_REPROCESS = False
SPLIT_MODE = "bands"  # "bands" | "stage2"

# Optional toggles.
ENABLE_MASK_INPAINT = False
ENABLE_HARDLINE = True
STRICT_VOLC = False
DEBUG_OVERLAY_ALPHA = 0.0

# Panel export settings.
PANEL_SCORE_THR = 0.12
PANEL_PAD = 6
PANEL_MIN_AREA_RATIO = 0.04
PANEL_CONTAINMENT_THR = 0.88
PANEL_IOU_THR = 0.75
PANEL_MERGE_IOU_THR = 0.45
PANEL_MERGE_X_OVERLAP_THR = 0.82
PANEL_MERGE_GAP_PX = 20
PANEL_MERGE_CONTAINMENT_THR = 0.78
PANEL_MERGE_FRAGMENT_MAX_AREA_RATIO = 0.12
PANEL_NMS_IOU_THR = 0.60
PANEL_NMS_CONTAINMENT_THR = 0.90
HEARTBEAT_INTERVAL_SEC = 8
DEFAULT_CONFIG_PATH = ROOT / "config" / "storyboard.toml"


def _log(msg: str) -> None:
    print(f"[storyboard] {msg}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run storyboard multi-agent workflow.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="TOML config path")
    parser.add_argument("--image", default="", help="Optional override image path")
    parser.add_argument("--prefix", default="", help="Optional override prefix")
    parser.add_argument("--out-dir", default="", help="Optional override output directory")
    parser.add_argument("--debug-dir", default="", help="Optional override debug directory")
    parser.add_argument("--verbose", action="store_true", help="Enable workflow logs")
    parser.add_argument("--quiet", action="store_true", help="Disable workflow logs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not PSD_PATH:
        raise ValueError("Please set PSD_PATH in scripts/run_storyboard_job.py")
    image_path = Path(args.image).expanduser() if str(args.image).strip() else Path(PSD_PATH).expanduser()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if image_path.suffix.lower() not in {".psd", ".psb"}:
        raise ValueError("run_storyboard_job.py only supports PSD/PSB input")

    default_paths = StoryboardPaths(
        image_path=image_path,
        out_dir=Path(args.out_dir).expanduser() if str(args.out_dir).strip() else Path(OUT_DIR).expanduser(),
        debug_dir=Path(args.debug_dir).expanduser() if str(args.debug_dir).strip() else Path(DEBUG_DIR).expanduser(),
        prefix=(str(args.prefix).strip() if str(args.prefix).strip() else (PREFIX or image_path.stem)),
    )
    default_options = StoryboardOptions(
        strict_ocr=bool(STRICT_OCR),
        reuse_preprocess_cache=bool(REUSE_PREPROCESS_CACHE),
        force_reprocess=bool(FORCE_REPROCESS),
        split_mode=str(SPLIT_MODE),
        enable_mask_inpaint=bool(ENABLE_MASK_INPAINT),
        enable_hardline=bool(ENABLE_HARDLINE),
        strict_volc=bool(STRICT_VOLC),
        debug_overlay_alpha=float(DEBUG_OVERLAY_ALPHA),
        panel_score_thr=float(PANEL_SCORE_THR),
        panel_pad=max(0, int(PANEL_PAD)),
        panel_min_area_ratio=float(PANEL_MIN_AREA_RATIO),
        panel_containment_thr=float(PANEL_CONTAINMENT_THR),
        panel_iou_thr=float(PANEL_IOU_THR),
        panel_merge_iou_thr=float(PANEL_MERGE_IOU_THR),
        panel_merge_x_overlap_thr=float(PANEL_MERGE_X_OVERLAP_THR),
        panel_merge_gap_px=max(0, int(PANEL_MERGE_GAP_PX)),
        panel_merge_containment_thr=float(PANEL_MERGE_CONTAINMENT_THR),
        panel_merge_fragment_max_area_ratio=float(PANEL_MERGE_FRAGMENT_MAX_AREA_RATIO),
        panel_nms_iou_thr=float(PANEL_NMS_IOU_THR),
        panel_nms_containment_thr=float(PANEL_NMS_CONTAINMENT_THR),
        heartbeat_interval_sec=max(3, int(HEARTBEAT_INTERVAL_SEC)),
    )
    default_retry = AgentRetryMatrix()
    config_path = Path(args.config).expanduser() if str(args.config).strip() else None
    paths, options, retry = load_storyboard_config(
        config_path=config_path,
        default_paths=default_paths,
        default_options=default_options,
        default_retry=default_retry,
    )
    # CLI explicit args have highest priority.
    if str(args.image).strip():
        paths.image_path = Path(args.image).expanduser()
    if str(args.prefix).strip():
        paths.prefix = str(args.prefix).strip()
    if str(args.out_dir).strip():
        paths.out_dir = Path(args.out_dir).expanduser()
    if str(args.debug_dir).strip():
        paths.debug_dir = Path(args.debug_dir).expanduser()
    if bool(args.quiet):
        log_fn = lambda _msg: None
    else:
        # Current default behavior is verbose-style logging; keep backward compatibility.
        log_fn = _log
    workflow = StoryboardWorkflow(paths=paths, options=options, log=log_fn, retry_matrix=retry)
    workflow.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
