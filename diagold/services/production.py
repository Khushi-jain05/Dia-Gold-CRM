"""Order -> job -> route -> vouchers -> bag: the production-planning rules.

Everything the screens do to production data goes through here, so the rules
the client stated on 11 September hold no matter which screen (or test) is
talking:

* saving an order allots one job per line, from one global sequence (TR1);
* a job cannot receive an issue voucher until it has a mapped route;
* every issue and receive names a worker (R7);
* loss per step is issued net weight - received net weight - scrap - dust,
  derived on the fly and never stored (TR4);
* a step that carries no metal (CAD) saves with no weight and no loss (TR5);
* stones in a job's bag are a ledger of movements; balance is derived (TR6);
* a location cannot issue more than it holds, and a job cannot return more
  than it holds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    DefaultProcessStep,
    InventoryReturn,
    InventoryReturnLine,
    Job,
    JobBagLine,
    JobBagMovement,
    JobStep,
    JobVoucher,
    Location,
    ManufacturingProcess,
    MaterialStock,
    Metal,
    Order,
    OrderLine,
    PrintLog,
    ProductSku,
    ProductSkuStone,
    StockMovement,
    StoneGroup,
    StoneInfo,
    StoneIssue,
    StoneIssueLine,
    StoneSize,
    StoneSku,
)

# The client's three heads for stone stock (S1 D4, reaffirmed 18 Sept D9),
# keyed by the Stone Group master's code.
STONE_GROUP_LABELS: dict[str, str] = {"DIA": "DIAMOND", "POLKI": "POLKI", "CS": "COLOR STONE"}
OTHER_GROUP = "OTHER"

ZERO = Decimal("0")
D3 = Decimal("0.001")
D4 = Decimal("0.0001")


class ProductionError(ValueError):
    """A rule the client stated was about to be broken. The message is the
    sentence shown to the person at the screen. A ValueError so the generic
    form dialog can refuse the save with it."""


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def next_number(session: Session, column) -> int:
    """The next free number in an explicit sequence (job no, order no, vr no).

    Live numbers migrate as they are, so this is max + 1, never autoincrement.
    """
    current = session.scalar(select(func.max(column)))
    return int(current or 0) + 1


# --------------------------------------------------------------------------
# Stone reference helpers
# --------------------------------------------------------------------------
def stone_group_label(session: Session, stone_sku_id: int | None,
                      particulars: str = "", cache: dict | None = None) -> str:
    """DIAMOND / POLKI / COLOR STONE for a stone, via the Stone master's group.

    A Stone SKU names its stone in free text ("EMERALD PEAR"); the Stone
    master carries the same name with a group. Text that matches no stone
    (e.g. "daank") lands in OTHER rather than being guessed.
    """
    key = ("sku", stone_sku_id) if stone_sku_id else ("txt", (particulars or "").strip().lower())
    if cache is not None and key in cache:
        return cache[key]
    name = particulars or ""
    if stone_sku_id:
        sku = session.get(StoneSku, stone_sku_id)
        name = (sku.stone or sku.sku_code) if sku else name
    label = OTHER_GROUP
    if name.strip():
        info = session.scalar(select(StoneInfo).where(
            func.lower(StoneInfo.name) == name.strip().lower()))
        if info is None:
            # "POLKI 14-16" -> "POLKI"; "DIA.(-2)" -> starts with DIA
            head = name.strip().split(" ")[0].lower()
            info = session.scalar(select(StoneInfo).where(
                func.lower(StoneInfo.name) == head))
        if info is not None and info.stone_group_id:
            grp = session.get(StoneGroup, info.stone_group_id)
            if grp is not None:
                label = STONE_GROUP_LABELS.get(grp.code.upper(), grp.name.upper())
        elif name.strip().upper().startswith("DIA"):
            label = "DIAMOND"
        elif name.strip().upper().startswith("POLKI"):
            label = "POLKI"
    if cache is not None:
        cache[key] = label
    return label


def stone_price(session: Session, stone_sku_id: int | None) -> tuple[Decimal, str]:
    """(price per unit, unit) for valuing stock. Cost price when the catalogue
    has one, else sale price - inventory is valued at cost (assumption)."""
    if not stone_sku_id:
        return ZERO, "Cts"
    sku = session.get(StoneSku, stone_sku_id)
    if sku is None:
        return ZERO, "Cts"
    price = _dec(sku.cost_price) or _dec(sku.sale_price)
    return price, (sku.per or "Cts")


def stone_amount(price: Decimal, unit: str, pcs: int, weight: Decimal) -> Decimal:
    qty = _dec(pcs) if (unit or "").lower().startswith("pc") else _dec(weight)
    return (price * qty).quantize(Decimal("0.01"))


def parse_order_remark(text: str) -> list[dict[str, Any]]:
    """The legacy keeps a job's stone requirement as text on the order:
    "daank/411/19.92, DIA./241/2.81, POLKI/411/28.75". Parse it into
    (particulars, pcs, weight) lines; anything that does not fit is skipped."""
    out: list[dict[str, Any]] = []
    for part in (text or "").split(","):
        bits = [b.strip() for b in part.strip().split("/")]
        if len(bits) < 2 or not bits[0]:
            continue
        try:
            pcs = int(float(bits[1])) if bits[1] else 0
            wt = Decimal(bits[2]) if len(bits) > 2 and bits[2] else ZERO
        except (ValueError, ArithmeticError):
            continue
        out.append({"particulars": bits[0], "pcs": pcs, "weight": wt})
    return out


# --------------------------------------------------------------------------
# Orders -> jobs
# --------------------------------------------------------------------------
def sync_jobs_for_order(session: Session, order: Order) -> list[Job]:
    """Make the order's jobs match its lines: one job per line (R1).

    A line that already has a job keeps it (and the job picks up any change
    to SKU, metal, pieces or dates); a new line gets the next job number; a
    line that was removed cancels its job - unless the job has moved, in
    which case the save is refused so history is never silently detached.
    """
    session.flush()
    existing = {
        j.line_sno: j for j in session.scalars(
            select(Job).where(Job.order_id == order.id, Job.status != "cancelled")
        )
    }
    seen: set[int] = set()
    jobs: list[Job] = []
    for line in order.lines:
        seen.add(line.sno)
        job = existing.get(line.sno)
        if job is None:
            job = Job(job_no=next_number(session, Job.job_no), order_id=order.id,
                      line_sno=line.sno, status="pending")
            session.add(job)
        job.product_sku_id = line.product_sku_id
        job.account_id = order.account_id
        job.c_ref = line.c_ref
        job.metal_id = line.metal_id
        job.colour = line.colour
        job.pcs = line.pcs or 1
        job.prod_del_date = line.delivery_date or order.delivery_date
        session.flush()
        if not job.id or not session.scalars(
            select(JobBagLine.id).where(JobBagLine.job_id == job.id).limit(1)
        ).first():
            seed_bag_requirements(session, job)
        jobs.append(job)

    for sno, job in existing.items():
        if sno in seen:
            continue
        if _job_has_movements(session, job):
            raise ProductionError(
                f"Line {sno} cannot be removed: job {job.job_no} already has "
                "material issued against it. Cancel the job's vouchers first."
            )
        job.status = "cancelled"
    session.flush()
    return jobs


def delete_order(session: Session, order: Order) -> None:
    """Delete an order together with the jobs its lines allotted.

    An order is deletable only while nothing has happened to it on the
    floor. A job with a voucher posted, stones issued against it, or a
    return booked is history, and history is never detached - the order
    stays and the message says which job holds it up.
    """
    jobs = list(session.scalars(select(Job).where(Job.order_id == order.id)))
    for job in jobs:
        if _job_has_movements(session, job) or session.scalars(
            select(StoneIssue.id).where(StoneIssue.job_id == job.id).limit(1)
        ).first() or session.scalars(
            select(InventoryReturn.id).where(InventoryReturn.job_id == job.id).limit(1)
        ).first():
            raise ProductionError(
                f"Order {order.order_no} cannot be deleted: job {job.job_no} "
                "already has vouchers or stones against it. Cancel those "
                "first, or leave the order in place - it is part of the "
                "job's history."
            )
    for job in jobs:
        for line in session.scalars(select(JobBagLine).where(JobBagLine.job_id == job.id)):
            session.delete(line)
        for log in session.scalars(select(PrintLog).where(PrintLog.job_id == job.id)):
            session.delete(log)
        session.delete(job)           # steps go with it
    for log in session.scalars(select(PrintLog).where(PrintLog.order_id == order.id)):
        session.delete(log)
    session.delete(order)             # lines go with it
    session.flush()


def _job_has_movements(session: Session, job: Job) -> bool:
    if session.scalars(select(JobVoucher.id).where(JobVoucher.job_id == job.id).limit(1)).first():
        return True
    return bool(session.scalars(
        select(JobBagMovement.id).join(JobBagLine)
        .where(JobBagLine.job_id == job.id).limit(1)
    ).first())


def seed_bag_requirements(session: Session, job: Job) -> None:
    """A new job's bag starts with the SKU's stone lines as its requirement,
    so Req and Pnd are visible before a single stone is issued."""
    stones = session.scalars(
        select(ProductSkuStone).where(ProductSkuStone.product_id == job.product_sku_id)
    ).all() if job.product_sku_id else []
    if not stones:
        # No stone grid on the SKU: the order remark may carry the
        # requirement as text (18 Sept R14) - "daank/411/19.92, DIA./241/2.81".
        order = session.get(Order, job.order_id) if job.order_id else None
        for line in parse_order_remark(order.remark if order else ""):
            session.add(JobBagLine(
                job_id=job.id, stone_sku_id=None, particulars=line["particulars"],
                size="", unit="ct",
                req_pcs=line["pcs"] * max(int(job.pcs or 1), 1),
                req_wt=line["weight"] * max(int(job.pcs or 1), 1),
            ))
        session.flush()
        return
    for st in stones:
        sku = session.get(StoneSku, st.stone_sku_id) if st.stone_sku_id else None
        size = session.get(StoneSize, st.size_id) if st.size_id else None
        session.add(JobBagLine(
            # a stone the SKU still names but which no longer exists keeps
            # its description and loses the link, rather than failing the save
            job_id=job.id, stone_sku_id=sku.id if sku else None,
            particulars=(sku.stone if sku else "") or st.description,
            size=(size.name if size else "") or (sku.size if sku else ""),
            s_type=(sku.stone_type if sku else ""),
            unit="ct" if (st.per or "Cts").lower().startswith("ct") else "pcs",
            req_pcs=int(st.pieces or 0) * max(int(job.pcs or 1), 1),
            req_wt=_dec(st.weight_cts) * max(int(job.pcs or 1), 1),
        ))
    session.flush()  # the session runs with autoflush off


# --------------------------------------------------------------------------
# Routes (Job Mapping)
# --------------------------------------------------------------------------
def group_names(session: Session) -> list[str]:
    names = session.scalars(
        select(DefaultProcessStep.group_name).where(DefaultProcessStep.is_active.is_(True))
        .distinct().order_by(DefaultProcessStep.group_name)
    ).all()
    names = [n or "Default" for n in names]
    if "Default" in names:
        names.remove("Default")
        names.insert(0, "Default")
    return names


def group_steps(session: Session, group_name: str) -> list[ManufacturingProcess]:
    rows = session.scalars(
        select(DefaultProcessStep)
        .where(DefaultProcessStep.group_name == group_name,
               DefaultProcessStep.is_active.is_(True))
        .order_by(DefaultProcessStep.step_no)
    ).all()
    out = []
    for r in rows:
        p = session.get(ManufacturingProcess, r.process_id) if r.process_id else None
        if p is not None:
            out.append(p)
    return out


def _step_has_vouchers(session: Session, step: JobStep) -> bool:
    return bool(session.scalars(
        select(JobVoucher.id).where(JobVoucher.step_id == step.id).limit(1)
    ).first())


def map_job(session: Session, job: Job, group_name: str,
            start: date | None = None, days_per_step: int = 1) -> list[JobStep]:
    """Copy a process group's ordered steps onto the job with a due date per
    step. Refused once material has moved on the current route."""
    processes = group_steps(session, group_name)
    if not processes:
        raise ProductionError(
            f"Process group '{group_name}' has no steps. Add them under "
            "Master > Set Default Process first."
        )
    start = start or job.prod_date or date.today()
    rows = [
        {"process_id": p.id,
         "due_date": start + timedelta(days=days_per_step * i)}
        for i, p in enumerate(processes, start=1)
    ]
    return set_job_steps(session, job, rows)


def set_job_steps(session: Session, job: Job, rows: list[dict]) -> list[JobStep]:
    """Replace the job's route with the given (process_id, due_date) rows.

    Steps that already carry vouchers are kept in place - the route may grow
    (a repair step inserted) but history is never cut out from under it.
    """
    session.flush()
    kept = {s.process_id: s for s in job.steps if _step_has_vouchers(session, s)}
    wanted = [r for r in rows if r.get("process_id")]
    if not wanted:
        raise ProductionError("A route needs at least one process step.")
    for pid, step in kept.items():
        if pid not in [r["process_id"] for r in wanted]:
            proc = session.get(ManufacturingProcess, pid)
            raise ProductionError(
                f"'{proc.name if proc else pid}' already has vouchers on this "
                "job and cannot be removed from its route."
            )
    for step in list(job.steps):
        if step.process_id not in kept:
            session.delete(step)
    session.flush()
    used: set[int] = set()
    out: list[JobStep] = []
    for seq, r in enumerate(wanted, start=1):
        pid = int(r["process_id"])
        proc = session.get(ManufacturingProcess, pid)
        if proc is None:
            raise ProductionError("One of the route steps is not a known process.")
        step = kept.get(pid) if pid not in used else None
        used.add(pid)
        if step is None:
            step = JobStep(job_id=job.id, process_id=pid,
                           weight_bearing=bool(proc.weight_bearing))
            session.add(step)
        step.seq = seq
        step.due_date = r.get("due_date")
        out.append(step)
    if job.status == "pending":
        job.status = "mapped"
    if job.mapped_on is None:
        job.mapped_on = date.today()
    session.flush()
    session.refresh(job)
    return out


def copy_route_to_siblings(session: Session, job: Job) -> int:
    """'Copy To All' - apply this job's route to every other job of its order.
    Returns how many jobs were mapped."""
    if not job.steps:
        raise ProductionError(f"Job {job.job_no} has no route to copy yet.")
    if not job.order_id:
        return 0
    rows = [{"process_id": s.process_id, "due_date": s.due_date} for s in job.steps]
    n = 0
    for sibling in session.scalars(
        select(Job).where(Job.order_id == job.order_id, Job.id != job.id,
                          Job.status != "cancelled")
    ):
        set_job_steps(session, sibling, rows)
        n += 1
    return n


def route_string(session: Session, job: Job) -> str:
    """The short form shown in headers: 'HM RHM PP ST FP fs Meena Puwai'."""
    parts = []
    for s in job.steps:
        p = session.get(ManufacturingProcess, s.process_id)
        if p is not None:
            parts.append(p.short_code or p.name)
    return " ".join(parts)


def pending_jobs(session: Session) -> list[Job]:
    """'Pending Jobs For Definition' - allotted, not yet routed (UX4)."""
    return list(session.scalars(
        select(Job).where(Job.status == "pending").order_by(Job.job_no)
    ))


# --------------------------------------------------------------------------
# Issue / receive vouchers
# --------------------------------------------------------------------------
def open_issue(session: Session, step: JobStep) -> JobVoucher | None:
    """The issue on this step that no receive has closed yet."""
    closed = select(JobVoucher.issue_id).where(
        JobVoucher.kind == "receive", JobVoucher.issue_id.is_not(None)
    )
    return session.scalars(
        select(JobVoucher)
        .where(JobVoucher.step_id == step.id, JobVoucher.kind == "issue",
               JobVoucher.id.not_in(closed))
        .order_by(JobVoucher.id)
    ).first()


def post_voucher(session: Session, job: Job, step: JobStep, kind: str,
                 worker_id: int | None, *, vr_date: date | None = None,
                 vr_time: str = "", pcs: int = 0, gross_wt: Any = None,
                 net_wt: Any = None, vr_no: int | None = None,
                 user_id: int | None = None, **extra: Any) -> JobVoucher:
    """Record an ISSUE to a worker or a RECEIVE back from them on one step."""
    if kind not in JobVoucher.KINDS:
        raise ProductionError(f"Unknown voucher kind '{kind}'.")
    if job.status == "cancelled":
        raise ProductionError(f"Job {job.job_no} is cancelled.")
    if not job.steps:
        raise ProductionError(
            f"Job {job.job_no} has no route yet. Map it in Job Mapping before "
            "issuing anything on it."
        )
    if step.job_id != job.id:
        raise ProductionError("That step does not belong to this job.")
    if not worker_id:
        raise ProductionError(
            "Worker is required - every issue and receive must say who has "
            "the piece."
        )
    if session.get(Account, worker_id) is None:
        raise ProductionError("The worker is not on the Account master.")

    gross = None if gross_wt in (None, "") else _dec(gross_wt)
    net = None if net_wt in (None, "") else _dec(net_wt)
    stone_wt = _dec(extra.get("stone_wt"))
    if step.weight_bearing:
        # The weight that matters is what comes BACK: loss is derived from the
        # receive. The client's own live rows issue HandMade with no metal
        # weight (Vr 3018 carried only stones, Vr 3019 nothing at all), so an
        # issue may go out unweighed; a receive on a metal step may not.
        if kind == "receive" and not (net and net > 0):
            raise ProductionError(
                "This step carries metal - enter the gross and net weight "
                "received back from the worker."
            )
    else:
        # Design-only step: nothing is weighed, so nothing may be typed.
        if (gross and gross > 0) or (net and net > 0):
            raise ProductionError(
                "This step (design only) carries no metal weight. Leave the "
                "weights empty."
            )
        gross = net = None

    issue_ref = None
    if kind == "receive":
        issue_ref = open_issue(session, step)
        if issue_ref is None:
            raise ProductionError(
                "Nothing is out on this step - issue it to a worker before "
                "receiving it back."
            )
    v = JobVoucher(
        vr_no=vr_no or next_number(session, JobVoucher.vr_no),
        kind=kind, job_id=job.id, step_id=step.id,
        issue_id=issue_ref.id if issue_ref is not None else None,
        worker_id=worker_id, vr_date=vr_date or date.today(), vr_time=vr_time,
        pcs=int(pcs or 0), gross_wt=gross, net_wt=net,
        stone_wt=stone_wt, extra=_dec(extra.get("extra")),
        finding=_dec(extra.get("finding")), mould=_dec(extra.get("mould")),
        wip_value=_dec(extra.get("wip_value")),
        del_date=extra.get("del_date"), rej_pcs=int(extra.get("rej_pcs") or 0),
        rej_wt=_dec(extra.get("rej_wt")), scrap=_dec(extra.get("scrap")),
        dust=_dec(extra.get("dust")), remark=extra.get("remark") or "",
        user_id=user_id,
    )
    session.add(v)
    if job.status in ("pending", "mapped"):
        job.status = "in_progress"
    # Receiving the last step of the route finishes the job. ASSUMPTION: the
    # finished piece is "in stock" at that receipt (18 Sept Q8 - it may be the
    # MFG transfer instead once that module exists).
    if kind == "receive" and job.steps and step.id == job.steps[-1].id:
        job.status = "complete"
        job.completed_on = v.vr_date
    session.flush()
    return v


def step_loss(issue: JobVoucher | None, receive: JobVoucher | None) -> Decimal | None:
    """Loss on one issue/receive pair, or None when it cannot be known yet."""
    if issue is None or receive is None:
        return None
    if issue.net_wt in (None, 0) or receive.net_wt is None:
        return None
    return (_dec(issue.net_wt) - _dec(receive.net_wt)
            - _dec(receive.scrap) - _dec(receive.dust)).quantize(D3)


@dataclass
class HistoryRow:
    step: JobStep
    process: ManufacturingProcess | None
    issue: JobVoucher | None
    receive: JobVoucher | None
    worker: str = ""
    loss: Decimal | None = None


def history_rows(session: Session, job: Job) -> list[HistoryRow]:
    """One row per issue (paired with the receive that closed it), in the
    order things happened, then any route step nothing has touched yet."""
    vouchers = session.scalars(
        select(JobVoucher).where(JobVoucher.job_id == job.id).order_by(JobVoucher.id)
    ).all()
    receives = {v.issue_id: v for v in vouchers if v.kind == "receive" and v.issue_id}
    steps = {s.id: s for s in job.steps}
    procs = {s.id: session.get(ManufacturingProcess, s.process_id) for s in job.steps}
    rows: list[HistoryRow] = []
    touched: set[int] = set()
    for v in vouchers:
        if v.kind != "issue":
            continue
        step = steps.get(v.step_id)
        if step is None:
            continue
        touched.add(step.id)
        rcv = receives.get(v.id)
        worker = session.get(Account, v.worker_id)
        rows.append(HistoryRow(step=step, process=procs.get(step.id), issue=v,
                               receive=rcv, worker=worker.name if worker else "",
                               loss=step_loss(v, rcv)))
    for s in job.steps:
        if s.id not in touched:
            rows.append(HistoryRow(step=s, process=procs.get(s.id), issue=None,
                                   receive=None))
    return rows


def job_summary(session: Session, job: Job) -> dict[str, Any]:
    """The block under Job History: PND (steps not started, by short code),
    WIP (issued, not back), Rejection, MFG transfer counts, total pcs."""
    rows = history_rows(session, job)
    started = {r.step.id for r in rows if r.issue is not None}
    pnd_parts = []
    for s in job.steps:
        if s.id not in started:
            p = session.get(ManufacturingProcess, s.process_id)
            pnd_parts.append(f"{(p.short_code or p.name) if p else '?'} {job.pcs}")
    wip = sum(1 for r in rows if r.issue is not None and r.receive is None)
    rejection = sum(int(r.receive.rej_pcs or 0) for r in rows if r.receive is not None)
    order = session.get(Order, job.order_id) if job.order_id else None
    return {
        "pnd": " ".join(pnd_parts),
        "wip": wip,
        "rejection": rejection,
        # The Manufacturing module (MFG Transfer) is a later phase; until it
        # lands nothing has been transferred.
        "pnd_mfg_transfer": job.pcs if job.status != "complete" else 0,
        "mfg_transfer": 0,
        "total_pcs": job.pcs,
        "order_remark": order.remark if order else "",
    }


# --------------------------------------------------------------------------
# Stock
# --------------------------------------------------------------------------
def stock_row(session: Session, location_id: int, material_class: str,
              ref_id: int | None, size: str = "", ref_text: str = "",
              create: bool = False) -> MaterialStock | None:
    stmt = select(MaterialStock).where(
        MaterialStock.location_id == location_id,
        MaterialStock.material_class == material_class,
        MaterialStock.size == (size or ""),
    )
    if ref_id:
        stmt = stmt.where(MaterialStock.ref_id == ref_id)
    else:
        stmt = stmt.where(MaterialStock.ref_id.is_(None),
                          MaterialStock.ref_text == (ref_text or ""))
    row = session.scalars(stmt).first()
    if row is None and create:
        row = MaterialStock(location_id=location_id, material_class=material_class,
                            ref_id=ref_id, ref_text=ref_text or "", size=size or "",
                            pcs=0, weight=ZERO)
        session.add(row)
        session.flush()
    return row


def stock_balance(session: Session, location_id: int, material_class: str,
                  ref_id: int | None, size: str = "", ref_text: str = "") -> tuple[int, Decimal]:
    row = stock_row(session, location_id, material_class, ref_id, size, ref_text)
    return (int(row.pcs), _dec(row.weight)) if row else (0, ZERO)


def holdings(session: Session, material_class: str, ref_id: int | None,
             size: str = "", ref_text: str = "") -> list[tuple[Location, int, Decimal]]:
    """Every location holding some of this item, most first."""
    stmt = select(MaterialStock).where(
        MaterialStock.material_class == material_class,
        MaterialStock.size == (size or ""),
        (MaterialStock.pcs > 0) | (MaterialStock.weight > 0),
    )
    if ref_id:
        stmt = stmt.where(MaterialStock.ref_id == ref_id)
    else:
        stmt = stmt.where(MaterialStock.ref_id.is_(None),
                          MaterialStock.ref_text == (ref_text or ""))
    out = []
    for row in session.scalars(stmt):
        loc = session.get(Location, row.location_id)
        if loc is not None:
            out.append((loc, int(row.pcs), _dec(row.weight)))
    out.sort(key=lambda t: (t[1], t[2]), reverse=True)
    return out


def adjust_stock(session: Session, location_id: int, material_class: str,
                 ref_id: int | None, d_pcs: int, d_wt: Any, size: str = "",
                 ref_text: str = "", what: str = "", *, kind: str = "adjust",
                 mv_date: date | None = None, job_id: int | None = None,
                 ref_kind: str = "", ref_no: int | None = None,
                 remark: str = "") -> MaterialStock:
    """Move stock in (+) or out (-). Going below zero is refused. Every call
    also writes one :class:`StockMovement`, the ledger the reports read."""
    if not location_id:
        raise ProductionError("A stock location is required.")
    if session.get(Location, location_id) is None:
        raise ProductionError("That location is not on the Location master.")
    row = stock_row(session, location_id, material_class, ref_id, size, ref_text, create=True)
    new_pcs = int(row.pcs) + int(d_pcs)
    new_wt = (_dec(row.weight) + _dec(d_wt)).quantize(D4)
    if new_pcs < 0 or new_wt < 0:
        loc = session.get(Location, location_id)
        raise ProductionError(
            f"{loc.name if loc else 'The location'} holds only {row.pcs} pcs / "
            f"{_dec(row.weight)} of {what or ref_text or 'this item'} - cannot "
            f"issue {abs(int(d_pcs))} pcs / {abs(_dec(d_wt))}."
        )
    row.pcs, row.weight = new_pcs, new_wt
    record_movement(session, location_id, material_class, ref_id, int(d_pcs), _dec(d_wt),
                    size=size, ref_text=ref_text, kind=kind, mv_date=mv_date, job_id=job_id,
                    ref_kind=ref_kind, ref_no=ref_no, remark=remark)
    session.flush()
    return row


def record_movement(session: Session, location_id: int, material_class: str,
                    ref_id: int | None, pcs: int, weight: Decimal, *, size: str = "",
                    ref_text: str = "", kind: str = "adjust", mv_date: date | None = None,
                    job_id: int | None = None, ref_kind: str = "", ref_no: int | None = None,
                    remark: str = "", value: Decimal | None = None) -> StockMovement:
    """One ledger row. Value = quantity x the stone's price (cost) unless given."""
    group = ""
    if material_class == "stone":
        group = stone_group_label(session, ref_id, ref_text)
    if value is None:
        price, unit = stone_price(session, ref_id) if material_class == "stone" else (ZERO, "Cts")
        value = stone_amount(price, unit, pcs, weight)
    m = StockMovement(mv_date=mv_date or date.today(), location_id=location_id,
                      material_class=material_class, ref_id=ref_id, ref_text=ref_text or "",
                      size=size or "", stone_group=group, kind=kind, pcs=pcs, weight=weight,
                      value=value, job_id=job_id, ref_kind=ref_kind, ref_no=ref_no,
                      remark=remark or "")
    session.add(m)
    return m


