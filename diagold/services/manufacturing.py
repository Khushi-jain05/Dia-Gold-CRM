"""Manufacturing: Pending for MFG Transfer -> MFG Ready Stock Transfer ->
ready stock -> Item Search, and the delete-and-redo correction path
(28 Sept R10-R12, T-07 / T-08).

* A job is pending for transfer once its last route step is received
  (status ``complete``). Nothing else is listed - if nothing is pending, the
  list is empty (R3).
* The transfer prices each job with :mod:`mfg_pricing` and stores every
  figure on the line, so history never re-prices.
* Saving gives each piece a Stock No (the bar code), In Stock at Primary, and
  moves the job to ``transferred``.
* Deleting a stock item writes a DeletionLog row with everything deleted and
  returns the job to Pending for MFG Transfer.

QC between completion and transfer ("Pending For Qc To Ready Transfer") is not
modelled until the client says what it records (28 Sept Q7).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    DeletionLog,
    Job,
    JobVoucher,
    Location,
    Metal,
    MfgTransfer,
    MfgTransferLine,
    Order,
    ProductSku,
    StockItem,
)
from diagold.services import mfg_pricing, production
from diagold.services.production import ProductionError, next_number

ZERO = Decimal("0")
READY_LOCATION = "Primary"


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


# --------------------------------------------------------------------------
# Pending
# --------------------------------------------------------------------------
def pending_jobs(session: Session) -> list[Job]:
    """Jobs whose last route step is received and not yet in ready stock."""
    return list(session.scalars(
        select(Job).where(Job.status == "complete").order_by(Job.job_no)))


def last_gross(session: Session, job: Job) -> Decimal:
    v = session.scalars(
        select(JobVoucher).where(JobVoucher.job_id == job.id, JobVoucher.kind == "receive",
                                 JobVoucher.gross_wt.is_not(None))
        .order_by(JobVoucher.vr_date.desc(), JobVoucher.vr_time.desc(), JobVoucher.id.desc())
    ).first()
    return _dec(v.gross_wt) if v is not None else ZERO


def job_rejections(session: Session, job: Job) -> tuple[int, Decimal]:
    """Rej Pcs / Rej Wt on the transfer line: everything rejected on the
    job's receipts."""
    pcs, wt = 0, ZERO
    for v in session.scalars(select(JobVoucher).where(JobVoucher.job_id == job.id,
                                                      JobVoucher.kind == "receive")):
        pcs += int(v.rej_pcs or 0)
        wt += _dec(v.rej_wt)
    return pcs, wt


def pending_rows(session: Session) -> list[dict[str, Any]]:
    """Pending For Mfg Transfer, with the legacy grid's columns."""
    rows = []
    for job in pending_jobs(session):
        sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
        client = session.get(Account, job.account_id) if job.account_id else None
        metal = session.get(Metal, job.metal_id) if job.metal_id else None
        stone_value = sum((s.amount for s in mfg_pricing.job_stones(session, job)), ZERO)
        rows.append({
            "job_no": job.job_no, "_job_id": job.id, "sku": sku.sku_code if sku else "",
            "item": (sku.description if sku else "") or "", "c_ref": job.c_ref,
            "metal": metal.name if metal else "", "col": job.colour, "pcs": job.pcs,
            "g_wt": last_gross(session, job), "n_wt": mfg_pricing.latest_net(session, job),
            "client": client.name if client else "stock", "completed": job.completed_on,
            "st_value": stone_value,
        })
    return rows


# --------------------------------------------------------------------------
# Transfer
# --------------------------------------------------------------------------
def price_job(session: Session, job: Job, on_date: date, *, labour_weight: Any = None,
              margin_pct: Any = None, manual_amount: Any = 0,
              is_repair: bool = False) -> mfg_pricing.TransferPrice:
    """Fill Prices for one job - what the transfer grid shows before saving."""
    return mfg_pricing.fill_prices(session, job, on_date, labour_weight=labour_weight,
                                   margin_pct=margin_pct, manual_amount=manual_amount,
                                   zero_tag=is_repair)


D3 = Decimal("0.001")
PAISA = Decimal("0.01")


def _split(total: Decimal, n: int, q: Decimal) -> list[Decimal]:
    """``total`` in ``n`` equal parts at precision ``q``; the last part takes
    the rounding, so the parts add back to the total exactly."""
    total = _dec(total)
    part = (total / n).quantize(q)
    return [part] * (n - 1) + [total - part * (n - 1)]


