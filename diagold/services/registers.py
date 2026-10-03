"""Loss, Dust and WIP registers (2 Oct Session 3 §4.7, R8 / R9, T-08).

"Kitna loss hua" - the control the owner watches. Every figure here is
derived from the vouchers already posted; nothing is typed:

* Metal Loss Register - one row per received step: issued net - received net
  - scrap - dust, against the allowance (loss_detail, 28 Sept T-04).
* Stone Loss Register - stones broken or lost out of job bags.
* Dust Register - dust and scrap recorded on receipts.
* WIP Register - every job in work: WIP = out with a karigar, PND = waiting
  for its next step; and a process-wise summary of it.
* WIP Stone - the stones held in jobs still in work, out with a karigar or
  still in the bag.

Value (WIP / PND) = net weight x the metal rate on the To date + the stones
in the job at their price - the same engine as Job Costing.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    Job,
    JobBagLine,
    JobBagMovement,
    JobStep,
    JobVoucher,
    Location,
    ManufacturingProcess,
    Metal,
    Order,
    StoneSku,
)
from diagold.services import costing, mfg_pricing, production

ZERO = Decimal("0")
D3 = Decimal("0.001")
PAISA = Decimal("0.01")


def _dec(v: Any) -> Decimal:
    if v is None or v == "":
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


class _Cache:
    """Masters looked up once per run - a year of vouchers repeats them."""

    def __init__(self, session: Session):
        self.s = session
        self._d: dict[tuple, Any] = {}

    def get(self, model, key):
        if key is None:
            return None
        k = (model, key)
        if k not in self._d:
            self._d[k] = self.s.get(model, key)
        return self._d[k]


def _job_cols(c: _Cache, job: Job) -> dict[str, Any]:
    sku = job.product_sku
    metal = c.get(Metal, job.metal_id)
    order = c.get(Order, job.order_id)
    client = c.get(Account, job.account_id)
    return {"_job_id": job.id, "job_no": job.job_no, "sku": sku.sku_code if sku else "",
            "cref": job.c_ref, "metal": metal.name if metal else "", "col": job.colour,
            "pcs": job.pcs, "ord_no": order.order_no if order else "",
            "ord_date": order.order_date if order else None,
            "ref_no": order.ref if order else "", "ccode": client.code if client else "",
            "group": (sku.category if sku else "") or ""}


def _fine(metal: Metal | None, wt: Decimal) -> Decimal:
    return costing.fine_metal_weight(metal, wt).quantize(D3) if metal else ZERO


# --------------------------------------------------------------------------
# Metal Loss Register
# --------------------------------------------------------------------------
def metal_loss_register(session: Session, date_from: date, date_to: date) -> list[dict]:
    c = _Cache(session)
    rows = []
    q = (select(JobVoucher).where(JobVoucher.kind == "receive",
                                  JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to)
         .order_by(JobVoucher.vr_date, JobVoucher.vr_no))
    for r in session.scalars(q):
        issue = c.get(JobVoucher, r.issue_id)
        step = c.get(JobStep, r.step_id)
        if step is None or not step.weight_bearing:
            continue
        proc = c.get(ManufacturingProcess, step.process_id)
        d = production.loss_detail(proc, issue, r)
        if d is None:
            continue
        job = c.get(Job, r.job_id)
        metal = c.get(Metal, job.metal_id)
        worker = c.get(Account, r.worker_id)
        rows.append({
            **_job_cols(c, job), "date": r.vr_date, "vrno": r.vr_no,
            "worker": worker.name if worker else "", "process": proc.name if proc else "",
            "iss_net": _dec(issue.net_wt) if issue and issue.net_wt is not None else None,
            "rcv_net": _dec(r.net_wt), "scrap": _dec(r.scrap) or None,
            "dust": _dec(r.dust) or None, "loss": d.loss, "loss_pct": d.loss_pct,
            "alw_pct": d.allow_pct, "alw_wt": d.allowed, "excess": d.excess,
            "fine_loss": _fine(metal, d.loss), "_negative": d.excess > 0,
        })
    return rows


# --------------------------------------------------------------------------
# Stone Loss Register
# --------------------------------------------------------------------------
def stone_loss_register(session: Session, date_from: date, date_to: date) -> list[dict]:
    """Stones broken or lost out of job bags, valued at the stone's price."""
    c = _Cache(session)
    rows = []
    q = (select(JobBagMovement, JobBagLine).join(JobBagLine)
         .where(JobBagMovement.kind.in_(("break", "lost")),
                JobBagMovement.mv_date >= date_from, JobBagMovement.mv_date <= date_to)
         .order_by(JobBagMovement.mv_date, JobBagMovement.id))
    for m, line in session.execute(q):
        job = c.get(Job, line.job_id)
        sku = c.get(StoneSku, line.stone_sku_id)
        price, unit = production.stone_price(session, line.stone_sku_id)
        voucher = c.get(JobVoucher, m.ref_id) if m.ref_kind == production.VOUCHER_REF else None
        step = c.get(JobStep, voucher.step_id) if voucher else None
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        worker = c.get(Account, m.worker_id)
        loc = c.get(Location, m.location_id or line.source_location_id)
        rows.append({
            **_job_cols(c, job), "date": m.mv_date, "vrno": voucher.vr_no if voucher else "",
            "kind": "Broken" if m.kind == "break" else "Lost",
            "worker": worker.name if worker else "", "process": proc.name if proc else "",
            "location": loc.name if loc else "", "ssku": sku.sku_code if sku else "",
            "stone": line.particulars, "size": line.size, "st_pcs": int(m.pcs or 0),
            "weight": _dec(m.weight), "price": price, "unit": unit,
            "amount": production.stone_amount(price, unit, int(m.pcs or 0), _dec(m.weight)),
            "s_type": line.s_type,
        })
    return rows