def post_opening_stock(session: Session, location_id: int, stone_sku_id: int | None,
                       pcs: int, weight: Any, *, as_of: date, group: str = "",
                       value: Any = None, size: str = "", remark: str = "") -> StockMovement:
    """Opening balance at a location (18 Sept C-03 / R7).

    With a Stone SKU the balance row is raised too, so the pieces can be
    issued; a group-only opening (pcs / ct / value per Diamond / Polki /
    Colour Stone, as the client will supply it) feeds the ledger only.
    """
    if stone_sku_id:
        sku = session.get(StoneSku, stone_sku_id)
        return adjust_stock(session, location_id, "stone", stone_sku_id, pcs, weight,
                            size=size or (sku.size if sku else ""), kind="opening",
                            mv_date=as_of, ref_kind="opening", remark=remark)
    m = record_movement(session, location_id, "stone", None, int(pcs), _dec(weight),
                        ref_text=group or "", kind="opening", mv_date=as_of,
                        ref_kind="opening", remark=remark,
                        value=None if value in (None, "") else _dec(value))
    m.stone_group = (group or OTHER_GROUP).upper()
    session.flush()
    return m


# --------------------------------------------------------------------------
# Stone Issue on Job-Card -> Job Bag
# --------------------------------------------------------------------------
def _find_bag_line(session: Session, job: Job, stone_sku_id: int | None,
                   particulars: str, size: str, create: bool = True) -> JobBagLine:
    stmt = select(JobBagLine).where(JobBagLine.job_id == job.id,
                                    JobBagLine.size == (size or ""))
    if stone_sku_id:
        stmt = stmt.where(JobBagLine.stone_sku_id == stone_sku_id)
    else:
        stmt = stmt.where(JobBagLine.stone_sku_id.is_(None),
                          JobBagLine.particulars == (particulars or ""))
    line = session.scalars(stmt).first()
    if line is None and create:
        sku = session.get(StoneSku, stone_sku_id) if stone_sku_id else None
        line = JobBagLine(job_id=job.id, stone_sku_id=stone_sku_id,
                          particulars=(sku.stone if sku else "") or particulars,
                          size=size or "", s_type=sku.stone_type if sku else "",
                          unit="ct")
        session.add(line)
        session.flush()
    return line


