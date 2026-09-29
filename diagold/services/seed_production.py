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

from datetime import date, timedelta
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
    SettingType,
    ProductSkuStone,
    StockMovement,
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
    _backfill_opening_movements(session)
    _seed_sample_jobs(session)
    _seed_report_samples(session)
    _seed_setting_prices(session)
    _seed_inventory_metals(session)
    _seed_bang577(session)
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
    fy_start = date(date.today().year if date.today().month >= 4 else date.today().year - 1, 4, 1)
    for sku in session.scalars(select(StoneSku).where(StoneSku.is_active.is_(True))):
        per = Decimal(str(sku.wt_per_pcs or 0))
        weight = (per * 100) if per > 0 else Decimal("25.000")
        production.post_opening_stock(session, primary.id, sku.id, 100, weight,
                                      as_of=fy_start, remark="sample opening stock")


def _backfill_opening_movements(session: Session) -> None:
    """A database from before the stock ledger existed has balances but no
    movements: treat what each location holds today as its opening, so the
    location x group report starts from the truth rather than from zero."""
    if session.scalar(select(func.count()).select_from(StockMovement)):
        return
    fy_start = date(date.today().year if date.today().month >= 4 else date.today().year - 1, 4, 1)
    for row in session.scalars(select(MaterialStock)):
        if not row.pcs and not row.weight:
            continue
        production.record_movement(session, row.location_id, row.material_class, row.ref_id,
                                   int(row.pcs), Decimal(str(row.weight)), size=row.size,
                                   ref_text=row.ref_text, kind="opening", mv_date=fy_start,
                                   ref_kind="opening", remark="opening carried from balances")
    session.flush()


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


# --------------------------------------------------------------------------
# Sample: the two jobs the 18 September reports were explained on
# --------------------------------------------------------------------------
def _seed_report_samples(session: Session) -> None:
    """Job 27751 - ordered 18 Aug, finished 8 Sep, "it took 21 days" (Job
    Stock Analysis); job 25006 - BANG-32 for stock, open since 1 April, the
    170-day line at the top of Job Analysis. Both marked SAMPLE."""
    if session.scalar(select(Job).where(Job.job_no.in_((27751, 25006)))):
        return
    if not session.scalar(select(func.count()).select_from(Order)):
        return  # the main sample did not load; nothing to hang these on
    metal590 = session.scalar(select(Metal).where(Metal.name == "14KT CASTING 590"))
    necklace = session.scalar(select(Item).where(Item.name == "NECKLACE"))
    bangle = session.scalar(select(Item).where(Item.name == "BANGLE"))
    office = session.scalar(select(Account).where(Account.code == "OFFICE"))
    ops = session.scalar(select(Account).where(Account.code == "OPS"))
    if ops is None:
        ops = Account(code="OPS", name="OPS", account_type="Client", group_name="Sundry Debtors")
        session.add(ops)
        session.flush()

    # -- 27751: complete, 21 days -------------------------------------------
    sku = _sample_sku(session, "NS-2649", necklace, metal590, "Necklace")
    order = Order(order_no=967, order_date=date(2026, 8, 18), account_id=ops.id,
                  delivery_date=date(2026, 8, 18), order_type="Customer", remark=_SAMPLE)
    session.add(order)
    session.flush()
    session.add(OrderLine(order_id=order.id, sno=1, product_sku_id=sku.id, sku_desc="Necklace",
                          metal_id=metal590.id if metal590 else None, colour="Y", pcs=1))
    job = Job(job_no=27751, order_id=order.id, line_sno=1, product_sku_id=sku.id,
              account_id=ops.id, metal_id=metal590.id if metal590 else None, colour="Y", pcs=1,
              prod_date=date(2026, 8, 18), prod_del_date=date(2026, 8, 18), status="pending",
              remark=_SAMPLE)
    session.add(job)
    session.flush()
    production.map_job(session, job, "Default", date(2026, 8, 18), days_per_step=2)
    job.mapped_on = date(2026, 8, 18)
    if office is not None:
        day = date(2026, 8, 19)
        weight = Decimal("35.249")
        for i, step in enumerate(job.steps):
            w = None if not step.weight_bearing else weight - Decimal("0.05") * i
            production.post_voucher(session, job, step, "issue", office.id, vr_date=day,
                                    vr_time="10:00", pcs=1, gross_wt=w, net_wt=w)
            back = None if w is None else (w - Decimal("0.02")).quantize(Decimal("0.001"))
            production.post_voucher(session, job, step, "receive", office.id,
                                    vr_date=day + timedelta(days=1), vr_time="18:00", pcs=1,
                                    gross_wt=back, net_wt=back)
            day += timedelta(days=2)
        job.completed_on = date(2026, 9, 8)
        job.status = "complete"

    # -- 25006: BANG-32 for stock, open since 1 April ----------------------
    sku2 = _sample_sku(session, "BANG-32", bangle, metal590, "Bangle")
    order2 = Order(order_no=1, order_date=date(2026, 4, 1), account_id=None,
                   delivery_date=date(2026, 4, 1), order_type="Stock", remark=_SAMPLE)
    session.add(order2)
    session.flush()
    session.add(OrderLine(order_id=order2.id, sno=1, product_sku_id=sku2.id, sku_desc="Bangle",
                          metal_id=metal590.id if metal590 else None, colour="Y", pcs=1))
    job2 = Job(job_no=25006, order_id=order2.id, line_sno=1, product_sku_id=sku2.id,
               metal_id=metal590.id if metal590 else None, colour="Y", pcs=1,
               prod_date=date(2026, 4, 1), prod_del_date=date(2026, 4, 1), status="pending",
               remark=_SAMPLE)
    session.add(job2)
    session.flush()
    production.map_job(session, job2, "Default", date(2026, 4, 1))
    job2.mapped_on = date(2026, 4, 1)
    if office is not None and job2.steps:
        production.post_voucher(session, job2, job2.steps[0], "issue", office.id,
                                vr_date=date(2026, 4, 1), vr_time="11:00", pcs=1)
    session.flush()


