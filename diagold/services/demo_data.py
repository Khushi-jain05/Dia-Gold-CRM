"""Demo data for walking the whole 28 September flow by hand.

Loaded into its own data folder (see ``diagold/demo.py``), never into the
working database. It adds, on top of the first-run data:

* the day's rates the price engine needs - fine (24K) rate 14,713 / g,
  labour 1,200 / g, a 50% tag mark-up - dated 25-09-2026;
* Inventory: the legacy metal purchase (800 g 24KT = Rs 1,24,64,400), casting
  metal at RAJESH JI, a 1.625 g issue to CHAND KUMAR HAZRA and a receipt
  back with 3.5% wastage, and a stone purchase (POLKI 12-14, EMERALD PEAR);
* order 9001 for KK JEWELS with three jobs left at three different points:
  the first only mapped (CAD pending), the second out with PRASENJIT at
  HandMade, the third through its whole route with stones set - pending for
  MFG Transfer.

``docs/demo-walkthrough.md`` lists what to do on each screen and the figure
each step should show.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    DailyMetalRate,
    InvVoucher,
    InvVoucherLine,
    Job,
    JobBagLine,
    LabourRate,
    Location,
    MarginSet,
    Metal,
    Order,
    OrderLine,
    ProductSku,
    SettingType,
    StoneIssue,
    StoneIssueLine,
    StoneSku,
)
from diagold.services import inventory as INV
from diagold.services import production as P

DEMO_ORDER_NO = 9001
DAY = date(2026, 9, 25)
FINE_RATE = Decimal("14713")        # 24K per gram: 14,713 x 0.590 = 8,680.67
LABOUR_RATE = Decimal("1200")       # STD per gram of net weight
MARGIN_PCT = Decimal("50")          # tag mark-up
DEMO_METAL = "14KT 590"
DEMO_SKU = "NS-1430"


def _account(s: Session, code: str, name: str, kind: str, group: str) -> Account:
    a = s.scalar(select(Account).where(Account.code == code))
    if a is None:
        a = Account(code=code, name=name, account_type=kind, group_name=group)
        s.add(a)
        s.flush()
    return a


def _one(s: Session, model, **where) -> Any:
    q = select(model)
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    obj = s.scalar(q)
    if obj is None:
        raise RuntimeError(f"Demo data needs {model.__name__} {where} from the first-run data.")
    return obj


def _inv(s: Session, vr_type: str, account: Account, d: date,
         lines: list[dict[str, Any]], ref: str = "") -> InvVoucher:
    v = InvVoucher(vr_type=vr_type, vr_no=INV.next_vr_no(s, vr_type), vr_date=d,
                   account_id=account.id, ref_no=ref, remark="demo data")
    s.add(v)
    s.flush()
    for n, row in enumerate(lines, start=1):
        INV.fill_line(s, vr_type, row)
        s.add(InvVoucherLine(voucher_id=v.id, sno=n, **row))
    s.flush()
    s.refresh(v)
    INV.post_voucher(s, v)
    return v


def _step(s: Session, job: Job, kind: str, worker: Account, d: date, time: str, *,
          gross: Any = None, net: Any = None, allow: Any = None,
          stones: dict[int, int] | None = None) -> int:
    """Post the job's current step (issue or receive) the way the
    Manufacturing Issue / Received voucher does."""
    rows = [r for r in P.pending_steps(s, kind) if r["_job_id"] == job.id]
    if not rows:
        raise RuntimeError(f"Job {job.job_no}: nothing pending to {kind}.")
    r = rows[0]
    line = {"job_id": job.id, "step_id": r["_step_id"], "pcs": job.pcs,
            "gross": Decimal(str(gross)) if gross is not None else None,
            "net": Decimal(str(net)) if net is not None else None,
            "allow": Decimal(str(allow)) if allow is not None else None,
            "stones": stones or {}, "metal": [], "remark": "demo data"}
    return P.post_multi_voucher(s, kind, worker.id, [line], vr_date=d, vr_time=time)


def load_demo(s: Session) -> str:
    """Add the demo data. Safe to call twice - the second call does nothing."""
    if s.scalar(select(Order).where(Order.order_no == DEMO_ORDER_NO)):
        return "Demo data is already loaded."

    # -- masters the price engine and vouchers read -----------------------
    metal = _one(s, Metal, name=DEMO_METAL)
    gold24 = _one(s, Metal, name="24KT Gold")
    for m in (metal, gold24):
        if not s.scalar(select(DailyMetalRate).where(DailyMetalRate.metal_id == m.id,
                                                    DailyMetalRate.rate_date == DAY)):
            s.add(DailyMetalRate(rate_date=DAY, metal_id=m.id, rate_per_gram=FINE_RATE,
                                 pure_rate_per_gram=FINE_RATE, remark="demo: 24K fine rate"))
    s.add(LabourRate(metal_id=metal.id, karat="14KT", rate=LABOUR_RATE, unit="Per Gram",
                     weight_basis="Net Weight", effective_from=date(2026, 9, 1)))
    if not s.scalar(select(MarginSet).where(MarginSet.tagprice_margin.is_(True))):
        s.add(MarginSet(margin_key="DEMO TAG 50", tagprice_margin=True,
                        tag_margin_percent=MARGIN_PCT, overall_percent=MARGIN_PCT))
    shrikant = _account(s, "SHRIKANT", "SHRIKANT", "Supplier", "Sundry Creditors")
    chand = _account(s, "CHANDKH", "CHAND KUMAR HAZRA", "Worker", "Karigar")
    workers = {code: _one(s, Account, code=code) for code in (
        "OFFICE", "PRASENJIT", "FACTORY", "BUDDHAPOL", "RAKESHS", "AKSHAYJ",
        "JAGDISHPRA")}
    client = _one(s, Account, code="KK")
    primary = _one(s, Location, name="Primary")
    rajesh = _one(s, Location, name="RAJESH JI")
    polki = _one(s, StoneSku, sku_code="POLKI 12-14")
    emerald = _one(s, StoneSku, sku_code="EMERALD PEAR 3*4")
    polki_type = _one(s, SettingType, name="Polki")
    # Client price charts as on the 5 Oct call: "A" and MANNU BHAI 1,175 / gm
    # (T-05) - RUBY SINGH is on MANNU BHAI to try "Prices From Client Chart".
    from diagold.db.models import PriceChart
    mannu = s.scalar(select(PriceChart).where(PriceChart.name == "MANNU BHAI"))
    if mannu is None:
        mannu = PriceChart(name="MANNU BHAI", labour_per_gm=Decimal("1175"))
        s.add(mannu)
    if not s.scalar(select(PriceChart).where(PriceChart.name == "A")):
        s.add(PriceChart(name="A"))
    s.flush()
    ruby = s.scalar(select(Account).where(Account.code == "RUBY"))
    if ruby is None:
        ruby = s.scalar(select(Account).where(Account.name == "RUBY SINGH"))
    if ruby is not None and ruby.price_chart_id is None:
        ruby.price_chart_id = mannu.id
    s.flush()

    # -- Inventory (28 Sept §4.12) ----------------------------------------
    _inv(s, "metal_purchase", shrikant, date(2026, 9, 23), [
        {"location_id": primary.id, "metal_id": gold24.id, "mt_type": "Actual", "colour": "Y",
         "weight": Decimal("300"), "price": Decimal("15598")},
        {"location_id": primary.id, "metal_id": gold24.id, "mt_type": "Actual", "colour": "Y",
         "weight": Decimal("300"), "price": Decimal("15570")},
        {"location_id": primary.id, "metal_id": gold24.id, "mt_type": "Actual", "colour": "Y",
         "weight": Decimal("200"), "price": Decimal("15570")},
    ], ref="DEMO-PUR")
    _inv(s, "metal_purchase", shrikant, date(2026, 9, 23), [
        {"location_id": rajesh.id, "metal_id": metal.id, "mt_type": "Actual", "colour": "Y",
         "weight": Decimal("200"), "price": Decimal("8680.67")},
    ], ref="DEMO-CASTING")
    _inv(s, "metal_issue", chand, date(2026, 9, 24), [
        {"location_id": rajesh.id, "metal_id": metal.id, "mt_type": "Actual", "colour": "Y",
         "weight": Decimal("1.625")},
    ])
    _inv(s, "metal_receipt", chand, date(2026, 9, 25), [
        {"location_id": rajesh.id, "metal_id": metal.id, "mt_type": "Actual", "colour": "Y",
         "weight": Decimal("1.000"), "wastage_pct": Decimal("3.5")},
    ])
    _inv(s, "stone_purchase", shrikant, date(2026, 9, 23), [
        {"location_id": primary.id, "stone_sku_id": polki.id, "size": polki.size or "",
         "pcs": 100, "weight": Decimal("8.000"), "price": Decimal("8100")},
        {"location_id": primary.id, "stone_sku_id": emerald.id, "size": emerald.size or "",
         "pcs": 50, "weight": Decimal("5.000"), "price": Decimal("2000")},
    ], ref="DEMO-STONE")

    # -- Order 9001 -> three jobs ------------------------------------------
    sku = _one(s, ProductSku, sku_code=DEMO_SKU)
    order = Order(order_no=DEMO_ORDER_NO, order_date=DAY, account_id=client.id,
                  order_type="Customer", ref="DEMO", terms="30 days credit",
                  priority="Normal", remark="Demo order - see docs/demo-walkthrough.md",
                  delivery_date=date(2026, 10, 10))
    s.add(order)
    s.flush()
    for sno, cref in enumerate(("DEMO-A", "DEMO-B", "DEMO-C"), start=1):
        s.add(OrderLine(order_id=order.id, sno=sno, product_sku_id=sku.id,
                        sku_desc=sku.sku_code, c_ref=cref, metal_id=metal.id, colour="Y",
                        size="7", pcs=1, delivery_date=date(2026, 10, 10)))
    s.flush()
    s.refresh(order)
    jobs = P.sync_jobs_for_order(s, order)
    for j in jobs:
        P.map_job(s, j, "Default", DAY)
    job_a, job_b, job_c = jobs

    # Stones into the bags of B and C (Stone Issue on Job-Card).
    for job in (job_b, job_c):
        issue = StoneIssue(vr_no=P.next_number(s, StoneIssue.vr_no), job_id=job.id,
                           vr_date=DAY, account_id=client.id, remark="demo data")
        s.add(issue)
        s.flush()
        s.add_all([
            StoneIssueLine(issue_id=issue.id, sno=1, location_id=primary.id,
                           stone_sku_id=polki.id, size=polki.size or "", pcs=10,
                           weight=Decimal("0.800"), price_unit="Cts", s_type="Polki"),
            StoneIssueLine(issue_id=issue.id, sno=2, location_id=primary.id,
                           stone_sku_id=emerald.id, size=emerald.size or "", pcs=5,
                           weight=Decimal("0.500"), price_unit="Cts", s_type="CS"),
        ])
        s.flush()
        s.refresh(issue)
        P.apply_stone_issue(s, issue)
        for line in s.scalars(select(JobBagLine).where(JobBagLine.job_id == job.id,
                                                        JobBagLine.stone_sku_id == polki.id)):
            P.set_bag_setting_type(s, line, polki_type.id)

    w = workers
    # Job B: CAD, CAMMING, CASTING done; out with PRASENJIT at HandMade.
    _step(s, job_b, "issue", w["OFFICE"], date(2026, 9, 25), "10:00")
    _step(s, job_b, "receive", w["OFFICE"], date(2026, 9, 25), "12:00")
    _step(s, job_b, "issue", w["OFFICE"], date(2026, 9, 25), "12:10")
    _step(s, job_b, "receive", w["OFFICE"], date(2026, 9, 25), "15:00")
    _step(s, job_b, "issue", chand, date(2026, 9, 26), "10:00",
          gross="15.000", net="15.000", allow="0")
    _step(s, job_b, "receive", chand, date(2026, 9, 26), "17:00",
          gross="14.800", net="14.800")
    _step(s, job_b, "issue", w["PRASENJIT"], date(2026, 9, 27), "10:00",
          gross="14.800", net="14.800", allow="3.5")

    # Job C: the whole route, stones set at Setting.
    c = job_c
    _step(s, c, "issue", w["OFFICE"], date(2026, 9, 25), "10:05")
    _step(s, c, "receive", w["OFFICE"], date(2026, 9, 25), "12:05")
    _step(s, c, "issue", w["OFFICE"], date(2026, 9, 25), "12:15")
    _step(s, c, "receive", w["OFFICE"], date(2026, 9, 25), "15:05")
    _step(s, c, "issue", chand, date(2026, 9, 26), "10:05",
          gross="13.500", net="13.500", allow="0")
    _step(s, c, "receive", chand, date(2026, 9, 26), "17:05", gross="13.200", net="13.200")
    _step(s, c, "issue", w["PRASENJIT"], date(2026, 9, 26), "17:30",
          gross="13.200", net="13.200", allow="3.5")
    _step(s, c, "receive", w["PRASENJIT"], date(2026, 9, 27), "11:00",
          gross="13.000", net="13.000")
    _step(s, c, "issue", w["FACTORY"], date(2026, 9, 27), "11:10", gross="13.000", net="13.000")
    _step(s, c, "receive", w["FACTORY"], date(2026, 9, 27), "12:00", gross="13.000", net="13.000")
    _step(s, c, "issue", w["BUDDHAPOL"], date(2026, 9, 27), "12:10",
          gross="13.000", net="13.000", allow="0.35")
    _step(s, c, "receive", w["BUDDHAPOL"], date(2026, 9, 27), "16:00",
          gross="12.900", net="12.900")
    bag = {l.stone_sku_id: l for l in s.scalars(select(JobBagLine)
                                                .where(JobBagLine.job_id == c.id))}
    _step(s, c, "issue", w["RAKESHS"], date(2026, 9, 27), "16:10", gross="12.900",
          net="12.900", allow="3", stones={bag[polki.id].id: 10, bag[emerald.id].id: 5})
    _step(s, c, "receive", w["RAKESHS"], date(2026, 9, 28), "11:00", gross="13.080",
          net="12.850", stones={bag[polki.id].id: 2})
    _step(s, c, "issue", w["BUDDHAPOL"], date(2026, 9, 28), "11:10",
          gross="13.080", net="12.850", allow="0.35")
    _step(s, c, "receive", w["BUDDHAPOL"], date(2026, 9, 28), "14:00",
          gross="12.990", net="12.760")
    _step(s, c, "issue", w["AKSHAYJ"], date(2026, 9, 28), "14:10",
          gross="12.990", net="12.760", allow="0")
    _step(s, c, "receive", w["AKSHAYJ"], date(2026, 9, 28), "16:00",
          gross="12.970", net="12.740")
    _step(s, c, "issue", w["JAGDISHPRA"], date(2026, 9, 28), "16:10",
          gross="12.970", net="12.740")
    _step(s, c, "receive", w["JAGDISHPRA"], date(2026, 9, 29), "10:00",
          gross="12.950", net="12.720")
    _step(s, c, "issue", w["JAGDISHPRA"], date(2026, 9, 29), "10:10",
          gross="12.950", net="12.720")
    _step(s, c, "receive", w["JAGDISHPRA"], date(2026, 9, 29), "12:00",
          gross="12.930", net="12.700")
    s.flush()
    return (f"Demo data loaded: order {DEMO_ORDER_NO}, jobs {job_a.job_no} (CAD pending), "
            f"{job_b.job_no} (out at HandMade), {job_c.job_no} (pending for MFG Transfer).")
