"""Quotation ▸ Quotation and Day Book (9 Oct Session 5 §4.27, T-12).

Built on the shared add / edit / list screen with a line grid, as Order is.
Every line is priced again on save from its SKU (Mt Amt = N-Wt x Metal Rate),
the quotation never posts to the ledger, and Convert to Order makes the order
(and its jobs)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtWidgets import QInputDialog, QMessageBox

from diagold.db.models import Account, Metal, ProductSku, Quotation, QuotationLine
from diagold.db.session import SessionLocal
from diagold.services import quotation as Q
from diagold.services.production import ProductionError
from diagold.ui.crud import ChildSpec, CrudSpec, Field
from diagold.ui.specs import _account_label, _metal_label, _register

_sku_label = lambda p: f"{p.sku_code}  {p.description or ''}".strip()  # noqa: E731


def _fill_from_sku(grid, row: int, sku_id) -> None:
    if not sku_id:
        return
    with SessionLocal() as s:
        d = Q.price_line(s, {"product_sku_id": sku_id, "pcs": grid.cell_value(row, "pcs") or 1})
    for k in ("sku_desc", "metal_id", "title", "gwt_pcs", "nwt_pcs", "tot_gwt", "metal_rate",
              "mt_amt", "stone_amt", "labour_rate", "labour", "total"):
        if not grid.cell_value(row, k) or k in ("mt_amt", "total", "tot_gwt", "stone_amt",
                                                "labour"):
            grid.set_cell_value(row, k, d.get(k))


def _recalc(grid, row: int, _value) -> None:
    """A weight, Pcs or Metal Rate typed: Tot GWt, Mt Amt and Total follow at
    once (legacy Quotation 176: G-Wt 11.650 typed on BANG-204)."""
    d = lambda k: Decimal(str(grid.cell_value(row, k) or 0))  # noqa: E731
    pcs = max(int(d("pcs")), 1)
    mt = (d("nwt_pcs") * pcs * d("metal_rate")).quantize(Decimal("0.01"))
    grid.set_cell_value(row, "tot_gwt", d("gwt_pcs") * pcs)
    grid.set_cell_value(row, "mt_amt", mt)
    grid.set_cell_value(row, "total", mt + d("stone_amt") + d("labour"))


def _lines_summary(rows: list[dict]) -> str:
    pcs = sum(int(r.get("pcs") or 0) for r in rows)
    gwt = sum(Decimal(str(r.get("tot_gwt") or 0)) for r in rows)
    tot = sum(Decimal(str(r.get("total") or 0)) for r in rows)
    # Account Information as the legacy screen shows it - Dr the client /
    # Cr Sales A/c - for reading only: a quotation posts nothing (9 Oct Q6).
    return (f"{len(rows)} line(s) · {pcs} pcs · Tot GWt {gwt:,.3f} · total {tot:,.2f}"
            f"      Account Information: Dr client / Cr Sales A/c {tot:,.2f} (not posted)")


def _quick_add(dialog, text: str) -> list[dict]:
    """Barcode / SKU box: a SKU code or Stock No + Enter adds the priced line."""
    values = {}
    for name in ("account_id", "quot_date", "client_chart"):
        ed = dialog.editors.get(name)
        if ed is not None:
            f = next(x for x in dialog.spec.fields if x.name == name)
            values[name] = dialog._editor_value(f)
    with SessionLocal() as s:
        d = Q.line_for_code(s, text, values.get("quot_date"),
                            account_id=values.get("account_id"),
                            client_chart=bool(values.get("client_chart")))
    editor = dialog.child_editors["lines"]
    d["sno"] = editor.table.rowCount() + 1
    return [d]


def _excel(widget, q, images: bool = True, breakup: bool = False) -> None:
    """Excel Format: the client's quotation sheet with photos and stone rows;
    ``breakup``: the client's breakup format, the same as the sale invoice
    (23 Nov sample)."""
    if not _need(widget, q, "Excel Format"):
        return
    from PySide6.QtWidgets import QFileDialog
    from diagold.services import documents
    default = str(documents.PRINT_DIR / f"quotation_{q.quot_no}.xlsx")
    path, _ = QFileDialog.getSaveFileName(widget, "Excel Format", default, "Excel (*.xlsx)")
    if not path:
        return
    with SessionLocal() as s:
        try:
            fn = Q.breakup_excel if breakup else Q.excel_format
            fn(s, s.get(Quotation, q.id), path, images=images)
        except Exception as exc:  # noqa: BLE001 - a locked file, say so
            QMessageBox.warning(widget, "Excel Format", f"Could not save: {exc}")
            return
    QMessageBox.information(widget, "Excel Format", f"Saved {path}")


def _validate(values: dict, children: dict) -> str | None:
    lines = [r for r in children.get("lines", []) if r.get("product_sku_id")
             or (r.get("sku_desc") or "").strip()]
    if not lines:
        return "A quotation needs at least one SKU line."
    return None


def _prepare(values: dict, children: dict, session) -> None:
    if not values.get("quot_no"):
        values["quot_no"] = Q.next_no(session)
    if not values.get("quot_time"):
        values["quot_time"] = datetime.now().strftime("%H:%M:%S")
    kept = [r for r in children.get("lines", []) if r.get("product_sku_id")
            or (r.get("sku_desc") or "").strip()]
    total = Decimal("0")
    for n, r in enumerate(kept, start=1):
        d = Q.price_line(session, r, values.get("quot_date") or date.today(),
                         account_id=values.get("account_id"),
                         client_chart=bool(values.get("client_chart")))
        r.update({k: d[k] for k in d if k in {c.name for c in QuotationLine.__table__.columns}})
        r["sno"] = n
        total += Decimal(str(r.get("total") or 0))
    values["total"] = total
    children["lines"] = kept


def _need(widget, q, title: str) -> bool:
    if q is None:
        QMessageBox.information(widget, title, "Select a quotation first.")
        return False
    return True


def _reload(widget) -> None:
    if hasattr(widget, "reload"):
        widget.reload()


def _convert(widget, q) -> None:
    if not _need(widget, q, "Convert to Order"):
        return
    with SessionLocal() as s:
        try:
            order = Q.convert_to_order(s, s.get(Quotation, q.id))
            s.commit()
            no = order.order_no
        except ProductionError as exc:
            s.rollback()
            QMessageBox.warning(widget, "Convert to Order", str(exc))
            return
    QMessageBox.information(widget, "Convert to Order", f"Order {no} made, with one job per "
                            "line (Production Planning ▸ Order).")
    _reload(widget)


def _status(widget, q) -> None:
    if not _need(widget, q, "Status"):
        return
    st, ok = QInputDialog.getItem(widget, "Status", f"Quotation {q.quot_no}:",
                                  list(Quotation.STATUSES[:-1]),
                                  max(0, list(Quotation.STATUSES).index(q.status)
                                      if q.status in Quotation.STATUSES[:-1] else 0), False)
    if not ok:
        return
    with SessionLocal() as s:
        try:
            Q.set_status(s, s.get(Quotation, q.id), st)
            s.commit()
        except ProductionError as exc:
            QMessageBox.warning(widget, "Status", str(exc))
            return
    _reload(widget)


def _copy_row(widget, q) -> None:
    if not _need(widget, q, "Copy Selected Row"):
        return
    n, ok = QInputDialog.getInt(widget, "Copy Selected Row", "Copy line number:", 1, 1, 999)
    if not ok:
        return
    with SessionLocal() as s:
        try:
            Q.copy_line(s, s.get(Quotation, q.id), n)
            s.commit()
        except ProductionError as exc:
            QMessageBox.warning(widget, "Copy Selected Row", str(exc))
            return
    _reload(widget)


def _client_chart(widget, q) -> None:
    """Prices From Client Chart: tick it and price the lines again."""
    if not _need(widget, q, "Prices From Client Chart"):
        return
    with SessionLocal() as s:
        qq = s.get(Quotation, q.id)
        qq.client_chart = True
        Q.reprice(s, qq)
        s.commit()
        total = qq.total
    QMessageBox.information(widget, "Prices From Client Chart",
                            f"Quotation {q.quot_no} priced from the client's chart: "
                            f"{Decimal(str(total)):,.2f}.")
    _reload(widget)


def _html(s, q: Quotation, *, images: bool = False, stones: bool = False) -> str:
    a = s.get(Account, q.account_id) if q.account_id else None
    rows = []
    req: dict[str, list] = {}
    for l in q.lines:
        sku = s.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
        metal = s.get(Metal, l.metal_id) if l.metal_id else None
        img = sku.photo if sku else ""
        pic = f"<td><img src='file://{img}' width='90'></td>" if images else ""
        rows.append(f"<tr>{pic}<td>{l.sno}</td><td>{sku.sku_code if sku else ''}</td>"
                    f"<td>{l.sku_desc or ''}</td><td>{l.c_ref or ''}</td>"
                    f"<td>{metal.name if metal else ''}</td><td>{l.pcs}</td>"
                    f"<td>{l.tot_gwt}</td><td>{Decimal(str(l.nwt_pcs or 0)) * (l.pcs or 1)}</td>"
                    f"<td>{Decimal(str(l.metal_rate or 0)):,.2f}</td>"
                    f"<td>{Decimal(str(l.mt_amt or 0)):,.2f}</td>"
                    f"<td>{Decimal(str(l.stone_amt or 0)):,.2f}</td>"
                    f"<td>{Decimal(str(l.labour or 0)):,.2f}</td>"
                    f"<td>{Decimal(str(l.total or 0)):,.2f}</td></tr>")
        if stones and sku is not None:
            for st in Q.sku_stones(s, sku):
                k = f"{st['label']} {st['size']}".strip()
                acc = req.setdefault(k, [0, Decimal("0")])
                acc[0] += int(st["pcs"]) * int(l.pcs or 1)
                acc[1] += Decimal(st["weight"]) * int(l.pcs or 1)
    head = (("<th>Image</th>" if images else "") + "<th>#</th><th>SKU</th><th>Desc</th>"
            "<th>C-Ref</th><th>Metal</th><th>Pcs</th><th>Tot GWt</th><th>N-Wt</th>"
            "<th>Metal Rate</th><th>Mt Amt</th><th>Stones</th><th>Labour</th><th>Total</th>")
    out = (f"<h2>Quotation {q.quot_no}</h2><p>{q.quot_date:%d-%m-%Y} {q.quot_time} · "
           f"{a.name if a else ''} · Ref {q.ref or '-'} · Status {q.status}"
           f"{' · Tracking ' + q.tracking_no if q.tracking_no else ''}</p>"
           f"<table border=1 cellspacing=0 cellpadding=3><tr>{head}</tr>{''.join(rows)}</table>"
           f"<p><b>Total {Decimal(str(q.total or 0)):,.2f}</b></p>")
    if stones:
        out += ("<h3>Stone requirement</h3><table border=1 cellspacing=0 cellpadding=3>"
                "<tr><th>Stone</th><th>Pcs</th><th>Cts</th></tr>"
                + "".join(f"<tr><td>{k}</td><td>{p}</td><td>{w:.3f}</td></tr>"
                          for k, (p, w) in req.items()) + "</table>")
    return out


def _print_pdf(widget, q, title: str, **kw) -> None:
    if not _need(widget, q, title):
        return
    from diagold.services import documents
    with SessionLocal() as s:
        qq = s.get(Quotation, q.id)
        path = documents.PRINT_DIR / f"quotation_{qq.quot_no}_{title.split()[0].lower()}_" \
                                     f"{datetime.now():%Y%m%d-%H%M%S}.pdf"
        documents.to_pdf(_html(s, qq, **kw), path)
    QMessageBox.information(widget, title, f"Saved {path}")


def _slide_show(widget, q) -> None:
    """Slide Show File…: the lines' product photos full screen, one by one."""
    if not _need(widget, q, "Slide Show"):
        return
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
    with SessionLocal() as s:
        pics = []
        for l in s.get(Quotation, q.id).lines:
            sku = s.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
            path = sku.photo if sku else ""
            if path:
                pics.append((f"{sku.sku_code} - {l.sku_desc or ''}", path))
    if not pics:
        QMessageBox.information(widget, "Slide Show", "None of the SKUs has a photo.")
        return
    dlg = QDialog(widget)
    dlg.setWindowTitle(f"Quotation {q.quot_no} — slide show")
    lay = QVBoxLayout(dlg)
    cap, img = QLabel(), QLabel()
    img.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(cap)
    lay.addWidget(img, 1)
    nxt = QPushButton("Next")
    lay.addWidget(nxt)
    pos = [0]

    def show() -> None:
        title, path = pics[pos[0] % len(pics)]
        cap.setText(f"<b>{title}</b>  ({pos[0] % len(pics) + 1} / {len(pics)})")
        pm = QPixmap(path)
        img.setPixmap(pm.scaled(900, 700, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                      if not pm.isNull() else QPixmap())
    nxt.clicked.connect(lambda: (pos.__setitem__(0, pos[0] + 1), show()))
    show()
    dlg.showMaximized()
    dlg.exec()


def _digicat(widget, _q) -> None:
    QMessageBox.information(widget, "Get DIGICAT Quote",
                            "DIGICAT is not connected - what this pulls from DIGICAT (id 1202) "
                            "is to be explained by the client.")


def _day_book(widget, _q) -> None:
    from diagold.ui.production import show_in_dialog
    from diagold.ui.reports import ReportWidget
    show_in_dialog(widget, ReportWidget(day_book_spec()), "Quotation Day Book")


def day_book_spec():
    from diagold.ui.reports import Col, ReportSpec, static
    m = lambda k, l: Col(k, l, "measure", 2, total=True)  # noqa: E731
    return ReportSpec(
        key="quotation_day_book", title="Quotation Day Book",
        columns=static([Col("date", "DATE"), Col("quot_no", "QUOT NO"),
                        Col("account", "ACCOUNT"), Col("status", "STATUS"), Col("sku", "SKU"),
                        Col("c_ref", "C-REF"), Col("metal", "METAL"),
                        Col("pcs", "PCS", "measure", 0, total=True),
                        Col("tot_gwt", "TOT GWT", "measure", 3, total=True),
                        Col("nwt", "N-WT", "measure", 3, total=True),
                        Col("metal_rate", "METAL RATE", "measure", 2), m("mt_amt", "MT AMT"),
                        m("stone_amt", "STONE AMT"), m("labour", "LABOUR"), m("total", "TOTAL"),
                        Col("order_no", "ORDER")]),
        query=lambda s, a, b, **_k: Q.day_book(s, a, b), group_by="account",
        filter_column="status", date_default="month",
        note="Every quotation line; ORDER = the order it was converted to. A quotation "
             "posts nothing to the accounts (9 Oct Q6).")


_register(CrudSpec(
    key="quotation.quotation",
    title="Quotation",
    model=Quotation,
    order_by="-quot_no",
    date_field="quot_date",
    search_hint="Search by ref, terms, tracking…",
    validate=_validate,
    before_save=_prepare,
    form_width=1240,
    form_maximized=True,
    quick_add=("Barcode / SKU - type a SKU code or Stock No, Enter adds the line", _quick_add),
    extra_buttons=[("Excel Format", _excel), ("Convert to Order", _convert), ("Status", _status),
                   ("Copy Selected Row", _copy_row), ("Prices From Client Chart", _client_chart),
                   ("Print", lambda w, q: _print_pdf(w, q, "Print")),
                   ("Requirement Sheet", lambda w, q: _print_pdf(w, q, "Requirement Sheet",
                                                                 stones=True)),
                   ("Catalog 2", lambda w, q: _print_pdf(w, q, "Catalog 2", images=True)),
                   ("Slide Show File…", _slide_show), ("Get DIGICAT Quote", _digicat),
                   ("Day Book", _day_book)],
    fields=[
        Field("quot_no", "Quot No", type="int", readonly=True, help_text="Allotted on save."),
        Field("quot_date", "Date", type="date", default=date.today, required=True),
        Field("quot_time", "Time", in_list=False),
        Field("ref", "Ref"),
        Field("currency_code", "Currency", default="INR", in_list=False),
        Field("quot_type", "Quot Type", in_list=False),
        Field("terms", "Terms", in_list=False),
        Field("account_id", "Account", type="fk", fk_model=Account, fk_label=_account_label),
        Field("salesperson", "Sales Person", in_list=False),
        Field("tracking_no", "Tracking No", in_list=False),
        Field("client_chart", "Prices From Client Chart", type="bool", default=False,
              in_list=False),
        Field("status", "Status", type="choice", choices=list(Quotation.STATUSES),
              default="Open"),
        Field("total", "Total", type="float", readonly=True),
        Field("remark", "Remark", in_list=False),
        Field("lines", "Lines", type="child",
              help_text="Pick the SKU: weights, metal rate (the day's), stones and labour fill "
                        "in; Mt Amt = N-Wt x Metal Rate. A typed rate is kept (9 Oct Q18).",
              child=ChildSpec(
                  model=QuotationLine, fk_attr="quotation_id", order_by="sno",
                  summary=_lines_summary, height=200,
                  fields=[
                      Field("sno", "Sno", type="int", default=1),
                      Field("product_sku_id", "SKU", type="fk", fk_model=ProductSku,
                            fk_label=_sku_label, on_change=_fill_from_sku),
                      Field("sku_desc", "SKU Desc"),
                      Field("c_ref", "C-Ref"),
                      Field("line_po", "Line P.O."),
                      Field("metal_id", "Metal", type="fk", fk_model=Metal,
                            fk_label=_metal_label),
                      Field("title", "Title", type="float", decimals=2),
                      Field("loss_pct", "Loss%", type="float", decimals=2),
                      Field("colour", "Color", type="choice", choices=["Y", "W", "R", ""]),
                      Field("size", "Size"),
                      Field("pcs", "Pcs", type="int", default=1, on_change=_recalc),
                      Field("gwt_pcs", "G-Wt/Pcs", type="float", decimals=3, on_change=_recalc),
                      Field("nwt_pcs", "N-Wt/Pcs", type="float", decimals=3, on_change=_recalc),
                      Field("tot_gwt", "Tot GWt", type="float", decimals=3),
                      Field("metal_rate", "Metal Rate", type="float", on_change=_recalc),
                      Field("unit", "Unit", default="NetWt"),
                      Field("mt_amt", "Mt Amt", type="float"),
                      Field("stone_amt", "Stone Amt", type="float"),
                      Field("labour", "Labour", type="float"),
                      Field("total", "Total", type="float"),
                      Field("remark", "Remark"),
                  ],
              )),
    ],
))


# --------------------------------------------------------------------------
# The Quotation screen, laid out and worked as the legacy one (19 Nov video,
# Quotation 176): header on top, Barcode / SKU box, the line grid, Account
# Information / Narration / photo under it, the buttons at the foot; it opens
# on a new Quot No and Edit picks a saved one from the Edit List.
# --------------------------------------------------------------------------
from PySide6.QtCore import QDate, Qt, Signal  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,  # noqa: E402
                               QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from sqlalchemy import select  # noqa: E402


class EditListDialog(QDialog):
    """Edit List: From / To, VrNo, Ref No, SKU, C-Ref, Particulars - pick the
    quotation to open (legacy)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit List")
        self.picked: int | None = None
        lay = QVBoxLayout(self)
        g = QGridLayout()
        today = date.today()
        fy = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
        self.d_from, self.d_to = QDateEdit(QDate(fy.year, fy.month, fy.day)), QDateEdit(
            QDate(today.year, today.month, today.day))
        for d in (self.d_from, self.d_to):
            d.setDisplayFormat("dd-MM-yyyy")
            d.dateChanged.connect(lambda _d: self._load())
        self.f_vr, self.f_ref, self.f_sku, self.f_cref, self.f_party = (
            QLineEdit() for _ in range(5))
        for i, (label, w) in enumerate((("From", self.d_from), ("To", self.d_to),
                                        ("VrNo", self.f_vr), ("Ref No", self.f_ref),
                                        ("SKU", self.f_sku), ("C-Ref", self.f_cref),
                                        ("Particulars", self.f_party))):
            g.addWidget(QLabel(label), i // 4, (i % 4) * 2)
            g.addWidget(w, i // 4, (i % 4) * 2 + 1)
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda _t: self._filter())
        lay.addLayout(g)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["VrNo", "Date", "RefNo", "Particulars"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._take(r))
        lay.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(lambda: self._take(self.table.currentRow()))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(640, 520)
        self._rows: list[dict] = []
        self._load()

    def _load(self) -> None:
        a, b = self.d_from.date().toPython(), self.d_to.date().toPython()
        with SessionLocal() as s:
            self._rows = Q.edit_list(s, a, b)
        self._filter()

    def _filter(self) -> None:
        want = [(self.f_vr, "vr_no"), (self.f_ref, "ref"), (self.f_sku, "skus"),
                (self.f_cref, "c_refs"), (self.f_party, "party")]
        self.table.setRowCount(0)
        self._shown = []
        for r in self._rows:
            if any(box.text().strip() and box.text().strip().lower() not in str(r[k]).lower()
                   for box, k in want):
                continue
            n = self.table.rowCount()
            self.table.insertRow(n)
            for c, v in enumerate((r["vr_no"], r["date"].strftime("%d-%m-%Y"), r["ref"],
                                   r["party"])):
                self.table.setItem(n, c, QTableWidgetItem(str(v)))
            self._shown.append(r["id"])
        if self._shown:
            self.table.selectRow(0)

    def _take(self, row: int) -> None:
        if 0 <= row < len(self._shown):
            self.picked = self._shown[row]
            self.accept()


class QuotationWidget(QWidget):
    close_requested = Signal()
    open_requested = Signal(str)

    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        from diagold.ui.crud import ChildTableEditor
        from diagold.ui.flow import FlowLayout
        from diagold.ui.specs import SPECS
        self.user = user
        self._id: int | None = None
        # The legacy "List of Account / SKU ..." panel down the right side, not
        # a list over the boxes (19 Nov).
        from diagold.ui.side_list import SideList
        page = QHBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        main = QWidget()
        page.addWidget(main, 1)
        outer = QVBoxLayout(main)
        outer.setContentsMargins(24, 16, 12, 12)
        h1 = QLabel("Quotation")
        h1.setObjectName("H1")
        outer.addWidget(h1)

        # -- header, as the legacy rows ----------------------------------
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        self.quot_no = QLabel("")
        self.quot_no.setStyleSheet("font-weight: 600; font-size: 15px;")
        self.date = QDateEdit()
        self.date.setDisplayFormat("dd-MM-yyyy")
        self.account = QComboBox()
        self.account.addItem("", None)
        with SessionLocal() as s:
            for a in s.scalars(select(Account).where(Account.is_active == True)  # noqa: E712
                               .order_by(Account.name)):
                self.account.addItem(_account_label(a), a.id)
        self.ref, self.terms, self.salesperson, self.tracking, self.quot_type = (
            QLineEdit() for _ in range(5))
        self.currency = QComboBox()
        self.currency.addItems(["INR", "USD", "AED", "EUR"])
        self.chart = QCheckBox("Prices From Client Chart")
        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("Barcode / SKU, Enter")
        self.barcode.setStyleSheet("background: #FDECEA;")
        self.barcode.returnPressed.connect(self._barcode)
        cells = [(0, "Quot No.", self.quot_no), (1, "Date", self.date), (2, "Account", self.account),
                 (3, "Barcode", self.barcode),
                 (4, "Ref", self.ref), (5, "Terms", self.terms),
                 (6, "Sales Person", self.salesperson), (7, None, self.chart),
                 (8, "Currency", self.currency), (9, "Quot Type", self.quot_type),
                 (10, "Tracking No.", self.tracking)]
        for i, label, w in cells:
            r, c = divmod(i, 4)
            if label:
                g.addWidget(QLabel(label), r, c * 2)
            g.addWidget(w, r, c * 2 + 1)
        g.setColumnStretch(5, 2)
        outer.addLayout(g)

        # -- the line grid -----------------------------------------------
        child = next(f.child for f in SPECS["quotation.quotation"].fields if f.name == "lines")
        self.lines = ChildTableEditor(child)
        orig = self.lines._refresh_summary

        def refreshed(*a) -> None:
            orig(*a)
            self._totals()
        self.lines._refresh_summary = refreshed     # Account Information follows the lines
        self.lines.table.itemSelectionChanged.connect(self._photo)
        self.lines.table.setMinimumHeight(260)
        outer.addWidget(self.lines, 1)

        # -- Account Information | Narration | photo ---------------------
        foot = QHBoxLayout()
        acc_box = QVBoxLayout()
        cap = QLabel("Account Information")
        cap.setStyleSheet("font-weight: 600;")
        acc_box.addWidget(cap)
        self.acc_info = QTableWidget(2, 4)
        self.acc_info.setHorizontalHeaderLabels(["Dr/Cr", "Account", "Debit", "Credit"])
        self.acc_info.verticalHeader().setVisible(False)
        self.acc_info.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.acc_info.setFixedHeight(100)
        self.acc_info.horizontalHeader().setStretchLastSection(True)
        for c, wdt in enumerate((50, 200, 110)):
            self.acc_info.setColumnWidth(c, wdt)
        acc_box.addWidget(self.acc_info)
        foot.addLayout(acc_box, 3)
        nar_box = QVBoxLayout()
        cap2 = QLabel("Narration")
        cap2.setStyleSheet("font-weight: 600;")
        nar_box.addWidget(cap2)
        self.narration = QPlainTextEdit()
        self.narration.setFixedHeight(100)
        nar_box.addWidget(self.narration)
        foot.addLayout(nar_box, 3)
        self.photo = QLabel("no photo")
        self.photo.setFixedSize(120, 120)
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setObjectName("ImageSlot")
        foot.addWidget(self.photo)
        outer.addLayout(foot)

        # -- the buttons, at the foot as the legacy screen ----------------
        bar = FlowLayout(spacing=6)
        for label, slot, primary in (
                ("Add", self.new_quote, False), ("Edit", self.edit, False),
                ("Save", self.save, True), ("Delete", self.delete, False),
                ("Requirement Sheet", lambda: self._on_saved(
                    lambda q: _print_pdf(self, q, "Requirement Sheet", stones=True)), False),
                ("Detailed Sheet", lambda: self._on_saved(
                    lambda q: _print_pdf(self, q, "Print")), False),
                ("Catalog 2", lambda: self._on_saved(
                    lambda q: _print_pdf(self, q, "Catalog 2", images=True)), False),
                ("Excel Formats", self._excel_formats, False),
                ("Copy Selected Row", self._copy_row, False),
                ("Convert to Order", lambda: self._on_saved(lambda q: _convert(self, q)), False),
                ("Status", lambda: self._on_saved(lambda q: _status(self, q)), False),
                ("Slide Show File…", lambda: self._on_saved(lambda q: _slide_show(self, q)),
                 False),
                ("SKU Search", self._sku_search, False),
                ("Day Book", lambda: _day_book(self, None), False),
                ("Exit", self.close_requested.emit, False)):
            b = QPushButton(label)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(slot)
            bar.addWidget(b)
        outer.addLayout(bar)
        self.side_list = SideList(self, {self.account: "Account", self.currency: "Currency"})
        page.addWidget(self.side_list)
        self.new_quote()

    # -- state -----------------------------------------------------------
    def new_quote(self) -> None:
        self._id = None
        with SessionLocal() as s:
            from sqlalchemy import func
            nxt = (s.scalar(select(func.max(Quotation.quot_no))) or 0) + 1
        self.quot_no.setText(str(nxt))
        t = date.today()
        self.date.setDate(QDate(t.year, t.month, t.day))
        self.account.setCurrentIndex(0)
        for w in (self.ref, self.terms, self.salesperson, self.tracking, self.quot_type,
                  self.barcode):
            w.clear()
        self.currency.setCurrentText("INR")
        self.chart.setChecked(False)
        self.narration.clear()
        self.lines.set_rows([])
        self._totals()
        self.barcode.setFocus()

    def load(self, quot_id: int) -> None:
        with SessionLocal() as s:
            q = s.get(Quotation, quot_id)
            if q is None:
                return
            self._id = q.id
            self.quot_no.setText(f"{q.quot_no}  ({q.status})")
            self.date.setDate(QDate(q.quot_date.year, q.quot_date.month, q.quot_date.day))
            self.account.setCurrentIndex(max(self.account.findData(q.account_id), 0))
            self.ref.setText(q.ref or "")
            self.terms.setText(q.terms or "")
            self.salesperson.setText(q.salesperson or "")
            self.tracking.setText(q.tracking_no or "")
            self.quot_type.setText(q.quot_type or "")
            self.currency.setCurrentText(q.currency_code or "INR")
            self.chart.setChecked(bool(q.client_chart))
            self.narration.setPlainText(q.remark or "")
            names = [f.name for f in self.lines.spec.fields]
            self.lines.set_rows([{n: getattr(l, n, None) for n in names} for l in q.lines])
        self._totals()

    def reload(self) -> None:          # the shared actions call this after a change
        if self._id:
            self.load(self._id)

    def _head(self) -> dict:
        return {"quot_date": self.date.date().toPython(),
                "quot_time": datetime.now().strftime("%H:%M:%S"),
                "ref": self.ref.text().strip(), "terms": self.terms.text().strip(),
                "account_id": self.account.currentData(),
                "salesperson": self.salesperson.text().strip(),
                "tracking_no": self.tracking.text().strip(),
                "quot_type": self.quot_type.text().strip(),
                "currency_code": self.currency.currentText(),
                "client_chart": self.chart.isChecked(),
                "remark": self.narration.toPlainText().strip()}

    # -- actions ---------------------------------------------------------
    def _barcode(self) -> None:
        text = self.barcode.text().strip()
        if not text:
            return
        with SessionLocal() as s:
            try:
                d = Q.line_for_code(s, text, self.date.date().toPython(),
                                    account_id=self.account.currentData(),
                                    client_chart=self.chart.isChecked())
            except ProductionError as exc:
                QMessageBox.warning(self, "Barcode", str(exc))
                return
        d["sno"] = self.lines.table.rowCount() + 1
        self.lines.add_row(d)
        self.lines.table.selectRow(self.lines.table.rowCount() - 1)
        self.barcode.clear()
        self.barcode.setFocus()

    def _sku_search(self) -> None:
        text, ok = QInputDialog.getText(self, "SKU Search", "SKU code or Stock No:")
        if ok and text.strip():
            self.barcode.setText(text.strip())
            self._barcode()

    def save(self) -> None:
        from diagold.ui.confirm import confirm_save
        if not confirm_save(self, "this quotation"):
            return
        with SessionLocal() as s:
            try:
                q = Q.save_quotation(s, self._head(), self.lines.rows(), self._id)
                s.commit()
                qid, no = q.id, q.quot_no
            except ProductionError as exc:
                s.rollback()
                QMessageBox.warning(self, "Cannot save", str(exc))
                return
        self.load(qid)
        QMessageBox.information(self, "Saved", f"Quotation {no} saved.")

    def edit(self) -> None:
        dlg = EditListDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.picked:
            self.load(dlg.picked)

    def delete(self) -> None:
        if not self._id:
            QMessageBox.information(self, "Delete", "Open a saved quotation first (Edit).")
            return
        if QMessageBox.question(self, "Delete", f"Delete quotation {self.quot_no.text()}?") \
                != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as s:
            try:
                Q.delete_quotation(s, s.get(Quotation, self._id))
                s.commit()
            except ProductionError as exc:
                s.rollback()
                QMessageBox.warning(self, "Cannot delete", str(exc))
                return
        self.new_quote()

    def _on_saved(self, fn) -> None:
        """An action on the saved quotation (prints, Excel, convert ...)."""
        if not self._id:
            QMessageBox.information(self, "Quotation", "Save the quotation first (or open one "
                                    "with Edit).")
            return
        with SessionLocal() as s:
            q = s.get(Quotation, self._id)
        fn(q)

    def _excel_formats(self) -> None:
        """Excel Formats: the legacy Format - 1 / Format - 2 choice."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Breakup  (DIAMOND / POLKI / COLOR STONE - client's format)",
                       lambda: self._on_saved(lambda q: _excel(self, q, breakup=True)))
        menu.addAction("Format - 1  (with photos)",
                       lambda: self._on_saved(lambda q: _excel(self, q, images=True)))
        menu.addAction("Format - 2  (without photos)",
                       lambda: self._on_saved(lambda q: _excel(self, q, images=False)))
        menu.exec(QCursor.pos())

    def _copy_row(self) -> None:
        r = self.lines.table.currentRow()
        if r < 0:
            QMessageBox.information(self, "Copy Selected Row", "Select a line first.")
            return
        row = dict(self.lines.rows()[r])
        row.pop("id", None)
        row["sno"] = self.lines.table.rowCount() + 1
        self.lines.add_row(row)

    # -- the foot ----------------------------------------------------------
    def _totals(self) -> None:
        tot = sum((Decimal(str(r.get("total") or 0)) for r in self.lines.rows()), Decimal("0"))
        client = self.account.currentText().split(" - ")[-1] if self.account.currentData() \
            else "(client)"
        for r, vals in enumerate((("Cr", "Sales A/c", "", f"{tot:,.2f}"),
                                  ("Dr", client, f"{tot:,.2f}", ""))):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c >= 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.acc_info.setItem(r, c, it)

    def _photo(self) -> None:
        r = self.lines.table.currentRow()
        path = ""
        if r >= 0:
            sku_id = self.lines.cell_value(r, "product_sku_id")
            if sku_id:
                with SessionLocal() as s:
                    sku = s.get(ProductSku, sku_id)
                    path = sku.photo if sku else ""
        from diagold.ui import photo_cache
        pix = photo_cache.load(path)
        if pix.isNull():
            self.photo.setPixmap(QPixmap())
            self.photo.setText("no photo")
        else:
            self.photo.setText("")
            self.photo.setPixmap(pix.scaled(116, 116, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
