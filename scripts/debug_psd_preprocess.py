from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comic_splitter.psd_preprocess import preprocess_psd_for_panels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug PSD preprocess (text/textbox layer removal).")
    parser.add_argument("--image", required=True, help="Input PSD/PSB file path")
    parser.add_argument("--prefix", default="debug-pre", help="Output prefix")
    parser.add_argument("--out-dir", default=str(ROOT / "output"), help="Output directory")

    ocr_group = parser.add_mutually_exclusive_group()
    ocr_group.add_argument(
        "--with-ocr",
        dest="with_ocr",
        action="store_true",
        help="Enable OCR upload+recognition (default).",
    )
    ocr_group.add_argument(
        "--no-ocr",
        dest="with_ocr",
        action="store_false",
        help="Disable OCR (local debug only).",
    )
    parser.set_defaults(with_ocr=True)

    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="Do not fail when OCR is unavailable/degraded.",
    )
    parser.add_argument(
        "--enable-mask-inpaint",
        action="store_true",
        help="Enable OCR-mask inpaint fallback after layer removal.",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=8,
        help="Heartbeat seconds while processing (default: 8).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = Path(args.image).expanduser()
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")
    if image_path.suffix.lower() not in {".psd", ".psb"}:
        raise ValueError("debug_psd_preprocess only supports PSD/PSB input")

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ["VOLC_OCR_ENABLE"] = "1" if args.with_ocr else "0"

    stop_event = threading.Event()

    def _heartbeat() -> None:
        start = time.perf_counter()
        interval = max(3, int(args.progress_interval))
        while not stop_event.wait(interval):
            elapsed = int(time.perf_counter() - start)
            print(f"[progress] preprocess running... {elapsed}s", flush=True)

    print("[progress] preprocess start", flush=True)
    t0 = time.perf_counter()
    th = threading.Thread(target=_heartbeat, daemon=True)
    th.start()
    try:
        result = preprocess_psd_for_panels(
            image_path=image_path,
            out_dir=out_dir,
            prefix=args.prefix,
            enable_mask_inpaint=bool(args.enable_mask_inpaint),
        )
    finally:
        stop_event.set()
        th.join(timeout=0.2)
    elapsed = time.perf_counter() - t0
    print(f"[progress] preprocess done in {elapsed:.2f}s", flush=True)

    if args.with_ocr and not args.allow_degraded and result.ocr_status not in {"ok", "ok_empty"}:
        raise RuntimeError(
            f"OCR required but status={result.ocr_status}, reason={result.ocr_degraded_reason or '<empty>'}"
        )

    print(f"image={image_path}")
    print(f"ocr_status={result.ocr_status}")
    print(f"ocr_request_id={result.ocr_request_id}")
    print(f"upload_latency_ms={result.upload_latency_ms}")
    print(f"ocr_latency_ms={result.ocr_latency_ms}")
    print(f"text_count={len(result.texts)}")
    print(f"textbox_layer_ids={result.textbox_layer_ids}")
    print(f"raster_text_layer_ids={result.raster_text_layer_ids}")
    print(f"removed_layer_ids={result.removed_layer_ids}")
    print(f"clean_image={result.art_clean_path}")
    print(f"texts_merged={result.texts_merged_path}")
    print(f"text_canvas_map={result.text_canvas_map_path}")
    print(f"textbox_ranking={result.textbox_ranking_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
