"""Production-Planning screens (11 September session).

Job History, Job Card Bag and Job Mapping are read and operated, not typed
into a form, so they are hand-built around the shared header card (UX2)
rather than generated from a CrudSpec. Order, Stone Issue and Return to
Inventory are vouchers with lines and stay on the generic form; their rules
live in ``services/production.py``.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import shiboken6
from PySide6.QtCore import QDate, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from diagold.db.models import (
    Account,
    InventoryReturn,
    InventoryReturnLine,
    Job,
    JobBagLine,
    JobComment,
    Location,
    ManufacturingProcess,
    Metal,
    Order,
    PrintLog,
    PrintTemplate,
    ProductSku,
    StoneSku,
    User,
)
from diagold.db.session import SessionLocal
from diagold.menu import MENU_BY_KEY
from diagold.services import documents, production, rates, settings
from diagold.services.production import ProductionError
from diagold.ui.crud import ROW_HEIGHT, CrudWidget

# Legacy colour cues (UX1, UX3) - kept as tints so the text stays readable.
TINT_ISSUE = QColor("#FBE7E7")
TINT_RECEIVE = QColor("#E3F3E6")
TINT_ISS = QColor("#FFF4C2")
TINT_BREAK = QColor("#FBE3E3")
TINT_LOST = QColor("#F5C6C6")
TINT_BAL = QColor("#DDF2E2")
TINT_GROUP = QColor("#EEF0F3")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _s(value: Any, places: int = 3) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal):
        return f"{value:.{places}f}"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%b-%y")
    return str(value)


def _item(text: Any, tint: QColor | None = None, right: bool = False,
          bold: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(_s(text))
    if tint is not None:
        it.setBackground(tint)
    if right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def _table(headers: list[str], stretch_last: bool = True,
           ledger: bool = False) -> QTableWidget:
    """A read-only grid.

    ``ledger`` is for the wide per-step / per-stone tables (twenty-odd
    columns): headers are two lines ("Break" over "Pcs") so a column is only
    as wide as its numbers, cells carry less padding, and the spare width is
    handed to the first column by :func:`_fit_columns` rather than to the
    last - otherwise the far columns fall off the right edge of a laptop.
    """
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    t.horizontalHeader().setStretchLastSection(stretch_last and not ledger)
    t.setAlternatingRowColors(False)
    if ledger:
        t.setObjectName("Ledger")
        t.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    return t


def _fit_columns(t: QTableWidget, flex: int = 0) -> None:
    """Size every column to what it holds, then give the spare width to
    column ``flex`` so the grid fills its viewport; when the columns need more
    than the viewport there is nothing spare and the grid scrolls."""
    t.resizeColumnsToContents()
    spare = t.viewport().width() - sum(t.columnWidth(c) for c in range(t.columnCount()))
    if spare > 0:
        t.setColumnWidth(flex, t.columnWidth(flex) + spare)


class _FrozenColumns(QTableView):
    """Keeps the first ``n`` columns of a wide table in view while the rest
    scroll sideways - Job History has twenty-five columns and the reader
    needs to know which step a row belongs to when looking at its far end.

    A second view over the same model and selection, laid over the left edge
    of the main table and kept in step with its row scrolling and widths.
    """

    def __init__(self, table: QTableWidget, n: int):
        super().__init__(table)
        self.table, self.n = table, n
        self.setModel(table.model())
        self.setSelectionModel(table.selectionModel())
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.verticalHeader().hide()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setDefaultAlignment(table.horizontalHeader().defaultAlignment())
        self.setObjectName("Frozen")
        table.viewport().stackUnder(self)
        table.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().valueChanged.connect(table.verticalScrollBar().setValue)
        table.horizontalHeader().sectionResized.connect(lambda *_: self.sync())
        table.verticalHeader().sectionResized.connect(lambda *_: self.sync())
        table.model().rowsInserted.connect(lambda *_: self.sync())
        table.model().modelReset.connect(lambda *_: self.sync())
        self.sync()

    def sync(self) -> None:
        t = self.table
        if not shiboken6.isValid(t) or not shiboken6.isValid(self):
            return  # the model resets once more while the screen is torn down
        for c in range(t.columnCount()):
            self.setColumnHidden(c, c >= self.n)
            if c < self.n:
                self.setColumnWidth(c, t.columnWidth(c))
        for r in range(t.rowCount()):
            self.setRowHeight(r, t.rowHeight(r))
        # the main header is two lines tall; ours must match or the rows drift
        self.horizontalHeader().setFixedHeight(t.horizontalHeader().height())
        width = sum(t.columnWidth(c) for c in range(self.n))
        self.setGeometry(t.frameWidth(), t.frameWidth(), width,
                         t.viewport().height() + t.horizontalHeader().height())
        self.setVisible(width > 0 and t.rowCount() > 0)


def _header_text(table: QTableWidget, c: int) -> str:
    """A header label on one line, for CSV and print."""
    return table.horizontalHeaderItem(c).text().replace("\n", " ")


def _qdate(d: date | None) -> QDate:
    d = d or date.today()
    return QDate(d.year, d.month, d.day)


def _pydate(w: QDateEdit) -> date:
    q = w.date()
    return date(q.year(), q.month(), q.day())


def show_in_dialog(parent: QWidget | None, widget: QWidget, title: str,
                   size: tuple[int, int] = (1180, 720)) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(widget)
    dlg.resize(*size)
    dlg.exec()


def _warn(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def _info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def _workers(session) -> list[Account]:
    rows = list(session.scalars(
        select(Account).where(Account.account_type == "Worker",
                              Account.is_active.is_(True)).order_by(Account.name)))
    if rows:
        return rows
    return list(session.scalars(select(Account).order_by(Account.name)))


def _export_csv(parent: QWidget, table: QTableWidget, suggested: str) -> None:
    path, _ = QFileDialog.getSaveFileName(parent, "Export", suggested, "CSV (*.csv)")
    if not path:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([_header_text(table, c) for c in range(table.columnCount())])
        for r in range(table.rowCount()):
            w.writerow([(table.item(r, c).text() if table.item(r, c) else "")
                        for c in range(table.columnCount())])
    _info(parent, "Export", f"Saved {path}")


def _table_to_html(title: str, table: QTableWidget) -> str:
    head = "".join(f"<th>{_header_text(table, c)}</th>"
                   for c in range(table.columnCount()))
    rows = []
    for r in range(table.rowCount()):
        cells = "".join(
            f"<td>{table.item(r, c).text() if table.item(r, c) else ''}</td>"
            for c in range(table.columnCount()))
        rows.append(f"<tr>{cells}</tr>")
    return (f"<h2>{title}</h2><table border='1' cellspacing='0' cellpadding='3' "
            f"width='100%'><tr style='background:#eee'>{head}</tr>{''.join(rows)}</table>"
            f"<p style='color:#666;font-size:8pt'>Printed "
            f"{datetime.now().strftime('%d-%b-%Y %H:%M')}</p>")


def _print_table(parent: QWidget, title: str, table: QTableWidget, stem: str) -> None:
    path = documents.PRINT_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    documents.to_pdf(_table_to_html(title, table), path)
    _info(parent, "Print", f"Saved {path}")


# --------------------------------------------------------------------------
# shared pieces: job picker and header card
# --------------------------------------------------------------------------
class JobPicker(QWidget):
    """Type a job number or pick from the list. Emits the job id."""

    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lab = QLabel("Job No")
        lab.setObjectName("Muted")
        lay.addWidget(lab)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumWidth(220)
        # Long labels ("28350 · NS-2968 · RUBY SINGH") must not widen the row.
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(18)
        lay.addWidget(self.combo)
        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setToolTip("Refresh the job list")
        self.btn_refresh.setFixedWidth(34)
        self.btn_refresh.clicked.connect(self.refresh)
        lay.addWidget(self.btn_refresh)
        lay.addStretch(1)
        self.combo.currentIndexChanged.connect(
            lambda _i: self.changed.emit(self.combo.currentData()))
        self.combo.lineEdit().returnPressed.connect(self._jump)
        self.refresh()

    def refresh(self) -> None:
        current = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        with SessionLocal() as s:
            jobs = list(s.scalars(select(Job).where(Job.status != "cancelled")))
            # Jobs on the floor first, newest first - what F11 is reached for.
            jobs.sort(key=lambda j: (j.status != "in_progress", -j.job_no))
            for job in jobs:
                self.combo.addItem(job.label, job.id)
        comp = QCompleter([self.combo.itemText(i) for i in range(self.combo.count())], self)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.setCompleter(comp)
        idx = self.combo.findData(current) if current is not None else 0
        self.combo.setCurrentIndex(max(idx, 0))
        self.combo.blockSignals(False)
        self.changed.emit(self.combo.currentData())

    def _jump(self) -> None:
        text = self.combo.currentText().strip()
        for i in range(self.combo.count()):
            if self.combo.itemText(i).split(" · ")[0] == text or \
                    self.combo.itemText(i).lower() == text.lower():
                self.combo.setCurrentIndex(i)
                return

    def job_id(self) -> int | None:
        return self.combo.currentData()

    def set_job(self, job_id: int) -> None:
        idx = self.combo.findData(job_id)
        if idx < 0:
            self.refresh()
            idx = self.combo.findData(job_id)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)


class JobHeaderCard(QFrame):
    """Job No, SKU, client, order, metal, pcs, route and photo - the same card
    on every job screen (UX2)."""

    FIELDS = (("job_no", "Job No"), ("sku", "SKU"), ("c_ref", "C-Ref"),
              ("ord_ref", "Ord-Ref"), ("client", "Client"), ("order", "Ord No"),
              ("metal", "Metal"), ("pcs", "Pcs"), ("delivery", "Delivery"),
              ("route", "Route"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(18)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.values: dict[str, QLabel] = {}
        for i, (key, label) in enumerate(self.FIELDS):
            r, c = divmod(i, 3)
            k = QLabel(label)
            k.setObjectName("Muted")
            v = QLabel("—")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            # A long route string or metal head wraps; it must never set the
            # minimum width of the whole screen.
            v.setWordWrap(True)
            v.setMinimumWidth(60)
            if key in ("job_no", "client"):
                f = v.font()
                f.setBold(True)
                v.setFont(f)
            self.values[key] = v
            grid.addWidget(k, r, c * 2)
            grid.addWidget(v, r, c * 2 + 1)
        for c in range(3):
            grid.setColumnStretch(c * 2 + 1, 1)
        lay.addLayout(grid, 1)
        self.photo = QLabel("no photo")
        self.photo.setObjectName("ImageSlot")
        self.photo.setFixedSize(96, 96)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.photo)

    def clear(self) -> None:
        for v in self.values.values():
            v.setText("—")
        self.photo.setPixmap(QPixmap())
        self.photo.setText("no photo")

    def set_job(self, session, job: Job | None) -> None:
        if job is None:
            self.clear()
            return
        sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
        order = session.get(Order, job.order_id) if job.order_id else None
        client = session.get(Account, job.account_id) if job.account_id else None
        metal = session.get(Metal, job.metal_id) if job.metal_id else None
        vals = {
            "job_no": str(job.job_no),
            "sku": sku.sku_code if sku else "",
            "c_ref": job.c_ref, "ord_ref": order.ref if order else "",
            "client": client.name if client else "stock",
            "order": f"{order.order_no} dt {_s(order.order_date)}" if order else "",
            "metal": (f"{metal.name} {metal.print_on_tag} {job.colour}-".strip()
                      if metal else job.colour),
            "pcs": str(job.pcs),
            "delivery": _s(job.prod_del_date or (order.delivery_date if order else None)),
            "route": production.route_string(session, job) or "(not mapped)",
        }
        for k, v in vals.items():
            self.values[k].setText(v or "—")
        path = (sku.image_finished or sku.image_design) if sku else ""
        pix = QPixmap(path) if path else QPixmap()
        if not pix.isNull():
            self.photo.setText("")
            self.photo.setPixmap(pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        else:
            self.photo.setPixmap(QPixmap())
            self.photo.setText("no photo")


class _Screen(QWidget):
    """Common frame: title, an optional job picker and a header card."""

    open_requested = Signal(str)
    close_requested = Signal()

    def __init__(self, title: str, with_picker: bool = True, parent=None):
        super().__init__(parent)
        self.user = None
        self.job_id: int | None = None
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(24, 20, 24, 20)
        self.outer.setSpacing(10)
        h1 = QLabel(title)
        h1.setObjectName("H1")
        self.outer.addWidget(h1)
        # Two rows of buttons, not one: the things done to the job (issue,
        # receive, return...) sit beside the job picker; prints, reports and
        # links to other screens go on a second row. One row of nine buttons
        # plus the picker is wider than a laptop's content area, and Qt then
        # clips the whole screen - the last buttons and the last table columns
        # simply fall off the right edge.
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        self.secondary = QHBoxLayout()
        self.secondary.setSpacing(8)
        self.picker: JobPicker | None = None
        if with_picker:
            self.picker = JobPicker()
            self.picker.changed.connect(self._on_job)
            self.job_id = self.picker.job_id()  # the first emit happened before connect
            self.toolbar.addWidget(self.picker, 1)
        self.outer.addLayout(self.toolbar)
        self.outer.addLayout(self.secondary)
        self.secondary.addStretch(1)
        self.header = JobHeaderCard()
        self.outer.addWidget(self.header)

    def button(self, label: str, slot: Callable, primary: bool = False,
               secondary: bool = False) -> QPushButton:
        b = QPushButton(label)
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(slot)
        if secondary:
            # keep the stretch first so these sit against the right edge
            self.secondary.insertWidget(self.secondary.count(), b)
        else:
            self.toolbar.addWidget(b)
        return b

    def _on_job(self, job_id) -> None:
        self.job_id = job_id
        self.refresh()

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass

    def show_job(self, job_id: int) -> None:
        if self.picker is not None:
            self.picker.set_job(job_id)


# --------------------------------------------------------------------------
# Job History (T-01)
# --------------------------------------------------------------------------
ISSUE_COLS = [("vr_date", "Date"), ("vr_time", "Time"), ("vr_no", "VrNo"), ("pcs", "Pcs"),
              ("gross_wt", "G-Wt"), ("net_wt", "N-Wt"), ("stone_wt", "Stone"),
              ("extra", "Extra"), ("finding", "Finding"), ("mould", "Mould"),
              ("wip_value", "WIP Value")]
RECEIVE_COLS = [("del_date", "Del-Date"), ("vr_date", "Date"), ("vr_time", "Time"),
                ("vr_no", "VrNo"), ("pcs", "Pcs"), ("gross_wt", "G-Wt"), ("net_wt", "N-Wt"),
                ("rej_pcs", "Rej Pcs"), ("rej_wt", "Rej Wt"), ("scrap", "Scrap"),
                ("dust", "Dust")]


class VoucherDialog(QDialog):
    """Post one issue or receive voucher on a job step."""

    def __init__(self, job_id: int, kind: str, user_id: int | None, parent=None):
        super().__init__(parent)
        self.job_id, self.kind, self.user_id = job_id, kind, user_id
        self.setWindowTitle("Issue to worker" if kind == "issue" else "Receive from worker")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.step = QComboBox()
        self.worker = QComboBox()
        with SessionLocal() as s:
            job = s.get(Job, job_id)
            for st in job.steps:
                p = s.get(ManufacturingProcess, st.process_id)
                open_iss = production.open_issue(s, st)
                tag = " (out)" if open_iss else ""
                self.step.addItem(f"{st.seq} · {p.name if p else '?'}{tag}", st.id)
                if kind == "receive" and open_iss:
                    self.step.setCurrentIndex(self.step.count() - 1)
                    w = s.get(Account, open_iss.worker_id)
                    self._default_worker = open_iss.worker_id
            for w in _workers(s):
                self.worker.addItem(w.name, w.id)
        if getattr(self, "_default_worker", None):
            i = self.worker.findData(self._default_worker)
            if i >= 0:
                self.worker.setCurrentIndex(i)
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.time = QLineEdit(datetime.now().strftime("%H:%M"))
        self.time.setMaximumWidth(80)
        self.pcs = QSpinBox()
        self.pcs.setRange(0, 100000)
        self.pcs.setValue(1)
        self.gross = self._wt()
        self.net = self._wt()
        form.addRow("Process step *", self.step)
        form.addRow("Worker *", self.worker)
        form.addRow("Date", self.date)
        form.addRow("Time", self.time)
        form.addRow("Pcs", self.pcs)
        form.addRow("Gross Wt (g)", self.gross)
        form.addRow("Net Wt (g)", self.net)
        self.extra: dict[str, QWidget] = {}
        if kind == "issue":
            for key, label in (("stone_wt", "Stone Wt"), ("extra", "Extra"),
                               ("finding", "Finding"), ("mould", "Mould"),
                               ("wip_value", "WIP Value")):
                self.extra[key] = self._wt(2 if key == "wip_value" else 3)
                form.addRow(label, self.extra[key])
        else:
            self.extra["del_date"] = QDateEdit(_qdate(None))
            self.extra["del_date"].setCalendarPopup(True)
            self.extra["del_date"].setDisplayFormat("yyyy-MM-dd")
            form.addRow("Del-Date", self.extra["del_date"])
            self.extra["rej_pcs"] = QSpinBox()
            self.extra["rej_pcs"].setRange(0, 100000)
            form.addRow("Rej Pcs", self.extra["rej_pcs"])
            for key, label in (("rej_wt", "Rej Wt"), ("scrap", "Scrap"), ("dust", "Dust")):
                self.extra[key] = self._wt()
                form.addRow(label, self.extra[key])
        self.remark = QLineEdit()
        form.addRow("Remark", self.remark)
        hint = QLabel("Loss is derived from what comes back: issued net − received net "
                      "− scrap − dust. A design-only step (CAD) takes no weights.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _wt(places: int = 3) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setDecimals(places)
        w.setRange(0, 1_000_000)
        w.setSpecialValueText(" ")  # zero shows blank: "not weighed"
        return w

    def _save(self) -> None:
        def val(w) -> Any:
            if isinstance(w, QDoubleSpinBox):
                return None if w.value() == 0 else Decimal(str(w.value()))
            if isinstance(w, QSpinBox):
                return w.value()
            if isinstance(w, QDateEdit):
                return _pydate(w)
            return w.text().strip()
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            step = next((st for st in job.steps if st.id == self.step.currentData()), None)
            try:
                production.post_voucher(
                    s, job, step, self.kind, self.worker.currentData(),
                    vr_date=_pydate(self.date), vr_time=self.time.text().strip(),
                    pcs=self.pcs.value(), gross_wt=val(self.gross), net_wt=val(self.net),
                    user_id=self.user_id, remark=self.remark.text().strip(),
                    **{k: val(w) for k, w in self.extra.items()},
                )
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self.accept()


class JobHistoryWidget(_Screen):
    """The complete life of a job in one view (R5, §4.6)."""

    def __init__(self, user=None, parent=None):
        super().__init__("Job History", parent=parent)
        self.user = user
        self.button("+ Issue", lambda: self._voucher("issue"), primary=True)
        self.button("+ Receive", lambda: self._voucher("receive"))
        self.button("WIP Costing", self._wip)
        self.button("Print", self._print, secondary=True)
        self.button("Stone Dtls", lambda: self.stones.setFocus(), secondary=True)
        self.button("Job Bag", lambda: self.open_requested.emit("production_planning.job_card_bag"),
                    secondary=True)
        self.button("Add Comments", self._add_comment, secondary=True)
        self.button("Stone Return",
                    lambda: self.open_requested.emit("production_planning.inv_return"),
                    secondary=True)
        self.button("Update", lambda: self.open_requested.emit("production_planning.job_mapping"),
                    secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)

        legend = QLabel("Issue columns are tinted pink, receive columns green — read "
                        "loss across a row.  F11 opens this screen.  Update opens the route in "
                        "Job Mapping; Stone Return opens the return voucher on this job.")
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        self.outer.addWidget(legend)

        headers = (["Process", "Worker"] + [f"Iss\n{l}" for _, l in ISSUE_COLS]
                   + [f"Rcv\n{l}" for _, l in RECEIVE_COLS] + ["Loss\n(g)"])
        self.grid = _table(headers, ledger=True)
        self.frozen = _FrozenColumns(self.grid, 2)
        self.outer.addWidget(self.grid, 3)

        stone_box = QGroupBox("Stones on this job")
        sl = QVBoxLayout(stone_box)
        self.stones = _table(["Location", "SSKU", "Description", "Size", "LotNo", "Wt/Pcs",
                              "Pcs", "Weight", "Rtn", "Break", "Loss", "S Type", "Remark"])
        sl.addWidget(self.stones)
        self.outer.addWidget(stone_box, 2)

        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.outer.addWidget(self.summary)
        self.remark = QLabel("")
        self.remark.setWordWrap(True)
        self.remark.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.outer.addWidget(self.remark)
        self.comments = QLabel("")
        self.comments.setObjectName("Muted")
        self.comments.setWordWrap(True)
        self.outer.addWidget(self.comments)
        self.refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        _fit_columns(self.grid)
        self.frozen.sync()

    def refresh(self) -> None:
        self.grid.setRowCount(0)
        self.stones.setRowCount(0)
        if not self.job_id:
            self.header.clear()
            self.summary.setText("")
            self.remark.setText("")
            self.comments.setText("")
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            self.header.set_job(s, job)
            for row in production.history_rows(s, job):
                r = self.grid.rowCount()
                self.grid.insertRow(r)
                self.grid.setItem(r, 0, _item(row.process.name if row.process else "",
                                              bold=row.issue is not None))
                self.grid.setItem(r, 1, _item(row.worker))
                c = 2
                for key, _ in ISSUE_COLS:
                    v = getattr(row.issue, key, None) if row.issue else None
                    self.grid.setItem(r, c, _item(v, TINT_ISSUE, right=key not in
                                                  ("vr_date", "vr_time")))
                    c += 1
                for key, _ in RECEIVE_COLS:
                    v = getattr(row.receive, key, None) if row.receive else None
                    self.grid.setItem(r, c, _item(v, TINT_RECEIVE, right=key not in
                                                  ("vr_date", "del_date", "vr_time")))
                    c += 1
                self.grid.setItem(r, c, _item(row.loss, right=True, bold=True))
            _fit_columns(self.grid)
            self.frozen.sync()
            for b in production.bag_ledger(s, job):
                r = self.stones.rowCount()
                self.stones.insertRow(r)
                loc = s.get(Location, b.line.source_location_id) if b.line.source_location_id else None
                sku = s.get(StoneSku, b.line.stone_sku_id) if b.line.stone_sku_id else None
                rc_pcs, rc_wt = b["rcvd"]
                per = (rc_wt / rc_pcs).quantize(Decimal("0.0001")) if rc_pcs else ""
                vals = [loc.name if loc else "", sku.sku_code if sku else "",
                        b.line.particulars, b.line.size, "", per, rc_pcs, rc_wt,
                        f"{b['rtn'][0]} / {b['rtn'][1]}", f"{b['break'][0]} / {b['break'][1]}",
                        f"{b['lost'][0]} / {b['lost'][1]}", b.line.s_type, ""]
                for c, v in enumerate(vals):
                    self.stones.setItem(r, c, _item(v, right=c in (5, 6, 7)))
            self.stones.resizeColumnsToContents()
            sm = production.job_summary(s, job)
            self.summary.setText(
                f"PND: {sm['pnd'] or '—'}    WIP: {sm['wip']}    Rejection: {sm['rejection']}"
                f"    PND For MFG Transfer: {sm['pnd_mfg_transfer']}    "
                f"MFG Transfer: {sm['mfg_transfer']}    TOTAL PCS: {sm['total_pcs']}")
            # Order Remark carries the stone requirement as text in the legacy
            # ("daank/411/19.92, DIA./241/2.81"); show it and what it parses to.
            parsed = production.parse_order_remark(sm["order_remark"])
            extra = ("  →  " + ", ".join(f"{p['particulars']} {p['pcs']} pcs / {p['weight']}"
                                        for p in parsed)) if parsed else ""
            self.remark.setText(f"<b>Order Remark:</b> {sm['order_remark'] or '—'}{extra}")
            notes = list(s.scalars(select(JobComment).where(JobComment.job_id == job.id)
                                   .order_by(JobComment.created_at.desc()).limit(8)))
            if notes:
                lines = []
                for n in notes:
                    who = s.get(User, n.user_id) if n.user_id else None
                    lines.append(f"{n.created_at.strftime('%d-%b %H:%M')} · "
                                 f"{who.full_name if who else '—'}: {n.text}")
                self.comments.setText("<b>Comments</b><br>" + "<br>".join(lines))
            else:
                self.comments.setText("")

    def _voucher(self, kind: str) -> None:
        if not self.job_id:
            _info(self, "Job History", "Pick a job first.")
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if not job.steps:
                _warn(self, "No route",
                      f"Job {job.job_no} has no route yet. Map it in Job Mapping first.")
                return
        dlg = VoucherDialog(self.job_id, kind, getattr(self.user, "id", None), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _add_comment(self) -> None:
        if not self.job_id:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Comments")
        dlg.setMinimumWidth(460)
        lay = QVBoxLayout(dlg)
        box = QPlainTextEdit()
        box.setPlaceholderText("Note on this job — timestamped and attributed to you.")
        lay.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted or not box.toPlainText().strip():
            return
        with SessionLocal() as s:
            s.add(JobComment(job_id=self.job_id, user_id=getattr(self.user, "id", None),
                             text=box.toPlainText().strip()))
            s.commit()
        self.refresh()

    def _print(self) -> None:
        if not self.job_id:
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            tpl = documents.templates_for(s, "job_sheet")
            if not tpl:
                _warn(self, "Print", "No Job Sheet template is active.")
                return
            path = documents.print_job(s, job, tpl[0], getattr(self.user, "id", None))
            s.commit()
        _info(self, "Print", f"Saved {path}")

    def _wip(self) -> None:
        """What is out with workers right now, valued at today's metal rate.
        The costing rule itself is for the factory session (Q6/Q8)."""
        if not self.job_id:
            return
        t = _table(["Process", "Worker", "Net Wt out (g)", "Stone Wt", "WIP Value typed",
                    "Metal value @ today's rate"])
        total = Decimal("0")
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            metal = s.get(Metal, job.metal_id) if job.metal_id else None
            info = rates.rate_for(s, metal.id, date.today()) if metal else None
            from diagold.services import costing
            per_g = costing.sku_metal_rate(info.rate, metal) if (info and metal) else Decimal("0")
            for row in production.history_rows(s, job):
                if row.issue is None or row.receive is not None:
                    continue
                net = Decimal(str(row.issue.net_wt or 0))
                value = (net * per_g).quantize(Decimal("0.01"))
                total += value
                r = t.rowCount()
                t.insertRow(r)
                for c, v in enumerate([row.process.name if row.process else "", row.worker,
                                       net, row.issue.stone_wt, row.issue.wip_value, value]):
                    t.setItem(r, c, _item(v, right=c >= 2))
        box = QWidget()
        lay = QVBoxLayout(box)
        note = QLabel(f"Metal rate used: {per_g:.2f}/g"
                      + (f" (rate of {info.effective_date})" if info and info.found
                         else " (no daily rate on file)")
                      + f".  Open WIP metal value: {total:,.2f}.  How WIP should be "
                        "costed is for the factory session (Q6, Q8) - this is a "
                        "straight net-weight x rate view.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        lay.addWidget(t)
        show_in_dialog(self, box, "WIP Costing", (900, 480))


# --------------------------------------------------------------------------
# Job Card Bag (T-02)
# --------------------------------------------------------------------------
class MovementDialog(QDialog):
    KINDS = {"iss": "Issue to worker", "back": "Back from worker",
             "rtn": "Return to stock", "break": "Broken", "lost": "Lost"}

    def __init__(self, row: production.BagRow, kind: str, parent=None):
        super().__init__(parent)
        self.row, self.kind = row, kind
        self.setWindowTitle(self.KINDS[kind])
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        bal_pcs, bal_wt = row["bal"]
        name = f"{row.line.particulars} {row.line.size}".strip()
        cap = bal_pcs if kind != "back" else row["iss"][0] - row["back"][0]
        head = QLabel(f"<b>{name}</b> — in bag {bal_pcs} pcs / {bal_wt} {row.line.unit}")
        form.addRow(head)
        self.pcs = QSpinBox()
        self.pcs.setRange(0, max(cap, 0))
        self.pcs.setValue(min(1, max(cap, 0)))
        self.weight = QDoubleSpinBox()
        self.weight.setDecimals(4)
        self.weight.setRange(0, 1_000_000)
        self._avg = (bal_wt / bal_pcs) if bal_pcs else Decimal("0")
        self.pcs.valueChanged.connect(self._follow)
        self._follow(self.pcs.value())
        form.addRow("Pcs", self.pcs)
        form.addRow(f"Weight ({row.line.unit})", self.weight)
        self.worker = self.location = None
        with SessionLocal() as s:
            if kind in ("iss", "back"):
                self.worker = QComboBox()
                for w in _workers(s):
                    self.worker.addItem(w.name, w.id)
                form.addRow("Worker *", self.worker)
            if kind == "rtn":
                self.location = QComboBox()
                for loc in s.scalars(select(Location).order_by(Location.name)):
                    self.location.addItem(loc.name, loc.id)
                if row.line.source_location_id:
                    i = self.location.findData(row.line.source_location_id)
                    if i >= 0:
                        self.location.setCurrentIndex(i)
                form.addRow("Back to location *", self.location)
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Date", self.date)
        self.remark = QLineEdit()
        form.addRow("Remark", self.remark)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _follow(self, pcs: int) -> None:
        self.weight.setValue(float((self._avg * pcs).quantize(Decimal("0.0001"))))

    def values(self) -> dict[str, Any]:
        return {
            "pcs": self.pcs.value(), "weight": Decimal(str(self.weight.value())),
            "worker_id": self.worker.currentData() if self.worker else None,
            "location_id": self.location.currentData() if self.location else None,
            "mv_date": _pydate(self.date), "remark": self.remark.text().strip(),
        }


class JobBagWidget(_Screen):
    """Per-job stone ledger with the two reports the client asked for (R3, R4)."""

    def __init__(self, user=None, parent=None):
        super().__init__("Job Card Bag", parent=parent)
        self.user = user
        self.button("Issue to Worker", lambda: self._move("iss"), primary=True)
        self.button("Back from Worker", lambda: self._move("back"))
        self.button("Return to Stock", lambda: self._move("rtn"))
        # Break and Lost are rarer; they sit on the second row so the first
        # row stays inside a laptop's width.
        self.button("Break", lambda: self._move("break"), secondary=True)
        self.button("Lost", lambda: self._move("lost"), secondary=True)
        self.button("Print", self._print, secondary=True)
        self.button("Stones in Job Cards", self._report_all, secondary=True)
        self.button("Bag Balance Report", self._report_bag, secondary=True)
        self.button("Job History", lambda: self.open_requested.emit("production_planning.job_history"),
                    secondary=True)

        headers = ["Particulars", "Size", "Type"]
        for col in production.COLUMNS:
            lab = production.COLUMN_LABELS[col]
            headers += [f"{lab}\nPcs", f"{lab}\nWt"]
        self.grid = _table(headers, ledger=True)
        self.outer.addWidget(self.grid, 1)
        legend = QLabel("Bal = Rcvd − Iss − Rtn − Break − Lost + Back.  Tints: Iss yellow, "
                        "Break pink, Lost red, Bal green (as on the legacy screen).  "
                        "'Back' is read as returned from the worker into the bag (Q7).")
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        self.outer.addWidget(legend)
        self._rows: list[production.BagRow] = []
        self.refresh()

    def refresh(self) -> None:
        self.grid.setRowCount(0)
        self._rows = []
        if not self.job_id:
            self.header.clear()
            return
        tints = {"iss": TINT_ISS, "break": TINT_BREAK, "lost": TINT_LOST, "bal": TINT_BAL}
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            self.header.set_job(s, job)
            self._rows = production.bag_ledger(s, job)
        for b in self._rows:
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            self.grid.setItem(r, 0, _item(b.line.particulars, bold=True))
            self.grid.setItem(r, 1, _item(b.line.size))
            self.grid.setItem(r, 2, _item(b.line.s_type))
            c = 3
            for col in production.COLUMNS:
                pcs, wt = b[col]
                tint = tints.get(col)
                self.grid.setItem(r, c, _item(pcs, tint, right=True, bold=col == "bal"))
                self.grid.setItem(r, c + 1, _item(wt, tint, right=True, bold=col == "bal"))
                c += 2
        _fit_columns(self.grid)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        _fit_columns(self.grid)

    def _selected_row(self) -> production.BagRow | None:
        rows = self.grid.selectionModel().selectedRows()
        if not rows or not self._rows:
            _info(self, "Job Card Bag", "Select a stone line first.")
            return None
        return self._rows[rows[0].row()]

    def _move(self, kind: str) -> None:
        row = self._selected_row()
        if row is None:
            return
        dlg = MovementDialog(row, kind, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        with SessionLocal() as s:
            line = s.get(JobBagLine, row.line.id)
            try:
                production.bag_move(s, line, kind, v["pcs"], v["weight"],
                                    worker_id=v["worker_id"], location_id=v["location_id"],
                                    mv_date=v["mv_date"], remark=v["remark"])
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self.refresh()

    def _print(self) -> None:
        if not self.job_id:
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            title = f"Job Card Bag — Job {job.job_no}"
        _print_table(self, title, self.grid, f"job_bag_{self.job_id}")

    def _report_bag(self) -> None:
        """Report B - this job's ledger with totals."""
        if not self._rows:
            return
        t = _table(["Particulars", "Size", "Type", "Rcvd Pcs", "Rcvd Wt", "Iss Pcs", "Iss Wt",
                    "Rtn Pcs", "Rtn Wt", "Break Pcs", "Break Wt", "Lost Pcs", "Lost Wt",
                    "Bal Pcs", "Bal Wt"])
        tot = {k: [0, Decimal("0")] for k in ("rcvd", "iss", "rtn", "break", "lost", "bal")}
        for b in self._rows:
            r = t.rowCount()
            t.insertRow(r)
            vals = [b.line.particulars, b.line.size, b.line.s_type]
            for k in tot:
                pcs, wt = b[k]
                tot[k][0] += pcs
                tot[k][1] += wt
                vals += [pcs, wt]
            for c, v in enumerate(vals):
                t.setItem(r, c, _item(v, right=c >= 3))
        r = t.rowCount()
        t.insertRow(r)
        vals = ["TOTAL", "", ""]
        for k in tot:
            vals += tot[k]
        for c, v in enumerate(vals):
            t.setItem(r, c, _item(v, TINT_GROUP, right=c >= 3, bold=True))
        t.resizeColumnsToContents()
        self._report_dialog("Job Card Bag balance", t, f"bag_balance_{self.job_id}")

    def _report_all(self) -> None:
        """Report A - what is lying in every open job card."""
        t = _table(["Job No", "SKU", "Client", "Stone", "Size", "Type", "Bal Pcs", "Bal Wt"])
        with SessionLocal() as s:
            for row in production.stones_in_job_cards(s):
                r = t.rowCount()
                t.insertRow(r)
                for c, k in enumerate(("job_no", "sku", "client", "stone", "size", "type",
                                       "bal_pcs", "bal_wt")):
                    t.setItem(r, c, _item(row[k], right=c >= 6))
        t.resizeColumnsToContents()
        self._report_dialog("Stones lying in job cards", t, "stones_in_job_cards")

    def _report_dialog(self, title: str, table: QTableWidget, stem: str) -> None:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 12)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"{table.rowCount()} row(s)"))
        bar.addStretch(1)
        b1 = QPushButton("Export CSV")
        b1.clicked.connect(lambda: _export_csv(box, table, f"{stem}.csv"))
        b2 = QPushButton("Print")
        b2.clicked.connect(lambda: _print_table(box, title, table, stem))
        bar.addWidget(b1)
        bar.addWidget(b2)
        lay.addLayout(bar)
        lay.addWidget(table)
        show_in_dialog(self, box, title, (1000, 560))


