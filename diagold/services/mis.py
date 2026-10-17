"""M.I.S. Reports - the queries (9 Oct Session 5 §4.4-§4.29).

Each function returns rows for one legacy M.I.S. report, with the legacy
column names as keys (lower-case) so the screen, the Excel export and the
acceptance figures in the 9 Oct notes line up. Formulas verified there:

    Sales Profit [Metal]  SOLD FINE = NET x SOLD PURITY / 1000      8.228 x 0.590 = 4.855
    Setting Analysis      LOSSWT = ISS N-WT - RTN N-WT; WAST REC = LOSSWT - ALWLOSS
    Refining Analysis     LOSS % = LOSS FINE / NET FINE x 100 ("-" when NET FINE = 0)
    Approval Out Counts   AGE = report date - MFG DATE           01-04 -> 09-10 = 191
    Shipping Analysis     DAYS = SHIP DT - ORD DT
    Sold Stone            AMOUNT = CTS x PRICE
    Sold Labour           AMOUNT = PRICE x net wt                 1,200 x 15.303
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, Metal, ProductSku, ReadyVoucher, ReadyVoucherLine,
                               StockItem)
from diagold.services import mfg_pricing, rates, sales
from diagold.services.sales_reports import _C, _base, _lines

ZERO = Decimal("0")
D2 = Decimal("0.01")
D3 = Decimal("0.001")
NONE = "(none)"


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


# --------------------------------------------------------------------------
# Sales (T-02)
# --------------------------------------------------------------------------
def sales_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Sales Analysis (§4.4): one row per piece sold (S) or returned (SR),
    the sale in the S_ columns and the return in the SR_ columns, so the
    totals show gross sale, return and - by difference - net."""
    c = _C(session)
    rows = []
    for l, v in _lines(session, ("rs_sale", "rs_sale_return"), date_from, date_to):
        b = _base(c, v, l)
        sale = v.vr_type == "rs_sale"
        p = "s_" if sale else "sr_"
        row = {"vrdate": v.vr_date, "vrno": v.vr_no, "type": "S" if sale else "SR",
               "client": b["particulars"], "sku": b["sku"], "metal": b["metal"],
               "_job_id": l.job_id}
        for k in ("s_", "sr_"):
            row.update({k + "pcs": None, k + "gwt": None, k + "nwt": None, k + "amt": None})
        row.update({p + "pcs": int(l.pcs or 0), p + "gwt": b["g_wt"], p + "nwt": b["n_wt"],
                    p + "amt": b["total"]})
        rows.append(row)
    return rows


SALES_MIS_BLOCKS = ("Item Wise", "Metal Wise", "Party Wise", "Sales Person Wise", "SKU Wise")


def sales_mis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Sales Analysis [Item Wise] - "Sales MIS" (§4.11): five blocks - Item,
    Metal, Party, Sales Person, SKU - each PARTICULARS, PCS, GROSSWT, NETWT,
    TOTAL, biggest first. A blank item / salesperson shows as (none)."""
    c = _C(session)
    acc: dict[tuple[str, str], list] = defaultdict(lambda: [0, ZERO, ZERO, ZERO])
    for l, v in _lines(session, ("rs_sale",), date_from, date_to):
        b = _base(c, v, l)
        keys = {"Item Wise": b["item"], "Metal Wise": b["metal"], "Party Wise": b["particulars"],
                "Sales Person Wise": (v.salesperson or "").strip(), "SKU Wise": b["sku"]}
        for block, k in keys.items():
            a = acc[(block, k or NONE)]
            a[0] += int(l.pcs or 0)
            a[1] += b["g_wt"]
            a[2] += b["n_wt"]
            a[3] += b["total"]
    rows = []
    for block in SALES_MIS_BLOCKS:
        part = [(k, a) for (bl, k), a in acc.items() if bl == block]
        part.sort(key=lambda kv: (-kv[1][0], -kv[1][3], kv[0].lower()))
        for k, a in part:
            rows.append({"block": block, "particulars": k, "pcs": a[0], "grosswt": a[1],
                         "netwt": a[2], "total": a[3]})
    return rows


def sales_voucher_wise(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Sales [Voucher Wise] - "Sales Summery" (§4.26): one row per sale
    voucher with the metal / stone / labour value split and how it shipped."""
    rows = []
    q = (select(ReadyVoucher).where(ReadyVoucher.vr_type == "rs_sale",
                                    ReadyVoucher.vr_date >= date_from,
                                    ReadyVoucher.vr_date <= date_to)
         .order_by(ReadyVoucher.vr_date, ReadyVoucher.vr_no))
    for v in session.scalars(q):
        acct = session.get(Account, v.account_id) if v.account_id else None
        r = {"date": v.vr_date, "group": acct.group_name if acct else "",
             "party": acct.name if acct else "", "vrno": v.vr_no, "refno": v.ref_no,
             "pcs": 0, "grosswt": ZERO, "netwt": ZERO, "finewt": ZERO, "stone": ZERO,
             "mt_value": ZERO, "st_value": ZERO, "lab_value": ZERO, "total_value": ZERO,
             "inv_value": _dec(v.total), "ship_by": v.ship_by or "", "ship_no": v.ship_no or ""}
        for l in v.lines:
            r["pcs"] += int(l.pcs or 0)
            r["grosswt"] += _dec(l.gross_wt)
            r["netwt"] += _dec(l.net_wt)
            r["finewt"] += _dec(l.fine_wt)
            r["stone"] += _dec(l.st_wt)
            r["mt_value"] += _dec(l.metal_amount)
            r["st_value"] += _dec(l.stone_amount)
            r["lab_value"] += _dec(l.labour) + _dec(l.setting_amount) + _dec(l.other_amount)
            r["total_value"] += _dec(l.total)
        rows.append(r)
    return rows


