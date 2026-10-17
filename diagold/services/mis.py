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

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, InvVoucher, InvVoucherLine, Job, JobBagLine,
                               JobBagMovement, JobStep, JobVoucher, Location,
                               ManufacturingProcess, Metal, Order, OrderLine, ProductSku,
                               ReadyVoucher, ReadyVoucherLine, StockItem, StockMovement,
                               StoneSku)
from diagold.db.models.sku import Item
from diagold.services import costing, mfg_pricing, production, rates, sales
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


# --------------------------------------------------------------------------
# Production (T-04)
# --------------------------------------------------------------------------
def _job_names(session: Session, c: _C, job: Job) -> tuple[str, str, str]:
    sku = c.get(ProductSku, job.product_sku_id)
    item = c.get(Item, sku.item_id) if sku and sku.item_id else None
    metal = c.get(Metal, job.metal_id)
    return (sku.sku_code if sku else ""), (item.name if item else ""), \
        (metal.name if metal else "")


def _worker_label(a: Account | None) -> str:
    """Worker by name with the code (legacy shows codes like B1202 alone)."""
    if a is None:
        return ""
    return f"{a.name} ({a.code})" if a.code and a.code != a.name else a.name


def _bag_wt(session: Session, voucher_id: int, kind: str) -> tuple[int, Decimal]:
    pcs, wt = 0, ZERO
    for m in session.scalars(select(JobBagMovement).where(JobBagMovement.voucher_id == voucher_id,
                                                          JobBagMovement.kind == kind)):
        pcs += int(m.pcs or 0)
        wt += _dec(m.weight)
    return pcs, wt


def setting_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Stone Setting Analysis - "Setting Analysis" (§4.7): one row per issue
    to a setter (any process named Setting) with its return. USE ST = the
    stones sent (F3) less those handed back; LOSSWT = ISS N-WT - RTN N-WT
    (negative = gain); ALWLOSS from the allowed %; WAST REC = LOSSWT -
    ALWLOSS (1,821.337 - 508.448 = 1,312.889); LABOUR = setting labour."""
    c = _C(session)
    rows = []
    q = (select(JobVoucher).where(JobVoucher.kind == "issue", JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to)
         .order_by(JobVoucher.vr_date, JobVoucher.vr_no, JobVoucher.id))
    for iss in session.scalars(q):
        step = c.get(JobStep, iss.step_id)
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        if proc is None or "setting" not in (proc.name or "").lower():
            continue
        rtn = session.scalar(select(JobVoucher).where(JobVoucher.issue_id == iss.id,
                                                      JobVoucher.kind == "receive"))
        job = c.get(Job, iss.job_id)
        sku, item, metal = _job_names(session, c, job)
        sent_pcs, sent_wt = _bag_wt(session, iss.id, "iss")
        back_pcs, back_wt = _bag_wt(session, rtn.id, "back") if rtn else (0, ZERO)
        d = production.loss_detail(proc, iss, rtn) if rtn else None
        loss = (_dec(iss.net_wt) - _dec(rtn.net_wt)).quantize(D3) \
            if rtn is not None and iss.net_wt is not None and rtn.net_wt is not None else None
        alw = d.allowed if d else None
        rows.append({
            "iss_dt": iss.vr_date, "worker": _worker_label(c.get(Account, iss.worker_id)),
            "sku": sku, "jobno": job.job_no, "_job_id": job.id, "metal": metal, "item": item,
            "pcs": _dec(iss.share) if iss.share else Decimal(iss.pcs or job.pcs or 0),
            "iss_gwt": _dec(iss.gross_wt) if iss.gross_wt is not None else None,
            "iss_nwt": _dec(iss.net_wt) if iss.net_wt is not None else None,
            "iss_stwt": _dec(iss.stone_wt) or sent_wt or None,
            "rtn_dt": rtn.vr_date if rtn else None,
            "rtn_gwt": _dec(rtn.gross_wt) if rtn and rtn.gross_wt is not None else None,
            "rtn_nwt": _dec(rtn.net_wt) if rtn and rtn.net_wt is not None else None,
            "use_stwt": (sent_wt - back_wt).quantize(D3) if rtn else None,
            "use_pcs": sent_pcs - back_pcs if rtn else None,
            "alwloss": alw, "losswt": loss, "labour": _dec(rtn.labour) if rtn else None,
            "wast_rec": (loss - alw).quantize(D3) if loss is not None and alw is not None
            else None})
    return rows


def refining_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Refining Analysis (§4.12): per PROCESS and WORKER, over the receipts
    in the period - NET FINE (fine of the net issued), SCRAP FINE, LOSS FINE,
    DUST and LOSS % = LOSS FINE / NET FINE x 100. A row with no net fine
    shows no % (the legacy divides by zero: 1,226.64 %)."""
    c = _C(session)
    acc: dict[tuple[str, str], list] = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO])
    q = (select(JobVoucher).where(JobVoucher.kind == "receive", JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to))
    for rcv in session.scalars(q):
        step = c.get(JobStep, rcv.step_id)
        if step is None or not step.weight_bearing:
            continue
        proc = c.get(ManufacturingProcess, step.process_id)
        iss = c.get(JobVoucher, rcv.issue_id)
        job = c.get(Job, rcv.job_id)
        metal = c.get(Metal, job.metal_id)
        frac = costing.purity_fraction(metal) if metal else ZERO
        net_iss = _dec(iss.net_wt) if iss is not None and iss.net_wt is not None else ZERO
        loss = (net_iss - _dec(rcv.net_wt) - _dec(rcv.scrap) - _dec(rcv.dust)) \
            if net_iss else ZERO
        a = acc[(proc.name if proc else "", _worker_label(c.get(Account, rcv.worker_id)))]
        a[0] += (net_iss * frac).quantize(D3)
        a[1] += (_dec(rcv.scrap) * frac).quantize(D3)
        a[2] += (loss * frac).quantize(D3)
        a[3] += (_dec(rcv.dust) * frac).quantize(D3)
    rows = []
    for (proc, worker), (net, scrap, loss, dust) in sorted(
            acc.items(), key=lambda kv: (kv[0][0].lower(), kv[0][1].lower())):
        rows.append({"process": proc, "worker": worker or "(blank)", "net_fine": net,
                     "scrap_fine": scrap, "loss_fine": loss, "dust": dust,
                     "loss_pct": (loss / net * 100).quantize(D2) if net else None,
                     "_negative": loss < 0})
    return rows


