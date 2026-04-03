from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "packaging" / "windows" / "Picslit2.spec"


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows 桌面包需要在 Windows 环境下构建。")


def _clean_build_artifacts() -> None:
    for rel in ("build", "dist"):
        target = ROOT / rel
        if target.exists():
            shutil.rmtree(target)


def _run_pyinstaller() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC_PATH)]
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> None:
    _require_windows()
    if not SPEC_PATH.exists():
        raise SystemExit(f"PyInstaller spec not found: {SPEC_PATH}")
    _clean_build_artifacts()
    _run_pyinstaller()
    print(f"Build completed: {ROOT / 'dist' / 'Picslit2'}")


if __name__ == "__main__":
    main()
