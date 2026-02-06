from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

import cv2
import numpy as np
from psd_tools import PSDImage

# Allow running as `uv run python scripts/run_stage1.py ...`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comic_splitter.stage1.splitter import Stage1Config, StructureSplitter

# Edit these defaults for local testing (absolute path recommended).
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage1 structure splitter on one image")
    parser.add_argument("--image", default=DEFAULT_IMAGE_PATH, help="Input image path")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument(
        "--debug-dir",
        default=DEFAULT_DEBUG_DIR,
        help="Debug output directory",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help="Output file prefix",
    )
    parser.add_argument(
        "--no-hardline",
        action="store_true",
        help="Disable hardline detector",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.image:
        raise ValueError("Please set DEFAULT_IMAGE_PATH in scripts/run_stage1.py or pass --image")

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    out_dir = Path(args.out_dir)
    debug_dir = Path(args.debug_dir)
    prefix = args.prefix or image_path.stem

    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    bgr = _load_image(image_path)

    cfg = Stage1Config(enable_hardline=not args.no_hardline)
    splitter = StructureSplitter(cfg)
    bands = splitter.split(bgr, debug_out_dir=str(debug_dir), debug_prefix=prefix)

    bands_json = [asdict(b) for b in bands]
    output_path = out_dir / f"{prefix}_bands.json"
    output_path.write_text(json.dumps(bands_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"image: {image_path}")
    print(f"bands: {len(bands)}")
    print(f"bands_json: {output_path}")
    print(f"debug: {debug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