def _reject_negative_lines(lines) -> None:
    """A minus sign on pieces or weight is a slip, never a quantity. Name the
    line rather than let it fall through as "nothing entered"."""
    for l in lines:
        if (l.pcs or 0) < 0 or _dec(l.weight) < 0:
            raise ProductionError(
                f"Line {l.sno}: pieces and weight cannot be negative "
                f"({l.pcs or 0} pcs / {_dec(l.weight)})."
            )


def apply_stone_issue(session: Session, issue: StoneIssue) -> None:
    """Post a saved Stone Issue voucher: stock leaves the location, the
    pieces land in the job's bag as Received."""
    head_job = session.get(Job, issue.job_id)
    if head_job is None:
        raise ProductionError("Pick the job the stones are being issued to.")
    _reject_negative_lines(issue.lines)
    lines = [l for l in issue.lines if (l.pcs or 0) > 0 or _dec(l.weight) > 0]
    if not lines:
        raise ProductionError("Enter at least one stone line with pieces or weight.")
    for l in lines:
        # "For Multiple": a line may name its own job; blank means the header's.
        job = session.get(Job, l.job_id) if l.job_id else head_job
        if job is None or job.status == "cancelled":
            raise ProductionError(f"Line {l.sno}: that job is cancelled or unknown.")
        sku = session.get(StoneSku, l.stone_sku_id) if l.stone_sku_id else None
        name = (sku.sku_code if sku else l.particulars) or "stone"
        if not sku and not l.particulars:
            raise ProductionError("Each line needs a Stone SKU (or a description).")
        size = l.size or (sku.size if sku else "")
        if not issue.is_opening:
            if not l.location_id:
                raise ProductionError(f"Choose the location {name} is issued from.")
            adjust_stock(session, l.location_id, "stone", l.stone_sku_id,
                         -int(l.pcs or 0), -_dec(l.weight), size=size,
                         ref_text="" if sku else l.particulars, what=name,
                         kind="outward", mv_date=issue.vr_date, job_id=job.id,
                         ref_kind="stone_issue", ref_no=issue.vr_no)
        bag = _find_bag_line(session, job, l.stone_sku_id, l.particulars, size)
        if bag.source_location_id is None and l.location_id:
            bag.source_location_id = l.location_id
        if l.s_type and not bag.s_type:
            bag.s_type = l.s_type
        session.add(JobBagMovement(
            line_id=bag.id, kind="rcvd", pcs=int(l.pcs or 0), weight=_dec(l.weight),
            mv_date=issue.vr_date, location_id=l.location_id,
            ref_kind="stone_issue", ref_id=issue.id, remark=l.remark or "",
        ))
    session.flush()


