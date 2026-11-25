"""Ready-stock voucher screens (2 Oct Session 3): Sale ▸ Ready Stock ▸ Sale /
Sale Return / Approval / Approval Return / Ready Repair Issue, and Purchase ▸
Ready Items / Ready Item Return / Opening Stock. One screen, the voucher type
decides the header and the way pieces are added:

* scan or type a barcode (Stock No) in "Read Barcode / SKU" - an unknown one
  says "Item not found"; a SKU opens the pieces of it that can go on;
* Show Stock / Show App (on approval with the party) / Sold pieces;
* From Order - the Pending Orders picker, Fill Balance Pcs / Fill Stock Qty;
* Read Barcode From Approval - pieces out on approval with this customer;
* a purchase or opening adds a new piece through Add Piece.

Add / Edit / Save / Delete as on every legacy voucher; Print; Excel Invoice
(the client's breakup format) on a sale; Stone Breakup per line.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
# Number boxes are text boxes (23 Nov: spin boxes showed nothing on the client's
# Windows PC); same names, same API - see diagold/ui/numbox.py.
from diagold.ui.numbox import DoubleSpinBox as QDoubleSpinBox  # noqa: E402,F811
from diagold.ui.numbox import SpinBox as QSpinBox  # noqa: E402,F811
from sqlalchemy import select

from diagold.db.models import (Account, Location, Metal, ProductSku, ReadyVoucher,
                               ReadyVoucherLine, StockItem)
from diagold.db.session import SessionLocal
from diagold.services import price_charts as PC
from diagold.services import sales as S
from diagold.services.production import ProductionError
from diagold.ui.confirm import confirm_save
from diagold.ui.crud import auto_fit
from diagold.ui import photo_cache
from diagold.ui.production import (TINT_RECEIVE, _Screen, _item, _pydate, _qdate,
                                   _table, show_in_dialog)

D = Decimal


def _num(text: str) -> Decimal | None:
    t = (text or "").replace(",", "").strip()
    try:
        return Decimal(t) if t else None
    except Exception:  # noqa: BLE001
        return None


def _info(parent, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def _warn(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


# --------------------------------------------------------------------------
# Pickers
# --------------------------------------------------------------------------
PIECE_COLS = [("location", "Location"), ("stock_no", "Barcode"), ("job_no", "Job No"),
              ("sku", "SKU"), ("c_ref", "C-Ref"), ("metal", "Metal"), ("colour", "Col"),
              ("size", "Size"), ("pcs", "Pcs"), ("gross_wt", "G-Wt"), ("net_wt", "N-Wt"),
              ("price", "Price"), ("holder", "With"), ("ord_no", "Ord No")]


class PiecePicker(QDialog):
    """Show Stock / Show App / Current Stock: tick the pieces to add."""

    def __init__(self, rows: list[dict], title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(1000, 480)
        self.rows = rows
        lay = QVBoxLayout(self)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Search barcode, SKU, job, C-Ref…")
        self.find.textChanged.connect(self._filter)
        lay.addWidget(self.find)
        self.grid = _table([""] + [h for _k, h in PIECE_COLS])
        self.grid.setRowCount(len(rows))
        for r, row in enumerate(rows):
            tick = QTableWidgetItem("")
            tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            tick.setCheckState(Qt.CheckState.Unchecked)
            self.grid.setItem(r, 0, tick)
            for c, (k, _h) in enumerate(PIECE_COLS, start=1):
                v = row.get(k)
                self.grid.setItem(r, c, _item(v if v is not None else "",
                                              right=isinstance(v, (int, Decimal))))
        auto_fit(self.grid)
        lay.addWidget(self.grid, 1)
        note = QLabel(f"{len(rows)} piece(s)." if rows else "Nothing to pick.")
        note.setObjectName("Muted")
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        sel_all = bb.addButton("Tick All", QDialogButtonBox.ButtonRole.ActionRole)
        sel_all.clicked.connect(self._tick_all)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _filter(self, text: str) -> None:
        t = text.strip().lower()
        for r in range(self.grid.rowCount()):
            hay = " ".join(self.grid.item(r, c).text() for c in range(1, self.grid.columnCount()))
            self.grid.setRowHidden(r, bool(t) and t not in hay.lower())

    def _tick_all(self) -> None:
        for r in range(self.grid.rowCount()):
            if not self.grid.isRowHidden(r):
                self.grid.item(r, 0).setCheckState(Qt.CheckState.Checked)

    def picked(self) -> list[dict]:
        return [self.rows[r] for r in range(self.grid.rowCount())
                if self.grid.item(r, 0).checkState() == Qt.CheckState.Checked]


class PendingOrdersDialog(QDialog):
    """From Order (legacy Pending Orders): Sno, OrdNo, RefNo, SKU, C Ref, Ord
    Pcs, Cancel Pcs, Shipped Pcs, Bal Pcs, Stock Pcs, Inv Pcs, Price and the
    pieces to take now; Fill Balance Pcs / Fill Stock Qty."""

    COLS = [("ord_no", "OrdNo"), ("ref_no", "RefNo"), ("sku", "SKU"), ("c_ref", "C Ref"),
            ("ord_pcs", "Ord Pcs"), ("cancel_pcs", "Cancel Pcs"), ("shipped_pcs", "Shipped Pcs"),
            ("bal_pcs", "Bal Pcs"), ("stock_pcs", "Stock Pcs"), ("inv_pcs", "Inv Pcs"),
            ("price", "Price")]

    def __init__(self, rows: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pending Orders")
        self.setMinimumSize(1000, 460)
        self.rows = rows
        lay = QVBoxLayout(self)
        self.grid = _table(["Sno"] + [h for _k, h in self.COLS] + ["Take"])
        self.grid.setRowCount(len(rows))
        take_col = len(self.COLS) + 1
        for r, row in enumerate(rows):
            self.grid.setItem(r, 0, _item(r + 1, right=True))
            for c, (k, _h) in enumerate(self.COLS, start=1):
                self.grid.setItem(r, c, _item(row[k], right=k not in ("ref_no", "sku", "c_ref")))
            take = _item(0, TINT_RECEIVE, right=True)
            take.setFlags(take.flags() | Qt.ItemFlag.ItemIsEditable)
            self.grid.setItem(r, take_col, take)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.AnyKeyPressed)
        auto_fit(self.grid)
        lay.addWidget(self.grid, 1)
        note = QLabel("Type the pieces to take in Take (green), or Fill Balance Pcs / Fill "
                      "Stock Qty. Pieces made on the order's own jobs are taken first."
                      if rows else "No pending order for this customer.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        for label, fn in (("Fill Balance Pcs", self._fill_bal), ("Fill Stock Qty", self._fill_stock)):
            b = bb.addButton(label, QDialogButtonBox.ButtonRole.ActionRole)
            b.clicked.connect(fn)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _set(self, fn) -> None:
        col = len(self.COLS) + 1
        for r, row in enumerate(self.rows):
            self.grid.item(r, col).setText(str(fn(row)))

    def _fill_bal(self) -> None:
        self._set(lambda row: max(row["bal_pcs"] - row["inv_pcs"], 0))

    def _fill_stock(self) -> None:
        self._set(lambda row: max(min(row["bal_pcs"], row["stock_pcs"]) - row["inv_pcs"], 0))

    def takes(self) -> dict[int, int]:
        col = len(self.COLS) + 1
        out = {}
        for r, row in enumerate(self.rows):
            t = self.grid.item(r, col).text().strip()
            if t.isdigit() and int(t) > 0:
                out[row["order_line_id"]] = int(t)
        return out


# Sale-side vouchers that can price from the client's chart (5 Oct T-05).
CHART_TYPES = ("rs_sale", "rs_approval")

STONE_COLS = [("label", "Stone"), ("s_type", "S Type"), ("size", "Size"), ("pcs", "Pcs"),
              ("weight", "Cts"), ("unit", "Per"), ("price", "Price")]


class StoneBreakupDialog(QDialog):
    """Stone Breakup: the stones of one piece with their price; prices (and,
    on a new piece, every column) can be typed, rows added or removed."""

    def __init__(self, stones: list[dict], parent=None, *, editable: bool = True,
                 full: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Stone Breakup")
        self.setMinimumSize(760, 420)
        self.full = full
        lay = QVBoxLayout(self)
        self.grid = QTableWidget(0, len(STONE_COLS) + 1)
        self.grid.setHorizontalHeaderLabels([h for _k, h in STONE_COLS] + ["Amount"])
        self.grid.verticalHeader().setVisible(False)
        auto_fit(self.grid)
        for st in stones:
            self._add(st)
        self.grid.itemChanged.connect(self._recalc)
        lay.addWidget(self.grid, 1)
        self.total = QLabel("")
        lay.addWidget(self.total)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        if full:
            for label, fn in (("Add Row", lambda: self._add({"unit": "ct"})),
                              ("Remove Row", self._remove)):
                b = bb.addButton(label, QDialogButtonBox.ButtonRole.ActionRole)
                b.clicked.connect(fn)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.editable = editable
        if not editable:
            self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._recalc()

    def _add(self, st: dict) -> None:
        self.grid.blockSignals(True)
        r = self.grid.rowCount()
        self.grid.insertRow(r)
        for c, (k, _h) in enumerate(STONE_COLS):
            it = QTableWidgetItem(str(st.get(k) if st.get(k) is not None else ""))
            if not (self.full or k == "price"):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                it.setBackground(TINT_RECEIVE)
            self.grid.setItem(r, c, it)
        amt = QTableWidgetItem("")
        amt.setFlags(amt.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.grid.setItem(r, len(STONE_COLS), amt)
        if self.full:
            self._pickers(r, st)
        self.grid.blockSignals(False)

    # -- SSKU / Size picked from the Stone SKU master (19 Nov: "stone breakup me
    # sku list nhi aa rhi") - the stone's name, then its sizes, as the legacy
    # List of Stone SKU; the size's S Type and cost fill in.
    def _sizes(self) -> dict:
        if not hasattr(self, "_size_map"):
            from diagold.ui.stock_transfer import _stone_sizes
            self._size_map = _stone_sizes()
        return self._size_map

    def _pickers(self, r: int, st: dict) -> None:
        sizes = self._sizes()
        name = QComboBox()
        name.addItem("")
        name.addItems(list(sizes))
        size = QComboBox()
        size.setEditable(True)
        label = (st.get("label") or "").strip()
        stone = label if label in sizes else next(
            (n for n in sizes if label.upper().startswith(n.upper() + " ")), label)
        name.setCurrentText(stone)
        size.addItems([z for z, *_x in sizes.get(stone, [])])
        size.setCurrentText(str(st.get("size") or ""))

        def stone_changed(_i: int = 0, n=name, z=size) -> None:
            z.blockSignals(True)
            z.clear()
            rows = sizes.get(n.currentText(), [])
            z.addItems([x for x, *_y in rows])
            z.setCurrentText(rows[0][0] if len(rows) == 1 else "")
            z.blockSignals(False)
            size_changed()

        def size_changed(_t: str = "", n=name, z=size, row=r) -> None:
            hit = next((x for x in sizes.get(n.currentText(), [])
                        if x[0].lower() == z.currentText().strip().lower()), None)
            self.grid.blockSignals(True)
            self.grid.item(row, 0).setText(n.currentText())
            self.grid.item(row, 2).setText(z.currentText())
            if hit is not None:
                self.grid.item(row, 1).setText(hit[2] or self.grid.item(row, 1).text())
                if not _num(self.grid.item(row, 6).text()):
                    self.grid.item(row, 6).setText(str(hit[3]))
            self.grid.blockSignals(False)
            self._recalc()
        name.currentIndexChanged.connect(stone_changed)
        size.currentTextChanged.connect(size_changed)
        self.grid.setCellWidget(r, 0, name)
        self.grid.setCellWidget(r, 2, size)
        self.grid.setColumnWidth(0, max(self.grid.columnWidth(0), 170))

    def _remove(self) -> None:
        r = self.grid.currentRow()
        if r >= 0:
            self.grid.removeRow(r)
            self._recalc()

    def stones(self) -> list[dict]:
        out = []
        for r in range(self.grid.rowCount()):
            st = {k: self.grid.item(r, c).text().strip() for c, (k, _h) in enumerate(STONE_COLS)}
            if self.full:
                st["label"] = self.grid.cellWidget(r, 0).currentText().strip()
                st["size"] = self.grid.cellWidget(r, 2).currentText().strip()
                hit = next((x for x in self._sizes().get(st["label"], [])
                            if x[0].lower() == st["size"].lower()), None)
                if hit is not None:
                    st["stone_sku_id"] = hit[1]
            st["pcs"] = int(st["pcs"]) if st["pcs"].isdigit() else 0
            st["weight"] = str(_num(st["weight"]) or 0)
            st["price"] = str(_num(st["price"]) or 0)
            st["unit"] = st["unit"] or "ct"
            if st["label"] or st["pcs"] or _num(st["weight"]):
                out.append(st)
        return out

    def _recalc(self, *_a) -> None:
        self.grid.blockSignals(True)
        total = D(0)
        for r in range(self.grid.rowCount()):
            st = {k: self.grid.item(r, c).text() for c, (k, _h) in enumerate(STONE_COLS)}
            st["pcs"] = int(st["pcs"]) if st["pcs"].strip().isdigit() else 0
            amt = S.stone_amount(st)
            total += amt
            self.grid.item(r, len(STONE_COLS)).setText(f"{amt:,.2f}")
        self.grid.blockSignals(False)
        self.total.setText(f"<b>Stone amount {total:,.2f}</b>")


class NewPieceDialog(QDialog):
    """Ready Items purchase / Opening Stock: one piece coming in. It gets its
    Stock No (barcode) when the voucher is saved."""

    def __init__(self, parent=None, piece: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Piece")
        self.setMinimumWidth(560)
        self.stones: list[dict] = list((piece or {}).get("stones") or [])
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.sku = QComboBox()
        self.sku.setEditable(True)
        self.loc = QComboBox()
        self.metal = QComboBox()
        with SessionLocal() as s:
            for p in s.scalars(select(ProductSku).order_by(ProductSku.sku_code)):
                self.sku.addItem(p.sku_code, p.id)
            for l in s.scalars(select(Location).order_by(Location.name)):
                self.loc.addItem(l.name, l.id)
            for m in s.scalars(select(Metal).order_by(Metal.name)):
                self.metal.addItem(m.name, m.id)
        i = self.loc.findText("Primary")
        if i >= 0:
            self.loc.setCurrentIndex(i)
        self.c_ref, self.colour, self.size = QLineEdit(), QLineEdit("Y"), QLineEdit()
        self.cert, self.huid = QLineEdit(), QLineEdit()
        self.pcs = QSpinBox()
        self.pcs.setRange(1, 999)

        def dbl(dec: int, top: float = 1e9) -> QDoubleSpinBox:
            w = QDoubleSpinBox()
            w.setDecimals(dec)
            w.setRange(0, top)
            w.setGroupSeparatorShown(True)
            return w
        self.title, self.loss = dbl(3, 1000), dbl(2, 100)
        self.gross, self.net = dbl(3), dbl(3)
        self.rate, self.lab_rate, self.setting, self.other = dbl(2), dbl(2), dbl(2), dbl(2)
        self.price = dbl(2)
        for label, w in (("SKU", self.sku), ("C Ref", self.c_ref), ("Location", self.loc),
                         ("Metal", self.metal), ("Tunch / Title", self.title),
                         ("Loss %", self.loss), ("Colour", self.colour), ("Size", self.size),
                         ("Pcs", self.pcs), ("Gross Wt", self.gross), ("Net Wt", self.net),
                         ("Metal Rate", self.rate), ("Labour Rate (per g)", self.lab_rate),
                         ("Setting Amount", self.setting), ("Other Amount", self.other),
                         ("Cert No", self.cert), ("HUID", self.huid),
                         ("Tag / sale price", self.price)):
            form.addRow(label, w)
        lay.addLayout(form)
        row = QHBoxLayout()
        b = QPushButton("Stones…")
        b.clicked.connect(self._stones)
        row.addWidget(b)
        self.st_label = QLabel("")
        row.addWidget(self.st_label, 1)
        lay.addLayout(row)
        self.amounts = QLabel("")
        self.amounts.setObjectName("Muted")
        lay.addWidget(self.amounts)
        for w in (self.net, self.rate, self.lab_rate, self.setting, self.other, self.title):
            w.valueChanged.connect(lambda _v: self._recalc())
        # N-Wt follows G-Wt less the stones (ct x 0.2 g) - 19 Oct meeting, item 3.
        self.gross.valueChanged.connect(lambda _v: self._net_from_stones())
        self.metal.currentIndexChanged.connect(lambda _i: self._metal_changed())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._metal_changed()

    def _metal_changed(self) -> None:
        from diagold.services import mfg_pricing, production
        with SessionLocal() as s:
            m = s.get(Metal, self.metal.currentData())
            self.title.setValue(float(mfg_pricing.title_of(m)))
            self.rate.setValue(float(production.metal_price(s, self.metal.currentData())))
        self._recalc()

    def _stones(self) -> None:
        dlg = StoneBreakupDialog(self.stones, self, full=True)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.stones = dlg.stones()
            self._net_from_stones()
        self._recalc()

    def _net_from_stones(self) -> None:
        gross = D(str(round(self.gross.value(), 3)))
        self.net.setValue(float(S.net_from_gross(gross, self.stones)))

    def values(self) -> dict[str, Any]:
        net = D(str(round(self.net.value(), 3)))
        rate = D(str(round(self.rate.value(), 2)))
        st_amt = sum((S.stone_amount(s) for s in self.stones), D(0))
        from diagold.services import costing
        labour = costing.labour_amount(D(str(self.lab_rate.value())), net_weight=net)
        metal_amount = (net * rate).quantize(D("0.01"))
        setting, other = D(str(self.setting.value())), D(str(self.other.value()))
        total = metal_amount + st_amt + setting + labour + other
        title = D(str(self.title.value()))
        return {
            "product_sku_id": self.sku.currentData(), "sku": self.sku.currentText(),
            "c_ref": self.c_ref.text().strip(), "location_id": self.loc.currentData(),
            "location": self.loc.currentText(), "metal_id": self.metal.currentData(),
            "metal": self.metal.currentText(), "title": title,
            "loss_pct": D(str(self.loss.value())), "colour": self.colour.text().strip(),
            "size": self.size.text().strip(), "pcs": self.pcs.value(),
            "gross_wt": D(str(round(self.gross.value(), 3))), "net_wt": net,
            "fine_wt": (net * title / 1000).quantize(D("0.001")), "metal_rate": rate,
            "metal_amount": metal_amount, "st_wt": sum((D(s["weight"]) for s in self.stones), D(0)),
            "stone_amount": st_amt, "setting_amount": setting,
            "labour_rate": D(str(self.lab_rate.value())), "labour": labour,
            "other_amount": other, "total": total, "stones": self.stones,
            "price": D(str(self.price.value())) or total, "cert_no": self.cert.text().strip(),
            "huid": self.huid.text().strip(), "stock_no": "new",
            "photo": self._photo(),
        }

    def _photo(self) -> str:
        with SessionLocal() as s:
            p = s.get(ProductSku, self.sku.currentData()) if self.sku.currentData() else None
            return p.photo if p else ""

    def _recalc(self) -> None:
        v = self.values()
        self.st_label.setText(f"{len(self.stones)} stone line(s) · {v['st_wt']} ct · "
                              f"{v['stone_amount']:,.2f}")
        self.amounts.setText(f"Metal {v['metal_amount']:,.2f} + Stones {v['stone_amount']:,.2f} "
                             f"+ Setting {v['setting_amount']:,.2f} + Labour {v['labour']:,.2f} "
                             f"+ Other {v['other_amount']:,.2f} = <b>{v['total']:,.2f}</b>")

    def _ok(self) -> None:
        if not self.sku.currentData():
            _warn(self, "Add Piece", "Choose the SKU.")
            return
        if self.gross.value() <= 0:
            _warn(self, "Add Piece", "Enter the gross weight.")
            return
        self.accept()


# --------------------------------------------------------------------------
# The voucher screen
# --------------------------------------------------------------------------
LINE_COLS: list[tuple[str, str, bool]] = [
    ("location", "Location", False), ("stock_no", "BarCode", False), ("job_no", "Job", False),
    ("sku", "SKU", False), ("c_ref", "Cref", False), ("metal", "Metal", False),
    ("title", "Fine", False), ("loss_pct", "Loss", False), ("colour", "Color", False),
    ("size", "Size", False), ("pcs", "Pcs", False), ("old_wt", "Old Wt", True),
    ("gross_wt", "G-Wt", False), ("net_wt", "N-Wt", False), ("fine_wt", "FineWt", False),
    ("fine_loss", "Fine With\nLoss", False),
    ("metal_rate", "Metal\nRate", True), ("metal_amount", "Metal\nAmount", False),
    ("st_wt", "St Wt", False), ("stone_amount", "Stone\nAmount", False),
    ("setting_amount", "Setting\nAmount", True), ("labour_rate", "Labour\nRate", True),
    ("labour", "Labour", False), ("other_amount", "Other\nAmt", True),
    ("total", "Total", False),
]
# Ready Items purchase / Opening, column for column as the legacy Ready Stock
# Purchase (19 Nov video): metal, stones, labour, Total Amount, then Margin %,
# Margin Amount, Price Per, Total Value, Tag %, Tag Price.
PURCHASE_COLS: list[tuple[str, str, bool]] = [
    ("sno", "Sno", False),
    ("location", "Location", True), ("job_no", "Job No", False), ("sku", "SKU", True),
    ("c_ref", "C Ref", True), ("metal", "Metal", True), ("title", "Title", False),
    ("loss_pct", "Loss%", True), ("colour", "Color", True), ("size", "Size", True),
    ("pcs", "Pcs", True), ("gross_wt", "Gross Wt", True), ("net_wt", "Net Wt", True),
    ("st_wt", "St Wt", False), ("fine_wt", "FineWt", False),
    ("fine_loss", "Fine With\nLoss", False), ("metal_rate", "Metal\nRate", True),
    ("metal_amount", "Metal\nAmount", False), ("stone_amount", "Stone\nAmount", False),
    ("setting_amount", "Setting\nAmount", True), ("other_amount", "Ex Metal\nAmt", True),
    ("st_handling", "St.Handling\nTotal", True), ("finding_labour", "Finding\nLabour", False),
    ("labour_rate", "Labour\nPrice", True), ("labour_per", "Unit", True),
    ("labour", "Labour", False), ("total", "Total\nAmount", False),
    ("margin_pct", "Margin %", True), ("margin_amount", "Margin\nAmount", False),
    ("price_per", "Price Per", False), ("total_value", "Total\nValue", False),
    ("tag_pct", "Tag %", True), ("tag_price", "Tag Price", True),
    ("stamp", "Stamp", True), ("snap", "Snap", False),
]
# Typed as text on the purchase grid (24 Nov: the line is typed in the grid as
# the legacy one - Location / SKU / Metal / Unit from their lists).
_TEXT_KEYS = {"location", "sku", "c_ref", "metal", "colour", "size", "labour_per", "stamp"}
_UNIT_SHOW = {"gm": "NetWt", "gw": "GrossWt", "pcs": "Pcs"}
_DECIMALS = {"title": 0, "loss_pct": 2, "old_wt": 3, "gross_wt": 3, "net_wt": 3, "fine_wt": 3,
             "fine_loss": 3,
             "st_wt": 3, "metal_rate": 2, "metal_amount": 2, "stone_amount": 2,
             "setting_amount": 2, "labour_rate": 2, "labour": 2, "other_amount": 2, "total": 2,
             "margin_pct": 2, "margin_amount": 2, "price_per": 2, "total_value": 2,
             "tag_pct": 2, "tag_price": 0, "st_handling": 2, "finding_labour": 2}


def _unit_code(text: str) -> str:
    t = (text or "").strip().lower()
    if t.startswith("p"):
        return "pcs"
    if t.startswith("g") and t not in ("gm", "g"):
        return "gw"
    return "gm"


class _ListDelegate(QStyledItemDelegate):
    """A grid cell typed from a list (Location, SKU, Metal, Unit): an editable
    drop-down that finds what is typed anywhere in the names."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self._items = items             # a list, or a function giving one

    def createEditor(self, parent, option, index):  # noqa: N802 - Qt name
        from PySide6.QtWidgets import QCompleter
        cb = QComboBox(parent)
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        items = self._items() if callable(self._items) else self._items
        cb.addItems(list(items))
        comp = QCompleter(list(items), cb)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        cb.setCompleter(comp)
        return cb

    def setEditorData(self, editor, index):  # noqa: N802
        editor.setCurrentText(str(index.data() or ""))
        editor.lineEdit().selectAll()

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, editor.currentText().strip())


