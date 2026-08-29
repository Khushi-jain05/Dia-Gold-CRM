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
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import String, Text, inspect, or_, select

from diagold.db.session import SessionLocal

FieldType = str  # "str" | "text" | "int" | "float" | "bool" | "date" | "choice" | "fk"


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


@dataclass
class CrudSpec:
    key: str
    title: str
    model: Any
    fields: list[Field]
    order_by: str | None = None
    search_hint: str = "Search…"


class FormDialog(QDialog):
    def __init__(self, spec: CrudSpec, instance: Any | None, session, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.instance = instance
        self.session = session
        self.editors: dict[str, QWidget] = {}
        self._fk_cache: dict[str, list[tuple[Any, str]]] = {}

        self.setWindowTitle(
            f"{'Edit' if instance else 'New'} {spec.title.rstrip('s')}"
        )
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for f in spec.fields:
            editor = self._build_editor(f)
            self.editors[f.name] = editor
            label = f.label + (" *" if f.required else "")
            form.addRow(label, editor)
            if f.help_text:
                hint = QLabel(f.help_text)
                hint.setStyleSheet("color: gray; font-size: 11px;")
                form.addRow("", hint)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_values()

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
            editor = self.editors[f.name]
            if f.type == "password":
                continue
            if self.instance is not None:
                value = getattr(self.instance, f.name, None)
            else:
                value = f.default
            self._set_editor_value(f, editor, value)

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
        values: dict[str, Any] = {}
        password: str | None = None
        for f in self.spec.fields:
            val = self._editor_value(f)
            if f.type == "password":
                if not val and self.instance is None:
                    QMessageBox.warning(self, "Required", "A password is required for a new user.")
                    return
                password = val or None
                continue
            if f.required and (val is None or val == ""):
                QMessageBox.warning(self, "Required", f"'{f.label}' is required.")
                return
            values[f.name] = val

        try:
            if self.instance is None:
                obj = self.spec.model(**values)
                if password is not None and hasattr(obj, "set_password"):
                    obj.set_password(password)
                self.session.add(obj)
            else:
                for k, v in values.items():
                    setattr(self.instance, k, v)
                if password and hasattr(self.instance, "set_password"):
                    self.instance.set_password(password)
            self.session.commit()
        except Exception as exc:  # noqa: BLE001 - surface DB errors to the user
            self.session.rollback()
            QMessageBox.critical(self, "Could not save", str(exc))
            return
        self.accept()


class CrudWidget(QWidget):
    def __init__(self, spec: CrudSpec, can_edit: bool = True, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.can_edit = can_edit
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
        self.btn_refresh = QPushButton("Refresh")
        for b in (self.btn_new, self.btn_edit, self.btn_delete, self.btn_refresh):
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
        layout.addWidget(self.table)

        self.status = QLabel("")
        self.status.setStyleSheet("color: gray;")
        layout.addWidget(self.status)

        self.btn_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_refresh.clicked.connect(self.reload)

        if not can_edit:
            for b in (self.btn_new, self.btn_edit, self.btn_delete):
                b.setEnabled(False)
            b.setToolTip("You have view-only access to this screen.")

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
    def _new(self) -> None:
        with SessionLocal() as session:
            dlg = FormDialog(self.spec, None, session, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.reload()

    def _edit(self) -> None:
        current = self._selected()
        if current is None:
            QMessageBox.information(self, "Edit", "Select a row first.")
            return
        with SessionLocal() as session:
            fresh = session.get(self.spec.model, current.id)
            dlg = FormDialog(self.spec, fresh, session, self)
            if not self.can_edit:
                return
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.reload()

    def _delete(self) -> None:
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
                    QMessageBox.critical(
                        self, "Could not delete",
                        f"{exc}\n\nThis record is probably referenced elsewhere.",
                    )
                    return
        self.reload()
