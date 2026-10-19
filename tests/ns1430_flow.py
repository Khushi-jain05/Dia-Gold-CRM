"""12 Oct walkthrough (docs/12-oct-flow-video.md): one stock order taken all
the way to ready stock on the legacy system - order 1680, NS-1430, job 29456,
MFG transfer Vr 1110, Stock No 45127, TAG 1218 - replayed on this app with
the same weights, stones and rates, checking every figure the screens showed.

    python tests/ns1430_flow.py

Runs on its own throw-away database. The stone prices of POLKI 18-20 and
above, RED FANCY, SOUTH SEA and SARAFA were not readable on the recording;
they are set here so the group totals match Item Search (POLKI 198,329,
COLOR STONE 51,366) - every other price is the one on screen.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DIAGOLD_DATA_DIR"] = tempfile.mkdtemp(prefix="diagold-ns1430-")

from datetime import date
from decimal import Decimal as D

from sqlalchemy import select

from diagold.db.session import SessionLocal, init_db
init_db()
from diagold.services.demo_data import load_demo
with SessionLocal() as _s:
    load_demo(_s)
    _s.commit()
from diagold.db.models import (Account, DailyMetalRate, Job, JobBagLine, LabourRate, Location,
                               Metal, Order, OrderLine, ProductSku, ProductSkuStone, StoneIssue,
                               StoneIssueLine, StoneSku)
from diagold.services import manufacturing as MF
from diagold.services import production as P
from diagold.services import sales as S

ON = date(2026, 10, 12)
fails, passes = [], 0


def check(label, got, want):
    global passes
    if got == want:
        passes += 1
        print("  PASS", label, got)
    else:
        fails.append(label)
        print("  FAIL", label, got, f"(want {want})")


# (sku, stone, size, type, sale price / ct, issued pcs, issued ct) - Vr 14800 / 14801
STONES = [
    ("daank", "daank", "", "", 0, 175, "12.600"),  # Req Wt 12.400, issued 12.600
    ("DIA. MIX", "DIA.", "MIX", "Diamond", 13500, 462, "6.300"),
    ("EMERALD OCTAGON 6*4", "EMERALD OCTAGON", "6*4", "Color Stone", 3000, 4, "1.920"),
    ("EMERALD OCTAGON 6*8", "EMERALD OCTAGON", "6*8", "Color Stone", 4000, 2, "2.600"),
    ("EMERALD OCTAGON 7*5", "EMERALD OCTAGON", "7*5", "Color Stone", 3250, 8, "7.400"),
    ("POLKI 10-12", "POLKI", "10-12", "Polki", 6700, 22, "0.850"),
    ("POLKI 12-14 V", "POLKI", "12-14", "Polki", 8100, 54, "2.860"),
    ("POLKI 14-16", "POLKI", "14-16", "Polki", 11600, 34, "2.850"),
    ("POLKI 16-18", "POLKI", "16-18", "Polki", 13900, 13, "1.420"),
    ("POLKI 18-20", "POLKI", "18-20", "Polki", 16000, 28, "3.450"),
    ("POLKI 20-22", "POLKI", "20-22", "Polki", 16000, 4, "0.690"),
    ("POLKI 22-24", "POLKI", "22-24", "Polki", 16000, 8, "1.400"),
    ("POLKI 24-26", "POLKI", "24-26", "Polki", 16000, 6, "1.340"),
    ("POLKI 26-28", "POLKI", "26-28", "Polki", 16000, 1, "0.250"),
    ("POLKI 28-30", "POLKI", "28-30", "Polki", 16000, 1, "0.240"),
    ("POLKI 8-10", "POLKI", "8-10", "Polki", "45871.08", 4, "0.120"),
    ("RED FANCY", "RED FANCY", "", "Color Stone", 1179, 49, "7.230"),
]
PEARLS = [  # Vr 14801 - by weight only
    ("SOUTH SEA/JAPANESE PEARLS", "SOUTH SEA/JAPANESE PEARLS", "", "Color Stone", "0.17", 0, "40.000"),
    ("FRESHWATER PEARL", "FRESHWATER PEARL", "", "Color Stone", 100, 0, "25.000"),
    ("SARAFA 00-0", "SARAFA", "00-0", "Color Stone", 0, 0, "45.900"),
    ("EMERALD BEADS EBDS-2", "EMERALD BEADS", "EBDS-2", "Color Stone", 250, 0, "0.500"),
]
# Received From Final Setting Vr 6138: (sku, return pcs, return ct, break pcs, break ct)
RETURNED = [("daank", 8, "0.580", 0, 0), ("DIA. MIX", 50, "0.750", 0, 0),
            ("POLKI 10-12", 1, "0.030", 0, 0), ("POLKI 12-14 V", 4, "0.210", 1, "0.050"),
            ("POLKI 16-18", 3, "0.320", 0, 0)]

with SessionLocal() as s:
    g = lambda m, **w: s.scalar(select(m).filter_by(**w))  # noqa: E731
    prim = g(Location, name="Primary")
    m590, wire = g(Metal, name="14KT 590"), g(Metal, name="14KT WIRE")
    stock = g(Account, name="stock") or Account(code="STOCK1680", name="stock",
                                                 account_type="Client",
                                                 group_name="Sundry Debtors")
    s.add(stock)
    office, factory = g(Account, name="Office"), g(Account, name="FACTORY")
    akshay = g(Account, name="akshay ji office")
    kailash, jagdish = g(Account, name="KAILASH MEENAKAR"), g(Account, name="JAGDISH PRASAD SONI")
    s.add(DailyMetalRate(rate_date=ON, metal_id=m590.id, rate_per_gram=D("8700.14"),
                         pure_rate_per_gram=D("14746")))
    s.add(LabourRate(metal_id=m590.id, rate=D("1200"), effective_from=ON, is_active=True))
    sku = g(ProductSku, sku_code="NS-1430")
    for old in s.scalars(select(ProductSkuStone).where(ProductSkuStone.product_id == sku.id)):
        s.delete(old)
    ids = {}
    for code, stone, size, typ, price, _p, _w in STONES + PEARLS:
        st = g(StoneSku, sku_code=code) or StoneSku(sku_code=code)
        st.stone, st.size, st.stone_type, st.sale_price, st.per = stone, size, typ, D(price), "Cts"
        s.add(st)
        s.flush()
        ids[code] = st.id
    s.flush()

    print("\n== 1. Order 1680 (stock) -> job, Default route")
    o = Order(order_no=P.next_number(s, Order.order_no), order_date=ON, account_id=stock.id,
              order_type="Stock")
    s.add(o)
    s.flush()
    s.add(OrderLine(order_id=o.id, sno=1, product_sku_id=sku.id, metal_id=m590.id, colour="Y",
                    pcs=1))
    s.flush()
    s.refresh(o)
    P.order_saved(s, o)
    check("order save leaves the line for the Job Card", s.scalars(select(Job).where(Job.order_id == o.id)).all(), [])
    pend = [r for r in P.pending_for_explode(s) if r["_order_id"] == o.id]
    check("Pending Orders For Explode: 1680 line, 1 pc", [(r["ord_no"], r["sku"], r["ord_pcs"]) for r in pend], [(o.order_no, "NS-1430", 1)])
    vr, made = P.explode_orders(s, [{"order_id": o.id, "sno": 1, "prod_pcs": 1, "job_pcs": 1, "due": ON}], vr_date=ON)
    job = s.scalar(select(Job).where(Job.job_no == made[0]))
    check("Job Card makes one job, line no longer pending", (len(made), job.job_card_vr, [r for r in P.pending_for_explode(s) if r["_order_id"] == o.id]), (1, vr, []))
    for bl in s.scalars(select(JobBagLine).where(JobBagLine.job_id == job.id)):
        s.delete(bl)
    s.flush()
    P.map_job(s, job, "Default", ON)
    check("route", P.route_string(s, job), "CAD CAM CS HM COL PP ST FP fs Meena Puwai")
    s.commit()

    def step(kind, worker, gross=None, net=None, stones=None, metal=None, allow=None):
        r = [r for r in P.pending_steps(s, kind) if r["_job_id"] == job.id][0]
        ln = {"job_id": job.id, "step_id": r["_step_id"], "pcs": 1,
              "gross": D(gross) if gross else None, "net": D(net) if net else None,
              "allow": D(allow) if allow is not None else None, "stones": stones or {},
              "metal": metal or []}
        vr = P.post_multi_voucher(s, kind, worker.id, [ln], vr_date=ON, vr_time="18:16")
        s.commit()
        return vr

    def last(kind):
        from diagold.db.models import JobVoucher
        return s.scalars(select(JobVoucher).where(JobVoucher.job_id == job.id,
                                                  JobVoucher.kind == kind)
                         .order_by(JobVoucher.id.desc())).first()

    print("\n== 2. CAD / CAMMING / CASTING unweighed, HandMade 50, COLOUR")
    for _ in range(3):
        step("issue", office)
        step("receive", office)
    check("CASTING received with no weight (issue was unweighed)",
          P.current_step(s, job)[0] is not None, True)
    step("issue", office)
    step("receive", office, "50.000", "50.000")
    step("issue", factory, "50.000", "50.000")
    step("receive", factory, "50.000", "50.000")

    print("\n== 3. PrePolish 3.00 %, Setting -1.24 %, Final Polish")

    def loss_pct():
        iss, rcv = last("issue"), last("receive")
        return ((D(str(iss.net_wt)) - D(str(rcv.net_wt))) / D(str(iss.net_wt)) * 100
                ).quantize(D("0.01"))
    step("issue", akshay, "50.000", "50.000")
    step("receive", akshay, "48.500", "48.500")
    check("PrePolish loss %", loss_pct(), D("3.00"))
    step("issue", akshay, "48.500", "48.500")
    step("receive", akshay, "49.100", "49.100")
    check("Setting loss % (gain)", loss_pct(), D("-1.24"))
    step("issue", akshay, "49.100", "49.100")
    step("receive", akshay, "49.100", "49.100")

    print("\n== 4. Stone Issue On Job-Card Vr 14800 (875 pcs / 53.520 ct)")
    si = StoneIssue(vr_no=P.next_number(s, StoneIssue.vr_no), job_id=job.id, vr_date=ON)
    s.add(si)
    s.flush()
    for n, (code, _st, size, typ, _pr, pcs, wt) in enumerate(STONES, 1):
        s.add(StoneIssueLine(issue_id=si.id, sno=n, location_id=prim.id, stone_sku_id=ids[code],
                             size=size, pcs=pcs, weight=D(wt), s_type=typ))
    s.flush()
    s.refresh(si)
    P.apply_stone_issue(s, si)
    s.commit()
    bag = {l.stone_sku_id: l for l in s.scalars(select(JobBagLine).where(
        JobBagLine.job_id == job.id))}
    rows = P.bag_ledger(s, job)
    check("bag received 875 pcs / 53.520 ct",
          (sum(r["rcvd"][0] for r in rows), sum(r["rcvd"][1] for r in rows)),
          (875, D("53.520")))

    print("\n== 5. final setting: issue 49.100 with all stones (St Wt 53.520)")
    step("issue", akshay, "49.100", "49.100",
         stones={bag[ids[c]].id: {"pcs": p, "wt": D(w)} for c, *_x, p, w in STONES})
    check("Issue St Wt", D(str(last("issue").stone_wt)), D("53.520"))

    print("\n== 6. Received From Final Setting Vr 6138: G 58.100 -> N 47.784 (2.68 %)")
    back = {bag[ids[c]].id: {"pcs": rp, "wt": D(rw), "break_pcs": bp, "break_wt": D(bw or 0)}
            for c, rp, rw, bp, bw in RETURNED}
    step("receive", akshay, "58.100", stones=back)
    check("N-Wt = G-Wt - set stones x 0.2", D(str(last("receive").net_wt)), D("47.784"))
    check("final setting loss %", loss_pct(), D("2.68"))
    check("stones in the piece 51.580 ct", P.piece_stone_ct(s, job), D("51.580"))

    print("\n== 7. Vr 14801 pearls by weight (111.400 ct), Meena, Puwai with 1.5 g wire")
    si2 = StoneIssue(vr_no=P.next_number(s, StoneIssue.vr_no), job_id=job.id, vr_date=ON)
    s.add(si2)
    s.flush()
    for n, (code, _st, size, typ, _pr, pcs, wt) in enumerate(PEARLS, 1):
        s.add(StoneIssueLine(issue_id=si2.id, sno=n, location_id=prim.id,
                             stone_sku_id=ids[code], size=size, pcs=pcs, weight=D(wt),
                             s_type=typ))
    s.flush()
    s.refresh(si2)
    P.apply_stone_issue(s, si2)
    s.commit()
    bag = {l.stone_sku_id: l for l in s.scalars(select(JobBagLine).where(
        JobBagLine.job_id == job.id))}
    step("issue", kailash, "58.100", "47.784")
    step("receive", kailash, "58.100", "47.784")
    step("issue", jagdish, "58.100", "47.784",
         stones={bag[ids[c]].id: {"pcs": 0, "wt": D(w)} for c, *_x, _p, w in PEARLS},
         metal=[{"location_id": prim.id, "metal_id": wire.id, "weight": D("1.500")}])
    check("Puwai issue St Wt 111.400 / Extra 1.500",
          (D(str(last("issue").stone_wt)), D(str(last("issue").extra))),
          (D("111.400"), D("1.500")))
    step("receive", jagdish, "81.880")
    check("Puwai N-Wt = 81.880 - 162.980 ct x 0.2", D(str(last("receive").net_wt)),
          D("49.284"))
    s.refresh(job)
    check("job pending for MFG transfer", job.status, "complete")
    s.refresh(o)
    check("order remark = stones used", o.remark,
          "daank/167/12.02, DIA./412/5.55, EMERALD BEADS/0/0.5, EMERALD OCTAGON/14/11.92, "
          "FRESHWATER PEARL/0/25, POLKI/166/14.86, RED FANCY/49/7.23, SARAFA/0/45.9, "
          "SOUTH SEA/JAPANESE PEARLS/0/40,")

    print("\n== 8. MFG Ready Stock Transfer Vr 1110 -> Stock 45127, TAG 1218")
    t = MF.post_transfer(s, [{"job_id": job.id, "margin_pct": D("50")}], vr_date=ON)
    s.commit()
    ln = t.lines[0]
    check("G / N / Fine", (D(str(ln.gross_wt)), D(str(ln.net_wt)), D(str(ln.fine_wt))),
          (D("81.880"), D("49.284"), D("29.078")))
    check("metal rate / amount", (D(str(ln.metal_rate)), D(str(ln.metal_amount))),
          (D("8700.1400"), D("428777.70")))
    check("labour 1,200 x N", D(str(ln.labour)), D("59140.80"))
    check("stone amount", D(str(ln.stone_amount)), D("324619.50"))
    check("total", D(str(ln.total)), D("812538.00"))
    check("price / tag", (D(str(ln.price_per_pcs)), ln.tag_text), (D("1218807.00"), "1218"))
    piece = MF.stock_for_transfer(s, t)[0]
    check("piece in stock at Primary", (piece.status, piece.location_id), ("in_stock", prim.id))

    print("\n== 9. Item Search value summary")
    st = S.describe(s, piece)["stones"]
    by = {}
    for x in st:
        b = S.stone_block(x)
        w, a = by.get(b, (D(0), D(0)))
        by[b] = (w + D(str(x["weight"])), a + S.stone_amount(x))
    check("DIAMOND 5.55 ct -> 74,925", by["DIAMOND"], (D("5.550"), D("74925.00")))
    check("POLKI 14.86 ct -> 198,329", (by["POLKI"][0], by["POLKI"][1].quantize(D("1"))),
          (D("14.860"), D("198329")))
    check("COLOR STONE 142.57 ct -> 51,366",
          (by["COLOR STONE"][0], by["COLOR STONE"][1].quantize(D("1"))),
          (D("142.570"), D("51366")))
    check("808 stones / 162.980 ct", (sum(int(x["pcs"]) for x in st),
                                       sum(D(str(x["weight"])) for x in st)),
          (808, D("162.980")))

    print("\n== 10. Stone Setting Analysis / Refining Analysis (9 Oct T-04)")
    from diagold.services import mis as MIS
    fs = [r for r in MIS.setting_analysis(s, ON, ON) if r["jobno"] == job.job_no
          and r["iss_stwt"]]
    check("final setting: ISS N / RTN N / LOSSWT / USE ST / USE PCS",
          [(r["iss_nwt"], r["rtn_nwt"], r["losswt"], r["use_stwt"], r["use_pcs"]) for r in fs],
          [(D("49.100"), D("47.784"), D("1.316"), D("51.580"), 808)])
    pp = [r for r in MIS.refining_analysis(s, ON, ON) if r["process"] == "PrePolish"]
    check("refining PrePolish loss % 3.00", [r["loss_pct"] for r in pp], [D("3.00")])

print(f"\nPASSED {passes}  FAILED {len(fails)}: {', '.join(fails) or 'none'}")
sys.exit(1 if fails else 0)
