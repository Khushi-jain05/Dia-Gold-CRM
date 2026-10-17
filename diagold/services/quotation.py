"""Quotation (9 Oct Session 5 §4.27, T-12).

A line is priced from its SKU the way the sale prices a piece:

    Mt Amt  = N-Wt/Pcs x Pcs x Metal Rate       9.176 x 8,670.64 = 79,561.79 (Quot 161)
    Stones  = the SKU's stone lines x their sale price, x Pcs
    Labour  = labour rate x N-Wt
    Total   = Mt Amt + Stones + Labour

Metal Rate is the day's rate for the metal unless typed; Quot 161 used
8,670.64 against the day's sale rate 8,798, so whether quotations carry
their own rate or the client's chart is asked (Q18). "Prices From Client
Chart" re-prices labour and stones from the client's chart.

A quotation NEVER posts to the ledger (legacy Quot 161 shows Cr Sales A/c /
Dr K J SE - treated as a defect until the client says otherwise, Q6).
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, Metal, Order, OrderLine, ProductSku, ProductSkuStone,
                               Quotation, QuotationLine, StoneSize, StoneSku)
from diagold.services import mfg_pricing, production
from diagold.services.production import ProductionError

ZERO = Decimal("0")
PAISA = Decimal("0.01")


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _money(v: Decimal) -> Decimal:
    return _dec(v).quantize(PAISA, rounding=ROUND_HALF_UP)


def next_no(session: Session) -> int:
    return (session.scalar(select(func.max(Quotation.quot_no))) or 0) + 1


def sku_stones(session: Session, sku: ProductSku) -> list[dict[str, Any]]:
    """The SKU's stone lines in the sale's stone shape (label, pcs, weight,
    unit, price, s_type)."""
    out = []
    for st in session.scalars(select(ProductSkuStone).where(
            ProductSkuStone.product_id == sku.id)):
        ssku = session.get(StoneSku, st.stone_sku_id) if st.stone_sku_id else None
        size = session.get(StoneSize, st.size_id) if st.size_id else None
        price = _dec(st.sale_price) or (_dec(ssku.sale_price) if ssku else ZERO)
        out.append({"label": (ssku.sku_code if ssku else "") or st.description,
                    "s_type": ssku.stone_type if ssku else "",
                    "size": (size.name if size else "") or (ssku.size if ssku else ""),
                    "pcs": int(st.pieces or 0), "weight": str(_dec(st.weight_cts)),
                    "unit": "pcs" if (st.per or "Cts").lower().startswith("pc") else "ct",
                    "price": str(price)})
    return out


def price_line(session: Session, ln: dict[str, Any], on_date: date | None = None, *,
               account_id: int | None = None, client_chart: bool = False,
               keep_rate: bool = True) -> dict[str, Any]:
    """Fill a line from its SKU and work out its amounts. Typed weights and a
    typed metal rate are kept (``keep_rate``)."""
    from diagold.services import sales
    on_date = on_date or date.today()
    out = dict(ln)
    sku = session.get(ProductSku, ln.get("product_sku_id")) if ln.get("product_sku_id") else None
    if sku is not None:
        out.setdefault("sku_desc", sku.description)
        if not out.get("sku_desc"):
            out["sku_desc"] = sku.description
        if not out.get("metal_id"):
            out["metal_id"] = sku.metal_id
        if not _dec(out.get("nwt_pcs")):
            out["nwt_pcs"] = _dec(sku.net_weight)
        if not _dec(out.get("gwt_pcs")):
            out["gwt_pcs"] = _dec(sku.gross_weight)
    metal = session.get(Metal, out.get("metal_id")) if out.get("metal_id") else None
    pcs = max(int(out.get("pcs") or 1), 1)
    out["pcs"] = pcs
    if not _dec(out.get("title")) and metal is not None:
        out["title"] = mfg_pricing.title_of(metal)
    rate = _dec(out.get("metal_rate"))
    if not (keep_rate and rate) and metal is not None:
        rate = production.metal_price(session, metal.id, on_date)
    out["metal_rate"] = rate
    net = (_dec(out.get("nwt_pcs")) * pcs)
    out["tot_gwt"] = (_dec(out.get("gwt_pcs")) * pcs).quantize(Decimal("0.001"))
    out["mt_amt"] = _money(net * rate)
    stones = sku_stones(session, sku) if sku is not None else []
    lab_rate = _dec(out.get("labour_rate"))
    if not lab_rate and metal is not None:
        lab_rate, _src = mfg_pricing.labour_rate_for(session, metal.id, on_date)
    info = {"stones": stones, "labour_rate": lab_rate, "labour_per": "gm",
            "product_sku_id": out.get("product_sku_id"), "metal_id": out.get("metal_id"),
            "pcs": pcs, "net_wt": net}
    if client_chart and account_id:
        from diagold.services import price_charts as PC
        chart = PC.chart_for(session, account_id)
        if chart is not None:
            info = PC.apply(session, chart, info)
    out["stone_amt"] = _money(sum((sales.stone_amount(s) for s in info["stones"]), ZERO) * pcs)
    out["labour_rate"] = _dec(info["labour_rate"])
    out["labour"] = sales.labour_amount(info["labour_rate"], info.get("labour_per") or "gm",
                                        net, pcs)
    out["total"] = _money(out["mt_amt"] + out["stone_amt"] + out["labour"])
    return out


def reprice(session: Session, q: Quotation, *, keep_rate: bool = True) -> Quotation:
    """Work every line out again (Prices From Client Chart, a new rate)."""
    total = ZERO
    for l in q.lines:
        d = price_line(session, {c.name: getattr(l, c.name) for c in l.__table__.columns},
                       q.quot_date, account_id=q.account_id, client_chart=q.client_chart,
                       keep_rate=keep_rate)
        for k in ("sku_desc", "metal_id", "title", "nwt_pcs", "gwt_pcs", "tot_gwt",
                  "metal_rate", "mt_amt", "stone_amt", "labour_rate", "labour", "total"):
            setattr(l, k, d.get(k))
        total += _dec(l.total)
    q.total = _money(total)
    session.flush()
    return q


def copy_line(session: Session, q: Quotation, sno: int) -> QuotationLine:
    """Copy Selected Row: the line again at the end."""
    src = next((l for l in q.lines if l.sno == sno), None)
    if src is None:
        raise ProductionError(f"Quotation {q.quot_no} has no line {sno}.")
    data = {c.name: getattr(src, c.name) for c in src.__table__.columns
            if c.name not in ("id", "sno")}
    new = QuotationLine(**data, sno=max(l.sno for l in q.lines) + 1)
    session.add(new)
    session.flush()
    session.refresh(q)
    reprice(session, q)
    return new


def set_status(session: Session, q: Quotation, status: str) -> None:
    if status not in Quotation.STATUSES:
        raise ProductionError(f"Unknown status {status}.")
    if q.status == "Converted" and status != "Converted":
        raise ProductionError(f"Quotation {q.quot_no} is already an order.")
    q.status = status
    session.flush()


def convert_to_order(session: Session, q: Quotation) -> Order:
    """Convert to Order: a customer order with the quotation's lines (SKU,
    C-Ref, metal, colour, size, pcs, N-Wt/Pcs, Tot GWt, rate, Mt Amt) - which
    allots one job per line as any order does."""
    if q.order_id:
        raise ProductionError(f"Quotation {q.quot_no} is already order "
                              f"{session.get(Order, q.order_id).order_no}.")
    if not q.lines:
        raise ProductionError("The quotation has no lines.")
    order = Order(order_no=production.next_number(session, Order.order_no), order_date=date.today(),
                  ref=q.ref or f"Quot {q.quot_no}", terms=q.terms,
                  currency_code=q.currency_code, account_id=q.account_id,
                  order_type="Customer" if q.account_id else "Stock",
                  remark=f"From Quotation {q.quot_no}")
    session.add(order)
    session.flush()
    for n, l in enumerate(q.lines, start=1):
        session.add(OrderLine(order_id=order.id, sno=n, product_sku_id=l.product_sku_id,
                              sku_desc=l.sku_desc, c_ref=l.c_ref, metal_id=l.metal_id,
                              colour=l.colour, size=l.size, pcs=int(l.pcs or 1),
                              net_wt_per_pcs=_dec(l.nwt_pcs), tot_gross_wt=_dec(l.tot_gwt),
                              metal_rate_unit=f"{_dec(l.metal_rate)}", metal_amount=_dec(l.mt_amt),
                              remark=l.remark))
    session.flush()
    session.refresh(order)
    production.sync_jobs_for_order(session, order)
    q.order_id, q.status = order.id, "Converted"
    session.flush()
    return order


def day_book(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Quotation ▸ Day Book: every quotation line of the period."""
    rows = []
    for q in session.scalars(select(Quotation).where(Quotation.quot_date >= date_from,
                                                     Quotation.quot_date <= date_to)
                             .order_by(Quotation.quot_date, Quotation.quot_no)):
        acct = session.get(Account, q.account_id) if q.account_id else None
        order = session.get(Order, q.order_id) if q.order_id else None
        for l in q.lines:
            sku = session.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
            metal = session.get(Metal, l.metal_id) if l.metal_id else None
            rows.append({"date": q.quot_date, "quot_no": q.quot_no,
                         "account": acct.name if acct else "", "status": q.status,
                         "sku": sku.sku_code if sku else l.sku_desc, "c_ref": l.c_ref,
                         "metal": metal.name if metal else "", "pcs": int(l.pcs or 0),
                         "tot_gwt": _dec(l.tot_gwt), "nwt": _dec(l.nwt_pcs) * int(l.pcs or 1),
                         "metal_rate": _dec(l.metal_rate), "mt_amt": _dec(l.mt_amt),
                         "stone_amt": _dec(l.stone_amt), "labour": _dec(l.labour),
                         "total": _dec(l.total), "order_no": order.order_no if order else ""})
    return rows