# --------------------------------------------------------------------------
# Job Mapping (T-03)
# --------------------------------------------------------------------------
class JobMappingWidget(_Screen):
    """Pending queue as a first-class list (UX4), then the route per job."""

    def __init__(self, user=None, parent=None):
        super().__init__("Job Mapping", with_picker=False, parent=parent)
        self.user = user
        self.show_all = QCheckBox("Show Jobs (mapped too)")
        self.show_all.toggled.connect(self.refresh)
        self.toolbar.addWidget(self.show_all)
        self.toolbar.addStretch(1)
        self.button("Refresh", self.refresh)
        self.button("Print", self._print)

        # The header card is not useful before a job is picked; it sits below.
        self.outer.removeWidget(self.header)

        queue_box = QGroupBox("Pending Jobs For Definition")
        ql = QVBoxLayout(queue_box)
        self.queue = _table(["Ord No", "Date", "Ref No", "C-Code", "SKU", "C-Ref", "Metal",
                             "Col", "Job No", "Pcs", "Status", "Image"])
        self.queue.itemSelectionChanged.connect(self._pick_from_queue)
        ql.addWidget(self.queue)
        self.outer.addWidget(queue_box, 2)

        self.outer.addWidget(self.header)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QGroupBox("Jobs of this order")
        ll = QVBoxLayout(left)
        self.siblings = _table(["SKU", "C-Ref", "Ord Ref", "JobNo", "Pcs", "Prod Date",
                                "Prod Del Date", "Manual", "Status"])
        self.siblings.itemSelectionChanged.connect(self._pick_sibling)
        ll.addWidget(self.siblings)
        split.addWidget(left)

        right = QGroupBox("Process route for the selected job")
        rl = QVBoxLayout(right)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Process Group"))
        self.group = QComboBox()
        bar.addWidget(self.group)
        bar.addWidget(QLabel("Start"))
        self.start = QDateEdit(_qdate(None))
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("yyyy-MM-dd")
        bar.addWidget(self.start)
        b_apply = QPushButton("Apply Group")
        b_apply.clicked.connect(self._apply_group)
        bar.addWidget(b_apply)
        bar.addStretch(1)
        rl.addLayout(bar)
        self.steps = QTableWidget(0, 3)
        self.steps.setHorizontalHeaderLabels(["Sno", "Process", "Prod Due Date"])
        self.steps.verticalHeader().setVisible(False)
        self.steps.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.steps.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.steps.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        rl.addWidget(self.steps)
        bar2 = QHBoxLayout()
        for label, slot, primary in (("Add Step", self._add_step, False),
                                     ("Remove Step", self._remove_step, False),
                                     ("Save Route", self._save, True),
                                     ("Copy To All", self._copy_all, False)):
            b = QPushButton(label)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(slot)
            bar2.addWidget(b)
        bar2.addStretch(1)
        rl.addLayout(bar2)
        split.addWidget(right)
        split.setSizes([480, 640])
        self.outer.addWidget(split, 3)

        self._processes: list[tuple[int, str]] = []
        self._queue_ids: list[int] = []
        self._sibling_ids: list[int] = []
        self.refresh()

    # -- data ---------------------------------------------------------
    def refresh(self) -> None:
        with SessionLocal() as s:
            self._processes = [(p.id, p.name) for p in s.scalars(
                select(ManufacturingProcess).where(ManufacturingProcess.is_active.is_(True))
                .order_by(ManufacturingProcess.sequence, ManufacturingProcess.name))]
            self.group.blockSignals(True)
            self.group.clear()
            self.group.addItems(production.group_names(s))
            self.group.blockSignals(False)
            stmt = select(Job).where(Job.status != "cancelled").order_by(Job.job_no)
            if not self.show_all.isChecked():
                stmt = stmt.where(Job.status == "pending")
            self.queue.setRowCount(0)
            self._queue_ids = []
            for job in s.scalars(stmt):
                order = s.get(Order, job.order_id) if job.order_id else None
                client = s.get(Account, job.account_id) if job.account_id else None
                sku = s.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
                metal = s.get(Metal, job.metal_id) if job.metal_id else None
                image = Path(sku.image_finished or sku.image_design).name if sku and (
                    sku.image_finished or sku.image_design) else ""
                vals = [order.order_no if order else "", order.order_date if order else "",
                        order.ref if order else "", client.code if client else "",
                        sku.sku_code if sku else "", job.c_ref, metal.name if metal else "",
                        job.colour, job.job_no, job.pcs, job.status, image]
                r = self.queue.rowCount()
                self.queue.insertRow(r)
                for c, v in enumerate(vals):
                    self.queue.setItem(r, c, _item(v, right=c in (0, 8, 9)))
                self._queue_ids.append(job.id)
            self.queue.resizeColumnsToContents()
        if self.job_id and self.job_id in self._queue_ids:
            self.queue.selectRow(self._queue_ids.index(self.job_id))
        elif self._queue_ids:
            self.queue.selectRow(0)
        else:
            self.job_id = None
            self._load_job()

    def _pick_from_queue(self) -> None:
        rows = self.queue.selectionModel().selectedRows()
        if not rows:
            return
        self.job_id = self._queue_ids[rows[0].row()]
        self._load_job()

    def _pick_sibling(self) -> None:
        rows = self.siblings.selectionModel().selectedRows()
        if not rows:
            return
        job_id = self._sibling_ids[rows[0].row()]
        if job_id != self.job_id:
            self.job_id = job_id
            self._load_job(keep_siblings=True)

    def _load_job(self, keep_siblings: bool = False) -> None:
        self.steps.setRowCount(0)
        if not keep_siblings:
            self.siblings.setRowCount(0)
            self._sibling_ids = []
        if not self.job_id:
            self.header.clear()
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            self.header.set_job(s, job)
            if not keep_siblings:
                order = s.get(Order, job.order_id) if job.order_id else None
                sibs = list(s.scalars(select(Job).where(Job.order_id == job.order_id,
                                                        Job.status != "cancelled")
                                      .order_by(Job.job_no))) if job.order_id else [job]
                for j in sibs:
                    sku = s.get(ProductSku, j.product_sku_id) if j.product_sku_id else None
                    vals = [sku.sku_code if sku else "", j.c_ref, order.ref if order else "",
                            j.job_no, j.pcs, j.prod_date, j.prod_del_date,
                            "Y" if j.manual else "N", j.status]
                    r = self.siblings.rowCount()
                    self.siblings.insertRow(r)
                    for c, v in enumerate(vals):
                        self.siblings.setItem(r, c, _item(v, right=c in (3, 4)))
                    self._sibling_ids.append(j.id)
                self.siblings.resizeColumnsToContents()
                if self.job_id in self._sibling_ids:
                    self.siblings.blockSignals(True)
                    self.siblings.selectRow(self._sibling_ids.index(self.job_id))
                    self.siblings.blockSignals(False)
            for st in job.steps:
                self._add_step(st.process_id, st.due_date)
            if job.prod_date:
                self.start.setDate(_qdate(job.prod_date))

    def show_job(self, job_id: int) -> None:
        """Land on a given job - from Job History's Update button, or a report."""
        with SessionLocal() as s:
            job = s.get(Job, job_id)
        if job is not None and job.status != "pending" and not self.show_all.isChecked():
            self.show_all.blockSignals(True)
            self.show_all.setChecked(True)
            self.show_all.blockSignals(False)
        self.job_id = job_id
        self.refresh()

    # -- route editor -------------------------------------------------
    def _add_step(self, process_id: int | None = None, due: date | None = None) -> None:
        r = self.steps.rowCount()
        self.steps.insertRow(r)
        self.steps.setRowHeight(r, ROW_HEIGHT)
        self.steps.setItem(r, 0, _item(r + 1, right=True))
        combo = QComboBox()
        for pid, name in self._processes:
            combo.addItem(name, pid)
        if process_id:
            i = combo.findData(process_id)
            combo.setCurrentIndex(max(i, 0))
        self.steps.setCellWidget(r, 1, combo)
        d = QDateEdit(_qdate(due))
        d.setCalendarPopup(True)
        d.setDisplayFormat("yyyy-MM-dd")
        self.steps.setCellWidget(r, 2, d)

    def _remove_step(self) -> None:
        rows = self.steps.selectionModel().selectedRows()
        r = rows[0].row() if rows else self.steps.rowCount() - 1
        if r >= 0:
            self.steps.removeRow(r)
            for i in range(self.steps.rowCount()):
                self.steps.setItem(i, 0, _item(i + 1, right=True))

    def _apply_group(self) -> None:
        if not self.job_id:
            return
        from datetime import timedelta
        with SessionLocal() as s:
            procs = production.group_steps(s, self.group.currentText())
        if not procs:
            _warn(self, "Process Group", "That group has no steps - add them under "
                                         "Master > Set Default Process.")
            return
        self.steps.setRowCount(0)
        start = _pydate(self.start)
        for i, p in enumerate(procs, start=1):
            self._add_step(p.id, start + timedelta(days=i))

    def _rows(self) -> list[dict]:
        out = []
        for r in range(self.steps.rowCount()):
            combo = self.steps.cellWidget(r, 1)
            d = self.steps.cellWidget(r, 2)
            out.append({"process_id": combo.currentData(), "due_date": _pydate(d)})
        return out

    def _save(self) -> None:
        if not self.job_id:
            _info(self, "Job Mapping", "Pick a job from the queue first.")
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            try:
                production.set_job_steps(s, job, self._rows())
                job.prod_date = _pydate(self.start)
                s.commit()
                n = job.job_no
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        keep = self.job_id
        self.refresh()
        self.job_id = keep
        self._load_job()
        _info(self, "Job Mapping", f"Route saved on job {n}.")

    def _copy_all(self) -> None:
        if not self.job_id:
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            try:
                if self.steps.rowCount() and not job.steps:
                    production.set_job_steps(s, job, self._rows())
                n = production.copy_route_to_siblings(s, job)
                s.commit()
                jn = job.job_no
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Copy To All", str(exc))
                return
        keep = self.job_id
        self.refresh()
        self.job_id = keep
        self._load_job()
        _info(self, "Copy To All", f"Route of job {jn} copied to {n} other job(s) of its order.")

    def _print(self) -> None:
        if not self.job_id:
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            tpl = documents.templates_for(s, "blank_front")
            if not tpl:
                return
            path = documents.print_job(s, job, tpl[0], getattr(self.user, "id", None))
            s.commit()
        _info(self, "Print", f"Saved {path}")


