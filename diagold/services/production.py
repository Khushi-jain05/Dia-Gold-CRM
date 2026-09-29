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
    SettingLabourRate,
    SettingType,
    StockMovement,
    StoneGroup,
    StoneInfo,
    StoneIssue,
    StoneIssueLine,
    StoneSize,
    StoneSku,
)
from diagold.services import costing

# The client's three heads for stone stock (S1 D4, reaffirmed 18 Sept D9),
# keyed by the Stone Group master's code.
STONE_GROUP_LABELS: dict[str, str] = {"DIA": "DIAMOND", "POLKI": "POLKI", "CS": "COLOR STONE"}
OTHER_GROUP = "OTHER"

ZERO = Decimal("0")
D2 = Decimal("0.01")
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
    A stray text value in the column would otherwise restart the sequence at
    1 and collide with everything, so those are skipped.
    """
    current = session.scalar(select(func.max(column)))
    try:
        return int(current or 0) + 1
    except (TypeError, ValueError):
        numbers = [int(v) for v in session.scalars(select(column))
                   if str(v).strip().isdigit()]
        return (max(numbers) + 1) if numbers else 1


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
            setting_type_id=st.setting_type_id,
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
    if job.status == "transferred":
        raise ProductionError(
            f"Job {job.job_no} is already in ready stock. To correct it, delete its "
            "stock item in Item Search - the job comes back to Pending for MFG "
            "Transfer - then fix it here and transfer it again."
        )
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
    allow = extra.get("allow_loss_pct")
    if allow in (None, ""):
        allow = default_allow_loss_pct(session, step, issue_ref)
    allow = _dec(allow)
    if allow < 0 or allow >= 100:
        raise ProductionError("Allowed loss % must be between 0 and 100.")
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
        allow_loss_pct=allow, user_id=user_id,
        mt_price=_dec(extra.get("mt_price")), mt_amt=_dec(extra.get("mt_amt")),
        manual_price=_dec(extra.get("manual_price")),
        manual_amt=_dec(extra.get("manual_amt")),
        rej_type=(extra.get("rej_type") or "")[:24],
        price_on=extra.get("price_on") or "NetWt", ref_no=(extra.get("ref_no") or "")[:40],
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
    if kind == "issue":
        _claim_bag_movements(session, v)
    else:
        _claim_bag_movements(session, issue_ref)
        refresh_setting_labour(session, v)
    return v


def default_allow_loss_pct(session: Session, step: JobStep,
                           issue: JobVoucher | None = None) -> Decimal:
    """The allowed loss % a new line starts on: a receive takes its issue's
    figure, an issue takes the process master's. Live figures seen on 28 Sept:
    HandMade 3.5, Setting 3.0, PrePolish 0.35, final setting 0. Whether the
    default belongs to the process, the karigar or the job is open (Q3)."""
    if issue is not None and issue.allow_loss_pct is not None:
        return _dec(issue.allow_loss_pct)
    process = session.get(ManufacturingProcess, step.process_id)
    return _dec(process.loss_percent if process else 0)


def step_loss(issue: JobVoucher | None, receive: JobVoucher | None) -> Decimal | None:
    """Loss on one issue/receive pair, or None when it cannot be known yet."""
    if issue is None or receive is None:
        return None
    if issue.net_wt in (None, 0) or receive.net_wt is None:
        return None
    return (_dec(issue.net_wt) - _dec(receive.net_wt)
            - _dec(receive.scrap) - _dec(receive.dust)).quantize(D3)


@dataclass
class LossDetail:
    """Loss on one received step, beside what the karigar was allowed.

    ``loss`` can be negative - setting adds stone weight, so BANG-577's
    Setting step shows -0.300 / -0.96% (28 Sept §4.5).
    """

    loss: Decimal                 # grams
    loss_pct: Decimal             # of the issued net weight
    allow_pct: Decimal
    allowed: Decimal              # grams the karigar may lose on this step
    excess: Decimal               # loss beyond the allowance (negative = under)
    # True when the step went out unweighed: nothing to subtract from, so the
    # loss is read as the allowance - the legacy HandMade row of job 28853
    # shows exactly that (1.141 = 3.5% x 32.610).
    from_allowance: bool = False


def allowed_loss(receive: JobVoucher, allow_pct: Decimal) -> Decimal:
    """Grams allowed on a receive: allowed % of the net weight received back.

    Both live figures agree - HandMade 3.5% x 32.610 = 1.141 (job 28853) and
    the worker ledger's 3.5% x 83.240 returned = 2.913 - and the voucher line
    says "L Price On: NetWt". The process master's loss-type letter is not
    used here: HandMade carries H (hourly) and Setting S (stone pcs), which
    give no weight at all, so that letter looks like a labour basis rather
    than the allowance basis (to confirm with C-03).
    """
    return (_dec(receive.net_wt) * allow_pct / Decimal("100")).quantize(D3)


def loss_detail(process: ManufacturingProcess | None, issue: JobVoucher | None,
                receive: JobVoucher | None) -> LossDetail | None:
    """Loss, loss % and allowance for one issue/receive pair (T-04).

    loss   = issued net - received net - scrap - dust
    loss % = loss / issued net x 100
    """
    if issue is None or receive is None or receive.net_wt is None:
        return None
    allow_pct = _dec(receive.allow_loss_pct if receive.allow_loss_pct is not None
                     else issue.allow_loss_pct if issue.allow_loss_pct is not None
                     else (process.loss_percent if process else 0))
    allowed = allowed_loss(receive, allow_pct)
    actual = step_loss(issue, receive)
    if actual is None:
        return LossDetail(loss=allowed, loss_pct=allow_pct.quantize(Decimal("0.01")),
                          allow_pct=allow_pct, allowed=allowed, excess=ZERO,
                          from_allowance=True)
    pct = (actual / _dec(issue.net_wt) * 100).quantize(Decimal("0.01"))
    return LossDetail(loss=actual, loss_pct=pct, allow_pct=allow_pct, allowed=allowed,
                      excess=(actual - allowed).quantize(D3))


@dataclass
class HistoryRow:
    step: JobStep
    process: ManufacturingProcess | None
    issue: JobVoucher | None
    receive: JobVoucher | None
    worker: str = ""
    loss: Decimal | None = None
    detail: LossDetail | None = None


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
        detail = loss_detail(procs.get(step.id), v, rcv) if step.weight_bearing else None
        rows.append(HistoryRow(step=step, process=procs.get(step.id), issue=v,
                               receive=rcv, worker=worker.name if worker else "",
                               loss=detail.loss if detail else None, detail=detail))
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
        # Finished (last step received) and not yet priced into stock is
        # Pending for MFG Transfer; transferred is in ready stock (28 Sept R2).
        "pnd_mfg_transfer": job.pcs if job.status == "complete" else 0,
        "mfg_transfer": job.pcs if job.status == "transferred" else 0,
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
                 remark: str = "", allow_negative: bool = False,
                 account_id: int | None = None, fine_wt: Any = None,
                 value: Decimal | None = None) -> MaterialStock:
    """Move stock in (+) or out (-). Going below zero is refused unless the
    caller allows it (Inventory's block / warn / allow setting). Every call
    also writes one :class:`StockMovement`, the ledger the reports read."""
    if not location_id:
        raise ProductionError("A stock location is required.")
    if session.get(Location, location_id) is None:
        raise ProductionError("That location is not on the Location master.")
    row = stock_row(session, location_id, material_class, ref_id, size, ref_text, create=True)
    new_pcs = int(row.pcs) + int(d_pcs)
    new_wt = (_dec(row.weight) + _dec(d_wt)).quantize(D4)
    if (new_pcs < 0 or new_wt < 0) and not allow_negative:
        loc = session.get(Location, location_id)
        raise ProductionError(
            f"{loc.name if loc else 'The location'} holds only {row.pcs} pcs / "
            f"{_dec(row.weight)} of {what or ref_text or 'this item'} - cannot "
            f"issue {abs(int(d_pcs))} pcs / {abs(_dec(d_wt))}."
        )
    row.pcs, row.weight = new_pcs, new_wt
    record_movement(session, location_id, material_class, ref_id, int(d_pcs), _dec(d_wt),
                    size=size, ref_text=ref_text, kind=kind, mv_date=mv_date, job_id=job_id,
                    ref_kind=ref_kind, ref_no=ref_no, remark=remark, value=value,
                    account_id=account_id, fine_wt=fine_wt)
    session.flush()
    return row


def record_movement(session: Session, location_id: int, material_class: str,
                    ref_id: int | None, pcs: int, weight: Decimal, *, size: str = "",
                    ref_text: str = "", kind: str = "adjust", mv_date: date | None = None,
                    job_id: int | None = None, ref_kind: str = "", ref_no: int | None = None,
                    remark: str = "", value: Decimal | None = None,
                    account_id: int | None = None, fine_wt: Any = None) -> StockMovement:
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
                      remark=remark or "", account_id=account_id, fine_wt=_dec(fine_wt))
    session.add(m)
    return m


def post_opening_stock(session: Session, location_id: int, stone_sku_id: int | None,
                       pcs: int, weight: Any, *, as_of: date, group: str = "",
                       value: Any = None, size: str = "", remark: str = "") -> StockMovement:
    """Opening balance at a location (18 Sept C-03 / R7).

    Value: what was typed wins; left blank, it is quantity x the Stone SKU's
    cost price (per its unit), or 0 for a group-only line. With a Stone SKU
    the balance row is raised too, so the pieces can be issued; a group-only
    opening (pcs / ct / value per Diamond / Polki / Colour Stone, as the
    client will supply it) feeds the ledger only.
    """
    typed = None if value in (None, "") else _dec(value)
    if stone_sku_id:
        sku = session.get(StoneSku, stone_sku_id)
        row_size = size or (sku.size if sku else "")
        stock_row(session, location_id, "stone", stone_sku_id, row_size, create=True)
        adjusted = adjust_stock(session, location_id, "stone", stone_sku_id, pcs, weight,
                                size=row_size, kind="opening", mv_date=as_of,
                                ref_kind="opening", remark=remark)
        if typed is not None:
            # adjust_stock priced the line from the catalogue; the typed value
            # is the client's own figure, so it replaces that.
            m = session.scalars(select(StockMovement)
                                .order_by(StockMovement.id.desc()).limit(1)).first()
            if m is not None:
                m.value = typed
                session.flush()
        return session.scalars(select(StockMovement)
                               .order_by(StockMovement.id.desc()).limit(1)).first()
    m = record_movement(session, location_id, "stone", None, int(pcs), _dec(weight),
                        ref_text=group or "", kind="opening", mv_date=as_of,
                        ref_kind="opening", remark=remark, value=typed)
    m.stone_group = (group or OTHER_GROUP).upper()
    session.flush()
    return m


def suggested_stone_value(session: Session, stone_sku_id: int | None, pcs: int,
                          weight: Any) -> tuple[Decimal, str]:
    """What the catalogue says a quantity of a stone is worth, and how it was
    priced ("2,000.00 / Cts") - shown before the user commits an opening."""
    price, unit = stone_price(session, stone_sku_id)
    return stone_amount(price, unit, int(pcs or 0), _dec(weight)), (
        f"{price:,.2f} per {unit} (cost price)" if price else "no price on this Stone SKU")


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
        if kind == "back":
            # Pieces coming back weigh what those still out with karigars
            # average - the bag's own balance is usually empty by then.
            out_pcs = row["iss"][0] - row["back"][0]
            out_wt = row["iss"][1] - row["back"][1]
            avg = (out_wt / out_pcs) if out_pcs > 0 else ZERO
        else:
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
        if worker_id:
            out_pcs = min(out_pcs, _out_with_worker(line, worker_id))
        if pcs > out_pcs:
            who = session.get(Account, worker_id) if worker_id else None
            raise ProductionError(
                f"Only {out_pcs} pcs of {name} are out with "
                f"{who.name if who else 'a worker'}."
            )
    if kind == "iss" and not worker_id:
        raise ProductionError("Say which worker the stones are issued to.")
    # Stones going to or coming back from a karigar belong to the step they
    # hold for this job, so setting labour can count them (28 Sept T-05).
    voucher = None
    if kind in ("iss", "back") and worker_id and not ref_kind:
        voucher = _open_issue_for_worker(session, line.job_id, worker_id)
        if voucher is None and kind == "back":
            voucher = _last_issue_for_worker(session, line.job_id, worker_id)
        if voucher is not None:
            ref_kind, ref_id = VOUCHER_REF, voucher.id
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
    if voucher is not None:
        # Stones back after the step was received: the labour on that
        # receive is re-counted, so it always matches what was set.
        receive = session.scalar(select(JobVoucher).where(
            JobVoucher.kind == "receive", JobVoucher.issue_id == voucher.id))
        if receive is not None:
            refresh_setting_labour(session, receive)
    return m


def _out_with_worker(line: JobBagLine, worker_id: int) -> int:
    """Pieces of this bag line still with one karigar: issued less back."""
    out = 0
    for m in line.movements:
        if m.worker_id != worker_id:
            continue
        if m.kind == "iss":
            out += int(m.pcs or 0)
        elif m.kind == "back":
            out -= int(m.pcs or 0)
    return out


# --------------------------------------------------------------------------
# Setting labour (28 Sept R8 / T-05)
# --------------------------------------------------------------------------
# Bag movements that went to (or came back from) a karigar carry the issue
# voucher of the step they were for.
VOUCHER_REF = "job_voucher"


def _open_issue_for_worker(session: Session, job_id: int,
                           worker_id: int) -> JobVoucher | None:
    closed = select(JobVoucher.issue_id).where(
        JobVoucher.kind == "receive", JobVoucher.issue_id.is_not(None))
    return session.scalars(
        select(JobVoucher).where(JobVoucher.job_id == job_id,
                                 JobVoucher.worker_id == worker_id,
                                 JobVoucher.kind == "issue",
                                 JobVoucher.id.not_in(closed))
        .order_by(JobVoucher.id.desc())
    ).first()


def _last_issue_for_worker(session: Session, job_id: int,
                           worker_id: int) -> JobVoucher | None:
    return session.scalars(
        select(JobVoucher).where(JobVoucher.job_id == job_id,
                                 JobVoucher.worker_id == worker_id,
                                 JobVoucher.kind == "issue")
        .order_by(JobVoucher.id.desc())
    ).first()


def _claim_bag_movements(session: Session, issue: JobVoucher | None) -> None:
    """Stones handed to this karigar on this job before the step voucher was
    posted belong to that step."""
    if issue is None:
        return
    rows = session.scalars(
        select(JobBagMovement).join(JobBagLine)
        .where(JobBagLine.job_id == issue.job_id,
               JobBagMovement.worker_id == issue.worker_id,
               JobBagMovement.kind.in_(("iss", "back")),
               JobBagMovement.ref_kind == "")
    ).all()
    for m in rows:
        m.ref_kind, m.ref_id = VOUCHER_REF, issue.id
    session.flush()


def setting_rate(session: Session, setting_type_id: int | None,
                 on_date: date) -> tuple[Decimal, str]:
    """Per-piece setting rate for a setting type on a date, and where it came
    from. A dated row on the Setting Labour Chart for that setting type wins;
    otherwise the Setting Type master's price (live: Polki 30, Diam 3). Never
    a literal - a type with no rate pays 0 and says so."""
    if not setting_type_id:
        return ZERO, "no setting type"
    row = session.scalars(
        select(SettingLabourRate)
        .where(SettingLabourRate.setting_type_id == setting_type_id,
               SettingLabourRate.sku_id.is_(None),
               SettingLabourRate.is_active.is_(True),
               SettingLabourRate.effective_from <= on_date)
        .order_by(SettingLabourRate.effective_from.desc(), SettingLabourRate.id.desc())
    ).first()
    if row is not None:
        return _dec(row.rate_per_piece), f"Setting Labour Chart from {row.effective_from}"
    st = session.get(SettingType, setting_type_id)
    if st is None:
        return ZERO, "setting type not found"
    return _dec(st.price), "Setting Type master"


@dataclass
class SettingLabourLine:
    line: JobBagLine
    setting_type: str
    issued: int
    back: int
    set_pcs: int
    rate: Decimal
    rate_source: str
    amount: Decimal


def setting_labour_lines(session: Session, issue: JobVoucher,
                         on_date: date | None = None) -> list[SettingLabourLine]:
    """Per stone line: pieces set on this step and the labour for them.

    pieces set = issued to the karigar - back from the karigar
    labour     = pieces set x setting rate of the line's setting type

    Everything that comes back - returned whole or broken - is unpaid. On job
    28853 this reproduces the Rs 2,400 on the final-setting row exactly
    (POLKI 16-18: 43 out, 5 back of which 1 broken -> 38 x 30). That broken
    pieces are unpaid was read from the arithmetic, not said (28 Sept Q4).
    """
    on_date = on_date or date.today()
    moves = session.scalars(
        select(JobBagMovement).where(JobBagMovement.ref_kind == VOUCHER_REF,
                                     JobBagMovement.ref_id == issue.id)
        .order_by(JobBagMovement.id)
    ).all()
    per_line: dict[int, list[int]] = {}
    for m in moves:
        tally = per_line.setdefault(m.line_id, [0, 0])
        if m.kind == "iss":
            tally[0] += int(m.pcs or 0)
        elif m.kind == "back":
            tally[1] += int(m.pcs or 0)
    out: list[SettingLabourLine] = []
    for line_id, (issued, back) in per_line.items():
        line = session.get(JobBagLine, line_id)
        if line is None or issued <= 0:
            continue
        st = session.get(SettingType, line.setting_type_id) if line.setting_type_id else None
        rate, source = setting_rate(session, line.setting_type_id, on_date)
        set_pcs = max(issued - back, 0)
        out.append(SettingLabourLine(
            line=line, setting_type=st.name if st else "", issued=issued, back=back,
            set_pcs=set_pcs, rate=rate, rate_source=source,
            amount=(Decimal(set_pcs) * rate).quantize(Decimal("0.01")),
        ))
    return out


def set_bag_setting_type(session: Session, line: JobBagLine,
                         setting_type_id: int | None) -> None:
    """Correct how a bag line is set. Receives that already counted this line
    are re-counted - at the rate of their own date, so only the type changes."""
    line.setting_type_id = setting_type_id
    session.flush()
    issue_ids = {m.ref_id for m in line.movements if m.ref_kind == VOUCHER_REF and m.ref_id}
    for receive in session.scalars(select(JobVoucher).where(
            JobVoucher.kind == "receive", JobVoucher.issue_id.in_(issue_ids))):
        refresh_setting_labour(session, receive)


def setting_labour_statement(session: Session, date_from: date, date_to: date,
                             worker_id: int | None = None) -> list[dict[str, Any]]:
    """Month-end karigar settlement (28 Sept R8 / T-05, 3 Sept R8): every
    receive in the period that earned setting labour, line by line - pieces
    set by setting type, the rate applied on the receive date, the amount.
    Grouped by karigar, the subtotals are what each is owed."""
    q = (select(JobVoucher).where(JobVoucher.kind == "receive", JobVoucher.labour > 0,
                                  JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to)
         .order_by(JobVoucher.vr_date, JobVoucher.vr_no))
    if worker_id:
        q = q.where(JobVoucher.worker_id == worker_id)
    rows = []
    for rcv in session.scalars(q):
        issue = session.get(JobVoucher, rcv.issue_id) if rcv.issue_id else None
        if issue is None:
            continue
        job = session.get(Job, rcv.job_id)
        worker = session.get(Account, rcv.worker_id)
        for l in setting_labour_lines(session, issue, rcv.vr_date):
            rows.append({
                "worker": worker.name if worker else "?", "month": rcv.vr_date.strftime("%Y-%m"),
                "date": rcv.vr_date, "vrno": rcv.vr_no, "job_no": job.job_no if job else "",
                "_job_id": job.id if job else None,
                "stone": f"{l.line.particulars} {l.line.size}".strip(),
                "setting_type": l.setting_type or "—", "issued": l.issued, "back": l.back,
                "set_pcs": l.set_pcs, "rate": l.rate, "amount": l.amount,
            })
    return rows


def refresh_setting_labour(session: Session, receive: JobVoucher) -> Decimal:
    """Store the setting labour on a receive, at the rate in force on its date."""
    issue = session.get(JobVoucher, receive.issue_id) if receive.issue_id else None
    if issue is None:
        return ZERO
    total = sum((l.amount for l in setting_labour_lines(session, issue, receive.vr_date)),
                ZERO)
    receive.labour = total
    session.flush()
    return total


# --------------------------------------------------------------------------
# Show Pending (28 Sept R3 / UX3)
# --------------------------------------------------------------------------
# Every voucher lists only the jobs pending for it; if nothing is pending,
# nothing shows.
ACTIVE_STATUSES = ("mapped", "in_progress")


def current_step(session: Session, job: Job) -> tuple[JobStep | None, JobVoucher | None]:
    """The step a job is at: the first route step not yet received back, and
    the issue that has it out (None when it is waiting to be issued)."""
    for step in job.steps:
        issues = session.scalars(select(JobVoucher).where(
            JobVoucher.step_id == step.id, JobVoucher.kind == "issue")
            .order_by(JobVoucher.id)).all()
        if not issues:
            return step, None
        received = {v.issue_id for v in session.scalars(select(JobVoucher).where(
            JobVoucher.step_id == step.id, JobVoucher.kind == "receive"))}
        open_ = [v for v in issues if v.id not in received]
        if open_:
            return step, open_[0]
    return None, None


def last_weights(session: Session, job: Job) -> tuple[Decimal | None, Decimal | None]:
    """Gross and net as last weighed - what goes out on the next issue."""
    v = session.scalars(
        select(JobVoucher).where(JobVoucher.job_id == job.id, JobVoucher.net_wt.is_not(None))
        .order_by(JobVoucher.vr_date.desc(), JobVoucher.vr_time.desc(), JobVoucher.id.desc())
    ).first()
    if v is None:
        return None, None
    return (_dec(v.gross_wt) if v.gross_wt is not None else None), _dec(v.net_wt)


def pending_steps(session: Session, kind: str, process_id: int | None = None,
                  worker_id: int | None = None) -> list[dict[str, Any]]:
    """Jobs pending for an issue (next step not yet issued) or a receive (out
    with a karigar, not back), optionally for one process / one karigar."""
    rows = []
    jobs = session.scalars(select(Job).where(Job.status.in_(ACTIVE_STATUSES))
                           .order_by(Job.job_no)).all()
    for job in jobs:
        step, issue = current_step(session, job)
        if step is None:
            continue
        if (kind == "issue") != (issue is None):
            continue
        if process_id and step.process_id != process_id:
            continue
        if kind == "receive" and worker_id and issue.worker_id != worker_id:
            continue
        proc = session.get(ManufacturingProcess, step.process_id)
        worker = session.get(Account, issue.worker_id) if issue else None
        gross, net = last_weights(session, job)
        if kind == "receive":
            gross = _dec(issue.gross_wt) if issue.gross_wt is not None else None
            net = _dec(issue.net_wt) if issue.net_wt is not None else None
        client = session.get(Account, job.account_id) if job.account_id else None
        order = session.get(Order, job.order_id) if job.order_id else None
        rows.append({
            "_job_id": job.id, "_step_id": step.id, "job_no": job.job_no,
            "sku": job.product_sku.sku_code if job.product_sku else "",
            "client": client.name if client else "stock",
            "process": proc.name if proc else "", "process_id": step.process_id,
            "weight_bearing": bool(step.weight_bearing),
            "worker": worker.name if worker else "", "worker_id": issue.worker_id if issue else None,
            "issued_on": issue.vr_date if issue else None, "vr_no": issue.vr_no if issue else None,
            "gross": gross, "net": net, "due": step.due_date, "pcs": job.pcs,
            # the rest of the legacy voucher grid
            "c_ref": job.c_ref, "colour": job.colour,
            "metal": (session.get(Metal, job.metal_id).name if job.metal_id else ""),
            "order_no": order.order_no if order else "",
            "order_date": order.order_date if order else None, "ref_no": order.ref if order else "",
            "allow": default_allow_loss_pct(session, step, issue),
            "size": _order_line_size(session, job),
            "mt_price": metal_price(session, job.metal_id) or None,
            "price_on": issue.price_on if issue and issue.price_on else "NetWt",
            "extra": _dec(issue.extra) or None if issue else None,
            "finding": _dec(issue.finding) or None if issue else None,
            "mould": _dec(issue.mould) or None if issue else None,
        })
        row = rows[-1]
        row["mt_amt"] = ((row["mt_price"] * row["net"]).quantize(D2)
                         if row["mt_price"] and row["net"] else None)
    return rows


def _order_line_size(session: Session, job: Job) -> str:
    if not job.order_id:
        return ""
    line = session.scalar(select(OrderLine).where(OrderLine.order_id == job.order_id,
                                                  OrderLine.sno == job.line_sno))
    return line.size if line else ""


def metal_price(session: Session, metal_id: int | None, on_date: date | None = None) -> Decimal:
    """Mt Price on an issue / receive line: the metal's rate per gram for the
    day - the day's fine (24K) rate x the metal's purity, the way the MFG
    transfer prices metal (8,680.67 = 14,713 x 0.590)."""
    if not metal_id:
        return ZERO
    from diagold.services import mfg_pricing, rates
    metal = session.get(Metal, metal_id)
    info = rates.rate_for(session, metal_id, on_date or date.today())
    if not info.found:
        return ZERO
    return (_dec(info.rate) * mfg_pricing.title_of(metal) / 1000).quantize(D2)


def worker_metal_balance(session: Session, worker_id: int,
                         on_date: date | None = None) -> tuple[Decimal, Decimal]:
    """Mt Bal on the voucher: the karigar's closing metal balance (weight,
    fine) from the Worker Metal Ledger."""
    on_date = on_date or date.today()
    # From the start of records: the running balance is carried row to row,
    # so a karigar with nothing on the day still shows what he holds.
    rows = worker_metal_ledger(session, date(2000, 1, 1), on_date, worker_id=worker_id)
    if not rows:
        return ZERO, ZERO
    return _dec(rows[-1]["bal_wt"]), _dec(rows[-1]["bal_fine"])


def post_multi_voucher(session: Session, kind: str, worker_id: int | None,
                       lines: list[dict[str, Any]], *, vr_date: date | None = None,
                       vr_time: str = "", allow_loss_pct: Any = None,
                       user_id: int | None = None) -> int:
    """One issue or receive voucher carrying several jobs, as the legacy
    "Issue To <Process>" does (Buddha Polish Vr 2333 received four jobs).
    Every line gets the same voucher number. A receive goes back from
    whoever has each job out. Returns the voucher number.

    A line may also carry ``allow`` (its own Allow Loss %), ``rej_pcs`` /
    ``rej_wt`` / ``stone_wt``, ``stones`` ({bag line id: pcs} - F3: out with
    an issue, back on a receipt) and ``metal`` ([{location_id, metal_id,
    weight, pcs}] - F5, issue only)."""
    if not lines:
        raise ProductionError("Tick at least one job.")
    vr_no = next_number(session, JobVoucher.vr_no)
    for ln in lines:
        _post_line_full(session, kind, worker_id, ln, vr_no, vr_date=vr_date,
                        vr_time=vr_time, allow_loss_pct=allow_loss_pct, user_id=user_id,
                        remark=ln.get("remark") or "")
    return vr_no


def _post_line_full(session: Session, kind: str, worker_id: int | None, ln: dict[str, Any],
                    vr_no: int, *, vr_date: date | None, vr_time: str, allow_loss_pct: Any,
                    user_id: int | None, remark: str = "") -> JobVoucher:
    """One line of a multi-job voucher, with its F3 stones and F5 metal."""
    job = session.get(Job, ln["job_id"])
    step = session.get(JobStep, ln["step_id"])
    who = worker_id
    if kind == "receive":
        out = open_issue(session, step)
        if out is None:
            raise ProductionError(f"Job {job.job_no}: nothing is out on this step - "
                                  "issue it before receiving it back.")
        who = out.worker_id
    lines = {l.id: l for l in session.scalars(select(JobBagLine).where(
        JobBagLine.id.in_(list((ln.get("stones") or {}).keys()))))}
    try:
        if kind == "receive":
            for line_id, pcs in (ln.get("stones") or {}).items():
                bag_move(session, lines[line_id], "back", pcs, worker_id=who, mv_date=vr_date)
        extra = {k: ln.get(k) for k in ("scrap", "dust", "rej_pcs", "rej_wt", "stone_wt",
                                        "extra", "finding", "mould", "mt_price", "mt_amt",
                                        "manual_price", "manual_amt", "rej_type", "price_on",
                                        "ref_no")}
        if kind == "issue" and ln.get("metal"):
            # F5 metal is the line's extra metal; the column shows its total.
            extra["extra"] = sum((_dec(m["weight"]) for m in ln["metal"]), ZERO)
        allow = ln.get("allow")
        v = post_voucher(session, job, step, kind, who, vr_date=vr_date, vr_time=vr_time,
                         pcs=ln.get("pcs") or job.pcs, gross_wt=ln.get("gross"),
                         net_wt=ln.get("net"), vr_no=vr_no, user_id=user_id, remark=remark,
                         allow_loss_pct=allow if allow not in (None, "") else
                         (allow_loss_pct if kind == "issue" else None), **extra)
        if kind == "issue":
            for line_id, pcs in (ln.get("stones") or {}).items():
                bag_move(session, lines[line_id], "iss", pcs, worker_id=who, mv_date=vr_date)
            from diagold.services import inventory as INV
            for m in ln.get("metal") or []:
                INV.metal_to_job_step(session, v, m["location_id"], m["metal_id"],
                                      m["weight"], m.get("pcs") or 0)
    except ProductionError as exc:
        raise ProductionError(f"Job {job.job_no}: {exc}") from exc
    return v


def pending_stone_jobs(session: Session) -> list[dict[str, Any]]:
    """Stone Issue on Job-Card: jobs whose bag still needs stones (Pnd)."""
    rows = []
    for job in session.scalars(select(Job).where(Job.status.not_in(
            ("complete", "transferred", "cancelled"))).order_by(Job.job_no)):
        pnd = [b for b in bag_ledger(session, job) if b["pnd"][0] > 0 or b["pnd"][1] > 0]
        if not pnd:
            continue
        client = session.get(Account, job.account_id) if job.account_id else None
        rows.append({
            "_job_id": job.id, "job_no": job.job_no,
            "sku": job.product_sku.sku_code if job.product_sku else "",
            "client": client.name if client else "stock", "lines": len(pnd),
            "pnd_pcs": sum(b["pnd"][0] for b in pnd),
            "pnd_wt": sum((b["pnd"][1] for b in pnd), ZERO),
        })
    return rows


def pending_stone_lines(session: Session, job: Job) -> list[dict[str, Any]]:
    """The lines a Stone Issue for this job should start with: what the bag
    still needs, from where it was taken before (or where it is held)."""
    out = []
    for b in bag_ledger(session, job):
        pcs, wt = b["pnd"]
        if pcs <= 0 and wt <= 0:
            continue
        line = b.line
        loc = line.source_location_id
        if loc is None and line.stone_sku_id:
            held = holdings(session, "stone", line.stone_sku_id, line.size)
            loc = held[0][0].id if held else None
        req_pcs, req_wt = b["req"]
        out.append({
            "job_id": None, "location_id": loc, "stone_sku_id": line.stone_sku_id,
            "particulars": line.particulars, "size": line.size,
            "wt_per_pcs": (req_wt / req_pcs).quantize(D4) if req_pcs else ZERO,
            "req_pcs": req_pcs, "req_wt": req_wt, "pcs": pcs, "weight": wt,
            "price_unit": "Cts" if line.unit == "ct" else "Pcs", "s_type": line.s_type,
            "remark": "",
        })
    return out


def jobs_with_stones_in_bag(session: Session) -> list[dict[str, Any]]:
    """Job Card Bag: jobs whose bag holds stones not yet issued or returned."""
    rows = []
    for r in stones_in_job_cards(session):
        key = r["job_no"]
        if rows and rows[-1]["job_no"] == key:
            rows[-1]["lines"] += 1
            rows[-1]["bal_pcs"] += r["bal_pcs"]
            rows[-1]["bal_wt"] += r["bal_wt"]
            continue
        rows.append({"_job_id": r.get("_job_id"), "job_no": key, "sku": r["sku"],
                     "client": r["client"], "lines": 1, "bal_pcs": r["bal_pcs"],
                     "bal_wt": r["bal_wt"]})
    return rows


# --------------------------------------------------------------------------
# Karigar metal ledger (28 Sept R5 / R13 / T-04)
# --------------------------------------------------------------------------
# Is the karigar charged for every gram lost, or only for what goes beyond
# the allowance? Not yet confirmed (28 Sept Q3 / C-03). The legacy Worker
# Ledger credits the allowance against the balance (RTN 83.240 at 3.5% ->
# 2.913 off), which is "charge only the excess" - so that is the default and
# the other reading is a switch in Tools > Option.
CHARGE_ALL_LOSS_FLAG = "loss.charge_all"


def worker_metal_ledger(session: Session, date_from: date, date_to: date, *,
                        worker_id: int | None = None,
                        charge_all_loss: bool | None = None) -> list[dict[str, Any]]:
    """One row per metal movement with a karigar, with a running balance in
    grams and in fine, per karigar - the legacy Worker Ledger (28 Sept §4.13).

    ISS / RTN = a job step issued to / received back from the karigar;
    MI / MR   = metal issued / received on an Inventory voucher.
    Inward  = net weight issued (ISS) or metal issued (MI).
    Outward = net weight received back plus scrap and dust (RTN), or metal
              received (MR).
    Loss    = issued - outward on a job step; Alw L Wt = the allowance on
              it, or the wastage allowed on an MR.
    Balance = opening + inward - outward - allowance credited, where the
              allowance is credited unless the karigar is charged for all loss.
    Fine    = weight x the metal's purity (Metal master).
    """
    from diagold.db.models import InvVoucher, InvVoucherLine
    if charge_all_loss is None:
        from diagold.services import settings
        charge_all_loss = settings.flag(CHARGE_ALL_LOSS_FLAG, False, session=session)
    q = select(JobVoucher).where(JobVoucher.vr_date <= date_to)
    if worker_id:
        q = q.where(JobVoucher.worker_id == worker_id)
    vouchers = session.scalars(q).all()
    iq = (select(InvVoucherLine, InvVoucher).join(InvVoucher)
          .where(InvVoucher.vr_type.in_(("metal_issue", "metal_receipt")),
                 InvVoucher.vr_date <= date_to, InvVoucher.account_id.is_not(None)))
    if worker_id:
        iq = iq.where(InvVoucher.account_id == worker_id)
    events: list[tuple] = [(v.vr_date, v.vr_time or "", 0, v.id, "job", v) for v in vouchers]
    events += [(v.vr_date, "", 1, line.id, "inv", (v, line))
               for line, v in session.execute(iq)]
    # F5: metal handed out with a job step, straight from a location's stock.
    xq = select(StockMovement).where(StockMovement.ref_kind == "job_voucher",
                                     StockMovement.material_class == "metal",
                                     StockMovement.account_id.is_not(None),
                                     StockMovement.mv_date <= date_to)
    if worker_id:
        xq = xq.where(StockMovement.account_id == worker_id)
    events += [(m.mv_date, "", 2, m.id, "extra", m) for m in session.scalars(xq)]
    events.sort(key=lambda e: e[:4])

    jobs: dict[int, Job] = {}
    steps: dict[int, JobStep | None] = {}
    procs: dict[int, ManufacturingProcess | None] = {}
    purity: dict[int | None, Decimal] = {}
    names: dict[int, str] = {}
    issues = {v.id: v for v in vouchers if v.kind == "issue"}
    balance: dict[int, list[Decimal]] = {}   # worker -> [wt, fine]
    opening_done: set[int] = set()
    rows: list[dict[str, Any]] = []

    def name(wid: int) -> str:
        if wid not in names:
            a = session.get(Account, wid)
            names[wid] = a.name if a else "?"
        return names[wid]

    def pf_of(metal_id: int | None) -> Decimal:
        if metal_id not in purity:
            metal = session.get(Metal, metal_id) if metal_id else None
            purity[metal_id] = costing.purity_fraction(metal) if metal else ZERO
        return purity[metal_id]

    for when, _t, _o, _id, source, obj in events:
        loss = allowed = inward = outward = ZERO
        alw_pct: Decimal | None = None
        is_return = False
        if source == "job":
            v = obj
            step = steps.setdefault(v.step_id, session.get(JobStep, v.step_id))
            if step is None or not step.weight_bearing or v.net_wt is None:
                continue
            job = jobs.setdefault(v.job_id, session.get(Job, v.job_id))
            if job is None:
                continue
            wid, metal_id, vr_no = v.worker_id, job.metal_id, v.vr_no
            proc = procs.setdefault(step.process_id,
                                    session.get(ManufacturingProcess, step.process_id))
            if v.kind == "issue":
                inward, vrtype = _dec(v.net_wt), "ISS"
            else:
                is_return, vrtype = True, "RTN"
                outward = _dec(v.net_wt) + _dec(v.scrap) + _dec(v.dust)
                detail = loss_detail(proc, issues.get(v.issue_id), v)
                if detail is not None:
                    loss, allowed, alw_pct = detail.loss, detail.allowed, detail.allow_pct
            job_no, job_id = job.job_no, job.id
            sku = job.product_sku.sku_code if job.product_sku else ""
            process = proc.name if proc else ""
        elif source == "extra":
            m = obj
            wid, metal_id, vr_no = m.account_id, m.ref_id, m.ref_no
            inward, vrtype = -_dec(m.weight), "MI"
            job = jobs.setdefault(m.job_id, session.get(Job, m.job_id)) if m.job_id else None
            job_no, job_id = (job.job_no if job else ""), (job.id if job else None)
            sku = job.product_sku.sku_code if job and job.product_sku else ""
            process = "F5 metal"
        else:
            iv, line = obj
            wid, metal_id, vr_no = iv.account_id, line.metal_id, iv.vr_no
            if iv.vr_type == "metal_issue":
                inward, vrtype = _dec(line.weight), "MI"
            else:
                is_return, vrtype = True, "MR"
                outward = _dec(line.weight)
                allowed = _dec(line.wastage_wt)
                alw_pct = _dec(line.wastage_pct) if line.wastage_pct else None
            job_no, job_id, sku, process = (line.job_no or ""), None, "", ""
        pf = pf_of(metal_id)
        bal = balance.setdefault(wid, [ZERO, ZERO])
        credited = ZERO if charge_all_loss else allowed
        in_range = when >= date_from
        if in_range and wid not in opening_done:
            opening_done.add(wid)
            rows.append({"worker": name(wid), "worker_id": wid,
                         "date": None, "vrno": "", "vrtype": "OPENING", "metal": "",
                         "job_no": "", "_job_id": None, "sku": "", "process": "",
                         "in_wt": None, "in_fine": None, "out_wt": None, "out_fine": None,
                         "loss_wt": None, "loss_fine": None, "alw_pct": None,
                         "alw_wt": None, "bal_wt": bal[0].quantize(D3),
                         "bal_fine": bal[1].quantize(D3)})
        bal[0] += inward - outward - credited
        bal[1] += (inward - outward - credited) * pf
        if not in_range:
            continue
        metal = session.get(Metal, metal_id) if metal_id else None
        rows.append({
            "worker": name(wid), "worker_id": wid, "date": when, "vrno": vr_no,
            "vrtype": vrtype, "metal": metal.name if metal else "", "job_no": job_no,
            "_job_id": job_id, "sku": sku, "process": process,
            "in_wt": inward.quantize(D3) if inward else None,
            "in_fine": (inward * pf).quantize(D3) if inward else None,
            "out_wt": outward.quantize(D3) if outward else None,
            "out_fine": (outward * pf).quantize(D3) if outward else None,
            "loss_wt": loss if vrtype == "RTN" else None,
            "loss_fine": (loss * pf).quantize(D3) if vrtype == "RTN" else None,
            "alw_pct": alw_pct, "alw_wt": allowed if is_return else None,
            "bal_wt": bal[0].quantize(D3), "bal_fine": bal[1].quantize(D3),
        })
    return rows


def voucher_day_book(session: Session, kind: str, date_from: date,
                     date_to: date) -> list[dict[str, Any]]:
    """Issue Day Book / Received Day Book (28 Sept §4.8): every job-step issue
    (or receive) in the period."""
    rows = []
    procs: dict[int, ManufacturingProcess | None] = {}
    q = (select(JobVoucher).where(JobVoucher.kind == kind, JobVoucher.vr_date >= date_from,
                                  JobVoucher.vr_date <= date_to)
         .order_by(JobVoucher.vr_date, JobVoucher.vr_time, JobVoucher.vr_no, JobVoucher.id))
    for v in session.scalars(q):
        job = session.get(Job, v.job_id)
        step = session.get(JobStep, v.step_id)
        proc = procs.setdefault(step.process_id, session.get(ManufacturingProcess,
                                                            step.process_id)) if step else None
        worker = session.get(Account, v.worker_id)
        row = {
            "date": v.vr_date, "time": v.vr_time, "vrno": v.vr_no,
            "process": proc.name if proc else "", "worker": worker.name if worker else "",
            "job_no": job.job_no if job else "", "_job_id": job.id if job else None,
            "sku": job.product_sku.sku_code if job and job.product_sku else "",
            "pcs": v.pcs, "g_wt": _dec(v.gross_wt) if v.gross_wt is not None else None,
            "n_wt": _dec(v.net_wt) if v.net_wt is not None else None,
            "stone_wt": _dec(v.stone_wt) or None,
        }
        if kind == "receive":
            issue = session.get(JobVoucher, v.issue_id) if v.issue_id else None
            d = loss_detail(proc, issue, v) if step and step.weight_bearing else None
            row.update({"loss": d.loss if d else None, "loss_pct": d.loss_pct if d else None,
                        "alw_pct": d.allow_pct if d else None,
                        "scrap": _dec(v.scrap) or None, "dust": _dec(v.dust) or None,
                        "labour": _dec(v.labour) or None})
        rows.append(row)
    return rows


def worker_stone_ledger(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Worker Stone Ledger (28 Sept §4.15): stones a karigar holds - issued
    from a job bag (ISS) or on an Inventory stone issue (SI), less what came
    back (BACK / SR) and what was set into the piece (SET, when the step is
    received) - in pieces and carats, running per karigar."""
    from diagold.db.models import InvVoucher, InvVoucherLine
    events: list[tuple] = []
    for m in session.scalars(select(JobBagMovement).where(
            JobBagMovement.kind.in_(("iss", "back")), JobBagMovement.worker_id.is_not(None),
            JobBagMovement.mv_date <= date_to)):
        line = session.get(JobBagLine, m.line_id)
        job = session.get(Job, line.job_id) if line else None
        sign = 1 if m.kind == "iss" else -1
        events.append((m.mv_date, 0, m.id, m.worker_id, "ISS" if sign > 0 else "BACK",
                       sign * int(m.pcs or 0), sign * _dec(m.weight),
                       f"{line.particulars} {line.size}".strip() if line else "",
                       job.job_no if job else "", job.id if job else None, None))
    # Stones set into the piece leave the karigar with the piece, when the
    # step is received back: "SET", pieces = issued - back on that step.
    linked = {m.ref_id for m in session.scalars(select(JobBagMovement).where(
        JobBagMovement.ref_kind == VOUCHER_REF))}
    for rcv in session.scalars(select(JobVoucher).where(
            JobVoucher.kind == "receive", JobVoucher.issue_id.in_(linked),
            JobVoucher.vr_date <= date_to)):
        issue = session.get(JobVoucher, rcv.issue_id)
        job = session.get(Job, rcv.job_id)
        for l in setting_labour_lines(session, issue, rcv.vr_date):
            per = (_dec(sum((_dec(m.weight) for m in l.line.movements
                             if m.kind == "iss" and m.ref_id == issue.id), ZERO))
                   - _dec(sum((_dec(m.weight) for m in l.line.movements
                               if m.kind == "back" and m.ref_id == issue.id), ZERO)))
            if l.set_pcs <= 0 and per <= 0:
                continue
            events.append((rcv.vr_date, 2, rcv.id * 1000 + l.line.id, issue.worker_id, "SET",
                           -l.set_pcs, -per, f"{l.line.particulars} {l.line.size}".strip(),
                           job.job_no if job else "", job.id if job else None, rcv.vr_no))
    q = (select(InvVoucherLine, InvVoucher).join(InvVoucher)
         .where(InvVoucher.vr_type.in_(("stone_issue", "stone_receipt")),
                InvVoucher.vr_date <= date_to, InvVoucher.account_id.is_not(None)))
    for line, v in session.execute(q):
        sign = 1 if v.vr_type == "stone_issue" else -1
        sku = session.get(StoneSku, line.stone_sku_id) if line.stone_sku_id else None
        events.append((v.vr_date, 1, line.id, v.account_id, "SI" if sign > 0 else "SR",
                       sign * int(line.pcs or 0), sign * _dec(line.weight),
                       (sku.sku_code if sku else line.particulars) or "", line.job_no or "",
                       None, v.vr_no))
    events.sort(key=lambda e: e[:3])
    bal: dict[int, list] = {}
    names: dict[int, str] = {}
    rows = []
    for when, _o, _i, wid, vtype, pcs, wt, stone, job_no, job_id, vr_no in events:
        b = bal.setdefault(wid, [0, ZERO])
        b[0] += pcs
        b[1] += wt
        if when < date_from:
            continue
        if wid not in names:
            a = session.get(Account, wid)
            names[wid] = a.name if a else "?"
        rows.append({"worker": names[wid], "date": when, "vrtype": vtype, "vrno": vr_no or "",
                     "stone": stone, "job_no": job_no, "_job_id": job_id,
                     "in_pcs": pcs if pcs > 0 else None, "in_wt": wt if wt > 0 else None,
                     "out_pcs": -pcs if pcs < 0 else None, "out_wt": -wt if wt < 0 else None,
                     "bal_pcs": b[0], "bal_wt": b[1].quantize(D3)})
    return rows