# --------------------------------------------------------------------------
# Bag ledger
# --------------------------------------------------------------------------
@dataclass
class BagRow:
    line: JobBagLine
    pcs: dict[str, int] = field(default_factory=dict)
    wt: dict[str, Decimal] = field(default_factory=dict)

    def __getitem__(self, key: str) -> tuple[int, Decimal]:
        return self.pcs.get(key, 0), self.wt.get(key, ZERO)


COLUMNS: tuple[str, ...] = ("req", "rcvd", "extra", "pnd", "iss", "rtn",
                            "break", "lost", "back", "bal")
COLUMN_LABELS: dict[str, str] = {
    "req": "Req", "rcvd": "Rcvd", "extra": "Extra", "pnd": "Pnd", "iss": "Iss",
    "rtn": "Rtn", "break": "Break", "lost": "Lost", "back": "Back", "bal": "Bal",
}


def bag_row(line: JobBagLine) -> BagRow:
    """Derive every ledger column from the movements on one line.

    Bal = Rcvd - Iss - Rtn - Break - Lost + Back. Extra and Pnd are the two
    sides of Rcvd against Req. 'Back' is read as "returned from the worker
    into the bag" - seen on screen, never explained; confirm with the client
    (Q7).
    """
    pcs = {k: 0 for k in COLUMNS}
    wt = {k: ZERO for k in COLUMNS}
    for m in line.movements:
        if m.kind in pcs:
            pcs[m.kind] += int(m.pcs or 0)
            wt[m.kind] += _dec(m.weight)
    pcs["req"], wt["req"] = int(line.req_pcs or 0), _dec(line.req_wt)
    pcs["extra"] = max(pcs["rcvd"] - pcs["req"], 0) if pcs["req"] else 0
    wt["extra"] = max(wt["rcvd"] - wt["req"], ZERO) if wt["req"] else ZERO
    pcs["pnd"] = max(pcs["req"] - pcs["rcvd"], 0)
    wt["pnd"] = max(wt["req"] - wt["rcvd"], ZERO)
    pcs["bal"] = pcs["rcvd"] - pcs["iss"] - pcs["rtn"] - pcs["break"] - pcs["lost"] + pcs["back"]
    wt["bal"] = wt["rcvd"] - wt["iss"] - wt["rtn"] - wt["break"] - wt["lost"] + wt["back"]
    for k in wt:
        wt[k] = wt[k].quantize(D3)
    return BagRow(line=line, pcs=pcs, wt=wt)


