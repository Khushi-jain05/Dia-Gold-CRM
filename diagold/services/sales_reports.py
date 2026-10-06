"""Sales registers and analysis (5 Oct §4.12 / §4.16, T-13).

Sales Register, Sales Return Register, Sales Profit Analysis, Purchase-Sales
Analysis, Today's Daybook, and the Sales Dashboard's figures (a dimension x
a measure, and the dashboard's ready-made analyses).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, AccountVoucher, FamilyCategory, InvVoucher, Job,
                               JobVoucher, Location, ManufacturingProcess, Metal, MfgTransfer,
                               MfgTransferLine, ProductSku, ReadyVoucher, ReadyVoucherLine,
                               StockItem, StoneSku)
from diagold.db.models.sku import Item
from diagold.services import sales

ZERO = Decimal("0")
D2 = Decimal("0.01")


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


class _C:
    def __init__(self, s: Session):
        self.s, self.d = s, {}

    def get(self, model, pk):
        if not pk:
            return None
        if (model, pk) not in self.d:
            self.d[(model, pk)] = self.s.get(model, pk)
        return self.d[(model, pk)]


def _lines(session: Session, types: tuple[str, ...], date_from: date, date_to: date):
    q = (select(ReadyVoucherLine, ReadyVoucher).join(ReadyVoucher)
         .where(ReadyVoucher.vr_type.in_(types), ReadyVoucher.vr_date >= date_from,
                ReadyVoucher.vr_date <= date_to)
         .order_by(ReadyVoucher.vr_date, ReadyVoucher.vr_no, ReadyVoucherLine.sno))
    return session.execute(q).all()


def _piece_flags(session: Session, item_id: int | None, after_line: int) -> tuple[str, str]:
    """(REPAIR, RETURN): was the piece ever issued to repair; did it come back
    on a sale return after this sale."""
    if not item_id:
        return "N", "N"
    types = set(session.scalars(select(ReadyVoucher.vr_type).join(ReadyVoucherLine).where(
        ReadyVoucherLine.stock_item_id == item_id)))
    ret = session.scalar(select(ReadyVoucherLine.id).join(ReadyVoucher).where(
        ReadyVoucherLine.stock_item_id == item_id, ReadyVoucher.vr_type == "rs_sale_return",
        ReadyVoucherLine.id > after_line))
    return ("Y" if "rs_repair_issue" in types else "N"), ("Y" if ret else "N")


def _base(c: _C, v: ReadyVoucher, l: ReadyVoucherLine) -> dict[str, Any]:
    acct = c.get(Account, v.account_id)
    item = c.get(StockItem, l.stock_item_id)
    sku = c.get(ProductSku, l.product_sku_id)
    fam = c.get(FamilyCategory, sku.family_id) if sku else None
    itm = c.get(Item, sku.item_id) if sku else None
    metal = c.get(Metal, l.metal_id)
    loc = c.get(Location, l.location_id)
    job = c.get(Job, l.job_id)
    g = sales._groups(l)
    return {
        "location": loc.name if loc else "", "date": v.vr_date, "vrno": v.vr_no,
        "vrtype": sales.READY_TYPES[v.vr_type].code, "particulars": acct.name if acct else "",
        "acc_code": acct.code if acct else "",
        "acc_group": acct.group_name if acct else "", "ref_no": v.ref_no,
        "sku": sku.sku_code if sku else "", "design": sku.design_no if sku else "",
        "family": fam.name if fam else "", "item": itm.name if itm else "",
        "sub_item": sku.s_item if sku else "", "snap": sku.snap if sku else "",
        "c_ref": l.c_ref or (item.c_ref if item else ""), "metal": metal.name if metal else "",
        "job_no": job.job_no if job else "", "_job_id": l.job_id,
        "barcode": item.stock_no if item else "", "stock_no": item.stock_no if item else "",
        "col": l.colour, "tag": (item.tag_text if item else "") or "",
        "pcs": l.pcs, "g_wt": _dec(l.gross_wt),
        "n_wt": _dec(l.net_wt), "fine_wt": _dec(l.fine_wt), "sec_wt": _dec(l.st_wt) or None,
        "metal_rate": _dec(l.metal_rate), "mt_total": _dec(l.metal_amount),
        "st_total": _dec(l.stone_amount), "labour": _dec(l.labour), "total": _dec(l.total),
        "tag_price": (item.tag_text if item else "") or "",
        "dia": g["DIAMOND"], "polki": g["POLKI"], "cs": g["COLOR STONE"],
        "cost": _dec(item.cost) if item else ZERO, "_item_id": l.stock_item_id,
        "_line_id": l.id, "_photo": (sku.image_finished or sku.image_design) if sku else "",
        "_account_id": v.account_id, "_family": fam.name if fam else "",
    }


def sales_register(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Every piece sold, with LOCATION … METAL RATE, MT TOTAL, ST TOTAL,
    TAGPRICE, REFNO, SNAP, REPAIR and RETURN (Y / N)."""
    c = _C(session)
    rows = []
    for l, v in _lines(session, ("rs_sale",), date_from, date_to):
        r = _base(c, v, l)
        r["repair"], r["ret"] = _piece_flags(session, l.stock_item_id, l.id)
        rows.append(r)
    return rows


