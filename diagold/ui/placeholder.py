"""Placeholder screen for modules that are scaffolded but not yet built."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderWidget(QWidget):
    def __init__(self, title: str, group_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel(
            f"“{group_label} › {title}” is part of the approved design and is\n"
            "scaffolded in the database, but its screen is not built yet.\n\n"
            "Master and SKU modules are fully functional in this build."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: gray;")

        layout.addWidget(heading)
        layout.addWidget(sub)
