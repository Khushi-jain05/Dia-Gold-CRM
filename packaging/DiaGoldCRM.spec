# PyInstaller spec - builds a standalone Dia Gold CRM app for macOS and Windows.
# Usage:  pyinstaller packaging/DiaGoldCRM.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(PROJECT_ROOT))


def _all_diagold_modules() -> list[str]:
    """Every module under diagold/, read from the files - collect_submodules
    alone found nothing on the build machine (diagold was not importable
    there), so screens loaded by name were left out of the exe (9 Oct:
    Advance Options, Backup, Audit Log, Client Wise Price "not found")."""
    base = PROJECT_ROOT / "diagold"
    mods = []
    for f in base.rglob("*.py"):
        parts = f.relative_to(PROJECT_ROOT).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        mods.append(".".join(parts))
    return sorted(mods)


hiddenimports = (
    _all_diagold_modules()
    + collect_submodules("diagold")
    + collect_submodules("sqlalchemy")
    + collect_submodules("openpyxl")      # Excel exports / invoice
    + ["PIL.Image", "PIL.PngImagePlugin", "PIL.JpegImagePlugin"]   # photos in Excel
)

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[(str(PROJECT_ROOT / "diagold" / "data"), "diagold/data")],
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DiaGoldCRM",
    console=False,           # windowed / GUI app - no terminal
    disable_windowed_traceback=False,
    argv_emulation=True,     # macOS: handle file-open events
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="DiaGoldCRM",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DiaGoldCRM.app",
        icon=None,
        bundle_identifier="works.iterativetech.diagoldcrm",
        info_plist={
            "CFBundleShortVersionString": "0.8.4",
            "CFBundleVersion": "0.8.4",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