def worker_stone_balance(session: Session, date_to: date) -> list[dict[str, Any]]:
    """Worker Balance (Stone): what each karigar holds now, by stone."""
    acc: dict[tuple[str, str], list] = {}
    for r in worker_stone_ledger(session, date(1900, 1, 1), date_to):
        a = acc.setdefault((r["worker"], r["stone"]), [0, ZERO])
        a[0] += (r["in_pcs"] or 0) - (r["out_pcs"] or 0)
        a[1] += (r["in_wt"] or ZERO) - (r["out_wt"] or ZERO)
    return [{"worker": w, "stone": st, "pcs": p, "weight": wt.quantize(D3),
             "_negative": p < 0 or wt < 0}
            for (w, st), (p, wt) in sorted(acc.items()) if p or wt]


def job_loss_total(session: Session, job: Job) -> tuple[Decimal, Decimal | None, int]:
    """Total loss on a job, as a % of its latest net weight, and the number of
    steps it covers. On job 28853 the legacy total row reads 3.574 / 11.81 -
    3.574 / 30.257 (the latest net) = 11.81%, which is the basis used here.
    (The legacy total leaves out one final-setting row that gained 0.080 g;
    why is asked as 28 Sept Q13.)"""
    rows = history_rows(session, job)
    losses = [r.loss for r in rows if r.loss is not None]
    total = sum(losses, ZERO)
    latest = None
    for v in session.scalars(select(JobVoucher).where(JobVoucher.job_id == job.id,
                                                      JobVoucher.net_wt.is_not(None))
                             .order_by(JobVoucher.vr_date, JobVoucher.vr_time,
                                       JobVoucher.id)):
        latest = _dec(v.net_wt)
    pct = (total / latest * 100).quantize(Decimal("0.01")) if latest else None
    return total.quantize(D3), pct, len(losses)


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
        select(Job).where(Job.status.not_in(("complete", "transferred", "cancelled"))).order_by(Job.job_no)
    ).all()
    for job in jobs:
        client = session.get(Account, job.account_id) if job.account_id else None
        sku = session.get(ProductSku, job.product_sku_id) if job.product_sku_id else None
        for row in bag_ledger(session, job):
            bal_pcs, bal_wt = row["bal"]
            if bal_pcs <= 0 and bal_wt <= 0:
                continue
            out.append({
                "job_no": job.job_no, "_job_id": job.id, "sku": sku.sku_code if sku else "",
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