def bag_ledger(session: Session, job: Job) -> list[BagRow]:
    lines = session.scalars(
        select(JobBagLine).where(JobBagLine.job_id == job.id).order_by(JobBagLine.id)
    ).all()
    return [bag_row(l) for l in lines]


def bag_move(session: Session, line: JobBagLine, kind: str, pcs: int,
             weight: Any = None, *, worker_id: int | None = None,
             location_id: int | None = None, mv_date: date | None = None,
             ref_kind: str = "", ref_id: int | None = None,
             remark: str = "") -> JobBagMovement:
    """Issue to a worker / return to stock / break / lost / back into the bag.

    Weight defaults to the line's average per piece when not given, which is
    how "returning 2 of 6 pieces at 0.680" comes to 0.227 and leaves 0.453.
    """
    if kind not in ("iss", "rtn", "break", "lost", "back"):
        raise ProductionError(f"Unknown bag movement '{kind}'.")
    pcs = int(pcs or 0)
    if pcs <= 0 and _dec(weight) <= 0:
        raise ProductionError("Enter the pieces (or weight) to move.")
    row = bag_row(line)
    bal_pcs, bal_wt = row["bal"]
    if weight in (None, ""):
        avg = (bal_wt / bal_pcs) if bal_pcs else ZERO
        weight = (avg * pcs).quantize(D4)
    weight = _dec(weight)
    name = f"{line.particulars} {line.size}".strip()
    if kind in ("iss", "rtn", "break", "lost"):
        if pcs > bal_pcs or weight > bal_wt + D3:
            raise ProductionError(
                f"Job bag holds {bal_pcs} pcs / {bal_wt} of {name} - cannot "
                f"{'return' if kind == 'rtn' else kind} {pcs} pcs / {weight}."
            )
    if kind == "back":
        out_pcs = row["iss"][0] - row["back"][0]
        if pcs > out_pcs:
            raise ProductionError(
                f"Only {out_pcs} pcs of {name} are out with a worker."
            )
    if kind == "iss" and not worker_id:
        raise ProductionError("Say which worker the stones are issued to.")
    sku = session.get(StoneSku, line.stone_sku_id) if line.stone_sku_id else None
    if kind == "rtn":
        location_id = location_id or line.source_location_id
        if not location_id:
            raise ProductionError("Choose the stock location the stones go back to.")
        adjust_stock(session, location_id, "stone", line.stone_sku_id, pcs, weight,
                     size=line.size, ref_text="" if sku else line.particulars, what=name,
                     kind="return", mv_date=mv_date, job_id=line.job_id,
                     ref_kind=ref_kind or "bag", ref_no=ref_id, remark=remark)
    if kind == "break":
        # Broken stones leave the bag but credit no saleable stock. Where they
        # go and how they are valued is open (18 Sept Q5); the ledger still
        # records them against the source location so the day book shows them.
        loc = location_id or line.source_location_id
        if loc:
            record_movement(session, loc, "stone", line.stone_sku_id, -pcs, -weight,
                            size=line.size, ref_text="" if sku else line.particulars,
                            kind="breakage", mv_date=mv_date, job_id=line.job_id,
                            ref_kind=ref_kind or "bag", ref_no=ref_id, remark=remark)
    m = JobBagMovement(line_id=line.id, kind=kind, pcs=pcs, weight=weight,
                       mv_date=mv_date or date.today(), worker_id=worker_id,
                       location_id=location_id, ref_kind=ref_kind, ref_id=ref_id,
                       remark=remark or "")
    session.add(m)
    session.flush()
    session.refresh(line)
    return m