def day_wise_sales(session: Session, date_from: date, date_to: date,
                   by_party: bool = False, **_k: Any) -> list[dict[str, Any]]:
    """Day Wise Sales [MetalValue] - "Bullion Sales" (§4.18): per day, sorted
    by date (the legacy is not), the fine weight sold, its GOLD VALUE at that
    day's fine (24K) rate, and the sale amount. Ticked Party wise: one row per
    day and party (the legacy shows "Other" on every row - Q7). Sales only;
    whether returns or fine settlements belong here is Q15."""
    c = _C(session)
    acc: dict[tuple, list] = defaultdict(lambda: [ZERO, ZERO, ZERO])
    for l, v in _lines(session, ("rs_sale",), date_from, date_to):
        fine = _dec(l.fine_wt)
        if not fine and l.metal_id:
            metal = c.get(Metal, l.metal_id)
            fine = (_dec(l.net_wt) * mfg_pricing.title_of(metal) / 1000).quantize(D3)
        pure = rates.rate_for(session, l.metal_id, v.vr_date).rate if l.metal_id else ZERO
        acct = c.get(Account, v.account_id)
        key = (v.vr_date, (acct.name if acct else "") if by_party else "All")
        a = acc[key]
        a[0] += fine
        a[1] += (fine * pure).quantize(D2)
        a[2] += _dec(l.total)
    return [{"date": d, "party": p, "finewt": a[0], "gold_value": a[1], "sale_amt": a[2]}
            for (d, p), a in sorted(acc.items(), key=lambda kv: (kv[0][0], kv[0][1].lower()))]


def _purity_rows(session: Session, vr_type: str, date_from: date,
                 date_to: date) -> list[dict[str, Any]]:
    c = _C(session)
    rows = []
    for l, v in _lines(session, (vr_type,), date_from, date_to):
        metal = c.get(Metal, l.metal_id)
        acct = c.get(Account, v.account_id)
        item = c.get(StockItem, l.stock_item_id)
        sku = c.get(ProductSku, l.product_sku_id)
        purity = mfg_pricing.title_of(metal).quantize(D2) if metal else ZERO
        sold = _dec(l.title) or purity
        net = _dec(l.net_wt)
        sold_fine = (net * sold / 1000).quantize(D3)
        actual = (net * purity / 1000).quantize(D3)
        ret = "No"
        if vr_type == "rs_sale" and l.stock_item_id:
            back = session.scalar(select(ReadyVoucherLine.id).join(ReadyVoucher).where(
                ReadyVoucherLine.stock_item_id == l.stock_item_id,
                ReadyVoucher.vr_type == "rs_sale_return", ReadyVoucherLine.id > l.id))
            ret = "Yes" if back else "No"
        rows.append({"vrno": v.vr_no, "date": v.vr_date, "client": acct.name if acct else "",
                     "stockno": item.stock_no if item else "", "sku": sku.sku_code if sku else "",
                     "metal": metal.name if metal else "", "purity": purity,
                     "sold_purity": sold, "grosswt": _dec(l.gross_wt), "net_wt": net,
                     "sold_fine": sold_fine, "actual_fine": actual,
                     "diff_fine": sold_fine - actual, "ret": ret, "_job_id": l.job_id,
                     "_negative": sold_fine < actual})
    return rows


def sales_profit_metal(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Sales Profit [Metal] - "Sales Metal Profit" (§4.24): per sold piece the
    purity it was invoiced at against its actual purity. SOLD FINE = NET x
    SOLD PURITY / 1000, ACTUAL FINE = NET x PURITY / 1000, DIFF = SOLD -
    ACTUAL; RETURN = it came back later. Profit arises only when the invoice
    purity is above the actual (none in Sept-Oct - Q8)."""
    return _purity_rows(session, "rs_sale", date_from, date_to)


def sales_return_profit_metal(session: Session, date_from: date,
                              date_to: date) -> list[dict[str, Any]]:
    """Sales Return Profit [Metal]: the same columns for pieces returned."""
    return _purity_rows(session, "rs_sale_return", date_from, date_to)
