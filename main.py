"""Dia Gold CRM - application entry point.

Run:  python main.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Testing on the demo database (Windows: "Open DEMO (testing).bat"):
#   DiaGoldCRM --demo            the demo data in ~/DiaGoldDemo, loaded on first run
#   DiaGoldCRM --demo --reset    throw the demo away and start it again
# Set before anything reads diagold.config, which fixes the data folder. The
# working database is never touched in demo mode.
DEMO = "--demo" in sys.argv
if DEMO:
    _demo_dir = Path.home() / "DiaGoldDemo"
    if "--reset" in sys.argv and _demo_dir.exists():
        shutil.rmtree(_demo_dir)
    os.environ["DIAGOLD_DATA_DIR"] = str(_demo_dir)

from PySide6.QtWidgets import QApplication, QMessageBox

from diagold import APP_NAME
from diagold.db.session import init_db
from diagold.ui.login import LoginDialog
from diagold.ui.main_window import MainWindow
from diagold.ui.style import APP_QSS, build_palette


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Dia Gold")
    app.setStyle("Fusion")
    app.setPalette(build_palette())   # before the sheet: the sheet wins where both speak
    app.setStyleSheet(APP_QSS)
    from diagold.ui.reports import wait_for_reports
    app.aboutToQuit.connect(wait_for_reports)   # never quit with a report still loading

    try:
        init_db()
        if DEMO:
            from diagold.db.session import SessionLocal
            from diagold.services.demo_data import load_demo
            with SessionLocal() as session:
                load_demo(session)      # idempotent: only the first run adds it
                session.commit()
    except Exception as exc:  # noqa: BLE001 - the user sees this, not a traceback
        from diagold.config import DB_PATH
        QMessageBox.critical(
            None, f"{APP_NAME} — could not open the data file",
            f"{exc}\n\nThe file is:\n{DB_PATH}\n\nNothing has been changed. Send "
            "this message to the developer; a copy of that file lets us fix it.")
        return 1

    while True:
        login = LoginDialog()
        if login.exec() != LoginDialog.DialogCode.Accepted or login.current_user is None:
            return 0

        window = MainWindow(login.current_user)
        if DEMO:
            window.setWindowTitle(window.windowTitle() + "  —  DEMO DATA (testing)")
        window.show()
        app.exec()

        if not window._relogin_requested():
            return 0
        # else: loop back to the login screen


if __name__ == "__main__":
    sys.exit(main())
