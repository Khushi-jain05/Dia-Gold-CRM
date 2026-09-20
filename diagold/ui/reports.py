"""The shared report engine (18 September, T-01) and the Reports hub.

Every Production-Planning report is a :class:`ReportSpec` - columns, a query
function from ``services/reports.py``, and a few switches - rendered by one
:class:`ReportWidget`: date range in the header, the legacy toolbar (Print,
Search, Set Column, Options, Group, Adv. Filter, Export, Auto Filter), a
filter bar above grouped reports (the client's one complaint: "to see final
setting I scroll to the bottom"), a total row, a row counter, and a query
that runs on a worker thread so the screen never shows "(Not Responding)".
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QObject,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from diagold.db.session import SessionLocal
from diagold.services import documents, settings
from diagold.services import reports as R

TINT_KEY = QColor("#FBEEEE")
TINT_MEASURE = QColor("#EAF5EC")
TINT_GROUP = QColor("#E4E7EC")
TINT_TOTAL = QColor("#D9DDE5")
RED = QColor("#B3261E")


# --------------------------------------------------------------------------
# spec
# --------------------------------------------------------------------------
@dataclass
class Col:
    key: str
    label: str
    kind: str = "key"            # "key" (pink) | "measure" (green)
    decimals: int | None = None  # None -> 3 for weights, 2 for values
    group: str = ""              # column group label, e.g. "OPENING"
    total: bool = False          # summed in subtotal / total rows


@dataclass
class ReportSpec:
    key: str
    title: str
    columns: Callable[[date, date], list[Col]]
    query: Callable[..., list[dict]]
    group_by: str | None = None
    filter_column: str | None = None
    footer: Callable[[list[dict]], str] | None = None
    options: dict[str, tuple[str, bool]] = field(default_factory=dict)
    on_activate: Callable[["ReportWidget", dict], None] | None = None
    negative_key: str | None = None
    date_mode: str = "range"
    note: str = ""


def static(cols: list[Col]) -> Callable[[date, date], list[Col]]:
    return lambda _a, _b: cols


def _is_day_key(key: str) -> bool:
    return key.count("-") == 2 and key[:2].isdigit()


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------
def fmt(value: Any, col: Col | None = None) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%y")
    if isinstance(value, Decimal):
        places = col.decimals if col and col.decimals is not None else (
            3 if col and ("wt" in col.key or "weight" in col.key) else 2)
        return f"{value:,.{places}f}"
    if isinstance(value, float):
        places = col.decimals if col and col.decimals is not None else 2
        return f"{value:,.{places}f}"
    if isinstance(value, int) and col is not None and col.kind == "measure":
        return f"{value:,}"
    return str(value)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
class ReportModel(QAbstractTableModel):
    """Rows are (kind, dict): kind = row | group | subtotal | total."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols: list[Col] = []
        self.rows: list[tuple[str, dict]] = []
        self.negative_key: str | None = None
        self.row_numbers = False

    def load(self, cols: list[Col], rows: list[tuple[str, dict]]) -> None:
        self.beginResetModel()
        self.cols, self.rows = cols, rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.cols) + (1 if self.row_numbers else 0)

    def _col(self, c: int) -> Col | None:
        if self.row_numbers:
            c -= 1
        return self.cols[c] if 0 <= c < len(self.cols) else None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        if self.row_numbers and section == 0:
            return "#"
        col = self._col(section)
        if col is None:
            return None
        return f"{col.group} · {col.label}" if col.group else col.label

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        kind, row = self.rows[index.row()]
        col = self._col(index.column())
        first = 1 if self.row_numbers else 0
        if role == Qt.ItemDataRole.DisplayRole:
            if self.row_numbers and index.column() == 0:
                return str(row.get("_n", "")) if kind == "row" else ""
            if col is None:
                return ""
            if kind == "group":
                return row.get("_label", "") if index.column() == first else ""
            return fmt(row.get(col.key), col)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            v = row.get(col.key) if col else None
            if _is_num(v) or (col and col.kind == "measure"):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            if kind == "group":
                return TINT_GROUP
            if kind in ("subtotal", "total"):
                return TINT_TOTAL
            if col is None:
                return None
            return TINT_MEASURE if col.kind == "measure" else TINT_KEY
        if role == Qt.ItemDataRole.FontRole and kind in ("group", "subtotal", "total"):
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.ForegroundRole and kind == "row":
            if self.negative_key and row.get(self.negative_key):
                return RED
            if col is not None:
                v = row.get(col.key)
                if _is_num(v) and v < 0:
                    return RED
        return None

    def row_at(self, r: int) -> tuple[str, dict] | None:
        return self.rows[r] if 0 <= r < len(self.rows) else None


# --------------------------------------------------------------------------
# worker
# --------------------------------------------------------------------------
class _Worker(QObject):
    done = Signal(object)
    failed = Signal(str)
    ended = Signal()          # always fires, so the thread's loop always quits

    def __init__(self, fn: Callable[..., list[dict]], args: tuple, kwargs: dict):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.cancelled = False

    def run(self) -> None:
        try:
            try:
                with SessionLocal() as s:
                    rows = self.fn(s, *self.args, **self.kwargs)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                if not self.cancelled:
                    self.failed.emit(str(exc))
                return
            if not self.cancelled:
                self.done.emit(rows)
        finally:
            self.ended.emit()


