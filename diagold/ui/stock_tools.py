"""Stock tools screens (5 Oct §4.8 / §4.14, T-09): Stock Reconciliation,
Ready Closing Stock, SKU Status, Stock View and Barcode Catalog."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFileDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QRadioButton, QTabWidget, QVBoxLayout, QWidget)
from sqlalchemy import select

from diagold.db.models import Location, ProductSku, StockItem, StockRecon
from diagold.db.session import SessionLocal
from diagold.services import stock_tools as ST
from diagold.ui.production import _Screen, _info, _warn
from diagold.ui.reports import Col, ReportSpec, ReportWidget, static


def _money(k, l):
    return Col(k, l, "measure", 2, total=True)


def _wt(k, l):
    return Col(k, l, "measure", 3, total=True)


def _pcs(k, l):
    return Col(k, l, "measure", 0, total=True)


PIECE_COLS = [Col("location", "Location"), Col("job_no", "Job No"), Col("sku", "SKU"),
              Col("metal", "Metal"), Col("size", "Size"), _pcs("pcs", "Pcs"),
              _wt("g_wt", "G-Wt"), _wt("n_wt", "N-Wt"), Col("barcode", "Barcode"),
              Col("status", "Status"), _money("amount", "Price")]


# --------------------------------------------------------------------------
# Catalog / Tag Print from any selection
# --------------------------------------------------------------------------
def catalog(widget: QWidget, rows: list[dict], small: bool = False) -> None:
    rows = [r for r in rows if r.get("stock_no")]
    if not rows:
        _info(widget, "Catalog", "No pieces to put in a catalog.")
        return
    from diagold.services import documents
    name = "catalog_4x8" if small else "catalog"
    path = documents.PRINT_DIR / f"{name}_{datetime.now():%Y%m%d-%H%M%S}.pdf"
    documents.to_pdf(ST.catalog_html(rows, "Catalog 4 x 8" if small else "Catalog",
                                     4 if small else 3, small), path)
    _info(widget, "Catalog", f"Saved {path}")


def tag_print(widget: QWidget, rows: list[dict]) -> None:
    ids = [r["_id"] for r in rows if r.get("_id")]
    if not ids:
        _info(widget, "Tag Print", "No pieces to print tags for.")
        return
    from diagold.ui.manufacturing import TagListDialog
    dlg = TagListDialog(None, widget)
    with SessionLocal() as s:
        dlg._add_items(s, [s.get(StockItem, i) for i in ids])
    dlg._fill()
    dlg.exec()


def image_folder(widget: QWidget, rows: list[dict]) -> None:
    folder = QFileDialog.getExistingDirectory(widget, "Create Image Folder")
    if folder:
        n = ST.create_image_folder(rows, folder)
        _info(widget, "Create Image Folder", f"{n} photo(s) copied to {folder}.")


def _sel(w: ReportWidget) -> list[dict]:
    return w.selected_rows()


STOCK_ACTIONS = [
    ("Catalog", "Ctrl+S", lambda w: catalog(w, _sel(w))),
    ("Catalog 4x8", "", lambda w: catalog(w, _sel(w), small=True)),
    ("Tag Print", "Ctrl+T", lambda w: tag_print(w, _sel(w))),
    ("Create Image Folder", "", lambda w: image_folder(w, _sel(w))),
]


def _sku_list(s) -> list[tuple[Any, str]]:
    return [("", "— choose a SKU —")] + [
        (c, c) for c in s.scalars(select(ProductSku.sku_code).order_by(ProductSku.sku_code))]


def specs() -> dict[str, ReportSpec]:
    return {
        "ready_closing_stock": ReportSpec(
            key="ready_closing_stock", title="Ready Closing Stock",
            columns=static([Col("location", "LOCATION"), Col("job_no", "JOB NO"),
                            Col("sku", "SKU"), Col("cf", "CF"), Col("category", "Category"),
                            Col("sub_category", "Sub-Category"), Col("family", "Family"),
                            Col("item", "Item"), Col("metal", "METAL"), Col("col", "COL"),
                            Col("size", "SIZE"), _pcs("pcs", "PCS"), _wt("g_wt", "G-WT"),
                            _wt("n_wt", "N-WT"), _wt("oth_wt", "OTH-WT"), _wt("fine", "FINE"),
                            _money("dia", "DIA"), _money("polki", "POL"), _money("cs", "CS"),
                            Col("mt_rate", "MT-RATE", "measure", 2), Col("price", "PRICE",
                                                                         "measure", 2),
                            _money("amount", "AMOUNT"), Col("tag", "TAG"),
                            Col("barcode", "BARCODE")]),
            query=lambda s, a, b, **_k: ST.ready_closing_stock(s, b), date_mode="to",
            group_by="location", filter_column="location", images=True,
            stone_group_cols=("dia", "polki", "cs"),
            on_activate=lambda w, r: w.open_job(r), actions=STOCK_ACTIONS,
            note="Every piece in ready stock on the date. MT-RATE = the day's rate per gram "
                 "of the piece's metal; PRICE per piece, AMOUNT = the piece's price; OTH-WT = "
                 "gross - net - stones (ct / 5). Select rows and Ctrl+S Catalog / Ctrl+T Tag "
                 "Print (nothing selected = every row shown); Shift+F12 photos; Ctrl+F1 DIA / POL / CS; "
                 "Ctrl+E Excel."),
        "sku_status": ReportSpec(
            key="sku_status", title="SKU Status",
            columns=static([Col("date", "DATE"), Col("vrtype", "VRTYPE"), Col("vrno", "VRNO"),
                            Col("particulars", "PARTICULARS"), Col("refno", "REFNO"),
                            Col("location", "LOCATION"), Col("job_no", "JOBNO"),
                            Col("barcode", "BARCODE"), Col("c_ref", "CREF"),
                            Col("item", "ITEM"), Col("metal", "METAL"), Col("col", "COLOR"),
                            Col("size", "SIZE"), _pcs("pcs", "PCS"), _wt("g_wt", "G-WT"),
                            _wt("n_wt", "N-WT"), _wt("st_wt", "ST-WT"),
                            Col("price", "PRICE", "measure", 2), Col("status", "STATUS")]),
            query=lambda s, a, b, sku="", **_k: ST.sku_status(s, sku), date_mode="none",
            pickers=[("sku", "SKU", _sku_list)], group_by="status", filter_column="status",
            images=True, on_activate=lambda w, r: w.open_job(r),
            note="Every piece ever made or bought of the SKU, on its latest voucher (MF made, "
                 "RS sold, RA approval, RSR returned, OPR opening …), and its jobs still in "
                 "manufacturing (MFG)."),
    }


# --------------------------------------------------------------------------
# Stock View
# --------------------------------------------------------------------------
class StockViewWidget(QWidget):
    """Filters on the left, the pieces on the shared report grid."""

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.user = user
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # The filters scroll on their own, so a 768-px-high laptop screen
        # shows all of them (6 Oct: the bottom was cut off).
        from PySide6.QtWidgets import QFrame, QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(300)
        panel = QWidget()
        scroll.setWidget(panel)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(12, 12, 4, 12)
        sbox = QGroupBox("Show")
        sl = QGridLayout(sbox)
        self.status: dict[str, QRadioButton] = {}
        for i, k in enumerate(ST.VIEW_STATUSES):
            rb = QRadioButton(k)
            self.status[k] = rb
            sl.addWidget(rb, i // 2, i % 2)
        self.status["In Stock"].setChecked(True)
        self.approval_no = QLineEdit()
        self.approval_no.setPlaceholderText("Approval No")
        sl.addWidget(self.approval_no, 2, 0, 1, 2)
        pl.addWidget(sbox)
        lbox = QGroupBox("Location")
        ll = QVBoxLayout(lbox)
        self.locations = QListWidget()
        self.locations.setMaximumHeight(130)
        with SessionLocal() as s:
            for loc in s.scalars(select(Location).order_by(Location.name)):
                it = QListWidgetItem(loc.name)
                it.setData(256, loc.id)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Unchecked)
                self.locations.addItem(it)
        ll.addWidget(self.locations)
        ll.addWidget(QLabel("None ticked = every location"))
        pl.addWidget(lbox)
        tabs = QTabWidget()
        self.stone: dict[str, QLineEdit] = {}
        self.other: dict[str, QLineEdit] = {}
        for title, keys, store in (
                ("Stone Info", [("ssku", "SSKU"), ("stone_group", "Stone Group / S-Type"),
                                ("shape", "Shape"), ("stone_type", "Type"),
                                ("quality", "Quality"), ("size", "Size")], self.stone),
                ("Other Info", [("sku", "SKU"), ("c_ref", "C Ref"), ("pattern", "Pattern"),
                                ("pattern2", "Pattern2"), ("category", "Category"),
                                ("sub_category", "Sub-Category"), ("style", "Style"),
                                ("sku_ref", "SKU Ref"), ("master_sku", "MasterSKU")],
                 self.other)):
            page = QWidget()
            g = QGridLayout(page)
            for r, (k, label) in enumerate(keys):
                g.addWidget(QLabel(label), r, 0)
                e = QLineEdit()
                e.returnPressed.connect(self._filter)
                store[k] = e
                g.addWidget(e, r, 1)
            tabs.addTab(page, title)
        pl.addWidget(tabs)
        dl = QHBoxLayout()
        self.use_date = QCheckBox("MF date")
        self.d0, self.d1 = QDateEdit(), QDateEdit()
        for d in (self.d0, self.d1):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yy")
            d.setDate(QDate.currentDate())
        self.d0.setDate(QDate(date.today().year, 4, 1))
        for w in (self.use_date, self.d0, self.d1):
            dl.addWidget(w)
        pl.addLayout(dl)
        fl = QHBoxLayout()
        self.cad, self.master = QCheckBox("CAD"), QCheckBox("Master")
        fl.addWidget(self.cad)
        fl.addWidget(self.master)
        pl.addLayout(fl)
        note = QLabel("Origin / Treatment / Creation, Finding / Process / Mould / Labour / V Ref "
                      "and the FTP / Not Checked flags are not kept on pieces yet (asked).")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        pl.addWidget(note)
        from PySide6.QtWidgets import QPushButton
        pl.addStretch(1)
        # Filter stays in sight above the scrolling filters.
        left = QWidget()
        left.setFixedWidth(300)
        ll2 = QVBoxLayout(left)
        ll2.setContentsMargins(0, 12, 0, 0)
        b = QPushButton("Filter")
        b.setObjectName("Primary")
        b.clicked.connect(self._filter)
        ll2.addWidget(b)
        ll2.addWidget(scroll, 1)
        lay.addWidget(left)
        spec = ReportSpec(
            key="stock_view", title="Stock View",
            columns=static([Col("location", "LOCATION"), Col("barcode", "STOCK NO"),
                            Col("sku", "SKU"), Col("job_no", "JOB NO"), Col("c_ref", "C REF"),
                            Col("category", "CATEGORY"), Col("item", "ITEM"),
                            Col("metal", "METAL"), Col("col", "COL"), Col("size", "SIZE"),
                            _pcs("pcs", "PCS"), _wt("g_wt", "G-WT"), _wt("n_wt", "N-WT"),
                            _wt("st_wt", "ST-WT"), _money("amount", "PRICE"), Col("tag", "TAG"),
                            Col("status", "STATUS"), Col("holder", "WITH")]),
            query=self._query, date_mode="none", group_by="location",
            filter_column="status", images=True, actions=STOCK_ACTIONS,
            on_activate=lambda w, r: w.open_job(r),
            note="Set the filters on the left and Filter. Select pieces for Catalog / Tag "
                 "Print / Create Image Folder (nothing selected = all shown); Excel from the "
                 "grid's export.")
        self.report = ReportWidget(spec, user, autorun=False)
        lay.addWidget(self.report, 1)
        self.open_requested = self.report.open_requested
        self._filter()

    @property
    def job_id(self) -> int | None:
        return self.report.job_id

    def _query(self, s, _a, _b, **_k) -> list[dict]:
        return ST.stock_view(s, **self._args)

    def _filter(self) -> None:
        locs = [self.locations.item(i).data(256) for i in range(self.locations.count())
                if self.locations.item(i).checkState() == Qt.CheckState.Checked]
        status = next(k for k, rb in self.status.items() if rb.isChecked())
        qd = lambda d: date(d.date().year(), d.date().month(), d.date().day())
        self._args = dict(
            status=status, location_ids=locs,
            stone={k: e.text() for k, e in self.stone.items()},
            other={k: e.text() for k, e in self.other.items()},
            date_from=qd(self.d0) if self.use_date.isChecked() else None,
            date_to=qd(self.d1) if self.use_date.isChecked() else None,
            cad=self.cad.isChecked(), master=self.master.isChecked(),
            approval_no=self.approval_no.text())
        self.report.run()


# --------------------------------------------------------------------------
# Stock Reconciliation
# --------------------------------------------------------------------------
PANELS = [("ok", "In Stock Show (scanned, in stock)"),
          ("missing", "Add Stock But Not Show In Stock (in stock, NOT scanned)"),
          ("unknown", "Data Unfound But In Reconciliation (scanned, not in stock here)")]


class StockReconWidget(_Screen):
    def __init__(self, user=None, parent=None):
        super().__init__("Stock Reconciliation", with_picker=False, parent=parent)
        self.header.hide()
        self.user = user
        self.recon_id: int | None = None
        self.toolbar.addWidget(QLabel("Count"))
        self.recons = QComboBox()
        self.recons.setMinimumWidth(240)
        self.recons.currentIndexChanged.connect(lambda _i: self._open())
        self.toolbar.addWidget(self.recons)
        self.toolbar.addWidget(QLabel("Location"))
        self.location = QComboBox()
        self.location.addItem("All locations", None)
        with SessionLocal() as s:
            for loc in s.scalars(select(Location).order_by(Location.name)):
                self.location.addItem(loc.name, loc.id)
        self.toolbar.addWidget(self.location)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.toolbar.addWidget(self.date)
        self.button("New Count", self._new, primary=True)
        self.toolbar.addStretch(1)
        self.button("Import TXT", self._import, secondary=True)
        self.button("Export To Excel", self._excel, secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)
        rd = QHBoxLayout()
        rd.addWidget(QLabel("Barcode Id"))
        self.reader = QLineEdit()
        self.reader.setPlaceholderText("Scan a barcode (Stock No) and Enter")
        self.reader.returnPressed.connect(self._scan)
        rd.addWidget(self.reader, 1)
        self.summary = QLabel("")
        rd.addWidget(self.summary)
        self.outer.addLayout(rd)
        self.tabs = QTabWidget()
        self.grids: dict[str, ReportWidget] = {}
        self._result: dict[str, list[dict]] = {"ok": [], "missing": [], "unknown": []}
        for key, title in PANELS:
            spec = ReportSpec(key=f"recon_{key}", title=title, columns=static(PIECE_COLS),
                              query=lambda _s, _a, _b, _k=key, **_kw: self._result[_k],
                              date_mode="none", group_by="location", actions=STOCK_ACTIONS)
            w = ReportWidget(spec, user, autorun=False)
            self.grids[key] = w
            self.tabs.addTab(w, title.split(" (")[0])
        self.outer.addWidget(self.tabs, 1)
        self._load_list()

    def _load_list(self, keep: int | None = None) -> None:
        self.recons.blockSignals(True)
        self.recons.clear()
        with SessionLocal() as s:
            for r in s.scalars(select(StockRecon).order_by(StockRecon.recon_no.desc())):
                loc = s.get(Location, r.location_id) if r.location_id else None
                self.recons.addItem(f"#{r.recon_no} · {r.recon_date:%d-%m-%Y} · "
                                    f"{loc.name if loc else 'All'} · {len(r.scans)} scanned", r.id)
        self.recons.blockSignals(False)
        i = self.recons.findData(keep) if keep else 0
        self.recons.setCurrentIndex(max(i, 0))
        self._open()

    def _new(self) -> None:
        d = self.date.date()
        with SessionLocal() as s:
            r = ST.new_recon(s, date(d.year(), d.month(), d.day()), self.location.currentData(),
                             user_id=getattr(self.user, "id", None))
            s.commit()
            rid = r.id
        self._load_list(rid)
        self.reader.setFocus()

    def _open(self) -> None:
        self.recon_id = self.recons.currentData()
        self._refresh()

    def _add(self, codes: list[str]) -> tuple[int, int]:
        if self.recon_id is None:
            self._new()
        with SessionLocal() as s:
            r = s.get(StockRecon, self.recon_id)
            res = ST.add_scans(s, r, codes)
            s.commit()
        self._refresh()
        return res

    def _scan(self) -> None:
        code = self.reader.text().strip()
        self.reader.clear()
        if code:
            _added, dup = self._add([code])
            if dup:
                self.summary.setText(self.summary.text() + f"   ({code} already scanned)")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import TXT", "",
                                              "Text (*.txt *.csv);;All files (*)")
        if not path:
            return
        with open(path, encoding="utf-8", errors="ignore") as fh:
            codes = [str(n) for n in ST.numbers_in(fh.read())]
        added, dup = self._add(codes)
        _info(self, "Import TXT", f"{added} barcode(s) added, {dup} already scanned.")

    def _refresh(self) -> None:
        with SessionLocal() as s:
            r = s.get(StockRecon, self.recon_id) if self.recon_id else None
            self._result = ST.reconcile(s, r) if r else {"ok": [], "missing": [], "unknown": []}
            n = len(r.scans) if r else 0
        for k, w in self.grids.items():
            w.run()
        ok, miss, unk = (len(self._result[k]) for k in ("ok", "missing", "unknown"))
        self.summary.setText(f"Scanned {n} · OK {ok} · Missing {miss} · Not in stock {unk}")
        for i, (k, title) in enumerate(PANELS):
            self.tabs.setTabText(i, f"{title.split(' (')[0]} ({len(self._result[k])})")
        ri = self.recons.currentIndex()
        if ri >= 0 and self.recon_id:
            t = self.recons.itemText(ri).rsplit(" · ", 1)[0]
            self.recons.setItemText(ri, f"{t} · {n} scanned")

    def _excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export To Excel", "reconciliation.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        for key, title in PANELS:
            ws = wb.create_sheet(title.split(" (")[0][:31])
            ws.append([c.label for c in PIECE_COLS])
            for r in self._result[key]:
                ws.append([(float(r[c.key]) if hasattr(r.get(c.key), "is_finite")
                            else r.get(c.key)) for c in PIECE_COLS])
        wb.save(path)
        _info(self, "Export To Excel", f"Saved {path}")


# --------------------------------------------------------------------------
# Barcode Catalog
# --------------------------------------------------------------------------
class BarcodeCatalogWidget(_Screen):
    def __init__(self, user=None, parent=None):
        super().__init__("Barcode Catalog", with_picker=False, parent=parent)
        self.header.hide()
        self.user = user
        self.by = QComboBox()
        for k, label in (("stock", "Stock ID"), ("job", "Job No"), ("sku", "SKU")):
            self.by.addItem(label, k)
        self.toolbar.addWidget(QLabel("By"))
        self.toolbar.addWidget(self.by)
        self.value = QLineEdit()
        self.value.setPlaceholderText("Enter Value (several: comma / space) and Enter")
        self.value.returnPressed.connect(self._enter)
        self.toolbar.addWidget(self.value, 1)
        self.button("Import TXT", self._import)
        self.button("Delete", self._delete, secondary=True)
        self.button("Clear", self._clear, secondary=True)
        self.button("Exit", self.close_requested.emit, secondary=True)
        self._ids: list[int] = []
        spec = ReportSpec(key="barcode_catalog", title="Pieces", columns=static(PIECE_COLS),
                          query=self._query, date_mode="none", images=True,
                          actions=STOCK_ACTIONS,
                          note="Add pieces by Stock ID, Job No or SKU (or a scanner TXT), "
                               "then Catalog, Catalog 4x8, Tag Print (TagPrint) or Excel "
                               "(Export).")
        self.report = ReportWidget(spec, user, autorun=False)
        self.outer.addWidget(self.report, 1)

    def _query(self, s, _a, _b, **_k):
        c = ST._Cache(s)
        return [ST.piece_row(s, s.get(StockItem, i), c) for i in self._ids]

    def add(self, by: str, values: list[str]) -> int:
        with SessionLocal() as s:
            found = ST.find_pieces(s, by, values)
            new = [i.id for i in found if i.id not in self._ids]
        self._ids += new
        self.report.run()
        return len(new)

    def _enter(self) -> None:
        vals = [v for v in self.value.text().replace(",", " ").split() if v]
        self.value.clear()
        if vals and not self.add(self.by.currentData(), vals):
            _warn(self, "Barcode Catalog", "Item not found: " + ", ".join(vals))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import TXT", "",
                                              "Text (*.txt *.csv);;All files (*)")
        if not path:
            return
        with open(path, encoding="utf-8", errors="ignore") as fh:
            vals = fh.read().replace(",", " ").split()
        n = self.add(self.by.currentData(), vals)
        _info(self, "Import TXT", f"{n} piece(s) added.")

    def _delete(self) -> None:
        drop = {r["_id"] for r in self.report.selected_rows(all_if_none=False)}
        self._ids = [i for i in self._ids if i not in drop]
        self.report.run()

    def _clear(self) -> None:
        self._ids = []
        self.report.run()
