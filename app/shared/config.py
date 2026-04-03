from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Picslit2"


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen_app():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(str(meipass)).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def runtime_data_root() -> Path:
    override = str(os.getenv("PICSLIT_APP_DATA_DIR", "")).strip()
    if override:
        return Path(override).expanduser().resolve()

    if not is_frozen_app():
        return resource_root()

    if sys.platform == "win32":
        local_app_data = str(os.getenv("LOCALAPPDATA", "")).strip()
        base = Path(local_app_data).expanduser() if local_app_data else Path.home() / "AppData" / "Local"
        return (base / APP_NAME).resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_NAME).resolve()

    xdg_data_home = str(os.getenv("XDG_DATA_HOME", "")).strip()
    if xdg_data_home:
        base = Path(xdg_data_home).expanduser()
    else:
        base = Path.home() / ".local" / "share"
    return (base / APP_NAME).resolve()


def load_runtime_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    data_env = runtime_data_root() / ".env"
    resource_env = resource_root() / ".env"
    seen: set[Path] = set()
    for candidate in (data_env, resource_env):
        resolved = candidate.resolve()
        if resolved in seen or not resolved.exists():
            continue
        load_dotenv(dotenv_path=resolved, override=False)
        seen.add(resolved)


def runtime_env_path() -> Path:
    return runtime_data_root() / ".env"


def project_root() -> Path:
    return resource_root()


def config_dir(root: Path | None = None) -> Path:
    base = root or resource_root()
    return Path(base) / "config"


def output_dir(root: Path | None = None) -> Path:
    base = root or runtime_data_root()
    return Path(base) / "output"


def frontend_dir(root: Path | None = None) -> Path:
    base = root or resource_root()
    return Path(base) / "frontend"


def ui_state_dir(root: Path | None = None) -> Path:
    return output_dir(root) / "_ui_state"


def workbench_ui_dir(root: Path | None = None) -> Path:
    return ui_state_dir(root) / "_workbench"


def workbench_ui_state_path(root: Path | None = None) -> Path:
    return workbench_ui_dir(root) / "ui_state.json"


def upload_dir(root: Path | None = None) -> Path:
    return output_dir(root) / "_uploads"


def storyboard_config_path(root: Path | None = None) -> Path:
    return config_dir(root) / "storyboard.toml"