# --------------------------------------------------------------------------
# Sample: job 28853 / BANG-577, walked through on 28 September
# --------------------------------------------------------------------------
_SAMPLE_28 = "SAMPLE — legacy job 28853 from the 28 Sept walkthrough. Safe to delete."

# Setting price per piece by setting type, read off the legacy Stone Job Bag
# pop-up (Issue To final setting, Vr 5389): Polki 30.00, Diam 3.00 (28 Sept
# D4, closes 3 Sept Q7). Written only where the master still holds 0, so a
# rate the client has typed is never overwritten.
_SETTING_PRICES: dict[str, str] = {"Polki": "30", "Diam": "3"}


def _seed_setting_prices(session: Session) -> None:
    for name, price in _SETTING_PRICES.items():
        st = session.scalar(select(SettingType).where(SettingType.name == name))
        if st is not None and not Decimal(str(st.price or 0)):
            st.price = Decimal(price)


def _worker(session: Session, code: str, name: str) -> Account:
    a = session.scalar(select(Account).where(Account.code == code))
    if a is None:
        a = Account(code=code, name=name, account_type="Worker",
                    group_name="Accounts Payable")
        session.add(a)
        session.flush()
    return a


def _seed_bang577(session: Session) -> None:
    """Job 28853 exactly as the legacy Job History and Job Bag showed it:
    the loss per step (§4.5), the Rs 2,400 setting labour on the final-setting
    row (§4.7) and a bag that balances to 0 on every line (§4.6). It is the
    worked example for loss, setting labour and the bag rules."""
    if session.scalar(select(Job).where(Job.job_no == 28853)):
        return
    if session.scalar(select(Order).where(Order.order_no == 1436)):
        return
    metal = session.scalar(select(Metal).where(Metal.name == "18KT Gold"))
    bangle = session.scalar(select(Item).where(Item.name == "BANGLE"))
    primary = session.scalar(select(Location).where(Location.name == "Primary"))
    rajat = session.scalar(select(Location).where(Location.name == "RAJAT JI")) or primary
    procs = {n: _process(session, n) for n in (
        "CAD", "CAMMING", "CASTING", "HandMade", "COLOUR", "PrePolish", "Setting",
        "Final Polish", "final setting", "Puwai")}
    types = {st.name: st for st in session.scalars(select(SettingType))}
    if primary is None or any(p is None for p in procs.values()):
        return
    client = session.scalar(select(Account).where(Account.code == "MJDUBAI"))
    if client is None:
        client = Account(code="MJDUBAI", name="MJ DUBAI", account_type="Client",
                         group_name="Sundry Debtors")
        session.add(client)
        session.flush()
    office = _worker(session, "OFFICE", "Office")
    # Names as far as the legacy grid showed them; complete from the export.
    prasenjit = _worker(session, "PRASENJIT", "PRASENJIT")
    factory = _worker(session, "FACTORY", "FACTORY")
    buddha = _worker(session, "BUDDHAPOL", "BUDDHA POL")
    rakesh = _worker(session, "RAKESHS", "rakesh sarkar")
    akshay = _worker(session, "AKSHAYJ", "akshay j")
    jagdish = _worker(session, "JAGDISHPRA", "JAGDISH PRA")

    sku = _sample_sku(session, "BANG-577", bangle, metal, "Bangle")
    order = Order(order_no=1436, order_date=date(2026, 9, 22), account_id=client.id,
                  order_type="Customer",
                  remark="daank/42/3.4,DIA./72/0.89,DIA. (-2)/308/2.37,POLKI/42/3.85,"
                         "RED FANCY/76/6.71,")
    session.add(order)
    session.flush()
    session.add(OrderLine(order_id=order.id, sno=1, product_sku_id=sku.id, sku_desc="Bangle",
                          metal_id=metal.id if metal else None, colour="Y", pcs=1))
    job = Job(job_no=28853, order_id=order.id, line_sno=1, product_sku_id=sku.id,
              account_id=client.id, metal_id=metal.id if metal else None, colour="Y", pcs=1,
              prod_date=date(2026, 9, 22), status="pending", remark=_SAMPLE_28)
    session.add(job)
    session.flush()

    # Route CD CAM CST HM CLR PP ST FP fs fs Puwai.
    route = ["CAD", "CAMMING", "CASTING", "HandMade", "COLOUR", "PrePolish", "Setting",
             "Final Polish", "final setting", "final setting", "Puwai"]
    production.set_job_steps(session, job, [
        {"process_id": procs[n].id, "due_date": date(2026, 9, 22)} for n in route])
    steps = list(job.steps)
    # This job was first weighed at HandMade, as the legacy rows show.
    for st in steps[:3]:
        st.weight_bearing = False
    session.flush()

    # Stones into the bag (opening: already with the job in the legacy).
    bag_spec = [  # particulars, size, pcs, weight, setting type, location
        ("daank", "", 48, "3.880", None, primary),
        ("POLKI", "12-14", 5, "0.360", "Polki", rajat),
        ("POLKI", "16-18", 43, "4.020", "Polki", rajat),
        ("DIA.", "MIX", 80, "0.980", "Diam", rajat),
        ("DIA. (-2)", "", 340, "2.620", "Diam", rajat),
        ("RED FANCY", "", 76, "6.710", None, rajat),
    ]
    issue = StoneIssue(vr_no=production.next_number(session, StoneIssue.vr_no), job_id=job.id,
                       vr_date=date(2026, 9, 22), is_opening=True, remark=_SAMPLE_28)
    session.add(issue)
    session.flush()
    for n, (part, size, pcs, wt, _t, loc) in enumerate(bag_spec, start=1):
        session.add(StoneIssueLine(issue_id=issue.id, sno=n, particulars=part, size=size,
                                   location_id=loc.id if loc else None, pcs=pcs,
                                   weight=Decimal(wt), price_unit="Cts"))
    session.flush()
    session.refresh(issue)
    production.apply_stone_issue(session, issue)
    bag = {(l.particulars, l.size): l for l in session.scalars(
        select(JobBagLine).where(JobBagLine.job_id == job.id))}
    for part, size, _p, _w, stype, loc in bag_spec:
        line = bag[(part, size)]
        line.setting_type_id = types[stype].id if stype and stype in types else None
        line.source_location_id = loc.id if loc else None
    session.flush()

    def post(step, worker, d, t_iss, vr_iss, w_iss, t_rcv, vr_rcv, w_rcv, allow):
        gi, ni = w_iss if w_iss else (None, None)
        gr, nr = w_rcv if w_rcv else (None, None)
        production.post_voucher(session, job, step, "issue", worker.id, vr_date=d[0],
                                vr_time=t_iss, pcs=1, gross_wt=gi, net_wt=ni, vr_no=vr_iss,
                                allow_loss_pct=allow)
        production.post_voucher(session, job, step, "receive", worker.id, vr_date=d[1],
                                vr_time=t_rcv, pcs=1, gross_wt=gr, net_wt=nr, vr_no=vr_rcv,
                                allow_loss_pct=allow)

    def give(worker, lines):
        return lambda: [production.bag_move(session, bag[k], "iss", p, Decimal(w),
                                            worker_id=worker.id, mv_date=date(2026, 9, 27))
                        for k, p, w in lines]

    def back(worker, lines):
        return [lambda k=k, p=p, w=w: production.bag_move(
            session, bag[k], "back", p, Decimal(w), worker_id=worker.id,
            mv_date=date(2026, 9, 27)) for k, p, w in lines]

    d25, d26, d27, d28 = (date(2026, 9, n) for n in (25, 26, 27, 28))
    post(steps[0], office, (d25, d25), "13:41", 2918, None, "13:42", 2915, None, 0)
    post(steps[1], office, (d25, d25), "13:42", 2879, None, "13:42", 2879, None, 0)
    post(steps[2], office, (d25, d25), "13:42", 2883, None, "13:42", 2881, None, 0)
    post(steps[3], prasenjit, (d25, d25), "13:42", 3437, None,
         "13:43", 3692, ("32.610", "32.610"), "3.5")
    post(steps[4], factory, (d25, d25), "14:15", 2825, ("32.610", "32.610"),
         "14:16", 2805, ("32.610", "32.610"), 0)
    post(steps[5], buddha, (d25, d25), "14:16", 3301, ("32.610", "32.610"),
         "17:33", 2333, ("31.380", "31.380"), "0.35")
    # Setting: RED FANCY goes with the setter here; it carries no setting type.
    production.post_voucher(session, job, steps[6], "issue", rakesh.id, vr_date=d26,
                            vr_time="11:25", pcs=1, gross_wt="31.380", net_wt="31.380",
                            vr_no=3963, allow_loss_pct="3")
    give(rakesh, [(("RED FANCY", ""), 76, "6.710")])()
    production.post_voucher(session, job, steps[6], "receive", rakesh.id, vr_date=d27,
                            vr_time="16:07", pcs=1, gross_wt="31.680", net_wt="31.680",
                            vr_no=4370, allow_loss_pct="3")
    post(steps[7], buddha, (d27, d27), "16:07", 3356, ("31.680", "31.680"),
         "16:07", 3349, ("31.510", "31.510"), 0)
    # final setting (rakesh): 516 pcs / 11.860 ct out, the unset ones back.
    production.post_voucher(session, job, steps[8], "issue", rakesh.id, vr_date=d27,
                            vr_time="16:07", pcs=1, gross_wt="31.510", net_wt="31.510",
                            vr_no=5389, allow_loss_pct=0, stone_wt="11.860")
    give(rakesh, [(("daank", ""), 48, "3.880"), (("POLKI", "12-14"), 5, "0.360"),
                  (("POLKI", "16-18"), 43, "4.020"), (("DIA.", "MIX"), 80, "0.980"),
                  (("DIA. (-2)", ""), 340, "2.620")])()
    for fn in back(rakesh, [(("daank", ""), 6, "0.480"), (("POLKI", "12-14"), 1, "0.070"),
                            (("POLKI", "16-18"), 5, "0.460"), (("DIA.", "MIX"), 8, "0.090"),
                            (("DIA. (-2)", ""), 32, "0.250")]):
        fn()
    production.post_voucher(session, job, steps[8], "receive", rakesh.id, vr_date=d27,
                            vr_time="16:08", pcs=1, gross_wt="32.279", net_wt="30.177",
                            vr_no=5409, allow_loss_pct=0)
    # What came back leaves the bag: to stock, and one POLKI 16-18 broken.
    for k, p, w in ((("daank", ""), 6, "0.480"), (("POLKI", "12-14"), 1, "0.070"),
                    (("POLKI", "16-18"), 4, "0.420"), (("DIA.", "MIX"), 8, "0.090"),
                    (("DIA. (-2)", ""), 32, "0.250")):
        production.bag_move(session, bag[k], "rtn", p, Decimal(w), mv_date=d27,
                            remark=_SAMPLE_28)
    production.bag_move(session, bag[("POLKI", "16-18")], "break", 1, Decimal("0.040"),
                        mv_date=d27, remark=_SAMPLE_28)
    # The legacy grid shows no loss on this row although net went 30.177 ->
    # 30.257, and its job total (3.574) leaves it out; here it reads -0.080,
    # so the job totals 3.494. Asked as 28 Sept Q13.
    post(steps[9], akshay, (d27, d27), "16:10", 5390, ("32.279", "30.177"),
         "16:10", 5410, ("33.701", "30.257"), 0)
    production.post_voucher(session, job, steps[10], "issue", jagdish.id, vr_date=d28,
                            vr_time="15:50", pcs=1, gross_wt="33.701", net_wt="30.257",
                            vr_no=3058, allow_loss_pct=0)
    production.post_voucher(session, job, steps[10], "receive", jagdish.id, vr_date=d28,
                            vr_time="15:51", pcs=1, gross_wt="33.701", net_wt="30.257",
                            vr_no=3086, allow_loss_pct=0)
    session.flush()


