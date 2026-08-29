"""Login dialog - the 'Software Start Process (ID / Password)' screen."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from diagold import APP_NAME, __version__
from diagold.db.session import SessionLocal
from diagold.services.auth import AuthError, CurrentUser, authenticate
from diagold.ui.style import GOLD, INK


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user: CurrentUser | None = None
        self.setWindowTitle(f"{APP_NAME} — Login")
        self.setFixedSize(400, 468)
        self.setStyleSheet(f"QDialog {{ background: {INK}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 30, 36, 24)
        outer.setSpacing(0)

        diamond = QLabel("◆")
        diamond.setAlignment(Qt.AlignmentFlag.AlignCenter)
        diamond.setStyleSheet(f"color: {GOLD}; font-size: 40px;")
        outer.addWidget(diamond)

        title = QLabel("Dia Gold CRM")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; font-size: 23px; font-weight: 800; padding-top: 6px;")
        outer.addWidget(title)

        subtitle = QLabel("JEWELLERY  MANUFACTURING  ERP")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {GOLD}; font-size: 10px; font-weight: 700; letter-spacing: 2px;")
        outer.addWidget(subtitle)
        outer.addSpacing(24)

        card = QFrame()
        card.setObjectName("Card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(22, 22, 22, 22)
        cv.setSpacing(12)

        self.username = QLineEdit()
        self.username.setPlaceholderText("User ID")
        self.username.setMinimumHeight(38)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Password")
        self.password.setMinimumHeight(38)
        cv.addWidget(QLabel("User ID"))
        cv.addWidget(self.username)
        cv.addWidget(QLabel("Password"))
        cv.addWidget(self.password)

        self.btn = QPushButton("Log In")
        self.btn.setObjectName("Primary")
        self.btn.setMinimumHeight(40)
        self.btn.setDefault(True)
        self.btn.clicked.connect(self._attempt)
        cv.addSpacing(4)
        cv.addWidget(self.btn)
        outer.addWidget(card)

        hint = QLabel("First run — <b style='color:#fff'>admin</b> / <b style='color:#fff'>admin</b>")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #8A8F9C; font-size: 11px; padding-top: 12px;")
        outer.addWidget(hint)

        outer.addStretch(1)
        version = QLabel(f"v{__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #5A5E6B; font-size: 10px;")
        outer.addWidget(version)

        self.password.returnPressed.connect(self._attempt)
        self.username.returnPressed.connect(lambda: self.password.setFocus())

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
