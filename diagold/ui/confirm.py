"""The "Save? Yes / No" question the legacy system asks before every save.

The client's staff are used to it (seen on the MFG Ready Stock Transfer in the
28 Sept walkthrough, and asked for on the call), so every screen that writes a
record asks it through here. It can be switched off in Tools > Option.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from diagold.services import settings

CONFIRM_SAVE_FLAG = "ui.confirm_save"


def confirm_save(parent: QWidget | None, what: str = "") -> bool:
    """Ask before saving. Yes is the default, so Enter saves and Esc cancels."""
    if not settings.flag(CONFIRM_SAVE_FLAG, True):
        return True
    box = QMessageBox(parent)
    box.setWindowTitle("Save")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(f"Save {what}?" if what else "Save?")
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    box.setEscapeButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes
