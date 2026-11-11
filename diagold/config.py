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


def _server_ini() -> Path | None:
    """The shared-server settings file, if this install has one.

    ``server.ini`` sits next to DiaGoldCRM.exe (as Path.ini does beside the
    legacy JewelleryERP.exe), or in the data folder. DIAGOLD_SERVER_INI names
    another file - the test suites point it at a scratch server.
    """
    override = os.environ.get("DIAGOLD_SERVER_INI")
    if override:
        return Path(override).expanduser()
    here = Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent.parent
    for p in (here / "server.ini", DATA_DIR / "server.ini"):
        if p.is_file():
            return p
    return None


def _database_url():
    """SQL Server from server.ini when there is one, else the local SQLite file.

    server.ini (any of the keys may be missing except Server and DatabaseName)::

        [Database]
        Server=SERVER2\\ERP        ; host, or host\\instance, as in Path.ini
        Port=                       ; only for a fixed port instead of the instance name
        DatabaseName=DiaGoldCRM
        UID=diagold_app
        PWD=...
    """
    ini = _server_ini()
    if ini is None or os.environ.get("DIAGOLD_LOCAL_DB") == "1":
        return f"sqlite:///{DB_PATH}"
    import configparser

    from sqlalchemy.engine import URL
    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cp.optionxform = str
    cp.read(ini, encoding="utf-8-sig")
    db = {k.lower(): v.strip().rstrip(";").strip() for k, v in cp["Database"].items()}
    return URL.create(
        "mssql+pymssql",
        username=db.get("uid") or None, password=db.get("pwd") or None,
        host=db["server"], port=int(db["port"]) if db.get("port") else None,
        database=db["databasename"], query={"charset": "utf8", "tds_version": "7.4"})


DATABASE_URL = _database_url()
IS_SERVER: bool = not str(DATABASE_URL).startswith("sqlite")
# What the status bar and error messages call the database.
DB_LABEL: str = (f"{DATABASE_URL.host}/{DATABASE_URL.database}" if IS_SERVER
                 else str(DB_PATH))

# Toggle SQLAlchemy echo with DIAGOLD_SQL_ECHO=1
SQL_ECHO: bool = os.environ.get("DIAGOLD_SQL_ECHO", "") == "1"

COMPANY_DISPLAY_NAME = "Dia Gold"