def _pieces(line: MfgTransferLine, p_cost: Decimal, p_price: Decimal,
            split: bool) -> list[dict[str, Any]]:
    """What each stock piece of a transfer line carries. Split Jobs: one per
    piece, weights / cost / price shared equally (2 Oct T-05); else one for
    the lot."""
    n = int(line.pcs or 1) if split else 1
    if n <= 1:
        return [{"pcs": line.pcs, "gross_wt": _dec(line.gross_wt), "net_wt": _dec(line.net_wt),
                 "cost": _dec(p_cost), "price": _dec(p_price)}]
    g, nw = _split(line.gross_wt, n, D3), _split(line.net_wt, n, D3)
    c, pr = _split(p_cost, n, PAISA), _split(p_price, n, PAISA)
    return [{"pcs": 1, "gross_wt": g[i], "net_wt": nw[i], "cost": c[i], "price": pr[i]}
            for i in range(n)]


def post_transfer(session: Session, lines: list[dict[str, Any]], *,
                  vr_date: date | None = None, ref_no: str = "", remark: str = "",
                  user_id: int | None = None, location_id: int | None = None,
                  split_jobs: bool = False) -> MfgTransfer:
    """Save an MFG Ready Stock Transfer.

    ``lines``: one dict per job - ``job_id`` and optionally ``labour_weight``,
    ``margin_pct``, ``manual_amount``, ``is_repair``. Each line is priced
    here, at the voucher date, so what is stored is what the masters said.
    """
    vr_date = vr_date or date.today()
    if not lines:
        raise ProductionError("Show Pending and pick at least one job to transfer.")
    seen: set[int] = set()
    location = (session.get(Location, location_id) if location_id else
                session.scalar(select(Location).where(Location.name == READY_LOCATION)))
    transfer = MfgTransfer(vr_no=next_number(session, MfgTransfer.vr_no), vr_date=vr_date,
                           ref_no=ref_no, remark=remark, user_id=user_id,
                           split_jobs=bool(split_jobs))
    session.add(transfer)
    session.flush()
    for sno, spec in enumerate(lines, start=1):
        job = session.get(Job, spec.get("job_id"))
        if job is None:
            raise ProductionError(f"Line {sno}: that job no longer exists.")
        if job.id in seen:
            raise ProductionError(f"Job {job.job_no} is on this transfer twice.")
        seen.add(job.id)
        if job.status != "complete":
            raise ProductionError(
                f"Job {job.job_no} is not pending for MFG transfer (status {job.status}) - "
                "its last route step has to be received first.")
        p = price_job(session, job, vr_date, labour_weight=spec.get("labour_weight"),
                      margin_pct=spec.get("margin_pct"),
                      manual_amount=spec.get("manual_amount") or 0,
                      is_repair=bool(spec.get("is_repair")))
        if p.net_wt <= 0:
            raise ProductionError(f"Job {job.job_no} has no received net weight to price.")
        line = MfgTransferLine(transfer_id=transfer.id, sno=sno, job_id=job.id,
                               location_id=location.id if location else None)
        _store_price(session, line, job, p, spec)
        session.add(line)
        session.flush()
        for piece in _pieces(line, p.total, p.price_per_pcs, split_jobs):
            session.add(StockItem(
                stock_no=next_number(session, StockItem.stock_no), job_id=job.id,
                line_id=line.id, product_sku_id=job.product_sku_id,
                location_id=location.id if location else None, pcs=piece["pcs"],
                gross_wt=piece["gross_wt"], net_wt=piece["net_wt"], cost=piece["cost"],
                price=piece["price"], tag_price=p.tag_price if p.tag_price else 0,
                tag_text=p.tag_text if piece["pcs"] == line.pcs else mfg_pricing.tag_display(
                    piece["price"], _tag_rule(session)),
            ))
            session.flush()
        job.status = "transferred"
        session.flush()
    session.refresh(transfer)
    return transfer


