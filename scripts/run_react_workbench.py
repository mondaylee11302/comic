from __future__ import annotations

import argparse
from pathlib import Path
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comic_splitter.ui import create_react_workbench_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch React storyboard workbench (FastAPI + static React UI).")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=7860, help="Bind port")
    parser.add_argument("--out-dir", default=str(ROOT / "output"), help="Default output directory")
    parser.add_argument("--debug-dir", default=str(ROOT / "output" / "debug"), help="Default debug directory")
    parser.add_argument("--static-dir", default=str(ROOT / "web" / "react"), help="React static directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_react_workbench_app(
        static_dir=Path(args.static_dir).expanduser(),
        default_out_dir=Path(args.out_dir).expanduser(),
        default_debug_dir=Path(args.debug_dir).expanduser(),
    )
    uvicorn.run(app, host=args.host, port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