def rejection_register(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Rejection Register (§4.10): every receipt with rejected pieces or
    weight (Rej Pcs / Rej Wt on the Mfg receive, 2 Oct B6), with its order."""
    c = _C(session)
    rows = []
    q = (select(JobVoucher).where(JobVoucher.kind == "receive", JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to,
                                  (JobVoucher.rej_pcs > 0) | (JobVoucher.rej_wt > 0))
         .order_by(JobVoucher.vr_date, JobVoucher.vr_no))
    for rcv in session.scalars(q):
        job = c.get(Job, rcv.job_id)
        order = c.get(Order, job.order_id)
        line = session.scalar(select(OrderLine).where(OrderLine.order_id == job.order_id,
                                                      OrderLine.sno == job.line_sno)) \
            if job.order_id else None
        step = c.get(JobStep, rcv.step_id)
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        sku, _item, _metal = _job_names(session, c, job)
        rows.append({"date": rcv.vr_date, "vrno": rcv.vr_no,
                     "ord_no": order.order_no if order else "",
                     "ord_pcs": int(line.pcs or 0) if line else job.pcs, "del_dt": rcv.del_date,
                     "worker": _worker_label(c.get(Account, rcv.worker_id)),
                     "process": proc.name if proc else "", "jobno": job.job_no,
                     "_job_id": job.id, "sku": sku, "explod_pcs": job.pcs,
                     "rej_wt": _dec(rcv.rej_wt), "rej_pcs": int(rcv.rej_pcs or 0),
                     "ord_ref": order.ref if order else "", "line_po": job.c_ref,
                     "type": rcv.rej_type, "remark": rcv.remark})
    return rows


def kundan_register(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """KM Register - "Kundan Register" (§4.16), behind a switch until the
    client says kundan work is done (Q1): receipts on a process named Kundan,
    with gross and net. GHAT, the wastage %s and KUNDAN weight wait for the
    client to explain how kundan is weighed - empty in legacy too."""
    c = _C(session)
    rows = []
    q = (select(JobVoucher).where(JobVoucher.kind == "receive", JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to)
         .order_by(JobVoucher.vr_date, JobVoucher.vr_no))
    for rcv in session.scalars(q):
        step = c.get(JobStep, rcv.step_id)
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        if proc is None or "kundan" not in (proc.name or "").lower():
            continue
        job = c.get(Job, rcv.job_id)
        sku, _item, metal = _job_names(session, c, job)
        acct = c.get(Account, job.account_id)
        rows.append({"date": rcv.vr_date, "vrno": rcv.vr_no, "jobno": job.job_no,
                     "_job_id": job.id, "account": acct.name if acct else "", "sku": sku,
                     "metal": metal, "gross": _dec(rcv.gross_wt), "netwt": _dec(rcv.net_wt),
                     "net_lab": _dec(rcv.labour) or None})
    return rows


# --------------------------------------------------------------------------
# Stone (T-03)
# --------------------------------------------------------------------------
def _stone_type(m: StockMovement) -> str:
    """TYPE on the stone reports: Breakage for broken stones, else Actual
    (stones lost in a job leave no location stock - Loss shows in the Stone
    Loss Register)."""
    return "Breakage" if m.kind == "breakage" else "Actual"


class _Lots:
    """The lot / certificate number a movement came in on (purchase lines)."""

    def __init__(self, session: Session):
        self.s, self.d = session, {}

    def get(self, m: StockMovement) -> str:
        if not m.ref_no or not m.ref_kind or not m.ref_id:
            return ""
        key = (m.ref_kind, m.ref_no, m.ref_id)
        if key not in self.d:
            self.d[key] = self.s.scalar(
                select(InvVoucherLine.lot_no).join(InvVoucher).where(
                    InvVoucher.vr_type == m.ref_kind, InvVoucher.vr_no == m.ref_no,
                    InvVoucherLine.stone_sku_id == m.ref_id)) or ""
        return self.d[key]


def stone_wise_inventory(session: Session, date_from: date, date_to: date,
                         only_negative: bool = False, **_k: Any) -> list[dict[str, Any]]:
    """Stone Wise Inventory - "Stone Wise Balance" (§4.5): per LOCATION, TYPE
    (Actual / Breakage), STONE and LOTNO - opening, in, out, closing in pcs
    and carats. CL = OP + IN - OUT. A negative closing is flagged red (the
    legacy has them everywhere - Data-Request 3e, C-02)."""
    c = _C(session)
    lots = _Lots(session)
    acc: dict[tuple, list] = defaultdict(lambda: [0, ZERO, 0, ZERO, 0, ZERO])
    q = select(StockMovement).where(StockMovement.material_class == "stone",
                                    StockMovement.mv_date <= date_to)
    for m in session.scalars(q):
        loc = c.get(Location, m.location_id)
        sku = c.get(StoneSku, m.ref_id)
        stone = (sku.sku_code if sku else m.ref_text) or ""
        key = (loc.name if loc else "", _stone_type(m), stone, m.size or "", lots.get(m))
        a = acc[key]
        pcs, wt = int(m.pcs or 0), _dec(m.weight)
        if m.mv_date < date_from:
            a[0] += pcs
            a[1] += wt
        elif pcs > 0 or wt > 0:
            a[2] += pcs
            a[3] += wt
        else:
            a[4] -= pcs
            a[5] -= wt
    rows = []
    for (loc, typ, stone, size, lot), a in sorted(acc.items(), key=lambda kv: tuple(
            str(x).lower() for x in kv[0])):
        cl_pcs, cl_wt = a[0] + a[2] - a[4], a[1] + a[3] - a[5]
        neg = cl_pcs < 0 or cl_wt < 0
        if only_negative and not neg:
            continue
        if not any(a) and not cl_pcs and not cl_wt:
            continue
        rows.append({"location": loc, "type": typ, "stone": stone, "size": size, "lotno": lot,
                     "op_pcs": a[0], "op_wt": a[1].quantize(D3), "in_pcs": a[2],
                     "in_wt": a[3].quantize(D3), "out_pcs": a[4], "out_wt": a[5].quantize(D3),
                     "cl_pcs": cl_pcs, "cl_wt": cl_wt.quantize(D3), "_negative": neg,
                     "flag": "⚠ negative" if neg else ""})
    return rows


def stone_daily_touch(session: Session, date_from: date, date_to: date,
                      only_negative: bool = False, **_k: Any) -> list[dict[str, Any]]:
    """Stone Daily Touch Report (§4.8): the stone balance on one day by
    LOCATION, TYPE, SSKU, SIZE, GROUP, STONE; every negative line in red -
    the evidence for Data-Request 3e (RAJAT JI DIA.(-2) -577,482 pcs)."""
    c = _C(session)
    acc: dict[tuple, list] = defaultdict(lambda: [0, ZERO])
    for m in session.scalars(select(StockMovement).where(
            StockMovement.material_class == "stone", StockMovement.mv_date <= date_to)):
        loc = c.get(Location, m.location_id)
        sku = c.get(StoneSku, m.ref_id)
        key = (loc.name if loc else "", _stone_type(m),
               (sku.sku_code if sku else m.ref_text) or "", m.size or "",
               (m.stone_group or "").upper() or production.stone_group_label(
                   session, m.ref_id, m.ref_text), (sku.stone if sku else m.ref_text) or "")
        acc[key][0] += int(m.pcs or 0)
        acc[key][1] += _dec(m.weight)
    rows = []
    for (loc, typ, ssku, size, group, stone), (p, w) in sorted(
            acc.items(), key=lambda kv: tuple(str(x).lower() for x in kv[0])):
        neg = p < 0 or w < 0
        if (not p and not w) or (only_negative and not neg):
            continue
        rows.append({"location": loc, "type": typ, "ssku": ssku, "size": size, "group": group,
                     "stone": stone, "bal_pcs": p, "bal_wt": w.quantize(D3), "_negative": neg,
                     "flag": "⚠ negative" if neg else ""})
    return rows


def sold_stone(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Stone in Sales Register - "Sold Stone" (§4.14): every stone line of
    every ready-stock sale (and Sale ▸ Stone lines). AMOUNT = CTS x PRICE
    (or pcs x price for a per-piece stone)."""
    c = _C(session)
    rows = []
    for l, v in _lines(session, ("rs_sale",), date_from, date_to):
        acct = c.get(Account, v.account_id)
        sku = c.get(ProductSku, l.product_sku_id)
        metal = c.get(Metal, l.metal_id)
        item = c.get(StockItem, l.stock_item_id)
        loc = c.get(Location, l.location_id)
        for st in json.loads(l.stones_json or "[]"):
            label = st.get("label") or ""
            ssku = session.scalar(select(StoneSku).where(StoneSku.sku_code == label))
            rows.append({"date": v.vr_date, "vrno": v.vr_no, "refno": v.ref_no,
                         "account": acct.name if acct else "", "sku": sku.sku_code if sku else "",
                         "metal": metal.name if metal else "", "ssku": label,
                         "barcode": item.stock_no if item else "",
                         "stone": (ssku.stone if ssku else "") or sales.stone_block(st),
                         "shape": ssku.shape if ssku else "",
                         "quality": ssku.quality if ssku else "", "size": st.get("size") or "",
                         "lotno": "", "pcs": int(st.get("pcs") or 0),
                         "cts": _dec(st.get("weight")), "price": _dec(st.get("price")),
                         "unit": "Pcs" if (st.get("unit") or "ct").lower().startswith("pc")
                         else "Cts", "amount": sales.stone_amount(st),
                         "location": loc.name if loc else "", "_job_id": l.job_id})
    for line, v in session.execute(
            select(InvVoucherLine, InvVoucher).join(InvVoucher)
            .where(InvVoucher.vr_type == "stone_sale", InvVoucher.vr_date >= date_from,
                   InvVoucher.vr_date <= date_to)
            .order_by(InvVoucher.vr_date, InvVoucher.vr_no)):
        acct = c.get(Account, v.account_id)
        ssku = c.get(StoneSku, line.stone_sku_id)
        loc = c.get(Location, line.location_id)
        rows.append({"date": v.vr_date, "vrno": v.vr_no, "refno": v.ref_no,
                     "account": acct.name if acct else "", "sku": "", "metal": "",
                     "ssku": (ssku.sku_code if ssku else line.particulars) or "", "barcode": "",
                     "stone": (ssku.stone if ssku else line.particulars) or "",
                     "shape": ssku.shape if ssku else "", "quality": ssku.quality if ssku else "",
                     "size": line.size, "lotno": line.lot_no, "pcs": int(line.pcs or 0),
                     "cts": _dec(line.weight), "price": _dec(line.price),
                     "unit": line.unit or "Cts", "amount": _dec(line.amount),
                     "location": loc.name if loc else "", "_job_id": None})
    rows.sort(key=lambda r: (r["date"], r["vrno"]))
    return rows


def stone_sku_balance(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Stone Summery - "Stone SKU Balance" (§4.25): per SSKU - RECEIPT (in to
    stock in the period), REP.RTN (back from jobs), WIP (in job bags of open
    jobs), ON JOB (with karigars / set in pieces being made), SOLD (Sold
    Stone carats of the period - the two reconcile), RETURN (on sale
    returns), BAL IN HAND (loose at the locations on the To date) and CLIENT
    BAL (out on stone approval with clients). Weights in carats."""
    c = _C(session)
    acc: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "receipt": ZERO, "rep_rtn": ZERO, "wip": ZERO, "on_job": ZERO, "sold": ZERO,
        "ret": ZERO, "bal_in_hand": ZERO, "client_bal": ZERO, "group": ""})
    for m in session.scalars(select(StockMovement).where(
            StockMovement.material_class == "stone", StockMovement.mv_date <= date_to)):
        sku = c.get(StoneSku, m.ref_id)
        key = (sku.sku_code if sku else m.ref_text) or "-"
        a = acc[key]
        a["group"] = a["group"] or (m.stone_group or "").upper()
        wt = _dec(m.weight)
        a["bal_in_hand"] += wt
        if m.mv_date >= date_from and wt > 0 and m.kind != "opening":
            if m.kind == "return":
                a["rep_rtn"] += wt
            else:
                a["receipt"] += wt
    for bl, job in session.execute(select(JobBagLine, Job).join(Job, JobBagLine.job_id == Job.id)
                                   .where(Job.status.in_(("pending", "mapped", "in_progress",
                                                          "complete")))):
        sku = c.get(StoneSku, bl.stone_sku_id)
        a = acc[(sku.sku_code if sku else bl.particulars) or "-"]
        row = production.bag_row(bl)
        a["wip"] += row["bal"][1]
        a["on_job"] += row["iss"][1] - row["back"][1]
    for r in sold_stone(session, date_from, date_to):
        acc[r["ssku"] or "-"]["sold"] += r["cts"]
    for l, v in _lines(session, ("rs_sale_return",), date_from, date_to):
        for st in json.loads(l.stones_json or "[]"):
            acc[st.get("label") or "-"]["ret"] += _dec(st.get("weight"))
    from diagold.services import inventory as INV
    for r in INV.stone_approval_analysis(session, date_from, date_to):
        acc[r["ssku"] or "-"]["client_bal"] += _dec(r["bal_wt"])
    rows = []
    for k, a in sorted(acc.items(), key=lambda kv: kv[0].lower()):
        if not any(v for kk, v in a.items() if kk != "group"):
            continue
        rows.append({"ssku": k, **{kk: (v.quantize(D3) if isinstance(v, Decimal) else v)
                                   for kk, v in a.items()},
                     "_negative": a["bal_in_hand"] < 0})
    return rows
