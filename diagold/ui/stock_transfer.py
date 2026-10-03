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
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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
from sqlalchemy import select

from diagold.db.models import Location, Metal, StockItem, StockTransfer, StoneSku
from diagold.db.session import SessionLocal
from diagold.services import sales as S
from diagold.services import stock_transfer as ST
from diagold.services.production import ProductionError
from diagold.ui.confirm import confirm_save
from diagold.ui.crud import auto_fit
from diagold.ui.production import _Screen, _item, _pydate, _qdate, _table

D = Decimal
PANE_TITLES = {"ready_out": "Ready Stock Outward", "metal": "Metal", "stone": "Stone",
               "ready_transfer": "Ready Stock Transfer"}
PANE_COLS: dict[str, list[tuple[str, str]]] = {
    "ready_out": [("location", "Location"), ("stock_no", "Barcode"), ("job_no", "JobNo"),
                  ("sku", "SKU"), ("metal", "Metal"), ("colour", "Col"), ("size", "Size"),
                  ("gross_wt", "GrossWt"), ("out_pcs", "Pcs"), ("out_wt", "Weight"),
                  ("price", "Price"), ("amount", "Amount"), ("remark", "Remark")],
    "metal": [("location", "Location"), ("mt_type", "MtType"), ("name", "Metal"),
              ("colour", "Col"), ("in_pcs", "In-Pcs"), ("in_wt", "In-Wt"),
              ("in_loss_wt", "In-Loss"), ("out_pcs", "Out-Pcs"), ("out_wt", "Out-Wt"),
              ("out_loss_wt", "Out-Loss"), ("price", "Price"), ("unit", "Unit"),
              ("amount", "Amount"), ("job_no", "JobNo")],
    "stone": [("location", "Location"), ("s_type", "StType"), ("name", "SSKU"), ("size", "Size"),
              ("in_pcs", "In-Pcs"), ("in_wt", "In-Wt"), ("in_loss_pcs", "In-LossPcs"),
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
        form = QFormLayout()
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
                for k in s.scalars(select(StoneSku).order_by(StoneSku.sku_code)):
                    self.item.addItem(k.sku_code, (k.id, k.size or "", k.stone_type or "",
                                                   str(k.cost_price or 0)))
        self.item.currentIndexChanged.connect(lambda _i: self._item_changed())
        self.mt_type, self.colour = QLineEdit("Actual"), QLineEdit("Y")
        self.size, self.s_type = QLineEdit(), QLineEdit()
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
        form.addRow("Location", self.loc)
        if pane == "metal":
            form.addRow("MtType", self.mt_type)
            form.addRow("Metal", self.item)
            form.addRow("Col", self.colour)
        else:
            form.addRow("SSKU", self.item)
            form.addRow("StType", self.s_type)
            form.addRow("Size", self.size)
        for label, w in (("In-Pcs", self.in_pcs), ("In-Wt", self.in_wt),
                         ("In-Loss Pcs", self.in_loss_pcs), ("In-Loss Wt", self.in_loss_wt),
                         ("Out-Pcs", self.out_pcs), ("Out-Wt", self.out_wt),
                         ("Out-Loss Pcs", self.out_loss_pcs), ("Out-Loss Wt", self.out_loss_wt),
                         ("Price", self.price), ("Unit", self.unit), ("JobNo", self.job_no),
                         ("Remark", self.remark)):
            if self.pane == "metal" and "Loss Pcs" in label:
                continue
            form.addRow(label, w)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._item_changed()

    def _item_changed(self) -> None:
        if self.pane == "stone" and isinstance(self.item.currentData(), tuple):
            _id, size, st, price = self.item.currentData()
            self.size.setText(size)
            self.s_type.setText(st)
            self.price.setValue(float(price))

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
        if self.pane == "metal":
            v.update(metal_id=self.item.currentData(), mt_type=self.mt_type.text().strip(),
                     colour=self.colour.text().strip())
        else:
            data = self.item.currentData()
            v.update(stone_sku_id=data[0] if isinstance(data, tuple) else None,
                     particulars="" if isinstance(data, tuple) else self.item.currentText(),
                     size=self.size.text().strip(), s_type=self.s_type.text().strip())
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
        self.size = QLineEdit()
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
                for k in s.scalars(select(StoneSku).order_by(StoneSku.sku_code)):
                    self.item.addItem(k.sku_code, k.id)
        self.size.setEnabled(self.kind.currentText() == "Stone")

    def _ok(self) -> None:
        if self.src.currentData() == self.dst.currentData():
            QMessageBox.warning(self, "Stock Location Transfer", "From and To are the same.")
            return
        if self.wt.value() <= 0 and self.pcs.value() <= 0:
            QMessageBox.warning(self, "Stock Location Transfer", "Enter what is sent.")
            return
        self.accept()

    def lines(self) -> list[dict[str, Any]]:
        metal = self.kind.currentText() == "Metal"
        pane = "metal" if metal else "stone"
        base = {"pane": pane, "name": self.item.currentText(),
                "price": D(str(self.price.value())), "unit": "Gms" if metal else "Cts"}
        base.update({"metal_id": self.item.currentData()} if metal else
                    {"stone_sku_id": self.item.currentData(), "size": self.size.text().strip()})
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
        if 0 <= r < len(rows):
            self.lines.remove(rows[r])
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
        for ln in lines:
            ln.setdefault("location", loc)
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
    def new_voucher(self) -> None:
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
                t = ST.post(s, head, self.lines, user_id=getattr(self.user, "id", None))
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
        self.totals.setText("Stock transfer deleted.")
        self.refresh()

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