class PurchaseBreakupDialog(QDialog):
    """The legacy breakup pop-up of a purchased piece (24 Nov video): headed
    "SKU : ER-1730" - Stone (Location, SSKU from the List of Stone SKU, Size,
    Pcs, Weight, Price Per, Amount), Finding (Finding, Metal, Fineness,
    Color, Pcs, Weight, Lab Price Per, Lab Value), Labour (Labour Type,
    Price On, rate, Total) and Metal (Metal, Col, Purity, Weight, Price,
    Amount). OK carries the stones, Finding Labour, Labour and Ex Metal Amt
    back to the line."""

    FIND_COLS = ("Finding", "Metal", "Fineness", "Color", "Pcs", "Weight", "Lab Price Per",
                 "Lab Value")
    METAL_COLS = ("Metal", "Col", "Purity", "Weight", "Price", "Amount")

    def __init__(self, ln: dict, parent=None):
        super().__init__(parent)
        self.ln = ln
        self.setWindowTitle(f"SKU : {ln.get('sku') or ''}")
        self.setMinimumSize(980, 680)
        bk = dict(ln.get("breakup") or {})
        with SessionLocal() as s:
            from diagold.services import mfg_pricing, production
            self._metals = {m.name.upper(): (m.name, float(mfg_pricing.title_of(m)),
                                             m.colour or "",
                                             float(production.metal_price(s, m.id) or 0))
                            for m in s.scalars(select(Metal).order_by(Metal.name))}
        lay = QVBoxLayout(self)
        head = QLabel(f"  SKU : {ln.get('sku') or ''}")
        head.setStyleSheet("background:#4a4a12; color:white; font-weight:700; padding:4px;")
        lay.addWidget(head)

        def cap(t: str) -> QLabel:
            lab = QLabel(t)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setStyleSheet("font-weight:700;")
            return lab
        # -- Stone: the Stone Breakup grid, its own OK / Cancel hidden --------
        lay.addWidget(cap("Stone"))
        self.stone = StoneBreakupDialog(ln.get("stones") or [], self, full=True)
        self.stone.setWindowFlags(Qt.WindowType.Widget)
        self.stone.setMinimumSize(0, 220)
        self.stone.layout().setContentsMargins(0, 0, 0, 0)
        for bb in self.stone.findChildren(QDialogButtonBox):
            for b in bb.buttons():
                if bb.buttonRole(b) in (QDialogButtonBox.ButtonRole.AcceptRole,
                                        QDialogButtonBox.ButtonRole.RejectRole):
                    b.hide()
        self.stone.grid.itemChanged.connect(lambda _i: self._labour_total())
        lay.addWidget(self.stone, 3)
        # -- Finding and Labour side by side --------------------------------
        mid = QHBoxLayout()
        fbox = QVBoxLayout()
        fbox.addWidget(cap("Finding"))
        self.find = self._table(self.FIND_COLS, bk.get("findings") or [],
                                ("finding", "metal", "fineness", "colour", "pcs", "weight",
                                 "price", "value"))
        self.find.itemChanged.connect(lambda it: self._row_calc(self.find, it, finding=True))
        fbox.addWidget(self.find, 1)
        fbox.addLayout(self._row_buttons(self.find))
        mid.addLayout(fbox, 3)
        lbox = QVBoxLayout()
        lbox.addWidget(cap("Labour"))
        lform = QFormLayout()
        self.lab_type = QLineEdit(bk.get("labour_type") or "STD")
        self.lab_rate = QDoubleSpinBox()
        self.lab_rate.setDecimals(2)
        self.lab_rate.setRange(0, 1e9)
        self.lab_rate.setValue(float(ln.get("labour_rate") or 0))
        self.lab_on = QComboBox()
        self.lab_on.addItems(["NetWt", "GrossWt", "Pcs"])
        self.lab_on.setCurrentText(_UNIT_SHOW.get(ln.get("labour_per") or "gm", "NetWt"))
        self.lab_total = QLabel()
        self.lab_total.setStyleSheet("font-weight:700;")
        for label, w in (("Labour Type", self.lab_type), ("Price", self.lab_rate),
                         ("Price On", self.lab_on), ("Total", self.lab_total)):
            lform.addRow(label, w)
        self.lab_rate.valueChanged.connect(lambda _v: self._labour_total())
        self.lab_on.currentIndexChanged.connect(lambda _i: self._labour_total())
        lbox.addLayout(lform)
        lbox.addStretch(1)
        mid.addLayout(lbox, 2)
        lay.addLayout(mid, 2)
        # -- Metal ------------------------------------------------------------
        lay.addWidget(cap("Metal"))
        self.metal = self._table(self.METAL_COLS, bk.get("metals") or [],
                                 ("metal", "colour", "purity", "weight", "price", "amount"))
        self.metal.itemChanged.connect(lambda it: self._row_calc(self.metal, it, finding=False))
        lay.addWidget(self.metal, 2)
        lay.addLayout(self._row_buttons(self.metal))
        self.sums = QLabel()
        self.sums.setStyleSheet("font-weight:700;")
        lay.addWidget(self.sums)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for t in (self.find, self.metal):
            if t.rowCount() == 0:
                self._add_row(t)
        self._labour_total()

    # -- small grids --------------------------------------------------------
    def _table(self, heads, rows, keys) -> QTableWidget:
        t = QTableWidget(0, len(heads))
        t.setHorizontalHeaderLabels(list(heads))
        t.verticalHeader().setVisible(False)
        t.setProperty("_keys", keys)
        auto_fit(t)
        for row in rows:
            self._add_row(t, [row.get(k, "") for k in keys])
        return t

    def _row_buttons(self, t: QTableWidget) -> QHBoxLayout:
        h = QHBoxLayout()
        for label, fn in (("Add Row", lambda: self._add_row(t)),
                          ("Remove Row", lambda: self._drop_row(t))):
            b = QPushButton(label)
            b.setAutoDefault(False)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch(1)
        return h

    def _add_row(self, t: QTableWidget, values=None) -> None:
        t.blockSignals(True)
        r = t.rowCount()
        t.insertRow(r)
        for c in range(t.columnCount()):
            v = (values or [""] * t.columnCount())[c]
            it = QTableWidgetItem("" if v in (None, 0, "0") else str(v))
            if c == t.columnCount() - 1:          # the amount is worked out
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                it.setBackground(TINT_RECEIVE)
            t.setItem(r, c, it)
        t.blockSignals(False)

    def _drop_row(self, t: QTableWidget) -> None:
        if t.currentRow() >= 0:
            t.removeRow(t.currentRow())
            self._labour_total()

    def _row_calc(self, t: QTableWidget, it: QTableWidgetItem, *, finding: bool) -> None:
        r = it.row()
        t.blockSignals(True)
        if it.column() == 1 and finding or it.column() == 0 and not finding:
            # A metal typed: its purity, colour and the day's rate fill in.
            hit = self._metals.get(it.text().strip().upper())
            if hit is not None:
                name, purity, col, rate = hit
                it.setText(name)
                if finding:
                    t.item(r, 2).setText(t.item(r, 2).text() or f"{purity:g}")
                    t.item(r, 3).setText(t.item(r, 3).text() or col)
                else:
                    t.item(r, 1).setText(t.item(r, 1).text() or col)
                    t.item(r, 2).setText(t.item(r, 2).text() or f"{purity:g}")
                    t.item(r, 4).setText(t.item(r, 4).text() or f"{rate:.2f}")
        if finding:     # Lab Value = Weight x Lab Price Per (Pcs x it with no weight)
            wt, pcs, price = (_num(t.item(r, c).text()) or D(0) for c in (5, 4, 6))
            val = (wt or pcs) * price
        else:           # Amount = Weight x Price
            wt, price = (_num(t.item(r, c).text()) or D(0) for c in (3, 4))
            val = wt * price
        t.item(r, t.columnCount() - 1).setText(f"{val:.2f}" if val else "")
        t.blockSignals(False)
        self._labour_total()

    @staticmethod
    def _rows(t: QTableWidget) -> list[dict]:
        keys = t.property("_keys")
        out = []
        for r in range(t.rowCount()):
            row = {k: (t.item(r, c).text().strip() if t.item(r, c) else "")
                   for c, k in enumerate(keys)}
            if any(row.values()):
                out.append(row)
        return out

    def _sum(self, t: QTableWidget) -> Decimal:
        return sum((_num(t.item(r, t.columnCount() - 1).text()) or D(0)
                    for r in range(t.rowCount())), D(0)).quantize(D("0.01"))

    def _net(self) -> Decimal:
        return S.net_from_gross(self.ln.get("gross_wt"), self.stone.stones())

    def _labour_total(self) -> None:
        per = _unit_code(self.lab_on.currentText())
        base = D(str(self.ln.get("gross_wt") or 0)) if per == "gw" else self._net()
        self._labour = S.labour_amount(self.lab_rate.value(), per, base, self.ln.get("pcs"))
        self.lab_total.setText(f"{self._labour:,.2f}")
        st = sum((S.stone_amount(x) for x in self.stone.stones()), D(0))
        self.sums.setText(f"Stone {st:,.2f}  ·  Finding Labour {self._sum(self.find):,.2f}  ·  "
                          f"Labour {self._labour:,.2f}  ·  Metal {self._sum(self.metal):,.2f}  ·  "
                          f"Net Wt {self._net():.3f}")

    def apply(self, ln: dict) -> None:
        """Carry the pop-up back to the purchase line."""
        ln["stones"] = self.stone.stones()
        ln["st_wt"] = sum((D(x["weight"]) for x in ln["stones"]), D(0))
        ln["net_wt"] = self._net()
        ln["finding_labour"] = self._sum(self.find)
        ln["other_amount"] = self._sum(self.metal)
        ln["labour_rate"] = D(str(round(self.lab_rate.value(), 2)))
        ln["labour_per"] = _unit_code(self.lab_on.currentText())
        ln["breakup"] = {"findings": self._rows(self.find), "metals": self._rows(self.metal),
                         "labour_type": self.lab_type.text().strip()}


