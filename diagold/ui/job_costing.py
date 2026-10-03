"""Manufacturing ▸ Job Costing (2 Oct Session 3 §4.3, T-02).

The register is the shared report grid (Print, Search, Set Column, Group,
Adv. Filter, Export, Auto Filter, F1 Show All); double-click opens the Job
Costing Sheet. Legacy shortcuts: Ctrl+F1 Stone Group Wise, Ctrl+P Excel Job
Costing, Ctrl+W Excel WIP Costing.
"""
from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from diagold.db.models import Job
from diagold.db.session import SessionLocal
from diagold.services import job_costing as JC
from diagold.ui.crud import auto_fit
from diagold.ui.reports import Col, ReportSpec, ReportWidget, static

GROUP_COLS = ("dia_amt", "polki_amt", "cs_amt", "setting", "std")


def _cols() -> list[Col]:
    k = lambda key, label: Col(key, label)                        # noqa: E731
    wt = lambda key, label: Col(key, label, "measure", 3, total=True)  # noqa: E731
    m = lambda key, label: Col(key, label, "measure", 2, total=True)   # noqa: E731
    return [k("job_no", "JOBNO"), k("sku", "SKU"), k("metal", "METAL"), k("col", "COL"),
            k("size", "SIZE"), Col("pcs", "PCS", "measure", total=True), wt("g_wt", "G-WT"),
            wt("n_wt", "N-WT"), Col("mt_price", "MT PRICE", "measure", 2),
            m("mt_amt", "MT AMT"), m("st_amt", "ST AMT"), m("dia_amt", "DIAMOND"),
            m("polki_amt", "POLKI"), m("cs_amt", "COLOUR STONE"), m("setting", "SETTING"),
            m("std", "STD"), m("labour", "LABOUR"), m("total", "TOTAL"),
            Col("margin_pct", "MARGIN %", "measure", 2), m("margin", "MARGIN"),
            Col("price_unit", "PRICE UNIT", "measure", 2), m("amount", "AMOUNT"),
            k("tag", "TAG PRICE"), k("stock", "STOCK"), k("basis", "RATES")]


def _query(s, d0: date, d1: date, wip: bool = False, **_k) -> list[dict]:
    return JC.register(s, d0, d1, wip=wip)


def _open_sheet(widget: ReportWidget, row: dict) -> None:
    CostingSheetDialog(row["_job_id"], widget).exec()


def _toggle_groups(widget: ReportWidget) -> None:
    """Ctrl+F1 Stone Group Wise: show the stone amount split into Diamond /
    Polki / Colour Stone and labour into Setting / STD, or fold them back."""
    keys = [c.key for c in widget.visible_cols()]
    if any(k in keys for k in GROUP_COLS):
        widget._visible = [k for k in keys if k not in GROUP_COLS]
    else:
        out = []
        for k in keys:
            out.append(k)
            if k == "st_amt":
                out += ["dia_amt", "polki_amt", "cs_amt"]
            if k == "labour":
                out += ["setting", "std"]
        widget._visible = out
    widget._rebuild()


def _excel(widget: ReportWidget, wip: bool) -> None:
    d0, d1 = widget.dates()
    name = "wip_costing" if wip else "job_costing"
    path, _ = QFileDialog.getSaveFileName(widget, "Excel", f"{name}_{d1:%Y%m%d}.xlsx",
                                          "Excel (*.xlsx)")
    if not path:
        return
    with SessionLocal() as s:
        rows = JC.register(s, d0, d1, wip=wip)
    JC.register_xlsx(rows, path, ("WIP Costing" if wip else "Job Costing")
                     + f" {d0:%d-%m-%Y} to {d1:%d-%m-%Y}")
    QMessageBox.information(widget, "Excel", f"Saved {path} - {len(rows)} job(s).")


def job_costing_spec() -> ReportSpec:
    return ReportSpec(
        key="job_costing", title="Job Costing", columns=static(_cols()), query=_query,
        options={"wip": ("WIP costing (jobs still in work)", False)},
        on_activate=_open_sheet, filter_column="metal",
        actions=[("Stone Group Wise", "Ctrl+F1", _toggle_groups),
                 ("Excel Job Costing", "Ctrl+P", lambda w: _excel(w, False)),
                 ("Excel WIP Costing", "Ctrl+W", lambda w: _excel(w, True))],
        note="One row per finished job (by the day it finished): metal at the rate, stones "
             "at their price, labour = setting paid + STD, margin %, price and tag. A job in "
             "ready stock shows the rates frozen on its MFG transfer; any other job is "
             "costed at the masters as on the To date. Tick WIP costing for jobs still in "
             "work (weights as last weighed, stones issued so far). Double-click opens the "
             "Job Costing Sheet. Tag price = Grand Total / 1000 is provisional (Q3).")


def job_costing_screen(user=None) -> ReportWidget:
    w = ReportWidget(job_costing_spec(), user)
    if w._visible is None:
        w._visible = [c.key for c in _cols() if c.key not in GROUP_COLS]
        w._rebuild()
    return w


