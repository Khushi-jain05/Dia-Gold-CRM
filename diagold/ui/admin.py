"""Tools ▸ Advance Options, Backup and the Audit Log (5 Oct §4.13 / §4.14,
T-11)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QTabWidget, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from sqlalchemy import select

from diagold.db.models import Metal, ProductSku, StoneSku
from diagold.db.session import SessionLocal
from diagold.services import admin as A
from diagold.services.production import ProductionError
from diagold.ui.confirm import confirm_save
from diagold.ui.production import _Screen, _info, _warn
from diagold.ui.reports import Col, ReportSpec, static


def _user_name(user) -> str:
    return getattr(user, "username", "") or ""


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    return t


class AdvanceOptionsWidget(_Screen):
    def __init__(self, user=None, parent=None):
        super().__init__("Advance Options", with_picker=False, parent=parent)
        self.header.hide()
        self.user = user
        self.button("Exit", self.close_requested.emit, secondary=True)
        tabs = QTabWidget()
        tabs.addTab(self._job_tab(), "Job Card Corrections")
        tabs.addTab(self._ssku_tab(), "Update SSKU Price")
        tabs.addTab(self._delete_tab(), "Delete Item History")
        tabs.addTab(self._decl_tab(), "Declarations")
        tabs.addTab(self._layout_tab(), "Print Layouts")
        tabs.addTab(self._masters_tab(), "Masters Excel")
        self.outer.addWidget(tabs, 1)

    # -- job card corrections ---------------------------------------------
    def _job_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("Job No"))
        self.job_no = QLineEdit()
        self.job_no.setMaximumWidth(140)
        self.job_no.returnPressed.connect(self._show_job)
        top.addWidget(self.job_no)
        b = QPushButton("Show")
        b.clicked.connect(self._show_job)
        top.addWidget(b)
        self.job_info = QLabel("")
        top.addWidget(self.job_info, 1)
        lay.addLayout(top)
        form = QFormLayout()
        self.metal = QComboBox()
        self.sku = QComboBox()
        self.sku.setEditable(True)
        with SessionLocal() as s:
            for m in s.scalars(select(Metal).order_by(Metal.name)):
                self.metal.addItem(m.name, m.id)
            for k in s.scalars(select(ProductSku).order_by(ProductSku.sku_code)):
                self.sku.addItem(k.sku_code, k.id)
        self.cref = QLineEdit()
        self.pcs = QSpinBox()
        self.pcs.setRange(1, 100000)
        self.add = QSpinBox()
        self.add.setRange(1, 100000)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Why - kept in the audit log (required)")
        for label, ed, field in (("Metal", self.metal, "metal_id"), ("C Ref", self.cref, "c_ref"),
                                 ("Pcs (job and order)", self.pcs, "pcs"),
                                 ("SKU", self.sku, "product_sku_id")):
            row = QHBoxLayout()
            row.addWidget(ed, 1)
            btn = QPushButton(f"Update {label.split(' (')[0]}")
            btn.clicked.connect(lambda _c=False, f=field: self._update(f))
            row.addWidget(btn)
            form.addRow(label, row)
        row = QHBoxLayout()
        row.addWidget(self.add, 1)
        btn = QPushButton("Add Pcs")
        btn.clicked.connect(self._add_pcs)
        row.addWidget(btn)
        form.addRow("Add Pcs in Job Card", row)
        form.addRow("Reason", self.reason)
        lay.addLayout(form)
        note = QLabel("A job already in ready stock cannot be changed here - correct or delete "
                      "the piece instead. The order line changes with the job. Every change is "
                      "in Tools ▸ Audit Log with before / after.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        return w

    def _job(self, s):
        return A.find_job(s, self.job_no.text())

    def _show_job(self) -> None:
        with SessionLocal() as s:
            try:
                job = self._job(s)
            except ProductionError as exc:
                self.job_info.setText(str(exc))
                return
            metal = s.get(Metal, job.metal_id) if job.metal_id else None
            sku = s.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
            self.job_info.setText(f"<b>Job {job.job_no}</b> · {sku.sku_code if sku else ''} · "
                                  f"{metal.name if metal else ''} · {job.pcs} pcs · C-Ref "
                                  f"{job.c_ref or '—'} · {job.status}")
            self.metal.setCurrentIndex(max(self.metal.findData(job.metal_id), 0))
            self.sku.setCurrentIndex(max(self.sku.findData(job.product_sku_id), 0))
            self.cref.setText(job.c_ref or "")
            self.pcs.setValue(int(job.pcs or 1))

    def _update(self, field: str) -> None:
        value = {"metal_id": self.metal.currentData(), "c_ref": self.cref.text(),
                 "pcs": self.pcs.value(),
                 "product_sku_id": self.sku.itemData(self.sku.findText(self.sku.currentText()))
                 }[field]
        self._run(lambda s, job: A.update_job(s, job, field, value, self.reason.text(),
                                              self.user))

    def _add_pcs(self) -> None:
        self._run(lambda s, job: A.add_pcs(s, job, self.add.value(), self.reason.text(),
                                           self.user))

    def _run(self, fn) -> None:
        if not confirm_save(self, "the correction"):
            return
        with SessionLocal() as s:
            try:
                fn(s, self._job(s))
                s.commit()
            except ProductionError as exc:
                _warn(self, "Correction", str(exc))
                return
        self._show_job()
        _info(self, "Correction", "Saved and logged.")

    # -- SSKU price ---------------------------------------------------------
    def _ssku_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.ssku = QComboBox()
        self.ssku.setEditable(True)
        with SessionLocal() as s:
            codes = sorted({(k.stone or k.sku_code) for k in s.scalars(select(StoneSku))}
                           | {k.sku_code for k in s.scalars(select(StoneSku))})
        self.ssku.addItems(codes)
        self.all_size = QCheckBox("All Size")
        self.all_size.setChecked(True)
        self.size = QLineEdit()
        self.size.setPlaceholderText("SIZE")
        self.new_price = QDoubleSpinBox()
        self.new_price.setRange(0, 1e9)
        self.new_price.setDecimals(2)
        self.ssku_reason = QLineEdit()
        self.ssku_reason.setPlaceholderText("Reason (required)")
        for x in (QLabel("SSKU"), self.ssku, self.all_size, self.size, QLabel("New Price"),
                  self.new_price):
            top.addWidget(x)
        b1 = QPushButton("Preview")
        b1.clicked.connect(self._preview)
        b2 = QPushButton("Update Ready Stock")
        b2.setObjectName("Primary")
        b2.clicked.connect(self._apply)
        top.addWidget(b1)
        top.addWidget(b2)
        lay.addLayout(top)
        lay.addWidget(self.ssku_reason)
        self.preview = _table(["Stock No", "SKU", "Stone", "Pcs", "Ct", "Old Price", "New Price",
                               "Old Amt", "New Amt", "Piece Price", "→ New"])
        lay.addWidget(self.preview, 1)
        return w

    def _args(self):
        return (self.ssku.currentText().strip(),
                None if self.all_size.isChecked() else self.size.text().strip() or None,
                Decimal(str(self.new_price.value())))

    def _preview(self) -> list:
        with SessionLocal() as s:
            rows = A.ssku_price_preview(s, *self._args())
        self.preview.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, k in enumerate(("stock_no", "sku", "stone", "pcs", "weight", "old_price",
                                   "new_price", "old_amount", "new_amount", "piece_old",
                                   "piece_new")):
                v = r[k]
                self.preview.setItem(i, c, QTableWidgetItem(
                    f"{v:,.2f}" if isinstance(v, Decimal) and k != "weight" else str(v)))
        return rows

    def _apply(self) -> None:
        rows = self._preview()
        if not rows:
            _info(self, "Update SSKU Price", "No piece in ready stock carries that stone.")
            return
        if QMessageBox.question(self, "Update SSKU Price",
                                f"Re-price {len(rows)} stone line(s) on pieces in ready stock?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                n = A.ssku_price_apply(s, *self._args(), self.ssku_reason.text(), self.user)
                s.commit()
            except ProductionError as exc:
                _warn(self, "Update SSKU Price", str(exc))
                return
        self._preview()
        _info(self, "Update SSKU Price", f"{n} piece(s) updated and logged.")

    # -- delete item --------------------------------------------------------
    def _delete_tab(self) -> QWidget:
        w = QWidget()
        lay = QFormLayout(w)
        self.del_no = QLineEdit()
        self.del_sku = QCheckBox("Delete SKU also (only when nothing else uses it)")
        self.del_reason = QLineEdit()
        b = QPushButton("Delete")
        b.clicked.connect(self._delete)
        lay.addRow("Stock No", self.del_no)
        lay.addRow("", self.del_sku)
        lay.addRow("Reason", self.del_reason)
        lay.addRow("", b)
        return w

    def _delete(self) -> None:
        if QMessageBox.question(self, "Delete", f"Delete Stock No {self.del_no.text()} from "
                                "ready stock?") != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                msg = A.delete_item_history(s, self.del_no.text(),
                                            delete_sku=self.del_sku.isChecked(),
                                            reason=self.del_reason.text(), user=self.user)
                s.commit()
            except ProductionError as exc:
                _warn(self, "Delete", str(exc))
                return
        _info(self, "Delete", msg)

    # -- declarations ---------------------------------------------------------
    def _decl_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("Document"))
        self.doc = QComboBox()
        self.doc.addItems(list(A.DECLARATION_DOCS))
        self.doc.currentIndexChanged.connect(lambda _i: self._load_decl())
        top.addWidget(self.doc)
        top.addStretch(1)
        lay.addLayout(top)
        self.decl_lines = [QLineEdit() for _ in range(max(A.DECLARATION_DOCS.values()))]
        form = QFormLayout()
        for i, e in enumerate(self.decl_lines, 1):
            form.addRow(f"Line {i}", e)
        lay.addLayout(form)
        b = QPushButton("Save")
        b.setObjectName("Primary")
        b.clicked.connect(self._save_decl)
        lay.addWidget(b)
        note = QLabel("Printed at the foot of that document (sale, approval, purchase and "
                      "stone vouchers, the order print).")
        note.setObjectName("Muted")
        lay.addWidget(note)
        lay.addStretch(1)
        self._load_decl()
        return w

    def _load_decl(self) -> None:
        doc = self.doc.currentText()
        with SessionLocal() as s:
            lines = A.declarations(s, doc)
        n = A.DECLARATION_DOCS[doc]
        for i, e in enumerate(self.decl_lines):
            e.setVisible(i < n)
            e.setText(lines[i] if i < n else "")

    def _save_decl(self) -> None:
        doc = self.doc.currentText()
        with SessionLocal() as s:
            A.set_declarations(s, doc, [e.text() for e in self.decl_lines], _user_name(self.user))
            s.commit()
        _info(self, "Declarations", f"Saved for {doc}.")

    # -- print layouts --------------------------------------------------------
    def _layout_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.layout_name = QComboBox()
        self.layout_name.addItems(list(A.LAYOUTS))
        self.layout_name.currentIndexChanged.connect(lambda _i: self._load_layout())
        top.addWidget(QLabel("Layout"))
        top.addWidget(self.layout_name)
        top.addStretch(1)
        lay.addLayout(top)
        form = QFormLayout()
        self.l_title = QLineEdit()
        self.l_header = QTextEdit()
        self.l_header.setMaximumHeight(70)
        self.l_footer = QTextEdit()
        self.l_footer.setMaximumHeight(70)
        self.l_prices = QCheckBox("Show prices")
        self.l_stones = QCheckBox("Show stone detail")
        form.addRow("Title", self.l_title)
        form.addRow("Header lines", self.l_header)
        form.addRow("", self.l_prices)
        form.addRow("", self.l_stones)
        form.addRow("Footer lines", self.l_footer)
        lay.addLayout(form)
        b = QPushButton("Save")
        b.setObjectName("Primary")
        b.clicked.connect(self._save_layout)
        lay.addWidget(b)
        note = QLabel("Each client picks DEFAULT or CLIENT for the Sale Invoice and the Packing "
                      "List in Masters ▸ Account. What the client's own layout must look like "
                      "is still to be shared (asked) - title, header / footer lines and which "
                      "columns show can be set here meanwhile.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        self._load_layout()
        return w

    def _load_layout(self) -> None:
        with SessionLocal() as s:
            v = A.layout(s, self.layout_name.currentText())
        self.l_title.setText(v["title"])
        self.l_header.setPlainText(v["header"])
        self.l_footer.setPlainText(v["footer"])
        self.l_prices.setChecked(bool(v["show_prices"]))
        self.l_stones.setChecked(bool(v["show_stones"]))

    def _save_layout(self) -> None:
        with SessionLocal() as s:
            A.set_layout(s, self.layout_name.currentText(), {
                "title": self.l_title.text().strip(),
                "header": self.l_header.toPlainText().strip(),
                "footer": self.l_footer.toPlainText().strip(),
                "show_prices": self.l_prices.isChecked(),
                "show_stones": self.l_stones.isChecked()}, _user_name(self.user))
            s.commit()
        _info(self, "Print Layouts", "Saved.")

    # -- masters excel --------------------------------------------------------
    def _masters_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("One workbook with every master list side by side: Item, Family, "
                             "Style, Metal, Color, Stone, Shape, Type, Quality, Group, Origin, "
                             "Treatment, CreationType, Vendors, Clients."))
        b = QPushButton("Masters Excel")
        b.setObjectName("Primary")
        b.clicked.connect(self._masters)
        lay.addWidget(b)
        lay.addStretch(1)
        return w

    def _masters(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Masters Excel", "masters.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        with SessionLocal() as s:
            n = A.masters_excel(s, path)
        _info(self, "Masters Excel", f"Saved {path} ({n} entries).")


class BackupWidget(_Screen):
    def __init__(self, user=None, parent=None):
        super().__init__("Backup", with_picker=False, parent=parent)
        self.header.hide()
        self.user = user
        self.button("Backup Now", self._backup, primary=True)
        self.button("Copy Selected To…", self._copy)
        self.button("Exit", self.close_requested.emit, secondary=True)
        self.where = QLabel("")
        self.outer.addWidget(self.where)
        self.grid = _table(["File", "Taken", "Size (KB)"])
        self.outer.addWidget(self.grid, 1)
        note = QLabel("A dated copy of the whole database. The folder is Backup Path in Tools ▸ "
                      "Option ▸ Settings ▸ Others. To restore, close the app and put the copy "
                      "back in place of diagold.sqlite3 (or ask us).")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.outer.addWidget(note)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as s:
            self.where.setText(f"Folder: {A.backup_dir(s)}")
            rows = A.backups(s)
        self._rows = rows
        self.grid.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, k in enumerate(("file", "at", "size_kb")):
                self.grid.setItem(i, c, QTableWidgetItem(str(r[k])))

    def _backup(self) -> None:
        with SessionLocal() as s:
            path = A.backup_now(s)
        self.refresh()
        _info(self, "Backup", f"Saved {path}")

    def _copy(self) -> None:
        r = self.grid.currentRow()
        if r < 0:
            return
        folder = QFileDialog.getExistingDirectory(self, "Copy backup to")
        if folder:
            _info(self, "Backup", f"Copied to {A.copy_backup(self._rows[r]['path'], folder)}")


def audit_spec() -> ReportSpec:
    return ReportSpec(
        key="audit_log", title="Audit Log",
        columns=static([Col("at", "WHEN"), Col("user", "USER"), Col("kind", "WHAT"),
                        Col("ref", "REF"), Col("reason", "REASON"), Col("before", "BEFORE"),
                        Col("after", "AFTER")]),
        query=lambda s, a, b, **_k: A.audit_rows(s, a, b), filter_column="kind",
        note="Every correction made with Tools ▸ Advance Options - who, when, why, and the "
             "values before and after. Instead of a SQL window (5 Oct §4.13).")
