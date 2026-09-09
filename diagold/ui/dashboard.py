"""Dashboard / home screen shown when the app opens."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from diagold.db.models import (
    Account,
    Currency,
    Metal,
    ProductSku,
    StoneInfo,
    StoneSku,
    User,
)
from diagold.db.session import SessionLocal


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


class _Card(QFrame):
    def __init__(self, label: str, value: str):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        v = QLabel(value)
        v.setObjectName("CardValue")
        lbl = QLabel(label.upper())
        lbl.setObjectName("CardLabel")
        lay.addWidget(v)
        lay.addWidget(lbl)


class DashboardWidget(QWidget):
    open_requested = Signal(str)  # menu key

    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Dashboard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        hour = datetime.now().hour
        greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        title = QLabel(f"{greet}, {self.user.full_name.split()[0]}")
        title.setObjectName("H1")
        outer.addWidget(title)

        sub = QLabel("Dia Gold CRM — jewellery manufacturing, end to end.")
        sub.setObjectName("Muted")
        outer.addWidget(sub)

        # stat cards
        grid = QGridLayout()
        grid.setSpacing(14)
        with SessionLocal() as s:
            stats = [
                ("Product SKUs", _count(s, ProductSku), "sku.product_sku_master"),
                ("Stone SKUs", _count(s, StoneSku), "sku.stone_sku"),
                ("Accounts", _count(s, Account), "master.account"),
                ("Metals", _count(s, Metal), "master.metal"),
                ("Stone Types", _count(s, StoneInfo), "master.stone_info"),
                ("Currencies", _count(s, Currency), "master.currency"),
                ("Users", _count(s, User), "master.user_right"),
            ]
        for i, (label, value, key) in enumerate(stats):
            card = _Card(label, str(value))
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda _e, k=key: self.open_requested.emit(k)
            grid.addWidget(card, i // 4, i % 4)
        outer.addLayout(grid)

        # quick actions
        qa_title = QLabel("QUICK ACTIONS")
        qa_title.setObjectName("CardLabel")
        outer.addSpacing(6)
        outer.addWidget(qa_title)

        row = QHBoxLayout()
        row.setSpacing(10)
        for text, key, primary in [
            ("+ New Product SKU", "sku.product_sku_master", True),
            ("+ New Account", "master.account", False),
            ("+ New Stone SKU", "sku.stone_sku", False),
            ("Manage Users && Rights", "master.user_right", False),
        ]:
            b = QPushButton(text)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(lambda _=False, k=key: self.open_requested.emit(k))
            row.addWidget(b)
        row.addStretch(1)
        outer.addLayout(row)

        outer.addStretch(1)

        note = QLabel(
            "This build covers the Master and SKU modules. Quotation, MRP, Production "
            "Planning, Manufacturing, Purchase, Inventory, Sale, Account and Reports are "
            "in the navigation and will be built next."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        outer.addWidget(note)
