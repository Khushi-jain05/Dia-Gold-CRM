"""Data behind the Production-Planning reports (18 September session).

Every function takes a session and a date range and returns plain rows
(list of dicts) for the report engine in ``ui/reports.py``. They load in bulk
- one query for jobs, one for vouchers, one for movements - because the
legacy app froze for 72 s on Job Analysis over ~4,500 jobs (TR7).

Definitions that the client has not yet confirmed are marked ASSUMPTION and
listed in the 18 Sept notes as C-01 / Q1, Q2, Q8.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    InventoryReturn,
    Job,
    JobBagLine,
    JobVoucher,
    Location,
    ManufacturingProcess,
    Metal,
    Order,
    OrderLine,
    ProductSku,
    StockMovement,
    StoneSku,
)
from diagold.services import production as P

ZERO = Decimal("0")
OPEN_STATUSES = ("pending", "mapped", "in_progress")   # ASSUMPTION: cancelled is not open (C-01a)


def fy_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    return start, date(start.year + 1, 3, 31)


# --------------------------------------------------------------------------
# shared loaders
# --------------------------------------------------------------------------
def _load_jobs(session: Session, statuses: tuple[str, ...] | None = None) -> list[Job]:
    stmt = select(Job)
    if statuses:
        stmt = stmt.where(Job.status.in_(statuses))
    return list(session.scalars(stmt.order_by(Job.job_no)))


def _orders(session: Session) -> dict[int, Order]:
    return {o.id: o for o in session.scalars(select(Order))}


def _clients(session: Session) -> dict[int, Account]:
    return {a.id: a for a in session.scalars(select(Account))}


def _processes(session: Session) -> dict[int, ManufacturingProcess]:
    return {p.id: p for p in session.scalars(select(ManufacturingProcess))}


def _prod_due(job: Job, order: Order | None) -> date | None:
    """PROD DUE: the job's production delivery date, else the order's delivery
    date, else the order date. ASSUMPTION - the client used both words (Q2)."""
    return job.prod_del_date or (order.delivery_date if order else None) \
        or (order.order_date if order else None)


def _created(job: Job, order: Order | None) -> date:
    if order is not None:
        return order.order_date
    return job.created_at.date() if job.created_at else date.today()


def _open_on(job: Job, order: Order | None, day: date) -> bool:
    if job.status == "cancelled":
        return False
    if _created(job, order) > day:
        return False
    return job.completed_on is None or job.completed_on > day


def _day_keys(date_from: date, date_to: date, cap: int = 31) -> list[date]:
    days = []
    d = date_from
    while d <= date_to and len(days) < cap:
        days.append(d)
        d += timedelta(days=1)
    return days


def day_label(d: date) -> str:
    return d.strftime("%d-%m-%y")


# --------------------------------------------------------------------------
# Job Analysis (T-02)
# --------------------------------------------------------------------------
def job_analysis(session: Session, date_from: date, date_to: date,
                 late_only: bool = False) -> list[dict[str, Any]]:
    """Open jobs with overdays as of ``date_from``, one column per day in the
    range (1 = open that day). ``late_only`` switches to the Google-Sheet
    view: completed jobs that missed their due date, with days late."""
    as_of = date_from
    orders = _orders(session)
    clients = _clients(session)
    days = _day_keys(date_from, date_to)
    rows = []
    for job in _load_jobs(session):
        order = orders.get(job.order_id) if job.order_id else None
        due = _prod_due(job, order)
        if late_only:
            if job.status != "complete" or not job.completed_on or not due:
                continue
            late = (job.completed_on - due).days
            if late <= 0:
                continue
        else:
            if job.status not in OPEN_STATUSES or _created(job, order) > as_of:
                continue
            late = (as_of - due).days if due else None
        client = clients.get(job.account_id) if job.account_id else None
        row: dict[str, Any] = {
            "job_no": job.job_no,
            "sku": job.product_sku.sku_code if job.product_sku else "",
            "ord_no": order.order_no if order else "",
            "orddate": order.order_date if order else None,
            "refno": order.ref if order else "",
            "client": client.name if client else "stock",
            "prod_due": due,
            "overdays": late,
            "delivered": job.completed_on if late_only else None,
            "_job_id": job.id,
        }
        total = 0
        for d in days:
            v = 1 if _open_on(job, order, d) else 0
            row[day_label(d)] = v
            total += v
        row["total"] = total
        rows.append(row)
    rows.sort(key=lambda r: (r["prod_due"] or date.max, r["job_no"]))
    return rows


# --------------------------------------------------------------------------
# Process Analysis (T-03)
# --------------------------------------------------------------------------
def _current_steps(session: Session, jobs: list[Job]) -> dict[int, Any]:
    """Job id -> its current route step.

    ASSUMPTION (C-01b): the last step issued but not yet received; if nothing
    is out, the first step that has not been received.
    """
    job_ids = [j.id for j in jobs]
    if not job_ids:
        return {}
    vouchers = session.scalars(
        select(JobVoucher).where(JobVoucher.job_id.in_(job_ids)).order_by(JobVoucher.id)
    ).all()
    issued: dict[int, set[int]] = defaultdict(set)     # step_id -> open issue ids
    received_steps: set[int] = set()
    by_id = {v.id: v for v in vouchers}
    for v in vouchers:
        if v.kind == "issue":
            issued[v.step_id].add(v.id)
    for v in vouchers:
        if v.kind == "receive":
            received_steps.add(v.step_id)
            if v.issue_id in issued.get(v.step_id, set()):
                issued[v.step_id].discard(v.issue_id)
    out = {}
    for job in jobs:
        current = None
        for step in reversed(job.steps):
            if issued.get(step.id):
                current = step
                break
        if current is None:
            for step in job.steps:
                if step.id not in received_steps:
                    current = step
                    break
        if current is not None:
            out[job.id] = current
    return out


def process_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    as_of = date_from
    orders = _orders(session)
    clients = _clients(session)
    procs = _processes(session)
    days = _day_keys(date_from, date_to)
    jobs = [j for j in _load_jobs(session, OPEN_STATUSES) if j.steps]
    current = _current_steps(session, jobs)
    rows = []
    for job in jobs:
        step = current.get(job.id)
        if step is None:
            continue
        order = orders.get(job.order_id) if job.order_id else None
        client = clients.get(job.account_id) if job.account_id else None
        proc = procs.get(step.process_id)
        due = step.due_date
        row: dict[str, Any] = {
            "process": (proc.short_code or proc.name) if proc else "?",
            "_seq": proc.sequence if proc else 999,
            "job_no": job.job_no,
            "sku": job.product_sku.sku_code if job.product_sku else "",
            "ord_no": order.order_no if order else "",
            "orddate": order.order_date if order else None,
            "client": client.name if client else "stock",
            "proc_due": due,
            "overdays": (as_of - due).days if due else None,
            "_job_id": job.id,
        }
        total = 0
        for d in days:
            v = 1 if _open_on(job, order, d) else 0
            row[day_label(d)] = v
            total += v
        row["total"] = total
        rows.append(row)
    rows.sort(key=lambda r: (r["_seq"], r["proc_due"] or date.max, r["job_no"]))
    return rows


# --------------------------------------------------------------------------
# Job Card Analysis - Stone: location x group ledger (T-04)
# --------------------------------------------------------------------------
_BUCKETS = ("opening", "inward", "outward", "closing")


def _empty_bucket() -> dict[str, Any]:
    return {f"{b}_{m}": (0 if m == "pcs" else ZERO)
            for b in _BUCKETS for m in ("pcs", "wt", "val")}


def job_card_analysis_stone(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """OPENING + INWARD - OUTWARD = CLOSING per location x stone group.

    Opening = the "opening" rows plus everything dated before the period.
    Returns from job bags count as inward (client: "added back to his
    balance"); breakage counts as outward. Closing is derived, never stored.
    """
    locs = {l.id: l for l in session.scalars(select(Location))}
    movements = session.scalars(
        select(StockMovement).where(StockMovement.material_class == "stone",
                                    StockMovement.mv_date <= date_to)
    ).all()
    acc: dict[tuple[int, str], dict[str, Any]] = {}
    for m in movements:
        key = (m.location_id, m.stone_group or P.OTHER_GROUP)
        b = acc.setdefault(key, _empty_bucket())
        pcs, wt, val = int(m.pcs or 0), Decimal(str(m.weight or 0)), Decimal(str(m.value or 0))
        if m.kind == "opening" or m.mv_date < date_from:
            bucket = "opening"
            sign = 1
        elif pcs >= 0 and wt >= 0:
            bucket, sign = "inward", 1
        else:
            bucket, sign = "outward", -1
        b[f"{bucket}_pcs"] += sign * pcs
        b[f"{bucket}_wt"] += sign * wt
        b[f"{bucket}_val"] += sign * val
    rows = []
    for (loc_id, group), b in sorted(acc.items(), key=lambda kv: (
            locs[kv[0][0]].name if kv[0][0] in locs else "", kv[0][1])):
        for m in ("pcs", "wt", "val"):
            b[f"closing_{m}"] = b[f"opening_{m}"] + b[f"inward_{m}"] - b[f"outward_{m}"]
        row = {"location": locs[loc_id].name if loc_id in locs else str(loc_id),
               "group": group, "_location_id": loc_id,
               "_negative": b["closing_pcs"] < 0 or b["closing_wt"] < 0}
        row.update(b)
        rows.append(row)
    return rows


def stock_drilldown(session: Session, location_id: int, group: str,
                    date_from: date, date_to: date) -> list[dict[str, Any]]:
    """The vouchers behind one location x group cell."""
    locs = {l.id: l for l in session.scalars(select(Location))}
    rows = []
    for m in session.scalars(
        select(StockMovement).where(StockMovement.location_id == location_id,
                                    StockMovement.stone_group == group,
                                    StockMovement.mv_date <= date_to)
        .order_by(StockMovement.mv_date, StockMovement.id)
    ):
        sku = session.get(StoneSku, m.ref_id) if m.ref_id else None
        job = session.get(Job, m.job_id) if m.job_id else None
        rows.append({
            "date": m.mv_date, "kind": m.kind, "vr": m.ref_no or "", "ref": m.ref_kind,
            "ssku": sku.sku_code if sku else m.ref_text, "size": m.size,
            "job_no": job.job_no if job else "", "pcs": m.pcs, "weight": m.weight,
            "value": m.value, "location": locs[m.location_id].name if m.location_id in locs else "",
            "bucket": "opening" if (m.kind == "opening" or m.mv_date < date_from) else "period",
        })
    return rows


# --------------------------------------------------------------------------
# Inv Rtn O/s Stone (T-05) and the return day book
# --------------------------------------------------------------------------
def inv_rtn_os_stone(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Stones still lying in the bags of unfinished jobs - outstanding until
    the job card is finished or the stones are returned (D3)."""
    orders = _orders(session)
    clients = _clients(session)
    locs = {l.id: l for l in session.scalars(select(Location))}
    cache: dict = {}
    rows = []
    for job in _load_jobs(session, OPEN_STATUSES):
        order = orders.get(job.order_id) if job.order_id else None
        if order is not None and not (date_from <= order.order_date <= date_to):
            continue
        client = clients.get(job.account_id) if job.account_id else None
        for b in P.bag_ledger(session, job):
            bal_pcs, bal_wt = b["bal"]
            if bal_pcs <= 0 and bal_wt <= 0:
                continue
            sku = session.get(StoneSku, b.line.stone_sku_id) if b.line.stone_sku_id else None
            price, unit = P.stone_price(session, b.line.stone_sku_id)
            rows.append({
                "location": locs[b.line.source_location_id].name
                if b.line.source_location_id in locs else "",
                "job_no": job.job_no, "sku": job.product_sku.sku_code if job.product_sku else "",
                "cref": job.c_ref, "ssku": sku.sku_code if sku else b.line.particulars,
                "size": b.line.size, "lotno": "", "stype": b.line.s_type,
                "type": P.stone_group_label(session, b.line.stone_sku_id, b.line.particulars, cache),
                "pcs": bal_pcs, "weight": bal_wt, "price_unit": f"{price} / {unit}" if price else unit,
                "amount": P.stone_amount(price, unit, bal_pcs, bal_wt),
                "ccode": client.code if client else "", "_job_id": job.id,
            })
    return rows


def inv_rtn_stone_day_book(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """What was returned (or broken) each day, from which bag, to which
    location - every return, whether posted on the return voucher or from the
    Job Card Bag screen."""
    locs = {l.id: l for l in session.scalars(select(Location))}
    rows = []
    for m in session.scalars(
        select(StockMovement).where(StockMovement.material_class == "stone",
                                    StockMovement.kind.in_(("return", "breakage")),
                                    StockMovement.mv_date >= date_from,
                                    StockMovement.mv_date <= date_to)
        .order_by(StockMovement.mv_date, StockMovement.id)
    ):
        sku = session.get(StoneSku, m.ref_id) if m.ref_id else None
        job = session.get(Job, m.job_id) if m.job_id else None
        price, unit = P.stone_price(session, m.ref_id)
        rows.append({
            "date": m.mv_date, "vrno": m.ref_no or "",
            "location": locs[m.location_id].name if m.location_id in locs else "",
            "type": "Breakage" if m.kind == "breakage" else "Returned",
            "ssku": sku.sku_code if sku else m.ref_text, "size": m.size,
            "stone": m.stone_group, "job_no": job.job_no if job else "",
            "pcs": abs(int(m.pcs or 0)), "weight": abs(Decimal(str(m.weight or 0))),
            "price_unit": f"{price} / {unit}" if price else unit,
            "amount": abs(Decimal(str(m.value or 0))), "_job_id": m.job_id,
        })
    return rows


# --------------------------------------------------------------------------
# Job O/s - Stone and the day books (T-06)
# --------------------------------------------------------------------------
def job_os_stone(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """One row per job x stone requirement, for orders in the range.
    PND = REQ - issued into the bag; CL = the requirement of a cancelled job."""
    orders = _orders(session)
    locs = {l.id: l for l in session.scalars(select(Location))}
    rows = []
    for job in _load_jobs(session):
        order = orders.get(job.order_id) if job.order_id else None
        if order is None or not (date_from <= order.order_date <= date_to):
            continue
        for b in P.bag_ledger(session, job):
            req_pcs, req_wt = b["req"]
            iss_pcs, iss_wt = b["rcvd"]
            if req_pcs == 0 and req_wt == 0 and iss_pcs == 0:
                continue
            sku = session.get(StoneSku, b.line.stone_sku_id) if b.line.stone_sku_id else None
            cancelled = job.status == "cancelled"
            rows.append({
                "job_no": job.job_no, "sku": job.product_sku.sku_code if job.product_sku else "",
                "location": locs[b.line.source_location_id].name
                if b.line.source_location_id in locs else "",
                "job_pcs": job.pcs, "ssku": sku.sku_code if sku else "",
                "stone": b.line.particulars, "shape": sku.shape if sku else "",
                "quality": sku.quality if sku else "", "size": b.line.size,
                "req_pcs": req_pcs, "req_wt": req_wt, "iss_pcs": iss_pcs, "iss_wt": iss_wt,
                "pnd_pcs": 0 if cancelled else max(req_pcs - iss_pcs, 0),
                "pnd_wt": ZERO if cancelled else max(req_wt - iss_wt, ZERO),
                "cl_pcs": req_pcs if cancelled else 0, "cl_wt": req_wt if cancelled else ZERO,
                "ordno": order.order_no, "orddt": order.order_date, "_job_id": job.id,
            })
    return rows


def job_card_day_book(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """One row per job card created in the range - the full register."""
    orders = _orders(session)
    clients = _clients(session)
    metals = {m.id: m for m in session.scalars(select(Metal))}
    lines = {(l.order_id, l.sno): l for l in session.scalars(select(OrderLine))}
    rows = []
    for job in _load_jobs(session):
        order = orders.get(job.order_id) if job.order_id else None
        day = _created(job, order)
        if not (date_from <= day <= date_to):
            continue
        client = clients.get(job.account_id) if job.account_id else None
        metal = metals.get(job.metal_id) if job.metal_id else None
        line = lines.get((job.order_id, job.line_sno)) if job.order_id else None
        sku = job.product_sku
        rows.append({
            "date": day, "vrno": order.order_no if order else "", "ord_no": order.order_no if order else "",
            "ref_no": order.ref if order else "", "client": client.name if client else "stock",
            "sku": sku.sku_code if sku else "", "design": sku.design_no if sku else "",
            "c_ref": job.c_ref, "metal": f"{metal.name} {metal.print_on_tag}".strip() if metal else "",
            "col": job.colour, "size": line.size if line else "",
            "del_dt": order.delivery_date if order else None, "job_no": job.job_no,
            "job_pcs": job.pcs, "p_del_dt": job.prod_del_date, "open_loc": "",
            "cancel": "Y" if job.status == "cancelled" else "N", "_job_id": job.id,
        })
    return rows


def job_mapping_day_book(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    orders = _orders(session)
    clients = _clients(session)
    rows = []
    for job in _load_jobs(session):
        if not job.mapped_on or not (date_from <= job.mapped_on <= date_to):
            continue
        order = orders.get(job.order_id) if job.order_id else None
        client = clients.get(job.account_id) if job.account_id else None
        dues = [s.due_date for s in job.steps if s.due_date]
        rows.append({
            "date": job.mapped_on, "job_no": job.job_no,
            "sku": job.product_sku.sku_code if job.product_sku else "",
            "client": client.name if client else "stock",
            "ord_no": order.order_no if order else "",
            "route": P.route_string(session, job), "steps": len(job.steps),
            "first_due": min(dues) if dues else None, "last_due": max(dues) if dues else None,
            "status": job.status, "_job_id": job.id,
        })
    return rows


# --------------------------------------------------------------------------
# Job Stock Analysis - lead time (T-07)
# --------------------------------------------------------------------------
def job_stock_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """DAYS = STOCK DT (final receipt) - ORD DT; blank while the job is open."""
    orders = _orders(session)
    clients = _clients(session)
    rows = []
    for job in _load_jobs(session):
        if job.status == "cancelled":
            continue
        order = orders.get(job.order_id) if job.order_id else None
        ord_dt = _created(job, order)
        if not (date_from <= ord_dt <= date_to):
            continue
        client = clients.get(job.account_id) if job.account_id else None
        rows.append({
            "ord_dt": ord_dt, "refno": order.ref if order else "",
            "party": client.name if client else "stock", "job_no": job.job_no,
            "sku": job.product_sku.sku_code if job.product_sku else "",
            "stock_dt": job.completed_on,
            "days": (job.completed_on - ord_dt).days if job.completed_on else None,
            "_job_id": job.id,
        })
    return rows


def lead_time_footer(rows: list[dict[str, Any]]) -> str:
    days = [r["days"] for r in rows if isinstance(r.get("days"), int)]
    if not days:
        return "No finished jobs in the range yet."
    return (f"Finished {len(days)} of {len(rows)} · average {sum(days) / len(days):.1f} days"
            f" · median {median(days):.0f} days")


# --------------------------------------------------------------------------
# Inv O/S - Job O/s % (T-08)
# --------------------------------------------------------------------------
def job_os_pct(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    orders = _orders(session)
    clients = _clients(session)
    rows = []
    for job in _load_jobs(session, OPEN_STATUSES):
        order = orders.get(job.order_id) if job.order_id else None
        if order is not None and not (date_from <= order.order_date <= date_to):
            continue
        client = clients.get(job.account_id) if job.account_id else None
        req = pnd = 0
        for b in P.bag_ledger(session, job):
            req += b["req"][0]
            pnd += max(b["req"][0] - b["rcvd"][0], 0)
        rows.append({
            "job_no": job.job_no, "sku": job.product_sku.sku_code if job.product_sku else "",
            "cref": job.c_ref, "st_pcs": pnd,
            "st_pct": round(pnd * 100 / req) if req else 0,
            # Findings are retired and moulds are not issued per job yet, so
            # nothing is outstanding on either - 100 % as in the legacy rows.
            "find_pcs": 0, "find_pct": 100, "mould_pcs": 0, "mould_pct": 100,
            "ord_no": order.order_no if order else "", "orddt": order.order_date if order else None,
            "ref": order.ref if order else "", "ccode": client.code if client else "",
            "deldt": order.delivery_date if order else None, "_job_id": job.id,
        })
    return rows


# --------------------------------------------------------------------------
# Data quality (T-11) - runs on whatever is in this database
# --------------------------------------------------------------------------
DQ_CHECKS: tuple[tuple[str, str], ...] = (
    ("negative_closing", "Stone balance negative by location x group"),
    ("open_90", "Jobs open more than 90 days"),
    ("weight_drop", "Steps received under 50% of issued, no reject/scrap"),
    ("never_received", "Steps issued but never received"),
    ("bag_negative", "Job bag lines with a negative balance"),
    ("voucher_one", "Return classes still at voucher 1 (metal / mould / finding)"),
)


def data_quality(session: Session, date_from: date, date_to: date,
                 check: str = "all") -> list[dict[str, Any]]:
    today = date.today()
    out: list[dict[str, Any]] = []

    def add(chk: str, key: Any, detail: str, job_id: int | None = None) -> None:
        out.append({"check": dict(DQ_CHECKS)[chk], "key": key, "detail": detail, "_job_id": job_id})

    if check in ("all", "negative_closing"):
        for r in job_card_analysis_stone(session, date_from, date_to):
            if r["_negative"]:
                add("negative_closing", f"{r['location']} / {r['group']}",
                    f"closing {r['closing_pcs']} pcs / {r['closing_wt']} - opening not loaded?")
    orders = _orders(session)
    if check in ("all", "open_90"):
        for job in _load_jobs(session, OPEN_STATUSES):
            order = orders.get(job.order_id) if job.order_id else None
            age = (today - _created(job, order)).days
            if age > 90:
                add("open_90", job.job_no, f"open {age} days, status {job.status}", job.id)
    if check in ("all", "weight_drop", "never_received"):
        procs = _processes(session)
        for job in _load_jobs(session):
            for r in P.history_rows(session, job):
                if r.issue is None:
                    continue
                name = r.process.name if r.process else "?"
                if r.receive is None and check in ("all", "never_received"):
                    add("never_received", job.job_no,
                        f"{name} issued {r.issue.vr_date} Vr {r.issue.vr_no}, nothing back", job.id)
                if r.receive is not None and check in ("all", "weight_drop"):
                    iss = Decimal(str(r.issue.gross_wt or 0))
                    rcv = Decimal(str(r.receive.gross_wt or 0))
                    if iss > 0 and rcv < iss / 2 and not (r.receive.rej_wt or r.receive.scrap):
                        add("weight_drop", job.job_no,
                            f"{name}: {iss} g out, {rcv} g back, no reject/scrap", job.id)
    if check in ("all", "bag_negative"):
        for job in _load_jobs(session):
            for b in P.bag_ledger(session, job):
                if b["bal"][0] < 0 or b["bal"][1] < 0:
                    add("bag_negative", job.job_no,
                        f"{b.line.particulars} {b.line.size}: balance {b['bal']}", job.id)
    if check in ("all", "voucher_one"):
        for cls in ("metal", "mould", "finding"):
            n = session.scalar(select(func.count()).select_from(InventoryReturn)
                               .where(InventoryReturn.material_class == cls)) or 0
            add("voucher_one", cls, f"{n} return voucher(s) - client says this class is not used")
    return out
