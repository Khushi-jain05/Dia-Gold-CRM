"""Seed for the Production-Planning module (11 September session).

Three kinds of data, all idempotent:

1. Reference: process short codes and the weight-bearing flag; the "Default"
   eleven-step process group; the workers and clients named on the call;
   placeholder print templates.
2. Opening stock at Primary for the priced stone catalogue, so Stone Issue can
   be exercised on a fresh install.
3. SAMPLE records reproducing what the client demonstrated live - order 1224
   / job 28350 (RUBY SINGH, NS-2968) with its five voucher rows and its bag,
   and order 1338 / jobs 28622-28624 (KK) waiting in the pending queue. They
   are the acceptance tests in §4.5-4.6 of the meeting notes and can simply
   be deleted.
"""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    DefaultProcessStep,
    Item,
    Job,
    JobBagLine,
    Location,
    ManufacturingProcess,
    MaterialStock,
    Metal,
    Order,
    OrderLine,
    ProductSku,
    ProductSkuStone,
    StoneIssue,
    StoneIssueLine,
    StoneSize,
    StoneSku,
)
from diagold.services import documents, production

# name -> (short code used in the legacy route string, carries metal weight?)
# Short codes for HM / RHM / PP / ST / FP / fs / Meena / Puwai were read off
# job 28350's header. The rest are ours, pending the legacy export (C-01).
_PROCESS_REF: dict[str, tuple[str, bool]] = {
    "CAD": ("CAD", False),          # design only - no weight goes (R6)
    "CAMMING": ("CAM", False),      # design/wax stage - ASSUMED no metal
    "OFFICE": ("OFF", False),
    "CASTING": ("CS", True),
    "HandMade": ("HM", True),
    "Repair HM": ("RHM", True),
    "COLOUR": ("COL", True),
    "PrePolish": ("PP", True),
    "Setting": ("ST", True),
    "Final Polish": ("FP", True),
    "final setting": ("fs", True),
    "Meena": ("Meena", True),
    "Puwai": ("Puwai", True),
    "Assamble": ("ASM", True),
    "DANK CHANGE": ("DC", True),
    "KHUDAI": ("KH", True),
    "RECTIFICATION": ("RECT", True),
}

# The Default group - the eleven steps on the Job Mapping screen (§4.4).
DEFAULT_ROUTE: tuple[str, ...] = (
    "CAD", "CAMMING", "CASTING", "HandMade", "COLOUR", "PrePolish", "Setting",
    "Final Polish", "final setting", "Meena", "Puwai",
)

_WORKERS: tuple[tuple[str, str], ...] = (
    ("OFFICE", "Office"),
    ("TUHIN", "TUHIN BHANI"),
    # Name truncated on the client's screen ("BUDDHA POL…"); complete it from
    # the legacy export.
    ("BUDDHAPOL", "BUDDHA POL"),
)
_CLIENTS: tuple[tuple[str, str], ...] = (
    ("RUBY", "RUBY SINGH"),
    ("KK", "KK JEWELS"),
)


def seed_production(session: Session) -> None:
    _seed_process_reference(session)
    _seed_default_group(session)
    _seed_parties(session)
    documents.seed_templates(session)
    session.flush()
    _seed_opening_stock(session)
    _seed_sample_jobs(session)
    session.flush()


def _process(session: Session, name: str) -> ManufacturingProcess | None:
    return session.scalar(
        select(ManufacturingProcess).where(func.lower(ManufacturingProcess.name) == name.lower())
    )


def _seed_process_reference(session: Session) -> None:
    """Stamp short codes and the weight flag once per process (blank code =
    never touched). A code typed by the client later is left alone."""
    for name, (short, bearing) in _PROCESS_REF.items():
        p = _process(session, name)
        if p is None or (p.short_code or "").strip():
            continue
        p.short_code = short
        p.weight_bearing = bearing


def _seed_default_group(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(DefaultProcessStep)):
        return
    for n, name in enumerate(DEFAULT_ROUTE, start=1):
        p = _process(session, name)
        if p is None:
            continue
        session.add(DefaultProcessStep(group_name="Default", step_no=n,
                                       process_id=p.id, is_active=True))


def _seed_parties(session: Session) -> None:
    existing = {c for c in session.scalars(select(Account.code)).all() if c}
    for code, name in _WORKERS:
        if code not in existing:
            session.add(Account(code=code, name=name, account_type="Worker",
                                group_name="Accounts Payable"))
    for code, name in _CLIENTS:
        if code not in existing:
            session.add(Account(code=code, name=name, account_type="Client",
                                group_name="Sundry Debtors"))


