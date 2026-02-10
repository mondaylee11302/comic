from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import tomllib
from typing import Dict, Tuple

from comic_splitter.workflow.panel_script import PanelScriptOptions, PanelScriptPaths
from comic_splitter.workflow.runtime import AgentRetryMatrix
from comic_splitter.workflow.storyboard import StoryboardOptions, StoryboardPaths


def _read_toml(path: Path) -> Dict:
    with path.open("rb") as f:
        obj = tomllib.load(f)
    return dict(obj) if isinstance(obj, dict) else {}


def _merge_known_fields(defaults: Dict, overrides: Dict) -> Dict:
    out = dict(defaults)
    for k, v in (overrides or {}).items():
        if k in out:
            out[k] = v
    return out


def _build_retry_matrix(default: AgentRetryMatrix, retry_overrides: Dict) -> AgentRetryMatrix:
    base = asdict(default)
    merged = _merge_known_fields(base, retry_overrides or {})
    per = merged.get("per_agent_max_attempts", {})
    if not isinstance(per, dict):
        per = {}
    merged["per_agent_max_attempts"] = {str(k): int(v) for k, v in per.items()}
    return AgentRetryMatrix(**merged)


def load_storyboard_config(
    config_path: Path | None,
    default_paths: StoryboardPaths,
    default_options: StoryboardOptions,
    default_retry: AgentRetryMatrix | None = None,
) -> Tuple[StoryboardPaths, StoryboardOptions, AgentRetryMatrix]:
    retry_default = default_retry or AgentRetryMatrix()
    if config_path is None or not Path(config_path).exists():
        return default_paths, default_options, retry_default

    raw = _read_toml(Path(config_path))
    path_over = dict(raw.get("paths", {})) if isinstance(raw.get("paths", {}), dict) else {}
    opt_over = dict(raw.get("options", {})) if isinstance(raw.get("options", {}), dict) else {}
    retry_over = dict(raw.get("retry", {})) if isinstance(raw.get("retry", {}), dict) else {}

    paths_dict = _merge_known_fields(asdict(default_paths), path_over)
    options_dict = _merge_known_fields(asdict(default_options), opt_over)

    paths = StoryboardPaths(
        image_path=Path(str(paths_dict["image_path"])).expanduser(),
        out_dir=Path(str(paths_dict["out_dir"])).expanduser(),
        debug_dir=Path(str(paths_dict["debug_dir"])).expanduser(),
        prefix=str(paths_dict["prefix"]),
    )
    options = StoryboardOptions(**options_dict)
    retry = _build_retry_matrix(retry_default, retry_over)
    return paths, options, retry


def load_panel_script_config(
    config_path: Path | None,
    default_paths: PanelScriptPaths,
    default_options: PanelScriptOptions,
    default_retry: AgentRetryMatrix | None = None,
) -> Tuple[PanelScriptPaths, PanelScriptOptions, AgentRetryMatrix]:
    retry_default = default_retry or AgentRetryMatrix()
    if config_path is None or not Path(config_path).exists():
        return default_paths, default_options, retry_default

    raw = _read_toml(Path(config_path))
    path_over = dict(raw.get("paths", {})) if isinstance(raw.get("paths", {}), dict) else {}
    opt_over = dict(raw.get("options", {})) if isinstance(raw.get("options", {}), dict) else {}
    retry_over = dict(raw.get("retry", {})) if isinstance(raw.get("retry", {}), dict) else {}

    path_defaults = asdict(default_paths)
    merged_paths = _merge_known_fields(path_defaults, path_over)

    panel_image = str(merged_paths.get("panel_image_path") or "").strip()
    panel_text = str(merged_paths.get("panel_text_path") or "").strip()
    output_json = str(merged_paths.get("output_json_path") or "").strip()
    output_md = str(merged_paths.get("output_md_path") or "").strip()

    paths = PanelScriptPaths(
        out_dir=Path(str(merged_paths["out_dir"])).expanduser(),
        prefix=str(merged_paths["prefix"]),
        panel_id=str(merged_paths["panel_id"]),
        panel_image_path=Path(panel_image).expanduser() if panel_image else None,
        panel_text_path=Path(panel_text).expanduser() if panel_text else None,
        output_json_path=Path(output_json).expanduser() if output_json else None,
        output_md_path=Path(output_md).expanduser() if output_md else None,
    )

    option_defaults = asdict(default_options)
    merged_options = _merge_known_fields(option_defaults, opt_over)
    if not isinstance(merged_options.get("selected_text_ids"), list):
        merged_options["selected_text_ids"] = list(default_options.selected_text_ids)
    if not isinstance(merged_options.get("selected_text_contains"), list):
        merged_options["selected_text_contains"] = list(default_options.selected_text_contains)
    options = PanelScriptOptions(**merged_options)
    retry = _build_retry_matrix(retry_default, retry_over)
    return paths, options, retry

