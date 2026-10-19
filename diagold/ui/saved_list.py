"""Saved Vouchers: the list under a voucher-entry screen (19 Oct testing).

The entry screens open on a new, empty voucher as the legacy ones do; this
panel shows what has already been saved on that screen - date range, the
voucher's figures, double-click (or Open) loads it into the form above.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)


def _fy() -> tuple[date, date]:
    t = date.today()
    start = date(t.year if t.month >= 4 else t.year - 1, 4, 1)
    return start, date(start.year + 1, 3, 31)


def _qd(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


class SavedVouchersPanel(QGroupBox):
    """``loader(date_from, date_to) -> rows`` (dicts carrying ``_id``) in the
    order to show; ``columns`` = [(key, header)]; ``on_open(_id)``."""

    def __init__(self, title: str, columns: list[tuple[str, str]],
                 loader: Callable[[date, date], list[dict[str, Any]]],
                 on_open: Callable[[Any], None], parent=None, height: int = 190):
        super().__init__(f"Saved {title} — double-click to open", parent)
        self.columns, self.loader, self.on_open = columns, loader, on_open
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        bar = QHBoxLayout()
        a, b = _fy()
        self.d_from, self.d_to = QDateEdit(_qd(a)), QDateEdit(_qd(b))
        for w in (self.d_from, self.d_to):
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd-MM-yyyy")
            w.dateChanged.connect(lambda _d: self.reload())
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        b_open = QPushButton("Open")
        b_open.clicked.connect(self._open_selected)
        b_ref = QPushButton("Refresh")
        b_ref.clicked.connect(self.reload)
        for w in (QLabel("From"), self.d_from, QLabel("To"), self.d_to, self.count):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(b_open)
        bar.addWidget(b_ref)
        lay.addLayout(bar)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([h for _k, h in columns])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._open(r))
        lay.addWidget(self.table)
        self.setMaximumHeight(height)
        self.rows: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        a = self.d_from.date().toPython()
        b = self.d_to.date().toPython()
        try:
            self.rows = self.loader(a, b)
        except Exception as exc:  # noqa: BLE001 - a list must never break the screen
            self.rows = []
            self.count.setText(f"could not load: {exc}")
            return
        self.table.setRowCount(0)
        for row in self.rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, (k, _h) in enumerate(self.columns):
                v = row.get(k)
                if isinstance(v, date):
                    v = v.strftime("%d-%m-%Y")
                elif v is None:
                    v = ""
                it = QTableWidgetItem(f"{v:,.2f}" if isinstance(v, float) else str(v))
                if k in ("amount", "total", "pcs", "lines", "gross", "net", "jobs"):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()
        self.count.setText(f"{len(self.rows)} saved")

    def _open_selected(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if sel:
            self._open(sel[0].row())

    def _open(self, r: int) -> None:
        if 0 <= r < len(self.rows):
            self.on_open(self.rows[r]["_id"])