# --------------------------------------------------------------------------
# Dust Register
# --------------------------------------------------------------------------
def dust_register(session: Session, date_from: date, date_to: date) -> list[dict]:
    c = _Cache(session)
    rows = []
    q = (select(JobVoucher).where(JobVoucher.kind == "receive",
                                  JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to,
                                  (JobVoucher.dust > 0) | (JobVoucher.scrap > 0))
         .order_by(JobVoucher.vr_date, JobVoucher.vr_no))
    for r in session.scalars(q):
        job = c.get(Job, r.job_id)
        step = c.get(JobStep, r.step_id)
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        metal = c.get(Metal, job.metal_id)
        worker = c.get(Account, r.worker_id)
        dust, scrap = _dec(r.dust), _dec(r.scrap)
        rows.append({
            **_job_cols(c, job), "date": r.vr_date, "vrno": r.vr_no,
            "worker": worker.name if worker else "", "process": proc.name if proc else "",
            "dust": dust, "scrap": scrap, "dust_fine": _fine(metal, dust),
            "scrap_fine": _fine(metal, scrap),
        })
    return rows


# --------------------------------------------------------------------------
# WIP Register
# --------------------------------------------------------------------------
def _job_value(session: Session, job: Job, net: Decimal, on_date: date) -> Decimal:
    """Metal at the day's rate + the stones in the job at their price."""
    metal_rate = production.metal_price(session, job.metal_id, on_date)
    stones = sum((s.amount for s in mfg_pricing.job_stones(session, job)), ZERO)
    return ((net * metal_rate) + stones).quantize(PAISA)


def wip_register(session: Session, date_from: date, date_to: date) -> list[dict]:
    """Every job in work as on the To date. WIP = out with a karigar on an
    issue not yet received; PND = waiting for its next step to be issued."""
    c = _Cache(session)
    rows = []
    for job in session.scalars(select(Job).where(Job.status.in_(("mapped", "in_progress")))
                               .order_by(Job.job_no)):
        step, issue = production.current_step(session, job)
        if step is None:
            continue
        proc = c.get(ManufacturingProcess, step.process_id)
        metal = c.get(Metal, job.metal_id)
        loss, _pct, _n = production.job_loss_total(session, job)
        base = {**_job_cols(c, job), "process": proc.name if proc else "",
                "size": production._order_line_size(session, job), "loss": loss or None}
        if issue is not None:
            if issue.vr_date > date_to:
                continue
            worker = c.get(Account, issue.worker_id)
            gross = _dec(issue.gross_wt) if issue.gross_wt is not None else None
            net = _dec(issue.net_wt) if issue.net_wt is not None else \
                production.last_weights(session, job)[1]
            rows.append({**base, "type": "WIP", "date": issue.vr_date, "vrno": issue.vr_no,
                         "particulars": worker.name if worker else "", "g_wt": gross,
                         "n_wt": net, "fine_wt": _fine(metal, _dec(net)) if net else None,
                         "st_wt": _dec(issue.stone_wt) or None,
                         "ex_wt": _dec(issue.extra) or None,
                         "find_wt": _dec(issue.finding) or None,
                         "mould_wt": _dec(issue.mould) or None,
                         "value": _job_value(session, job, _dec(net), date_to)})
        else:
            last = session.scalars(select(JobVoucher).where(JobVoucher.job_id == job.id)
                                   .order_by(JobVoucher.vr_date.desc(),
                                             JobVoucher.id.desc())).first()
            gross, net = production.last_weights(session, job)
            rows.append({**base, "type": "PND", "date": last.vr_date if last else job.mapped_on,
                         "vrno": last.vr_no if last else "", "particulars": "",
                         "g_wt": gross, "n_wt": net,
                         "fine_wt": _fine(metal, _dec(net)) if net else None,
                         "st_wt": None, "ex_wt": None, "find_wt": None, "mould_wt": None,
                         "value": _job_value(session, job, _dec(net), date_to)})
    return rows