class ReadyVoucherWidget(_Screen):

    def __init__(self, vr_type: str, user=None, parent=None):
        self.vr_type = vr_type
        self.t = S.READY_TYPES[vr_type]
        super().__init__(self.t.title, with_picker=False, parent=parent)
        self.user = user
        self.header.hide()
        self.lines: list[dict] = []
        self._edit_id: int | None = None
        self._last_id: int | None = None
        new = vr_type in S.NEW_PIECES
        self.cols = PURCHASE_COLS if new else LINE_COLS

        # header
        self.vr = QLabel("")
        self.vr.setObjectName("H2")
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.date.dateChanged.connect(lambda _d: self._revalue())
        self.time = QLineEdit(datetime.now().strftime("%H:%M:%S"))
        self.time.setMaximumWidth(80)
        self.account = QComboBox()
        self.account.setEditable(True)
        self.account.setMinimumWidth(220)
        with SessionLocal() as s:
            self.account.addItem("", None)
            for a in s.scalars(select(Account).order_by(Account.name)):
                self.account.addItem(a.name, a.id)
        self.ref = QLineEdit()
        self.ref.setPlaceholderText("Ref")
        self.ref.setMaximumWidth(120)
        # Cl Bal: the party's closing balance (legacy sale header).
        self.cl_bal = QLabel("")
        self.cl_bal.setObjectName("Muted")
        self.account.currentIndexChanged.connect(lambda _i: self._show_balance())
        self.account.editTextChanged.connect(lambda _t: self._show_balance())
        # Prices From Client Chart (5 Oct T-05): the client's price chart
        # prices labour, stones and setting; off = the standard price.
        self.chart_cb = QCheckBox("Prices From Client Chart")
        self.chart_cb.setToolTip("Labour, stone and setting prices from the client's price "
                                 "chart (Tools ▸ Client Wise … Price). Off: standard prices.")
        self.chart_cb.toggled.connect(lambda _on: self._reprice_chart())
        self._chart_for: int | None = None
        self.account.currentIndexChanged.connect(lambda _i: self._client_changed())
        self.account.editTextChanged.connect(lambda _t: self._client_changed())
        self._docs: list[str] = []
        head = [QLabel("Vr No"), self.vr, QLabel("Date"), self.date, self.time]
        if self.t.party != "none":
            head += [QLabel("Supplier" if self.t.party == "supplier" else "Account"),
                     self.account, self.cl_bal]
        head += [self.ref]
        for w in head:
            self.toolbar.addWidget(w)
        self.toolbar.addStretch(1)
        self.photo = QLabel("no photo")
        self.photo.setObjectName("ImageSlot")
        self.photo.setFixedSize(64, 64)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.mousePressEvent = lambda _e: self._enlarge()
        self._photo_path = ""
        self.toolbar.addWidget(self.photo)

        # second header row: sale terms / approval / purchase bill
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.currency = QComboBox()
        self.currency.addItems(["INR", "USD", "AED", "EUR"])
        self.credit = QSpinBox()
        self.credit.setRange(0, 365)
        self.credit.valueChanged.connect(lambda _v: self._due())
        self.due = QLabel("")
        self.due.setObjectName("Muted")
        self.due.setMinimumWidth(110)
        self.salesperson = QLineEdit()
        self.salesperson.setPlaceholderText("Salesperson")
        self.bank = QLineEdit()
        self.bank.setPlaceholderText("Bank Name")
        self.margin_type = QLineEdit()
        self.margin_type.setPlaceholderText("Margin Type")
        self.bill_date = QDateEdit(_qdate(None))
        self.bill_date.setCalendarPopup(True)
        self.bill_date.setDisplayFormat("dd-MM-yyyy")
        self.bill_no = QLineEdit()
        self.bill_no.setPlaceholderText("Bill Number")
        self.bill_acct = QComboBox()
        self.bill_acct.addItem("", None)
        for i in range(1, self.account.count()):
            self.bill_acct.addItem(self.account.itemText(i), self.account.itemData(i))
        self.bill_amt = QLineEdit()
        self.bill_amt.setPlaceholderText("Bill Amt")
        self.bill_amt.setMaximumWidth(110)
        # Cash or Bill on a sale and on its return (5 Oct D2 / T-04): a cash
        # voucher settles at once and never shows as a bill outstanding.
        self.mode = QComboBox()
        self.mode.addItems(["Bill", "Cash"])
        self.mode.currentIndexChanged.connect(lambda _i: self._render())
        from diagold.services import settings as _settings
        if not _settings.opt_on("opt.multi_currency"):
            self.currency.setEnabled(False)        # Allow Multi-Currency off: INR only
        if vr_type in ("rs_sale", "rs_sale_return"):
            for w in (QLabel("Mode"), self.mode, QLabel("Currency"), self.currency,
                      QLabel("Credit Days"), self.credit, self.due, self.salesperson, self.bank):
                row2.addWidget(w)
        elif vr_type == "rs_approval":
            row2.addWidget(self.margin_type)
        elif vr_type in ("rp_purchase", "rp_return"):
            for w in (QLabel("Currency"), self.currency, QLabel("Bill Date"), self.bill_date,
                      self.bill_no, QLabel("Bill Account"), self.bill_acct, self.bill_amt):
                row2.addWidget(w)
        self.for_repair = QCheckBox("For Repair")
        self.for_repair.setToolTip("Taken back to be repaired: the pieces come first on "
                                   "Ready Repair Issue (legacy credit note, 17 Nov).")
        if vr_type == "rs_sale_return":
            row2.addWidget(self.for_repair)
        else:
            self.for_repair.setVisible(False)
        if vr_type in CHART_TYPES:
            row2.addWidget(self.chart_cb)
        else:
            self.chart_cb.setVisible(False)
        row2.addStretch(1)
        self.outer.insertLayout(2, row2)

        # barcode / SKU reader
        rd = QHBoxLayout()
        self.reader = QLineEdit()
        self.reader.setPlaceholderText(
            "Add Piece (new piece coming in)" if new else
            "Read Barcode / SKU here - scan a Stock No or type a SKU, Enter")
        self.reader.returnPressed.connect(self._read)
        self.reader.setEnabled(not new)
        rd.addWidget(self.reader, 1)
        self.outer.insertLayout(3, rd)

        # buttons
        self.button("Add", self.new_voucher)
        self.button("Edit", self.edit_voucher)
        self.button("Save", self.save, primary=True)
        self.button("Delete", self.delete_voucher)
        if new:
            self.button("Add Piece", self.add_piece, secondary=True)
            self.button("SKU Search", self.sku_search, secondary=True)
        elif vr_type in ("rs_approval_return",):
            self.button("Show App", lambda: self._pick("Show App — out on approval"),
                        secondary=True)
        elif vr_type == "rs_sale_return":
            self.button("Sold Pieces", lambda: self._pick("Pieces sold to this account"),
                        secondary=True)
        else:
            self.button("Show Stock", lambda: self._pick("Show Stock", status="in_stock"),
                        secondary=True)
        if vr_type == "rs_sale":
            self.button("From Order", self.from_order, secondary=True)
            self.button("Read Barcode From Approval",
                        lambda: self._pick("Read Barcode From Approval", status="on_approval"),
                        secondary=True)
        self.button("Attach Doc", self.attach_doc, secondary=True)
        if vr_type.startswith("rs_"):
            # The legacy sale actions (2 Oct §4.9).
            self.button("TXT Import", self.txt_import, secondary=True)
            self.button("TXT Export", self.txt_export, secondary=True)
            self.button("Tag Print", self.tag_print, secondary=True)
            self.button("Catalog", self.picture_invoice, secondary=True)
        if vr_type in ("rs_sale", "rs_approval", "rs_repair_issue"):
            # 14 Nov: "price do not update and metal rate or labour" - the day's
            # metal rate, labour rate and client chart read again for every line.
            self.button("Re-price (F6)", self.reprice, secondary=True)
            QShortcut(QKeySequence("F6"), self, activated=self.reprice)
        self.button("Stone Breakup", self.stone_breakup, secondary=True)
        self.button("Remove Line", self.remove_line, secondary=True)
        self.button("Print", self.print_voucher, secondary=True)
        if vr_type == "rs_sale":
            self.button("Excel Invoice", self.excel_invoice, secondary=True)
            # 9 Oct T-07 / T-08: dispatch with tracking, WhatsApp to the customer.
            self.button("Dispatch / Tracking", self.dispatch, secondary=True)
            self.button("Resend WhatsApp", self.resend_whatsapp, secondary=True)
        if vr_type in ("rp_purchase", "rp_opening", "rp_return"):
            # The legacy Ready Stock Purchase actions (2 Oct §4.5).
            self.button("BreakUp Sheet", self.breakup_sheet, secondary=True)
            self.button("Packing List", self.packing_list, secondary=True)
            self.button("Picture Invoice", self.picture_invoice, secondary=True)
            self.button("St. Summ.", self.stone_summary, secondary=True)
            if new:
                self.button("Tag Print", self.tag_print, secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)

        self.grid = _table([h for _k, h, _e in self.cols], ledger=True)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed
                                  | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.grid.itemChanged.connect(self._edited)
        self.grid.itemSelectionChanged.connect(self._line_selected)
        self.grid.cellDoubleClicked.connect(lambda r, c: self.stone_breakup()
                                            if self.cols[c][0] in ("st_wt", "stone_amount")
                                            else None)
        auto_fit(self.grid)
        if new:
            self._inline_lists()
        self.outer.addWidget(self.grid, 1)
        self.narration = QLineEdit()
        self.narration.setPlaceholderText("Narration")
        self.outer.addWidget(self.narration)
        self.totals = QLabel("")
        self.outer.addWidget(self.totals)
        self.accounts = QLabel("")
        self.accounts.setObjectName("Muted")
        self.outer.addWidget(self.accounts)
        self.acc_table: QTableWidget | None = None
        if new:
            self._legacy_layout(row2, rd)
        self.refresh()

    def _legacy_layout(self, row2, rd) -> None:
        """Ready Stock Purchase laid out as the legacy screen (19 Nov video):
        Vr No / Ref no / Currency, Date, Account / Margin Type / Prices From
        Client Chart across the top; the grid; ACCOUNT INFORMATION; Bill Date,
        Bill Number, Bill Account, Bill Amt and Remark; the buttons at the foot."""
        from PySide6.QtWidgets import QGridLayout, QPushButton
        from diagold.ui.flow import FlowLayout
        buttons: dict[str, QPushButton] = {}
        for lay in (self.toolbar, self.secondary):
            for i in reversed(range(lay.count())):
                w = lay.itemAt(i).widget()
                if w is None:
                    continue
                lay.removeWidget(w)
                if isinstance(w, QPushButton):
                    buttons[w.text()] = w
                else:
                    w.setParent(None)
                    w.hide()
        for i in reversed(range(row2.count())):
            w = row2.itemAt(i).widget()
            if w is not None:
                row2.removeWidget(w)
                w.hide()
        self.reader.hide()
        # -- header -------------------------------------------------------
        head = QGridLayout()
        head.setHorizontalSpacing(10)
        head.setVerticalSpacing(6)

        def cap(t: str) -> QLabel:
            lab = QLabel(t)
            lab.setObjectName("Muted")
            return lab
        self.ref.setPlaceholderText("")
        self.ref.setMaximumWidth(220)
        self.margin_type.setPlaceholderText("")
        party = "Supplier" if self.t.party == "supplier" else "Account"
        grid_items = [
            (0, 0, cap("Vr No")), (0, 1, self.vr), (1, 0, cap("Ref no")), (1, 1, self.ref),
            (2, 0, cap("Currency")), (2, 1, self.currency),
            (0, 3, cap("Date")), (0, 4, self.date), (0, 5, self.time),
        ]
        if self.t.party != "none":
            grid_items += [(0, 7, cap(party)), (0, 8, self.account), (0, 9, self.cl_bal),
                           (2, 7, cap("Margin Type")), (2, 8, self.margin_type)]
        if self.vr_type in CHART_TYPES:
            grid_items.append((2, 9, self.chart_cb))
        self.cl_bal.setMinimumWidth(160)
        for r, c, w in grid_items:
            head.addWidget(w, r, c)
            w.show()
        head.setColumnMinimumWidth(2, 30)
        head.setColumnMinimumWidth(6, 30)
        head.setColumnStretch(10, 1)
        head.addWidget(self.photo, 0, 11, 3, 1)
        self.photo.show()
        self.outer.insertLayout(1, head)
        # -- ACCOUNT INFORMATION (Dr Purchase A/c / Cr the supplier) --------
        self.outer.removeWidget(self.accounts)
        self.accounts.hide()
        acap = QLabel("ACCOUNT INFORMATION")
        acap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        acap.setStyleSheet("font-weight: 600; letter-spacing: 2px;")
        self.acc_table = QTableWidget(2, 5)
        self.acc_table.setHorizontalHeaderLabels(["Sno", "Dr/Cr", "Account", "Debit", "Credit"])
        self.acc_table.verticalHeader().setVisible(False)
        self.acc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.acc_table.setFixedHeight(92)
        self.acc_table.horizontalHeader().setStretchLastSection(True)
        for c, wdt in enumerate((40, 50, 320, 140)):
            self.acc_table.setColumnWidth(c, wdt)
        idx = self.outer.indexOf(self.narration)
        self.outer.removeWidget(self.narration)
        self.outer.insertWidget(idx, acap)
        self.outer.insertWidget(idx + 1, self.acc_table)
        # -- Bill Date / Bill Number / Bill Account / Bill Amt, Remark ------
        bill = QGridLayout()
        bill.setHorizontalSpacing(10)
        self.narration.setPlaceholderText("")
        if self.vr_type == "rp_purchase":
            self.bill_no.setPlaceholderText("")
            self.bill_amt.setPlaceholderText("")
            for c, w in enumerate((cap("Bill Date"), self.bill_date, cap("Bill Number"),
                                   self.bill_no, cap("Bill Account"), self.bill_acct,
                                   cap("Bill Amt"), self.bill_amt)):
                bill.addWidget(w, 0, c)
                w.show()
        bill.addWidget(cap("Remark"), 1, 0)
        bill.addWidget(self.narration, 1, 1, 1, 5)
        bill.setColumnStretch(8, 1)
        self.outer.insertLayout(idx + 2, bill)
        # -- the buttons, at the foot, in the legacy order -------------------
        foot = FlowLayout(spacing=6)
        # The line is typed in the grid (24 Nov), so no Add Piece form.
        ap = buttons.pop("Add Piece", None)
        if ap is not None:
            ap.hide()
        order = ["Add", "Edit", "Save", "Delete", "Stone Breakup", "Remove Line",
                 "BreakUp Sheet", "Tag Print", "Print", "Packing List", "Picture Invoice",
                 "SKU Search", "St. Summ.", "Attach Doc"]
        names = {"Picture Invoice": "Catalog / Picture Invoice"}
        for label in order + [k for k in buttons if k not in order and k != "Exit"] + ["Exit"]:
            b = buttons.pop(label, None)
            if b is not None:
                b.setText(names.get(label, label))
                foot.addWidget(b)
                b.show()
        self.outer.addLayout(foot)
        self.account.currentIndexChanged.connect(lambda _i: self._render())

    # -- header ---------------------------------------------------------
    def refresh(self) -> None:
        with SessionLocal() as s:
            if self._edit_id is not None:
                v = s.get(ReadyVoucher, self._edit_id)
                self.vr.setText(f"{v.vr_no} (editing)" if v else "")
            else:
                self.vr.setText(str(S.next_vr_no(s, self.vr_type)))
        self._render()
        self._due()
        self._show_balance()

    def _due(self) -> None:
        if self.credit.value():
            d = _pydate(self.date) + timedelta(days=self.credit.value())
            self.due.setText(f"due {d:%d-%m-%Y}")
        else:
            self.due.setText("")

    def _show_balance(self) -> None:
        aid = self._account_id()
        if not aid:
            self.cl_bal.setText("")
            return
        with SessionLocal() as s:
            bal, side = S.closing_balance(s, aid)
        self.cl_bal.setText(f"Cl Bal {bal:,.2f} {side}")

    def attach_doc(self) -> None:
        from diagold.ui.attachments import AttachDocDialog
        vid = self._edit_id
        with SessionLocal() as s:
            vr = s.get(ReadyVoucher, vid).vr_no if vid else None
        AttachDocDialog(self.vr_type, vr, f"{self.t.title} Vr {vr}" if vr else "new voucher",
                        user=self.user, pending=self._docs, parent=self).exec()

    def txt_import(self) -> None:
        """TXT Import (Barcode / SKU): a text file of Stock Nos (one or many per
        line) - each piece that can go on this voucher is added."""
        if self._editing_blocked():
            return
        import re
        path, _ = QFileDialog.getOpenFileName(self, "TXT Import", "", "Text (*.txt *.csv);;All (*)")
        if not path:
            return
        nos = re.findall(r"\d+", open(path, encoding="utf-8", errors="ignore").read())
        added, bad = [], []
        with SessionLocal() as s:
            for n in nos:
                try:
                    item = S.find_item(s, n)
                    S.check_piece(s, self.vr_type, item, self._account_id())
                    added.append(S.describe(s, item))
                except ProductionError as exc:
                    bad.append(str(exc))
        self._add_infos(added)
        _info(self, "TXT Import", f"{len(added)} piece(s) added."
              + (("\nSkipped:\n" + "\n".join(bad[:20])) if bad else ""))

    def txt_export(self) -> None:
        """TXT Export: the barcodes and SKUs on the voucher, one per line."""
        if not self.lines:
            _info(self, "TXT Export", "No pieces on the voucher.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "TXT Export", f"{self.vr_type}.txt",
                                              "Text (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            for l in self.lines:
                fh.write(f"{l.get('stock_no', '')}\t{l.get('sku', '')}\n")
        _info(self, "TXT Export", f"Saved {path}")

    def _account_id(self) -> int | None:
        i = self.account.findText(self.account.currentText())
        return self.account.itemData(i) if i >= 0 else None

    # -- adding pieces -----------------------------------------------------
    def _have(self) -> set[int]:
        return {l["stock_item_id"] for l in self.lines if l.get("stock_item_id")}

    def _chart(self, s) -> Any:
        if self.vr_type not in CHART_TYPES or not self.chart_cb.isChecked():
            return None
        return PC.chart_for(s, self._account_id())

    def _client_changed(self) -> None:
        """A new client: tick Prices From Client Chart when they are on a
        chart and the option "Client wise price chart applicable" is on."""
        if self.vr_type not in CHART_TYPES or self._edit_id is not None:
            return
        aid = self._account_id()
        if aid == self._chart_for:
            return
        self._chart_for = aid
        with SessionLocal() as s:
            chart = PC.chart_for(s, aid)
            on = chart is not None and PC.applicable(s)
            self.chart_cb.setText(f"Prices From Client Chart ({chart.name})" if chart
                                  else "Prices From Client Chart")
        self.chart_cb.blockSignals(True)
        self.chart_cb.setChecked(on)
        self.chart_cb.blockSignals(False)
        self._reprice_chart()

    def _reprice_chart(self) -> None:
        """Re-price the pieces on the voucher: chart prices when ticked, the
        standard prices when not. The metal rate typed stays."""
        if self._edit_id is not None or self.vr_type in S.RETURN_OF:
            return                  # a return keeps the values it went out at (17 Nov T-05)
        if self.chart_cb.isChecked() and self._account_id():
            with SessionLocal() as s:
                missing = self._chart(s) is None
            if missing and not self._choose_chart():
                self.chart_cb.blockSignals(True)
                self.chart_cb.setChecked(False)
                self.chart_cb.blockSignals(False)
                return
        if not self.lines:
            return
        with SessionLocal() as s:
            chart = self._chart(s)
            for i, ln in enumerate(self.lines):
                item = s.get(StockItem, ln.get("stock_item_id")) if ln.get("stock_item_id") \
                    else None
                if item is None:
                    continue
                info = S.describe(s, item)
                if chart is not None:
                    info = PC.apply(s, chart, info)
                v = S.value(info, _pydate(self.date), s, metal_rate=ln.get("metal_rate"))
                self.lines[i] = {**ln, **info, **v}
        self._render()

    def _choose_chart(self) -> bool:
        """Prices From Client Chart ticked for a client on no chart (23 Nov:
        the sale 'did not take the chart price'): pick the chart here - it is
        saved on the client's Account master - instead of a dead end."""
        from PySide6.QtWidgets import QInputDialog
        from diagold.db.models import PriceChart
        with SessionLocal() as s:
            charts = [(c.name, c.id) for c in s.scalars(select(PriceChart)
                                                         .order_by(PriceChart.name))]
        who = self.account.currentText()
        if not charts:
            _info(self, "Prices From Client Chart",
                  "No price chart is set up yet (Tools ▸ Client Wise Price Chart).")
            return False
        name, ok = QInputDialog.getItem(
            self, "Prices From Client Chart",
            f"{who} is not on a price chart yet.\nPut them on this chart (saved on the "
            "Account master) and price from it:", [n for n, _i in charts], 0, False)
        if not ok or not name:
            return False
        with SessionLocal() as s:
            chart = PC.put_on_chart(s, self._account_id(), dict(charts)[name])
            s.commit()
            self.chart_cb.setText(f"Prices From Client Chart ({chart.name})")
        self._chart_for = self._account_id()
        return True

    def reprice(self) -> None:
        """Every piece on the voucher at the date's Daily Metal Rate, its labour
        rate and the client's chart (when ticked) - rates typed are replaced."""
        if not self.lines:
            return
        with SessionLocal() as s:
            chart = self._chart(s)
            for i, ln in enumerate(self.lines):
                item = s.get(StockItem, ln.get("stock_item_id")) if ln.get("stock_item_id") \
                    else None
                if item is None:
                    continue
                info = S.describe(s, item)
                if chart is not None:
                    info = PC.apply(s, chart, info)
                self.lines[i] = {**ln, **info, **S.return_value(
                    s, self.vr_type, info, _pydate(self.date), account_id=self._account_id())}
        self._render()

    def _add_infos(self, infos: list[dict], order_line_id: int | None = None) -> None:
        if self._editing_blocked():
            return
        with SessionLocal() as s:
            chart = self._chart(s)
            for info in infos:
                if info["stock_item_id"] in self._have():
                    continue
                if chart is not None:
                    info = PC.apply(s, chart, info)
                v = S.return_value(s, self.vr_type, info, _pydate(self.date),
                                   account_id=self._account_id())
                self.lines.append({**info, **v, "old_wt": D(0),
                                   "order_line_id": order_line_id or info.get("order_line_id")})
        self._render()

    def _read(self) -> None:
        text = self.reader.text().strip()
        if not text:
            return
        self.reader.clear()
        with SessionLocal() as s:
            if text.isdigit():
                try:
                    item = S.find_item(s, text)
                    S.check_piece(s, self.vr_type, item, self._account_id())
                    info = S.describe(s, item)
                except ProductionError as exc:
                    _warn(self, "Read Barcode", str(exc))
                    return
                self._add_infos([info])
                return
            rows = S.available(s, self.vr_type, self._account_id(), sku_text=text)
        if not rows:
            _warn(self, "Read SKU", f"Item not found: no piece of {text} can go on this voucher.")
            return
        self._pick_from(rows, f"SKU {text}")

    def _pick(self, title: str, status: str | None = None) -> None:
        # Pieces with or sold to a party: that party has to be chosen first.
        needs_party = self.vr_type in ("rs_sale_return", "rs_approval_return") \
            or status == "on_approval"
        if needs_party and not self._account_id():
            _info(self, title, "Choose the account first.")
            return
        with SessionLocal() as s:
            rows = S.available(s, self.vr_type, self._account_id())
        if status:
            rows = [r for r in rows if r["status"] == status]
        self._pick_from(rows, title)

    def _pick_from(self, rows: list[dict], title: str) -> None:
        have = self._have()
        rows = [r for r in rows if r["stock_item_id"] not in have]
        dlg = PiecePicker(rows, title, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._add_infos(dlg.picked())

    def from_order(self) -> None:
        if self._editing_blocked():
            return
        if not self._account_id():
            _info(self, "From Order", "Choose the customer first.")
            return
        on_inv: dict[int, int] = {}
        for l in self.lines:
            if l.get("order_line_id"):
                on_inv[l["order_line_id"]] = on_inv.get(l["order_line_id"], 0) + 1
        with SessionLocal() as s:
            rows = S.pending_orders(s, self._account_id(), on_inv)
        dlg = PendingOrdersDialog(rows, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        short = []
        takes = dlg.takes()
        names = {r["order_line_id"]: f"Ord {r['ord_no']} {r['sku']}" for r in rows}
        with SessionLocal() as s:
            got = S.pieces_for_orders(s, takes, exclude=self._have())
            for ol_id, items in got.items():
                if len(items) < takes[ol_id]:
                    short.append(f"{names.get(ol_id, ol_id)}: {takes[ol_id]} asked, "
                                 f"{len(items)} in stock")
                self._add_infos([S.describe(s, i) for i in items], order_line_id=ol_id)
        if short:
            _info(self, "From Order", "Not enough in stock:\n" + "\n".join(short))

    def add_piece(self) -> None:
        if self._editing_blocked():
            return
        dlg = NewPieceDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ln = dlg.values()
            if self.lines:          # the Margin % / Tag % of the line above carry on
                for k in ("margin_pct", "tag_pct"):
                    ln.setdefault(k, self.lines[-1].get(k))
            self._margin(ln)
            self.lines.append(ln)
            self._render()

    # -- grid -------------------------------------------------------------
    def _render(self) -> None:
        self.grid.blockSignals(True)
        self.grid.setRowCount(0)
        total = D(0)
        inline = self.vr_type in S.NEW_PIECES
        rows = self.lines + ([{"location": self._default_loc()[1], "_blank": True}]
                             if inline else [])
        for i, ln in enumerate(rows):
            r = self.grid.rowCount()
            self.grid.insertRow(r)
            # Fine With Loss = FineWt grossed up by the Loss % (as on the MFG transfer).
            fine, loss = ln.get("fine_wt"), ln.get("loss_pct")
            ln["fine_loss"] = ((D(str(fine)) * (1 + D(str(loss or 0)) / 100)).quantize(D("0.001"))
                               if fine not in (None, "") else None)
            for c, (k, _h, editable) in enumerate(self.cols):
                v = ln.get(k)
                if k == "sno":
                    v = "" if ln.get("_blank") else i + 1
                elif k == "labour_per" and inline and not ln.get("_blank"):
                    v = _UNIT_SHOW.get(v or "gm", v)
                if k in _DECIMALS and v not in (None, ""):
                    v = f"{D(str(v)):,.{_DECIMALS[k]}f}"
                it = _item(v if v is not None else "", TINT_RECEIVE if editable else None,
                           right=k in _DECIMALS or k in ("pcs", "stock_no", "job_no"))
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                if editable:
                    flags |= Qt.ItemFlag.ItemIsEditable
                it.setFlags(flags)
                self.grid.setItem(r, c, it)
            if ln.get("_blank"):
                continue
            # A purchase is booked at its Total Value (Total Amount + Margin).
            total += D(str((ln.get("total_value") if self.vr_type in S.NEW_PIECES else None)
                           or ln.get("total") or 0))
        self.grid.blockSignals(False)
        n = len(self.lines)
        pcs = sum(int(l.get("pcs") or 0) for l in self.lines)
        g = sum((D(str(l.get("gross_wt") or 0)) for l in self.lines), D(0))
        nw = sum((D(str(l.get("net_wt") or 0)) for l in self.lines), D(0))
        self.totals.setText(f"<b>{n} line(s) · {pcs} pcs · Gross {g:,.3f} · Net {nw:,.3f} · "
                            f"Total {total:,.2f}</b>" if n else "No pieces yet.")
        self._account_info(total)

    def _account_info(self, total: Decimal) -> None:
        """Account Information block (TR5): what the voucher will post."""
        who = self.account.currentText() or "the account"
        cash = self.mode.currentText() == "Cash"
        lines = {
            "rs_sale": f"Dr {who} {total:,.2f}   ·   Cr {S.SALES_LEDGER} {total:,.2f}"
                       + (f"   ·   Dr Cash {total:,.2f}   ·   Cr {who} {total:,.2f} (cash, settled)"
                          if cash else ""),
            "rs_sale_return": f"Dr {S.SALES_RETURN_LEDGER} {total:,.2f}   ·   Cr {who} {total:,.2f}"
                              + (f"   ·   Dr {who} {total:,.2f}   ·   Cr Cash {total:,.2f} "
                                 "(cash, settled)" if cash else ""),
            "rp_purchase": f"Dr {S.PURCHASE_LEDGER} {total:,.2f}   ·   Cr {who} {total:,.2f}",
            "rp_return": f"Dr {who} {total:,.2f}   ·   Cr {S.PURCHASE_RETURN_LEDGER} {total:,.2f}",
        }
        text = lines.get(self.vr_type, "No accounting - the pieces only change hands.")
        self.accounts.setText(f"Account Information: {text}")
        if self.acc_table is not None:
            who = self.account.currentText() or ""
            dr = S.PURCHASE_LEDGER if self.vr_type == "rp_purchase" else "Opening Stock"
            rows = [("1", "Dr", dr, f"{total:,.2f}", ""), ("", "Cr", who, "", f"{total:,.2f}")]
            if self.vr_type != "rp_purchase":
                rows = [("", "", "No accounting - opening stock only.", "", ""),
                        ("", "", "", "", "")]
            for r, row in enumerate(rows):
                for c, v in enumerate(row):
                    self.acc_table.setItem(r, c, QTableWidgetItem(v))

    def _edited(self, it: QTableWidgetItem) -> None:
        r, c = it.row(), it.column()
        k = self.cols[c][0]
        if self.vr_type in S.NEW_PIECES:
            self._edited_inline(r, c, k, it.text().strip())
            return
        ln = self.lines[r]
        val = _num(it.text())
        ln[k] = val if val is not None else D(0)
        if k == "gross_wt":
            # N-Wt = G-Wt less the stones in the piece (19 Oct meeting, item 3).
            ln["net_wt"] = S.net_from_gross(ln[k], ln.get("stones") or [])
            self._refine(ln)
        elif k == "net_wt":
            self._refine(ln)
        elif k == "tag_price":
            ln["_tag_typed"] = bool(ln[k])          # a tag typed stays (630)
        self._recalc_line(ln)
        self._render()
        self.grid.selectRow(r)

    # -- the purchase line typed in the grid (24 Nov video) -------------------
    def _inline_lists(self) -> None:
        with SessionLocal() as s:
            self._locs = {l.name: l.id for l in s.scalars(select(Location).order_by(Location.name))}
            self._metal_ids = {m.name: m.id for m in s.scalars(select(Metal).order_by(Metal.name))}
            self._sku_codes = list(s.scalars(select(ProductSku.sku_code)
                                             .order_by(ProductSku.sku_code)))
        for key, items in (("location", list(self._locs)), ("sku", self._sku_codes),
                           ("metal", list(self._metal_ids)),
                           ("labour_per", ["NetWt", "GrossWt", "Pcs"])):
            c = next(i for i, x in enumerate(self.cols) if x[0] == key)
            self.grid.setItemDelegateForColumn(c, _ListDelegate(items, self.grid))

    def _default_loc(self) -> tuple[int | None, str]:
        locs = getattr(self, "_locs", {})
        if self.lines:
            return self.lines[-1].get("location_id"), self.lines[-1].get("location") or ""
        if "Primary" in locs:
            return locs["Primary"], "Primary"
        return next(((i, n) for n, i in locs.items()), (None, ""))

    def _blank_line(self) -> dict:
        lid, lname = self._default_loc()
        ln = {"location_id": lid, "location": lname, "pcs": 1, "stock_no": "new",
              "stones": [], "labour_per": "gm", "colour": ""}
        if self.lines:          # the Margin % / Tag % of the line above carry on
            for k in ("margin_pct", "tag_pct"):
                ln[k] = self.lines[-1].get(k)
        return ln

    def _set_metal(self, s, ln: dict, metal_id: int | None) -> None:
        from diagold.services import mfg_pricing, production
        m = s.get(Metal, metal_id) if metal_id else None
        ln["metal_id"], ln["metal"] = (m.id, m.name) if m else (None, "")
        if m is not None:
            ln["title"] = mfg_pricing.title_of(m)
            ln["metal_rate"] = production.metal_price(s, m.id, _pydate(self.date))
            ln["colour"] = ln.get("colour") or m.colour or ""

    def _edited_inline(self, r: int, c: int, k: str, text: str) -> None:
        if r >= len(self.lines):
            if not text:
                return
            self.lines.append(self._blank_line())
        ln = self.lines[r]
        bad = ""
        if k == "location":
            if text in self._locs:
                ln["location_id"], ln["location"] = self._locs[text], text
            else:
                bad = f"No location '{text}'."
        elif k == "sku":
            with SessionLocal() as s:
                p = s.scalar(select(ProductSku).where(ProductSku.sku_code == text))
                if p is None:
                    bad = f"No SKU '{text}' in the SKU master."
                else:
                    ln.update({"product_sku_id": p.id, "sku": p.sku_code,
                               "photo": p.photo or "", "snap": p.snap or "",
                               "size": ln.get("size") or p.jewelry_size or ""})
                    self._set_metal(s, ln, p.metal_id or ln.get("metal_id"))
        elif k == "metal":
            if text in self._metal_ids:
                with SessionLocal() as s:
                    self._set_metal(s, ln, self._metal_ids[text])
            else:
                bad = f"No metal '{text}'."
        elif k == "labour_per":
            ln[k] = _unit_code(text)
        elif k in _TEXT_KEYS:
            ln[k] = text
        else:
            val = _num(text)
            ln[k] = (int(val) if k == "pcs" and val is not None else val) \
                if val is not None else (1 if k == "pcs" else D(0))
            if k == "gross_wt":
                ln["net_wt"] = S.net_from_gross(ln[k], ln.get("stones") or [])
            elif k == "tag_price":
                ln["_tag_typed"] = bool(ln[k])
        self._refine(ln)
        self._recalc_line(ln)
        self._render()
        if bad:
            _warn(self, self.t.title, bad)
            self.grid.setCurrentCell(r, c)
            return
        if k == "gross_wt" and not ln.get("stones") and not ln.get("_breakup_asked"):
            # As the legacy screen: the gross typed, the breakup pop-up opens.
            ln["_breakup_asked"] = True
            QTimer.singleShot(0, lambda row=r: self._breakup_row(row))
        self._next_cell(r, c)

    def _next_cell(self, r: int, c: int) -> None:
        """Enter moves on to the next box to type, then the next line."""
        nxt = next((i for i in range(c + 1, len(self.cols)) if self.cols[i][2]), None)
        if nxt is None:
            r, nxt = r + 1, next(i for i, x in enumerate(self.cols) if x[0] == "sku")
        if r < self.grid.rowCount():
            self.grid.setCurrentCell(r, nxt)

    @staticmethod
    def _refine(ln: dict) -> None:
        """FineWt follows a new N-Wt: net x title / 1000."""
        if ln.get("title") not in (None, ""):
            ln["fine_wt"] = (D(str(ln.get("net_wt") or 0)) * D(str(ln["title"]))
                             / 1000).quantize(D("0.001"))

    def _recalc_line(self, ln: dict) -> None:
        from diagold.services import costing
        net = D(str(ln.get("net_wt") or 0))
        ln["metal_amount"] = (net * D(str(ln.get("metal_rate") or 0))).quantize(D("0.01"))
        ln["stone_amount"] = sum((S.stone_amount(s) for s in ln.get("stones") or []), D(0))
        per = ln.get("labour_per") or "gm"
        base = D(str(ln.get("gross_wt") or 0)) if per == "gw" else net
        ln["labour"] = S.labour_amount(ln.get("labour_rate"), per, base, ln.get("pcs"))
        ln["total"] = (ln["metal_amount"] + ln["stone_amount"]
                       + D(str(ln.get("setting_amount") or 0)) + ln["labour"]
                       + D(str(ln.get("other_amount") or 0))
                       + D(str(ln.get("st_handling") or 0))
                       + D(str(ln.get("finding_labour") or 0))).quantize(D("0.01"))
        self._margin(ln)

    @staticmethod
    def _margin(ln: dict) -> None:
        """Margin % of the Total Amount, Total Value = Total Amount + Margin,
        Price Per = Total Value / Pcs, Tag Price from the value and Tag %
        unless typed (legacy: Margin 50 % on 4,20,257.63 = 2,10,128.82 ->
        6,30,386.45, tag 630)."""
        total = D(str(ln.get("total") or 0))
        margin = (total * D(str(ln.get("margin_pct") or 0)) / 100).quantize(D("0.01"))
        ln["margin_amount"] = margin
        ln["total_value"] = (total + margin).quantize(D("0.01"))
        pcs = max(int(ln.get("pcs") or 1), 1)
        ln["price_per"] = (ln["total_value"] / pcs).quantize(D("0.01"))
        if not ln.get("_tag_typed"):
            tagged = ln["total_value"] * (1 + D(str(ln.get("tag_pct") or 0)) / 100)
            from diagold.services import mfg_pricing
            shown = mfg_pricing.tag_display(tagged)
            ln["tag_price"] = _num(shown) or D(0)

    def _revalue(self) -> None:
        """The date moved: metal at that day's rate, unless typed."""
        if self._edit_id is not None or self.vr_type in S.NEW_PIECES:
            self._due()
            return
        from diagold.services import production
        with SessionLocal() as s:
            for ln in self.lines:
                ln["metal_rate"] = production.metal_price(s, ln.get("metal_id"), _pydate(self.date))
                self._recalc_line(ln)
        self._render()
        self._due()

    def _selected(self) -> int | None:
        rows = self.grid.selectionModel().selectedRows()
        if not rows or not self.lines or rows[0].row() >= len(self.lines):
            _info(self, self.t.title, "Select a line first.")
            return None
        return rows[0].row()

    def _line_selected(self) -> None:
        rows = self.grid.selectionModel().selectedRows()
        path = self.lines[rows[0].row()].get("photo", "") if rows and rows[0].row() < len(
            self.lines) else ""
        pix = photo_cache.load(path)
        self._photo_path = path if not pix.isNull() else ""
        if pix.isNull():
            self.photo.setPixmap(QPixmap())
            self.photo.setText("no photo")
        else:
            self.photo.setText("")
            self.photo.setPixmap(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))

    def _enlarge(self) -> None:
        if self._photo_path:
            big = QLabel()
            big.setPixmap(photo_cache.load(self._photo_path).scaled(
                720, 720, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            show_in_dialog(self, big, "Photo", (760, 760))

    def remove_line(self) -> None:
        if self._editing_blocked():
            return
        r = self._selected()
        if r is not None:
            self.lines.pop(r)
            self._render()

    def _breakup_row(self, r: int) -> None:
        if 0 <= r < len(self.lines):
            self.grid.selectRow(r)
            self.stone_breakup(r)

    def stone_breakup(self, row: int | None = None) -> None:
        r = row if row is not None else self._selected()
        if r is None:
            return
        ln = self.lines[r]
        if self.vr_type in S.NEW_PIECES and not ln.get("_line_id"):
            dlg = PurchaseBreakupDialog(ln, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                dlg.apply(ln)
                self._refine(ln)
                self._recalc_line(ln)
                self._render()
                self.grid.selectRow(r)
            return
        dlg = StoneBreakupDialog(ln.get("stones") or [], self,
                                 full=self.vr_type in S.NEW_PIECES and not ln.get("_line_id"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ln["stones"] = dlg.stones()
            ln["st_wt"] = sum((D(s["weight"]) for s in ln["stones"]), D(0))
            if self.vr_type in S.NEW_PIECES and not ln.get("_line_id"):
                ln["net_wt"] = S.net_from_gross(ln.get("gross_wt"), ln["stones"])
                self._refine(ln)
            self._recalc_line(ln)
            self._render()

    # -- Add / Edit / Save / Delete ----------------------------------------
    def _editing_blocked(self) -> bool:
        """Nothing is blocked on a voucher open for editing any more (23 Nov):
        pieces may be added and removed and Save keeps the same Vr No."""
        return False

    def new_voucher(self) -> None:
        self._edit_id = None
        self._docs = []
        self.lines = []
        self.narration.clear()
        self.ref.clear()
        self.account.setEnabled(True)
        self.refresh()

    def _pick_voucher(self, title: str) -> int | None:
        with SessionLocal() as s:
            rows = []
            for v in s.scalars(select(ReadyVoucher).where(ReadyVoucher.vr_type == self.vr_type)
                               .order_by(ReadyVoucher.vr_no.desc()).limit(500)):
                a = s.get(Account, v.account_id) if v.account_id else None
                rows.append((v.id, f"Vr {v.vr_no}   {v.vr_date:%d-%m-%Y}   "
                             f"{a.name if a else ''}   {len(v.lines)} pc   {v.total:,.2f}"))
        if not rows:
            _info(self, title, f"No {self.t.title} has been saved yet.")
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(560, 380)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        for vid, text in rows:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, vid)
            lst.addItem(it)
        lst.setCurrentRow(0)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
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
        vid = self._pick_voucher(f"Edit — open a saved {self.t.title}")
        if vid is None:
            return
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            self.date.blockSignals(True)
            self.date.setDate(_qdate(v.vr_date))
            self.date.blockSignals(False)
            self.time.setText(v.vr_time or "")
            a = s.get(Account, v.account_id) if v.account_id else None
            self.account.setCurrentText(a.name if a else "")
            self.ref.setText(v.ref_no or "")
            self.narration.setText(v.remark or "")
            self.credit.setValue(int(v.credit_days or 0))
            self.salesperson.setText(v.salesperson or "")
            self.bank.setText(v.bank_name or "")
            self.margin_type.setText(v.margin_type or "")
            self.mode.setCurrentText(v.mode or "Bill")
            self.chart_cb.blockSignals(True)
            self.chart_cb.setChecked(bool(v.client_chart))
            self.chart_cb.blockSignals(False)
            self.for_repair.setChecked(bool(v.for_repair))
            self.bill_no.setText(v.bill_no or "")
            self.bill_amt.setText(f"{v.bill_amount or ''}")
            if v.bill_date:
                self.bill_date.setDate(_qdate(v.bill_date))
            self.lines = []
            for l in v.lines:
                item = s.get(StockItem, l.stock_item_id) if l.stock_item_id else None
                info = S.describe(s, item) if item else {}
                self.lines.append({**info, "_line_id": l.id,
                                   **{k: getattr(l, k) for k, _h, _e in self.cols
                                      if hasattr(l, k)},
                                   "stock_no": item.stock_no if item else "",
                                   "stones": json.loads(l.stones_json or "[]"),
                                   "breakup": json.loads(l.breakup_json or "{}")})
                if self.vr_type in S.NEW_PIECES:
                    ln = self.lines[-1]
                    ln["_tag_typed"] = bool(l.tag_price)
                    self._margin(ln)
        self._edit_id = self._last_id = vid
        self.account.setEnabled(False)
        self.refresh()
        self.totals.setText(self.totals.text() + "   <b>Editing</b> - add or remove pieces, change the green cells "
                            "or the header and Save.")

    def _head(self) -> dict[str, Any]:
        return {"vr_date": _pydate(self.date), "vr_time": self.time.text().strip(),
                "account_id": self._account_id(), "ref_no": self.ref.text().strip(),
                "currency_code": self.currency.currentText(),
                "credit_days": self.credit.value(),
                "salesperson": self.salesperson.text().strip(),
                "bank_name": self.bank.text().strip(),
                "margin_type": self.margin_type.text().strip(),
                "bill_date": _pydate(self.bill_date) if self.bill_no.text().strip() else None,
                "bill_no": self.bill_no.text().strip(),
                "bill_account_id": self.bill_acct.currentData(),
                "bill_amount": _num(self.bill_amt.text()) or 0,
                "remark": self.narration.text().strip(),
                "mode": self.mode.currentText(),
                "client_chart": self.vr_type in CHART_TYPES and self.chart_cb.isChecked(),
                "for_repair": self.vr_type == "rs_sale_return" and self.for_repair.isChecked()}

    def save(self) -> None:
        if not self.lines:
            _info(self, "Save", "Add the pieces first.")
            return
        if self.t.party != "none" and not self._account_id():
            _info(self, "Save", "Choose the " + ("supplier." if self.t.party == "supplier"
                                                 else "account."))
            return
        what = (f"the changes to this {self.t.title}" if self._edit_id
                else f"{self.t.title} of {len(self.lines)} piece(s)")
        if not confirm_save(self, what):
            return
        with SessionLocal() as s:
            try:
                if self._edit_id is not None:
                    v = S.edit_ready(s, s.get(ReadyVoucher, self._edit_id), self._head(),
                                     self.lines, user_id=getattr(self.user, "id", None))
                else:
                    v = S.post_ready(s, self.vr_type, self._head(), self.lines,
                                     user_id=getattr(self.user, "id", None))
                s.commit()
                vid, vr = v.id, v.vr_no
                nos = [s.get(StockItem, l.stock_item_id).stock_no for l in v.lines
                       if l.stock_item_id]
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot save", str(exc))
                return
        from diagold.ui.attachments import attach_pending
        attach_pending(self.vr_type, vr, self._docs, self.user)
        self.new_voucher()
        self._last_id = vid
        extra = (f" New Stock No {', '.join(map(str, nos))}." if self.vr_type in S.NEW_PIECES
                 else "")
        self.totals.setText(f"Saved {self.t.title} Vr {vr}.{extra} Print prints it.")
        if self.vr_type in S.NEW_PIECES and nos:
            # As the legacy screen: the Bar-Code Tag List opens on Save.
            QTimer.singleShot(0, self.tag_print)

    def delete_voucher(self) -> None:
        vid = self._edit_id or self._pick_voucher(f"Delete — pick the {self.t.title}")
        if vid is None:
            return
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            vr = v.vr_no
        if QMessageBox.question(self, "Delete", f"Delete {self.t.title} Vr {vr}?\n\nEvery "
                                "piece goes back to where it was; the voucher is kept in the "
                                "deletion log.") != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                S.delete_ready(s, s.get(ReadyVoucher, vid), user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Cannot delete", str(exc))
                return
        self.new_voucher()
        self._last_id = None
        self.totals.setText(f"{self.t.title} Vr {vr} deleted.")

    # -- print / excel ------------------------------------------------------
    def _voucher_for_print(self) -> int | None:
        vid = self._edit_id or self._last_id
        if vid is None:
            vid = self._pick_voucher(f"Print — pick the {self.t.title}")
        return vid

    def print_voucher(self) -> None:
        vid = self._voucher_for_print()
        if vid is None:
            return
        from diagold.services import documents
        from diagold.services import admin as ADM
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            a = s.get(Account, v.account_id) if v.account_id else None
            # Sale Invoice: the client's layout or the default (5 Oct §4.14).
            lay = ADM.layout_for(s, "SALE INVOICE", v.account_id)[1] \
                if self.vr_type == "rs_sale" else dict(ADM.LAYOUT_DEFAULT)
            rows = []
            for l in v.lines:
                item = s.get(StockItem, l.stock_item_id) if l.stock_item_id else None
                sku = s.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
                prices = (
                    f"<td align=right>{D(str(l.metal_rate)):,.2f}</td>"
                    f"<td align=right>{D(str(l.metal_amount)):,.2f}</td>"
                    f"<td align=right>{D(str(l.stone_amount)):,.2f}</td>"
                    f"<td align=right>{D(str(l.labour)):,.2f}</td>"
                    f"<td align=right><b>{D(str(l.total)):,.2f}</b></td>"
                    if lay["show_prices"] else "")
                rows.append(
                    f"<tr><td>{l.sno}</td><td>{item.stock_no if item else ''}</td>"
                    f"<td>{sku.sku_code if sku else ''}</td><td align=right>{l.pcs}</td>"
                    f"<td align=right>{D(str(l.gross_wt)):.3f}</td>"
                    f"<td align=right>{D(str(l.net_wt)):.3f}</td>{prices}</tr>")
            heads = ("<th>Mt Rate</th><th>Metal</th><th>Stone</th><th>Labour</th><th>Total</th>"
                     if lay["show_prices"] else "")
            total_row = (f"<tr><td colspan=10 align=right><b>Total</b></td><td align=right><b>"
                         f"{D(str(v.total)):,.2f}</b></td></tr>" if lay["show_prices"] else "")
            html = (f"<h2>{lay['title'] or self.t.title} — Vr {v.vr_no}</h2>"
                    + (f"<p>{lay['header'].replace(chr(10), '<br>')}</p>" if lay["header"]
                       else "")
                    + f"<p>Date {v.vr_date:%d-%m-%Y} {v.vr_time or ''} · {a.name if a else ''}"
                    + (f" · Ref {v.ref_no}" if v.ref_no else "")
                    + (f" · Credit {v.credit_days} days, due {v.due_date:%d-%m-%Y}"
                       if v.due_date else "") + "</p>"
                    "<table border=1 cellspacing=0 cellpadding=3 width=100%><tr><th>#</th>"
                    "<th>Barcode</th><th>SKU</th><th>Pcs</th><th>G-Wt</th><th>N-Wt</th>"
                    + heads + "</tr>" + "".join(rows) + total_row + "</table>"
                    + ("<p><b>NOTE: Metal Rate Will Be Charged as on Date of Payment</b></p>"
                       if self.vr_type == "rs_sale" else "") + f"<p>{v.remark or ''}</p>"
                    + (f"<p>{lay['footer'].replace(chr(10), '<br>')}</p>" if lay["footer"]
                       else "")
                    + ADM.declaration_html(s, self.vr_type))
            path = documents.PRINT_DIR / f"{self.vr_type}_{v.vr_no}.pdf"
        documents.to_pdf(html, path)
        _info(self, "Print", f"Saved {path}")

    def excel_invoice(self) -> None:
        vid = self._voucher_for_print()
        if vid is None:
            return
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            path, _ = QFileDialog.getSaveFileName(self, "Excel Invoice",
                                                  f"invoice_{v.vr_no}.xlsx", "Excel (*.xlsx)")
            if not path:
                return
            S.excel_invoice(s, v, path)
        _info(self, "Excel Invoice", f"Saved {path}")

    def dispatch(self) -> None:
        """Ship By / Tracking No / Ship Date / Expected Date on the sale, and
        the WhatsApp message to the customer (9 Oct T-07 / T-08)."""
        vid = self._voucher_for_print()
        if vid is None:
            return
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            dlg = DispatchDialog(v, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            try:
                msg = S.dispatch(s, v, **dlg.values(), user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                _warn(self, "Dispatch", str(exc))
                return
            text = f"Sale Vr {v.vr_no} dispatched on {v.ship_date:%d-%m-%Y} via {v.ship_by}."
            if msg is not None:
                text += f"\n\nWhatsApp: {msg.status}" + (f" - {msg.error}" if msg.error else "")
                if msg.status == "sandbox":
                    text += f"\n(sandbox - not sent)\n\n{msg.body}"
        _info(self, "Dispatch", text)

    def resend_whatsapp(self) -> None:
        vid = self._voucher_for_print()
        if vid is None:
            return
        from diagold.services import whatsapp
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            if not v.ship_date:
                _info(self, "Resend WhatsApp", "Dispatch the sale first (Dispatch / Tracking).")
                return
            msg = whatsapp.notify_dispatch(s, v, user_id=getattr(self.user, "id", None),
                                           force=True)
            s.commit()
            _info(self, "Resend WhatsApp", f"{msg.status}" + (f" - {msg.error}" if msg.error
                                                              else "") + f"\n\n{msg.body}")

    # -- purchase actions (2 Oct §4.5) ------------------------------------
    def sku_search(self) -> None:
        """SKU Search: find the SKU by code / description, then Add Piece on it."""
        if self._editing_blocked():
            return
        with SessionLocal() as s:
            skus = [(p.id, p.sku_code, p.description or "", p.category or "")
                    for p in s.scalars(select(ProductSku).order_by(ProductSku.sku_code))]
        dlg = QDialog(self)
        dlg.setWindowTitle("SKU Search")
        dlg.setMinimumSize(560, 420)
        lay = QVBoxLayout(dlg)
        find = QLineEdit()
        find.setPlaceholderText("SKU code, description, category…")
        lay.addWidget(find)
        lst = QListWidget()
        for sid, code, desc, cat in skus:
            it = QListWidgetItem(f"{code}   {desc}   {cat}".strip())
            it.setData(Qt.ItemDataRole.UserRole, sid)
            lst.addItem(it)
        find.textChanged.connect(lambda t: [lst.item(i).setHidden(
            t.strip().lower() not in lst.item(i).text().lower()) for i in range(lst.count())])
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted or lst.currentItem() is None:
            return
        piece = NewPieceDialog(self)
        i = piece.sku.findData(lst.currentItem().data(Qt.ItemDataRole.UserRole))
        if i >= 0:
            piece.sku.setCurrentIndex(i)
        if piece.exec() == QDialog.DialogCode.Accepted:
            self.lines.append(piece.values())
            self._render()

    def _pdf(self, name: str, html: str) -> None:
        from diagold.services import documents
        path = documents.PRINT_DIR / f"{name}_{datetime.now():%Y%m%d-%H%M%S}.pdf"
        documents.to_pdf(html, path)
        _info(self, "Print", f"Saved {path}")

    def _rows_for(self, vid: int) -> tuple[str, list[dict]]:
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            a = s.get(Account, v.account_id) if v.account_id else None
            head = (f"{self.t.title} — Vr {v.vr_no} dt {v.vr_date:%d-%m-%Y}"
                    + (f" · {a.name}" if a else "") + (f" · Ref {v.ref_no}" if v.ref_no else "")
                    + (f" · Bill {v.bill_no} dt {v.bill_date:%d-%m-%Y}" if v.bill_no and v.bill_date
                       else ""))
            rows = []
            for l in v.lines:
                item = s.get(StockItem, l.stock_item_id) if l.stock_item_id else None
                sku = s.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
                metal = s.get(Metal, l.metal_id) if l.metal_id else None
                rows.append({"sno": l.sno, "stock_no": item.stock_no if item else "",
                             "sku": sku.sku_code if sku else "", "metal": metal.name if metal else "",
                             "pcs": l.pcs, "g": D(str(l.gross_wt)), "n": D(str(l.net_wt)),
                             "st": D(str(l.st_wt)), "fine": D(str(l.fine_wt)), "line": l,
                             "stones": json.loads(l.stones_json or "[]"),
                             "photo": sku.photo if sku else "",
                             "total": D(str(l.total))})
        return head, rows

    def breakup_sheet(self) -> None:
        """BreakUp Sheet: each piece with metal, every stone and labour."""
        vid = self._voucher_for_print()
        if vid is None:
            return
        head, rows = self._rows_for(vid)
        parts = [f"<h2>BreakUp Sheet</h2><p>{head}</p>"]
        for r in rows:
            l = r["line"]
            parts.append(
                f"<h3>{r['sno']}. Stock {r['stock_no']} · {r['sku']} · {r['metal']} · "
                f"{r['pcs']} pc · G {r['g']:.3f} · N {r['n']:.3f}</h3>"
                "<table border=1 cellspacing=0 cellpadding=3 width=100%>"
                "<tr><th>Item</th><th>Pcs</th><th>Cts / Wt</th><th>Rate</th><th>Amount</th></tr>"
                f"<tr><td>Metal</td><td></td><td align=right>{r['n']:.3f}</td>"
                f"<td align=right>{D(str(l.metal_rate)):,.2f}</td>"
                f"<td align=right>{D(str(l.metal_amount)):,.2f}</td></tr>"
                + "".join(f"<tr><td>{st.get('label', '')} {st.get('size') or ''}</td>"
                          f"<td align=right>{st.get('pcs') or 0}</td>"
                          f"<td align=right>{st.get('weight') or 0}</td>"
                          f"<td align=right>{D(str(st.get('price') or 0)):,.2f}</td>"
                          f"<td align=right>{S.stone_amount(st):,.2f}</td></tr>"
                          for st in r["stones"])
                + f"<tr><td>Labour</td><td></td><td align=right>{r['n']:.3f}</td>"
                f"<td align=right>{D(str(l.labour_rate)):,.2f}</td>"
                f"<td align=right>{D(str(l.labour)):,.2f}</td></tr>"
                f"<tr><td colspan=4><b>Total</b></td><td align=right><b>{r['total']:,.2f}</b>"
                "</td></tr></table>")
        self._pdf(f"{self.vr_type}_breakup", "".join(parts))

    def packing_list(self) -> None:
        """Packing List: the pieces with their weights, no prices."""
        vid = self._voucher_for_print()
        if vid is None:
            return
        head, rows = self._rows_for(vid)
        from diagold.services import admin as ADM
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            lay = ADM.layout_for(s, "PACKING LIST", v.account_id)[1]
            decl = ADM.declaration_html(s, self.vr_type)
        if lay["header"]:
            head += "<br>" + lay["header"].replace("\n", "<br>")
        foot = (f"<p>{lay['footer'].replace(chr(10), '<br>')}</p>" if lay["footer"] else "")
        body = "".join(f"<tr><td>{r['sno']}</td><td>{r['stock_no']}</td><td>{r['sku']}</td>"
                       f"<td>{r['metal']}</td><td align=right>{r['pcs']}</td>"
                       f"<td align=right>{r['g']:.3f}</td><td align=right>{r['n']:.3f}</td>"
                       f"<td align=right>{r['st']:.3f}</td><td align=right>{r['fine']:.3f}</td></tr>"
                       for r in rows)
        tot = lambda k: sum((r[k] for r in rows), D(0))          # noqa: E731
        self._pdf(f"{self.vr_type}_packing",
                  f"<h2>{lay['title'] or 'Packing List'}</h2><p>{head}</p><table border=1 "
                  "cellspacing=0 "
                  "cellpadding=3 width=100%><tr><th>#</th><th>Barcode</th><th>SKU</th>"
                  "<th>Metal</th><th>Pcs</th><th>Gross</th><th>Net</th><th>St Wt</th>"
                  "<th>Fine</th></tr>" + body +
                  f"<tr><td colspan=4><b>Total</b></td><td align=right><b>"
                  f"{sum(r['pcs'] for r in rows)}</b></td><td align=right><b>{tot('g'):.3f}</b>"
                  f"</td><td align=right><b>{tot('n'):.3f}</b></td><td align=right><b>"
                  f"{tot('st'):.3f}</b></td><td align=right><b>{tot('fine'):.3f}</b></td></tr>"
                  "</table>" + foot + decl)

    def picture_invoice(self) -> None:
        """Catalog / Picture Invoice: each piece with its photo."""
        vid = self._voucher_for_print()
        if vid is None:
            return
        head, rows = self._rows_for(vid)
        cells = "".join(
            "<td width=33% valign=top align=center style='border:1px solid #ccc;padding:6px'>"
            + (f"<img src='{r['photo']}' height=110><br>" if r["photo"] else "<br>[no photo]<br>")
            + f"<b>{r['sku']}</b><br>Stock {r['stock_no']}<br>G {r['g']:.3f} · N {r['n']:.3f}"
            f"<br>{r['total']:,.2f}</td>" + ("</tr><tr>" if (i + 1) % 3 == 0 else "")
            for i, r in enumerate(rows))
        self._pdf(f"{self.vr_type}_picture", f"<h2>Picture Invoice</h2><p>{head}</p>"
                  f"<table width=100% cellspacing=4><tr>{cells}</tr></table>")

    def stone_summary(self) -> None:
        """St. Summ.: the stones on the voucher by group - pcs, carats, amount."""
        source = self.lines
        if not source:
            vid = self._voucher_for_print()
            if vid is None:
                return
            _head, rows = self._rows_for(vid)
            source = [{"stones": r["stones"]} for r in rows]
        acc: dict[str, list] = {}
        for ln in source:
            for st in ln.get("stones") or []:
                a = acc.setdefault(S.stone_block(st), [0, D(0), D(0)])
                a[0] += int(st.get("pcs") or 0)
                a[1] += D(str(st.get("weight") or 0))
                a[2] += S.stone_amount(st)
        t = QTableWidget(len(acc), 4)
        t.setHorizontalHeaderLabels(["Stone", "Pcs", "Cts", "Amount"])
        t.verticalHeader().setVisible(False)
        for r, (k, (p, w, a)) in enumerate(sorted(acc.items())):
            for c, v in enumerate((k, str(p), f"{w:.3f}", f"{a:,.2f}")):
                t.setItem(r, c, QTableWidgetItem(v))
        auto_fit(t)
        show_in_dialog(self, t, "St. Summ. — stones by group", (520, 300))

    def tag_print(self) -> None:
        """Tag Print: the barcode tags of the pieces this voucher brought in."""
        vid = self._voucher_for_print()
        if vid is None:
            return
        from diagold.ui.manufacturing import TagListDialog
        with SessionLocal() as s:
            v = s.get(ReadyVoucher, vid)
            items = [s.get(StockItem, l.stock_item_id) for l in v.lines if l.stock_item_id]
            dlg = TagListDialog(None, self)
            dlg._add_items(s, items)
        dlg._fill()
        dlg.exec()


class DispatchDialog(QDialog):
    """Dispatch of a sale (9 Oct §4.17 / A4): Ship By, Tracking No, Ship
    Date, Expected Date - and whether the customer gets a WhatsApp."""

    SHIP_BY = ("Courier", "By Hand", "Transport", "Angadia", "Post")

    def __init__(self, v: ReadyVoucher, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Dispatch — Sale Vr {v.vr_no}")
        form = QFormLayout(self)
        self.ship_by = QComboBox()
        self.ship_by.setEditable(True)
        self.ship_by.addItems(self.SHIP_BY)
        if v.ship_by:
            self.ship_by.setCurrentText(v.ship_by)
        self.ship_no = QLineEdit(v.ship_no or "")
        self.ship_no.setPlaceholderText("AWB / docket / tracking number")
        self.ship_date = QDateEdit(_qdate(v.ship_date or date.today()))
        self.expected = QDateEdit(_qdate(v.expected_date or (date.today() + timedelta(days=3))))
        for d in (self.ship_date, self.expected):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
        form.addRow("Ship By", self.ship_by)
        form.addRow("Tracking No", self.ship_no)
        form.addRow("Ship Date", self.ship_date)
        form.addRow("Expected Delivery", self.expected)
        note = QLabel("Saving sends the dispatch message on WhatsApp when it is switched on in "
                      "Tools ▸ Option and the customer has opted in.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict[str, Any]:
        return {"ship_by": self.ship_by.currentText().strip(),
                "ship_no": self.ship_no.text().strip(),
                "ship_date": _pydate(self.ship_date), "expected_date": _pydate(self.expected)}