def _store_price(session: Session, line: MfgTransferLine, job: Job,
                 p: mfg_pricing.TransferPrice, spec: dict[str, Any]) -> None:
    """Every figure of the priced job goes on the line, so history never
    re-prices."""
    _total, loss_pct, _n = production.job_loss_total(session, job)
    rej_pcs, rej_wt = job_rejections(session, job)
    for key, val in dict(
            pcs=p.pcs, gross_wt=last_gross(session, job), net_wt=p.net_wt, title=p.title,
            fine_wt=p.fine_wt, loss_pct=loss_pct or 0, fine_rate=p.fine_rate,
            metal_rate=p.metal_rate, metal_amount=p.metal_amount,
            stone_amount=p.stone_amount, setting_amount=p.setting_amount,
            ex_metal_amount=p.ex_metal_amount, finding_labour=p.finding_labour,
            labour_rate=p.labour_rate, labour_weight=p.labour_weight, labour=p.labour,
            manual_amount=p.manual_amount, total=p.total, margin_pct=p.margin_pct,
            margin_amount=p.margin_amount, price_per_pcs=p.price_per_pcs,
            total_value=p.total_value, tag_price=p.tag_price, tag_text=p.tag_text,
            is_repair=bool(spec.get("is_repair")), stamp=(spec.get("stamp") or "")[:32],
            rej_pcs=rej_pcs, rej_wt=rej_wt,
            stones_json=json.dumps([{**asdict(s), "amount": str(s.amount)} for s in p.stones],
                                   default=str)).items():
        setattr(line, key, val)


def _tag_rule(session: Session) -> str:
    from diagold.services import settings
    return settings.get_setting(session, mfg_pricing.TAG_DISPLAY_SETTING, "thousands")


def _image(obj) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns} if obj else {}


def _items_of(session: Session, transfer: MfgTransfer) -> list[StockItem]:
    items = stock_for_transfer(session, transfer)
    for it in items:
        if it.status != "in_stock":
            raise ProductionError(
                f"Stock No {it.stock_no} on Vr {transfer.vr_no} is {it.status} - a transfer "
                "can only be changed while every piece on it is still in stock.")
    return items


def transfer_overrides(transfer: MfgTransfer) -> dict[int, dict[str, Any]]:
    """What was typed over Fill Prices on each saved line, by job - to open
    the transfer for editing."""
    return {l.job_id: {"labour_weight": _dec(l.labour_weight), "margin_pct": _dec(l.margin_pct),
                       "manual_amount": _dec(l.manual_amount), "is_repair": bool(l.is_repair),
                       "stamp": l.stamp or ""} for l in transfer.lines}


def update_transfer(session: Session, transfer: MfgTransfer, lines: list[dict[str, Any]], *,
                    vr_date: date | None = None, ref_no: str | None = None,
                    user_id: int | None = None) -> MfgTransfer:
    """Edit a saved transfer (28 Sept §4.9: Add, Edit, Save, Delete): the
    lines are priced again with what is typed now - labour weight, margin,
    manual amount, repair, stamp - at the voucher date. The pieces keep
    their Stock Nos; their cost, price and tag follow the new figures. The
    transfer as it was is kept in the deletion log."""
    items: dict[int, list[StockItem]] = {}
    for it in _items_of(session, transfer):
        items.setdefault(it.line_id, []).append(it)
    by_job = {spec["job_id"]: spec for spec in lines}
    before = {"transfer": _image(transfer), "lines": [_image(l) for l in transfer.lines]}
    if vr_date is not None:
        transfer.vr_date = vr_date
    if ref_no is not None:
        transfer.ref_no = ref_no[:64]
    for line in transfer.lines:
        job = session.get(Job, line.job_id)
        spec = by_job.get(job.id, {})
        p = price_job(session, job, transfer.vr_date, labour_weight=spec.get("labour_weight"),
                      margin_pct=spec.get("margin_pct"),
                      manual_amount=spec.get("manual_amount") or 0,
                      is_repair=bool(spec.get("is_repair")))
        _store_price(session, line, job, p, spec)
        pieces = sorted(items.get(line.id, []), key=lambda i: i.stock_no)
        values = _pieces(line, p.total, p.price_per_pcs, len(pieces) > 1)
        for it, v in zip(pieces, values):
            it.pcs, it.gross_wt, it.net_wt = v["pcs"], v["gross_wt"], v["net_wt"]
            it.cost, it.price = v["cost"], v["price"]
            it.tag_price = p.tag_price
            it.tag_text = p.tag_text if len(pieces) == 1 else mfg_pricing.tag_display(
                v["price"], _tag_rule(session)) if p.tag_price else "0"
    session.add(DeletionLog(user_id=user_id, kind="mfg_transfer_edit",
                            ref=f"MFG Transfer Vr {transfer.vr_no}", reason="edited",
                            before_json=json.dumps(before, default=str)))
    session.flush()
    return transfer