# Heads read off the legacy Metal Analysis (28 Sept §4.14) that the metal
# master did not carry - without 24KT there is nothing to buy. Title in parts
# per 1000 and base as the screen showed them; added only where no head of
# that name exists, so the client's own master always wins.
_ANALYSIS_HEADS: tuple[tuple[str, str, str], ...] = (
    ("24KT Gold", "1000", "GOLD"),
    ("24KT CASTING", "995", "GOLD"),
    ("22KT CASTING", "922.5", "GOLD"),
    ("22KT WIRE", "916", "GOLD"),
    ("ALLOY14KT", "595", "ALLOY"),
    ("ALLOY18KT", "760", "ALLOY"),
)


def _seed_inventory_metals(session: Session) -> None:
    from diagold.services.seed import metal_code
    names = {n.lower() for n in session.scalars(select(Metal.name)) if n}
    taken = {c for c in session.scalars(select(Metal.code)) if c}
    for name, title, base in _ANALYSIS_HEADS:
        if name.lower() in names:
            continue
        session.add(Metal(code=metal_code(name, taken), name=name, print_on_tag=title,
                          base_metal=base, purity_fineness=Decimal(title), colour="Y",
                          hsn_code="7108" if name.startswith("24KT") else "7113",
                          is_active=True))
    session.flush()