def _seed_opening_stock(session: Session) -> None:
    """Opening balance at Primary for every priced stone, so the Stone Issue
    screen has something to issue. Purchase > Opening Stock owns this once
    that module is built."""
    if session.scalar(select(func.count()).select_from(MaterialStock)):
        return
    primary = session.scalar(select(Location).where(Location.name == "Primary"))
    if primary is None:
        return
    for sku in session.scalars(select(StoneSku).where(StoneSku.is_active.is_(True))):
        per = Decimal(str(sku.wt_per_pcs or 0))
        weight = (per * 100) if per > 0 else Decimal("25.000")
        session.add(MaterialStock(location_id=primary.id, material_class="stone",
                                  ref_id=sku.id, size=sku.size or "", pcs=100,
                                  weight=weight))


# --------------------------------------------------------------------------
# Sample: what the client demonstrated on 11 September
# --------------------------------------------------------------------------
_SAMPLE = "SAMPLE — reproduced from the 11 Sept walkthrough. Safe to delete."


def _sample_sku(session: Session, code: str, item: Item | None, metal: Metal | None,
                desc: str) -> ProductSku:
    sku = session.scalar(select(ProductSku).where(ProductSku.sku_code == code))
    if sku is None:
        sku = ProductSku(sku_code=code, description=desc, remark=_SAMPLE,
                         item_id=item.id if item else None,
                         family_id=item.family_id if item else None,
                         metal_id=metal.id if metal else None, item_pcs=1, is_active=True)
        session.add(sku)
        session.flush()
    return sku


