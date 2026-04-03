# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
CONFIG_ROOT = PROJECT_ROOT / "config"


def optional_collect_submodules(package_name: str) -> list[str]:
    try:
        return collect_submodules(package_name)
    except Exception:
        return []


def optional_collect_data_files(package_name: str) -> list[tuple[str, str]]:
    try:
        return collect_data_files(package_name)
    except Exception:
        return []


datas = [
    (str(FRONTEND_ROOT / "index.html"), "frontend"),
    (str(FRONTEND_ROOT / "main.js"), "frontend"),
    (str(FRONTEND_ROOT / "style.css"), "frontend"),
    (str(FRONTEND_ROOT / "src"), "frontend/src"),
    (str(CONFIG_ROOT), "config"),
]

for optional_file in (".env.example", "README.md"):
    candidate = PROJECT_ROOT / optional_file
    if candidate.exists():
        datas.append((str(candidate), "."))

hiddenimports = []
for package_name in (
    "PIL",
    "cv2",
    "numpy",
    "psd_tools",
    "skimage",
    "volcengine",
    "volcenginesdkarkruntime",
    "webview",
):
    hiddenimports.extend(optional_collect_submodules(package_name))

for package_name in ("psd_tools", "skimage", "PIL"):
    datas.extend(optional_collect_data_files(package_name))


a = Analysis(
    [str(PROJECT_ROOT / "scripts" / "picslit_desktop.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Picslit2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Picslit2",
)
