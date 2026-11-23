"""Inventory ▸ Stock Transfer (2 Oct Session 3 §4.6, T-06): one voucher, four
panes - Ready Stock Outward, Metal, Stone, Ready Stock Transfer - with the
legacy actions Print 2, Melting List, Stock Melting, Barcode, Stock Location
Transfer and Transfer Reg. What melting and the loss columns mean is still to
be explained by the client (UNCONFIRMED, Q6): stock moves by In / Out, losses
are recorded for the loss registers.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
# Number boxes are text boxes (23 Nov: spin boxes showed nothing on the client's
# Windows PC); same names, same API - see diagold/ui/numbox.py.
from diagold.ui.numbox import DoubleSpinBox as QDoubleSpinBox  # noqa: E402,F811
from diagold.ui.numbox import SpinBox as QSpinBox  # noqa: E402,F811
from sqlalchemy import select

from diagold.db.models import Location, Metal, StockItem, StockTransfer, StoneSku
from diagold.db.session import SessionLocal
from diagold.services import sales as S
from diagold.services import stock_transfer as ST
from diagold.services.production import ProductionError
from diagold.ui.confirm import confirm_save
from diagold.ui.crud import _wide_popup, auto_fit
from diagold.ui.production import _Screen, _item, _pydate, _qdate, _table

D = Decimal
PANE_TITLES = {"ready_out": "Ready Stock Outward", "metal": "Metal", "stone": "Stone",
               "ready_transfer": "Ready Stock Transfer"}
PANE_COLS: dict[str, list[tuple[str, str]]] = {
    "ready_out": [("location", "Location"), ("stock_no", "Barcode"), ("job_no", "JobNo"),
                  ("sku", "SKU"), ("metal", "Metal"), ("colour", "Col"), ("size", "Size"),
                  ("gross_wt", "GrossWt"), ("out_pcs", "Pcs"), ("out_wt", "Weight"),
                  ("price", "Price"), ("amount", "Amount"), ("remark", "Remark")],
    "metal": [("location", "Location"), ("mt_type", "MtType"), ("metal_mould", "Metal/Mould"),
              ("name", "Metal"), ("colour", "Col"), ("wt_per_pcs", "Wt/Pcs"),
              ("in_pcs", "In-Pcs"), ("in_wt", "In-Wt"),
              ("in_loss_wt", "In-Loss"), ("out_pcs", "Out-Pcs"), ("out_wt", "Out-Wt"),
              ("out_loss_wt", "Out-Loss"), ("price", "Price"), ("unit", "Unit"),
              ("amount", "Amount"), ("job_no", "JobNo"), ("item_size", "Item Size"),
              ("st_size", "St Size")],
    "stone": [("location", "Location"), ("s_type", "StType"), ("name", "SSKU"), ("size", "Size"),
              ("wt_per_pcs", "Wt/Pcs"), ("in_pcs", "In-Pcs"), ("in_wt", "In-Wt"), ("in_loss_pcs", "In-LossPcs"),
              ("in_loss_wt", "In-LossWt"), ("out_pcs", "Out-Pcs"), ("out_wt", "Out-Wt"),
              ("out_loss_pcs", "Out-LossPcs"), ("out_loss_wt", "Out-LossWt"),
              ("price", "Price"), ("unit", "Unit"), ("amount", "Amount"), ("remark", "Remark")],
    "ready_transfer": [("location", "From"), ("to_location", "To"), ("stock_no", "Barcode"),
                       ("job_no", "JobNo"), ("sku", "SKU"), ("metal", "Metal"),
                       ("gross_wt", "GrossWt"), ("out_pcs", "Pcs"), ("out_wt", "Weight"),
                       ("remark", "Remark")],
}


def _locations() -> list[tuple[int, str]]:
    with SessionLocal() as s:
        return [(l.id, l.name) for l in s.scalars(select(Location).order_by(Location.name))]


def _stone_sizes() -> dict[str, list[tuple[str, int, str, str]]]:
    """{stone name: [(size, Stone SKU id, stone type, cost)]} - SSKU lists each
    stone once and Size its sizes, as the purchase grids (16 Nov)."""
    from diagold.db.models import StoneMaster
    from diagold.services.stone_master import group_stone_skus, size_label
    out: dict[str, list[tuple[str, int, str, str]]] = {}
    with SessionLocal() as s:
        if group_stone_skus(s):
            s.commit()
        for m in s.scalars(select(StoneMaster).where(StoneMaster.is_active == True)
                           .order_by(StoneMaster.name)):
            rows = [(size_label(k), k.id, k.stone_type or "", str(k.cost_price or 0))
                    for k in m.sizes if k.is_active]
            if rows:
                out[m.name] = rows
    return out


def _pick_stone(sizes: dict, name: str, size: str) -> tuple[str, int, str, str] | None:
    rows = sizes.get(name, [])
    hit = [r for r in rows if r[0].lower() == size.strip().lower()]
    return hit[0] if hit else (rows[0] if len(rows) == 1 and not size.strip() else None)


def _dbl(dec: int) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setDecimals(dec)
    w.setRange(0, 1e9)
    return w


class LineDialog(QDialog):
    """A Metal or Stone pane line."""

    def __init__(self, pane: str, parent=None):
        super().__init__(parent)
        self.pane = pane
        self.setWindowTitle(f"{PANE_TITLES[pane]} line")
        lay = QVBoxLayout(self)
        self.setMinimumWidth(1340)
        self.loc = QComboBox()
        for lid, name in _locations():
            self.loc.addItem(name, lid)
        self.item = QComboBox()
        self.item.setEditable(True)
        with SessionLocal() as s:
            if pane == "metal":
                for m in s.scalars(select(Metal).order_by(Metal.name)):
                    self.item.addItem(m.name, m.id)
            else:
                # SSKU lists each stone once (POLKI, EMERALD PEAR ...), Size its
                # sizes (16 Nov: "only SSKU name, remove size").
                self._sizes = _stone_sizes()
                for name in self._sizes:
                    self.item.addItem(name, name)
        _wide_popup(self.item)
        self.item.currentIndexChanged.connect(lambda _i: self._item_changed())
        self.mt_type, self.colour = QLineEdit("Actual"), QLineEdit("Y")
        self.metal_mould = QComboBox()
        self.metal_mould.addItems(["Metal", "Mould"])
        self.item_size, self.st_size = QLineEdit(), QLineEdit()
        self.size, self.s_type = QComboBox(), QLineEdit()
        self.size.setEditable(True)
        self.size.currentTextChanged.connect(lambda _t: self._size_changed())
        self.in_pcs, self.out_pcs = QSpinBox(), QSpinBox()
        self.in_loss_pcs, self.out_loss_pcs = QSpinBox(), QSpinBox()
        for w in (self.in_pcs, self.out_pcs, self.in_loss_pcs, self.out_loss_pcs):
            w.setRange(0, 1000000)
        self.in_wt, self.out_wt = _dbl(3), _dbl(3)
        self.in_loss_wt, self.out_loss_wt = _dbl(3), _dbl(3)
        self.price = _dbl(2)
        self.unit = QComboBox()
        self.unit.addItems(["Gms"] if pane == "metal" else ["Cts", "Pcs"])
        self.job_no, self.remark = QLineEdit(), QLineEdit()
        # One line across, headings over the boxes - the same format as the
        # pane's grid and the legacy line (14 Nov: "SAME FORMAT").
        cells: list[tuple[str, QWidget]] = [("Location", self.loc)]
        if pane == "metal":
            cells += [("MtType", self.mt_type), ("Metal/Mould", self.metal_mould),
                      ("Metal", self.item), ("Col", self.colour),
                      ("Item Size", self.item_size), ("St Size", self.st_size)]
        else:
            cells += [("StType", self.s_type), ("SSKU", self.item), ("Size", self.size)]
        for label, w in (("In-Pcs", self.in_pcs), ("In-Wt", self.in_wt),
                         ("In-LossPcs", self.in_loss_pcs), ("In-LossWt", self.in_loss_wt),
                         ("Out-Pcs", self.out_pcs), ("Out-Wt", self.out_wt),
                         ("Out-LossPcs", self.out_loss_pcs), ("Out-LossWt", self.out_loss_wt),
                         ("Price", self.price), ("Unit", self.unit), ("JobNo", self.job_no),
                         ("Remark", self.remark)):
            if self.pane == "metal" and "LossPcs" in label:
                continue
            cells.append((label, w))
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        for c, (label, w) in enumerate(cells):
            head = QLabel(label)
            head.setObjectName("Muted")
            grid.addWidget(head, 0, c)
            grid.addWidget(w, 1, c)
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                w.setMinimumWidth(84 if label == "Price" else 56)
            elif label in ("Location", "SSKU", "Metal"):
                w.setMinimumWidth(150)       # the whole name in view (14 Nov)
            elif label in ("Size", "Remark", "Metal/Mould", "StType", "MtType", "Col", "Unit",
                           "JobNo", "Item Size", "St Size"):
                w.setMinimumWidth(70)
        grid.setColumnStretch([l for l, _w in cells].index("SSKU" if pane != "metal"
                                                               else "Metal"), 3)
        lay.addLayout(grid)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._item_changed()

    def _item_changed(self) -> None:
        if self.pane != "stone":
            return
        rows = getattr(self, "_sizes", {}).get(self.item.currentText(), [])
        self.size.blockSignals(True)
        self.size.clear()
        self.size.addItems([sz for sz, *_r in rows])
        self.size.setCurrentText(rows[0][0] if len(rows) == 1 else "")
        self.size.blockSignals(False)
        self._size_changed()

    def _stone(self) -> tuple[str, int, str, str] | None:
        """The Stone SKU the SSKU + Size pair names."""
        return _pick_stone(getattr(self, "_sizes", {}), self.item.currentText(),
                           self.size.currentText())

    def _size_changed(self) -> None:
        hit = self._stone()
        if hit is not None:
            self.s_type.setText(hit[2])
            self.price.setValue(float(hit[3]))

    def values(self) -> dict[str, Any]:
        v = {"pane": self.pane, "location_id": self.loc.currentData(),
             "location": self.loc.currentText(), "name": self.item.currentText(),
             "in_pcs": self.in_pcs.value(), "in_wt": D(str(round(self.in_wt.value(), 3))),
             "in_loss_pcs": self.in_loss_pcs.value(),
             "in_loss_wt": D(str(round(self.in_loss_wt.value(), 3))),
             "out_pcs": self.out_pcs.value(), "out_wt": D(str(round(self.out_wt.value(), 3))),
             "out_loss_pcs": self.out_loss_pcs.value(),
             "out_loss_wt": D(str(round(self.out_loss_wt.value(), 3))),
             "price": D(str(self.price.value())), "unit": self.unit.currentText(),
             "job_no": int(self.job_no.text()) if self.job_no.text().strip().isdigit() else None,
             "remark": self.remark.text().strip()}
        pcs = v["in_pcs"] or v["out_pcs"]
        wt = v["in_wt"] or v["out_wt"]
        v["wt_per_pcs"] = (wt / pcs).quantize(D("0.0001")) if pcs else D(0)
        if self.pane == "metal":
            v.update(metal_id=self.item.currentData(), mt_type=self.mt_type.text().strip(),
                     colour=self.colour.text().strip(),
                     metal_mould=self.metal_mould.currentText(),
                     item_size=self.item_size.text().strip(), st_size=self.st_size.text().strip())
        else:
            hit = self._stone()
            v.update(stone_sku_id=hit[1] if hit else None,
                     particulars="" if hit else self.item.currentText(),
                     size=self.size.currentText().strip(), s_type=self.s_type.text().strip())
            v["name"] = self.item.currentText()
        v["amount"] = ST.line_amount(v)
        return v


class LocationTransferDialog(QDialog):
    """Stock Location Transfer: metal or stones out of one location and into
    another, less any loss on the way - two lines, out and in."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stock Location Transfer")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItems(["Stone", "Metal"])
        self.kind.currentIndexChanged.connect(lambda _i: self._fill_items())
        self.item = QComboBox()
        self.item.setEditable(True)
        self.size = QComboBox()
        self.size.setEditable(True)
        self._sizes = _stone_sizes()
        self.item.currentIndexChanged.connect(lambda _i: self._fill_sizes())
        self.src, self.dst = QComboBox(), QComboBox()
        for lid, name in _locations():
            self.src.addItem(name, lid)
            self.dst.addItem(name, lid)
        self.pcs, self.loss_pcs = QSpinBox(), QSpinBox()
        for w in (self.pcs, self.loss_pcs):
            w.setRange(0, 1000000)
        self.wt, self.loss_wt, self.price = _dbl(3), _dbl(3), _dbl(2)
        for label, w in (("Metal / Stone", self.kind), ("Item", self.item), ("Size", self.size),
                         ("From location", self.src), ("To location", self.dst),
                         ("Pcs sent", self.pcs), ("Weight sent", self.wt),
                         ("Loss pcs", self.loss_pcs), ("Loss weight", self.loss_wt),
                         ("Price", self.price)):
            form.addRow(label, w)
        lay.addLayout(form)
        note = QLabel("Example (2 Oct): DIA. BAGG TAPPER 10 pcs / 1.4 ct from RAJAT JI to "
                      "SONU JI. What arrives = sent - loss.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._fill_items()

    def _fill_items(self) -> None:
        self.item.clear()
        with SessionLocal() as s:
            if self.kind.currentText() == "Metal":
                for m in s.scalars(select(Metal).order_by(Metal.name)):
                    self.item.addItem(m.name, m.id)
            else:
                for name in self._sizes:
                    self.item.addItem(name, name)
        self.size.setEnabled(self.kind.currentText() == "Stone")
        self._fill_sizes()

    def _fill_sizes(self) -> None:
        if self.kind.currentText() != "Stone":
            self.size.clear()
            return
        rows = self._sizes.get(self.item.currentText(), [])
        self.size.clear()
        self.size.addItems([r[0] for r in rows])
        self.size.setCurrentText(rows[0][0] if len(rows) == 1 else "")

    def _ok(self) -> None:
        if self.src.currentData() == self.dst.currentData():
            QMessageBox.warning(self, "Stock Location Transfer", "From and To are the same.")
            return
        if self.wt.value() <= 0 and self.pcs.value() <= 0:
            QMessageBox.warning(self, "Stock Location Transfer", "Enter what is sent.")
            return
        if self.kind.currentText() == "Stone" and _pick_stone(
                self._sizes, self.item.currentText(), self.size.currentText()) is None:
            QMessageBox.warning(self, "Stock Location Transfer", "Pick the stone's size.")
            return
        self.accept()

    def lines(self) -> list[dict[str, Any]]:
        metal = self.kind.currentText() == "Metal"
        pane = "metal" if metal else "stone"
        base = {"pane": pane, "name": self.item.currentText(),
                "price": D(str(self.price.value())), "unit": "Gms" if metal else "Cts"}
        base.update({"metal_id": self.item.currentData()} if metal else
                    {"stone_sku_id": (hit := _pick_stone(self._sizes, self.item.currentText(),
                                                         self.size.currentText())) and hit[1],
                     "size": self.size.currentText().strip()})
        wt, lwt = D(str(round(self.wt.value(), 3))), D(str(round(self.loss_wt.value(), 3)))
        pcs, lpcs = self.pcs.value(), self.loss_pcs.value()
        out = {**base, "location_id": self.src.currentData(), "location": self.src.currentText(),
               "out_pcs": pcs, "out_wt": wt, "out_loss_pcs": lpcs, "out_loss_wt": lwt}
        inn = {**base, "location_id": self.dst.currentData(), "location": self.dst.currentText(),
               "in_pcs": pcs - lpcs, "in_wt": wt - lwt}
        for ln in (out, inn):
            ln["amount"] = ST.line_amount(ln)
        return [out, inn]


class StockTransferWidget(_Screen):

    def __init__(self, user=None, parent=None):
        super().__init__("Stock Transfer", with_picker=False, parent=parent)
        self.user = user
        self.header.hide()
        self.lines: list[dict] = []
        self._last_id: int | None = None
        self._edit_id: int | None = None     # the saved transfer being edited
        self.vr = QLabel("")
        self.vr.setObjectName("H2")
        self.date = QDateEdit(_qdate(None))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.contact = QLineEdit(getattr(user, "full_name", "") or "")
        self.contact.setPlaceholderText("Contact Person")
        self.ref = QLineEdit()
        self.ref.setPlaceholderText("Ref No")
        for w in (QLabel("Vr No"), self.vr, QLabel("Date"), self.date, QLabel("Contact"),
                  self.contact, self.ref):
            self.toolbar.addWidget(w)
        self.toolbar.addStretch(1)
        self.button("Add", self.new_voucher)
        self.button("Edit", self.edit_voucher)
        self.button("Save", self.save, primary=True)
        self.button("Delete", self.delete_voucher)
        for label, fn in (("Barcode", self.barcode), ("Stock Melting", self.stock_melting),
                          ("Stock Location Transfer", self.location_transfer),
                          ("Print 2", self.print_voucher),
                          ("Melting List", lambda: self._report("melting_list")),
                          ("Transfer Reg.", lambda: self._report("transfer_register")),
                          ("Exit", self.close_requested.emit)):
            self.button(label, fn, secondary=True)

        self.tabs = QTabWidget()
        self.grids = {}
        for pane, title in PANE_TITLES.items():
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(0, 6, 0, 0)
            bar = QHBoxLayout()
            if pane in ("metal", "stone"):
                b = QPushButton("Add Line")
                b.clicked.connect(lambda _c=False, p=pane: self.add_line(p))
                bar.addWidget(b)
            else:
                b = QPushButton("Show Stock")
                b.clicked.connect(lambda _c=False, p=pane: self.show_stock(p))
                bar.addWidget(b)
            r = QPushButton("Remove Line")
            r.clicked.connect(lambda _c=False, p=pane: self.remove_line(p))
            bar.addWidget(r)
            bar.addStretch(1)
            pl.addLayout(bar)
            g = _table([h for _k, h in PANE_COLS[pane]], ledger=True)
            auto_fit(g)
            pl.addWidget(g, 1)
            self.grids[pane] = g
            self.tabs.addTab(page, title)
        self.outer.addWidget(self.tabs, 1)
        self.narration = QLineEdit()
        self.narration.setPlaceholderText("Narration")
        self.outer.addWidget(self.narration)
        self.totals = QLabel("")
        self.outer.addWidget(self.totals)
        note = QLabel("Stock melting: a ready piece out (Ready Stock Outward) and its metal and "
                      "stones in. Location transfer: out of one location, into another. In / "
                      "Out move the location's stock; the loss columns are recorded for the "
                      "loss registers - how the client books these is to be confirmed (Q6).")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        self.outer.addWidget(note)
        self.refresh()

    def refresh(self) -> None:
        if self._edit_id is None:
            with SessionLocal() as s:
                self.vr.setText(str(ST.next_vr_no(s)))
        self._render()

    # -- lines -------------------------------------------------------------
    def _render(self) -> None:
        for pane, g in self.grids.items():
            rows = [l for l in self.lines if l["pane"] == pane]
            g.setRowCount(0)
            for ln in rows:
                r = g.rowCount()
                g.insertRow(r)
                for c, (k, _h) in enumerate(PANE_COLS[pane]):
                    v = ln.get(k)
                    if isinstance(v, Decimal):
                        v = f"{v:,.2f}" if k in ("price", "amount") else f"{v:.3f}"
                    g.setItem(r, c, _item(v if v not in (None, 0) else "",
                                          right=isinstance(ln.get(k), (int, Decimal))))
        counts = {p: sum(1 for l in self.lines if l["pane"] == p) for p in PANE_TITLES}
        for i, (p, title) in enumerate(PANE_TITLES.items()):
            self.tabs.setTabText(i, f"{title} ({counts[p]})" if counts[p] else title)
        self.totals.setText(" · ".join(f"{PANE_TITLES[p]} {n}" for p, n in counts.items() if n)
                            or "No lines yet.")

    def add_line(self, pane: str) -> None:
        dlg = LineDialog(pane, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.lines.append(dlg.values())
            self._render()

    def remove_line(self, pane: str) -> None:
        g = self.grids[pane]
        r = g.currentRow()
        rows = [l for l in self.lines if l["pane"] == pane]
        if not 0 <= r < len(rows):
            return
        ln = rows[r]
        melt = ln.get("_melt")
        if melt is not None:
            # A melted piece and the metal / stones it gave go together (19 Oct
            # meeting, item 4): removing any one of them removes the lot.
            group = [l for l in self.lines if l.get("_melt") == melt]
            if len(group) > 1 and QMessageBox.question(
                    self, "Remove Line",
                    f"This line is part of the melting of Stock {ln.get('stock_no') or melt}. "
                    f"Remove the piece and its {len(group) - 1} metal / stone line(s)?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.lines = [l for l in self.lines if l.get("_melt") != melt]
        else:
            self.lines.remove(ln)
        self._render()

    def _piece_line(self, pane: str, info: dict, to_loc: tuple[int, str] | None = None) -> dict:
        ln = {"pane": pane, "stock_item_id": info["stock_item_id"],
              "location_id": info["location_id"], "location": info["location"],
              "stock_no": info["stock_no"], "job_no": info["job_no"] or None,
              "sku": info["sku"], "metal": info["metal"], "colour": info["colour"],
              "size": info["size"], "gross_wt": info["gross_wt"], "out_pcs": info["pcs"],
              "out_wt": info["net_wt"], "price": info["cost"], "amount": info["cost"]}
        if to_loc:
            ln["to_location_id"], ln["to_location"] = to_loc
        return ln

    def _ask_to(self) -> tuple[int, str] | None:
        locs = _locations()
        name, ok = QInputDialog.getItem(self, "Ready Stock Transfer", "Move to location:",
                                        [n for _i, n in locs], 0, False)
        if not ok:
            return None
        return next((i, n) for i, n in locs if n == name)

    def show_stock(self, pane: str) -> None:
        from diagold.ui.ready_vouchers import PiecePicker
        have = {l.get("stock_item_id") for l in self.lines}
        with SessionLocal() as s:
            rows = [S.describe(s, i) for i in s.scalars(
                select(StockItem).where(StockItem.status == "in_stock")
                .order_by(StockItem.stock_no)) if i.id not in have]
        dlg = PiecePicker(rows, f"Show Stock — {PANE_TITLES[pane]}", self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.picked():
            return
        to = self._ask_to() if pane == "ready_transfer" else None
        if pane == "ready_transfer" and to is None:
            return
        for info in dlg.picked():
            self.lines.append(self._piece_line(pane, info, to))
        self._render()

    def barcode(self) -> None:
        """Barcode: read a Stock No into the pane on view (Ready Stock Outward or
        Ready Stock Transfer)."""
        pane = list(PANE_TITLES)[self.tabs.currentIndex()]
        if pane not in ("ready_out", "ready_transfer"):
            pane = "ready_out"
        text, ok = QInputDialog.getText(self, "Barcode", f"Stock No for {PANE_TITLES[pane]}:")
        if not ok or not text.strip():
            return
        with SessionLocal() as s:
            try:
                item = S.find_item(s, text)
                if item.status != "in_stock":
                    raise ProductionError(f"Stock No {item.stock_no} is not in stock.")
                info = S.describe(s, item)
            except ProductionError as exc:
                QMessageBox.warning(self, "Barcode", str(exc))
                return
        to = self._ask_to() if pane == "ready_transfer" else None
        if pane == "ready_transfer" and to is None:
            return
        self.lines.append(self._piece_line(pane, info, to))
        self._render()

    def stock_melting(self) -> None:
        """Stock Melting: a ready piece out, its metal and stones in."""
        text, ok = QInputDialog.getText(self, "Stock Melting", "Stock No of the piece to melt:")
        if not ok or not text.strip():
            return
        with SessionLocal() as s:
            try:
                item = S.find_item(s, text)
                if item.status != "in_stock":
                    raise ProductionError(f"Stock No {item.stock_no} is not in stock.")
                lines = ST.melting_lines(s, item, _pydate(self.date))
                info = S.describe(s, item)
            except ProductionError as exc:
                QMessageBox.warning(self, "Stock Melting", str(exc))
                return
        loc = info["location"]
        if any(l.get("_melt") == item.id for l in self.lines):
            QMessageBox.information(self, "Stock Melting",
                                    f"Stock {info['stock_no']} is already on this voucher.")
            return
        for ln in lines:
            ln.setdefault("location", loc)
            ln["_melt"] = item.id
            if ln["pane"] == "ready_out":
                ln.update({k: info[k] for k in ("stock_no", "sku", "metal", "colour", "size")})
        self.lines += lines
        self._render()
        self.tabs.setCurrentIndex(0)

    def location_transfer(self) -> None:
        dlg = LocationTransferDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.lines += dlg.lines()
            self._render()
            self.tabs.setCurrentIndex(2 if dlg.kind.currentText() == "Stone" else 1)

    # -- save / delete / print -----------------------------------------------
    def edit_voucher(self) -> None:
        """Edit (16 Nov): open a saved transfer; Save replaces it under the
        same Vr No."""
        tid = self._pick("Edit — pick the stock transfer")
        if tid is None:
            return
        with SessionLocal() as s:
            t = s.get(StockTransfer, tid)
            self.lines = ST.lines_of(s, t)
            self.vr.setText(f"{t.vr_no}  (editing)")
            self.date.setDate(_qdate(t.vr_date))
            self.contact.setText(t.contact_person or "")
            self.ref.setText(t.ref_no or "")
            self.narration.setText(t.remark or "")
        self._edit_id = tid
        self._render()
        first = next((i for i, p in enumerate(PANE_TITLES)
                      if any(l["pane"] == p for l in self.lines)), 0)
        self.tabs.setCurrentIndex(first)

    def new_voucher(self) -> None:
        self._edit_id = None
        self.lines = []
        self.narration.clear()
        self.ref.clear()
        self.refresh()

    def save(self) -> None:
        if not self.lines:
            QMessageBox.information(self, "Save", "Add lines to a pane first.")
            return
        off = ST.imbalance(self.lines)
        if off and QMessageBox.question(
                self, "Check before saving", "This transfer does not balance:\n"
                + "\n".join(off) + "\n\nSave anyway?") != QMessageBox.StandardButton.Yes:
            return
        if not confirm_save(self, f"stock transfer of {len(self.lines)} line(s)"):
            return
        head = {"vr_date": _pydate(self.date), "contact_person": self.contact.text().strip(),
                "ref_no": self.ref.text().strip(), "remark": self.narration.text().strip()}
        with SessionLocal() as s:
            try:
                uid = getattr(self.user, "id", None)
                if self._edit_id is not None:
                    old = s.get(StockTransfer, self._edit_id)
                    if old is None:
                        raise ProductionError("That stock transfer was deleted meanwhile.")
                    t = ST.edit(s, old, head, self.lines, user_id=uid)
                else:
                    t = ST.post(s, head, self.lines, user_id=uid)
                s.commit()
                tid, vr = t.id, t.vr_no
            except ProductionError as exc:
                s.rollback()
                QMessageBox.warning(self, "Cannot save", str(exc))
                return
        self.new_voucher()
        self._last_id = tid
        self.totals.setText(f"Saved Stock Transfer Vr {vr}. Print 2 prints it.")

    def _pick(self, title: str) -> int | None:
        with SessionLocal() as s:
            rows = [(t.id, f"Vr {t.vr_no}   {t.vr_date:%d-%m-%Y}   {t.contact_person}   "
                     f"{len(t.lines)} line(s)   {t.ref_no or ''}")
                    for t in s.scalars(select(StockTransfer).order_by(StockTransfer.vr_no.desc())
                                       .limit(300))]
        if not rows:
            QMessageBox.information(self, title, "No stock transfer has been saved yet.")
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(520, 360)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        for tid, text in rows:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, tid)
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

    def delete_voucher(self) -> None:
        tid = self._pick("Delete — pick the stock transfer")
        if tid is None:
            return
        if QMessageBox.question(self, "Delete", "Delete this stock transfer? Pieces go back "
                                "in stock where they were and the metal / stone movements "
                                "are reversed.") != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                ST.delete(s, s.get(StockTransfer, tid), user_id=getattr(self.user, "id", None))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                QMessageBox.warning(self, "Cannot delete", str(exc))
                return
        self.new_voucher()
        self.totals.setText("Stock transfer deleted.")

    def print_voucher(self) -> None:
        """Print 2: the voucher, pane by pane."""
        tid = self._last_id or self._pick("Print — pick the stock transfer")
        if tid is None:
            return
        from diagold.services import documents
        with SessionLocal() as s:
            t = s.get(StockTransfer, tid)
            rows = ST.register(s, t.vr_date, t.vr_date)
            rows = [r for r in rows if r["vrno"] == t.vr_no]
            vr, vd, who = t.vr_no, t.vr_date, t.contact_person
        body = "".join(
            f"<tr><td>{r['pane']}</td><td>{r['location']}</td><td>{r['to_location']}</td>"
            f"<td>{r['item']}</td><td>{r['size'] or ''}</td>"
            f"<td align=right>{r['in_pcs'] or ''}</td><td align=right>{r['in_wt'] or ''}</td>"
            f"<td align=right>{r['out_pcs'] or ''}</td><td align=right>{r['out_wt'] or ''}</td>"
            f"<td align=right>{r['in_loss_wt'] or r['out_loss_wt'] or ''}</td>"
            f"<td align=right>{r['amount'] or ''}</td></tr>" for r in rows)
        html = (f"<h2>Stock Transfer — Vr {vr} dt {vd:%d-%m-%Y}</h2><p>Contact {who}</p>"
                "<table border=1 cellspacing=0 cellpadding=3 width=100%><tr><th>Pane</th>"
                "<th>Location</th><th>To</th><th>Item</th><th>Size</th><th>In Pcs</th>"
                "<th>In Wt</th><th>Out Pcs</th><th>Out Wt</th><th>Loss</th><th>Amount</th></tr>"
                + body + "</table>")
        path = documents.PRINT_DIR / f"stock_transfer_{vr}_{datetime.now():%H%M%S}.pdf"
        documents.to_pdf(html, path)
        QMessageBox.information(self, "Print 2", f"Saved {path}")

    def _report(self, key: str) -> None:
        from diagold.ui.production import show_in_dialog
        from diagold.ui.reports import ReportWidget, build_specs
        show_in_dialog(self, ReportWidget(build_specs()[key]), build_specs()[key].title,
                       (1200, 700))