def wip_process_summary(session: Session, date_from: date, date_to: date) -> list[dict]:
    """The WIP Register by process: PENDING pcs / G / N / value, WIP pcs / G /
    N / stone / finding / mould / extra / value, totals and karigars at work.
    Every process on the master is listed (RECTIFICATION, Assamble, KHUDAI,
    DANK CHANGE, Repair HM … too), in its master order."""
    acc: dict[str, dict[str, Any]] = {}
    workers: dict[str, set[str]] = defaultdict(set)
    for p in session.scalars(select(ManufacturingProcess).where(
            ManufacturingProcess.is_active.is_(True)).order_by(ManufacturingProcess.id)):
        acc.setdefault(p.name, {})
    for r in wip_register(session, date_from, date_to):
        a = acc.setdefault(r["process"], {})
        t = "pnd" if r["type"] == "PND" else "wip"
        for k, v in (("pcs", r["pcs"]), ("g", r["g_wt"]), ("n", r["n_wt"]),
                     ("val", r["value"])):
            a[f"{t}_{k}"] = a.get(f"{t}_{k}", ZERO) + _dec(v)
        if t == "wip":
            for k in ("st_wt", "find_wt", "mould_wt", "ex_wt"):
                a[k] = a.get(k, ZERO) + _dec(r[k])
            workers[r["process"]].add(r["particulars"])
    rows = []
    for name, a in acc.items():
        rows.append({
            "process": name,
            "pnd_pcs": a.get("pnd_pcs"), "pnd_g": a.get("pnd_g"), "pnd_n": a.get("pnd_n"),
            "pnd_val": a.get("pnd_val"), "wip_pcs": a.get("wip_pcs"), "wip_g": a.get("wip_g"),
            "wip_n": a.get("wip_n"), "st_wt": a.get("st_wt"), "find_wt": a.get("find_wt"),
            "mould_wt": a.get("mould_wt"), "ex_wt": a.get("ex_wt"),
            "wip_val": a.get("wip_val"),
            "tot_pcs": _dec(a.get("pnd_pcs")) + _dec(a.get("wip_pcs")) or None,
            "tot_val": _dec(a.get("pnd_val")) + _dec(a.get("wip_val")) or None,
            "tot_wrk": len(workers.get(name, ())) or None,
        })
    return rows


# --------------------------------------------------------------------------
# WIP Stone
# --------------------------------------------------------------------------
def wip_stone(session: Session, date_from: date, date_to: date) -> list[dict]:
    """Stones held in jobs still in work: out with a karigar (WIP, with his
    process) or still in the job bag (BAG)."""
    c = _Cache(session)
    rows = []
    jobs = session.scalars(select(Job).where(Job.status.in_(("mapped", "in_progress")))
                           .order_by(Job.job_no)).all()
    for job in jobs:
        step, issue = production.current_step(session, job)
        proc = c.get(ManufacturingProcess, step.process_id) if step else None
        for row in production.bag_ledger(session, job):
            line = row.line
            sku = c.get(StoneSku, line.stone_sku_id)
            price, unit = production.stone_price(session, line.stone_sku_id)
            loc = c.get(Location, line.source_location_id)
            group = production.stone_group_label(session, line.stone_sku_id, line.particulars)
            base = {**_job_cols(c, job), "location": loc.name if loc else "",
                    "stone_group": group, "barcode": "", "stone": line.particulars,
                    "quality": sku.quality if sku else "", "ssku": sku.sku_code if sku else "",
                    "size": line.size, "lot_no": "", "price": price, "unit": unit}
            # out with karigars: issued less back, per karigar
            out: dict[int | None, list] = {}
            for m in line.movements:
                if m.mv_date > date_to or m.kind not in ("iss", "back"):
                    continue
                o = out.setdefault(m.worker_id, [0, ZERO])
                sign = 1 if m.kind == "iss" else -1
                o[0] += sign * int(m.pcs or 0)
                o[1] += sign * _dec(m.weight)
            for wid, (pcs, wt) in out.items():
                if pcs <= 0 and wt <= 0:
                    continue
                worker = c.get(Account, wid)
                rows.append({**base, "type": "WIP", "st_pcs": pcs, "weight": wt,
                             "amount": production.stone_amount(price, unit, pcs, wt),
                             "process": proc.name if proc and issue else "",
                             "worker": worker.name if worker else ""})
            bal_pcs, bal_wt = row["bal"]
            if bal_pcs > 0 or bal_wt > 0:
                rows.append({**base, "type": "BAG", "st_pcs": bal_pcs, "weight": bal_wt,
                             "amount": production.stone_amount(price, unit, bal_pcs, bal_wt),
                             "process": "", "worker": ""})
    return rows
