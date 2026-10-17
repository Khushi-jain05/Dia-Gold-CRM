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


def _lines_summary(rows: list[dict]) -> str:
    pcs = sum(int(r.get("pcs") or 0) for r in rows)
    tot = sum(Decimal(str(r.get("total") or 0)) for r in rows)
    return f"{len(rows)} line(s) · {pcs} pcs · total {tot:,.2f} (worked again on save)"


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
        img = (sku.image_finished or sku.image_design) if sku else ""
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
            path = (sku.image_finished or sku.image_design) if sku else ""
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
    extra_buttons=[("Convert to Order", _convert), ("Status", _status),
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
                      Field("pcs", "Pcs", type="int", default=1),
                      Field("gwt_pcs", "G-Wt/Pcs", type="float", decimals=3),
                      Field("nwt_pcs", "N-Wt/Pcs", type="float", decimals=3),
                      Field("tot_gwt", "Tot GWt", type="float", decimals=3),
                      Field("metal_rate", "Metal Rate", type="float"),
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