def delete_transfer(session: Session, transfer: MfgTransfer, *,
                    user_id: int | None = None, reason: str = "") -> list[int]:
    """Delete a whole saved transfer: every piece on it leaves stock and its
    job goes back to Pending for MFG Transfer - the same as deleting each
    piece in Item Search. Returns the job numbers."""
    vr = transfer.vr_no
    jobs = []
    first_of_line: dict[int, StockItem] = {}
    for it in _items_of(session, transfer):
        first_of_line.setdefault(it.line_id, it)       # its split siblings go with it
    for it in first_of_line.values():
        job = delete_stock_item(session, it, user_id=user_id,
                                reason=reason or f"MFG Transfer Vr {vr} deleted")
        jobs.append(job.job_no if job else None)
    if session.get(MfgTransfer, transfer.id) is not None:
        session.delete(transfer)
    session.flush()
    return jobs


def stock_for_transfer(session: Session, transfer: MfgTransfer) -> list[StockItem]:
    ids = [l.id for l in transfer.lines]
    return list(session.scalars(select(StockItem).where(StockItem.line_id.in_(ids))
                                .order_by(StockItem.stock_no)))


# --------------------------------------------------------------------------
# Item Search and the correction path
# --------------------------------------------------------------------------
def find_items(session: Session, text: str) -> list[StockItem]:
    """By Stock No, Job No, SKU or Cert No (28 Sept TR8)."""
    text = (text or "").strip()
    q = select(StockItem).join(Job, Job.id == StockItem.job_id).outerjoin(
        ProductSku, ProductSku.id == StockItem.product_sku_id)
    if text:
        conds = [ProductSku.sku_code.ilike(f"%{text}%"), StockItem.cert_no.ilike(f"%{text}%")]
        if text.isdigit():
            conds += [StockItem.stock_no == int(text), Job.job_no == int(text)]
        q = q.where(or_(*conds))
    return list(session.scalars(q.order_by(StockItem.stock_no.desc()).limit(500)))


def item_detail(session: Session, item: StockItem) -> dict[str, Any]:
    """Everything the legacy Item Search shows for one piece."""
    job = session.get(Job, item.job_id)
    line = session.get(MfgTransferLine, item.line_id) if item.line_id else None
    transfer = session.get(MfgTransfer, line.transfer_id) if line else None
    sku = session.get(ProductSku, item.product_sku_id) if item.product_sku_id else None
    client = session.get(Account, job.account_id) if job and job.account_id else None
    loc = session.get(Location, item.location_id) if item.location_id else None
    order = session.get(Order, job.order_id) if job and job.order_id else None
    same_sku = len(session.scalars(select(StockItem.id).where(
        StockItem.product_sku_id == item.product_sku_id,
        StockItem.status == "in_stock")).all()) if item.product_sku_id else 1
    stones = json.loads(line.stones_json) if line else []
    groups: dict[str, list[Decimal]] = {}
    for st in stones:
        g = (st.get("s_type") or "Other").strip() or "Other"
        acc = groups.setdefault(g, [ZERO, ZERO])
        acc[0] += _dec(st.get("weight"))
        acc[1] += _dec(st.get("amount"))
    return {
        "item": item, "job": job, "line": line, "transfer": transfer, "sku": sku,
        "client": client, "order": order, "location": loc, "same_sku_in_stock": same_sku,
        "stones": stones, "stone_groups": groups,
    }