# --------------------------------------------------------------------------
# Return to inventory
# --------------------------------------------------------------------------
def job_metal_held(session: Session, job: Job) -> Decimal:
    """Metal the job is holding: everything issued on it, less what has been
    returned to stock. ASSUMPTION pending the factory session (Q6, Q8)."""
    issued = session.scalar(
        select(func.coalesce(func.sum(JobVoucher.net_wt), 0))
        .where(JobVoucher.job_id == job.id, JobVoucher.kind == "issue")
    ) or 0
    returned = session.scalar(
        select(func.coalesce(func.sum(InventoryReturnLine.weight), 0))
        .join(InventoryReturn)
        .where(InventoryReturn.job_id == job.id, InventoryReturn.material_class == "metal")
    ) or 0
    return (_dec(issued) - _dec(returned)).quantize(D3)


def apply_inventory_return(session: Session, ret: InventoryReturn) -> None:
    """Post a saved return: leaves the job, re-enters stock at the location."""
    job = session.get(Job, ret.job_id)
    if job is None:
        raise ProductionError("Pick the job the material is coming back from.")
    if not ret.location_id:
        raise ProductionError("Choose the location the material returns to.")
    _reject_negative_lines(ret.lines)
    lines = [l for l in ret.lines if (l.pcs or 0) > 0 or _dec(l.weight) > 0]
    if not lines:
        raise ProductionError("Enter at least one line with pieces or weight.")
    cls = ret.material_class
    if cls == "stone":
        for l in lines:
            bag = session.get(JobBagLine, l.bag_line_id) if l.bag_line_id else None
            if bag is None or bag.job_id != job.id:
                raise ProductionError(
                    "Each stone line must pick one of this job's bag lines.")
            kind = "break" if (l.rtn_type or "").lower().startswith("break") else "rtn"
            bag_move(session, bag, kind, int(l.pcs or 0),
                     None if _dec(l.weight) == 0 else l.weight,
                     location_id=l.location_id or ret.location_id, mv_date=ret.vr_date,
                     ref_kind="inv_return", ref_id=ret.vr_no, remark=l.remark or "")
            l.particulars, l.size = bag.particulars, bag.size
            l.location_id = l.location_id or ret.location_id or bag.source_location_id
            price, unit = stone_price(session, bag.stone_sku_id)
            l.price, l.price_unit = price, unit
            l.amount = stone_amount(price, unit, int(l.pcs or 0), _dec(l.weight))
        return
    if cls == "metal":
        held = job_metal_held(session, job)
        total = sum((_dec(l.weight) for l in lines), ZERO)
        if total > held + D3:
            raise ProductionError(
                f"Job {job.job_no} holds {held} g of metal - cannot return {total} g."
            )
        for l in lines:
            if not l.metal_id:
                raise ProductionError("Each metal line must name the metal head.")
            metal = session.get(Metal, l.metal_id)
            adjust_stock(session, ret.location_id, "metal", l.metal_id, 0, l.weight,
                         what=metal.name if metal else "metal", kind="return",
                         mv_date=ret.vr_date, job_id=job.id, ref_kind="inv_return",
                         ref_no=ret.vr_no)
        return
    for l in lines:  # mould / finding - counted in pieces
        ref_id = l.mould_id if cls == "mould" else None
        if cls == "mould" and not ref_id:
            raise ProductionError("Each mould line must pick the mould.")
        if cls == "finding" and not l.particulars:
            raise ProductionError("Describe the finding being returned.")
        adjust_stock(session, ret.location_id, cls, ref_id, int(l.pcs or 0), l.weight,
                     size=l.size or "", ref_text=l.particulars if cls == "finding" else "",
                     what=l.particulars or cls, kind="return", mv_date=ret.vr_date,
                     job_id=job.id, ref_kind="inv_return", ref_no=ret.vr_no)