# --------------------------------------------------------------------------
# dialogs
# --------------------------------------------------------------------------
class _ColumnsDialog(QDialog):
    def __init__(self, cols: list[Col], visible: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Column")
        self.setMinimumSize(380, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Tick the columns to show; move them to change the order."))
        self.list = QListWidget()
        keys = {c.key for c in cols}
        order = [k for k in visible if k in keys]
        order += [c.key for c in cols if c.key not in order]
        by_key = {c.key: c for c in cols}
        for k in order:
            c = by_key[k]
            it = QListWidgetItem(f"{c.group} · {c.label}" if c.group else c.label)
            it.setData(Qt.ItemDataRole.UserRole, k)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if k in visible else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        bar = QHBoxLayout()
        for label, d in (("Up", -1), ("Down", 1)):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, d=d: self._move(d))
            bar.addWidget(b)
        b_all = QPushButton("All")
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none = QPushButton("None")
        b_none.clicked.connect(lambda: self._set_all(False))
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        bar.addStretch(1)
        lay.addLayout(bar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _move(self, d: int) -> None:
        r = self.list.currentRow()
        if r < 0 or not (0 <= r + d < self.list.count()):
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + d, it)
        self.list.setCurrentRow(r + d)

    def _set_all(self, on: bool) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def visible(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]


class _AutoFilterDialog(QDialog):
    """Per-column: distinct values with a count, checkboxes, a text filter."""

    def __init__(self, col: Col, values: dict[str, int], selected: set[str] | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Auto Filter — {col.label}")
        self.setMinimumSize(360, 460)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to narrow the list…")
        self.search.textChanged.connect(self._narrow)
        lay.addWidget(self.search)
        self.list = QListWidget()
        for text, n in sorted(values.items(), key=lambda kv: kv[0].lower()):
            it = QListWidgetItem(f"{text or '(blank)'}   ({n})")
            it.setData(Qt.ItemDataRole.UserRole, text)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            on = selected is None or text in selected
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        self.count = QLabel(f"Count: {len(values)}")
        self.count.setObjectName("Muted")
        lay.addWidget(self.count)
        bar = QHBoxLayout()
        b_all = QPushButton("All")
        b_all.clicked.connect(lambda: self._set(True))
        b_none = QPushButton("None")
        b_none.clicked.connect(lambda: self._set(False))
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        bar.addStretch(1)
        lay.addLayout(bar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _narrow(self, text: str) -> None:
        t = text.strip().lower()
        shown = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            hide = bool(t) and t not in it.text().lower()
            it.setHidden(hide)
            shown += 0 if hide else 1
        self.count.setText(f"Count: {shown}")

    def _set(self, on: bool) -> None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def selected(self) -> set[str] | None:
        out = {self.list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(self.list.count())
               if self.list.item(i).checkState() == Qt.CheckState.Checked}
        return None if len(out) == self.list.count() else out


_OPS = ("contains", "=", "≠", ">", "<", "≥", "≤", "is blank", "not blank")


class _AdvFilterDialog(QDialog):
    def __init__(self, cols: list[Col], current: list[tuple[str, str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adv. Filter")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Rows must match every condition."))
        self.rows: list[tuple[QComboBox, QComboBox, QLineEdit]] = []
        for i in range(3):
            h = QHBoxLayout()
            c = QComboBox()
            c.addItem("— none —", None)
            for col in cols:
                c.addItem(col.label, col.key)
            o = QComboBox()
            o.addItems(_OPS)
            v = QLineEdit()
            if i < len(current):
                k, op, val = current[i]
                c.setCurrentIndex(max(c.findData(k), 0))
                o.setCurrentText(op)
                v.setText(val)
            h.addWidget(c, 2)
            h.addWidget(o, 1)
            h.addWidget(v, 2)
            lay.addLayout(h)
            self.rows.append((c, o, v))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def conditions(self) -> list[tuple[str, str, str]]:
        return [(c.currentData(), o.currentText(), v.text().strip())
                for c, o, v in self.rows if c.currentData()]


def _match(value: Any, op: str, text: str) -> bool:
    if op == "is blank":
        return value in (None, "")
    if op == "not blank":
        return value not in (None, "")
    if op == "contains":
        return text.lower() in fmt(value).lower()
    if _is_num(value):
        try:
            other: Any = Decimal(text.replace(",", ""))
        except Exception:  # noqa: BLE001
            return False
        v: Any = Decimal(str(value))
    elif isinstance(value, (date, datetime)):
        other = None
        for pattern in ("%d-%m-%y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                other = datetime.strptime(text, pattern).date()
                break
            except ValueError:
                continue
        if other is None:
            return False
        v = value if isinstance(value, date) else value.date()
    else:
        v, other = fmt(value).lower(), text.lower()
    return {"=": v == other, "≠": v != other, ">": v > other, "<": v < other,
            "≥": v >= other, "≤": v <= other}.get(op, False)


class _OptionsDialog(QDialog):
    def __init__(self, show_total: bool, row_numbers: bool, summary_only: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        form = QFormLayout(self)
        self.total = QCheckBox("Show total row")
        self.total.setChecked(show_total)
        self.numbers = QCheckBox("Show row numbers")
        self.numbers.setChecked(row_numbers)
        self.summary = QCheckBox("Summary only (group and total rows)")
        self.summary.setChecked(summary_only)
        for w in (self.total, self.numbers, self.summary):
            form.addRow(w)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


# --------------------------------------------------------------------------
# the report widget
# --------------------------------------------------------------------------
class ReportWidget(QWidget):
    open_requested = Signal(str)

    def __init__(self, spec: ReportSpec, user=None, parent=None, autorun: bool = True):
        super().__init__(parent)
        self.spec, self.user = spec, user
        self.job_id: int | None = None
        self._raw: list[dict] = []
        self._filtered: list[dict] = []
        self._cols: list[Col] = []
        self._visible: list[str] | None = self._load_columns()
        self._auto: dict[str, set[str]] = {}
        self._adv: list[tuple[str, str, str]] = []
        self._bar_values: set[str] | None = None
        self._bar_boxes: dict[str, QCheckBox] = {}
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        # Runs that were superseded before they finished: kept alive until
        # their thread ends, because a running QThread must never be deleted.
        self._orphans: list[tuple[QThread, _Worker]] = []
        self._started = datetime.now()
        self.show_total = True
        self.row_numbers = False
        self.summary_only = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(8)

        # Three short rows instead of one long one: on a laptop, with the
        # Reports list on the left, a single row of nine buttons plus search
        # and group ran past the right edge of the window.
        head = QHBoxLayout()
        h1 = QLabel(spec.title)
        h1.setObjectName("H1")
        h1.setWordWrap(True)
        head.addWidget(h1, 1)
        fy0, fy1 = R.fy_range()
        self.d_from = QDateEdit(QDate(fy0.year, fy0.month, fy0.day))
        self.d_to = QDateEdit(QDate(fy1.year, fy1.month, fy1.day))
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
        if spec.date_mode == "range":
            head.addWidget(QLabel("From"))
            head.addWidget(self.d_from)
            head.addWidget(QLabel("To"))
            head.addWidget(self.d_to)
        self.btn_run = QPushButton("Run")
        self.btn_run.setObjectName("Primary")
        self.btn_run.clicked.connect(self.run)
        head.addWidget(self.btn_run)
        outer.addLayout(head)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(120)
        self.search.textChanged.connect(self._rebuild)
        row2.addWidget(self.search, 1)
        row2.addWidget(QLabel("Group"))
        self.group = QComboBox()
        self.group.setMinimumWidth(140)
        self.group.currentIndexChanged.connect(lambda _i: self._rebuild())
        row2.addWidget(self.group)
        outer.addLayout(row2)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        for label, slot in (("Print", self._print), ("Set Column", self._set_columns),
                            ("Options", self._options), ("Adv. Filter", self._adv_filter),
                            ("Export", self._export), ("Auto Filter", self._auto_filter)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        self.option_boxes: dict[str, QCheckBox] = {}
        for key, (label, default) in spec.options.items():
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.toggled.connect(lambda _c: self.run())
            self.option_boxes[key] = cb
            bar.addWidget(cb)
        outer.addLayout(bar)

        # Filter bar: restrict a grouped report to chosen groups in one click.
        self.filter_box = QWidget()
        fb = QHBoxLayout(self.filter_box)
        fb.setContentsMargins(0, 0, 0, 0)
        fb.setSpacing(6)
        lab = QLabel("Show:")
        lab.setObjectName("Muted")
        fb.addWidget(lab)
        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setFixedHeight(40)
        self.filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.filter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filter_inner = QWidget()
        self.filter_layout = QHBoxLayout(self.filter_inner)
        self.filter_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_layout.setSpacing(4)
        self.filter_scroll.setWidget(self.filter_inner)
        fb.addWidget(self.filter_scroll, 1)
        self.filter_box.setVisible(bool(spec.filter_column))
        outer.addWidget(self.filter_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.model = ReportModel(self)
        self.model.negative_key = spec.negative_key
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(26)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.doubleClicked.connect(self._activate)
        outer.addWidget(self.view, 1)

        foot = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        foot.addWidget(self.status, 1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel)
        foot.addWidget(self.btn_cancel)
        outer.addLayout(foot)
        if spec.note:
            note = QLabel(spec.note)
            note.setObjectName("Muted")
            note.setWordWrap(True)
            outer.addWidget(note)
        if autorun:
            self.run()

    # -- dates / options ------------------------------------------------
    def dates(self) -> tuple[date, date]:
        a, b = self.d_from.date(), self.d_to.date()
        return date(a.year(), a.month(), a.day()), date(b.year(), b.month(), b.day())

    def set_dates(self, d_from: date, d_to: date) -> None:
        self.d_from.setDate(QDate(d_from.year, d_from.month, d_from.day))
        self.d_to.setDate(QDate(d_to.year, d_to.month, d_to.day))

    def _opts(self) -> dict[str, bool]:
        return {k: cb.isChecked() for k, cb in self.option_boxes.items()}

    # -- running ----------------------------------------------------------
    def run(self) -> None:
        if self._thread is not None:
            self._detach()          # let the old run finish on its own, ignored
        d0, d1 = self.dates()
        if d0 > d1:
            self.status.setText("From is after To.")
            return
        self._cols = self.spec.columns(d0, d1)
        self.progress.setVisible(True)
        self.btn_cancel.setVisible(True)
        self.btn_run.setEnabled(False)
        self.status.setText("Running…")
        worker = _Worker(self.spec.query, (d0, d1), self._opts())
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.ended.connect(thread.quit)
        # Only the run that is still current resets the screen; a superseded
        # thread just tidies itself away when it finishes.
        thread.finished.connect(lambda t=thread: self._cleanup(t))
        self._worker, self._thread = worker, thread
        self._started = datetime.now()
        thread.start()

    def _detach(self) -> None:
        """Stop listening to the current run without destroying its thread."""
        if self._worker is not None:
            self._worker.cancelled = True
            for sig, slot in ((self._worker.done, self._loaded),
                              (self._worker.failed, self._failed)):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if self._thread is not None:
            self._orphans.append((self._thread, self._worker))
        self._thread = None
        self._worker = None

    def _cleanup(self, thread: QThread | None = None) -> None:
        if thread is not None and thread is not self._thread:
            thread.deleteLater()
            self._orphans = [(t, w) for t, w in self._orphans if t is not thread]
            return
        self.progress.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_run.setEnabled(True)
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def _cancel(self) -> None:
        self._detach()
        self.progress.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_run.setEnabled(True)
        self.status.setText("Cancelled.")

    def _failed(self, message: str) -> None:
        self.status.setText(f"Could not run: {message}")

    def _loaded(self, rows: list[dict]) -> None:
        self._raw = rows
        for n, r in enumerate(rows, start=1):
            r["_n"] = n
        self._auto.clear()
        self._bar_values = None
        self._fill_group_combo()
        self._fill_filter_bar()
        self._rebuild()
        secs = (datetime.now() - self._started).total_seconds()
        self.status.setText(self.status.text() + f"   ·   {secs:.2f} s")

    def wait(self, timeout_ms: int = 10000) -> None:
        """Block until the current run (and any superseded one) finishes."""
        from PySide6.QtWidgets import QApplication
        t0 = datetime.now()
        while (self._thread is not None or self._orphans) and \
                (datetime.now() - t0).total_seconds() * 1000 < timeout_ms:
            QApplication.processEvents()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt name
        # Never let a running thread be destroyed with the widget.
        for t, _w in [(self._thread, self._worker)] + self._orphans:
            if t is not None and t.isRunning():
                t.quit()
                t.wait(5000)
        super().closeEvent(event)

    # -- columns / grouping ----------------------------------------------
    def _load_columns(self) -> list[str] | None:
        with SessionLocal() as s:
            raw = settings.get_setting(s, f"report.{self.spec.key}.columns", "")
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def visible_cols(self) -> list[Col]:
        if not self._visible:
            return list(self._cols)
        by_key = {c.key: c for c in self._cols}
        out = [by_key[k] for k in self._visible if k in by_key]
        # Day columns are born per run and were not around when the order was
        # saved; they still show, after the chosen ones.
        known = set(self._visible)
        out += [c for c in self._cols if c.key not in known and _is_day_key(c.key)]
        return out or list(self._cols)

    def _fill_group_combo(self) -> None:
        self.group.blockSignals(True)
        current = self.group.currentData()
        self.group.clear()
        self.group.addItem("— none —", None)
        for c in self._cols:
            if c.kind == "key" and not _is_day_key(c.key):
                self.group.addItem(c.label, c.key)
        want = current if current is not None else self.spec.group_by
        idx = self.group.findData(want) if want else 0
        self.group.setCurrentIndex(max(idx, 0))
        self.group.blockSignals(False)

    def _fill_filter_bar(self) -> None:
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._bar_boxes = {}
        if not self.spec.filter_column:
            return
        values = sorted({fmt(r.get(self.spec.filter_column)) for r in self._raw},
                        key=lambda v: v.lower())
        b_all = QPushButton("All")
        b_all.setFixedHeight(26)
        b_all.clicked.connect(lambda: self._bar_set(None))
        self.filter_layout.addWidget(b_all)
        for v in values:
            cb = QCheckBox(v or "(blank)")
            cb.setChecked(True)
            cb.toggled.connect(lambda _c: self._bar_changed())
            self._bar_boxes[v] = cb
            self.filter_layout.addWidget(cb)
        self.filter_layout.addStretch(1)

    def _bar_set(self, values: set[str] | None) -> None:
        for v, cb in self._bar_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(values is None or v in values)
            cb.blockSignals(False)
        self._bar_changed()

    def _bar_changed(self) -> None:
        on = {v for v, cb in self._bar_boxes.items() if cb.isChecked()}
        self._bar_values = None if len(on) == len(self._bar_boxes) else on
        self._rebuild()

    def only_group(self, value: str) -> None:
        """Show a single group - what the filter bar does in one click."""
        self._bar_set({value})

    def jump_to_group(self, value: str) -> None:
        for i, (kind, row) in enumerate(self.model.rows):
            if kind == "group" and row.get("_value") == value:
                self.view.scrollTo(self.model.index(i, 0),
                                   QAbstractItemView.ScrollHint.PositionAtTop)
                self.view.selectRow(i)
                return

    # -- filtering + display rows -----------------------------------------
    def _passes(self, row: dict) -> bool:
        term = self.search.text().strip().lower()
        cols = self.visible_cols()
        if term and term not in " ".join(fmt(row.get(c.key), c) for c in cols).lower():
            return False
        for key, allowed in self._auto.items():
            if fmt(row.get(key)) not in allowed:
                return False
        for key, op, text in self._adv:
            if not _match(row.get(key), op, text):
                return False
        if self._bar_values is not None and self.spec.filter_column:
            if fmt(row.get(self.spec.filter_column)) not in self._bar_values:
                return False
        return True

    def _sum_row(self, rows: list[dict], label_key: str | None, label: str) -> dict:
        out: dict[str, Any] = {}
        for c in self._cols:
            if c.total:
                vals = [r.get(c.key) for r in rows if _is_num(r.get(c.key))]
                if vals:
                    out[c.key] = sum(vals)
        if label_key:
            out[label_key] = label
        return out

    def _rebuild(self) -> None:
        cols = self.visible_cols()
        self._filtered = [r for r in self._raw if self._passes(r)]
        gkey = self.group.currentData()
        display: list[tuple[str, dict]] = []
        rows = list(self._filtered)
        first_key = cols[0].key if cols else None
        if gkey:
            rows.sort(key=lambda r: (fmt(r.get(gkey)).lower(), r.get("_n", 0)))
            glabel = next((c.label for c in self._cols if c.key == gkey), gkey)
            current: Any = None
            bucket: list[dict] = []
            started = False

            def flush() -> None:
                if bucket:
                    display.append(("subtotal", self._sum_row(
                        bucket, first_key, f"{fmt(current)} Total ({len(bucket)})")))

            for r in rows:
                v = r.get(gkey)
                if not started or fmt(v) != fmt(current):
                    flush()
                    current, started = v, True
                    bucket = []
                    display.append(("group", {
                        "_label": f"{glabel.upper()} : {fmt(v) or '(blank)'}",
                        "_value": fmt(v)}))
                if not self.summary_only:
                    display.append(("row", r))
                bucket.append(r)
            flush()
        elif not self.summary_only:
            display = [("row", r) for r in rows]
        if self.show_total:
            display.append(("total", self._sum_row(rows, first_key, f"TOTAL ({len(rows)})")))
        self.model.row_numbers = self.row_numbers
        self.model.load(cols, display)
        self.view.resizeColumnsToContents()
        # A long remark must not push every other column off the screen; the
        # user can still drag a column wider.
        header = self.view.horizontalHeader()
        for c in range(self.model.columnCount()):
            if header.sectionSize(c) > 260:
                header.resizeSection(c, 260)
        parts = [f"{len(rows)} row(s)"]
        if len(rows) != len(self._raw):
            parts.append(f"of {len(self._raw)}")
        if self.spec.footer:
            try:
                parts.append(self.spec.footer(rows))
            except Exception:  # noqa: BLE001
                pass
        active = len(self._auto) + len(self._adv) + (1 if self._bar_values is not None else 0)
        if active:
            parts.append(f"{active} filter(s) on")
        self.status.setText("   ·   ".join(parts))

    # -- toolbar actions ------------------------------------------------
    def _set_columns(self) -> None:
        dlg = _ColumnsDialog(self._cols, [c.key for c in self.visible_cols()], self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._visible = dlg.visible()
        with SessionLocal() as s:
            settings.set_setting(s, f"report.{self.spec.key}.columns", json.dumps(self._visible))
            s.commit()
        self._rebuild()

    def _options(self) -> None:
        dlg = _OptionsDialog(self.show_total, self.row_numbers, self.summary_only, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.show_total = dlg.total.isChecked()
        self.row_numbers = dlg.numbers.isChecked()
        self.summary_only = dlg.summary.isChecked()
        self._rebuild()

    def _current_col(self) -> Col | None:
        cols = self.visible_cols()
        c = self.view.currentIndex().column() - (1 if self.row_numbers else 0)
        return cols[c] if 0 <= c < len(cols) else (cols[0] if cols else None)

    def distinct_counts(self, key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._raw:
            v = fmt(r.get(key))
            counts[v] = counts.get(v, 0) + 1
        return counts

    def set_auto_filter(self, key: str, values: set[str] | None) -> None:
        if values is None:
            self._auto.pop(key, None)
        else:
            self._auto[key] = values
        self._rebuild()

    def _auto_filter(self) -> None:
        col = self._current_col()
        if col is None:
            return
        dlg = _AutoFilterDialog(col, self.distinct_counts(col.key), self._auto.get(col.key), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_auto_filter(col.key, dlg.selected())

    def set_adv_filter(self, conditions: list[tuple[str, str, str]]) -> None:
        self._adv = conditions
        self._rebuild()

    def _adv_filter(self) -> None:
        dlg = _AdvFilterDialog(self._cols, self._adv, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_adv_filter(dlg.conditions())

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{self.spec.key}.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        self.export_csv(path)
        QMessageBox.information(self, "Export", f"Saved {path}")

    def export_csv(self, path: str) -> int:
        cols = self.visible_cols()
        n = 0
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([f"{c.group} {c.label}".strip() for c in cols])
            for kind, row in self.model.rows:
                if kind == "group":
                    w.writerow([row.get("_label", "")])
                    continue
                w.writerow([fmt(row.get(c.key), c) for c in cols])
                n += 1
        return n

    def _print(self) -> None:
        cols = self.visible_cols()
        d0, d1 = self.dates()
        head = "".join(f"<th>{c.group + ' ' if c.group else ''}{c.label}</th>" for c in cols)
        body = []
        for kind, row in self.model.rows:
            if kind == "group":
                body.append(f"<tr style='background:#e4e7ec'><td colspan='{len(cols)}'>"
                            f"<b>{row.get('_label', '')}</b></td></tr>")
                continue
            style = " style='background:#d9dde5;font-weight:bold'" if kind != "row" else ""
            body.append(f"<tr{style}>" + "".join(
                f"<td align='{'right' if _is_num(row.get(c.key)) else 'left'}'>"
                f"{fmt(row.get(c.key), c)}</td>" for c in cols) + "</tr>")
        html = (f"<h2>{self.spec.title}</h2><p>{d0.strftime('%d-%m-%Y')} to "
                f"{d1.strftime('%d-%m-%Y')} · {len(self._filtered)} row(s) · printed "
                f"{datetime.now().strftime('%d-%b-%Y %H:%M')}</p>"
                f"<table border='1' cellspacing='0' cellpadding='3' width='100%'>"
                f"<tr style='background:#eee'>{head}</tr>{''.join(body)}</table>")
        path = documents.PRINT_DIR / f"{self.spec.key}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        documents.to_pdf(html, path)
        QMessageBox.information(self, "Print", f"Saved {path}")

    def _activate(self, index) -> None:
        got = self.model.row_at(index.row())
        if got is None:
            return
        kind, row = got
        if kind == "row" and self.spec.on_activate is not None:
            self.spec.on_activate(self, row)

    def open_job(self, row: dict, key: str = "production_planning.job_history") -> None:
        if row.get("_job_id"):
            self.job_id = row["_job_id"]
            self.open_requested.emit(key)


# --------------------------------------------------------------------------
# report specs
# --------------------------------------------------------------------------
def _day_cols(d0: date, d1: date) -> list[Col]:
    return [Col(R.day_label(d), R.day_label(d), "measure", 0, total=True)
            for d in R._day_keys(d0, d1)]


def _job_analysis_cols(d0: date, d1: date) -> list[Col]:
    return [Col("job_no", "JOB NO"), Col("sku", "SKU"), Col("ord_no", "ORD NO"),
            Col("orddate", "ORDDATE"), Col("refno", "REFNO"), Col("client", "CLIENT"),
            Col("prod_due", "PROD DUE"), Col("delivered", "DELIVERED"),
            Col("overdays", "OVERDAYS", "measure", 0)] + _day_cols(d0, d1) + [
            Col("total", "TOTAL", "measure", 0, total=True)]


def _process_analysis_cols(d0: date, d1: date) -> list[Col]:
    return [Col("process", "PROCESS"), Col("job_no", "JOB NO"), Col("sku", "SKU"),
            Col("ord_no", "ORD NO"), Col("orddate", "ORDDATE"), Col("client", "CLIENT"),
            Col("proc_due", "PROC DUE"), Col("overdays", "OVERDAYS", "measure", 0)] \
        + _day_cols(d0, d1) + [Col("total", "TOTAL", "measure", 0, total=True)]


_LEDGER_COLS = [Col("location", "LOCATION"), Col("group", "STONE GROUP")] + [
    Col(f"{b}_{m}", lab, "measure", dec, group=b.upper(), total=True)
    for b in ("opening", "inward", "outward", "closing")
    for m, lab, dec in (("pcs", "PCS", 0), ("wt", "WEIGHT", 3), ("val", "VALUE", 2))]


def _drill_stock(widget: ReportWidget, row: dict) -> None:
    """The vouchers behind one location x group line."""
    d0, d1 = widget.dates()
    with SessionLocal() as s:
        rows = R.stock_drilldown(s, row["_location_id"], row["group"], d0, d1)
    spec = ReportSpec(
        key="stock_drill", title=f"{row['location']} · {row['group']} — movements",
        columns=static([Col("date", "DATE"), Col("bucket", "PERIOD"), Col("kind", "KIND"),
                        Col("vr", "VR NO"), Col("ref", "REF"), Col("ssku", "SSKU"),
                        Col("size", "SIZE"), Col("job_no", "JOB NO"),
                        Col("pcs", "PCS", "measure", 0, total=True),
                        Col("weight", "WEIGHT", "measure", 3, total=True),
                        Col("value", "VALUE", "measure", 2, total=True)]),
        query=lambda _s, _a, _b, **_k: rows, date_mode="none",
        on_activate=lambda w, r: w.open_job(r))
    from diagold.ui.production import show_in_dialog
    w = ReportWidget(spec, widget.user)
    w.open_requested.connect(lambda key: (setattr(widget, "job_id", w.job_id),
                                          widget.open_requested.emit(key)))
    show_in_dialog(widget, w, spec.title, (1100, 600))


def build_specs() -> dict[str, ReportSpec]:
    from diagold.services.production import order_day_book

    def money(k: str, l: str) -> Col:
        return Col(k, l, "measure", 2, total=True)

    def wt(k: str, l: str) -> Col:
        return Col(k, l, "measure", 3, total=True)

    def pcs(k: str, l: str) -> Col:
        return Col(k, l, "measure", 0, total=True)

    return {
        # -- day books ---------------------------------------------------
        "order_day_book": ReportSpec(
            key="order_day_book", title="Order Day Book",
            columns=static([Col("date", "DATE"), Col("ord_no", "ORD NO"), Col("vr_type", "VR TYPE"),
                            Col("ref_no", "REF NO"), Col("particulars", "PARTICULARS"),
                            Col("family", "Family"), Col("ref", "REF"), Col("metal", "METAL"),
                            Col("loss_pct", "LOSS %", "measure", 2), Col("col", "COL"),
                            Col("size", "SIZE"), pcs("pcs", "PCS"), wt("gwt_pcs", "G-WT/PCS"),
                            Col("del_dt", "DEL-DT"), Col("job_no", "JOB NO"),
                            pcs("job_pcs", "JOB PCS"), Col("prod_dt", "PROD-DT"),
                            Col("priority", "PRIORITY"), Col("remark", "REMARK"),
                            Col("sku", "SKU")]),
            query=lambda s, a, b, **_k: order_day_book(s, a, b)),
        "job_card_day_book": ReportSpec(
            key="job_card_day_book", title="Job Card Day-Book",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("ord_no", "ORD NO"),
                            Col("ref_no", "REF NO"), Col("client", "CLIENT"), Col("sku", "SKU"),
                            Col("design", "DESIGN"), Col("c_ref", "C-REF"), Col("metal", "METAL"),
                            Col("col", "COL"), Col("size", "SIZE"), Col("del_dt", "DEL-DT"),
                            Col("job_no", "JOBNO"), pcs("job_pcs", "JOB PCS"),
                            Col("p_del_dt", "P DEL-DT"), Col("open_loc", "OPEN_LOC"),
                            Col("cancel", "CANCEL")]),
            query=lambda s, a, b, **_k: R.job_card_day_book(s, a, b),
            on_activate=lambda w, r: w.open_job(r)),
        "job_mapping_day_book": ReportSpec(
            key="job_mapping_day_book", title="Job Mapping Day Book",
            columns=static([Col("date", "DATE"), Col("job_no", "JOBNO"), Col("sku", "SKU"),
                            Col("client", "CLIENT"), Col("ord_no", "ORD NO"), Col("route", "ROUTE"),
                            pcs("steps", "STEPS"), Col("first_due", "FIRST DUE"),
                            Col("last_due", "LAST DUE"), Col("status", "STATUS")]),
            query=lambda s, a, b, **_k: R.job_mapping_day_book(s, a, b),
            on_activate=lambda w, r: w.open_job(r, "production_planning.job_mapping")),
        "inv_rtn_stone_day_book": ReportSpec(
            key="inv_rtn_stone_day_book", title="Inv Rtn Stone Day Book",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"), Col("location", "LOCATION"),
                            Col("type", "TYPE"), Col("ssku", "SSKU"), Col("size", "SIZE"),
                            Col("stone", "STONE"), Col("job_no", "JOBNO"), pcs("pcs", "PCS"),
                            wt("weight", "WEIGHT"), Col("price_unit", "PRICE UNIT"),
                            money("amount", "AMOUNT")]),
            query=lambda s, a, b, **_k: R.inv_rtn_stone_day_book(s, a, b),
            on_activate=lambda w, r: w.open_job(r, "production_planning.job_card_bag"),
            note="What was returned - or broken - each day, from which job bag, to which "
                 "location. Includes returns posted from the Job Card Bag screen."),
        # -- outstanding -------------------------------------------------
        "inv_rtn_os_stone": ReportSpec(
            key="inv_rtn_os_stone", title="Inv Rtn O/s Stone",
            columns=static([Col("location", "LOCATION"), Col("job_no", "JOBNO"), Col("sku", "SKU"),
                            Col("cref", "CREF"), Col("ssku", "SSKU"), Col("size", "SIZE"),
                            Col("lotno", "LOTNO"), Col("stype", "STYPE"), Col("type", "TYPE"),
                            pcs("pcs", "PCS"), wt("weight", "WEIGHT"),
                            Col("price_unit", "PRICE UNIT"), money("amount", "AMOUNT"),
                            Col("ccode", "CCODE")]),
            query=lambda s, a, b, **_k: R.inv_rtn_os_stone(s, a, b),
            on_activate=lambda w, r: w.open_job(r, "production_planning.job_card_bag"),
            note="Stones still lying in the bags of unfinished jobs. A line drops out when "
                 "the job card is finished or the stones are returned (18 Sept D3)."),
        "job_os_stone": ReportSpec(
            key="job_os_stone", title="Job O/s – Stone (Job Request Outstanding)",
            columns=static([Col("job_no", "JOB NO"), Col("sku", "SKU"), Col("location", "LOCATION"),
                            pcs("job_pcs", "JOB PCS"), Col("ssku", "SSKU"), Col("stone", "STONE"),
                            Col("shape", "SHAPE"), Col("quality", "QUALITY"), Col("size", "SIZE"),
                            pcs("req_pcs", "REQ PCS"), wt("req_wt", "REQ WT"),
                            pcs("iss_pcs", "ISS PCS"), wt("iss_wt", "ISS WT"),
                            pcs("pnd_pcs", "PND PCS"), wt("pnd_wt", "PND WT"),
                            pcs("cl_pcs", "CL PCS"), wt("cl_wt", "CL WT"),
                            Col("ordno", "ORDNO"), Col("orddt", "ORDDT")]),
            query=lambda s, a, b, **_k: R.job_os_stone(s, a, b),
            on_activate=lambda w, r: w.open_job(r, "production_planning.job_card_bag"),
            note="Order-date range. PND = REQ − issued into the bag; CL = requirement of a "
                 "cancelled job. Options ▸ Summary only gives the footer view."),
        "job_os_pct": ReportSpec(
            key="job_os_pct", title="Inv O/S (Job O/s %)",
            columns=static([Col("job_no", "JOBNO"), Col("sku", "SKU"), Col("cref", "CREF"),
                            pcs("st_pcs", "ST PCS"), Col("st_pct", "ST %", "measure", 0),
                            pcs("find_pcs", "FIND PCS"), Col("find_pct", "FIND %", "measure", 0),
                            pcs("mould_pcs", "MOULD PCS"),
                            Col("mould_pct", "MOULD %", "measure", 0),
                            Col("ord_no", "ORD NO"), Col("orddt", "ORDDT"), Col("ref", "REF"),
                            Col("ccode", "CCODE"), Col("deldt", "DELDT")]),
            query=lambda s, a, b, **_k: R.job_os_pct(s, a, b),
            on_activate=lambda w, r: w.open_job(r, "production_planning.job_card_bag"),
            note="The client does not use this one (\"the vendor built it\"); kept last. "
                 "Double-click drills to the Job Card Bag."),
        # -- analysis ----------------------------------------------------
        "job_analysis": ReportSpec(
            key="job_analysis", title="Job Analysis", columns=_job_analysis_cols,
            query=lambda s, a, b, late_only=False, **_k: R.job_analysis(s, a, b, late_only),
            options={"late_only": ("Late deliveries only", False)},
            on_activate=lambda w, r: w.open_job(r),
            note="Overdays are counted as of the From date. A day column shows 1 when the job "
                 "was open that day. Open = pending / mapped / in progress, cancelled excluded "
                 "- to confirm (18 Sept C-01)."),
        "process_analysis": ReportSpec(
            key="process_analysis", title="Process Analysis (Production Analysis)",
            columns=_process_analysis_cols,
            query=lambda s, a, b, **_k: R.process_analysis(s, a, b),
            group_by="process", filter_column="process",
            on_activate=lambda w, r: w.open_job(r),
            note="Grouped by the job's current step: the last step issued but not received, "
                 "else the next step not yet received (to confirm, C-01). Tick a process in "
                 "the Show bar to see only that group - no scrolling to the bottom."),
        "job_card_analysis_stone": ReportSpec(
            key="job_card_analysis_stone",
            title="Job Card Analysis – Stone (Job Inventory – Stone)",
            columns=static(_LEDGER_COLS),
            query=lambda s, a, b, **_k: R.job_card_analysis_stone(s, a, b),
            negative_key="_negative", on_activate=_drill_stock,
            note="CLOSING = OPENING + INWARD − OUTWARD, derived. Returns from job bags count as "
                 "inward, breakage as outward. Negative closings are red: load the opening "
                 "balances (Production Planning ▸ Opening Stone Balances). Double-click a line "
                 "for the vouchers behind it."),
        "job_stock_analysis": ReportSpec(
            key="job_stock_analysis", title="Job Stock Analysis",
            columns=static([Col("ord_dt", "ORD DT"), Col("refno", "REFNO"), Col("party", "PARTY"),
                            Col("job_no", "JOBNO"), Col("sku", "SKU"), Col("stock_dt", "STOCK DT"),
                            Col("days", "DAYS", "measure", 0)]),
            query=lambda s, a, b, **_k: R.job_stock_analysis(s, a, b),
            footer=R.lead_time_footer, on_activate=lambda w, r: w.open_job(r),
            note="DAYS = STOCK DT − ORD DT; blank while the job is open. STOCK DT is the "
                 "receipt of the last route step (MFG transfer once that module exists - Q8)."),
        # -- data quality ------------------------------------------------
        "data_quality": ReportSpec(
            key="data_quality", title="Data Quality",
            columns=static([Col("check", "CHECK"), Col("key", "KEY"), Col("detail", "DETAIL")]),
            query=lambda s, a, b, **_k: R.data_quality(s, a, b),
            group_by="check", filter_column="check",
            on_activate=lambda w, r: w.open_job(r),
            note="The migration exception checks from the 18 Sept notes, run on this database. "
                 "They run on the legacy data once server access arrives (S1 C-01)."),
    }


SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Day Books", ("job_card_day_book", "job_mapping_day_book", "inv_rtn_stone_day_book",
                   "order_day_book")),
    ("Outstanding", ("inv_rtn_os_stone", "job_os_stone")),
    ("Analysis", ("job_analysis", "process_analysis", "job_card_analysis_stone",
                  "job_stock_analysis")),
    ("Other", ("job_os_pct", "data_quality")),
)


class ReportsHub(QWidget):
    """Production Planning ▸ Reports: the list on the left, the report on the right."""

    open_requested = Signal(str)

    def __init__(self, user=None, parent=None, first: str = "job_analysis"):
        super().__init__(parent)
        self.user = user
        self.job_id: int | None = None
        self.specs = build_specs()
        self._widgets: dict[str, ReportWidget] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)
        self.list = QListWidget()
        self.list.setMinimumWidth(150)
        self.list.setMaximumWidth(320)
        for section, keys in SECTIONS:
            head = QListWidgetItem(section.upper())
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            f = head.font()
            f.setBold(True)
            head.setFont(f)
            self.list.addItem(head)
            for k in keys:
                it = QListWidgetItem("   " + self.specs[k].title.split(" (")[0])
                it.setData(Qt.ItemDataRole.UserRole, k)
                self.list.addItem(it)
        self.list.currentItemChanged.connect(self._pick)
        split.addWidget(self.list)
        self.stack = QStackedWidget()
        split.addWidget(self.stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 900])
        self.show_report(first)

    def _pick(self, current, _previous) -> None:
        if current is None or not current.data(Qt.ItemDataRole.UserRole):
            return
        self.show_report(current.data(Qt.ItemDataRole.UserRole))

    def show_report(self, key: str) -> ReportWidget:
        if key not in self._widgets:
            w = ReportWidget(self.specs[key], self.user)
            w.open_requested.connect(lambda k, w=w: (setattr(self, "job_id", w.job_id),
                                                    self.open_requested.emit(k)))
            self._widgets[key] = w
            self.stack.addWidget(w)
        w = self._widgets[key]
        self.stack.setCurrentWidget(w)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.blockSignals(False)
        return w
