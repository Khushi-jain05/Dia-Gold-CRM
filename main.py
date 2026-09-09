"""Dia Gold CRM - application entry point.

Run:  python main.py
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from diagold import APP_NAME
from diagold.db.session import init_db
from diagold.ui.login import LoginDialog
from diagold.ui.main_window import MainWindow
from diagold.ui.style import APP_QSS


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Dia Gold")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)

    init_db()

    while True:
        login = LoginDialog()
        if login.exec() != LoginDialog.DialogCode.Accepted or login.current_user is None:
            return 0

        window = MainWindow(login.current_user)
        window.show()
        app.exec()

        if not window._relogin_requested():
            return 0
        # else: loop back to the login screen


if __name__ == "__main__":
    sys.exit(main())
