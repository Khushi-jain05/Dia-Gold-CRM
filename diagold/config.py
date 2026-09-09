"""Application configuration and platform-aware paths."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _app_data_dir() -> Path:
    """Return a per-user writable directory for the database and settings.

    Works on both macOS and Windows without extra dependencies.
    """
    override = os.environ.get("DIAGOLD_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:  # linux / other - keep it usable for developers
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return base / "DiaGoldCRM"


DATA_DIR: Path = _app_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH: Path = DATA_DIR / "diagold.sqlite3"
DATABASE_URL: str = f"sqlite:///{DB_PATH}"

# Toggle SQLAlchemy echo with DIAGOLD_SQL_ECHO=1
SQL_ECHO: bool = os.environ.get("DIAGOLD_SQL_ECHO", "") == "1"

COMPANY_DISPLAY_NAME = "Dia Gold"