def _seed_sample_jobs(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(Order)):
        return
    metal590 = session.scalar(select(Metal).where(Metal.name == "14KT CASTING 590"))
    metal595 = session.scalar(select(Metal).where(Metal.name == "14KT CASTING 59.50")) or metal590
    necklace = session.scalar(select(Item).where(Item.name == "NECKLACE"))
    ruby = session.scalar(select(Account).where(Account.code == "RUBY"))
    kk = session.scalar(select(Account).where(Account.code == "KK"))
    workers = {a.code: a for a in session.scalars(
        select(Account).where(Account.code.in_([c for c, _ in _WORKERS])))}
    if not (ruby and kk and workers):
        return
    polki = {s.size: s for s in session.scalars(
        select(StoneSku).where(StoneSku.stone == "POLKI"))}

    def size_ref(name: str) -> StoneSize | None:
        # Polki on job 28350 is sized 14-16 / 20-22 / 26-28 / 28-30 (mm bands)
        # that the priced catalogue does not carry yet; they go on the Size
        # master so the bag keeps the size even without a rate card.
        if not name:
            return None
        row = session.scalar(select(StoneSize).where(StoneSize.name == name))
        if row is None:
            row = StoneSize(code=name.replace("-", "_").upper(), name=name, is_active=True)
            session.add(row)
            session.flush()
        return row

    # -- Job 28350: NS-2968 for RUBY SINGH, order 1224 dt 05-09-2026 --------
    ns2968 = _sample_sku(session, "NS-2968", necklace, metal590, "Necklace")
    if not session.scalar(select(func.count()).select_from(ProductSkuStone)
                          .where(ProductSkuStone.product_id == ns2968.id)):
        # The bag rows of job 28350 are the SKU's requirement.
        for particulars, size, pcs, wt in (("daank", "", 27, "4.530"),
                                            ("POLKI", "14-16", 6, "0.680"),
                                            ("POLKI", "20-22", 8, "1.160"),
                                            ("POLKI", "26-28", 6, "1.190"),
                                            ("POLKI", "28-30", 7, "1.500")):
            sku = polki.get(size) if particulars == "POLKI" else None
            sz = size_ref(size)
            session.add(ProductSkuStone(
                product_id=ns2968.id, stone_sku_id=sku.id if sku else None,
                size_id=sz.id if sz else None, description=particulars,
                pieces=pcs, weight_cts=Decimal(wt), per="Cts",
            ))
    order1224 = Order(order_no=1224, order_date=date(2026, 9, 5), account_id=ruby.id,
                      order_type="Customer", remark=_SAMPLE)
    session.add(order1224)
    session.flush()
    session.add(OrderLine(order_id=order1224.id, sno=1, product_sku_id=ns2968.id,
                          sku_desc="Necklace", metal_id=metal590.id if metal590 else None,
                          colour="Y", pcs=1))
    session.flush()
    session.refresh(order1224)
    job = Job(job_no=28350, order_id=order1224.id, line_sno=1, product_sku_id=ns2968.id,
              account_id=ruby.id, metal_id=metal590.id if metal590 else None, colour="Y",
              pcs=1, prod_date=date(2026, 9, 9), status="pending", remark=_SAMPLE)
    session.add(job)
    session.flush()
    # Its bag: the requirement, then the stones received (opening issue - the
    # stones were already with the job, so no location is reduced).
    production.seed_bag_requirements(session, job)
    bag_lines = {(l.particulars, l.size): l for l in session.scalars(
        select(JobBagLine).where(JobBagLine.job_id == job.id))}
    for (particulars, size), line in bag_lines.items():
        line.particulars = particulars
    issue = StoneIssue(vr_no=11262, job_id=job.id, vr_date=date(2026, 9, 9),
                       is_opening=True, remark=_SAMPLE)
    session.add(issue)
    session.flush()
    for n, ((particulars, size), line) in enumerate(bag_lines.items(), start=1):
        session.add(StoneIssueLine(issue_id=issue.id, sno=n, stone_sku_id=line.stone_sku_id,
                                   particulars=particulars, size=size,
                                   pcs=line.req_pcs, weight=line.req_wt, price_unit="Cts"))
    session.flush()
    session.refresh(issue)
    production.apply_stone_issue(session, issue)

    # Route as shown in the header: HM RHM PP ST FP fs Meena Puwai
    route = ["HandMade", "Repair HM", "PrePolish", "Setting", "Final Polish",
             "final setting", "Meena", "Puwai"]
    rows = []
    for i, name in enumerate(route, start=1):
        p = _process(session, name)
        if p is not None:
            rows.append({"process_id": p.id, "due_date": date(2026, 9, 9 + i)})
    production.set_job_steps(session, job, rows)
    step = {session.get(ManufacturingProcess, s.process_id).name: s for s in job.steps}

    # The five live rows (grams, gross / net). Issue on HandMade Vr 3018
    # carried only the stone weight - metal entered at that step (R6).
    d = date(2026, 9, 9)
    off, tuhin, buddha = workers["OFFICE"], workers["TUHIN"], workers["BUDDHAPOL"]
    live = [
        ("HandMade", off, "16:52", 3018, None, "16:52", 3241, "299.917", {"stone_wt": "299.917"}),
        ("Repair HM", tuhin, "16:52", 706, "299.917", "16:53", 707, "299.980", {}),
        ("HandMade", tuhin, "16:53", 3019, None, "16:53", 3242, "28.981", {}),
        ("Repair HM", off, "19:07", 708, "28.981", "19:07", 709, "28.981", {}),
        ("PrePolish", buddha, "19:07", 2937, "28.981", "19:08", 2082, "27.800", {}),
    ]
    for proc, worker, t_iss, vr_iss, w_iss, t_rcv, vr_rcv, w_rcv, extra in live:
        s = step[proc]
        production.post_voucher(session, job, s, "issue", worker.id, vr_date=d,
                                vr_time=t_iss, pcs=1, gross_wt=w_iss, net_wt=w_iss,
                                vr_no=vr_iss, **extra)
        production.post_voucher(session, job, s, "receive", worker.id, vr_date=d,
                                vr_time=t_rcv, pcs=1, gross_wt=w_rcv, net_wt=w_rcv,
                                vr_no=vr_rcv)

    # -- Order 1338 (KK): three necklaces waiting in the pending queue ------
    order1338 = Order(order_no=1338, order_date=date(2026, 9, 11), account_id=kk.id,
                      order_type="Customer", remark=_SAMPLE)
    session.add(order1338)
    session.flush()
    for sno, code in enumerate(("NS-1430", "NS-2171", "NS-1930"), start=1):
        sku = _sample_sku(session, code, necklace, metal595, "Necklace")
        session.add(OrderLine(order_id=order1338.id, sno=sno, product_sku_id=sku.id,
                              sku_desc="Necklace", metal_id=metal595.id if metal595 else None,
                              colour="Y", pcs=1))
    session.flush()
    session.refresh(order1338)
    for sno, line in enumerate(order1338.lines, start=1):
        session.add(Job(job_no=28621 + sno, order_id=order1338.id, line_sno=sno,
                        product_sku_id=line.product_sku_id, account_id=kk.id,
                        metal_id=line.metal_id, colour="Y", pcs=1, status="pending",
                        remark=_SAMPLE))
    session.flush()
