"""A reusable master-data CRUD screen driven by a declarative field spec.

Every Master and SKU screen is just a :class:`CrudSpec` describing the model and
its editable fields; :class:`CrudWidget` turns that into a searchable list with
add / edit / delete and an auto-generated form dialog.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
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
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import String, Text, inspect, or_, select
from sqlalchemy.exc import IntegrityError

from diagold.db.session import SessionLocal
from diagold.services.rights import (
    PermissionDenied,
    master_for_menu_key as rights_master_for,
    require,
)

# Tall enough for a styled combo / spin box sitting inside a table cell.
ROW_HEIGHT = 38

FieldType = str  # "str" | "text" | "int" | "float" | "bool" | "date"
                 # | "choice" | "fk" | "password" | "child"


@dataclass
class Field:
    name: str
    label: str
    type: FieldType = "str"
    required: bool = False
    choices: list[str] = field(default_factory=list)
    fk_model: Any = None
    fk_label: Callable[[Any], str] | None = None
    default: Any = None
    in_list: bool = True
    decimals: int = 2
    help_text: str = ""
    child: "ChildSpec | None" = None  # only for type="child"
    # Derived values: shown, never typed. The legacy screen distinguishes
    # computed money from entered money by colour; this keeps that.
    readonly: bool = False
    # Fires whenever this field's editor changes, as (dialog, new_value) -
    # new_value is the fk id for "fk" fields, else the raw text/choice. Lets a
    # spec keep a couple of related fields in sync (e.g. auto-filling Family
    # once an Item is picked) without any bespoke screen code.
    on_change: Callable[["FormDialog", Any], None] | None = None


@dataclass
class Shortcut:
    """One keyboard shortcut, shown on the screen and actually bound.

    The client works this screen by reflex, so the shortcuts are listed where
    they can be seen rather than hidden in a menu.
    """

    keys: str                       # "Ctrl+S"
    label: str                      # "Stone Info"
    target: str | None = None       # field to jump to, if it exists yet
    action: str = ""                # "image_attach" | "image_remove" | "details"
    note: str = ""                  # shown when the panel it opens is not built


@dataclass
class ChildSpec:
    """A grid of rows belonging to the record being edited.

    Used for one-to-many detail tables such as a metal head's Mining Metal
    Ratio rows, and later a mould's modification log or a process's QC
    check points.
    """

    model: Any
    fk_attr: str                       # e.g. "metal_id"
    fields: list[Field]
    order_by: str | None = None
    summary: Callable[[list[dict]], str] | None = None
    row_template: dict[str, Any] = field(default_factory=dict)
    default_rows: list[dict] = field(default_factory=list)
    # An append-only log: rows already saved are shown read-only and are
    # never rewritten, only added to.
    append_only: bool = False
    height: int = 150


@dataclass
class CrudSpec:
    key: str
    title: str
    model: Any
    fields: list[Field]
    order_by: str | None = None
    search_hint: str = "Search…"
    # Cross-field check run before save. Returns an error message, or None.
    validate: Callable[[dict, dict[str, list[dict]]], str | None] | None = None
    # Some records are never deleted, only deactivated, so that historic
    # references keep resolving (users, for example).
    deletable: bool = True
    # Recomputes derived fields from the typed values and the child rows,
    # just before the write. Mutates `values` in place.
    before_save: Callable[[dict, dict[str, list[dict]], Any], None] | None = None
    # Keyboard shortcuts to bind and display on the form.
    shortcuts: list[Shortcut] = field(default_factory=list)
    # Read-only summary panels shown beneath the list, as (title, field names).
    # The legacy screens put the selected record's details right below the
    # list rather than making you open the form to read them.
    detail_panels: list[tuple[str, list[str]]] = field(default_factory=list)
    # "Make A Copy" - clone the selected record and open it for editing.
    copyable: bool = False


class ImageSlot(QWidget):
    """One image on a record: a thumbnail, an Attach and a Clear.

    Holds a path, not the bytes - images live on disk with only a reference on
    the record. An empty slot renders as a placeholder, never as a broken
    image, because most records will carry only the finished photograph for a
    long time.
    """

    FORMATS = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
    THUMB = 104

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._path = ""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self.thumb = QLabel()
        self.thumb.setObjectName("ImageSlot")
        self.thumb.setFixedSize(self.THUMB, self.THUMB)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb.mousePressEvent = lambda _e: self.show_full_size()
        outer.addWidget(self.thumb)

        caption = QLabel(label)
        caption.setObjectName("Muted")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(caption)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.btn_attach = QPushButton("Attach")
        self.btn_clear = QPushButton("Clear")
        for b in (self.btn_attach, self.btn_clear):
            b.setFixedHeight(24)
            bar.addWidget(b)
        self.btn_attach.clicked.connect(self.attach)
        self.btn_clear.clicked.connect(self.clear)
        outer.addLayout(bar)

        self._render()

    # -- value -----------------------------------------------------------
    def path(self) -> str:
        return self._path

    def set_path(self, value: str | None) -> None:
        self._path = (value or "").strip()
        self._render()

    def _render(self) -> None:
        if self._path:
            pix = QPixmap(self._path)
            if not pix.isNull():
                self.thumb.setPixmap(pix.scaled(
                    self.THUMB, self.THUMB,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                self.thumb.setToolTip(self._path)
                self.btn_clear.setEnabled(True)
                return
            # A path that no longer resolves is reported, never shown broken.
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("file\nmissing")
            self.thumb.setToolTip(f"Not found:\n{self._path}")
            self.btn_clear.setEnabled(True)
            return
        self.thumb.setPixmap(QPixmap())
        self.thumb.setText("—")
        self.thumb.setToolTip("No image. Ctrl+I to attach.")
        self.btn_clear.setEnabled(False)

    # -- actions ----------------------------------------------------------
    def attach(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose an image", "", self.FORMATS)
        if path:
            self.set_path(path)

    def clear(self) -> None:
        self.set_path("")

    def show_full_size(self) -> None:
        if not self._path:
            return
        pix = QPixmap(self._path)
        if pix.isNull():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self._path)
        lay = QVBoxLayout(dlg)
        label = QLabel()
        label.setPixmap(pix.scaled(900, 700, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(label)
        dlg.exec()


class ChildTableEditor(QWidget):
    """An editable grid of child rows, with Add / Remove and a live summary.

    Values round-trip as a list of plain dicts so the owning dialog can validate
    them before anything touches the database.
    """

    def __init__(self, spec: "ChildSpec", parent=None):
        super().__init__(parent)
        self.spec = spec
        self._locked = 0
        self._fk_cache: dict[str, list[tuple[Any, str]]] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.table = QTableWidget(0, len(spec.fields))
        self.table.setHorizontalHeaderLabels([f.label for f in spec.fields])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(spec.height)
        # A styled QComboBox/QDoubleSpinBox is ~32px tall; the default row is
        # shorter than that, which clipped the cell contents.
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        outer.addWidget(self.table)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.summary = QLabel("")
        self.summary.setStyleSheet("color: gray;")
        bar.addWidget(self.summary, 1)
        self.btn_add = QPushButton("Add row")
        self.btn_remove = QPushButton("Remove row")
        self.btn_add.clicked.connect(lambda: self.add_row(dict(spec.row_template)))
        self.btn_remove.clicked.connect(self._remove_row)
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_remove)
        outer.addLayout(bar)

    # -- rows ------------------------------------------------------------
    def add_row(self, values: dict | None = None) -> None:
        values = values or {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setRowHeight(r, ROW_HEIGHT)
        for c, f in enumerate(self.spec.fields):
            widget = self._cell(f, values.get(f.name))
            if f.on_change is not None:
                self._wire_cell_change(f, widget, r)
            self.table.setCellWidget(r, c, widget)
        self._refresh_summary()

    def _wire_cell_change(self, f: Field, widget: QWidget, row: int) -> None:
        """Let a grid cell react to its own change, e.g. to fill sibling cells."""
        callback = f.on_change
        if f.type == "fk":
            widget.currentIndexChanged.connect(
                lambda _=None, w=widget, r=row: callback(self, r, w.currentData())
            )
        elif f.type == "choice":
            widget.currentTextChanged.connect(lambda t, r=row: callback(self, r, t))
        elif f.type in ("float", "int"):
            widget.valueChanged.connect(lambda v, r=row: callback(self, r, v))
        else:
            widget.textChanged.connect(lambda t, r=row: callback(self, r, t))

    def cell_value(self, row: int, name: str) -> Any:
        """Read one cell of a row by field name."""
        for c, f in enumerate(self.spec.fields):
            if f.name == name:
                return self._cell_value(row, c, f)
        return None

    def set_cell_value(self, row: int, name: str, value: Any) -> None:
        """Write one cell of a row by field name."""
        for c, f in enumerate(self.spec.fields):
            if f.name != name:
                continue
            w = self.table.cellWidget(row, c)
            if w is None:
                return
            if f.type in ("float", "int"):
                w.setValue(float(value or 0))
            elif f.type == "choice":
                w.setCurrentText("" if value is None else str(value))
            elif f.type == "fk":
                idx = w.findData(value)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            else:
                w.setText("" if value is None else str(value))
            return

    def _cell(self, f: Field, value: Any) -> QWidget:
        if f.type == "float":
            w = QDoubleSpinBox()
            w.setDecimals(f.decimals)
            w.setRange(-1_000_000_000, 1_000_000_000)
            w.setValue(float(value) if value not in (None, "") else 0.0)
            w.valueChanged.connect(self._refresh_summary)
            return w
        if f.type == "int":
            w = QSpinBox()
            w.setRange(-1_000_000, 1_000_000_000)
            w.setValue(int(value) if value not in (None, "") else 0)
            w.valueChanged.connect(self._refresh_summary)
            return w
        if f.type == "choice":
            w = QComboBox()
            w.setEditable(True)  # users add their own values (R2)
            w.addItems(f.choices)
            w.setCurrentText("" if value is None else str(value))
            w.currentTextChanged.connect(self._refresh_summary)
            return w
        if f.type == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd")
            w.setDate(value if isinstance(value, date) else date.today())
            return w
        if f.type == "fk":
            w = QComboBox()
            w.addItem("— none —", None)
            for obj_id, text in self._fk_options(f):
                w.addItem(text, obj_id)
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)
            return w
        w = QLineEdit("" if value is None else str(value))
        w.textChanged.connect(self._refresh_summary)
        return w

    def _fk_options(self, f: Field) -> list[tuple[Any, str]]:
        """Look up a child grid's FK choices once, then cache for this editor."""
        if f.name not in self._fk_cache:
            with SessionLocal() as session:
                rows = session.scalars(select(f.fk_model)).all()
                label = f.fk_label or (lambda o: str(o))
                self._fk_cache[f.name] = sorted(
                    ((r.id, label(r)) for r in rows), key=lambda t: t[1].lower()
                )
        return self._fk_cache[f.name]

    def _cell_value(self, row: int, col: int, f: Field) -> Any:
        w = self.table.cellWidget(row, col)
        if f.type == "float":
            return Decimal(str(w.value()))
        if f.type == "int":
            return w.value()
        if f.type == "choice":
            return w.currentText().strip()
        if f.type == "date":
            qd = w.date()
            return date(qd.year(), qd.month(), qd.day())
        if f.type == "fk":
            return w.currentData()
        return w.text().strip()

    def _remove_row(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        r = rows[0].row() if rows else self.table.rowCount() - 1
        if self.spec.append_only and r < self._locked:
            return  # saved history is never removed
        if r >= 0:
            self.table.removeRow(r)
            self._refresh_summary()

    def set_rows(self, rows: list[dict]) -> None:
        self.table.setRowCount(0)
        for row in rows:
            self.add_row(row)
        if self.spec.append_only:
            # Everything loaded from the database is history - lock it.
            self._locked = self.table.rowCount()
            for r in range(self._locked):
                for c in range(self.table.columnCount()):
                    w = self.table.cellWidget(r, c)
                    if w is not None:
                        w.setEnabled(False)
        self._refresh_summary()

    def saved_row_count(self) -> int:
        """How many rows came from the database (append-only grids)."""
        return getattr(self, "_locked", 0)

    def rows(self) -> list[dict]:
        out: list[dict] = []
        for r in range(self.table.rowCount()):
            out.append({
                f.name: self._cell_value(r, c, f)
                for c, f in enumerate(self.spec.fields)
            })
        return out

    def _refresh_summary(self, *_) -> None:
        if self.spec.summary is None:
            return
        try:
            self.summary.setText(self.spec.summary(self.rows()))
        except Exception:  # noqa: BLE001 - a half-typed row must not raise
            self.summary.setText("")


def friendly_db_error(exc: Exception, spec: "CrudSpec", values: dict | None = None) -> str:
    """Turn a database constraint failure into a sentence a person can act on.

    SQLite reports these as e.g. "UNIQUE constraint failed: product_skus.sku_code"
    followed by the whole INSERT statement - useless to whoever typed the value.
    """
    raw = str(getattr(exc, "orig", exc))
    labels = {f.name: f.label for f in spec.fields}
    values = values or {}

    def label_for(column: str) -> str:
        return labels.get(column, column.replace("_", " ").title())

    if "UNIQUE constraint failed" in raw:
        col = raw.split("UNIQUE constraint failed:")[1].split("\n")[0].strip()
        col = col.split(".")[-1].split(",")[0].strip()
        val = values.get(col)
        shown = f" '{val}'" if val not in (None, "") else ""
        return (f"{label_for(col)}{shown} is already in use.\n\n"
                f"Each {spec.title.rstrip('s').lower()} needs its own {label_for(col).lower()} - "
                f"choose a different one, or edit the existing record instead.")
    if "NOT NULL constraint failed" in raw:
        col = raw.split("NOT NULL constraint failed:")[1].split("\n")[0].strip()
        col = col.split(".")[-1].strip()
        return f"{label_for(col)} is required."
    if "FOREIGN KEY constraint failed" in raw:
        return ("One of the linked records no longer exists.\n\n"
                "Re-select the item from the list and try again.")
    if "CHECK constraint failed" in raw:
        return "One of the values is outside what this field allows."
    # Anything else: first line only, without the SQL that follows.
    return raw.split("[SQL:")[0].strip()


class FormDialog(QDialog):
    def __init__(self, spec: CrudSpec, instance: Any | None, session, parent=None,
                 rights: Any = None):
        super().__init__(parent)
        self.spec = spec
        self.instance = instance
        self.session = session
        self.rights = rights
        self.master = rights_master_for(spec.key) if rights is not None else None
        self.editors: dict[str, QWidget] = {}
        self.child_editors: dict[str, ChildTableEditor] = {}
        self._fk_cache: dict[str, list[tuple[Any, str]]] = {}

        self.setWindowTitle(
            f"{'Edit' if instance else 'New'} {spec.title.rstrip('s')}"
        )
        self.setMinimumWidth(460)

        # On Windows with the OS dark theme on, a plain QWidget's stylesheet
        # background can fail to actually paint, letting the dark OS palette
        # show through and swallowing dark form-label text. Forcing this
        # attribute keeps the dialog the same light card colour regardless of
        # the user's Windows theme.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # A long master (Metal has 18 fields plus two child grids) can easily
        # exceed the screen, so the body scrolls and the buttons stay put.
        body = QWidget()
        body.setObjectName("FormBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 16, 18, 8)
        body_layout.setSpacing(10)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        for f in spec.fields:
            if f.type in ("child", "image"):
                continue  # rendered in their own blocks below
            editor = self._build_editor(f)
            if f.readonly:
                editor.setEnabled(False)
                editor.setToolTip("Calculated — not entered by hand.")
            if f.on_change is not None:
                self._wire_on_change(f, editor)
            self.editors[f.name] = editor
            label = f.label + (" *" if f.required else "")
            form.addRow(label, editor)
            if f.help_text:
                hint = QLabel(f.help_text)
                hint.setStyleSheet("color: gray; font-size: 11px;")
                hint.setWordWrap(True)  # long guidance must not clip
                form.addRow("", hint)

        body_layout.addLayout(form)

        # Images sit together in a row of slots, above the child grids.
        self.image_slots: dict[str, ImageSlot] = {}
        image_fields = [f for f in spec.fields if f.type == "image"]
        if image_fields:
            box = QGroupBox("Images")
            grid = QGridLayout(box)
            grid.setSpacing(10)
            for col, f in enumerate(image_fields):
                slot = ImageSlot(f.label)
                self.image_slots[f.name] = slot
                grid.addWidget(slot, 0, col)
            grid.setColumnStretch(len(image_fields), 1)
            body_layout.addWidget(box)
            self.setMinimumWidth(760)

        for f in spec.fields:
            if f.type != "child" or f.child is None:
                continue
            editor = ChildTableEditor(f.child)
            self.child_editors[f.name] = editor
            box = QGroupBox(f.label)
            box_layout = QVBoxLayout(box)
            if f.help_text:
                hint = QLabel(f.help_text)
                hint.setStyleSheet("color: gray; font-size: 11px;")
                hint.setWordWrap(True)
                box_layout.addWidget(hint)
            box_layout.addWidget(editor)
            body_layout.addWidget(box)
            self.setMinimumWidth(660)

        if spec.shortcuts:
            self._build_shortcut_panel(body_layout)

        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("FormScroll")
        scroll.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setContentsMargins(18, 6, 18, 14)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_values()
        self._fit_to_screen(body)

    def _build_shortcut_panel(self, body_layout) -> None:
        """List the shortcuts on the screen and bind every one of them."""
        box = QGroupBox("Keyboard")
        grid = QGridLayout(box)
        grid.setSpacing(6)
        per_row = 4
        for i, sc in enumerate(self.spec.shortcuts):
            chip = QLabel(f"<b>{sc.keys}</b>&nbsp; {sc.label}")
            chip.setObjectName("Muted")
            if sc.note:
                chip.setToolTip(sc.note)
            grid.addWidget(chip, i // per_row, i % per_row)
            QShortcut(QKeySequence(sc.keys), self,
                      activated=lambda s=sc: self._run_shortcut(s))
        body_layout.addWidget(box)

    def _focused_image_slot(self) -> "ImageSlot | None":
        """The image slot with focus, else the first one."""
        widget = QApplication.focusWidget()
        while widget is not None:
            if isinstance(widget, ImageSlot):
                return widget
            widget = widget.parentWidget()
        return next(iter(self.image_slots.values()), None)

    def _run_shortcut(self, sc: "Shortcut") -> None:
        if sc.action == "image_attach":
            slot = self._focused_image_slot()
            if slot is not None:
                slot.attach()
            return
        if sc.action == "image_remove":
            slot = self._focused_image_slot()
            if slot is not None:
                slot.clear()
            return
        if sc.target:
            widget = self.editors.get(sc.target)
            if widget is None and sc.target in self.child_editors:
                widget = self.child_editors[sc.target]
            if widget is not None:
                widget.setFocus(Qt.FocusReason.ShortcutFocusReason)
                scroll = self.findChild(QScrollArea)
                if scroll is not None:
                    scroll.ensureWidgetVisible(widget, 0, 60)
                return
        # The panel this opens belongs to a module that is not built yet.
        QMessageBox.information(
            self, sc.label,
            sc.note or f"{sc.label} is not part of this build yet.")

    def _fit_to_screen(self, body: QWidget) -> None:
        """Size to the content, but never taller than the available screen."""
        body.adjustSize()
        wanted = body.sizeHint().height() + 72  # + button bar
        screen = self.screen() or QApplication.primaryScreen()
        cap = int(screen.availableGeometry().height() * 0.88) if screen else 900
        self.resize(max(self.minimumWidth(), 700), min(wanted, cap))

    # -- editor construction -------------------------------------------------
    def _build_editor(self, f: Field) -> QWidget:
        if f.type == "text":
            w = QPlainTextEdit()
            w.setMaximumHeight(80)
            return w
        if f.type == "bool":
            return QCheckBox()
        if f.type == "int":
            w = QSpinBox()
            w.setRange(-1_000_000, 1_000_000_000)
            return w
        if f.type == "float":
            w = QDoubleSpinBox()
            w.setDecimals(f.decimals)
            w.setRange(-1_000_000_000, 1_000_000_000)
            w.setGroupSeparatorShown(True)
            return w
        if f.type == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd")
            w.setDate(date.today())
            return w
        if f.type == "choice":
            w = QComboBox()
            w.addItems(f.choices)
            return w
        if f.type == "password":
            w = QLineEdit()
            w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setPlaceholderText("leave blank to keep unchanged" if self.instance else "")
            return w
        if f.type == "fk":
            w = QComboBox()
            options = self._fk_options(f)
            w.addItem("— none —", None)
            for obj_id, text in options:
                w.addItem(text, obj_id)
            return w
        return QLineEdit()

    def _wire_on_change(self, f: Field, editor: QWidget) -> None:
        """Connect an editor's change signal to its Field.on_change callback."""
        callback = f.on_change
        if f.type == "fk":
            editor.currentIndexChanged.connect(
                lambda _=None, e=editor: callback(self, e.currentData())
            )
        elif f.type == "choice":
            editor.currentTextChanged.connect(lambda text: callback(self, text))
        elif f.type == "bool":
            editor.toggled.connect(lambda checked: callback(self, checked))
        else:
            editor.textChanged.connect(lambda text: callback(self, text))

    def _fk_options(self, f: Field) -> list[tuple[Any, str]]:
        if f.name in self._fk_cache:
            return self._fk_cache[f.name]
        rows = self.session.scalars(select(f.fk_model)).all()
        label = f.fk_label or (lambda o: str(o))
        opts = sorted(((r.id, label(r)) for r in rows), key=lambda t: t[1].lower())
        self._fk_cache[f.name] = opts
        return opts

    # -- value <-> editor ---------------------------------------------------
    def _load_values(self) -> None:
        for f in self.spec.fields:
            if f.type == "child":
                self._load_child(f)
                continue
            if f.type == "image":
                self.image_slots[f.name].set_path(
                    getattr(self.instance, f.name, "") if self.instance else "")
                continue
            editor = self.editors[f.name]
            if f.type == "password":
                continue
            if self.instance is not None:
                value = getattr(self.instance, f.name, None)
            else:
                value = f.default
            self._set_editor_value(f, editor, value)

    def _load_child(self, f: Field) -> None:
        editor = self.child_editors[f.name]
        child = f.child
        if self.instance is None:
            editor.set_rows([dict(r) for r in child.default_rows])
            return
        stmt = select(child.model).where(
            getattr(child.model, child.fk_attr) == self.instance.id
        )
        if child.order_by:
            stmt = stmt.order_by(getattr(child.model, child.order_by))
        editor.set_rows([
            {cf.name: getattr(row, cf.name, None) for cf in child.fields}
            for row in self.session.scalars(stmt)
        ])

    def _set_editor_value(self, f: Field, editor: QWidget, value: Any) -> None:
        if f.type == "text":
            editor.setPlainText("" if value is None else str(value))
        elif f.type == "bool":
            editor.setChecked(bool(value) if value is not None else bool(f.default))
        elif f.type == "int":
            editor.setValue(int(value) if value not in (None, "") else 0)
        elif f.type == "float":
            editor.setValue(float(value) if value not in (None, "") else 0.0)
        elif f.type == "date":
            if isinstance(value, (date, datetime)):
                editor.setDate(value if isinstance(value, date) else value.date())
        elif f.type == "choice":
            if value is not None:
                idx = editor.findText(str(value))
                if idx < 0 and str(value).strip():
                    # A stored value that is no longer in the list (a legacy
                    # account group, say). Keep it as an option rather than
                    # silently rewriting the record to the first choice on save.
                    editor.addItem(str(value))
                    idx = editor.findText(str(value))
                editor.setCurrentIndex(idx if idx >= 0 else 0)
        elif f.type == "fk":
            idx = editor.findData(value)
            editor.setCurrentIndex(idx if idx >= 0 else 0)
        elif f.type == "password":
            editor.clear()
        else:
            editor.setText("" if value is None else str(value))

    def _editor_value(self, f: Field) -> Any:
        editor = self.editors[f.name]
        if f.type == "text":
            return editor.toPlainText().strip()
        if f.type == "bool":
            return editor.isChecked()
        if f.type == "int":
            return editor.value()
        if f.type == "float":
            return Decimal(str(editor.value()))
        if f.type == "date":
            qd = editor.date()
            return date(qd.year(), qd.month(), qd.day())
        if f.type == "choice":
            return editor.currentText()
        if f.type == "fk":
            return editor.currentData()
        if f.type == "password":
            return editor.text()
        return editor.text().strip()

    def _on_save(self) -> None:
        # Rights are checked here as well as on the button, so a caller that
        # constructs this dialog directly is refused too.
        if self.rights is not None and self.master is not None:
            try:
                require(self.rights, self.master,
                        "edit" if self.instance is not None else "add")
            except PermissionDenied as exc:
                QMessageBox.warning(self, "Not permitted", str(exc))
                return

        values: dict[str, Any] = {}
        secrets: dict[str, str] = {}
        for f in self.spec.fields:
            if f.type == "child":
                continue
            if f.type == "image":
                values[f.name] = self.image_slots[f.name].path()
                continue
            val = self._editor_value(f)
            if f.type == "password":
                secrets[f.name] = val
                continue
            if f.required and (val is None or val == ""):
                QMessageBox.warning(self, "Required", f"'{f.label}' is required.")
                return
            values[f.name] = val

        password = secrets.get("password") or None
        if "password" in secrets:
            if password is None and self.instance is None:
                QMessageBox.warning(self, "Required",
                                    "A password is required for a new user.")
                return
            if "password_confirm" in secrets:
                if (secrets.get("password_confirm") or None) != password:
                    QMessageBox.warning(self, "Passwords do not match",
                                        "The password and its confirmation differ.")
                    return

        children = {name: ed.rows() for name, ed in self.child_editors.items()}

        # Cross-field rules (e.g. metal ratio rows must total 100.00) run
        # before anything is written.
        if self.spec.validate is not None:
            error = self.spec.validate(values, children)
            if error:
                QMessageBox.warning(self, "Cannot save", error)
                return

        # Derived fields are recalculated here, never typed.
        if self.spec.before_save is not None:
            try:
                self.spec.before_save(values, children, self.session)
            except Exception as exc:  # noqa: BLE001 - surface, do not crash
                QMessageBox.critical(self, "Could not calculate", str(exc))
                return

        # Catch a duplicate key before the database does, so the message can
        # name the field and put the cursor back in it.
        for col in inspect(self.spec.model).columns:
            if not col.unique or col.name not in values or values[col.name] in (None, ""):
                continue
            stmt = select(self.spec.model).where(
                getattr(self.spec.model, col.name) == values[col.name]
            )
            if self.instance is not None:
                stmt = stmt.where(self.spec.model.id != self.instance.id)
            if self.session.scalar(stmt) is not None:
                f = next((f for f in self.spec.fields if f.name == col.name), None)
                label = f.label if f else col.name
                QMessageBox.warning(
                    self, "Already exists",
                    f"{label} '{values[col.name]}' is already in use.\n\n"
                    f"Each {self.spec.title.rstrip('s').lower()} needs its own "
                    f"{label.lower()} - choose a different one, or edit the "
                    f"existing record instead.",
                )
                if f and f.name in self.editors:
                    self.editors[f.name].setFocus()
                return

        try:
            if self.instance is None:
                obj = self.spec.model(**values)
                if password is not None and hasattr(obj, "set_password"):
                    obj.set_password(password)
                self.session.add(obj)
            else:
                obj = self.instance
                for k, v in values.items():
                    setattr(obj, k, v)
                if password and hasattr(obj, "set_password"):
                    obj.set_password(password)
            self.session.flush()  # obj.id is needed by the child rows
            self._save_children(obj, children)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            QMessageBox.warning(self, "Could not save",
                                friendly_db_error(exc, self.spec, values))
            return
        except Exception as exc:  # noqa: BLE001 - surface DB errors to the user
            self.session.rollback()
            QMessageBox.critical(self, "Could not save",
                                 friendly_db_error(exc, self.spec, values))
            return
        self.accept()

    def _save_children(self, obj: Any, children: dict[str, list[dict]]) -> None:
        """Replace each child grid's rows wholesale - simple and correct."""
        for f in self.spec.fields:
            if f.type != "child" or f.child is None:
                continue
            child = f.child
            fk = getattr(child.model, child.fk_attr)
            rows = children.get(f.name, [])
            if child.append_only:
                # Never touch what is already saved; only add what is new.
                editor = self.child_editors.get(f.name)
                rows = rows[editor.saved_row_count():] if editor else []
            else:
                for stale in self.session.scalars(
                    select(child.model).where(fk == obj.id)
                ):
                    self.session.delete(stale)
                self.session.flush()
            for row in rows:
                if not any(str(v).strip() for v in row.values() if v is not None):
                    continue  # skip a blank row the user left behind
                self.session.add(child.model(**{child.fk_attr: obj.id}, **row))


class CrudWidget(QWidget):
    def __init__(self, spec: CrudSpec, can_edit: bool = True, parent=None,
                 rights: Any = None):
        super().__init__(parent)
        self.spec = spec
        self.can_edit = can_edit
        # The acting user's rights. Held so every write is checked here, in the
        # data layer - greying out a button is not enforcement.
        self.rights = rights
        self.master = rights_master_for(spec.key) if rights is not None else None
        self._rows: list[Any] = []

        self.setWindowTitle(spec.title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        heading = QLabel(spec.title)
        heading.setObjectName("H1")
        layout.addWidget(heading)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(spec.search_hint)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.reload)
        bar.addWidget(self.search, 1)

        self.btn_new = QPushButton("+ New")
        self.btn_new.setObjectName("Primary")
        self.btn_edit = QPushButton("Edit")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("Danger")
        self.btn_copy = QPushButton("Make A Copy")
        self.btn_refresh = QPushButton("Refresh")
        buttons = [self.btn_new, self.btn_edit]
        if spec.copyable:
            buttons.append(self.btn_copy)
        else:
            self.btn_copy.setVisible(False)
        buttons += [self.btn_delete, self.btn_refresh]
        for b in buttons:
            bar.addWidget(b)
        layout.addLayout(bar)

        self.list_fields = [f for f in spec.fields if f.in_list]
        self.table = QTableWidget(0, len(self.list_fields) + 1)
        self.table.setHorizontalHeaderLabels(["ID"] + [f.label for f in self.list_fields])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnHidden(0, True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda *_: self._edit())
        self.table.itemSelectionChanged.connect(self._refresh_details)
        layout.addWidget(self.table)

        self.detail_widgets: dict[str, QLabel] = {}
        if spec.detail_panels:
            panels = QHBoxLayout()
            panels.setSpacing(14)
            for title, names in spec.detail_panels:
                box = QGroupBox(title)
                grid = QGridLayout(box)
                grid.setColumnStretch(1, 1)
                grid.setVerticalSpacing(5)
                for row, name in enumerate(names):
                    f = next((f for f in spec.fields if f.name == name), None)
                    if f is None:
                        continue
                    key = QLabel(f"{f.label}:")
                    key.setObjectName("Muted")
                    key.setAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
                    val = QLabel("—")
                    val.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextSelectableByMouse)
                    self.detail_widgets[name] = val
                    grid.addWidget(key, row, 0)
                    grid.addWidget(val, row, 1)
                grid.setRowStretch(len(names), 1)
                panels.addWidget(box, 1)
            layout.addLayout(panels)

        self.status = QLabel("")
        self.status.setStyleSheet("color: gray;")
        layout.addWidget(self.status)

        self.btn_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_copy.clicked.connect(self._make_copy)
        self.btn_refresh.clicked.connect(self.reload)

        if not spec.deletable:
            self.btn_delete.setVisible(False)

        if not can_edit:
            for b in (self.btn_new, self.btn_edit, self.btn_delete):
                b.setEnabled(False)
                b.setToolTip("You have view-only access to this screen.")
        elif self.rights is not None and self.master is not None:
            for b, action in ((self.btn_new, "add"), (self.btn_edit, "edit"),
                              (self.btn_delete, "delete")):
                if not self.rights.allows(self.master, action):
                    b.setEnabled(False)
                    b.setToolTip(
                        f"You do not have permission to {action} on {self.master}."
                    )

        self.reload()

    # -- data -------------------------------------------------------------
    def reload(self) -> None:
        term = self.search.text().strip()
        with SessionLocal() as session:
            stmt = select(self.spec.model)
            if term:
                cols = [
                    c for c in inspect(self.spec.model).columns
                    if isinstance(c.type, (String, Text))
                ]
                if cols:
                    like = f"%{term}%"
                    stmt = stmt.where(or_(*[c.ilike(like) for c in cols]))
            if self.spec.order_by:
                stmt = stmt.order_by(getattr(self.spec.model, self.spec.order_by))
            self._rows = list(session.scalars(stmt).all())
            self._fill_table(session)

    def _display(self, obj: Any, f: Field, session) -> str:
        value = getattr(obj, f.name)
        if f.type == "fk":
            if value is None:
                return ""
            related = session.get(f.fk_model, value)
            if related is None:
                return str(value)
            return (f.fk_label or str)(related)
        if f.type == "bool":
            return "Yes" if value else "No"
        if value is None:
            return ""
        return str(value)

    def _fill_table(self, session) -> None:
        self.table.setRowCount(0)
        for obj in self._rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            id_item = QTableWidgetItem(str(obj.id))
            self.table.setItem(r, 0, id_item)
            for c, f in enumerate(self.list_fields, start=1):
                item = QTableWidgetItem(self._display(obj, f, session))
                if f.type in ("int", "float"):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.status.setText(f"{len(self._rows)} record(s)")
        if self._rows and self.spec.detail_panels:
            self.table.selectRow(0)
        self._refresh_details()

    def _selected(self) -> Any | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        obj_id = int(self.table.item(rows[0].row(), 0).text())
        for obj in self._rows:
            if obj.id == obj_id:
                return obj
        return None

    # -- actions --------------------------------------------------------
    def _require(self, action: str) -> bool:
        """Check rights here, not only where the button lives."""
        if self.rights is None or self.master is None:
            return True
        try:
            require(self.rights, self.master, action)
        except PermissionDenied as exc:
            QMessageBox.warning(self, "Not permitted", str(exc))
            return False
        return True

    def _new(self) -> None:
        if not self._require("add"):
            return
        with SessionLocal() as session:
            dlg = FormDialog(self.spec, None, session, self, rights=self.rights)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.reload()

    def _edit(self) -> None:
        if not self._require("edit"):
            return
        current = self._selected()
        if current is None:
            QMessageBox.information(self, "Edit", "Select a row first.")
            return
        with SessionLocal() as session:
            fresh = session.get(self.spec.model, current.id)
            dlg = FormDialog(self.spec, fresh, session, self, rights=self.rights)
            if not self.can_edit:
                return
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.reload()

    def _refresh_details(self) -> None:
        """Show the selected record in the panels beneath the list."""
        if not self.detail_widgets:
            return
        current = self._selected()
        with SessionLocal() as session:
            for name, label in self.detail_widgets.items():
                if current is None:
                    label.setText("—")
                    continue
                f = next((f for f in self.spec.fields if f.name == name), None)
                text_value = self._display(current, f, session) if f else ""
                label.setText(text_value or "—")

    def _make_copy(self) -> None:
        """Clone the selected record and open the copy for editing.

        The client relies on this to add a stone that is nearly the same as one
        already on file. Unique keys get a " (copy)" suffix so the clone saves
        without clashing; everything else comes across as it is.
        """
        if not self._require("add"):
            return
        current = self._selected()
        if current is None:
            QMessageBox.information(self, "Make A Copy", "Select a row first.")
            return
        with SessionLocal() as session:
            source = session.get(self.spec.model, current.id)
            if source is None:
                return
            values: dict[str, Any] = {}
            for f in self.spec.fields:
                if f.type in ("child", "password"):
                    continue
                values[f.name] = getattr(source, f.name, None)
            for col in inspect(self.spec.model).columns:
                if col.unique and col.name in values and values[col.name]:
                    values[col.name] = f"{values[col.name]} (copy)"

            clone = self.spec.model(**values)
            session.add(clone)
            try:
                session.flush()
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                QMessageBox.critical(self, "Could not copy", str(exc))
                return
            # Child rows come across too, so a copy is a real duplicate.
            for f in self.spec.fields:
                if f.type != "child" or f.child is None:
                    continue
                child = f.child
                fk = getattr(child.model, child.fk_attr)
                for row in session.scalars(select(child.model).where(fk == source.id)):
                    session.add(child.model(**{child.fk_attr: clone.id}, **{
                        cf.name: getattr(row, cf.name) for cf in child.fields
                    }))
            session.commit()
            fresh = session.get(self.spec.model, clone.id)
            dlg = FormDialog(self.spec, fresh, session, self, rights=self.rights)
            dlg.exec()
        self.reload()

    def _delete(self) -> None:
        if not self.spec.deletable:
            QMessageBox.information(
                self, "Not deleted",
                f"{self.spec.title} are never deleted — clear the Active flag "
                "instead so historic records keep resolving.",
            )
            return
        if not self._require("delete"):
            return
        current = self._selected()
        if current is None:
            QMessageBox.information(self, "Delete", "Select a row first.")
            return
        if QMessageBox.question(
            self, "Delete", f"Delete this {self.spec.title.rstrip('s').lower()}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as session:
            obj = session.get(self.spec.model, current.id)
            if obj is not None:
                try:
                    session.delete(obj)
                    session.commit()
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    QMessageBox.warning(
                        self, "Could not delete",
                        "This record is used by other records, so it cannot be "
                        "deleted.\n\nClear its Active flag instead to retire it.",
                    )
                    return
        self.reload()
