from __future__ import annotations

from pathlib import Path


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def ensure_file_exists(path: str | Path) -> Path:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return p
