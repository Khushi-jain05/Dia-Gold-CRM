"""Order ▸ Shipping Details dialog (12 Oct video, order 1680)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QGridLayout, QLineEdit,
    QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget,
)

from diagold.db.models import Order
from diagold.db.session import SessionLocal
from diagold.services import order_shipping as OS


class ShippingDetailsDialog(QDialog):
    """Despatch, Order, Buyer's / Consignee details and Export, with Fetch
    Dept and Fetch Last Dtls, as the legacy order's dialog."""

    def __init__(self, order_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.order_id = order_id
        with SessionLocal() as s:
            o = s.get(Order, order_id)
            self.setWindowTitle(f"Shipping Details — Order {o.order_no}")
            values = OS.get(o)
            tracking = o.tracking_no
        self.setMinimumWidth(820)
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        self.editors: dict[str, QLineEdit | QPlainTextEdit] = {}
        self.tracking = QLineEdit(tracking)
        self.tracking.setObjectName("tracking_no")
        boxes: dict[str, QFormLayout] = {}
        place = {"Despatch": (0, 0), "Order": (0, 1), "Buyer's details": (1, 0),
                 "Consignee details": (1, 1), "Export": (2, 0)}
        for section, key, label, multi in OS.FIELDS:
            if section not in boxes:
                box = QGroupBox(section)
                boxes[section] = QFormLayout(box)
                r, c = place[section]
                grid.addWidget(box, r, c, 1, 2 if section == "Export" else 1)
                if section == "Despatch":
                    boxes[section].addRow("Tracking No", self.tracking)
            if multi:
                ed = QPlainTextEdit(values[key])
                ed.setFixedHeight(64)
            else:
                ed = QLineEdit(values[key])
            ed.setObjectName(key)
            self.editors[key] = ed
            boxes[section].addRow(label, ed)
        lay.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        b_dept = buttons.addButton("Fetch Dept", QDialogButtonBox.ButtonRole.ActionRole)
        b_dept.setToolTip("Fill Buyer's / Consignee details from the customer's account "
                          "(name, address, GSTIN, phone)")
        b_last = buttons.addButton("Fetch Last Dtls", QDialogButtonBox.ButtonRole.ActionRole)
        b_last.setToolTip("Copy the details of this customer's last order")
        b_dept.clicked.connect(self._fetch_dept)
        b_last.clicked.connect(self._fetch_last)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {k: (e.toPlainText() if isinstance(e, QPlainTextEdit) else e.text())
                for k, e in self.editors.items()}

    def _fill(self, data: dict[str, str]) -> None:
        for k, v in data.items():
            e = self.editors.get(k)
            if e is None:
                continue
            if isinstance(e, QPlainTextEdit):
                e.setPlainText(v)
            else:
                e.setText(v)

    def _fetch_dept(self) -> None:
        with SessionLocal() as s:
            data = OS.account_details(s, s.get(Order, self.order_id))
        if not data:
            QMessageBox.information(self, "Fetch Dept", "This order has no customer account.")
            return
        self._fill(data)

    def _fetch_last(self) -> None:
        with SessionLocal() as s:
            data = OS.last_details(s, s.get(Order, self.order_id))
        if data is None:
            QMessageBox.information(self, "Fetch Last Dtls",
                                    "No earlier order of this customer has shipping details.")
            return
        self._fill(data)

    def _save(self) -> None:
        with SessionLocal() as s:
            o = s.get(Order, self.order_id)
            o.tracking_no = self.tracking.text().strip()
            OS.save(s, o, self.values())
            s.commit()
        self.accept()


def open_for(parent: QWidget, order_id: int) -> bool:
    return ShippingDetailsDialog(order_id, parent).exec() == QDialog.DialogCode.Accepted