def sales_return_register(session: Session, date_from: date,
                          date_to: date) -> list[dict[str, Any]]:
    c = _C(session)
    return [{**_base(c, v, l), "vrtype": "SR"}
            for l, v in _lines(session, ("rs_sale_return",), date_from, date_to)]


def sales_profit(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Per sold piece: SALE AMT (the line total) vs COST AMT (the piece's
    cost), PROFIT and PROFIT %. A piece that came back is marked RETURN Y."""
    rows = []
    for r in sales_register(session, date_from, date_to):
        profit = r["total"] - r["cost"]
        rows.append({**r, "sale_amt": r["total"], "cost_amt": r["cost"], "profit": profit,
                     "profit_pct": (profit / r["total"] * 100).quantize(D2) if r["total"]
                     else None, "_negative": profit < 0})
    return rows


def purchase_sales(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Pieces sold in the period with where they came from: PUR DATE / VRNO /
    FROM (a ready purchase, MFG transfer or opening), cost and net price,
    tag, weights, sale date / party / price, profit, % and DAYS in stock."""
    c = _C(session)
    rows = []
    for r in sales_register(session, date_from, date_to):
        item = c.get(StockItem, r["_item_id"])
        pur_date = pur_no = None
        pur_from = ""
        if item is not None and item.in_line_id:
            src = session.get(ReadyVoucherLine, item.in_line_id)
            pv = src.voucher if src else None
            if pv is not None:
                a = c.get(Account, pv.account_id)
                pur_date, pur_no = pv.vr_date, pv.vr_no
                pur_from = (a.name if a else "") or ("Opening" if pv.vr_type == "rp_opening"
                                                     else "")
        elif item is not None and item.line_id:
            line = c.get(MfgTransferLine, item.line_id)
            t = c.get(MfgTransfer, line.transfer_id) if line else None
            if t is not None:
                pur_date, pur_no, pur_from = t.vr_date, t.vr_no, "MFG"
        profit = r["total"] - r["cost"]
        rows.append({
            "pur_date": pur_date, "pur_vrno": pur_no or "", "pur_from": pur_from,
            "sku": r["sku"], "cost_price": r["cost"],
            "net_price": _dec(item.price) if item else ZERO, "tag": r["tag_price"],
            "g_wt": r["g_wt"], "n_wt": r["n_wt"], "sale_date": r["date"],
            "sale_to": r["particulars"], "sale_price": r["total"], "profit": profit,
            "profit_pct": (profit / r["total"] * 100).quantize(D2) if r["total"] else None,
            "days": (r["date"] - pur_date).days if pur_date else None,
            "stock_id": r["barcode"], "_job_id": r["_job_id"], "_negative": profit < 0,
            "_photo": r["_photo"]})
    return rows


# --------------------------------------------------------------------------
# Today's Daybook
# --------------------------------------------------------------------------
def todays_daybook(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Every voucher of the day(s): ready stock (with each stone line under
    the piece), inventory metal / stone, job steps (with the process) and
    account vouchers."""
    c = _C(session)
    rows: list[dict[str, Any]] = []
    for l, v in _lines(session, tuple(sales.READY_TYPES), date_from, date_to):
        acct = c.get(Account, v.account_id)
        sku = c.get(ProductSku, l.product_sku_id)
        rows.append({"date": v.vr_date, "vrtype": sales.READY_TYPES[v.vr_type].code,
                     "vrno": v.vr_no, "party": acct.name if acct else "", "process": "",
                     "detail": f"{sku.sku_code if sku else ''} · Stock {l.stock_item_id or ''}",
                     "group": "", "pcs": l.pcs, "weight": _dec(l.net_wt),
                     "amount": _dec(l.total), "_job_id": l.job_id})
        for st in json.loads(l.stones_json or "[]"):
            rows.append({"date": v.vr_date, "vrtype": "", "vrno": "", "party": "",
                         "process": "", "detail": "   " + (st.get("label") or ""),
                         "group": (st.get("s_type") or "").upper(),
                         "pcs": int(st.get("pcs") or 0), "weight": _dec(st.get("weight")),
                         "amount": sales.stone_amount(st), "_job_id": None, "_sub": True})
    from diagold.services import inventory as INV
    for v in session.scalars(select(InvVoucher).where(
            InvVoucher.vr_date >= date_from, InvVoucher.vr_date <= date_to)
            .order_by(InvVoucher.vr_date, InvVoucher.vr_no)):
        acct = c.get(Account, v.account_id)
        t = INV.VOUCHER_TYPES.get(v.vr_type)
        for l in v.lines:
            sku = c.get(StoneSku, l.stone_sku_id) if l.stone_sku_id else None
            metal = c.get(Metal, l.metal_id) if l.metal_id else None
            rows.append({"date": v.vr_date, "vrtype": t.title if t else v.vr_type,
                         "vrno": v.vr_no, "party": acct.name if acct else "", "process": "",
                         "detail": (sku.sku_code if sku else (metal.name if metal else
                                                              l.particulars or "")),
                         "group": "METAL" if l.metal_id else "STONE",
                         "pcs": int(l.pcs or 0) or None, "weight": _dec(l.weight),
                         "amount": _dec(l.amount), "_job_id": None})
    for jv in session.scalars(select(JobVoucher).where(
            JobVoucher.vr_date >= date_from, JobVoucher.vr_date <= date_to)
            .order_by(JobVoucher.vr_date, JobVoucher.id)):
        from diagold.db.models import JobStep
        step = c.get(JobStep, jv.step_id)
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        job = c.get(Job, jv.job_id)
        w = c.get(Account, jv.worker_id)
        rows.append({"date": jv.vr_date, "vrtype": "ISS" if jv.kind == "issue" else "RTN",
                     "vrno": jv.vr_no, "party": w.name if w else "",
                     "process": proc.name if proc else "",
                     "detail": f"Job {job.job_no if job else ''}", "group": "",
                     "pcs": jv.pcs, "weight": _dec(jv.net_wt), "amount": None,
                     "_job_id": jv.job_id})
    from diagold.services import accounts
    for av in session.scalars(select(AccountVoucher).where(
            AccountVoucher.vr_date >= date_from, AccountVoucher.vr_date <= date_to)
            .order_by(AccountVoucher.vr_date, AccountVoucher.vr_no)):
        acct = c.get(Account, av.account_id)
        rows.append({"date": av.vr_date, "vrtype": accounts.vr_title(av.vr_type),
                     "vrno": av.vr_no, "party": acct.name if acct else "", "process": "",
                     "detail": f"{av.mode} {av.narration}".strip(), "group": "",
                     "pcs": None, "weight": _dec(av.weight) or None, "amount": _dec(av.amount),
                     "_job_id": None})
    return rows


# --------------------------------------------------------------------------
# Sales Dashboard
# --------------------------------------------------------------------------
DIMENSIONS = {"Item": "item", "Client": "particulars", "Metal": "metal", "Family": "family",
              "SubItem": "sub_item", "Stone": "_stone"}
MEASURES = {"Pcs": "pcs", "Weight": "n_wt", "Fine": "fine_wt", "Value": "total"}


def _signed(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Sales less returns: a return counts negative."""
    rows = sales_register(session, date_from, date_to)
    for r in sales_return_register(session, date_from, date_to):
        rows.append({**r, **{k: -_dec(r[k]) for k in ("pcs", "n_wt", "fine_wt", "total",
                                                      "cost", "dia", "polki", "cs")}})
    return rows


def cube(session: Session, date_from: date, date_to: date, dimension: str,
         measure: str) -> list[tuple[str, Decimal]]:
    """Sales (net of returns) by one dimension, biggest first."""
    key, m = DIMENSIONS[dimension], MEASURES[measure]
    acc: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in _signed(session, date_from, date_to):
        if key == "_stone":
            for g, k in (("DIAMOND", "dia"), ("POLKI", "polki"), ("COLOR STONE", "cs")):
                if r.get(k):
                    acc[g] += _dec(r[k]) if m == "total" else _dec(r[m])
            continue
        acc[str(r.get(key) or "(blank)")] += _dec(r[m])
    return sorted(acc.items(), key=lambda kv: -kv[1])


def _month(d: date) -> str:
    return d.strftime("%Y-%m")


def analysis(session: Session, name: str, date_from: date, date_to: date
             ) -> tuple[list[str], list[dict[str, Any]], str, str]:
    """The dashboard's buttons. Returns (columns, rows, chart label key,
    chart value key)."""
    rows = _signed(session, date_from, date_to)
    if name == "Month-wise Sales":
        acc: dict[str, list] = defaultdict(lambda: [0, ZERO, ZERO])
        for r in rows:
            a = acc[_month(r["date"])]
            a[0] += int(r["pcs"])
            a[1] += _dec(r["n_wt"])
            a[2] += _dec(r["total"])
        out = [{"month": k, "pcs": v[0], "weight": v[1], "value": v[2]}
               for k, v in sorted(acc.items())]
        return ["month", "pcs", "weight", "value"], out, "month", "value"
    if name == "Client-wise Monthly Sales":
        acc2: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        months = sorted({_month(r["date"]) for r in rows})
        for r in rows:
            acc2[(r["particulars"], _month(r["date"]))] += _dec(r["total"])
        clients = sorted({k[0] for k in acc2})
        out = [{"client": cl, **{m: acc2.get((cl, m)) for m in months},
                "total": sum((acc2.get((cl, m), ZERO) for m in months), ZERO)}
               for cl in clients]
        out.sort(key=lambda r: -r["total"])
        return ["client", *months, "total"], out, "client", "total"
    if name == "Monthly Performance":
        acc3: dict[str, list] = defaultdict(lambda: [ZERO, ZERO])
        for r in rows:
            a = acc3[_month(r["date"])]
            a[0] += _dec(r["total"])
            a[1] += _dec(r["total"]) - _dec(r["cost"])
        out = [{"month": k, "sales": v[0], "profit": v[1],
                "profit_pct": (v[1] / v[0] * 100).quantize(D2) if v[0] else None}
               for k, v in sorted(acc3.items())]
        return ["month", "sales", "profit", "profit_pct"], out, "month", "profit"
    if name == "Top 20 Profitable Clients":
        acc4: dict[str, list] = defaultdict(lambda: [ZERO, ZERO])
        for r in rows:
            acc4[r["particulars"]][0] += _dec(r["total"])
            acc4[r["particulars"]][1] += _dec(r["total"]) - _dec(r["cost"])
        out = sorted(({"client": k, "sales": v[0], "profit": v[1]} for k, v in acc4.items()),
                     key=lambda r: -r["profit"])[:20]
        return ["client", "sales", "profit"], out, "client", "profit"
    if name == "Monthly Comparison (YoY)":
        prev = _signed(session, date_from.replace(year=date_from.year - 1),
                       date_to.replace(year=date_to.year - 1))
        acc5: dict[str, list] = defaultdict(lambda: [ZERO, ZERO])
        for r in rows:
            acc5[r["date"].strftime("%m %b")][0] += _dec(r["total"])
        for r in prev:
            acc5[r["date"].strftime("%m %b")][1] += _dec(r["total"])
        out = [{"month": k[3:], "this_year": v[0], "last_year": v[1],
                "change_pct": ((v[0] - v[1]) / v[1] * 100).quantize(D2) if v[1] else None}
               for k, v in sorted(acc5.items())]
        return ["month", "this_year", "last_year", "change_pct"], out, "month", "this_year"
    if name in ("Price Range Wise", "Family-wise Sales Range"):
        bands = [(0, 25000), (25000, 50000), (50000, 100000), (100000, 200000),
                 (200000, 500000), (500000, None)]

        def band(v: Decimal) -> str:
            for lo, hi in bands:
                if hi is None or v < hi:
                    return f"{lo:,} - {hi:,}" if hi else f"{lo:,}+"
            return ""
        acc6: dict[tuple, list] = defaultdict(lambda: [0, ZERO])
        for r in rows:
            if _dec(r["pcs"]) <= 0:
                continue
            per = _dec(r["total"]) / max(int(r["pcs"]), 1)
            k = (r["_family"] or "(blank)", band(per)) if name.startswith("Family") \
                else ("", band(per))
            acc6[k][0] += int(r["pcs"])
            acc6[k][1] += _dec(r["total"])
        order = {band(Decimal(lo)): i for i, (lo, _hi) in enumerate(bands)}
        out = [{"family": k[0], "range": k[1], "pcs": v[0], "value": v[1]}
               for k, v in sorted(acc6.items(), key=lambda kv: (kv[0][0], order[kv[0][1]]))]
        cols = (["family"] if name.startswith("Family") else []) + ["range", "pcs", "value"]
        return cols, out, "range", "pcs"
    if name == "Sales Return":
        out = sales_return_register(session, date_from, date_to)
        return (["date", "vrno", "particulars", "sku", "pcs", "n_wt", "total"], out,
                "particulars", "total")
    raise ValueError(name)


ANALYSES = ("Month-wise Sales", "Client-wise Monthly Sales", "Monthly Performance",
            "Top 20 Profitable Clients", "Monthly Comparison (YoY)", "Price Range Wise",
            "Family-wise Sales Range", "Sales Return")
