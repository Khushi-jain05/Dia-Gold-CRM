"""Manufacturing screens: MFG Ready Stock Transfer (with Fill Prices, the cost
break-up and the Tag List) and Item Search with the delete-and-redo
correction path (28 Sept §4.8-4.10, T-07 / T-08).

The pending list and the day book are report-grid screens (see reports.py).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QMessageBox,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from diagold.db.models import (Account, Job, JobStep, JobVoucher, ManufacturingProcess, Metal,
                               Location, MfgTransfer, ProductSku, StockItem)
from diagold.db.session import SessionLocal
from diagold.services import manufacturing as mfg
from diagold.services import mfg_pricing, production
from diagold.services.production import ProductionError
from diagold.ui.confirm import confirm_save
from diagold.ui.production import (
    TINT_RECEIVE,
    _fit_columns,
    _info,
    _item,
    _print_table,
    _pydate,
    _qdate,
    _Screen,
    _table,
    _warn,
    show_in_dialog,
)

EDIT_TINT = TINT_RECEIVE

# key, header, editable
COLS: list[tuple[str, str, bool]] = [
    ("location", "Location", False), ("job_no", "Job No", False), ("sku", "SKU", False),
    ("c_ref", "C-Ref", False), ("metal", "Metal", False), ("title", "Title", False),
    ("loss_pct", "Loss%", False), ("colour", "Col", False), ("size", "Size", False),
    ("pcs", "Pcs", False), ("gross_wt", "G-Wt", False), ("net_wt", "N-Wt", False),
    ("fine_wt", "FineWt", False), ("fine_loss", "Fine With\nLoss", False),
    ("rej_pcs", "Rej\nPcs", False), ("rej_wt", "Rej\nWt", False),
    ("metal_rate", "Metal\nRate", False), ("metal_amount", "Metal\nAmount", False),
    ("stone_amount", "Stone\nAmount", False), ("setting_amount", "Setting\nAmount", False),
    ("ex_metal_amount", "Ex Metal\nAmt", False), ("finding_labour", "Finding\nLabour", False),
    ("labour_rate", "Labour\nPrice", False), ("labour_weight", "Labour\nWt", True),
    ("labour", "Labour", False), ("manual_amount", "Manual\nAmount", True),
    ("total", "Total\nAmount", False), ("margin_pct", "Margin\n%", True),
    ("margin_amount", "Margin\nAmount", False), ("price_per_pcs", "Price\nPer Pcs", False),
    ("total_value", "Total\nValue", False), ("tag_text", "Tag\nPrice", False),
    ("is_repair", "Repair\n(tag 0)", True), ("stamp", "Stamp", True),
]
_IDX = {k: i for i, (k, _h, _e) in enumerate(COLS)}


def _num(text: str) -> Decimal | None:
    text = (text or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class PendingPicker(QDialog):
    """Show Pending: the jobs pending for MFG transfer, tick the ones to add."""

    def __init__(self, exclude: set[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pending For MFG Transfer")
        self.setMinimumSize(640, 420)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        with SessionLocal() as s:
            rows = mfg.pending_rows(s)
        for r in rows:
            if r["_job_id"] in exclude:
                continue
            it = QListWidgetItem(
                f"{r['job_no']}   {r['sku']}   {r['metal']}   {r['pcs']} pc   "
                f"G {r['g_wt']} / N {r['n_wt']} g   {r['client']}")
            it.setData(Qt.ItemDataRole.UserRole, r["_job_id"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            self.list.addItem(it)
        note = QLabel("Jobs whose last route step has been received and that are not yet "
                      "in ready stock." if self.list.count() else
                      "Nothing is pending for MFG transfer. A job appears here once its "
                      "last route step is received back in Job History.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def job_ids(self) -> list[int]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]


def breakup_widget(result: mfg_pricing.TransferPrice | None, stones: list[dict],
                   rows: list[tuple[str, str, str]]) -> QWidget:
    """The cost break-up pop-up: components, then the stones."""
    t = _table(["Component", "How", "Amount"])
    for comp, how, amount in rows:
        r = t.rowCount()
        t.insertRow(r)
        bold = comp in ("Total cost", "Price per piece", "Tag price")
        t.setItem(r, 0, _item(comp, bold=bold))
        t.setItem(r, 1, _item(how))
        t.setItem(r, 2, _item(amount, right=True, bold=bold))
    st = _table(["Stone", "Pcs", "Weight (ct)", "Per", "Price", "Amount", "S Type"])
    for sc in stones:
        r = st.rowCount()
        st.insertRow(r)
        for c, v in enumerate([sc["label"], sc["pcs"], sc["weight"], sc["unit"],
                               sc["price"], sc["amount"], sc.get("s_type", "")]):
            st.setItem(r, c, _item(v, right=c in (1, 2, 4, 5)))
    t.resizeColumnsToContents()
    st.resizeColumnsToContents()
    box = QWidget()
    lay = QVBoxLayout(box)
    if result is not None and result.notes:
        note = QLabel("<br>".join(result.notes))
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
    lay.addWidget(t)
    lay.addWidget(QLabel("<b>Stones</b>"))
    lay.addWidget(st)
    return box


def _stones_of(result: mfg_pricing.TransferPrice) -> list[dict]:
    return [{"label": s.label, "pcs": s.pcs, "weight": s.weight, "unit": s.unit,
             "price": s.price, "amount": s.amount, "s_type": s.s_type} for s in result.stones]


class TagListDialog(QDialog):
    """Bar-code tag list for the pieces a transfer created (28 Sept §4.10):
    print all or the ticked ones, with or without the tag price, one tag per
    piece if wanted, the stone detail on the tag, straight to a chosen
    printer, or a text file for the label printer; more pieces can be pulled
    in from a text file of Stock IDs (TXT Import)."""

    def __init__(self, transfer_id: int | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag List")
        self.setMinimumSize(960, 440)
        lay = QVBoxLayout(self)
        self.items: list[dict] = []
        self.title = "Tag List"
        with SessionLocal() as s:
            t = s.get(MfgTransfer, transfer_id) if transfer_id else None
            if t is not None:
                self.title = f"Tag List — MFG Transfer Vr {t.vr_no}"
                self._add_items(s, mfg.stock_for_transfer(s, t))
        lay.addWidget(QLabel(f"<b>{self.title}</b> — the Stock No is the bar code."))
        opts = QHBoxLayout()
        self.o_price = QCheckBox("Print Tag Price")
        self.o_price.setChecked(True)
        self.o_cref = QCheckBox("C-Ref Barcode")
        self.o_detail = QCheckBox("Detail")
        self.o_detail.setToolTip("Put the stone detail (Dia / Polki / CS carats) on the tag")
        self.o_pcs = QCheckBox("Pcs Wise Tag Print")
        for w in (self.o_price, self.o_cref, self.o_detail, self.o_pcs):
            w.toggled.connect(lambda _on: self._fill())
            opts.addWidget(w)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.grid = _table(["", "Sno", "Bar Code", "SKU", "Pcs", "Gross", "Net", "Price/Pcs",
                            "Tag", "Detail"])
        lay.addWidget(self.grid, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for label, fn in (("TXT Import (Stock ID)", self._txt_import),
                          ("Clear Tag List", self._clear), ("Create Txt", self._txt),
                          ("Select Printer", self._to_printer),
                          ("Print Selected", lambda: self._print(True)),
                          ("Print All", lambda: self._print(False))):
            b = buttons.addButton(label, QDialogButtonBox.ButtonRole.ActionRole)
            b.clicked.connect(fn)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill()

    def _add_items(self, s, stock_items) -> None:
        have = {i["id"] for i in self.items}
        for it in stock_items:
            if it.id in have:
                continue
            job = s.get(Job, it.job_id) if it.job_id else None
            groups = mfg.item_detail(s, it)["stone_groups"]
            detail = " · ".join(f"{g} {w:.2f}ct" for g, (w, _a) in groups.items() if w)
            sku = s.get(ProductSku, it.product_sku_id) if it.product_sku_id else None
            self.items.append({
                "id": it.id, "stock_no": it.stock_no,
                "sku": sku.sku_code if sku else "",
                "c_ref": it.c_ref or (job.c_ref if job else ""), "pcs": it.pcs,
                "gross": it.gross_wt, "net": it.net_wt,
                "price": f"{Decimal(str(it.price)):,.2f}", "tag": it.tag_text,
                "detail": detail,
            })

    def _txt_import(self) -> None:
        """Add the pieces named in a text file of Stock IDs (one or many per
        line, any separator) - the legacy "TXT Import (Stock ID)"."""
        import re
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "TXT Import (Stock ID)", "",
                                              "Text (*.txt *.csv);;All files (*)")
        if not path:
            return
        with open(path, encoding="utf-8", errors="ignore") as fh:
            nos = {int(n) for n in re.findall(r"\d+", fh.read())}
        self.import_stock_ids(nos)

    def import_stock_ids(self, nos: set[int]) -> int:
        with SessionLocal() as s:
            found = list(s.scalars(select(StockItem).where(StockItem.stock_no.in_(nos))
                                   .order_by(StockItem.stock_no)))
            before = len(self.items)
            self._add_items(s, found)
        self._fill()
        added = len(self.items) - before
        missing = len(nos) - len(found)
        _info(self, "TXT Import", f"Added {added} piece(s) to the tag list."
              + (f" {missing} Stock ID(s) were not found." if missing else ""))
        return added

    def _to_printer(self) -> None:
        """Select Printer: print the ticked tags (or all) on a chosen printer."""
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        rows = self._picked(True) or self._picked(False)
        if not rows:
            _info(self, "Print", "The tag list is empty.")
            return
        printer = QPrinter()
        from diagold.services import settings as _settings
        name = _settings.opt("opt.printer_name").strip()
        if name:
            printer.setPrinterName(name)        # Tools > Option > Printer Name
        if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
            return
        doc = QTextDocument()
        doc.setHtml(self._html(rows))
        doc.print_(printer)
        self._mark_printed(rows)

    def _cols(self) -> list[int]:
        return list(range(1, 9)) + ([9] if self.o_detail.isChecked() else [])

    def _html(self, rows: list[int]) -> str:
        cols = self._cols()
        head = "".join(f"<th>{self.grid.horizontalHeaderItem(c).text()}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{self.grid.item(r, c).text()}</td>"
                                         for c in cols) + "</tr>" for r in rows)
        return (f"<h3>{self.title}</h3><table border=1 cellspacing=0 cellpadding=3>"
                f"<tr>{head}</tr>{body}</table>")

    def _rows(self) -> list[dict]:
        out = []
        for it in self.items:
            for _n in range(max(int(it["pcs"] or 1), 1) if self.o_pcs.isChecked() else 1):
                out.append(it)
        return out

    def _fill(self) -> None:
        self.grid.setRowCount(0)
        for n, it in enumerate(self._rows(), start=1):
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            chk = QTableWidgetItem("")
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.grid.setItem(r, 0, chk)
            code = f"{it['stock_no']}" + (f" / {it['c_ref']}" if self.o_cref.isChecked()
                                          and it["c_ref"] else "")
            vals = [n, code, it["sku"], 1 if self.o_pcs.isChecked() else it["pcs"],
                    it["gross"], it["net"], it["price"],
                    it["tag"] if self.o_price.isChecked() else "", it["detail"]]
            for c, v in enumerate(vals, start=1):
                self.grid.setItem(r, c, _item(v, right=c not in (3, 9)))
        self.grid.setColumnHidden(9, not self.o_detail.isChecked())

    def _clear(self) -> None:
        self.items = []
        self._fill()

    def _picked(self, selected: bool) -> list[int]:
        return [r for r in range(self.grid.rowCount())
                if not selected or self.grid.item(r, 0).checkState() == Qt.CheckState.Checked]

    def _print(self, selected: bool) -> None:
        rows = self._picked(selected)
        if not rows:
            _info(self, "Print", "Tick the tags to print first." if selected
                  else "The tag list is empty.")
            return
        cols = self._cols()
        t = _table([self.grid.horizontalHeaderItem(c).text() for c in cols])
        for r in rows:
            t.insertRow(t.rowCount())
            for i, c in enumerate(cols):
                t.setItem(t.rowCount() - 1, i, _item(self.grid.item(r, c).text()))
        _print_table(self, self.title, t, "tag_list")
        self._mark_printed(rows)

    def _txt(self) -> None:
        """A plain text file for the label printer, one tag per line."""
        rows = self._picked(False)
        if not rows:
            return
        from diagold.services import documents
        from datetime import datetime
        path = documents.PRINT_DIR / f"tags_{datetime.now():%Y%m%d-%H%M%S}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            detail = self.o_detail.isChecked()
            fh.write("BARCODE\tSKU\tPCS\tGROSS\tNET\tTAG" + ("\tDETAIL" if detail else "")
                     + "\n")
            cols = (2, 3, 4, 5, 6, 8) + ((9,) if detail else ())
            for r in rows:
                fh.write("\t".join(self.grid.item(r, c).text() for c in cols) + "\n")
        self._mark_printed(rows)
        _info(self, "Create Txt", f"Saved {path}")

    def _mark_printed(self, rows: list[int]) -> None:
        nos = {int(self.grid.item(r, 2).text().split(" /")[0]) for r in rows}
        with SessionLocal() as s:
            for it in s.scalars(select(StockItem).where(StockItem.stock_no.in_(nos))):
                it.tag_printed = True
            s.commit()


class MfgTransferWidget(_Screen):
    """Manufacturing ▸ MFG Transfer - "MFG Ready Stock Transfer" (§4.9)."""

    def __init__(self, user=None, parent=None):
        super().__init__("MFG Ready Stock Transfer", with_picker=False, parent=parent)
        self.user = user
        self.header.hide()
        self._results: dict[int, mfg_pricing.TransferPrice] = {}
        self._job_ids: list[int] = []
        self._last_transfer: int | None = None
        self._filling = False
        # A saved transfer open for editing, and what was typed on its lines.
        self._edit_tid: int | None = None
        self._seed: dict[int, dict[str, Any]] = {}

        self.vr = QLabel("")
        self.vr.setObjectName("H2")
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.date.dateChanged.connect(lambda _d: self.fill_prices())
        self.ref = QLineEdit()
        self.ref.setPlaceholderText("Ref no")
        self.ref.setMaximumWidth(160)
        # Where the finished pieces go into stock (2 Oct §4.4) - Primary unless
        # chosen otherwise.
        self.location = QComboBox()
        with SessionLocal() as s:
            for loc in s.scalars(select(Location).order_by(Location.name)):
                self.location.addItem(loc.name, loc.id)
        i = self.location.findText(mfg.READY_LOCATION)
        if i >= 0:
            self.location.setCurrentIndex(i)
        self.location.currentIndexChanged.connect(lambda _i: self.fill_prices())
        self.split = QCheckBox("Split Jobs")
        self.split.setToolTip("A job of several pieces gets one Stock No per piece, its "
                              "weights, cost and price shared equally.")
        for w in (QLabel("Vr No"), self.vr, QLabel("Date"), self.date, self.ref,
                  QLabel("Location"), self.location, self.split):
            self.toolbar.addWidget(w)
        self.toolbar.addStretch(1)
        self.button("Show Pending", self.show_pending, primary=True)
        self.button("Fill Prices", self.fill_prices)
        self.button("Add", self.new_transfer, secondary=True)
        self.button("Edit", self.edit_transfer, secondary=True)
        self.button("Save", self.save)
        self.button("Delete", self.delete_transfer, secondary=True)
        self.button("Remove Line", self.remove_line, secondary=True)
        self.button("Cost Break-up", self.show_breakup, secondary=True)
        self.button("Tag List", self.tag_list, secondary=True)
        self.button("Tag Print", self.tag_print, secondary=True)
        self.button("Print", self.print_transfer, secondary=True)
        self.button("Format-2", self.print_format2, secondary=True)
        self.button("Excel Format", self.export_excel, secondary=True)
        self.button("Item Search",
                    lambda: self.open_requested.emit("manufacturing.item_search"),
                    secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)

        self.grid = _table([h for _k, h, _e in COLS], ledger=True)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed
                                  | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.grid.itemChanged.connect(self._edited)
        self.outer.addWidget(self.grid, 1)
        self.totals = QLabel("")
        self.totals.setObjectName("Muted")
        self.outer.addWidget(self.totals)
        legend = QLabel(
            "Show Pending lists finished jobs (last route step received). Fill Prices reads "
            "the day's metal rate, the labour rate, the margin set and the stones in each "
            "job; the green columns can be changed per line. Price = total + Margin % "
            "(a mark-up: 50% gives cost × 1.5). Save gives each piece a Stock No / bar code "
            "in Primary. Double-click a grey cell for the cost break-up.")
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        self.outer.addWidget(legend)
        self.grid.cellDoubleClicked.connect(self._double_click)
        self.refresh()

    # -- data ---------------------------------------------------------
    def refresh(self) -> None:
        with SessionLocal() as s:
            if self._edit_tid is not None:
                t = s.get(MfgTransfer, self._edit_tid)
                self.vr.setText(f"{t.vr_no} (editing)" if t else "")
                return
            nxt = production.next_number(s, MfgTransfer.vr_no)
        self.vr.setText(f"{nxt}")

    # -- Add / Edit / Delete a saved transfer (28 Sept §4.9) ----------
    def _editing_blocked(self) -> bool:
        if self._edit_tid is None:
            return False
        _info(self, "Edit", "A saved transfer is open for editing - change the green cells "
              "and Save. To take a piece off it, delete that piece in Item Search; to add "
              "jobs, make a new transfer (Add).")
        return True

    def new_transfer(self) -> None:
        self.location.setEnabled(True)
        self.split.setEnabled(True)
        self._edit_tid, self._seed = None, {}
        self._job_ids, self._results = [], {}
        self.grid.setRowCount(0)
        self.ref.clear()
        self.refresh()
        self.totals.setText("No jobs on this transfer yet - Show Pending.")

    def _pick_transfer(self, title: str) -> int | None:
        with SessionLocal() as s:
            rows = []
            for t in s.scalars(select(MfgTransfer).order_by(MfgTransfer.vr_no.desc())
                               .limit(500)):
                jobs = [str(s.get(Job, l.job_id).job_no) for l in t.lines]
                rows.append((t.id, f"Vr {t.vr_no}   {t.vr_date:%d-%m-%Y}   "
                             f"{t.ref_no or ''}   job {', '.join(jobs)}"))
        if not rows:
            _info(self, title, "No MFG transfer has been saved yet.")
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(560, 400)
        lay = QVBoxLayout(dlg)
        find = QLineEdit()
        find.setPlaceholderText("Vr No, job no or ref…")
        lay.addWidget(find)
        lst = QListWidget()
        for tid, text in rows:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, tid)
            lst.addItem(it)
        lst.setCurrentRow(0)
        find.textChanged.connect(lambda t: [lst.item(i).setHidden(
            t.strip().lower() not in lst.item(i).text().lower()) for i in range(lst.count())])
        lst.itemDoubleClicked.connect(lambda _it: dlg.accept())
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted or lst.currentItem() is None:
            return None
        return lst.currentItem().data(Qt.ItemDataRole.UserRole)

    def edit_transfer(self) -> None:
        tid = self._pick_transfer("Edit — open a saved transfer")
        if tid is None:
            return
        with SessionLocal() as s:
            t = s.get(MfgTransfer, tid)
            self._seed = mfg.transfer_overrides(t)
            self._job_ids = [l.job_id for l in t.lines]
            vr_date, ref = t.vr_date, t.ref_no
            loc_id = t.lines[0].location_id if t.lines else None
            split = bool(t.split_jobs)
        i = self.location.findData(loc_id)
        if i >= 0:
            self.location.blockSignals(True)
            self.location.setCurrentIndex(i)
            self.location.blockSignals(False)
        self.split.setChecked(split)
        self._edit_tid = self._last_transfer = tid
        # Where the pieces went and how they were split stay as saved.
        self.location.setEnabled(False)
        self.split.setEnabled(False)
        self.date.blockSignals(True)
        self.date.setDate(_qdate(vr_date))
        self.date.blockSignals(False)
        self.ref.setText(ref or "")
        self.grid.setRowCount(0)
        self.refresh()
        self.fill_prices()
        self.totals.setText(self.totals.text() + "    <b>Editing</b> - change the green "
                            "cells and Save; the pieces keep their Stock Nos.")

    def delete_transfer(self) -> None:
        tid = self._edit_tid or self._pick_transfer("Delete — pick the transfer")
        if tid is None:
            return
        with SessionLocal() as s:
            t = s.get(MfgTransfer, tid)
            vr = t.vr_no
            nos = [str(i.stock_no) for i in mfg.stock_for_transfer(s, t)]
        if QMessageBox.question(
                self, "Delete",
                f"Delete MFG Transfer Vr {vr}?\n\nStock No {', '.join(nos)} leave stock and "
                "the jobs go back to Pending for MFG Transfer. Everything is kept in the "
                "deletion log.") != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                mfg.delete_transfer(s, s.get(MfgTransfer, tid),
                                    user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot delete", str(exc))
                return
        self.new_transfer()
        self._last_transfer = None
        self.totals.setText(f"MFG Transfer Vr {vr} deleted - its jobs are pending again.")

    def show_pending(self) -> None:
        if self._editing_blocked():
            return
        dlg = PendingPicker(set(self._job_ids), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for jid in dlg.job_ids():
            if jid not in self._job_ids:
                self._job_ids.append(jid)
        self.fill_prices()

    def _overrides(self, row: int) -> dict[str, Any]:
        def cell(key: str) -> str:
            it = self.grid.item(row, _IDX[key])
            return it.text() if it else ""
        rep = self.grid.item(row, _IDX["is_repair"])
        return {
            "labour_weight": _num(cell("labour_weight")),
            "manual_amount": _num(cell("manual_amount")) or 0,
            "margin_pct": _num(cell("margin_pct")),
            "is_repair": bool(rep and rep.checkState() == Qt.CheckState.Checked),
            "stamp": cell("stamp").strip(),
        }

    def fill_prices(self, keep_overrides: bool = True) -> None:
        overrides = dict(self._seed)
        if keep_overrides:
            for r, jid in enumerate(self._job_ids):
                if r < self.grid.rowCount():
                    overrides[jid] = self._overrides(r)
        self._results = {}
        with SessionLocal() as s:
            for jid in self._job_ids:
                job = s.get(Job, jid)
                o = overrides.get(jid, {})
                self._results[jid] = mfg.price_job(
                    s, job, _pydate(self.date), labour_weight=o.get("labour_weight"),
                    margin_pct=o.get("margin_pct"), manual_amount=o.get("manual_amount", 0),
                    is_repair=o.get("is_repair", False))
            meta = {}
            for jid in self._job_ids:
                job = s.get(Job, jid)
                metal = s.get(Metal, job.metal_id) if job.metal_id else None
                _tot, pct, _n = production.job_loss_total(s, job)
                rej_pcs, rej_wt = mfg.job_rejections(s, job)
                meta[jid] = {
                    "job_no": job.job_no,
                    "sku": job.product_sku.sku_code if job.product_sku else "",
                    "metal": metal.name if metal else "", "loss_pct": pct,
                    "gross_wt": mfg.last_gross(s, job), "c_ref": job.c_ref,
                    "colour": job.colour, "size": production._order_line_size(s, job),
                    "location": self.location.currentText(), "rej_pcs": rej_pcs or "",
                    "rej_wt": rej_wt or "",
                }
        self._render(meta, overrides)

    def _render(self, meta: dict, overrides: dict) -> None:
        self._filling = True
        self.grid.setRowCount(0)
        totals = {"total": Decimal("0"), "price": Decimal("0"), "net": Decimal("0")}
        for jid in self._job_ids:
            p = self._results[jid]
            m = meta[jid]
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            vals = {
                **m, "title": f"{p.title:.0f}", "pcs": p.pcs, "net_wt": p.net_wt,
                "fine_wt": p.fine_wt,
                "fine_loss": mfg_pricing.fine_with_loss(p.fine_wt, m["loss_pct"]),
                "ex_metal_amount": f"{p.ex_metal_amount:,.2f}",
                "finding_labour": f"{p.finding_labour:,.2f}",
                "total_value": f"{p.total_value:,.2f}",
                "stamp": overrides.get(jid, {}).get("stamp", ""),
                "metal_rate": f"{p.metal_rate:,.2f}",
                "metal_amount": f"{p.metal_amount:,.2f}",
                "stone_amount": f"{p.stone_amount:,.2f}",
                "setting_amount": f"{p.setting_amount:,.2f}",
                "labour_rate": f"{p.labour_rate:,.2f}", "labour_weight": p.labour_weight,
                "labour": f"{p.labour:,.2f}", "manual_amount": f"{p.manual_amount:.2f}",
                "total": f"{p.total:,.2f}", "margin_pct": f"{p.margin_pct:g}",
                "margin_amount": f"{p.margin_amount:,.2f}",
                "price_per_pcs": f"{p.price_per_pcs:,.2f}", "tag_text": p.tag_text,
            }
            for key, _h, editable in COLS:
                if key == "is_repair":
                    it = QTableWidgetItem("")
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                    on = overrides.get(jid, {}).get("is_repair", False)
                    it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
                    it.setBackground(EDIT_TINT)
                else:
                    bold = key in ("total", "price_per_pcs", "tag_text")
                    it = _item(vals[key], EDIT_TINT if editable else None,
                               right=key not in ("sku", "metal", "location", "c_ref",
                                                 "colour", "size", "stamp"), bold=bold)
                    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    if editable:
                        flags |= Qt.ItemFlag.ItemIsEditable
                    it.setFlags(flags)
                self.grid.setItem(r, _IDX[key], it)
            totals["total"] += p.total
            totals["price"] += p.total_value
            totals["net"] += p.net_wt
        _fit_columns(self.grid)
        self._filling = False
        n = len(self._job_ids)
        self.totals.setText(
            f"<b>{n} job(s)</b>    Net {totals['net']:.3f} g    Total cost "
            f"{totals['total']:,.2f}    Total value {totals['price']:,.2f}" if n else
            "No jobs on this transfer yet - Show Pending.")

    def _edited(self, _item_: QTableWidgetItem) -> None:
        if not self._filling:
            self.fill_prices()

    def remove_line(self) -> None:
        if self._editing_blocked():
            return
        rows = self.grid.selectionModel().selectedRows()
        if not rows:
            _info(self, "Remove Line", "Select a line first.")
            return
        self._job_ids.pop(rows[0].row())
        self.fill_prices()

    def _double_click(self, row: int, col: int) -> None:
        if not COLS[col][2]:
            self.grid.selectRow(row)
            self.show_breakup()

    def show_breakup(self) -> None:
        rows = self.grid.selectionModel().selectedRows()
        if not rows or not self._job_ids:
            _info(self, "Cost Break-up", "Select a line first.")
            return
        p = self._results[self._job_ids[rows[0].row()]]
        show_in_dialog(self, breakup_widget(p, _stones_of(p), p.as_rows()),
                       "Cost Break-up", (860, 620))

    def save(self) -> None:
        if not self._job_ids:
            _info(self, "Save", "Show Pending and pick the jobs to transfer first.")
            return
        lines = [{"job_id": jid, **self._overrides(r)} for r, jid in enumerate(self._job_ids)]
        if self._edit_tid is not None:
            self._save_edit(lines)
            return
        if not confirm_save(self, f"MFG transfer of {len(self._job_ids)} job(s)"):
            return
        with SessionLocal() as s:
            try:
                t = mfg.post_transfer(s, lines, vr_date=_pydate(self.date),
                                      ref_no=self.ref.text().strip(),
                                      user_id=getattr(self.user, "id", None),
                                      location_id=self.location.currentData(),
                                      split_jobs=self.split.isChecked())
                s.commit()
                tid, vr = t.id, t.vr_no
                nos = [i.stock_no for i in mfg.stock_for_transfer(s, t)]
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self._last_transfer = tid
        self._job_ids, self._results = [], {}
        self.grid.setRowCount(0)
        self.ref.clear()
        self.refresh()
        self.totals.setText(f"Saved Vr {vr}: Stock No {', '.join(map(str, nos))} in Primary.")
        from diagold.services import settings as _settings
        if _settings.opt_on("legacy.inventory_prompt_tag_printing_when_stock_entry"):
            TagListDialog(tid, self).exec()       # Tools > Option: Prompt Tag Printing

    def _save_edit(self, lines: list[dict[str, Any]]) -> None:
        tid = self._edit_tid
        if not confirm_save(self, "the changes to this MFG transfer"):
            return
        with SessionLocal() as s:
            try:
                t = mfg.update_transfer(s, s.get(MfgTransfer, tid), lines,
                                        vr_date=_pydate(self.date),
                                        ref_no=self.ref.text().strip(),
                                        user_id=getattr(self.user, "id", None))
                s.commit()
                vr = t.vr_no
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self.new_transfer()
        self._last_transfer = tid
        self.totals.setText(f"MFG Transfer Vr {vr} updated. Tag List reprints its tags.")

    def print_format2(self) -> None:
        """Format-2: the saved transfer piece by piece - one block per job with
        its cost break-up (metal, each stone, labour, margin, price, tag)."""
        from diagold.services import documents
        tid = self._edit_tid or self._last_transfer
        with SessionLocal() as s:
            if tid is None:
                tid = s.scalar(select(func.max(MfgTransfer.id)))
            if tid is None:
                _info(self, "Format-2", "No MFG transfer has been saved yet.")
                return
            t = s.get(MfgTransfer, tid)
            import json as _json
            from diagold.services import admin as ADM
            lay = ADM.layout(s, "MFG TRANSFER")       # Advance Options ▸ Print Layouts
            parts = [f"<h2>{lay['title'] or 'MFG Ready Stock Transfer'} — Vr {t.vr_no} dt "
                     f"{t.vr_date:%d-%m-%Y}"
                     + (f" · Ref {t.ref_no}" if t.ref_no else "") + "</h2>"
                     + (f"<p>{lay['header'].replace(chr(10), '<br>')}</p>" if lay["header"]
                        else "")]
            items = {i.line_id: i for i in mfg.stock_for_transfer(s, t)}
            for l in t.lines:
                job = s.get(Job, l.job_id)
                it = items.get(l.id)
                sku = job.product_sku.sku_code if job.product_sku else ""
                parts.append(
                    f"<h3>{l.sno}. Job {job.job_no} · {sku} · C-Ref {job.c_ref or ''}"
                    + (f" · Stock No {it.stock_no}" if it else "") + "</h3>"
                    f"<p>Pcs {l.pcs} · G-Wt {l.gross_wt:.3f} · N-Wt {l.net_wt:.3f} · "
                    f"Title {l.title:.0f} · FineWt {l.fine_wt:.3f} · Loss {l.loss_pct:.2f}%"
                    + (f" · Stamp {l.stamp}" if l.stamp else "") + "</p>"
                    "<table border=1 cellspacing=0 cellpadding=3 width=100%>"
                    "<tr><th>Component</th><th>Detail</th><th>Amount</th></tr>"
                    f"<tr><td>Metal</td><td>{l.net_wt:.3f} g × {l.metal_rate:,.2f}</td>"
                    f"<td align=right>{l.metal_amount:,.2f}</td></tr>")
                for st in _json.loads(l.stones_json or "[]"):
                    parts.append(
                        f"<tr><td>Stone {st.get('s_type') or ''}</td><td>{st.get('label') or ''}"
                        f" · {st.get('pcs') or 0} pcs / {st.get('weight') or 0} ct @ "
                        f"{st.get('price') or 0} per {st.get('unit') or 'ct'}</td>"
                        f"<td align=right>{Decimal(str(st.get('amount') or 0)):,.2f}</td></tr>")
                for label, amt in (("Setting", l.setting_amount),
                                   ("Ex Metal", l.ex_metal_amount),
                                   ("Finding Labour", l.finding_labour)):
                    if amt:
                        parts.append(f"<tr><td>{label}</td><td></td>"
                                     f"<td align=right>{amt:,.2f}</td></tr>")
                parts.append(
                    f"<tr><td>Labour</td><td>{l.labour_rate:,.2f} × {l.labour_weight:.3f} g"
                    f"</td><td align=right>{l.labour:,.2f}</td></tr>"
                    + (f"<tr><td>Manual</td><td></td><td align=right>"
                       f"{l.manual_amount:,.2f}</td></tr>" if l.manual_amount else "")
                    + f"<tr><td><b>Total cost</b></td><td></td><td align=right><b>"
                    f"{l.total:,.2f}</b></td></tr>"
                    f"<tr><td>Margin</td><td>{Decimal(str(l.margin_pct)).normalize():f}%</td><td align=right>"
                    f"{l.margin_amount:,.2f}</td></tr>"
                    f"<tr><td><b>Price / pcs</b></td><td>Tag {l.tag_text}</td>"
                    f"<td align=right><b>{l.price_per_pcs:,.2f}</b></td></tr></table>")
            if lay["footer"]:
                parts.append(f"<p>{lay['footer'].replace(chr(10), '<br>')}</p>")
        path = documents.PRINT_DIR / f"mfg_transfer_f2_{datetime.now():%Y%m%d-%H%M%S}.pdf"
        documents.to_pdf("".join(parts), path)
        _info(self, "Format-2", f"Saved {path}")

    def _grid_rows(self) -> tuple[list[str], list[list[str]]]:
        heads = [h.replace("\n", " ") for _k, h, _e in COLS]
        rows = []
        for r in range(self.grid.rowCount()):
            row = []
            for c, (key, _h, _e) in enumerate(COLS):
                it = self.grid.item(r, c)
                if key == "is_repair":
                    row.append("Y" if it and it.checkState() == Qt.CheckState.Checked else "")
                else:
                    row.append(it.text() if it else "")
            rows.append(row)
        return heads, rows

    def export_excel(self) -> None:
        """Excel Format: the grid as it stands, as an .xlsx with figures as
        numbers and a totals row."""
        if not self.grid.rowCount():
            _info(self, "Excel Format", "Nothing on the grid to export - Show Pending first.")
            return
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
        from PySide6.QtWidgets import QFileDialog
        vr = self.vr.text().split(" ")[0]
        path, _ = QFileDialog.getSaveFileName(self, "Excel Format", f"mfg_transfer_{vr}.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        heads, rows = self._grid_rows()
        wb = Workbook()
        ws = wb.active
        ws.title = "MFG Transfer"
        ws.append([f"MFG Ready Stock Transfer — Vr {self.vr.text()} dt "
                   f"{_pydate(self.date):%d-%m-%Y}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append(heads)
        for c in ws[2]:
            c.font = Font(bold=True)

        def num(v: str):
            t = v.replace(",", "").strip()
            try:
                return float(t) if t and t not in ("Y",) else v
            except ValueError:
                return v
        text_cols = {i for i, (k, _h, _e) in enumerate(COLS)
                     if k in ("sku", "metal", "location", "c_ref", "colour", "size", "stamp",
                              "tag_text", "job_no", "is_repair")}
        for row in rows:
            ws.append([v if i in text_cols else num(v) for i, v in enumerate(row)])
        first, last = 3, ws.max_row
        ws.append(["TOTAL"])
        for i, (k, _h, _e) in enumerate(COLS, start=1):
            if k in ("pcs", "gross_wt", "net_wt", "fine_wt", "metal_amount", "stone_amount",
                     "labour", "total", "margin_amount", "total_value"):
                L = get_column_letter(i)
                ws[f"{L}{last + 1}"] = f"=SUM({L}{first}:{L}{last})"
        for c in ws[last + 1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A3"
        wb.save(path)
        _info(self, "Excel Format", f"Saved {path}")

    def print_transfer(self) -> None:
        """Print the grid (before saving) or, when it is empty, the last
        saved transfer, to PDF."""
        from diagold.services import documents
        if self.grid.rowCount():
            heads, rows = self._grid_rows()
            title = f"MFG Ready Stock Transfer — Vr {self.vr.text()} (not saved)"
        else:
            tid = self._last_transfer
            with SessionLocal() as s:
                if tid is None:
                    tid = s.scalar(select(func.max(MfgTransfer.id)))
                if tid is None:
                    _info(self, "Print", "No MFG transfer has been saved yet.")
                    return
                t = s.get(MfgTransfer, tid)
                heads = ["Sno", "Job No", "SKU", "Pcs", "G-Wt", "N-Wt", "FineWt", "Metal Amt",
                         "Stone Amt", "Labour", "Total", "Margin %", "Price/Pcs", "Tag",
                         "Stamp"]
                rows = []
                for l in t.lines:
                    job = s.get(Job, l.job_id)
                    rows.append([str(l.sno), str(job.job_no),
                                 job.product_sku.sku_code if job.product_sku else "",
                                 str(l.pcs), f"{l.gross_wt:.3f}", f"{l.net_wt:.3f}",
                                 f"{l.fine_wt:.3f}", f"{l.metal_amount:,.2f}",
                                 f"{l.stone_amount:,.2f}", f"{l.labour:,.2f}",
                                 f"{l.total:,.2f}", f"{Decimal(str(l.margin_pct)).normalize():f}",
                                 f"{l.price_per_pcs:,.2f}", l.tag_text, l.stamp or ""])
                title = (f"MFG Ready Stock Transfer — Vr {t.vr_no} dt {t.vr_date:%d-%m-%Y}"
                         + (f" · Ref {t.ref_no}" if t.ref_no else ""))
        html = (f"<h2>{title}</h2><table border=1 cellspacing=0 cellpadding=3>"
                "<tr>" + "".join(f"<th>{h}</th>" for h in heads) + "</tr>"
                + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>"
                          for row in rows) + "</table>")
        path = documents.PRINT_DIR / f"mfg_transfer_{datetime.now():%Y%m%d-%H%M%S}.pdf"
        documents.to_pdf(html, path)
        _info(self, "Print", f"Saved {path}")

    def tag_print(self) -> None:
        """Tag Print: every barcode tag of the last (or open) transfer, at once."""
        tid = self._edit_tid or self._last_transfer
        if tid is None:
            with SessionLocal() as s:
                tid = s.scalar(select(func.max(MfgTransfer.id)))
        if tid is None:
            _info(self, "Tag Print", "No MFG transfer has been saved yet.")
            return
        TagListDialog(tid, self)._print(False)

    def tag_list(self) -> None:
        tid = self._last_transfer
        if tid is None:
            with SessionLocal() as s:
                tid = s.scalar(select(func.max(MfgTransfer.id)))
        if tid is None:
            _info(self, "Tag List", "No MFG transfer has been saved yet.")
            return
        TagListDialog(tid, self).exec()


class ItemSearchWidget(_Screen):
    """Item Search: one finished piece - stock, cost, stones, value summary -
    and "Delete History & Purchase", which sends the job back to Pending for
    MFG Transfer for correction (§4.10)."""

    def __init__(self, user=None, parent=None):
        super().__init__("Item Search", with_picker=False, parent=parent)
        self.user = user
        self.header.hide()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Stock No, Job No, SKU or Cert No…")
        self.search.returnPressed.connect(self.refresh)
        self.search.setMinimumWidth(280)
        self.toolbar.addWidget(self.search)
        self.button("Search", self.refresh, primary=True)
        self.toolbar.addStretch(1)
        self.button("Print", self.print_card, secondary=True)
        self.button("Tag Print", self.tag_print, secondary=True)
        self.button("Cert Excel", self.cert_excel, secondary=True)
        self.button("Costing Sheet", self.costing_sheet, secondary=True)
        self.button("Job History", self.open_job, secondary=True)
        self.button("Delete History && Purchase", self.delete_item, secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.results = _table(["Stock No", "SKU", "Job No", "Status", "Net", "Price", "Tag"])
        self.results.itemSelectionChanged.connect(self._show_selected)
        split.addWidget(self.results)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.card = QLabel("")
        self.card.setWordWrap(True)
        self.card.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box = QGroupBox("Piece")
        bl = QHBoxLayout(box)
        bl.addWidget(self.card, 1)
        # The product photo ("Double Click Here" in the legacy screen).
        self.photo = QLabel("no photo")
        self.photo.setObjectName("ImageSlot")
        self.photo.setFixedSize(120, 120)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setToolTip("Double-click to enlarge")
        self.photo.mouseDoubleClickEvent = lambda _e: self._enlarge()
        self._photo_path = ""
        bl.addWidget(self.photo)
        rl.addWidget(box)
        self.moves = _table(["Location", "Date", "Vr Type", "Vr No", "Particulars", "Loss %",
                             "Pcs", "Price", "Amount", "HUID"])
        self.moves.setMaximumHeight(170)
        rl.addWidget(self.moves)
        self.stones = _table(["Stone", "Pcs", "Weight", "Price Per", "Amount", "S Type"])
        rl.addWidget(self.stones, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        split.addWidget(right)
        split.setSizes([380, 820])
        self.outer.addWidget(split, 1)
        self._items: list[int] = []
        self.refresh()

    def refresh(self) -> None:
        self.results.setRowCount(0)
        self._items = []
        with SessionLocal() as s:
            for it in mfg.find_items(s, self.search.text()):
                job = s.get(Job, it.job_id) if it.job_id else None
                psku = s.get(ProductSku, it.product_sku_id) if it.product_sku_id else None
                sku = psku.sku_code if psku else ""
                r = self.results.rowCount()
                self.results.insertRow(r)
                self._items.append(it.id)
                for c, v in enumerate([it.stock_no, sku, job.job_no if job else "",
                                       "In Stock" if it.status == "in_stock" else it.status,
                                       it.net_wt, f"{Decimal(str(it.price)):,.2f}",
                                       it.tag_text]):
                    self.results.setItem(r, c, _item(v, right=c in (0, 2, 4, 5, 6)))
        self.results.resizeColumnsToContents()
        if self._items:
            self.results.selectRow(0)
        else:
            self.card.setText("Nothing found." if self.search.text().strip() else
                              "No piece is in ready stock yet - save an MFG transfer first.")
            self.moves.setRowCount(0)
            self.stones.setRowCount(0)
            self.summary.setText("")

    def _current(self) -> int | None:
        rows = self.results.selectionModel().selectedRows()
        return self._items[rows[0].row()] if rows and self._items else None

    def _show_selected(self) -> None:
        iid = self._current()
        if iid is None:
            return
        with SessionLocal() as s:
            it = s.get(StockItem, iid)
            d = mfg.item_detail(s, it)
            job, line, t = d["job"], d["line"], d["transfer"]
            self.job_id = job.id if job else None
            from diagold.services import stock_tools as STK
            made, left = STK.sku_made_left(s, it.product_sku_id)
            status = STK.STATUS_TEXT.get(it.status, it.status)
            holder = s.get(Account, it.holder_account_id) if it.holder_account_id else None
            self._photo_path = (d["sku"].image_finished or d["sku"].image_design) \
                if d["sku"] else ""
            pix = QPixmap(self._photo_path) if self._photo_path else QPixmap()
            if pix.isNull():
                self.photo.setPixmap(QPixmap())
                self.photo.setText("no photo")
            else:
                self.photo.setPixmap(pix.scaled(118, 118, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
            self.card.setText(
                f"<b style='font-size:15px'>Stock No {it.stock_no}</b> · "
                f"{d['sku'].sku_code if d['sku'] else ''} · Job {job.job_no if job else ''}"
                f"<br>Client: {d['client'].name if d['client'] else 'stock'} · "
                f"Ord No: {d['order'].order_no if d['order'] else '—'}"
                f"{' dt ' + d['order'].order_date.strftime('%d-%m-%Y') if d['order'] else ''} · "
                f"Status <b>{status}</b>{' - ' + holder.name if holder else ''} / "
                f"<b>{d['location'].name if d['location'] else ''}</b> · "
                f"This SKU Stock: made <b>{made}</b>, left <b>{left}</b>"
                f"<br>G-Wt {it.gross_wt} g · N-Wt {it.net_wt} g · "
                f"Cost {Decimal(str(it.cost)):,.2f} · Net <b>{Decimal(str(it.price)):,.2f}</b>"
                f" · TAG <b style='color:#A9861B'>{it.tag_text}</b>")
            from diagold.services import sales
            self.moves.setRowCount(0)
            # Every voucher the barcode has been on - made, bought, sold,
            # approval, repair, transfer (2 Oct T-10).
            for h in sales.piece_history(s, it):
                r = self.moves.rowCount()
                self.moves.insertRow(r)
                for c, v in enumerate([h["location"], h["date"], h["vrtype"], h["vrno"],
                                       h["party"], h["loss_pct"] if h["loss_pct"] else "",
                                       h["pcs"], f"{h['price']:,.2f}", f"{h['amount']:,.2f}",
                                       it.huid]):
                    self.moves.setItem(r, c, _item(v, right=c in (3, 5, 6, 7, 8)))
            self.moves.resizeColumnsToContents()
            stones = d["stones"] or [
                {**st, "amount": sales.stone_amount(st)}
                for st in sales.describe(s, it)["stones"]]
            if not d["stones"] and stones:
                d["stone_groups"] = {}
                for st in stones:
                    g = sales.stone_block(st).title()
                    w, a = d["stone_groups"].get(g, (Decimal(0), Decimal(0)))
                    d["stone_groups"][g] = (w + Decimal(str(st.get("weight") or 0)),
                                            a + st["amount"])
            self.stones.setRowCount(0)
            for st in stones:
                r = self.stones.rowCount()
                self.stones.insertRow(r)
                for c, v in enumerate([st.get("label", ""), st.get("pcs"), st.get("weight"),
                                       f"{st.get('price')} {st.get('unit', '')}", st["amount"],
                                       st.get("s_type", "")]):
                    self.stones.setItem(r, c, _item(v, right=c in (1, 2, 4)))
            self.stones.resizeColumnsToContents()
            parts = [f"Net Wt {it.net_wt} g → {Decimal(str(line.metal_amount)):,.0f}"
                     if line else ""]
            for g, (wt, amt) in d["stone_groups"].items():
                parts.append(f"{g} {wt} ct → {amt:,.0f}")
            if line:
                parts.append(f"Labour → {Decimal(str(line.labour)):,.0f}")
            self.summary.setText("<b>Value:</b> " + "   ·   ".join(p for p in parts if p))

    def open_job(self) -> None:
        if self.job_id:
            self.open_requested.emit("production_planning.job_history")

    def _enlarge(self) -> None:
        pix = QPixmap(self._photo_path) if self._photo_path else QPixmap()
        if pix.isNull():
            return
        lbl = QLabel()
        lbl.setPixmap(pix.scaled(640, 640, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation))
        show_in_dialog(self, lbl, "Photo", (680, 680))

    def print_card(self) -> None:
        """Print: the piece card, its voucher history, stones and value."""
        if self._current() is None:
            return
        from diagold.services import documents

        def table(t) -> str:
            head = "".join(f"<th>{t.horizontalHeaderItem(c).text()}</th>"
                           for c in range(t.columnCount()))
            body = "".join("<tr>" + "".join(
                f"<td>{t.item(r, c).text() if t.item(r, c) else ''}</td>"
                for c in range(t.columnCount())) + "</tr>" for r in range(t.rowCount()))
            return f"<table border=1 cellspacing=0 cellpadding=3><tr>{head}</tr>{body}</table>"
        html = (f"<h2>Item Search</h2><p>{self.card.text()}</p><h3>History</h3>"
                f"{table(self.moves)}<h3>Stones</h3>{table(self.stones)}"
                f"<p>{self.summary.text()}</p>")
        path = documents.PRINT_DIR / f"item_{datetime.now():%Y%m%d-%H%M%S}.pdf"
        documents.to_pdf(html, path)
        _info(self, "Print", f"Saved {path}")

    def cert_excel(self) -> None:
        iid = self._current()
        if iid is None:
            return
        from diagold.services import stock_tools as STK
        with SessionLocal() as s:
            it = s.get(StockItem, iid)
            path, _ = QFileDialog.getSaveFileName(self, "Cert Excel", f"cert_{it.stock_no}.xlsx",
                                                  "Excel (*.xlsx)")
            if not path:
                return
            STK.cert_xlsx(s, it, path)
        _info(self, "Cert Excel", f"Saved {path}")

    def costing_sheet(self) -> None:
        """Costing Sheet: the job's costing (frozen on its MFG transfer)."""
        if not self.job_id:
            _info(self, "Costing Sheet", "This piece has no job (bought in / opening stock).")
            return
        from diagold.services import job_costing as JC
        with SessionLocal() as s:
            sheet = JC.costing_sheet(s, s.get(Job, self.job_id))
        path, _ = QFileDialog.getSaveFileName(self, "Costing Sheet",
                                              f"costing_{sheet.job_no}.xlsx", "Excel (*.xlsx)")
        if path:
            JC.sheet_xlsx(sheet, path)
            _info(self, "Costing Sheet", f"Saved {path}")

    def tag_print(self) -> None:
        iid = self._current()
        if iid is None:
            return
        with SessionLocal() as s:
            it = s.get(StockItem, iid)
            line_transfer = mfg.item_detail(s, it)["transfer"]
        if line_transfer is not None:
            TagListDialog(line_transfer.id, self).exec()
            return
        # A piece bought in or loaded as opening stock: its own tag.
        with SessionLocal() as s:
            dlg = TagListDialog(None, self)
            dlg._add_items(s, [s.get(StockItem, iid)])
        dlg._fill()
        dlg.exec()

    def delete_item(self) -> None:
        iid = self._current()
        if iid is None:
            _info(self, "Delete", "Select a piece first.")
            return
        with SessionLocal() as s:
            it = s.get(StockItem, iid)
            no = it.stock_no
            job = s.get(Job, it.job_id) if it.job_id else None
            jn = job.job_no if job else ""
        reason, ok = QInputDialog.getText(
            self, "Delete History & Purchase",
            f"Stock No {no} (job {jn}) leaves stock and the job goes back to Pending for "
            "MFG Transfer, to be corrected and transferred again.\n\nReason:")
        if not ok:
            return
        box = QMessageBox(QMessageBox.Icon.Warning, "Delete",
                          f"Delete Stock No {no}?\nAfter Delete You can not Recover.",
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        also = QCheckBox("Delete SKU Also (only when nothing else uses it)")
        box.setCheckBox(also)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        from diagold.services import admin
        with SessionLocal() as s:
            try:
                msg = admin.delete_item_history(s, no, delete_sku=also.isChecked(),
                                                reason=reason.strip() or "Item Search delete",
                                                user=self.user)
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot delete", str(exc))
                return
        _info(self, "Deleted", msg)
        self.refresh()


# --------------------------------------------------------------------------
# Manufacturing ▸ Issue / Received - "Issue To <Process>" and
# "Received From <Process>" (28 Sept §4.4, R4, T-03)
# --------------------------------------------------------------------------
class ProcessVoucherWidget(_Screen):
    """One voucher per process per karigar, many jobs on it. Show Pending
    lists only the jobs waiting for this process; F3 / F5 work on the
    selected line, as on the legacy voucher."""

    # Grid column -> the saved voucher's field, for Edit.
    EDIT_FIELDS = {"pcs": "pcs", "gross": "gross_wt", "net": "net_wt", "stone_wt": "stone_wt",
                   "finding": "finding", "mould": "mould", "allow": "allow_loss_pct",
                   "rej_type": "rej_type", "rej_pcs": "rej_pcs", "rej_wt": "rej_wt",
                   "scrap": "scrap", "dust": "dust", "mt_price": "mt_price",
                   "manual_price": "manual_price", "manual_amt": "manual_amt"}

    def __init__(self, kind: str, user=None, parent=None):
        self.kind = kind
        issue = kind == "issue"
        super().__init__("Issue To — process" if issue else "Received From — process",
                         with_picker=False, parent=parent)
        self.user = user
        self.header.hide()
        self.h1 = self.findChild(QLabel, "H1")
        self.lines: list[dict[str, Any]] = []
        self.vr = QLabel("")
        self.vr.setObjectName("H2")
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.time = QLineEdit(datetime.now().strftime("%H:%M"))
        self.time.setMaximumWidth(64)
        self.process = QComboBox()
        self.worker = QComboBox()
        with SessionLocal() as s:
            for p in s.scalars(select(ManufacturingProcess).where(
                    ManufacturingProcess.is_active.is_(True)).order_by(ManufacturingProcess.name)):
                self.process.addItem(p.name, p.id)
            for w in s.scalars(select(Account).where(Account.account_type == "Worker")
                               .order_by(Account.name)):
                self.worker.addItem(w.name, w.id)
        self.process.currentIndexChanged.connect(lambda _i: self._process_changed())
        if not issue:
            # A receipt may come from any karigar; picking one narrows Show
            # Pending to what that karigar holds and shows his Mt Bal.
            self.worker.insertItem(0, "(any karigar)", None)
            self.worker.setCurrentIndex(0)
        self.worker.currentIndexChanged.connect(lambda _i: self._worker_changed())
        self.mt_bal = QLabel("")
        self.mt_bal.setObjectName("Muted")
        self.vr_ref = QLineEdit()
        self.vr_ref.setPlaceholderText("RefNo")
        self.vr_ref.setMaximumWidth(110)
        for w in (QLabel("Vr No"), self.vr, QLabel("Date"), self.date, self.time,
                  QLabel("Process"), self.process, QLabel("Account"), self.worker,
                  self.mt_bal, self.vr_ref):
            self.toolbar.addWidget(w)
        self.toolbar.addStretch(1)
        self.photo = QLabel("no photo")
        self.photo.setObjectName("ImageSlot")
        self.photo.setFixedSize(64, 64)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setToolTip("Photo of the selected line - click to enlarge")
        self._photo_path = ""
        self.photo.mousePressEvent = lambda _e: self._enlarge_photo()
        self.toolbar.addWidget(self.photo)
        self.button("Show Pending", self.show_pending, primary=True)
        self.button("Add", self.new_voucher, secondary=True)
        self.button("Edit", self.edit_voucher, secondary=True)
        self.button("Save", self.save)
        self.button("Delete", self.delete_voucher, secondary=True)
        if not issue:
            self.button("Attach Doc", self.attach_doc, secondary=True)
        self.button("F3 Stone", self.f3, secondary=True)
        if issue:
            self.button("F4 Finding", lambda: self._edit_cell("finding"), secondary=True)
            self.button("F5 Metal", self.f5, secondary=True)
            self.button("F7 Mould", lambda: self._edit_cell("mould"), secondary=True)
        self.button("Remove Line", self.remove_line, secondary=True)
        self.button("Print Voucher", self.print_voucher, secondary=True)
        self.button("Statement",
                    lambda: self.open_requested.emit("manufacturing.worker_statement"),
                    secondary=True)
        self.button("Day Book", lambda: self.open_requested.emit(
            "manufacturing.issue_day_book" if issue else "manufacturing.received_day_book"),
            secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)
        QShortcut(QKeySequence("F3"), self, activated=self.f3)
        if issue:
            QShortcut(QKeySequence("F4"), self, activated=lambda: self._edit_cell("finding"))
            QShortcut(QKeySequence("F5"), self, activated=self.f5)
            QShortcut(QKeySequence("F7"), self, activated=lambda: self._edit_cell("mould"))

        # The legacy grid, column for column (28 Sept §4.4). Green = typed.
        self.cols: list[tuple[str, str, bool]] = [
            ("job_no", "JobNo", False), ("sku", "SKU", False), ("c_ref", "C-Ref", False),
            ("metal", "Metal", False), ("colour", "Col", False), ("size", "Size", False),
            ("pcs", "Pcs", True), ("gross", "GrossWt", True), ("net", "NetWt", True),
            ("mt_price", "Mt\nPrice", True), ("mt_amt", "Mt\nAmt", False)]
        if issue:
            self.cols += [("manual_price", "Manual\nPrice", True),
                          ("stone_wt", "Issue\nSt Wt", True),
                          ("extra", "Issue\nExtraMt", True),
                          ("finding", "Issue\nFinding", True),
                          ("mould", "Issue\nMouldWt", True),
                          ("allow", "Allow\nLoss %", True),
                          ("price_on", "L Price\nOn", False), ("f3f5", "F3 / F5", False)]
        else:
            self.cols += [("worker", "From", False), ("rej_type", "Rej.\nType", True),
                          ("rej_pcs", "Rej/Can\nPcs", True), ("rej_wt", "Rej Wt", True),
                          ("scrap", "Scrap", True), ("dust", "Dust", True),
                          ("allow", "Allow\nLoss %", True),
                          ("manual_price", "Manual\nPrice", True),
                          ("manual_amt", "Manual\nAmt", True), ("f3f5", "F3", False)]
        self.cols += [("order_no", "OrderNo", False), ("order_date", "Date", False),
                      ("ref_no", "RefNo", False), ("client", "Client", False)]
        self.grid = _table([h for _k, h, _e in self.cols], ledger=True)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed
                                  | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.grid.itemChanged.connect(self._edited)
        self.grid.itemSelectionChanged.connect(self._line_selected)
        self.outer.addWidget(self.grid, 1)
        self.narration = QLineEdit()
        self.narration.setPlaceholderText("Narration")
        self.outer.addWidget(self.narration)
        self.totals = QLabel("")
        self.totals.setObjectName("Muted")
        self.outer.addWidget(self.totals)
        legend = QLabel(
            ("Pick the process and the karigar, Show Pending lists the jobs whose next step "
             "is this process; tick them, check the weights (green), Save - one voucher "
             "number for all. F3 sends stones from the job's bag with the selected line; "
             "F5 sends metal from a location.") if issue else
            ("Pick the process, Show Pending lists the jobs out on it with any karigar; enter "
             "the weights coming back (green) and Save - each job comes back from whoever "
             "has it. F3 on a line records the stones handed back; the rest count as set."))
        legend.setWordWrap(True)
        legend.setObjectName("Muted")
        self.outer.addWidget(legend)
        self._last_vr: int | None = None
        # The saved voucher open for editing (Edit), None on a new one.
        self._edit_vr: int | None = None
        # Attach Doc on a voucher not saved yet: attached when it saves.
        self._docs: list[str] = []
        self._process_changed()

    # -- header ---------------------------------------------------------
    def _process_changed(self) -> None:
        name = self.process.currentText()
        self.h1.setText(("Issue To " if self.kind == "issue" else "Received From ") + name)
        if self.lines and any(l["process_id"] != self.process.currentData() for l in self.lines):
            self.lines = []
        self.refresh()

    def refresh(self) -> None:
        if self._edit_vr is not None:
            self.vr.setText(f"{self._edit_vr} (editing)")
        else:
            with SessionLocal() as s:
                self.vr.setText(str(production.next_number(s, JobVoucher.vr_no)))
        self._render()
        self._worker_changed()

    def _worker_changed(self) -> None:
        wid = self.worker.currentData()
        if not wid:
            self.mt_bal.setText("")
            return
        with SessionLocal() as s:
            wt, fine = production.worker_metal_balance(s, wid, _pydate(self.date))
        self.mt_bal.setText(f"Mt Bal {wt:.3f} g / fine {fine:.3f}")

    def _line_selected(self) -> None:
        rows = self.grid.selectionModel().selectedRows()
        path = ""
        if rows and rows[0].row() < len(self.lines):
            with SessionLocal() as s:
                job = s.get(Job, self.lines[rows[0].row()]["_job_id"])
                sku = job.product_sku if job else None
                path = (sku.image_finished or sku.image_design) if sku else ""
        pix = QPixmap(path) if path else QPixmap()
        self._photo_path = path if not pix.isNull() else ""
        if pix.isNull():
            self.photo.setPixmap(QPixmap())
            self.photo.setText("no photo")
        else:
            self.photo.setText("")
            self.photo.setPixmap(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))

    def _enlarge_photo(self) -> None:
        if not self._photo_path:
            return
        from diagold.ui.production import show_in_dialog
        big = QLabel()
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        big.setPixmap(QPixmap(self._photo_path).scaled(
            720, 720, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        show_in_dialog(self, big, "Photo", (760, 760))

    def _edit_cell(self, key: str) -> None:
        """F4 / F7: jump to the line's Finding / Mould weight to type it."""
        r = self._selected()
        if r is None:
            return
        c = [k for k, _h, _e in self.cols].index(key)
        self.grid.setCurrentCell(r, c)
        self.grid.editItem(self.grid.item(r, c))

    # -- lines ----------------------------------------------------------
    def show_pending(self) -> None:
        if self._editing_blocked():
            return
        with SessionLocal() as s:
            rows = production.pending_steps(s, self.kind, self.process.currentData(),
                                            worker_id=self.worker.currentData()
                                            if self.kind == "receive" else None)
        have = {l["_job_id"] for l in self.lines}
        rows = [r for r in rows if r["_job_id"] not in have]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Show Pending — {self.h1.text()}")
        dlg.setMinimumSize(760, 400)
        lay = QVBoxLayout(dlg)
        note = QLabel(f"{len(rows)} job(s) pending for this process." if rows else
                      "Nothing is pending for this process - it shows here as soon as it is.")
        note.setObjectName("Muted")
        lay.addWidget(note)
        lst = QListWidget()
        for r in rows:
            it = QListWidgetItem(
                f"{r['job_no']}   {r['sku']}   {r['metal']}   {r['pcs']} pc   "
                + (f"N {r['net']} g   " if r["net"] is not None else "")
                + (f"with {r['worker']}   " if r["worker"] else "") + r["client"])
            it.setData(Qt.ItemDataRole.UserRole, r)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            lst.addItem(it)
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for i in range(lst.count()):
            if lst.item(i).checkState() == Qt.CheckState.Checked:
                r = dict(lst.item(i).data(Qt.ItemDataRole.UserRole))
                if self.kind == "receive":
                    r["gross"] = r["net"] = r["mt_amt"] = None     # typed from the scale
                r["stones"], r["metal_lines"] = {}, []
                self.lines.append(r)
        self._render()

    # -- Add / Edit / Delete a saved voucher (28 Sept §4.4) -----------
    def _editing_blocked(self) -> bool:
        if self._edit_vr is None:
            return False
        _info(self, "Edit", f"Vr {self._edit_vr} is open for editing - only its weights, "
              "prices, date, RefNo and narration can change. To change which jobs, stones "
              "or metal are on it, Delete it and make it again (Add).")
        return True

    def attach_doc(self) -> None:
        """Attach Doc (legacy receipt header): documents kept with the voucher."""
        from diagold.ui.attachments import AttachDocDialog
        vr = self._edit_vr
        AttachDocDialog("job_voucher", vr, f"Vr {vr}" if vr else "new voucher",
                        user=self.user, pending=self._docs, parent=self).exec()

    def new_voucher(self) -> None:
        """Add: a fresh, empty voucher."""
        self._edit_vr = None
        self._docs = []
        self.lines = []
        self.narration.clear()
        self.vr_ref.clear()
        self.refresh()

    def _pick_voucher(self, title: str) -> int | None:
        """The saved vouchers of this kind (this process first), newest on top."""
        with SessionLocal() as s:
            rows = s.execute(
                select(JobVoucher.vr_no, JobVoucher.vr_date, JobVoucher.worker_id,
                       JobVoucher.step_id, Job.job_no)
                .join(Job, Job.id == JobVoucher.job_id)
                .where(JobVoucher.kind == self.kind)
                .order_by(JobVoucher.vr_no.desc(), JobVoucher.id).limit(1000)).all()
            procs = {sid: pid for sid, pid in s.execute(
                select(JobStep.id, JobStep.process_id).where(
                    JobStep.id.in_({r.step_id for r in rows})))}
            names = {a.id: a.name for a in s.scalars(select(Account))}
            pnames = {p.id: p.name for p in s.scalars(select(ManufacturingProcess))}
        vouchers: dict[int, dict] = {}
        for r in rows:
            v = vouchers.setdefault(r.vr_no, {"date": r.vr_date, "worker": names.get(r.worker_id, ""),
                                              "process_id": procs.get(r.step_id), "jobs": []})
            v["jobs"].append(str(r.job_no))
        this = self.process.currentData()
        order = sorted(vouchers, key=lambda n: (vouchers[n]["process_id"] != this, -n))
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(640, 420)
        lay = QVBoxLayout(dlg)
        find = QLineEdit()
        find.setPlaceholderText("Vr No, job no, karigar or process…")
        lay.addWidget(find)
        lst = QListWidget()
        for n in order:
            v = vouchers[n]
            it = QListWidgetItem(
                f"Vr {n}   {v['date']:%d-%m-%Y}   {pnames.get(v['process_id'], '')}   "
                f"{v['worker']}   job {', '.join(v['jobs'])}")
            it.setData(Qt.ItemDataRole.UserRole, n)
            lst.addItem(it)
        if not lst.count():
            _info(self, title, "No voucher of this kind has been saved yet.")
            return None
        lst.setCurrentRow(0)
        find.textChanged.connect(lambda t: [lst.item(i).setHidden(
            t.strip().lower() not in lst.item(i).text().lower()) for i in range(lst.count())])
        lst.itemDoubleClicked.connect(lambda _it: dlg.accept())
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted or lst.currentItem() is None:
            return None
        return lst.currentItem().data(Qt.ItemDataRole.UserRole)

    def edit_voucher(self) -> None:
        """Edit: open a saved voucher, change its figures, Save."""
        vr = self._pick_voucher("Edit — open a saved voucher")
        if vr is None:
            return
        with SessionLocal() as s:
            rows = production.voucher_rows(s, vr)
        if not rows:
            return
        first = rows[0]
        self._edit_vr = None
        self.lines = []
        i = self.process.findData(first["process_id"])
        if i >= 0:
            self.process.setCurrentIndex(i)
        if self.kind == "issue":
            i = self.worker.findData(first["worker_id"])
            if i >= 0:
                self.worker.setCurrentIndex(i)
        self.date.setDate(_qdate(first["vr_date"]))
        self.time.setText(first["vr_time"] or "")
        self.vr_ref.setText(first["vr_ref"] or "")
        self.narration.setText(first["remark"] or "")
        for r in rows:
            r["stones"], r["metal_lines"] = {}, []
        self.lines = rows
        self._edit_vr = self._last_vr = vr
        self.refresh()
        self.totals.setText(f"Editing Vr {vr} - change the green cells and Save.")

    def delete_voucher(self) -> None:
        """Delete: the voucher open for editing, or one picked from the list."""
        vr = self._edit_vr or self._pick_voucher("Delete — pick the voucher")
        if vr is None:
            return
        with SessionLocal() as s:
            jobs = [str(r.job_no) for r in s.execute(
                select(Job.job_no).join(JobVoucher, JobVoucher.job_id == Job.id)
                .where(JobVoucher.vr_no == vr))]
        if QMessageBox.question(
                self, "Delete",
                f"Delete Vr {vr} (job {', '.join(jobs)})?\n\nThe jobs go back to pending "
                "for this step; stones and metal sent with it go back. It is kept in the "
                "deletion log.") != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                production.delete_job_voucher(s, vr, user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot delete", str(exc))
                return
        self.new_voucher()
        self._last_vr = None
        self.totals.setText(f"Vr {vr} deleted.")

    def _render(self) -> None:
        self.grid.blockSignals(True)
        self.grid.setRowCount(0)
        net_total = Decimal("0")
        for ln in self.lines:
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            for c, (key, _h, editable) in enumerate(self.cols):
                if key == "f3f5" and self._edit_vr is not None:
                    parts = []
                    if ln.get("saved_stones"):
                        parts.append(f"{ln['saved_stones']} st")
                    if ln.get("saved_metal"):
                        parts.append(f"{ln['saved_metal']} g")
                    v = " · ".join(parts)
                elif key == "f3f5":
                    parts = []
                    if ln.get("stones"):
                        parts.append(f"{sum(ln['stones'].values())} st")
                    if ln.get("metal_lines"):
                        parts.append(f"{sum(Decimal(str(m['weight'])) for m in ln['metal_lines'])} g")
                    v = " · ".join(parts)
                elif key == "allow" and ln.get(key) is not None:
                    v = f"{Decimal(str(ln[key])):.2f}"
                elif key == "extra" and ln.get("metal_lines"):
                    v = sum(Decimal(str(m["weight"])) for m in ln["metal_lines"])
                else:
                    v = ln.get(key)
                wb = ln.get("weight_bearing", True)
                edit = editable and (wb or key in ("pcs", "rej_type", "manual_price",
                                                   "manual_amt"))
                if key == "extra" and ln.get("metal_lines"):
                    edit = False        # F5 metal is the extra metal on this line
                if self._edit_vr is not None and key not in self.EDIT_FIELDS:
                    edit = False
                it = _item(v if v is not None else "", TINT_RECEIVE if edit else None,
                           right=key not in ("sku", "c_ref", "metal", "colour", "worker",
                                             "client", "ref_no", "f3f5", "size",
                                             "rej_type", "price_on"))
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                if edit:
                    flags |= Qt.ItemFlag.ItemIsEditable
                it.setFlags(flags)
                self.grid.setItem(r, c, it)
            net_total += Decimal(str(ln.get("net") or 0))
        self.grid.blockSignals(False)
        _fit_columns(self.grid, len(self.cols) - 1)
        self.totals.setText(f"<b>{len(self.lines)} job(s)</b>    Net {net_total:.3f} g"
                            if self.lines else "No jobs on this voucher yet - Show Pending.")

    def _edited(self, it: QTableWidgetItem) -> None:
        r, c = it.row(), it.column()
        key = self.cols[c][0]
        text = it.text().replace(",", "").strip()
        ln = self.lines[r]
        if key in ("pcs", "rej_pcs"):
            ln[key] = int(text) if text.isdigit() else 0
        elif key == "rej_type":
            ln[key] = it.text().strip()
        else:
            ln[key] = _num(text)
        # Amounts follow the net weight and the price, as on the legacy grid.
        if key in ("net", "mt_price", "manual_price"):
            net = Decimal(str(ln.get("net") or 0))
            if ln.get("mt_price") is not None:
                ln["mt_amt"] = (Decimal(str(ln["mt_price"])) * net).quantize(Decimal("0.01"))
            if ln.get("manual_price") is not None and self.kind == "receive":
                ln["manual_amt"] = (Decimal(str(ln["manual_price"])) * net).quantize(
                    Decimal("0.01"))
            self._render()
            self.grid.selectRow(r)

    def _selected(self) -> int | None:
        rows = self.grid.selectionModel().selectedRows()
        if not rows or not self.lines:
            _info(self, "Voucher", "Select a line first.")
            return None
        return rows[0].row()

    def remove_line(self) -> None:
        if self._editing_blocked():
            return
        r = self._selected()
        if r is not None:
            self.lines.pop(r)
            self._render()

    def f3(self) -> None:
        if self._editing_blocked():
            return
        r = self._selected()
        if r is None:
            return
        from diagold.ui.production import StoneBagDialog
        ln = self.lines[r]
        worker = self.worker.currentData() if self.kind == "issue" else ln["worker_id"]
        dlg = StoneBagDialog(ln["_job_id"], self.kind, worker, ln.get("stones") or {}, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ln["stones"] = dlg.values
            self._render()

    def f5(self) -> None:
        if self._editing_blocked():
            return
        r = self._selected()
        if r is None:
            return
        from diagold.ui.production import MetalLinesDialog
        dlg = MetalLinesDialog(self.lines[r].get("metal_lines") or [], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.lines[r]["metal_lines"] = dlg.lines()
            self._render()

    # -- save / print ---------------------------------------------------
    def save(self) -> None:
        if not self.lines:
            _info(self, "Save", "Show Pending and pick the jobs first.")
            return
        issue = self.kind == "issue"
        if issue and not self.worker.currentData():
            _info(self, "Save", "Choose the karigar (Account).")
            return
        if self._edit_vr is not None:
            self._save_edit()
            return
        what = (f"issue of {len(self.lines)} job(s) to {self.worker.currentText()}" if issue
                else f"receipt of {len(self.lines)} job(s)")
        if not confirm_save(self, what):
            return
        payload = []
        for ln in self.lines:
            payload.append({
                "job_id": ln["_job_id"], "step_id": ln["_step_id"], "pcs": ln.get("pcs"),
                "gross": ln.get("gross"), "net": ln.get("net"),
                "stone_wt": ln.get("stone_wt"), "rej_pcs": ln.get("rej_pcs"),
                "rej_wt": ln.get("rej_wt"), "scrap": ln.get("scrap"), "dust": ln.get("dust"),
                "allow": ln.get("allow"), "stones": ln.get("stones") or {},
                "metal": ln.get("metal_lines") or [], "remark": self.narration.text().strip(),
                "extra": ln.get("extra"), "finding": ln.get("finding"),
                "mould": ln.get("mould"), "mt_price": ln.get("mt_price"),
                "mt_amt": ln.get("mt_amt"), "manual_price": ln.get("manual_price"),
                "manual_amt": ln.get("manual_amt"), "rej_type": ln.get("rej_type"),
                "price_on": ln.get("price_on") or "NetWt", "ref_no": self.vr_ref.text().strip(),
            })
        with SessionLocal() as s:
            try:
                vr = production.post_multi_voucher(
                    s, self.kind, self.worker.currentData(), payload,
                    vr_date=_pydate(self.date), vr_time=self.time.text().strip(),
                    user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        from diagold.ui.attachments import attach_pending
        attach_pending("job_voucher", vr, self._docs, self.user)
        self._docs = []
        self._last_vr = vr
        n = len(self.lines)
        self.lines = []
        self.narration.clear()
        self.vr_ref.clear()
        self.refresh()
        self.totals.setText(f"Saved Vr {vr}: {n} job(s). Print Voucher prints it.")

    def _save_edit(self) -> None:
        vr = self._edit_vr
        if not confirm_save(self, f"the changes to Vr {vr}"):
            return
        changes = {}
        for ln in self.lines:
            ch = {field: ln.get(key) for key, field in self.EDIT_FIELDS.items()}
            ch["mt_amt"] = ln.get("mt_amt")
            changes[ln["_voucher_id"]] = ch
        with SessionLocal() as s:
            try:
                production.update_voucher(
                    s, vr, changes, vr_date=_pydate(self.date),
                    vr_time=self.time.text().strip(), ref_no=self.vr_ref.text().strip(),
                    remark=self.narration.text().strip(),
                    user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        self.new_voucher()
        self._last_vr = vr
        self.totals.setText(f"Vr {vr} updated. Print Voucher prints it.")

    def print_voucher(self) -> None:
        if self._last_vr is None:
            _info(self, "Print", "Save a voucher first - Print Voucher prints the last one.")
            return
        with SessionLocal() as s:
            v = s.scalar(select(JobVoucher).where(JobVoucher.vr_no == self._last_vr,
                                                  JobVoucher.kind == self.kind))
            vid = v.id if v else None
        if vid:
            from diagold.ui.production import voucher_view
            voucher_view(self, vid)
