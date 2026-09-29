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
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
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

from diagold.db.models import (Account, Job, JobVoucher, ManufacturingProcess, Metal,
                               MfgTransfer, StockItem)
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
    ("job_no", "Job No", False), ("sku", "SKU", False), ("metal", "Metal", False),
    ("title", "Title", False), ("loss_pct", "Loss%", False), ("pcs", "Pcs", False),
    ("gross_wt", "G-Wt", False), ("net_wt", "N-Wt", False), ("fine_wt", "FineWt", False),
    ("metal_rate", "Metal\nRate", False), ("metal_amount", "Metal\nAmount", False),
    ("stone_amount", "Stone\nAmount", False), ("setting_amount", "Setting\nAmount", False),
    ("labour_rate", "Labour\nPrice", False), ("labour_weight", "Labour\nWt", True),
    ("labour", "Labour", False), ("manual_amount", "Manual\nAmount", True),
    ("total", "Total\nAmount", False), ("margin_pct", "Margin\n%", True),
    ("margin_amount", "Margin\nAmount", False), ("price_per_pcs", "Price\nPer Pcs", False),
    ("tag_text", "Tag\nPrice", False), ("is_repair", "Repair\n(tag 0)", True),
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
    piece if wanted, or write a text file for the label printer."""

    def __init__(self, transfer_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag List")
        self.setMinimumSize(860, 420)
        lay = QVBoxLayout(self)
        self.items: list[dict] = []
        with SessionLocal() as s:
            t = s.get(MfgTransfer, transfer_id)
            self.title = f"Tag List — MFG Transfer Vr {t.vr_no}" if t else "Tag List"
            for it in (mfg.stock_for_transfer(s, t) if t else []):
                job = s.get(Job, it.job_id)
                self.items.append({
                    "id": it.id, "stock_no": it.stock_no,
                    "sku": job.product_sku.sku_code if job and job.product_sku else "",
                    "c_ref": job.c_ref if job else "", "pcs": it.pcs,
                    "gross": it.gross_wt, "net": it.net_wt,
                    "price": f"{Decimal(str(it.price)):,.2f}", "tag": it.tag_text,
                })
        lay.addWidget(QLabel(f"<b>{self.title}</b> — the Stock No is the bar code."))
        opts = QHBoxLayout()
        self.o_price = QCheckBox("Print Tag Price")
        self.o_price.setChecked(True)
        self.o_cref = QCheckBox("C-Ref Barcode")
        self.o_pcs = QCheckBox("Pcs Wise Tag Print")
        for w in (self.o_price, self.o_cref, self.o_pcs):
            w.toggled.connect(lambda _on: self._fill())
            opts.addWidget(w)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.grid = _table(["", "Sno", "Bar Code", "SKU", "Pcs", "Gross", "Net", "Price/Pcs",
                            "Tag"])
        lay.addWidget(self.grid, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for label, fn in (("Clear Tag List", self._clear), ("Create Txt", self._txt),
                          ("Print Selected", lambda: self._print(True)),
                          ("Print All", lambda: self._print(False))):
            b = buttons.addButton(label, QDialogButtonBox.ButtonRole.ActionRole)
            b.clicked.connect(fn)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill()

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
                    it["tag"] if self.o_price.isChecked() else ""]
            for c, v in enumerate(vals, start=1):
                self.grid.setItem(r, c, _item(v, right=c not in (3,)))
        self.grid.resizeColumnsToContents()

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
        t = _table([self.grid.horizontalHeaderItem(c).text() for c in range(1, 9)])
        for r in rows:
            t.insertRow(t.rowCount())
            for c in range(1, 9):
                t.setItem(t.rowCount() - 1, c - 1, _item(self.grid.item(r, c).text()))
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
            fh.write("BARCODE\tSKU\tPCS\tGROSS\tNET\tTAG\n")
            for r in rows:
                fh.write("\t".join(self.grid.item(r, c).text() for c in (2, 3, 4, 5, 6, 8))
                         + "\n")
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

        self.vr = QLabel("")
        self.vr.setObjectName("H2")
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.date.dateChanged.connect(lambda _d: self.fill_prices())
        self.ref = QLineEdit()
        self.ref.setPlaceholderText("Ref no")
        self.ref.setMaximumWidth(160)
        for w in (QLabel("Vr No"), self.vr, QLabel("Date"), self.date, self.ref):
            self.toolbar.addWidget(w)
        self.toolbar.addStretch(1)
        self.button("Show Pending", self.show_pending, primary=True)
        self.button("Fill Prices", self.fill_prices)
        self.button("Save", self.save)
        self.button("Remove Line", self.remove_line, secondary=True)
        self.button("Cost Break-up", self.show_breakup, secondary=True)
        self.button("Tag List", self.tag_list, secondary=True)
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
            nxt = production.next_number(s, MfgTransfer.vr_no)
        self.vr.setText(f"{nxt}")

    def show_pending(self) -> None:
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
        }

    def fill_prices(self, keep_overrides: bool = True) -> None:
        overrides = {}
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
                meta[jid] = (job.job_no, job.product_sku.sku_code if job.product_sku else "",
                             metal.name if metal else "", pct, mfg.last_gross(s, job))
        self._render(meta, overrides)

    def _render(self, meta: dict, overrides: dict) -> None:
        self._filling = True
        self.grid.setRowCount(0)
        totals = {"total": Decimal("0"), "price": Decimal("0"), "net": Decimal("0")}
        for jid in self._job_ids:
            p = self._results[jid]
            job_no, sku, metal, loss_pct, gross = meta[jid]
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            vals = {
                "job_no": job_no, "sku": sku, "metal": metal, "title": f"{p.title:.0f}",
                "loss_pct": loss_pct, "pcs": p.pcs, "gross_wt": gross, "net_wt": p.net_wt,
                "fine_wt": p.fine_wt, "metal_rate": f"{p.metal_rate:,.2f}",
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
                               right=key not in ("sku", "metal"), bold=bold)
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
        if not confirm_save(self, f"MFG transfer of {len(self._job_ids)} job(s)"):
            return
        lines = [{"job_id": jid, **self._overrides(r)} for r, jid in enumerate(self._job_ids)]
        with SessionLocal() as s:
            try:
                t = mfg.post_transfer(s, lines, vr_date=_pydate(self.date),
                                      ref_no=self.ref.text().strip(),
                                      user_id=getattr(self.user, "id", None))
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
        TagListDialog(tid, self).exec()

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
        self.button("Tag Print", self.tag_print, secondary=True)
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
        bl = QVBoxLayout(box)
        bl.addWidget(self.card)
        rl.addWidget(box)
        self.moves = _table(["Location", "Date", "Vr Type", "Vr No", "Loss %", "Pcs",
                             "Price", "Cost Price", "HUID"])
        self.moves.setMaximumHeight(90)
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
                job = s.get(Job, it.job_id)
                sku = job.product_sku.sku_code if job and job.product_sku else ""
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
            self.card.setText(
                f"<b style='font-size:15px'>Stock No {it.stock_no}</b> · "
                f"{d['sku'].sku_code if d['sku'] else ''} · Job {job.job_no if job else ''}"
                f"<br>Client: {d['client'].name if d['client'] else 'stock'} · "
                f"Ord No: {d['order'].order_no if d['order'] else '—'}"
                f"{' dt ' + d['order'].order_date.strftime('%d-%m-%Y') if d['order'] else ''} · "
                f"{'In Stock' if it.status == 'in_stock' else it.status} at "
                f"<b>{d['location'].name if d['location'] else ''}</b> · "
                f"This SKU in stock: {d['same_sku_in_stock']}"
                f"<br>G-Wt {it.gross_wt} g · N-Wt {it.net_wt} g · "
                f"Cost {Decimal(str(it.cost)):,.2f} · Net <b>{Decimal(str(it.price)):,.2f}</b>"
                f" · TAG <b style='color:#A9861B'>{it.tag_text}</b>")
            self.moves.setRowCount(0)
            if t is not None:
                self.moves.insertRow(0)
                for c, v in enumerate([d["location"].name if d["location"] else "", t.vr_date,
                                       "MF", t.vr_no, line.loss_pct, line.pcs,
                                       f"{Decimal(str(line.price_per_pcs)):,.2f}",
                                       f"{Decimal(str(line.total)):,.2f}", it.huid]):
                    self.moves.setItem(0, c, _item(v))
            self.stones.setRowCount(0)
            for st in d["stones"]:
                r = self.stones.rowCount()
                self.stones.insertRow(r)
                for c, v in enumerate([st["label"], st["pcs"], st["weight"],
                                       f"{st['price']} {st['unit']}", st["amount"],
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

    def tag_print(self) -> None:
        iid = self._current()
        if iid is None:
            return
        with SessionLocal() as s:
            it = s.get(StockItem, iid)
            line_transfer = mfg.item_detail(s, it)["transfer"]
        if line_transfer is not None:
            TagListDialog(line_transfer.id, self).exec()

    def delete_item(self) -> None:
        iid = self._current()
        if iid is None:
            _info(self, "Delete", "Select a piece first.")
            return
        with SessionLocal() as s:
            it = s.get(StockItem, iid)
            no = it.stock_no
            job = s.get(Job, it.job_id)
            jn = job.job_no if job else ""
        reason, ok = QInputDialog.getText(
            self, "Delete History & Purchase",
            f"Stock No {no} (job {jn}) leaves stock and the job goes back to Pending for "
            "MFG Transfer, to be corrected and transferred again.\n\nReason:")
        if not ok:
            return
        if QMessageBox.question(self, "Delete", f"Delete Stock No {no}?") \
                != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                mfg.delete_stock_item(s, s.get(StockItem, iid),
                                      user_id=getattr(self.user, "id", None),
                                      reason=reason.strip())
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot delete", str(exc))
                return
        _info(self, "Deleted", f"Stock No {no} deleted. Job {jn} is back in Pending for "
                               "MFG Transfer.")
        self.refresh()


# --------------------------------------------------------------------------
# Manufacturing ▸ Issue / Received - "Issue To <Process>" and
# "Received From <Process>" (28 Sept §4.4, R4, T-03)
# --------------------------------------------------------------------------
class ProcessVoucherWidget(_Screen):
    """One voucher per process per karigar, many jobs on it. Show Pending
    lists only the jobs waiting for this process; F3 / F5 work on the
    selected line, as on the legacy voucher."""

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
        for w in (QLabel("Vr No"), self.vr, QLabel("Date"), self.date, self.time,
                  QLabel("Process"), self.process):
            self.toolbar.addWidget(w)
        if issue:
            self.toolbar.addWidget(QLabel("Account"))
            self.toolbar.addWidget(self.worker)
        self.toolbar.addStretch(1)
        self.button("Show Pending", self.show_pending, primary=True)
        self.button("Save", self.save)
        self.button("F3 Stone", self.f3, secondary=True)
        if issue:
            self.button("F5 Metal", self.f5, secondary=True)
        self.button("Remove Line", self.remove_line, secondary=True)
        self.button("Print Voucher", self.print_voucher, secondary=True)
        self.button("Day Book", lambda: self.open_requested.emit(
            "manufacturing.issue_day_book" if issue else "manufacturing.received_day_book"),
            secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)
        QShortcut(QKeySequence("F3"), self, activated=self.f3)
        if issue:
            QShortcut(QKeySequence("F5"), self, activated=self.f5)

        self.cols: list[tuple[str, str, bool]] = [
            ("job_no", "JobNo", False), ("sku", "SKU", False), ("c_ref", "C-Ref", False),
            ("metal", "Metal", False), ("colour", "Col", False), ("pcs", "Pcs", True),
            ("gross", "GrossWt", True), ("net", "NetWt", True)]
        if issue:
            self.cols += [("stone_wt", "Issue\nSt Wt", True)]
        else:
            self.cols += [("worker", "From", False), ("rej_pcs", "Rej\nPcs", True),
                          ("rej_wt", "Rej Wt", True), ("scrap", "Scrap", True),
                          ("dust", "Dust", True)]
        self.cols += [("allow", "Allow\nLoss %", True), ("f3f5", "F3 / F5", False),
                      ("order_no", "OrderNo", False), ("order_date", "Date", False),
                      ("ref_no", "RefNo", False), ("client", "Client", False)]
        self.grid = _table([h for _k, h, _e in self.cols], ledger=True)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed
                                  | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.grid.itemChanged.connect(self._edited)
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
        self._process_changed()

    # -- header ---------------------------------------------------------
    def _process_changed(self) -> None:
        name = self.process.currentText()
        self.h1.setText(("Issue To " if self.kind == "issue" else "Received From ") + name)
        if self.lines and any(l["process_id"] != self.process.currentData() for l in self.lines):
            self.lines = []
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as s:
            self.vr.setText(str(production.next_number(s, JobVoucher.vr_no)))
        self._render()

    # -- lines ----------------------------------------------------------
    def show_pending(self) -> None:
        with SessionLocal() as s:
            rows = production.pending_steps(s, self.kind, self.process.currentData())
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
                    r["gross"] = r["net"] = None     # typed from the scale
                r["stones"], r["metal_lines"] = {}, []
                self.lines.append(r)
        self._render()

    def _render(self) -> None:
        self.grid.blockSignals(True)
        self.grid.setRowCount(0)
        net_total = Decimal("0")
        for ln in self.lines:
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            for c, (key, _h, editable) in enumerate(self.cols):
                if key == "f3f5":
                    parts = []
                    if ln.get("stones"):
                        parts.append(f"{sum(ln['stones'].values())} st")
                    if ln.get("metal_lines"):
                        parts.append(f"{sum(Decimal(str(m['weight'])) for m in ln['metal_lines'])} g")
                    v = " · ".join(parts)
                elif key == "allow" and ln.get(key) is not None:
                    v = f"{Decimal(str(ln[key])):.2f}"
                else:
                    v = ln.get(key)
                wb = ln.get("weight_bearing", True)
                edit = editable and (wb or key in ("pcs",))
                it = _item(v if v is not None else "", TINT_RECEIVE if edit else None,
                           right=key not in ("sku", "c_ref", "metal", "colour", "worker",
                                             "client", "ref_no", "f3f5"))
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
        if key in ("pcs", "rej_pcs"):
            self.lines[r][key] = int(text) if text.isdigit() else 0
        else:
            self.lines[r][key] = _num(text)

    def _selected(self) -> int | None:
        rows = self.grid.selectionModel().selectedRows()
        if not rows or not self.lines:
            _info(self, "Voucher", "Select a line first.")
            return None
        return rows[0].row()

    def remove_line(self) -> None:
        r = self._selected()
        if r is not None:
            self.lines.pop(r)
            self._render()

    def f3(self) -> None:
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
        self._last_vr = vr
        n = len(self.lines)
        self.lines = []
        self.narration.clear()
        self.refresh()
        self.totals.setText(f"Saved Vr {vr}: {n} job(s). Print Voucher prints it.")

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
