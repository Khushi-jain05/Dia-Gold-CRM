"""Main application window - menu bar mirrors the client's design workbook."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMdiArea,
    QMdiSubWindow,
    QMainWindow,
    QMessageBox,
    QDialogButtonBox,
)

from diagold import APP_NAME
from diagold.config import COMPANY_DISPLAY_NAME, DB_PATH
from diagold.db.session import SessionLocal
from diagold.menu import MENU
from diagold.services.auth import AuthError, CurrentUser, change_password
from diagold.ui.registry import build_widget, has_real_screen

_WINDOW_ACTIONS = {"window.cascade", "window.tile", "window.close_all"}


class MainWindow(QMainWindow):
    def __init__(self, user: CurrentUser):
        super().__init__()
        self.user = user
        self._open: dict[str, QMdiSubWindow] = {}

        self.setWindowTitle(f"{APP_NAME} — {COMPANY_DISPLAY_NAME}")
        self.resize(1180, 760)

        self.mdi = QMdiArea()
        self.mdi.setViewMode(QMdiArea.ViewMode.TabbedView)
        self.mdi.setTabsClosable(True)
        self.mdi.setTabsMovable(True)
        self.setCentralWidget(self.mdi)

        self._build_menu()
        self._build_statusbar()

    # -- menu ----------------------------------------------------------
    def _build_menu(self) -> None:
        bar = self.menuBar()
        for group in MENU:
            menu = bar.addMenu(group.label)
            for item in group.items:
                action = QAction(item.label, self)
                action.setData(item.key)
                if item.key in _WINDOW_ACTIONS:
                    action.triggered.connect(lambda _=False, k=item.key: self._window_action(k))
                elif item.key == "tools.change_password":
                    action.triggered.connect(self._change_password)
                else:
                    action.triggered.connect(
                        lambda _=False, k=item.key, lbl=item.label: self._open_screen(k, lbl)
                    )
                    if not self.user.can_view(item.key):
                        action.setEnabled(False)
                    elif not has_real_screen(item.key):
                        action.setText(f"{item.label}  —  (coming soon)")
                menu.addAction(action)

            if group.key == "master":
                menu.addSeparator()
                logout = QAction("Log Out", self)
                logout.triggered.connect(self._logout)
                menu.addAction(logout)
                quit_action = QAction("Exit", self)
                quit_action.setShortcut(QKeySequence.StandardKey.Quit)
                quit_action.triggered.connect(self.close)
                menu.addAction(quit_action)

    def _build_statusbar(self) -> None:
        role = self.user.role_name or ("Superuser" if self.user.is_superuser else "No role")
        self.statusBar().showMessage(
            f"Signed in as {self.user.full_name} ({self.user.username}) · {role} · DB: {DB_PATH}"
        )

    # -- actions -----------------------------------------------------
    def _open_screen(self, menu_key: str, label: str) -> None:
        if not self.user.can_view(menu_key):
            QMessageBox.warning(self, "Access denied",
                                f"You do not have permission to open '{label}'.")
            return
        if menu_key in self._open:
            sub = self._open[menu_key]
            self.mdi.setActiveSubWindow(sub)
            return
        try:
            widget = build_widget(menu_key, self.user)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not open '{label}':\n{exc}")
            return
        sub = self.mdi.addSubWindow(widget)
        sub.setWindowTitle(widget.windowTitle() or label)
        sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        sub.destroyed.connect(lambda *_: self._open.pop(menu_key, None))
        self._open[menu_key] = sub
        widget.show()
        sub.showMaximized()

    def _window_action(self, key: str) -> None:
        if key == "window.cascade":
            self.mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
            self.mdi.cascadeSubWindows()
        elif key == "window.tile":
            self.mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
            self.mdi.tileSubWindows()
        elif key == "window.close_all":
            self.mdi.closeAllSubWindows()

    def _change_password(self) -> None:
        dlg = _ChangePasswordDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        with SessionLocal() as session:
            try:
                change_password(session, self.user.id, dlg.old_pw(), dlg.new_pw())
            except AuthError as exc:
                QMessageBox.critical(self, "Change Password", str(exc))
                return
        QMessageBox.information(self, "Change Password", "Password updated.")

    def _logout(self) -> None:
        self._relogin = True
        self.close()

    def _relogin_requested(self) -> bool:
        return getattr(self, "_relogin", False)


class _ChangePasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Password")
        layout = QFormLayout(self)
        self._old = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self._new = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self._confirm = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        layout.addRow("Current Password", self._old)
        layout.addRow("New Password", self._new)
        layout.addRow("Confirm New Password", self._confirm)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate(self) -> None:
        if self._new.text() != self._confirm.text():
            QMessageBox.warning(self, "Change Password", "New passwords do not match.")
            return
        self.accept()

    def old_pw(self) -> str:
        return self._old.text()

    def new_pw(self) -> str:
        return self._new.text()
