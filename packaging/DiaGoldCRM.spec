# PyInstaller spec - builds a standalone Dia Gold CRM app for macOS and Windows.
# Usage:  pyinstaller packaging/DiaGoldCRM.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent

hiddenimports = (
    collect_submodules("diagold")
    + collect_submodules("sqlalchemy")
)

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
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
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