def delete_stock_item(session: Session, item: StockItem, *, user_id: int | None = None,
                      reason: str = "") -> Job:
    """Delete a ready-stock piece: the job returns to Pending for MFG Transfer
    so it can be corrected in Job History and transferred again (R12).
    The deleted item and its priced line are kept whole in the DeletionLog."""
    if item.status != "in_stock":
        raise ProductionError(f"Stock No {item.stock_no} is {item.status}; only a piece "
                              "still in stock can be deleted.")
    job = session.get(Job, item.job_id)
    line = session.get(MfgTransferLine, item.line_id) if item.line_id else None
    transfer = session.get(MfgTransfer, line.transfer_id) if line else None
    # A job split into pieces (Split Jobs) comes back whole: every piece of
    # its line goes together, so the job can be corrected and re-transferred.
    pieces = [item]
    if line is not None:
        pieces = list(session.scalars(select(StockItem).where(StockItem.line_id == line.id)
                                      .order_by(StockItem.stock_no)))
        for other in pieces:
            if other.status != "in_stock":
                raise ProductionError(
                    f"Stock No {other.stock_no}, split from the same job, is {other.status} - "
                    "the job cannot come back while one of its pieces is out.")

    def image(obj) -> dict[str, Any]:
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns} if obj else {}

    session.add(DeletionLog(
        user_id=user_id, kind="stock_item",
        ref=f"Stock No {', '.join(str(i.stock_no) for i in pieces)}"[:64], reason=reason,
        before_json=json.dumps({"stock_items": [image(i) for i in pieces],
                                "transfer_line": image(line),
                                "transfer_vr_no": transfer.vr_no if transfer else None,
                                "job_no": job.job_no if job else None}, default=str),
    ))
    for other in pieces:
        session.delete(other)
    if line is not None:
        session.delete(line)
    session.flush()
    if transfer is not None:
        session.refresh(transfer)
        if not transfer.lines:
            session.delete(transfer)
    if job is not None and job.status == "transferred":
        job.status = "complete"
    session.flush()
    return job


# --------------------------------------------------------------------------
# Day book
# --------------------------------------------------------------------------
def transfer_day_book(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    rows = []
    for t in session.scalars(select(MfgTransfer).where(MfgTransfer.vr_date >= date_from,
                                                       MfgTransfer.vr_date <= date_to)
                             .order_by(MfgTransfer.vr_date, MfgTransfer.vr_no)):
        for l in t.lines:
            job = session.get(Job, l.job_id)
            sku = session.get(ProductSku, job.product_sku_id) if job and job.product_sku_id else None
            item = session.scalar(select(StockItem).where(StockItem.line_id == l.id))
            rows.append({
                "date": t.vr_date, "vrno": t.vr_no, "job_no": job.job_no if job else "",
                "_job_id": job.id if job else None, "sku": sku.sku_code if sku else "",
                "stock_no": item.stock_no if item else "", "pcs": l.pcs,
                "g_wt": _dec(l.gross_wt), "n_wt": _dec(l.net_wt),
                "metal_amt": _dec(l.metal_amount), "stone_amt": _dec(l.stone_amount),
                "labour": _dec(l.labour), "total": _dec(l.total),
                "price": _dec(l.price_per_pcs), "tag": l.tag_text,
            })
    return rows


def ready_stock(session: Session, date_to: date) -> list[dict[str, Any]]:
    """Ready Stock (28 Sept §4.15): every finished piece in stock on a date -
    where it sits, what it cost, its price and tag."""
    rows = []
    q = (select(StockItem).where(StockItem.status == "in_stock")
         .order_by(StockItem.stock_no))
    for item in session.scalars(q):
        line = session.get(MfgTransferLine, item.line_id) if item.line_id else None
        transfer = session.get(MfgTransfer, line.transfer_id) if line else None
        if transfer is not None and transfer.vr_date > date_to:
            continue
        job = session.get(Job, item.job_id)
        sku = session.get(ProductSku, item.product_sku_id) if item.product_sku_id else None
        client = session.get(Account, job.account_id) if job and job.account_id else None
        loc = session.get(Location, item.location_id) if item.location_id else None
        rows.append({
            "stock_no": item.stock_no, "sku": sku.sku_code if sku else "",
            "job_no": job.job_no if job else "", "_job_id": job.id if job else None,
            "client": client.name if client else "stock", "location": loc.name if loc else "",
            "date": transfer.vr_date if transfer else None,
            "vrno": transfer.vr_no if transfer else "", "pcs": item.pcs,
            "g_wt": _dec(item.gross_wt), "n_wt": _dec(item.net_wt),
            "cost": _dec(item.cost), "price": _dec(item.price), "tag": item.tag_text,
            "printed": "Y" if item.tag_printed else "",
        })
    return rows
