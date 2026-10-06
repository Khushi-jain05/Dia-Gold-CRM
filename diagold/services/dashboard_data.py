"""Business dashboard figures (5 Oct §4.16, T-14) - the client's Looker
pages, computed live from the ERP.

1. Department pending - per process, pieces and grams waiting (PND) or in
   work (WIP), with a date-wise series.
2. Daily output - Ghat ready in-house / out-house (grams, SKUs), casting by
   karat, setting (diamond / polki pieces set), setting lead days.
3. Daily sale & return by party.
4. Bills due - receivables pending, by office / branch (the bill's location).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, Job, JobStep, JobVoucher, ManufacturingProcess, Metal)
from diagold.services import production, registers

ZERO = Decimal("0")


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def department_pending(session: Session, date_to: date) -> dict[str, Any]:
    """{"by_process": [(process, pcs, grams)], "by_date": [(date, pcs)],
    "total_pcs", "total_wt"} - every process on the master, in its order."""
    acc: dict[str, list] = {p.name: [0, ZERO] for p in session.scalars(
        select(ManufacturingProcess).where(ManufacturingProcess.is_active.is_(True))
        .order_by(ManufacturingProcess.id))}
    by_date: dict[date, int] = defaultdict(int)
    for r in registers.wip_register(session, date(2000, 1, 1), date_to):
        a = acc.setdefault(r["process"], [0, ZERO])
        a[0] += int(r["pcs"] or 0)
        a[1] += _dec(r["n_wt"])
        if r.get("date"):
            by_date[r["date"]] += int(r["pcs"] or 0)
    rows = [(k, v[0], v[1].quantize(Decimal("0.001"))) for k, v in acc.items()]
    return {"by_process": rows, "by_date": sorted(by_date.items()),
            "total_pcs": sum(r[1] for r in rows), "total_wt": sum((r[2] for r in rows), ZERO)}


def _receives(session: Session, date_from: date, date_to: date, name_has: str):
    q = (select(JobVoucher, JobStep, ManufacturingProcess)
         .join(JobStep, JobVoucher.step_id == JobStep.id)
         .join(ManufacturingProcess, JobStep.process_id == ManufacturingProcess.id)
         .where(JobVoucher.kind == "receive", JobVoucher.vr_date >= date_from,
                JobVoucher.vr_date <= date_to))
    for v, st, p in session.execute(q):
        if name_has in (p.name or "").lower() or name_has in (p.short_code or "").lower():
            yield v, st, p


def daily_output(session: Session, date_from: date, date_to: date) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # Ghat ready: receipts on the Ghat (HandMade) process, in-house vs out-house karigar.
    ghat = {"in-house": [ZERO, set()], "out-house": [ZERO, set()]}
    for v, _st, _p in list(_receives(session, date_from, date_to, "ghat")) or \
            list(_receives(session, date_from, date_to, "handmade")):
        w = session.get(Account, v.worker_id)
        k = "in-house" if w is not None and w.in_house else "out-house"
        job = session.get(Job, v.job_id)
        ghat[k][0] += _dec(v.net_wt)
        ghat[k][1].add(job.product_sku_id)
    out["ghat"] = {k: (v[0].quantize(Decimal("0.001")), len(v[1])) for k, v in ghat.items()}
    cast: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for v, _st, _p in _receives(session, date_from, date_to, "cast"):
        job = session.get(Job, v.job_id)
        m = session.get(Metal, job.metal_id) if job.metal_id else None
        karat = (m.name.split()[0] if m and m.name else "?")
        cast[karat] += _dec(v.net_wt)
    out["casting"] = sorted((k, v.quantize(Decimal("0.001"))) for k, v in cast.items())
    setting = {"DIAMOND": 0, "POLKI": 0, "COLOR STONE": 0, "OTHER": 0}
    lead: list[int] = []
    for v, _st, _p in _receives(session, date_from, date_to, "set"):
        issue = session.get(JobVoucher, v.issue_id) if v.issue_id else None
        if issue is None:
            continue
        lead.append((v.vr_date - issue.vr_date).days)
        for l in production.setting_labour_lines(session, issue, v.vr_date):
            g = production.stone_group_label(session, l.line.stone_sku_id, l.line.particulars)
            setting[g if g in setting else "OTHER"] += l.set_pcs
    out["setting"] = setting
    out["setting_lead_days"] = (Decimal(sum(lead)) / len(lead)).quantize(Decimal("0.1")) \
        if lead else None
    return out


def sale_return_by_party(session: Session, date_from: date,
                         date_to: date) -> list[dict[str, Any]]:
    from diagold.services import sales_reports
    acc: dict[str, list] = defaultdict(lambda: [ZERO, ZERO])
    for r in sales_reports.sales_register(session, date_from, date_to):
        acc[r["particulars"]][0] += _dec(r["total"])
    for r in sales_reports.sales_return_register(session, date_from, date_to):
        acc[r["particulars"]][1] += _dec(r["total"])
    return sorted(({"party": k, "sale": v[0], "return": v[1], "net": v[0] - v[1]}
                   for k, v in acc.items()), key=lambda r: -r["sale"])


def bills_due(session: Session, date_to: date) -> list[dict[str, Any]]:
    """Receivable bills pending, by office / branch (the bill's location),
    with the overdue part."""
    from diagold.services import accounts
    acc: dict[str, list] = defaultdict(lambda: [ZERO, ZERO, 0])
    for r in accounts.outstanding(session, date(2000, 1, 1), date_to, side="receivable"):
        if r["ref_no"] == "On account":
            continue
        a = acc[r["location"] or "Office"]
        a[0] += _dec(r["pnd_amt"])
        if r["overdue"]:
            a[1] += _dec(r["pnd_amt"])
        a[2] += 1
    return [{"office": k, "due": v[0], "overdue": v[1], "bills": v[2]}
            for k, v in sorted(acc.items())]
