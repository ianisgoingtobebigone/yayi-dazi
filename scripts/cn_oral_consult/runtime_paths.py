from __future__ import annotations

from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
PROJECT_DATA = MODULE_DIR.parent / "data"
BUNDLED_DATA = MODULE_DIR.parent.parent / "references" / "runtime-data"
DATA_DIR = BUNDLED_DATA if BUNDLED_DATA.is_dir() else PROJECT_DATA


def data_path(name: str) -> Path:
    path = DATA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return path