def post_stone_return(session: Session, job: Job, lines: list[dict[str, Any]], *,
                      vr_date: date | None = None, account_id: int | None = None,
                      user_id: int | None = None, remark: str = "") -> InventoryReturn:
    """Rtn To Inv - Stone, as the client walked it (18 Sept §4.2).

    ``lines`` come from the Show Pending list: each names a bag line of the
    job with the pieces / weight going back, Returned or Breakage, and the
    location credited (default: where the stones were picked from). The bag
    goes down; for Returned the location's stock goes up.
    """
    if job is None:
        raise ProductionError("Job No is required - enter the job the stones come back from.")
    keep = [l for l in lines if int(l.get("pcs") or 0) > 0 or _dec(l.get("weight")) > 0]
    if not keep:
        raise ProductionError("Enter the pieces (or weight) being returned on at least one line.")
    ret = InventoryReturn(vr_no=next_number(session, InventoryReturn.vr_no),
                          material_class="stone", job_id=job.id,
                          vr_date=vr_date or date.today(),
                          location_id=int(keep[0].get("location_id") or 0) or None,
                          account_id=account_id, remark=remark or "", user_id=user_id)
    if ret.location_id is None:
        first = session.get(JobBagLine, keep[0]["bag_line_id"])
        ret.location_id = first.source_location_id if first else None
    if ret.location_id is None:
        raise ProductionError("Choose the location the stones go back to.")
    session.add(ret)
    session.flush()
    for n, l in enumerate(keep, start=1):
        session.add(InventoryReturnLine(
            return_id=ret.id, sno=n, bag_line_id=l["bag_line_id"],
            rtn_type=l.get("rtn_type") or "Returned",
            location_id=l.get("location_id") or ret.location_id,
            pcs=int(l.get("pcs") or 0), weight=_dec(l.get("weight")),
            remark=l.get("remark") or "",
        ))
    session.flush()
    session.refresh(ret)
    apply_inventory_return(session, ret)
    return ret


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def stones_in_job_cards(session: Session) -> list[dict[str, Any]]:
    """Report A - across all open jobs: what is still lying in each bag."""
    out = []
    jobs = session.scalars(
        select(Job).where(Job.status.not_in(("complete", "cancelled"))).order_by(Job.job_no)
    ).all()
    for job in jobs:
        client = session.get(Account, job.account_id) if job.account_id else None
        sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
        for row in bag_ledger(session, job):
            bal_pcs, bal_wt = row["bal"]
            if bal_pcs <= 0 and bal_wt <= 0:
                continue
            out.append({
                "job_no": job.job_no, "sku": sku.sku_code if sku else "",
                "client": client.name if client else "stock",
                "stone": row.line.particulars, "size": row.line.size,
                "type": row.line.s_type, "bal_pcs": bal_pcs, "bal_wt": bal_wt,
            })
    return out


