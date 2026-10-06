"""Tools ▸ Client Wise Labour / Stone / Setting Price (5 Oct §4.7, T-05).

The legacy "Labour Price Type List": the charts (price types) on the left,
the chosen chart's rules on the right. Add / Edit / Save / Delete / Make A
Copy / Set Priority as in the legacy screen; a blank match cell matches
anything, and the rule nearer the top wins.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)
from sqlalchemy import select

from diagold.db.models import PriceChart, SettingType, StoneSku
from diagold.db.session import SessionLocal
from diagold.services import price_charts as PC
from diagold.ui.confirm import confirm_save
from diagold.ui.production import _Screen, _info, _warn

# (field, header, numeric)
COLUMNS: dict[str, list[tuple[str, str, bool]]] = {
    "labour": [("family", "Family", False), ("style", "Style", False), ("sku", "SKU", False),
               ("item", "Item", False), ("metal", "Metal", False), ("colour", "Color", False),
               ("labour", "Labour", False), ("from_gwt", "From G-Wt", True),
               ("to_gwt", "To G-Wt", True), ("sale_price", "SalePrice", True),
               ("per_unit", "Per Unit", False), ("cost_price", "CostPrice", True)],
    "stone": [("family", "Family", False), ("metal", "Metal", False), ("style", "Style", False),
              ("sku", "SKU", False), ("stone_group", "Stone Group", False),
              ("ssku", "SSKU", False), ("stone", "Stone", False), ("shape", "Shape", False),
              ("stone_type", "Type", False), ("quality", "Quality", False),
              ("size", "Size", False), ("price", "Price", True), ("unit", "Unit", False),
              ("cost_price", "Cost Price", True)],
    "setting": [("setting_type", "Setting Type", False), ("stone_group", "Stone Group", False),
                ("size", "Size", False), ("price", "Price / Pc", True)],
}
TITLES = {"labour": "Client Wise Labour Price", "stone": "Client Wise Stone Price",
          "setting": "Client Wise Setting Price"}
NOTES = {
    "labour": "Labour Price Type List. Per Grm Price is the chart's labour when no rule "
              "matches (MANNU BHAI = 1,175 / gm). A rule: blank cells match anything, G-Wt "
              "slab From .. To (To 0 = no limit), SalePrice per gm or pc (Per Unit). The "
              "rule nearer the top wins - Move Up / Down then Set Priority.",
    "stone": "Stone prices for this chart. Fill Stones lists every stone SKU at its standard "
             "sale price to edit. A stone with no rule keeps its standard price.",
    "setting": "Setting price per piece, by setting type (the stone's S Type: Diamond / Polki "
               "/ Colour Stone …), stone group and size. Setting amount = pcs x price.",
}


def _num(text: str) -> Decimal:
    try:
        return Decimal((text or "0").replace(",", "").strip() or "0")
    except InvalidOperation:
        raise PC.PriceChartError(f"Not a number: {text}") from None


class PriceChartWidget(_Screen):
    def __init__(self, kind: str, user=None, parent=None):
        super().__init__(TITLES[kind], with_picker=False, parent=parent)
        self.header.hide()
        self.kind, self.user = kind, user
        self.cols = COLUMNS[kind]
        self.chart_id: int | None = None
        self.button("Add", self._add, primary=True)
        self.btn_edit = self.button("Edit", self._edit)
        self.button("Save", self._save)
        self.button("Delete", self._delete)
        self.button("Make A Copy", self._copy)
        self.button("Set Priority", self._priority)
        self.toolbar.addStretch(1)
        self.button("Add Row", self._add_row, secondary=True)
        self.button("Delete Row", self._del_row, secondary=True)
        self.button("Move Up", lambda: self._move(-1), secondary=True)
        self.button("Move Down", lambda: self._move(1), secondary=True)
        if kind == "stone":
            self.button("Fill Stones", self._fill_stones, secondary=True)
            self.button("Import Excel", self._import_excel, secondary=True)
            self.button("Export Excel", self._export_excel, secondary=True)
        if kind == "setting":
            self.button("Fill Setting Types", self._fill_settings, secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)

        split = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Price Types"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda cur, _prev: self._open(cur))
        ll.addWidget(self.list, 1)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        form = QHBoxLayout()
        form.addWidget(QLabel("Name"))
        self.name = QLineEdit()
        form.addWidget(self.name, 1)
        self.per_gm = QDoubleSpinBox()
        self.per_gm.setRange(0, 10_000_000)
        self.per_gm.setDecimals(2)
        self.price_type = QLineEdit()
        self.quality = QLineEdit()
        if kind == "labour":
            form.addWidget(QLabel("Per Grm Price"))
            form.addWidget(self.per_gm)
        elif kind == "stone":
            form.addWidget(QLabel("Price Type"))
            form.addWidget(self.price_type)
            form.addWidget(QLabel("Stone Quality"))
            form.addWidget(self.quality)
        rl.addLayout(form)
        self.clients = QLabel("")
        self.clients.setObjectName("Muted")
        self.clients.setWordWrap(True)
        rl.addWidget(self.clients)
        self.grid = QTableWidget(0, len(self.cols) + 1)
        self.grid.setHorizontalHeaderLabels(["Sno"] + [h for _f, h, _n in self.cols])
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.grid.horizontalHeader().setStretchLastSection(True)
        self.grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        rl.addWidget(self.grid, 1)
        note = QLabel(NOTES[kind])
        note.setObjectName("Muted")
        note.setWordWrap(True)
        rl.addWidget(note)
        split.addWidget(right)
        split.setSizes([220, 900])
        self.outer.addWidget(split, 1)
        self._set_editing(False)
        self.refresh()

    # -- list ---------------------------------------------------------------
    def refresh(self) -> None:
        keep = self.chart_id
        self.list.blockSignals(True)
        self.list.clear()
        with SessionLocal() as s:
            for c in s.scalars(select(PriceChart).order_by(PriceChart.name)):
                it = QListWidgetItem(c.name)
                it.setData(256, c.id)
                self.list.addItem(it)
        self.list.blockSignals(False)
        for i in range(self.list.count()):
            if self.list.item(i).data(256) == keep:
                self.list.setCurrentRow(i)
                return
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._open(None)

    def _open(self, it: QListWidgetItem | None) -> None:
        self.chart_id = it.data(256) if it is not None else None
        self.grid.setRowCount(0)
        with SessionLocal() as s:
            c = s.get(PriceChart, self.chart_id) if self.chart_id else None
            self.name.setText(c.name if c else "")
            self.per_gm.setValue(float(c.labour_per_gm or 0) if c else 0)
            self.price_type.setText(c.price_type if c else "")
            self.quality.setText(c.stone_quality if c else "")
            names = PC.clients_on(s, c) if c else []
            self.clients.setText(("Clients on this chart: " + ", ".join(names)) if names else
                                 "No client is on this chart yet - pick it in Masters ▸ "
                                 "Account ▸ Price Chart.")
            rules = getattr(c, PC.RULE_ATTR[self.kind]) if c else []
            for r in rules:
                self._append({f: getattr(r, f) for f, _h, _n in self.cols})
        self._set_editing(False)

    # -- grid ---------------------------------------------------------------
    def _append(self, values: dict[str, Any]) -> None:
        r = self.grid.rowCount()
        self.grid.insertRow(r)
        sno = QTableWidgetItem(str(r + 1))
        sno.setFlags(sno.flags() & ~sno.flags().ItemIsEditable)
        self.grid.setItem(r, 0, sno)
        for c, (f, _h, num) in enumerate(self.cols, 1):
            v = values.get(f)
            text = "" if v in (None, "") else (f"{Decimal(str(v)):g}" if num else str(v))
            if num and text == "0":
                text = ""
            self.grid.setItem(r, c, QTableWidgetItem(text))

    def _renumber(self) -> None:
        for r in range(self.grid.rowCount()):
            self.grid.item(r, 0).setText(str(r + 1))

    def _rows(self) -> list[dict[str, Any]]:
        out = []
        for r in range(self.grid.rowCount()):
            row: dict[str, Any] = {}
            for c, (f, h, num) in enumerate(self.cols, 1):
                it = self.grid.item(r, c)
                text = it.text().strip() if it else ""
                row[f] = _num(text) if num else text
            if self.kind == "labour":
                row["per_unit"] = "pc" if row["per_unit"].lower().startswith("p") else "gm"
            if self.kind == "stone":
                row["unit"] = "pc" if row["unit"].lower().startswith("p") else "ct"
            out.append(row)
        return out

    def _set_editing(self, on: bool) -> None:
        self._editing = on
        trig = (QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
                | QAbstractItemView.EditTrigger.AnyKeyPressed) if on else \
            QAbstractItemView.EditTrigger.NoEditTriggers
        self.grid.setEditTriggers(trig)
        for w in (self.name, self.price_type, self.quality):
            w.setReadOnly(not on)
        self.per_gm.setReadOnly(not on)
        self.btn_edit.setText("Editing…" if on else "Edit")

    def _need_edit(self) -> bool:
        if self.chart_id is None:
            _info(self, TITLES[self.kind], "Add or choose a price type first.")
            return False
        if not self._editing:
            self._set_editing(True)
        return True

    def _add_row(self) -> None:
        if self._need_edit():
            self._append({"per_unit": "gm", "unit": "ct"})
            self.grid.setCurrentCell(self.grid.rowCount() - 1, 1)

    def _del_row(self) -> None:
        r = self.grid.currentRow()
        if r >= 0 and self._need_edit():
            self.grid.removeRow(r)
            self._renumber()

    def _move(self, step: int) -> None:
        r = self.grid.currentRow()
        t = r + step
        if r < 0 or not 0 <= t < self.grid.rowCount() or not self._need_edit():
            return
        for c in range(1, self.grid.columnCount()):
            a, b = self.grid.takeItem(r, c), self.grid.takeItem(t, c)
            self.grid.setItem(r, c, b)
            self.grid.setItem(t, c, a)
        self.grid.selectRow(t)

    def _fill_stones(self) -> None:
        if not self._need_edit():
            return
        have = {self.grid.item(r, 6).text() for r in range(self.grid.rowCount())
                if self.grid.item(r, 6)}
        with SessionLocal() as s:
            for k in s.scalars(select(StoneSku).where(StoneSku.is_active.is_(True))
                               .order_by(StoneSku.sku_code)):
                if k.sku_code in have:
                    continue
                self._append({"ssku": k.sku_code, "stone": k.stone, "shape": k.shape,
                              "stone_type": k.stone_type, "quality": k.quality, "size": k.size,
                              "price": k.sale_price,
                              "unit": "pc" if (k.per or "").lower().startswith("p") else "ct",
                              "cost_price": k.cost_price})

    def _import_excel(self) -> None:
        """The legacy grid exported to Excel (Family … SSKU, Size, Price, Unit,
        CostPrice) replaces this chart's stone prices."""
        if self.chart_id is None:
            _info(self, "Import Excel", "Add or choose a price type first.")
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Import stone prices", "",
                                              "Excel (*.xlsx)")
        if not path:
            return
        if QMessageBox.question(self, "Import Excel",
                                f"Replace the stone prices of {self.name.text()} with the "
                                "sheet's rows?") != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                n, notes = PC.import_stone_excel(s, s.get(PriceChart, self.chart_id), path)
                s.commit()
            except (PC.PriceChartError, ValueError, KeyError) as exc:
                _warn(self, "Import Excel", str(exc))
                return
        self.refresh()
        _info(self, "Import Excel", f"{n} stone price(s) imported." +
              ("\n" + "\n".join(notes) if notes else ""))

    def _export_excel(self) -> None:
        if self.chart_id is None:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export stone prices",
                                              f"stone price {self.name.text()}.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        with SessionLocal() as s:
            PC.export_stone_excel(s.get(PriceChart, self.chart_id), path)
        _info(self, "Export Excel", f"Saved {path}")

    def _fill_settings(self) -> None:
        if not self._need_edit():
            return
        with SessionLocal() as s:
            for t in s.scalars(select(SettingType).order_by(SettingType.name)):
                self._append({"setting_type": t.name})

    # -- chart --------------------------------------------------------------
    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "Add", "Name of the new price type")
        if not ok or not name.strip():
            return
        with SessionLocal() as s:
            if s.scalar(select(PriceChart).where(PriceChart.name == name.strip())):
                _warn(self, "Add", f"{name.strip()} already exists.")
                return
            c = PriceChart(name=name.strip())
            s.add(c)
            s.commit()
            self.chart_id = c.id
        self.refresh()
        self._set_editing(True)

    def _edit(self) -> None:
        if self.chart_id is not None:
            self._set_editing(True)

    def _save(self) -> None:
        if self.chart_id is None:
            return
        try:
            rows = self._rows()
        except PC.PriceChartError as exc:
            _warn(self, "Save", str(exc))
            return
        if not self.name.text().strip():
            _warn(self, "Save", "The name cannot be empty.")
            return
        if not confirm_save(self, "the price chart"):
            return
        with SessionLocal() as s:
            c = s.get(PriceChart, self.chart_id)
            other = s.scalar(select(PriceChart).where(PriceChart.name == self.name.text().strip(),
                                                      PriceChart.id != c.id))
            if other is not None:
                _warn(self, "Save", f"{other.name} already exists.")
                return
            c.name = self.name.text().strip()
            if self.kind == "labour":
                c.labour_per_gm = Decimal(str(self.per_gm.value()))
            if self.kind == "stone":
                c.price_type = self.price_type.text().strip()
                c.stone_quality = self.quality.text().strip()
            PC.save_rules(s, c, self.kind, rows)
            s.commit()
        self.refresh()

    def _delete(self) -> None:
        if self.chart_id is None:
            return
        if QMessageBox.question(self, "Delete", f"Delete the price type "
                                f"{self.name.text()} and all its rules?") \
                != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                PC.delete_chart(s, s.get(PriceChart, self.chart_id))
                s.commit()
            except PC.PriceChartError as exc:
                _warn(self, "Delete", str(exc))
                return
        self.chart_id = None
        self.refresh()

    def _copy(self) -> None:
        if self.chart_id is None:
            return
        name, ok = QInputDialog.getText(self, "Make A Copy",
                                        f"Copy {self.name.text()} (every rule) as")
        if not ok:
            return
        with SessionLocal() as s:
            try:
                new = PC.copy_chart(s, s.get(PriceChart, self.chart_id), name)
                s.commit()
            except PC.PriceChartError as exc:
                _warn(self, "Make A Copy", str(exc))
                return
            self.chart_id = new.id
        self.refresh()

    def _priority(self) -> None:
        """Set Priority: the rows' order as it stands becomes the priority."""
        if self.chart_id is None:
            return
        self._renumber()
        self._save()