# --------------------------------------------------------------------------
# Planning Printing Options (T-04)
# --------------------------------------------------------------------------
class PrintingOptionsWidget(_Screen):
    def __init__(self, user=None, parent=None):
        super().__init__("Planning Printing Options", with_picker=False, parent=parent)
        self.user = user
        self.outer.removeWidget(self.header)
        self.header.setVisible(False)
        self.toolbar.addStretch(1)
        self.button("Templates…", self._templates)
        self.button("Open print folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(documents.PRINT_DIR))))

        form_box = QGroupBox("What to print")
        form = QGridLayout(form_box)
        form.setHorizontalSpacing(12)
        form.addWidget(QLabel("Order No"), 0, 0)
        self.order = QComboBox()
        form.addWidget(self.order, 0, 1)
        self.r_order = QRadioButton("every job of the order")
        self.r_order.setChecked(True)
        form.addWidget(self.r_order, 0, 2)
        form.addWidget(QLabel("Job No"), 1, 0)
        self.job = JobPicker()
        form.addWidget(self.job, 1, 1)
        self.r_job = QRadioButton("this job only")
        form.addWidget(self.r_job, 1, 2)
        self.outer.addWidget(form_box)

        prints_box = QGroupBox("PRINTS")
        pg = QGridLayout(prints_box)
        self.checks: dict[str, tuple[QCheckBox, QComboBox]] = {}
        for i, (kind, label) in enumerate(PrintTemplate.KINDS):
            cb = QCheckBox(label)
            cb.setChecked(kind == "job_sheet")
            combo = QComboBox()
            pg.addWidget(cb, i, 0)
            pg.addWidget(QLabel("Template"), i, 1)
            pg.addWidget(combo, i, 2)
            self.checks[kind] = (cb, combo)
        pg.setColumnStretch(2, 1)
        self.outer.addWidget(prints_box)

        bar = QHBoxLayout()
        b_print = QPushButton("Print")
        b_print.setObjectName("Primary")
        b_print.clicked.connect(self._print)
        bar.addWidget(b_print)
        b_exit = QPushButton("Exit")
        b_exit.clicked.connect(self.close_requested.emit)
        bar.addWidget(b_exit)
        bar.addStretch(1)
        self.outer.addLayout(bar)

        note = QLabel("The job sheet is generated from job data, not re-typed. Every "
                      "seeded layout is a marked PLACEHOLDER until the client's Word "
                      "format arrives (C-02) - then the template is edited to match it, "
                      "with no code change.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.outer.addWidget(note)

        log_box = QGroupBox("Recent prints")
        ll = QVBoxLayout(log_box)
        self.log = _table(["Printed at", "Print", "Job", "By", "File"])
        ll.addWidget(self.log)
        self.outer.addWidget(log_box, 1)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as s:
            self.order.clear()
            for o in s.scalars(select(Order).order_by(Order.order_no.desc())):
                client = s.get(Account, o.account_id) if o.account_id else None
                self.order.addItem(f"{o.order_no} · {client.name if client else 'stock'} · "
                                   f"{_s(o.order_date)}", o.id)
            for kind, (cb, combo) in self.checks.items():
                combo.clear()
                for t in documents.templates_for(s, kind):
                    combo.addItem(t.name, t.id)
                cb.setEnabled(combo.count() > 0)
            self.log.setRowCount(0)
            for pl in s.scalars(select(PrintLog).order_by(PrintLog.id.desc()).limit(50)):
                job = s.get(Job, pl.job_id) if pl.job_id else None
                user = s.get(User, pl.user_id) if pl.user_id else None
                r = self.log.rowCount()
                self.log.insertRow(r)
                for c, v in enumerate([pl.printed_at.strftime("%d-%b-%y %H:%M") if pl.printed_at
                                       else "", pl.kind, job.job_no if job else "",
                                       user.full_name if user else "", pl.file_path]):
                    self.log.setItem(r, c, _item(v))
            self.log.resizeColumnsToContents()

    def _print(self) -> None:
        wanted = [(kind, combo.currentData()) for kind, (cb, combo) in self.checks.items()
                  if cb.isChecked() and combo.currentData()]
        if not wanted:
            _info(self, "Print", "Tick at least one print.")
            return
        paths: list[Path] = []
        with SessionLocal() as s:
            if self.r_job.isChecked():
                jobs = [s.get(Job, self.job.job_id())] if self.job.job_id() else []
            else:
                jobs = list(s.scalars(select(Job).where(Job.order_id == self.order.currentData(),
                                                        Job.status != "cancelled")))
            if not jobs:
                _info(self, "Print", "Nothing to print for that selection.")
                return
            for job in jobs:
                for kind, tid in wanted:
                    tpl = s.get(PrintTemplate, tid)
                    paths.append(documents.print_job(s, job, tpl, getattr(self.user, "id", None)))
            s.commit()
        self.refresh()
        _info(self, "Print", f"{len(paths)} file(s) written to\n{documents.PRINT_DIR}")

    def _templates(self) -> None:
        from diagold.ui.specs import SPECS
        show_in_dialog(self, CrudWidget(SPECS["production_planning.print_templates"]),
                       "Print Templates", (1000, 640))
        self.refresh()


# --------------------------------------------------------------------------
# Order Day Book (T-06)
# --------------------------------------------------------------------------
DAY_BOOK_COLS = [("date", "DATE"), ("ord_no", "ORD NO"), ("vr_type", "VR TYPE"),
                 ("ref_no", "REF NO"), ("particulars", "PARTICULARS"), ("family", "Family"),
                 ("ref", "REF"), ("metal", "METAL"), ("loss_pct", "LOSS %"), ("col", "COL"),
                 ("size", "SIZE"), ("pcs", "PCS"), ("gwt_pcs", "G-WT/PCS"), ("del_dt", "DEL-DT"),
                 ("job_no", "JOB NO"), ("job_pcs", "JOB PCS"), ("prod_dt", "PROD-DT"),
                 ("priority", "PRIORITY"), ("remark", "REMARK"), ("sku", "SKU")]
_GROUPS = {"None": None, "Customer": "particulars", "Metal": "metal", "Date": "date",
           "Priority": "priority"}


def _financial_year() -> tuple[date, date]:
    today = date.today()
    start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    return start, date(start.year + 1, 3, 31)


class OrderDayBookWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)
        h1 = QLabel("Order Day Book")
        h1.setObjectName("H1")
        outer.addWidget(h1)
        bar = QHBoxLayout()
        fy0, fy1 = _financial_year()
        bar.addWidget(QLabel("From"))
        self.d_from = QDateEdit(_qdate(fy0))
        self.d_to = QDateEdit(_qdate(fy1))
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
        bar.addWidget(self.d_from)
        bar.addWidget(QLabel("To"))
        bar.addWidget(self.d_to)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        bar.addWidget(QLabel("Group"))
        self.group = QComboBox()
        self.group.addItems(list(_GROUPS))
        bar.addWidget(self.group)
        for label, slot in (("Refresh", self.refresh),
                            ("Export", lambda: _export_csv(self, self.table, "order_day_book.csv")),
                            ("Print", lambda: _print_table(self, "Order Day Book", self.table,
                                                           "order_day_book"))):
            b = QPushButton(label)
            b.clicked.connect(slot)
            bar.addWidget(b)
        outer.addLayout(bar)
        self.table = _table([l for _, l in DAY_BOOK_COLS])
        outer.addWidget(self.table, 1)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        outer.addWidget(self.status)
        self.search.textChanged.connect(self.refresh)
        self.group.currentTextChanged.connect(self.refresh)
        self.d_from.dateChanged.connect(self.refresh)
        self.d_to.dateChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as s:
            rows = production.order_day_book(s, _pydate(self.d_from), _pydate(self.d_to),
                                             self.search.text())
        key = _GROUPS[self.group.currentText()]
        if key:
            rows.sort(key=lambda r: (str(r.get(key) or ""), r["date"], r["ord_no"]))
        self.table.setRowCount(0)
        totals = {"pcs": 0, "gwt_pcs": Decimal("0"), "job_pcs": 0}
        sub = dict(totals)
        current: Any = None
        in_group = False

        def emit_subtotal(label: str) -> None:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, (k, _) in enumerate(DAY_BOOK_COLS):
                v = f"{label} total" if k == "particulars" else sub.get(k, "")
                self.table.setItem(r, c, _item(v, TINT_GROUP, right=k in totals, bold=True))

        for row in rows:
            if key and (not in_group or row.get(key) != current):
                if in_group:
                    emit_subtotal(_s(current))
                current, in_group = row.get(key), True
                sub = {"pcs": 0, "gwt_pcs": Decimal("0"), "job_pcs": 0}
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, (k, _) in enumerate(DAY_BOOK_COLS):
                self.table.setItem(r, c, _item(row.get(k), right=k in
                                               ("ord_no", "loss_pct", "pcs", "gwt_pcs",
                                                "job_no", "job_pcs")))
            for k in totals:
                v = row.get(k) or 0
                totals[k] += v
                sub[k] += v
        if in_group:
            emit_subtotal(_s(current))
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, (k, _) in enumerate(DAY_BOOK_COLS):
            v = "TOTAL" if k == "particulars" else totals.get(k, "")
            self.table.setItem(r, c, _item(v, TINT_GROUP, right=k in totals, bold=True))
        self.table.resizeColumnsToContents()
        self.status.setText(f"{len(rows)} order line(s) · {_s(_pydate(self.d_from))} to "
                            f"{_s(_pydate(self.d_to))}")


# --------------------------------------------------------------------------
# Options (Tools > Option) - the Production-Planning menu switches (T-07)
# --------------------------------------------------------------------------
class OptionsWidget(QWidget):
    nav_changed = Signal()

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)
        h1 = QLabel("Options")
        h1.setObjectName("H1")
        outer.addWidget(h1)
        box = QGroupBox("Production Planning menu")
        bl = QVBoxLayout(box)
        note = QLabel("The client said only two of these are used day to day and the rest "
                      "should go - but has not yet named the two (C-01). Until then the "
                      "items demonstrated on the call are on; the rest are off. Tick or "
                      "untick and Save - the menu changes without a code change.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        bl.addWidget(note)
        self.checks: dict[str, QCheckBox] = {}
        group = MENU_BY_KEY["production_planning"]
        with SessionLocal() as s:
            for item in group.items:
                cb = QCheckBox(item.label)
                cb.setChecked(settings.menu_visible(item.key, s))
                self.checks[item.key] = cb
                bl.addWidget(cb)
        outer.addWidget(box)
        fbox = QGroupBox("Behaviour")
        fl = QVBoxLayout(fbox)
        self.flags: dict[str, QCheckBox] = {}
        with SessionLocal() as s:
            for key, (label, default) in settings.FLAGS.items():
                cb = QCheckBox(label)
                cb.setChecked(settings.flag(key, default, s))
                self.flags[key] = cb
                fl.addWidget(cb)
        outer.addWidget(fbox)
        bar = QHBoxLayout()
        b = QPushButton("Save")
        b.setObjectName("Primary")
        b.clicked.connect(self._save)
        bar.addWidget(b)
        bar.addStretch(1)
        outer.addLayout(bar)
        outer.addStretch(1)

    def _save(self) -> None:
        with SessionLocal() as s:
            for key, cb in self.checks.items():
                settings.set_menu_visible(s, key, cb.isChecked())
            for key, cb in self.flags.items():
                settings.set_flag(s, key, cb.isChecked())
            s.commit()
        self.nav_changed.emit()
        _info(self, "Options", "Saved. The menu has been updated.")


# --------------------------------------------------------------------------
# Rtn To Inv - Stone, with Show Pending (18 Sept T-05)
# --------------------------------------------------------------------------
class StoneReturnWidget(_Screen):
    """Enter the job number, Show Pending lists what its bag still holds, tick
    the lines and quantities coming back. Returned credits the location the
    stones were picked from; Breakage is recorded separately.

    Metal comes back through the Manufacturing side; mould and finding
    returns are "not used, never needed" (18 Sept D1) - those classes sit
    behind a switch in Tools > Option.
    """

    def __init__(self, user=None, parent=None):
        super().__init__("Rtn To Inv – Stone", parent=parent)
        self.user = user
        self.btn_pending = self.button("Show Pending", self._show_pending, primary=True)
        self.button("Save", self._save)
        self.button("Print", self._print, secondary=True)
        self.button("Job Card Bag",
                    lambda: self.open_requested.emit("production_planning.job_card_bag"),
                    secondary=True)
        self._other = self.button("Other classes…", self._other_classes, secondary=True)
        self._other.setVisible(settings.flag("pp.return_other_classes", False))
        self.button("Exit", self.close_requested.emit, secondary=True)

        form = QHBoxLayout()
        form.setSpacing(10)
        form.addWidget(QLabel("Vr No"))
        self.vr_no = QLabel("—")
        self.vr_no.setObjectName("CardValue")
        self.vr_no.setStyleSheet("font-size:16px;")
        form.addWidget(self.vr_no)
        form.addSpacing(12)
        form.addWidget(QLabel("Date"))
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addWidget(self.date)
        form.addSpacing(12)
        form.addWidget(QLabel("Contact Person"))
        self.contact = QComboBox()
        self.contact.addItem("— none —", None)
        self.contact.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.contact.setMinimumContentsLength(14)
        form.addWidget(self.contact, 1)
        form.addSpacing(12)
        form.addWidget(QLabel("Remark"))
        self.remark = QLineEdit()
        form.addWidget(self.remark, 1)
        self.outer.addLayout(form)

        self.grid = QTableWidget(0, 12)
        self.grid.setHorizontalHeaderLabels(["Location", "Type", "SSKU", "Size", "Bal Pcs",
                                             "Bal Wt", "Return Pcs", "Return Wt", "Unit",
                                             "Amount", "JobNo", "Account"])
        self.grid.verticalHeader().setVisible(False)
        self.grid.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.grid.horizontalHeader().setStretchLastSection(True)
        self.grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.outer.addWidget(self.grid, 3)
        note = QLabel("Show Pending lists every stone still in the job's bag. Enter the pieces "
                      "coming back (weight follows the bag's average and can be changed). "
                      "Returned → the location's stock goes up; Breakage → leaves the bag only "
                      "(where it goes and how it is valued is open, 18 Sept Q5).")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.outer.addWidget(note)

        hist = QGroupBox("Return vouchers on this job")
        hl = QVBoxLayout(hist)
        self.history = _table(["Vr No", "Date", "Type", "SSKU", "Size", "Pcs", "Weight",
                               "Location", "Amount", "Remark"])
        hl.addWidget(self.history)
        self.outer.addWidget(hist, 2)
        self._rows: list[production.BagRow] = []
        self._pending_for: int | None = None
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as s:
            self.vr_no.setText(str(production.next_number(s, InventoryReturn.vr_no)))
            if self.contact.count() <= 1:
                for a in s.scalars(select(Account).order_by(Account.name)):
                    self.contact.addItem(a.name, a.id)
            job = s.get(Job, self.job_id) if self.job_id else None
            self.header.set_job(s, job)
            self.history.setRowCount(0)
            if job is not None:
                locs = {l.id: l for l in s.scalars(select(Location))}
                for ret in s.scalars(select(InventoryReturn)
                                     .where(InventoryReturn.job_id == job.id,
                                            InventoryReturn.material_class == "stone")
                                     .order_by(InventoryReturn.vr_no.desc())):
                    for l in ret.lines:
                        bag = s.get(JobBagLine, l.bag_line_id) if l.bag_line_id else None
                        sku = s.get(StoneSku, bag.stone_sku_id) if bag and bag.stone_sku_id else None
                        loc = locs.get(l.location_id or ret.location_id)
                        r = self.history.rowCount()
                        self.history.insertRow(r)
                        for c, v in enumerate([ret.vr_no, ret.vr_date, l.rtn_type,
                                               sku.sku_code if sku else l.particulars, l.size,
                                               l.pcs, l.weight, loc.name if loc else "",
                                               l.amount, l.remark]):
                            self.history.setItem(r, c, _item(v, right=c in (0, 5, 6, 8)))
                self.history.resizeColumnsToContents()
        if self._pending_for != self.job_id:
            self.grid.setRowCount(0)
            self._rows = []

    def _show_pending(self) -> None:
        if not self.job_id:
            _info(self, "Show Pending", "Enter the job number first.")
            return
        self.grid.setRowCount(0)
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            self._rows = [b for b in production.bag_ledger(s, job)
                          if b["bal"][0] > 0 or b["bal"][1] > 0]
            locs = [(l.id, l.name) for l in s.scalars(select(Location).order_by(Location.name))]
            client = s.get(Account, job.account_id) if job.account_id else None
            for b in self._rows:
                sku = s.get(StoneSku, b.line.stone_sku_id) if b.line.stone_sku_id else None
                price, unit = production.stone_price(s, b.line.stone_sku_id)
                bal_pcs, bal_wt = b["bal"]
                r = self.grid.rowCount()
                self.grid.insertRow(r)
                loc = QComboBox()
                for lid, name in locs:
                    loc.addItem(name, lid)
                if b.line.source_location_id:
                    loc.setCurrentIndex(max(loc.findData(b.line.source_location_id), 0))
                self.grid.setCellWidget(r, 0, loc)
                typ = QComboBox()
                typ.addItems(list(InventoryReturnLine.RTN_TYPES))
                self.grid.setCellWidget(r, 1, typ)
                self.grid.setItem(r, 2, _item(sku.sku_code if sku else b.line.particulars))
                self.grid.setItem(r, 3, _item(b.line.size))
                self.grid.setItem(r, 4, _item(bal_pcs, right=True))
                self.grid.setItem(r, 5, _item(bal_wt, right=True))
                pcs = QSpinBox()
                pcs.setRange(0, bal_pcs)
                wt = QDoubleSpinBox()
                wt.setDecimals(4)
                wt.setRange(0, float(bal_wt))
                avg = (bal_wt / bal_pcs) if bal_pcs else Decimal("0")
                amount = QTableWidgetItem("0.00")
                amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                def follow(n, wt=wt, avg=avg, amount=amount, price=price, unit=unit, pcs=pcs):
                    wt.blockSignals(True)
                    wt.setValue(float((avg * n).quantize(Decimal("0.0001"))))
                    wt.blockSignals(False)
                    amount.setText(str(production.stone_amount(
                        price, unit, pcs.value(), Decimal(str(wt.value())))))

                def reprice(_v, wt=wt, amount=amount, price=price, unit=unit, pcs=pcs):
                    amount.setText(str(production.stone_amount(
                        price, unit, pcs.value(), Decimal(str(wt.value())))))
                pcs.valueChanged.connect(follow)
                wt.valueChanged.connect(reprice)
                self.grid.setCellWidget(r, 6, pcs)
                self.grid.setCellWidget(r, 7, wt)
                self.grid.setItem(r, 8, _item(unit))
                self.grid.setItem(r, 9, amount)
                self.grid.setItem(r, 10, _item(job.job_no, right=True))
                self.grid.setItem(r, 11, _item(client.name if client else "stock"))
            self._pending_for = self.job_id
        self.grid.resizeColumnsToContents()
        if not self._rows:
            _info(self, "Show Pending", "Nothing is lying in this job's bag.")

    def lines(self) -> list[dict]:
        out = []
        for r, b in enumerate(self._rows):
            pcs = self.grid.cellWidget(r, 6).value()
            wt = Decimal(str(self.grid.cellWidget(r, 7).value()))
            if pcs <= 0 and wt <= 0:
                continue
            out.append({"bag_line_id": b.line.id, "pcs": pcs, "weight": wt,
                        "rtn_type": self.grid.cellWidget(r, 1).currentText(),
                        "location_id": self.grid.cellWidget(r, 0).currentData()})
        return out

    def _save(self) -> None:
        if not self.job_id or not self._rows:
            _info(self, "Save", "Show Pending first, then enter what is coming back.")
            return
        lines = self.lines()
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            try:
                ret = production.post_stone_return(
                    s, job, lines, vr_date=_pydate(self.date),
                    account_id=self.contact.currentData(),
                    user_id=getattr(self.user, "id", None), remark=self.remark.text().strip())
                s.commit()
                vr = ret.vr_no
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self._pending_for = None
        self.remark.clear()
        self.refresh()
        _info(self, "Saved", f"Return voucher {vr} posted. The bag is down and the "
                             "location's stock is up.")

    def _print(self) -> None:
        if not self.job_id:
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            title = f"Rtn To Inv – Stone — Job {job.job_no}"
        _print_table(self, title, self.history, f"stone_return_{self.job_id}")

    def _other_classes(self) -> None:
        from diagold.ui.specs import SPECS
        show_in_dialog(self, CrudWidget(SPECS["production_planning.inv_return"]),
                       "Return to Inventory – Metal / Mould / Finding", (1100, 640))

    def show_job(self, job_id: int) -> None:
        super().show_job(job_id)
        self._show_pending()


# --------------------------------------------------------------------------
# Opening stone balances (18 Sept C-03 / T-04)
# --------------------------------------------------------------------------
class OpeningStockWidget(QWidget):
    """Load the opening balance per location - by stone SKU (so the pieces can
    be issued) or by group only (pcs / ct / value, as the client will supply
    it). Each row is one 'opening' movement on the ledger."""

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)
        h1 = QLabel("Opening Stone Balances")
        h1.setObjectName("H1")
        outer.addWidget(h1)
        note = QLabel("The legacy Opening column was never filled, which is why its closings go "
                      "negative. Enter the balance each location held at the start of the "
                      "year - per stone SKU where known, otherwise per group. Ledger reports "
                      "pick it up at once.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        self.as_of = QDateEdit(_qdate(_financial_year()[0]))
        self.as_of.setCalendarPopup(True)
        self.as_of.setDisplayFormat("yyyy-MM-dd")
        self.location = QComboBox()
        self.sku = QComboBox()
        self.sku.addItem("— group only —", None)
        self.group = QComboBox()
        self.group.addItems(["DIAMOND", "POLKI", "COLOR STONE", "OTHER"])
        self.pcs = QSpinBox()
        self.pcs.setRange(0, 10_000_000)
        self.weight = QDoubleSpinBox()
        self.weight.setDecimals(3)
        self.weight.setRange(0, 100_000_000)
        self.value = QDoubleSpinBox()
        self.value.setDecimals(2)
        self.value.setRange(0, 10_000_000_000)
        self.value.setGroupSeparatorShown(True)
        with SessionLocal() as s:
            for l in s.scalars(select(Location).order_by(Location.name)):
                self.location.addItem(l.name, l.id)
            for k in s.scalars(select(StoneSku).where(StoneSku.is_active.is_(True))
                               .order_by(StoneSku.sku_code)):
                self.sku.addItem(k.sku_code, k.id)
        for combo in (self.location, self.sku, self.group):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(14)
        # Two rows of four: one row of eight fields is wider than a laptop.
        for i, (label, w) in enumerate((("As of", self.as_of), ("Location", self.location),
                                        ("Stone SKU", self.sku), ("Group", self.group))):
            form.addWidget(QLabel(label), 0, i)
            form.addWidget(w, 1, i)
        for i, (label, w) in enumerate((("Pcs", self.pcs), ("Weight (ct)", self.weight),
                                        ("Value", self.value))):
            form.addWidget(QLabel(label), 2, i)
            form.addWidget(w, 3, i)
        b = QPushButton("Add opening")
        b.setObjectName("Primary")
        b.clicked.connect(self._add)
        form.addWidget(b, 3, 3)
        for c in range(4):
            form.setColumnStretch(c, 1)
        outer.addLayout(form)
        self.table = _table(["As of", "Location", "Stone SKU / Group", "Size", "Pcs", "Weight",
                             "Value", "Remark"])
        outer.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        from diagold.db.models import StockMovement
        self.table.setRowCount(0)
        with SessionLocal() as s:
            locs = {l.id: l for l in s.scalars(select(Location))}
            for m in s.scalars(select(StockMovement).where(StockMovement.kind == "opening")
                               .order_by(StockMovement.mv_date.desc(), StockMovement.id.desc())
                               .limit(300)):
                sku = s.get(StoneSku, m.ref_id) if m.ref_id else None
                r = self.table.rowCount()
                self.table.insertRow(r)
                for c, v in enumerate([m.mv_date, locs[m.location_id].name if m.location_id in locs
                                       else "", sku.sku_code if sku else m.stone_group, m.size,
                                       m.pcs, m.weight, m.value, m.remark]):
                    self.table.setItem(r, c, _item(v, right=c in (4, 5, 6)))
        self.table.resizeColumnsToContents()

    def _add(self) -> None:
        if self.pcs.value() == 0 and self.weight.value() == 0:
            _info(self, "Opening", "Enter pieces or weight.")
            return
        with SessionLocal() as s:
            try:
                production.post_opening_stock(
                    s, self.location.currentData(), self.sku.currentData(), self.pcs.value(),
                    Decimal(str(self.weight.value())), as_of=_pydate(self.as_of),
                    group=self.group.currentText(),
                    value=Decimal(str(self.value.value())) if self.value.value() else None,
                    remark="opening balance")
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self.pcs.setValue(0)
        self.weight.setValue(0)
        self.value.setValue(0)
        self.refresh()