def order_day_book(session: Session, date_from: date, date_to: date,
                   term: str = "") -> list[dict[str, Any]]:
    """Report rows for the Order Day Book - one per order line, with its job."""
    orders = session.scalars(
        select(Order).where(Order.order_date >= date_from, Order.order_date <= date_to)
        .order_by(Order.order_date, Order.order_no)
    ).all()
    jobs = {(j.order_id, j.line_sno): j for j in session.scalars(
        select(Job).where(Job.status != "cancelled"))}
    out = []
    term = (term or "").strip().lower()
    for o in orders:
        client = session.get(Account, o.account_id) if o.account_id else None
        for l in o.lines:
            sku = session.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
            metal = session.get(Metal, l.metal_id) if l.metal_id else None
            job = jobs.get((o.id, l.sno))
            row = {
                "date": o.order_date, "ord_no": o.order_no, "vr_type": "Order",
                "ref_no": o.ref, "particulars": client.name if client else "stock",
                "family": "", "ref": l.c_ref, "metal": metal.name if metal else "",
                "loss_pct": _dec(sku.mt_loss_pct) if sku else ZERO,
                "col": l.colour, "size": l.size, "pcs": l.pcs,
                "gwt_pcs": _dec(l.tot_gross_wt), "del_dt": l.delivery_date or o.delivery_date,
                "job_no": job.job_no if job else "", "job_pcs": job.pcs if job else 0,
                "prod_dt": job.prod_del_date if job else None,
                "priority": l.priority or o.priority, "remark": l.remark or o.remark,
                "sku": sku.sku_code if sku else l.sku_desc,
            }
            if sku and sku.family_id:
                from diagold.db.models import FamilyCategory
                fam = session.get(FamilyCategory, sku.family_id)
                row["family"] = fam.name if fam else ""
            if term and term not in " ".join(str(v) for v in row.values()).lower():
                continue
            out.append(row)
    return out


def job_label(session: Session, job: Job) -> str:
    sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
    client = session.get(Account, job.account_id) if job.account_id else None
    return " · ".join(p for p in (str(job.job_no), sku.sku_code if sku else "",
                                  client.name if client else "stock") if p)