class CostingSheetDialog(QDialog):
    """The Job Costing Sheet: metal, each stone, setting + STD, total, margin,
    grand total, tag price and price per gm; Export To Excel, Print, WIP
    Costing (the same job at today's masters), Exit."""

    def __init__(self, job_id: int, parent=None, *, live: bool = False):
        super().__init__(parent)
        self.job_id, self.live = job_id, live
        with SessionLocal() as s:
            job = s.get(Job, job_id)
            self.sheet = JC.costing_sheet(s, job, date.today(), live=live)
        sh = self.sheet
        self.setWindowTitle(f"Job Costing Sheet — Job {sh.job_no}"
                            + ("  (WIP costing)" if live else ""))
        self.setMinimumSize(860, 640)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        head = QLabel(f"<b>Job {sh.job_no}</b> · {sh.sku} · {sh.metal} {sh.colour} · "
                      f"{sh.pcs} pc · size {sh.size or '-'}<br>G-Wt {sh.gross_wt:.3f} · "
                      f"N-Wt {sh.price.net_wt:.3f}"
                      + (f" · Stock No {sh.stock_no}" if sh.stock_no else "")
                      + f"<br><span style='color:#667085'>{sh.basis}</span>")
        head.setWordWrap(True)
        top.addWidget(head, 1)
        self.photo = QLabel("no photo")
        self.photo.setObjectName("ImageSlot")
        self.photo.setFixedSize(110, 110)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(sh.photo) if sh.photo else QPixmap()
        if not pix.isNull():
            self.photo.setPixmap(pix.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
            self.photo.mousePressEvent = lambda _e: self._enlarge(sh.photo)
        top.addWidget(self.photo)
        lay.addLayout(top)

        rows = self._rows()
        t = QTableWidget(len(rows), 3)
        t.setHorizontalHeaderLabels(["Item", "Basis", "Amount (Rs)"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r, (item, basis, amount, bold) in enumerate(rows):
            for c, v in enumerate((item, basis, amount)):
                it = QTableWidgetItem(v)
                if c == 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                        | Qt.AlignmentFlag.AlignVCenter)
                if bold:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(r, c, it)
        auto_fit(t)
        lay.addWidget(t, 1)
        if sh.notes:
            n = QLabel(" · ".join(sh.notes))
            n.setObjectName("Muted")
            n.setWordWrap(True)
            lay.addWidget(n)
        bar = QHBoxLayout()
        for label, slot in (("Export To Excel", self._excel), ("Print", self._print),
                            ("WIP Costing", self._wip), ("Exit", self.accept)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

    def _rows(self) -> list[tuple[str, str, str, bool]]:
        sh, p = self.sheet, self.sheet.price
        out = [("Metal", f"N-Wt {p.net_wt:.3f} g × {p.metal_rate:,.2f}/g "
                         f"(G-Wt {sh.gross_wt:.3f})", f"{p.metal_amount:,.2f}", False)]
        for s in p.stones:
            per = "pc" if s.unit == "pcs" else "ct"
            out.append((f"Stones — {s.label}", f"{s.pcs} / {s.weight:.3f} ct @ "
                                              f"{s.price:,.0f}/{per}", f"{s.amount:,.2f}", False))
        out.append(("Stone total", f"{sh.stone_pcs} pcs / {sh.stone_wt:.3f} ct",
                    f"{p.stone_amount:,.2f}", True))
        out.append(("Setting + STD (labour)", f"{sh.setting:,.2f} + {p.labour:,.2f} "
                    f"({p.labour_rate:,.2f} × {p.labour_weight:.3f} g)",
                    f"{sh.setting + p.labour:,.2f}", False))
        extra = p.finding_labour + p.ex_metal_amount + p.manual_amount
        if extra:
            out.append(("Finding / Ex metal / Manual", "", f"{extra:,.2f}", False))
        out += [("Total", "", f"{p.total:,.2f}", True),
                ("Margin", f"{p.margin_pct.normalize():f} %", f"{p.margin_amount:,.2f}", False),
                ("Grand Total", "", f"{p.price_per_pcs:,.2f}", True),
                ("Tag price / Price per gm", "Grand total ÷ 1,000 (provisional, Q3) · per "
                 "gross gm", f"{sh.tag_value:,.2f} · {sh.price_per_gm:,.2f}", False)]
        return out

    def _enlarge(self, path: str) -> None:
        from diagold.ui.production import show_in_dialog
        big = QLabel()
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        big.setPixmap(QPixmap(path).scaled(720, 720, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        show_in_dialog(self, big, "Photo", (760, 760))

    def _excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export To Excel", f"job_costing_{self.sheet.job_no}.xlsx", "Excel (*.xlsx)")
        if path:
            JC.sheet_xlsx(self.sheet, path)
            QMessageBox.information(self, "Export To Excel", f"Saved {path}")

    def _print(self) -> None:
        from diagold.services import documents
        sh = self.sheet
        body = "".join(
            f"<tr><td>{'<b>' + a + '</b>' if bold else a}</td><td>{b}</td>"
            f"<td align=right>{'<b>' + c + '</b>' if bold else c}</td></tr>"
            for a, b, c, bold in self._rows())
        html = (f"<h2>Job Costing Sheet — Job {sh.job_no}</h2>"
                f"<p>{sh.sku} · {sh.metal} {sh.colour} · {sh.pcs} pc · G-Wt "
                f"{sh.gross_wt:.3f} · N-Wt {sh.price.net_wt:.3f}<br>{sh.basis}</p>"
                + (f"<img src='{sh.photo}' height=120>" if sh.photo else "")
                + "<table border=1 cellspacing=0 cellpadding=4 width=100%>"
                "<tr><th>Item</th><th>Basis</th><th>Amount (Rs)</th></tr>" + body + "</table>")
        path = documents.PRINT_DIR / f"job_costing_{sh.job_no}_{datetime.now():%Y%m%d-%H%M%S}.pdf"
        documents.to_pdf(html, path)
        QMessageBox.information(self, "Print", f"Saved {path}")

    def _wip(self) -> None:
        CostingSheetDialog(self.job_id, self, live=True).exec()
