"""Login dialog - the 'Software Start Process (ID / Password)' screen."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from diagold import APP_NAME, __version__
from diagold.db.session import SessionLocal
from diagold.services.auth import AuthError, CurrentUser, authenticate


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user: CurrentUser | None = None
        self.setWindowTitle(f"{APP_NAME} — Login")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Jewellery Manufacturing ERP")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        form = QFormLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("User ID")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Password")
        form.addRow("User ID", self.username)
        form.addRow("Password", self.password)
        layout.addLayout(form)

        self.btn = QPushButton("Log In")
        self.btn.setDefault(True)
        self.btn.clicked.connect(self._attempt)
        layout.addWidget(self.btn)

        hint = QLabel("First run: user <b>admin</b> / password <b>admin</b>")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        version = QLabel(f"v{__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignRight)
        version.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(version)

        self.password.returnPressed.connect(self._attempt)

    def _attempt(self) -> None:
        uid = self.username.text().strip()
        pwd = self.password.text()
        if not uid or not pwd:
            QMessageBox.warning(self, "Login", "Enter both User ID and Password.")
            return
        with SessionLocal() as session:
            try:
                self.current_user = authenticate(session, uid, pwd)
            except AuthError as exc:
                QMessageBox.critical(self, "Login failed", str(exc))
                self.password.clear()
                self.password.setFocus()
                return
        self.accept()
