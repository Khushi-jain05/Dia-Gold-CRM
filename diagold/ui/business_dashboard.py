"""Reports ▸ Business Dashboard (5 Oct §4.16, T-14): the client's Looker
pages from live ERP data - Department Pending, Daily Output, Daily Sale &
Return, Bills Due. Which tiles stay is for the client to confirm (C-04)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (QDateEdit, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from diagold.db.session import SessionLocal
from diagold.services import dashboard_data as DD
from diagold.ui.charts import BarChart, PieChart


def _tile(label: str, value: str) -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    a = QLabel(label)
    a.setObjectName("CardLabel")
    b = QLabel(value)
    b.setObjectName("CardValue")
    lay.addWidget(a)
    lay.addWidget(b)
    return f


def _fmt(v) -> str:
    if isinstance(v, Decimal):
        return f"{v:,.2f}" if v != v.to_integral_value() or abs(v) >= 1000 else f"{v:,.3f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def _table(headers: list[str], rows: list[list]) -> QTableWidget:
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            t.setItem(r, c, QTableWidgetItem(_fmt(v) if v is not None else ""))
    return t


class _Page(QWidget):
    open_report = Signal(str)

    def __init__(self, single_date: bool, report_key: str, report_label: str, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        today = QDate.currentDate()
        self.d0 = QDateEdit(today if single_date else QDate(today.year(), today.month(), 1))
        self.d1 = QDateEdit(today)
        for d in (self.d0, self.d1):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
        if single_date:
            bar.addWidget(QLabel("As on"))
            bar.addWidget(self.d1)
        else:
            for w in (QLabel("From"), self.d0, QLabel("To"), self.d1):
                bar.addWidget(w)
        b = QPushButton("Show")
        b.setObjectName("Primary")
        b.clicked.connect(self.refresh)
        bar.addWidget(b)
        if report_key:
            r = QPushButton(report_label)
            r.clicked.connect(lambda: self.open_report.emit(report_key))
            bar.addWidget(r)
        bar.addStretch(1)
        self.lay.addLayout(bar)
        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.lay.addWidget(self.body, 1)

    def dates(self) -> tuple[date, date]:
        q = lambda d: date(d.date().year(), d.date().month(), d.date().day())  # noqa: E731
        return q(self.d0), q(self.d1)

    def clear(self) -> None:
        while self.body_lay.count():
            item = self.body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    x = item.layout().takeAt(0).widget()
                    if x is not None:
                        x.deleteLater()

    def tiles(self, items: list[tuple[str, str]], per_row: int = 6) -> None:
        g = QGridLayout()
        for i, (k, v) in enumerate(items):
            g.addWidget(_tile(k, v), i // per_row, i % per_row)
        self.body_lay.addLayout(g)

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass


class PendingPage(_Page):
    def __init__(self, parent=None):
        super().__init__(True, "report.wip_process_summary", "WIP by process", parent)
        self.refresh()

    def refresh(self) -> None:
        self.clear()
        with SessionLocal() as s:
            d = DD.department_pending(s, self.dates()[1])
        self.tiles([("TOTAL", f"{d['total_pcs']} pcs · {d['total_wt']:,.3f} g")]
                   + [(p, f"{n} pcs · {w:,.3f} g") for p, n, w in d["by_process"]])
        row = QHBoxLayout()
        row.addWidget(BarChart([k.strftime("%d-%m") for k, _v in d["by_date"]][-20:],
                               [v for _k, v in d["by_date"]][-20:], "Pending pcs by date"), 2)
        shown = [(p, n) for p, n, _w in d["by_process"] if n]
        row.addWidget(PieChart([p for p, _n in shown], [n for _p, n in shown],
                               "Share by process"), 1)
        box = QWidget()
        box.setLayout(row)
        self.body_lay.addWidget(box, 1)


class OutputPage(_Page):
    def __init__(self, parent=None):
        super().__init__(False, "report.received_day_book", "Received Day Book", parent)
        self.refresh()

    def refresh(self) -> None:
        self.clear()
        with SessionLocal() as s:
            d = DD.daily_output(s, *self.dates())
        gi, go = d["ghat"]["in-house"], d["ghat"]["out-house"]
        self.tiles([("Ghat ready in-house", f"{gi[0]:,.3f} g · {gi[1]} SKUs"),
                    ("Ghat ready out-house", f"{go[0]:,.3f} g · {go[1]} SKUs")]
                   + [(f"Casting {k}", f"{v:,.3f} g") for k, v in d["casting"]]
                   + [("Setting diamond pcs", str(d["setting"]["DIAMOND"])),
                      ("Setting polki pcs", str(d["setting"]["POLKI"])),
                      ("Setting colour stone pcs", str(d["setting"]["COLOR STONE"])),
                      ("Setting lead days (avg)", str(d["setting_lead_days"] or "—"))], 4)
        self.body_lay.addWidget(BarChart([k for k, _v in d["casting"]],
                                         [v for _k, v in d["casting"]], "Casting by karat (g)",
                                         decimals=3), 1)
        note = QLabel("In-house / out-house follows the karigar's In-house flag in the Account "
                      "master.")
        note.setObjectName("Muted")
        self.body_lay.addWidget(note)


class SalePage(_Page):
    def __init__(self, parent=None):
        super().__init__(False, "report.sales_register", "Sales Register", parent)
        self.d0.setDate(QDate.currentDate())
        self.refresh()

    def refresh(self) -> None:
        self.clear()
        with SessionLocal() as s:
            rows = DD.sale_return_by_party(s, *self.dates())
        tot = lambda k: sum((r[k] for r in rows), Decimal("0"))  # noqa: E731
        self.tiles([("Sale", f"{tot('sale'):,.2f}"), ("Return", f"{tot('return'):,.2f}"),
                    ("Net", f"{tot('net'):,.2f}")])
        row = QHBoxLayout()
        row.addWidget(BarChart([r["party"] for r in rows][:15], [r["sale"] for r in rows][:15],
                               "Party-wise sale", decimals=0), 1)
        row.addWidget(_table(["Party", "Sale", "Return", "Net"],
                             [[r["party"], r["sale"], r["return"], r["net"]] for r in rows]), 1)
        box = QWidget()
        box.setLayout(row)
        self.body_lay.addWidget(box, 1)


class BillsPage(_Page):
    def __init__(self, parent=None):
        super().__init__(True, "account.outstandings.receivables", "Receivables", parent)
        self.refresh()

    def refresh(self) -> None:
        self.clear()
        with SessionLocal() as s:
            rows = DD.bills_due(s, self.dates()[1])
        self.tiles([(f"{r['office']} bill due", f"{r['due']:,.2f}") for r in rows]
                   or [("Bills due", "0.00")])
        self.body_lay.addWidget(_table(["Office / Branch", "Due", "Overdue", "Bills"],
                                       [[r["office"], r["due"], r["overdue"], r["bills"]]
                                        for r in rows]), 1)


class BusinessDashboardWidget(QWidget):
    open_requested = Signal(str)
    close_requested = Signal()

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.user = user
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        h1 = QLabel("Business Dashboard")
        h1.setObjectName("H1")
        lay.addWidget(h1)
        note = QLabel("Live from the ERP - the Looker pages (Department Pending, Ghat / Casting "
                      "/ Setting, Daily Sale & Return, Bills Due). Which tiles stay is to be "
                      "confirmed (C-04).")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        tabs = QTabWidget()
        for page, title in ((PendingPage(), "Department Pending"), (OutputPage(), "Daily Output"),
                            (SalePage(), "Daily Sale & Return"), (BillsPage(), "Bills Due")):
            page.open_report.connect(self.open_requested.emit)
            tabs.addTab(page, title)
        lay.addWidget(tabs, 1)
