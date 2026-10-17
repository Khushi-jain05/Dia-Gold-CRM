"""Repair traceability (9 Oct Session 5 §4.9, §4.21, §4.22; T-06 / TR4).

The legacy data shows one chain for a repaired piece:

    stock piece (often a sales return of the same day)
      -> REPAIR JOB    a new job number that keeps the OLD STOCK NO
      -> MFG TRANSFER  back to ready stock under a NEW STOCK NO, the old
                       gross / net / fine kept next to the new ones

e.g. 09-10-2026: sales returns of stock 41672, 44907, 44593 and 44473 became
repair jobs 29360-29363 the same day; Vr 1047 brought job 28575 (NS-2513)
back as stock 44211, 47.580 / 18.414 / 10.864 against the old 56.072 / 16.924
/ 9.985.

A repair job is a job of a repair order (Repair List) whose line names the
piece. While the job is on the floor the old piece is "repair_job" - out of
stock, not saleable. When the job comes back on an MFG transfer the new piece
points at the old one (``repair_of_id``) and the old one is "repaired",
pointing at its replacement.

The old piece's stones go into the repaired piece with STATUS = OLD; stones
issued to the repair job are NEW (MFG TR Stone [only Repair], 747 rows, all
OLD). That contradicts the 2 Oct note (D8, probable) that stone detail is not
carried forward, so carrying them is a setting, default ON, UNCONFIRMED (Q5).
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Job, Metal, MfgTransfer, MfgTransferLine, Order, ProductSku,
                               StockItem)
from diagold.db.models.sku import Item

ZERO = Decimal("0")
D3 = Decimal("0.001")
# Tools > Option > Manufacturing (9 Oct Q5 - UNCONFIRMED).
CARRY_STONES = "repair.carry_stones"
# Pieces that may become a repair job: in stock (a sales return lands there)
# or already out with a party on a Ready Repair Issue.
TAKES = ("in_stock", "in_repair")


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def carry_stones(session: Session) -> bool:
    from diagold.services import settings
    return settings.opt(CARRY_STONES, session) == "1"


# --------------------------------------------------------------------------
# The job <-> old piece link
# --------------------------------------------------------------------------
def link(session: Session, job: Job, item: StockItem) -> None:
    """Make ``job`` the repair job of ``item``: keep the old Stock No, its
    weights and its stones (status OLD) on the job, and take the piece out
    of stock while it is being repaired."""
    from diagold.services import sales
    from diagold.services.production import ProductionError
    if job.repair_item_id == item.id:
        return
    if job.repair_item_id:
        release(session, job)
    if item.status not in TAKES:
        raise ProductionError(f"Stock No {item.stock_no} is "
                              f"{sales.STATE_LABEL.get(item.status, item.status)} - only a piece "
                              "in stock or out for repair can go into a repair job.")
    other = session.scalar(select(Job).where(Job.repair_item_id == item.id, Job.id != job.id,
                                             Job.status.not_in(("cancelled",))))
    if other is not None and other.status != "transferred":
        raise ProductionError(f"Stock No {item.stock_no} is already in repair job "
                              f"{other.job_no}.")
    info = sales.describe(session, item)
    title = _dec(info["title"])
    net = _dec(item.net_wt)
    stones = [{**st, "status": "OLD"} for st in info["stones"]]
    job.repair_item_id = item.id
    job.old_stock_no = item.stock_no
    job.old_gross_wt = _dec(item.gross_wt)
    job.old_net_wt = net
    job.old_fine_wt = (net * title / 1000).quantize(D3) if title else ZERO
    job.old_stones_json = json.dumps(stones, default=str)
    job.repair_prev_status = item.status
    item.status = "repair_job"
    session.flush()


def release(session: Session, job: Job) -> None:
    """The repair job is cancelled or deleted before it came back: the old
    piece returns to where it was."""
    item = session.get(StockItem, job.repair_item_id) if job.repair_item_id else None
    if item is not None and item.status == "repair_job":
        item.status = job.repair_prev_status or "in_stock"
    job.repair_item_id = None
    session.flush()


def old_stones(session: Session, job: Job) -> list[dict[str, Any]]:
    """The old piece's stones as carried into the repaired piece (OLD), or
    none when the setting is off."""
    if not job.repair_item_id or not carry_stones(session):
        return []
    return json.loads(job.old_stones_json or "[]")


def on_transfer(session: Session, job: Job, line: MfgTransferLine,
                new_items: list[StockItem]) -> None:
    """A repair job priced into stock: the line keeps the old Stock No and
    weights; the new piece points at the old one, the old one is replaced."""
    if not job.repair_item_id:
        return
    line.old_stock_no = job.old_stock_no
    line.old_gross_wt = _dec(job.old_gross_wt)
    line.old_net_wt = _dec(job.old_net_wt)
    line.old_fine_wt = _dec(job.old_fine_wt)
    old = session.get(StockItem, job.repair_item_id)
    for it in new_items:
        it.repair_of_id = job.repair_item_id
    if old is not None:
        old.status = "repaired"
        old.replaced_by_id = new_items[0].id if new_items else None
    session.flush()


def on_transfer_undone(session: Session, job: Job | None) -> None:
    """The repaired piece was deleted (Item Search / transfer delete): the old
    piece is back in the repair job."""
    if job is None or not job.repair_item_id:
        return
    old = session.get(StockItem, job.repair_item_id)
    if old is not None and old.status == "repaired":
        old.status = "repair_job"
        old.replaced_by_id = None
    session.flush()


def is_repair_line(session: Session, line: MfgTransferLine) -> bool:
    if line.is_repair or line.old_stock_no:
        return True
    job = session.get(Job, line.job_id)
    return bool(job and job.repair_item_id)


# --------------------------------------------------------------------------
# The chain, for Item Search
# --------------------------------------------------------------------------
def chain(session: Session, item: StockItem) -> list[StockItem]:
    """Every Stock No the piece has had, oldest first (old stock -> repair
    job -> new stock -> ...)."""
    first = item
    seen = {item.id}
    while first.repair_of_id and first.repair_of_id not in seen:
        prev = session.get(StockItem, first.repair_of_id)
        if prev is None:
            break
        seen.add(prev.id)
        first = prev
    out = [first]
    cur = first
    while cur.replaced_by_id and cur.replaced_by_id not in {i.id for i in out}:
        nxt = session.get(StockItem, cur.replaced_by_id)
        if nxt is None:
            break
        out.append(nxt)
        cur = nxt
    return out


def chain_text(session: Session, item: StockItem) -> str:
    """"41672 -> job 29360 -> 45100" for the Item Search card."""
    items = chain(session, item)
    if len(items) == 1 and item.status != "repair_job":
        return ""
    parts = []
    for it in items:
        parts.append(str(it.stock_no))
        job = session.scalar(select(Job).where(Job.repair_item_id == it.id,
                                               Job.status != "cancelled")
                             .order_by(Job.id.desc()))
        if job is not None:
            parts.append(f"repair job {job.job_no}")
    return " → ".join(parts)


def history_rows(session: Session, item: StockItem) -> list[dict[str, Any]]:
    """The repair links as Item Search history rows: RJ (into a repair job)
    (into a repair job), MF (back under a new Stock No) and REP (repaired from
    an old Stock No)."""
    rows: list[dict[str, Any]] = []
    for job in session.scalars(select(Job).where(Job.repair_item_id == item.id,
                                                 Job.status != "cancelled")):
        order = session.get(Order, job.order_id) if job.order_id else None
        on = order.order_date if order else (job.created_at.date() if job.created_at
                                              else date.today())
        rows.append({"date": on, "vrtype": "RJ", "vrno": job.job_no,
                     "party": f"Repair job {job.job_no}", "location": "", "loss_pct": None,
                     "pcs": item.pcs, "price": _dec(item.price), "amount": _dec(item.cost),
                     "_order": (on, 3, job.id)})
    if item.replaced_by_id:
        new = session.get(StockItem, item.replaced_by_id)
        if new is not None:
            line = session.get(MfgTransferLine, new.line_id) if new.line_id else None
            t = session.get(MfgTransfer, line.transfer_id) if line else None
            on = t.vr_date if t else date.today()
            rows.append({"date": on, "vrtype": "MF", "vrno": t.vr_no if t else "",
                         "party": f"Back as Stock No {new.stock_no}", "location": "",
                         "loss_pct": None, "pcs": new.pcs, "price": _dec(new.price),
                         "amount": _dec(new.cost), "_order": (on, 4, new.id)})
    if item.repair_of_id:
        old = session.get(StockItem, item.repair_of_id)
        if old is not None:
            line = session.get(MfgTransferLine, item.line_id) if item.line_id else None
            t = session.get(MfgTransfer, line.transfer_id) if line else None
            on = t.vr_date if t else date.today()
            rows.append({"date": on, "vrtype": "REP", "vrno": old.stock_no,
                         "party": f"Repaired from Stock No {old.stock_no}", "location": "",
                         "loss_pct": None, "pcs": old.pcs, "price": _dec(old.price),
                         "amount": _dec(old.cost), "_order": (on, -1, old.id)})
    return rows


# --------------------------------------------------------------------------
# Reports (9 Oct §4.9, §4.21, §4.22)
# --------------------------------------------------------------------------
def _names(session: Session, job: Job) -> tuple[str, str, str]:
    sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
    item = session.get(Item, sku.item_id) if sku and sku.item_id else None
    metal = session.get(Metal, job.metal_id) if job.metal_id else None
    return (sku.sku_code if sku else ""), (item.name if item else ""), \
        (metal.name if metal else "")


def wip_repair_items(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """WIP Repair Items: repair jobs not yet back in stock - DATE, NEW JOBNO,
    SKU, ITEM, METAL, OLD STOCK NO."""
    rows = []
    q = (select(Job, Order).join(Order, Order.id == Job.order_id)
         .where(Job.repair_item_id.is_not(None),
                Job.status.not_in(("transferred", "cancelled")),
                Order.order_date >= date_from, Order.order_date <= date_to)
         .order_by(Order.order_date, Job.job_no))
    for job, order in session.execute(q):
        sku, item, metal = _names(session, job)
        rows.append({"date": order.order_date, "job_no": job.job_no, "_job_id": job.id,
                     "sku": sku, "item": item, "metal": metal, "old_stock_no": job.old_stock_no,
                     "old_g": _dec(job.old_gross_wt), "old_n": _dec(job.old_net_wt),
                     "status": job.status, "ord_no": order.order_no})
    return rows


def _repair_lines(session: Session, date_from: date, date_to: date):
    q = (select(MfgTransferLine, MfgTransfer).join(MfgTransfer)
         .where(MfgTransfer.vr_date >= date_from, MfgTransfer.vr_date <= date_to)
         .order_by(MfgTransfer.vr_date, MfgTransfer.vr_no, MfgTransferLine.sno))
    for line, t in session.execute(q):
        if is_repair_line(session, line):
            yield line, t


def mfg_tr_repair(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """MFG TR [only Repair]: repaired pieces back to stock, the new weights
    next to the old ones (old in red) and the difference."""
    rows = []
    for line, t in _repair_lines(session, date_from, date_to):
        job = session.get(Job, line.job_id)
        sku, _item, metal = _names(session, job)
        new = session.scalars(select(StockItem).where(StockItem.line_id == line.id)
                              .order_by(StockItem.stock_no)).all()
        g, n, f = _dec(line.gross_wt), _dec(line.net_wt), _dec(line.fine_wt)
        og, on, of = _dec(line.old_gross_wt), _dec(line.old_net_wt), _dec(line.old_fine_wt)
        rows.append({"vrno": t.vr_no, "date": t.vr_date, "sku": sku, "metal": metal,
                     "job_no": job.job_no, "_job_id": job.id,
                     "stock_no": ", ".join(str(i.stock_no) for i in new),
                     "g_wt": g, "n_wt": n, "fine_wt": f, "old_g": og, "old_n": on,
                     "old_fine": of, "old_stock_no": line.old_stock_no or "",
                     "diff_g": g - og, "diff_n": n - on, "diff_fine": f - of})
    return rows


def mfg_tr_repair_stones(session: Session, date_from: date,
                         date_to: date) -> list[dict[str, Any]]:
    """MFG TR Stone [only Repair]: every stone line of the repaired pieces,
    with STATUS OLD (carried from the old piece) or NEW (added in repair)."""
    from diagold.services import sales
    rows = []
    for line, t in _repair_lines(session, date_from, date_to):
        job = session.get(Job, line.job_id)
        sku, _item, metal = _names(session, job)
        new = session.scalar(select(StockItem.stock_no).where(StockItem.line_id == line.id)
                             .order_by(StockItem.stock_no))
        for st in json.loads(line.stones_json or "[]"):
            label = st.get("label") or ""
            size = st.get("size") or ""
            rows.append({"vrno": t.vr_no, "date": t.vr_date, "sku": sku, "metal": metal,
                         "job_no": job.job_no, "_job_id": job.id, "stock_no": new or "",
                         "group": sales.stone_block(st), "ssku": label,
                         "stone": label.replace(size, "").strip() if size else label,
                         "size": size, "pcs": int(st.get("pcs") or 0),
                         "weight": _dec(st.get("weight")),
                         "status": st.get("status") or "NEW"})
    return rows
