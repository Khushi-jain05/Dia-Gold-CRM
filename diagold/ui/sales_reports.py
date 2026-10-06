"""Sales registers and the Sales Dashboard (5 Oct §4.12 / §4.16, T-13)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFileDialog, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from diagold.db.session import SessionLocal
from diagold.services import reports as R
from diagold.services import sales_reports as SR
from diagold.ui.charts import BarChart
from diagold.ui.production import _info
from diagold.ui.reports import Col, ReportSpec, static


def _m(k, l):
    return Col(k, l, "measure", 2, total=True)


def _w(k, l):
    return Col(k, l, "measure", 3, total=True)


def _p(k, l):
    return Col(k, l, "measure", 0, total=True)


STONE_COLS = (("dia", "DIA"), ("polki", "POL"), ("cs", "CS"))


def _catalog(widget, rows) -> None:
    from diagold.ui.stock_tools import catalog
    catalog(widget, rows)


def specs() -> dict[str, ReportSpec]:
    open_job = lambda w, r: w.open_job(r)                       # noqa: E731
    stone = [_m(k, l) for k, l in STONE_COLS]
    return {
        "sales_register": ReportSpec(
            key="sales_register", title="Sales Register",
            columns=static([Col("location", "LOCATION"), Col("date", "DATE"),
                            Col("vrno", "VRNO"), Col("acc_code", "A/C ID"),
                            Col("particulars", "PARTICULARS"),
                            Col("sku", "SKU"), Col("metal", "METAL"), Col("job_no", "JOBNO"),
                            _p("pcs", "PCS"), _w("g_wt", "GROSS WT"), _w("n_wt", "NET WT"),
                            _w("fine_wt", "FINE WT"), Col("metal_rate", "METAL RATE",
                                                          "measure", 2),
                            _m("mt_total", "MT TOTAL"), _m("st_total", "ST TOTAL"), *stone,
                            _m("total", "TOTAL"), Col("tag_price", "TAGPRICE"),
                            Col("ref_no", "REFNO"), Col("snap", "SNAP"),
                            Col("repair", "REPAIR"), Col("ret", "RETURN")]),
            query=lambda s, a, b, **_k: SR.sales_register(s, a, b),
            group_by="particulars", filter_column="particulars", images=True,
            stone_group_cols=tuple(k for k, _l in STONE_COLS), on_activate=open_job,
            toggle_cols=[("F9", "A/c Ids", ("acc_code",))],
            actions=[("Catalog", "Ctrl+C", lambda w: _catalog(w, w.selected_rows()))],
            note="Every piece sold. REPAIR = the piece was ever issued for repair; RETURN = "
                 "it came back on a sale return. Ctrl+F1 DIA / POL / CS, Shift+F12 photos, Ctrl+C "
                 "Catalog of the selected pieces, F9 A/c Ids, Ctrl+E Excel."),
        "sales_return_register": ReportSpec(
            key="sales_return_register", title="Sales Return Register",
            columns=static([Col("location", "LOCATION"), Col("date", "DATE"),
                            Col("vrno", "VRNO"), Col("ref_no", "REFNO"),
                            Col("vrtype", "VR TYPE"), Col("particulars", "PARTICULARS"),
                            Col("acc_group", "GROUP"), Col("design", "DESIGN"),
                            Col("sku", "SKU"), Col("family", "Family"), Col("c_ref", "CREF"),
                            Col("metal", "METAL"), Col("item", "Item"),
                            Col("sub_item", "SUB-ITEM"), Col("job_no", "JOBNO"),
                            _p("pcs", "PCS"), _w("g_wt", "GROSS WT"), _w("n_wt", "NET WT"),
                            _w("sec_wt", "SEC WT"), _m("mt_total", "MT TOTAL"), *stone,
                            _m("total", "TOTAL")]),
            query=lambda s, a, b, **_k: SR.sales_return_register(s, a, b),
            group_by="particulars", filter_column="acc_group", images=True,
            stone_group_cols=tuple(k for k, _l in STONE_COLS), on_activate=open_job,
            note="Every piece a client returned (SR). SEC WT = the stones' weight."),
        "sales_profit": ReportSpec(
            key="sales_profit", title="Sales Profit Analysis",
            columns=static([Col("date", "DATE"), Col("vrno", "VRNO"),
                            Col("particulars", "PARTICULARS"), Col("barcode", "STOCK ID"),
                            Col("sku", "SKU"), _p("pcs", "PCS"), _w("n_wt", "NET WT"),
                            _m("sale_amt", "SALE AMT"), _m("cost_amt", "COST AMT"),
                            _m("profit", "PROFIT"), Col("profit_pct", "PROFIT %", "measure", 2),
                            Col("ret", "RETURN")]),
            query=lambda s, a, b, **_k: SR.sales_profit(s, a, b), negative_key="_negative",
            group_by="particulars", filter_column="particulars", on_activate=open_job,
            note="Each piece sold: its sale amount against its cost (the cost on the piece "
                 "from MFG transfer or purchase). Loss-making sales in red."),
        "purchase_sales": ReportSpec(
            key="purchase_sales", title="Purchase - Sales Analysis",
            columns=static([Col("pur_date", "PUR DATE"), Col("pur_vrno", "PUR VRNO"),
                            Col("pur_from", "PUR FROM"), Col("sku", "SKU"),
                            _m("cost_price", "COST PRICE"), _m("net_price", "NET PRICE"),
                            Col("tag", "TAG"), _w("g_wt", "G-WT"), _w("n_wt", "N-WT"),
                            Col("sale_date", "SALE DATE"), Col("sale_to", "SALE TO"),
                            _m("sale_price", "SALE PRICE"), _m("profit", "PROFIT"),
                            Col("profit_pct", "PROFIT %", "measure", 2),
                            Col("days", "DAYS", "measure", 0), Col("stock_id", "STOCK ID")]),
            query=lambda s, a, b, **_k: SR.purchase_sales(s, a, b), negative_key="_negative",
            group_by="pur_from", filter_column="pur_from", images=True, on_activate=open_job,
            note="Pieces sold in the period with where they came in (purchase, MFG transfer or "
                 "opening), cost, sale and the days they sat in stock."),
        "todays_daybook": ReportSpec(
            key="todays_daybook", title="Today's Daybook",
            columns=static([Col("date", "DATE"), Col("vrtype", "VR TYPE"), Col("vrno", "VRNO"),
                            Col("party", "PARTY"), Col("process", "PROCESS"),
                            Col("detail", "DETAIL"), Col("group", "GROUP"), _p("pcs", "PCS"),
                            _w("weight", "WEIGHT"), _m("amount", "AMOUNT")]),
            query=lambda s, a, b, **_k: SR.todays_daybook(s, a, b), date_default="today",
            filter_column="vrtype", on_activate=open_job,
            note="Every voucher of the day - sale-side vouchers with their stone lines under "
                 "each piece, inventory metal / stone, job steps with the process, account "
                 "vouchers."),
    }


class SalesDashboardWidget(QWidget):
    """Dimension x measure for a date range as a bar chart and a table, and
    the dashboard's ready-made analyses."""

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.user = user
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        h1 = QLabel("Sales Dashboard")
        h1.setObjectName("H1")
        lay.addWidget(h1)
        bar = QHBoxLayout()
        fy0, fy1 = R.fy_range()
        self.d0 = QDateEdit(QDate(fy0.year, fy0.month, fy0.day))
        self.d1 = QDateEdit(QDate.currentDate())
        for d in (self.d0, self.d1):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
        self.dim = QComboBox()
        self.dim.addItems(list(SR.DIMENSIONS))
        self.measure = QComboBox()
        self.measure.addItems(list(SR.MEASURES))
        for w in (QLabel("From"), self.d0, QLabel("To"), self.d1, QLabel("By"), self.dim,
                  QLabel("Show"), self.measure):
            bar.addWidget(w)
        b = QPushButton("Show")
        b.setObjectName("Primary")
        b.clicked.connect(self.show_cube)
        bar.addWidget(b)
        bx = QPushButton("Custom Excel")
        bx.clicked.connect(self._excel)
        bar.addWidget(bx)
        bar.addStretch(1)
        lay.addLayout(bar)
        grid = QGridLayout()
        for i, name in enumerate(SR.ANALYSES):
            ab = QPushButton(name)
            ab.clicked.connect(lambda _c=False, n=name: self.show_analysis(n))
            grid.addWidget(ab, i // 4, i % 4)
        lay.addLayout(grid)
        self.split = QSplitter()
        self.chart_box = QWidget()
        self.chart_lay = QVBoxLayout(self.chart_box)
        self.chart_lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.split.addWidget(self.chart_box)
        self.split.addWidget(self.table)
        lay.addWidget(self.split, 1)
        self._cols: list[str] = []
        self._rows: list[dict] = []
        self.show_cube()

    def _dates(self) -> tuple[date, date]:
        q = lambda d: date(d.date().year(), d.date().month(), d.date().day())  # noqa: E731
        return q(self.d0), q(self.d1)

    def _chart(self, title: str, labels: list[str], values: list) -> None:
        while self.chart_lay.count():
            w = self.chart_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.chart = BarChart(labels[:25], values[:25], title,
                              decimals=0 if self.measure.currentText() == "Pcs" else 2)
        self.chart_lay.addWidget(self.chart)

    def _fill(self, cols: list[str], rows: list[dict]) -> None:
        self._cols, self._rows = cols, rows
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels([c.replace("_", " ").upper() for c in cols])
        for r, row in enumerate(rows):
            for c, k in enumerate(cols):
                v = row.get(k)
                text = "" if v is None else (f"{v:,.2f}" if isinstance(v, Decimal) else str(v))
                self.table.setItem(r, c, QTableWidgetItem(text))

    def show_cube(self) -> None:
        a, b = self._dates()
        dim, meas = self.dim.currentText(), self.measure.currentText()
        with SessionLocal() as s:
            data = SR.cube(s, a, b, dim, meas)
        self._chart(f"{dim} with {meas}", [k for k, _v in data], [v for _k, v in data])
        self._fill([dim.lower(), meas.lower()],
                   [{dim.lower(): k, meas.lower(): v} for k, v in data])

    def show_analysis(self, name: str) -> None:
        a, b = self._dates()
        with SessionLocal() as s:
            cols, rows, lk, vk = SR.analysis(s, name, a, b)
        self._chart(name, [str(r.get(lk) or "") for r in rows], [r.get(vk) or 0 for r in rows])
        self._fill(cols, rows)

    def _excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Custom Excel", "sales.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append([c.replace("_", " ").upper() for c in self._cols])
        for r in self._rows:
            ws.append([float(r[c]) if isinstance(r.get(c), Decimal) else r.get(c)
                       for c in self._cols])
        wb.save(path)
        _info(self, "Custom Excel", f"Saved {path}")
