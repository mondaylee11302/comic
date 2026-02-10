from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comic_splitter.workflow import (
    AgentRetryMatrix,
    PanelScriptOptions,
    PanelScriptPaths,
    PanelScriptWorkflow,
    load_panel_script_config,
)


DEFAULT_PREFIX = "storyboard_001"
DEFAULT_OUT_DIR = str(ROOT / "output")
DEFAULT_CONFIG_PATH = ROOT / "config" / "panel_script.toml"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=ROOT / ".env", override=False)
    except Exception:
        pass


def _parse_csv(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate storyboard script for one selected panel.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="TOML config path")
    parser.add_argument("--prefix", default="", help="Optional override prefix")
    parser.add_argument("--out-dir", default="", help="Optional override output directory")
    parser.add_argument("--panel-id", default="", help="Optional override panel id like panel_001")
    parser.add_argument("--panel-image", default="", help="Optional explicit panel image path")
    parser.add_argument("--panel-text", default="", help="Optional explicit panel text jsonl path")
    parser.add_argument("--text-ids", default="", help="Comma-separated text ids, e.g. text_001,text_003")
    parser.add_argument("--text-contains", default="", help="Comma-separated substrings for text filtering")
    parser.add_argument(
        "--goal",
        default="",
        help="User intent for script generation",
    )
    parser.add_argument("--output-json", default="", help="Optional output json path")
    parser.add_argument("--output-md", default="", help="Optional output markdown path")
    parser.add_argument("--temperature", type=float, default=None, help="Optional override LLM temperature")
    parser.add_argument("--max-tokens", type=int, default=None, help="Optional override LLM max tokens")
    parser.add_argument("--request-timeout", type=float, default=None, help="Optional override request timeout seconds")
    parser.add_argument("--model-retries", type=int, default=None, help="Optional override retries per mode")
    parser.add_argument("--heartbeat-sec", type=int, default=None, help="Optional override heartbeat interval")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose model logs")
    parser.add_argument("--no-local-fallback", action="store_true", help="Fail when model unavailable")
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()

    default_paths = PanelScriptPaths(
        out_dir=Path(DEFAULT_OUT_DIR).expanduser(),
        prefix=str(DEFAULT_PREFIX),
        panel_id="panel_001",
        panel_image_path=None,
        panel_text_path=None,
        output_json_path=None,
        output_md_path=None,
    )
    default_options = PanelScriptOptions(
        selected_text_ids=[],
        selected_text_contains=[],
        goal="保留原文语义并增强戏剧性，输出可直接给创作团队使用的分镜脚本",
        temperature=0.35,
        max_tokens=1200,
        request_timeout_sec=60.0,
        model_retries=2,
        heartbeat_interval_sec=8,
        allow_local_fallback=True,
    )
    default_retry = AgentRetryMatrix()
    config_path = Path(args.config).expanduser() if str(args.config).strip() else None
    paths, options, retry = load_panel_script_config(
        config_path=config_path,
        default_paths=default_paths,
        default_options=default_options,
        default_retry=default_retry,
    )
    # CLI explicit args have highest priority.
    if str(args.out_dir).strip():
        paths.out_dir = Path(args.out_dir).expanduser()
    if str(args.prefix).strip():
        paths.prefix = str(args.prefix).strip()
    if str(args.panel_id).strip():
        paths.panel_id = str(args.panel_id).strip()
    if str(args.panel_image).strip():
        paths.panel_image_path = Path(args.panel_image).expanduser()
    if str(args.panel_text).strip():
        paths.panel_text_path = Path(args.panel_text).expanduser()
    if str(args.output_json).strip():
        paths.output_json_path = Path(args.output_json).expanduser()
    if str(args.output_md).strip():
        paths.output_md_path = Path(args.output_md).expanduser()
    if str(args.text_ids).strip():
        options.selected_text_ids = _parse_csv(str(args.text_ids))
    if str(args.text_contains).strip():
        options.selected_text_contains = _parse_csv(str(args.text_contains))
    if str(args.goal).strip():
        options.goal = str(args.goal)
    if args.temperature is not None:
        options.temperature = float(args.temperature)
    if args.max_tokens is not None:
        options.max_tokens = int(args.max_tokens)
    if args.request_timeout is not None:
        options.request_timeout_sec = float(args.request_timeout)
    if args.model_retries is not None:
        options.model_retries = max(1, int(args.model_retries))
    if args.heartbeat_sec is not None:
        options.heartbeat_interval_sec = max(3, int(args.heartbeat_sec))
    if bool(args.no_local_fallback):
        options.allow_local_fallback = False

    def _log(msg: str) -> None:
        if args.verbose:
            print(f"[script-agent] {msg}", flush=True)

    workflow = PanelScriptWorkflow(paths=paths, options=options, log=_log, retry_matrix=retry)
    workflow.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
