"""End-to-end check of every module on a fresh demo database, with data:
masters, inventory, order -> job -> every manufacturing step (edit / delete),
job costing, MFG transfer (split / edit / delete), sale / approval / return /
From Order, repair, ready-items purchase / return / opening, metal and stone
sale / approval, stock transfer (melting, location), every register, and the
invariants (accounts Dr = Cr, stock = sum of movements).

    python tests/e2e_flow.py

Runs on its own throw-away database; the working data is never touched.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = tempfile.mkdtemp(prefix="diagold-e2e-")
os.environ["DIAGOLD_DATA_DIR"] = OUT            # before diagold.config is read

from collections import defaultdict
from datetime import date
from decimal import Decimal as D

from sqlalchemy import func, select

from diagold.db.session import SessionLocal, init_db
init_db()
from diagold.services.demo_data import load_demo
with SessionLocal() as _s:
    load_demo(_s)
    _s.commit()
from diagold.db.models import (Account, AccountEntry, InvVoucher, InvVoucherLine, Job, JobBagLine,
                               JobVoucher, Location, MaterialStock, Metal, Order, OrderLine,
                               ProductSku, SettingType, StockItem, StockMovement, StoneIssue,
                               StoneIssueLine, StoneSku, DailyMetalRate)
from diagold.services import (inventory as INV, production as P, manufacturing as MF,
                              job_costing as JC, sales as S, stock_transfer as ST,
                              registers as RG, attachments as AT, rates)
from diagold.services.production import ProductionError

T = date(2026, 9, 30)
FY = (date(2026, 4, 1), date(2027, 3, 31))
fails, passes = [], 0


def check(label, got, want):
    global passes
    if got == want:
        passes += 1
        print("  PASS", label, got)
    else:
        fails.append(label)
        print("  FAIL", label, got, f"(want {want})")


def refused(label, fn):
    global passes
    try:
        fn()
    except (ProductionError, ValueError) as e:
        passes += 1
        print("  PASS refused:", label, "->", str(e)[:90])
        return
    fails.append(label)
    print("  FAIL not refused:", label)


def inv(s, vt, acct, lines, **h):
    v = InvVoucher(vr_type=vt, vr_no=INV.next_vr_no(s, vt), vr_date=T,
                   account_id=acct.id if acct else None, **h)
    s.add(v); s.flush()
    for n, r in enumerate(lines, 1):
        INV.fill_line(s, vt, r); s.add(InvVoucherLine(voucher_id=v.id, sno=n, **r))
    s.flush(); s.refresh(v); INV.post_voucher(s, v); return v


def stock_consistent(s):
    """Every MaterialStock balance = sum of its StockMovements."""
    acc = defaultdict(lambda: [0, D(0)])
    # Breakage is written to the ledger only (broken stones credit no stock -
    # 18 Sept Q5), so it is left out of the comparison.
    for m in s.scalars(select(StockMovement).where(StockMovement.kind != "breakage")):
        k = (m.location_id, m.material_class, m.ref_id, m.size or "", m.ref_text or "")
        acc[k][0] += int(m.pcs); acc[k][1] += D(str(m.weight))
    bad = []
    for r in s.scalars(select(MaterialStock)):
        k = (r.location_id, r.material_class, r.ref_id, r.size or "", r.ref_text or "")
        if (int(r.pcs), D(str(r.weight)).quantize(D("0.0001"))) != (acc[k][0], acc[k][1].quantize(D("0.0001"))):
            if int(r.pcs) or D(str(r.weight)) or acc[k][0] or acc[k][1]:
                bad.append(k)
    return bad


def ledger_balanced(s):
    dr = s.scalar(select(func.sum(AccountEntry.debit))) or 0
    cr = s.scalar(select(func.sum(AccountEntry.credit))) or 0
    return D(str(dr)) == D(str(cr))


with SessionLocal() as s:
    g = lambda m, **w: s.scalar(select(m).filter_by(**w))
    print("\n== A. Masters")
    sup = Account(code="TESTSUP", name="TEST SUPPLIER", account_type="Accounts", group_name="Accounts Payable")
    rahul = Account(code="RAHUL", name="RAHUL JI", account_type="Worker", group_name="x")
    mb = Account(code="MANNU", name="MANNU BHAI", account_type="Client", group_name="Sundry Debtors")
    s.add_all([sup, rahul, mb]); s.flush()
    kk, chand = g(Account, code="KK"), g(Account, code="CHANDKH")
    prim, raj = g(Location, name="Primary"), g(Location, name="RAJESH JI")
    m590, g24 = g(Metal, name="14KT 590"), g(Metal, name="24KT Gold")
    polki, em = g(StoneSku, sku_code="POLKI 12-14"), g(StoneSku, sku_code="EMERALD PEAR 3*4")
    info = rates.rate_for(s, m590.id, T)
    check("daily rate 14,713 in force", info.rate, D("14713.0000"))
    check("metal price 14KT 590", P.metal_price(s, m590.id, T), D("8680.67"))

    print("\n== B. Inventory: purchase / issue / receipt / opening / check bal / show O/S")
    sp = inv(s, "stone_purchase", sup, [
        {"location_id": prim.id, "stone_sku_id": polki.id, "size": polki.size or "", "pcs": 20, "weight": D("1.600"), "price": D("8100"), "lot_no": "CERT-9"},
        {"location_id": prim.id, "stone_sku_id": em.id, "size": em.size or "", "pcs": 10, "weight": D("1.000"), "price": D("2000")}])
    check("stone purchase amounts", [l.amount for l in sp.lines], [D("12960.00"), D("2000.00")])
    mp = inv(s, "metal_purchase", sup, [{"location_id": raj.id, "metal_id": m590.id, "colour": "Y", "weight": D("50"), "price": D("8680.67")}])
    check("metal purchase amount / fine", (mp.lines[0].amount, D(str(mp.lines[0].fine_wt)).quantize(D("0.001"))), (D("434033.50"), D("29.500")))
    mi = inv(s, "metal_issue", chand, [{"location_id": raj.id, "metal_id": m590.id, "weight": D("2.000")}])
    check("issue fine", D(str(mi.lines[0].fine_wt)).quantize(D("0.001")), D("1.180"))
    check("500 g warns", bool(INV.shortfalls(s, "metal_issue", [{"location_id": raj.id, "metal_id": m590.id, "weight": D("500")}])), True)
    mr = inv(s, "metal_receipt", chand, [{"location_id": raj.id, "metal_id": m590.id, "weight": D("1.800"), "wastage_pct": D("2.5")}])
    check("wastage", mr.lines[0].wastage_wt, D("0.045"))
    mo = inv(s, "metal_opening", None, [{"location_id": prim.id, "metal_id": g24.id, "weight": D("5")}])
    check("metal opening needs no account", mo.account_id, None)
    si = inv(s, "stone_issue", chand, [{"location_id": prim.id, "stone_sku_id": polki.id, "size": polki.size or "", "pcs": 4, "weight": D("0.32")}])
    sr = inv(s, "stone_receipt", chand, [{"location_id": prim.id, "stone_sku_id": polki.id, "size": polki.size or "", "pcs": 1, "weight": D("0.08")}])
    os_ = [r for r in INV.stone_outstanding(s, chand.id)]
    check("stone O/S for CHAND", [(r["stone"], r["pcs"], r["weight"]) for r in os_], [("POLKI 12-14", 3, D("0.240"))])
    cb = INV.check_balance(s, chand.id, T)
    check("check bal per metal CHAND (2 - 1.8 - .045 + demo .59)", [r["balance"] for r in cb["per_metal"]], [D("0.745")])
    from diagold.ui.inventory import _lot_line
    check("read cert/lot finds the purchase", (_lot_line(s, "CERT-9") or {}).get("pcs"), 20)
    s.commit()

    print("\n== C. Order -> job -> route -> stones -> bag")
    sku = g(ProductSku, sku_code="NS-1430")
    o = Order(order_no=P.next_number(s, Order.order_no), order_date=T, account_id=kk.id,
              order_type="Customer", ref="E2E-1", terms="15 days", priority="High")
    s.add(o); s.flush()
    s.add(OrderLine(order_id=o.id, sno=1, product_sku_id=sku.id, c_ref="E2E-C", metal_id=m590.id, colour="Y", size="7", pcs=1))
    s.flush(); s.refresh(o)
    job = P.sync_jobs_for_order(s, o)[0]
    print("   job", job.job_no)
    P.map_job(s, job, "Default", T)
    check("route", P.route_string(s, job), "CAD CAM CS HM COL PP ST FP fs Meena Puwai")
    stissue = StoneIssue(vr_no=P.next_number(s, StoneIssue.vr_no), job_id=job.id, vr_date=T); s.add(stissue); s.flush()
    s.add_all([StoneIssueLine(issue_id=stissue.id, sno=1, location_id=prim.id, stone_sku_id=polki.id, size=polki.size or "", pcs=10, weight=D("0.800"), s_type="Polki"),
               StoneIssueLine(issue_id=stissue.id, sno=2, location_id=prim.id, stone_sku_id=em.id, size=em.size or "", pcs=5, weight=D("0.500"), s_type="CS")])
    s.flush(); s.refresh(stissue); P.apply_stone_issue(s, stissue)
    bag = {l.stone_sku_id: l for l in s.scalars(select(JobBagLine).where(JobBagLine.job_id == job.id))}
    P.set_bag_setting_type(s, bag[polki.id], g(SettingType, name="Polki").id)
    refused("return 50 from a bag of 10", lambda: P.bag_move(s, bag[polki.id], "rtn", 50))
    s.commit()

    print("\n== D. Manufacturing: issue / receive every step, edit + delete a voucher")
    W = {c: g(Account, code=c) for c in ("OFFICE", "FACTORY", "BUDDHAPOL", "RAKESHS", "AKSHAYJ", "JAGDISHPRA")}

    def st(kind, w, gross=None, net=None, allow=None, stones=None, **x):
        r = [r for r in P.pending_steps(s, kind) if r["_job_id"] == job.id][0]
        ln = {"job_id": job.id, "step_id": r["_step_id"], "pcs": 1, "gross": D(gross) if gross else None,
              "net": D(net) if net else None, "allow": D(allow) if allow is not None else None,
              "stones": stones or {}, "metal": [], **x}
        vr = P.post_multi_voucher(s, kind, w.id, [ln], vr_date=T, vr_time="10:00"); s.commit(); return vr
    st("issue", W["OFFICE"]); st("receive", W["OFFICE"]); st("issue", W["OFFICE"]); st("receive", W["OFFICE"])
    st("issue", chand, "13.500", "13.500", "0"); st("receive", chand, "13.200", "13.200")
    st("issue", rahul, "13.200", "13.200", "3.5", finding=D("0.050"), mould=D("0.100"))
    vr = st("receive", rahul, "13.100", "13.100")
    v = s.scalar(select(JobVoucher).where(JobVoucher.vr_no == vr))
    P.update_voucher(s, vr, {v.id: {"net_wt": "13.000", "gross_wt": "13.000"}}); s.commit()
    check("edit receive net", D(str(v.net_wt)), D("13.000"))
    vr_fac = st("issue", W["FACTORY"], "13.000", "13.000", "0")
    refused("delete receive while next step is issued", lambda: P.delete_job_voucher(s, vr))
    s.rollback()
    P.delete_job_voucher(s, vr_fac); s.commit()
    check("deleted issue -> pending again", job.id in [r["_job_id"] for r in P.pending_steps(s, "issue")], True)
    st("issue", W["FACTORY"], "13.000", "13.000", "0"); st("receive", W["FACTORY"], "13.000", "13.000")
    st("issue", W["BUDDHAPOL"], "13.000", "13.000", "0.35"); st("receive", W["BUDDHAPOL"], "12.900", "12.900")
    st("issue", W["RAKESHS"], "12.900", "12.900", "3", stones={bag[polki.id].id: 10, bag[em.id].id: 5})
    st("receive", W["RAKESHS"], "13.080", "12.850", stones={bag[polki.id].id: 2})
    st("issue", W["BUDDHAPOL"], "13.080", "12.850", "0.35"); st("receive", W["BUDDHAPOL"], "12.990", "12.760")
    st("issue", W["AKSHAYJ"], "12.990", "12.760", "0"); st("receive", W["AKSHAYJ"], "12.970", "12.740")
    st("issue", W["JAGDISHPRA"], "12.970", "12.740"); st("receive", W["JAGDISHPRA"], "12.950", "12.720")
    st("issue", W["JAGDISHPRA"], "12.950", "12.720"); vr_last = st("receive", W["JAGDISHPRA"], "12.930", "12.700")
    s.refresh(job); check("job complete", job.status, "complete")
    setting = [x for x in P.setting_labour_statement(s, date(2026, 9, 1), date(2026, 9, 30)) if x["job_no"] == job.job_no]
    check("setting labour 8 polki x 30", sum(x["amount"] for x in setting), D("240.00"))
    AT.add(s, "job_voucher", vr_last, str(Path(__file__))); s.commit()
    check("attach doc on receipt", len(AT.list_for(s, "job_voucher", vr_last)), 1)
    check("worker Mt Bal CHAND", P.worker_metal_balance(s, chand.id, T)[0], D("1.545"))

    print("\n== E. Job Costing")
    sh = JC.costing_sheet(s, job, T)
    check("costing: setting + total", (sh.setting, sh.total), (D("240.00"), D("131908.51")))
    check("costing tag / price per gm", (sh.price.tag_text, sh.price_per_gm), ("197", D("15.24")))
    reg = JC.register(s, *FY)
    check("job in costing register", job.job_no in [r["job_no"] for r in reg], True)
    wip = JC.register(s, *FY, wip=True)
    check("WIP costing lists demo job 28855", 28855 in [r["job_no"] for r in wip], True)

    print("\n== F. MFG transfer: split, location, edit, delete, re-transfer")
    job.pcs = 2; s.flush()
    t = MF.post_transfer(s, [{"job_id": job.id}], vr_date=T, location_id=prim.id, split_jobs=True); s.commit()
    items = MF.stock_for_transfer(s, t)
    check("split into 2 Stock Nos", len(items), 2)
    check("pieces add back to the price", sum(D(str(i.price)) for i in items), D(str(t.lines[0].price_per_pcs)))
    MF.update_transfer(s, t, [{"job_id": job.id, "margin_pct": 40}]); s.commit()
    check("edit keeps 2 pieces", len(MF.stock_for_transfer(s, t)), 2)
    MF.delete_transfer(s, t); s.commit(); s.refresh(job)
    check("transfer deleted -> job pending again", job.status, "complete")
    job.pcs = 1; s.flush()
    t = MF.post_transfer(s, [{"job_id": job.id}], vr_date=T); s.commit()
    piece = MF.stock_for_transfer(s, t)[0]
    check("transfer price / tag", (D(str(piece.price)), piece.tag_text), (D("197502.77"), "197"))
    check("ready stock lists it", piece.stock_no in [r["stock_no"] for r in MF.ready_stock(s, T)], True)
    check("item search finds it", [i.stock_no for i in MF.find_items(s, str(piece.stock_no))], [piece.stock_no])

    print("\n== G. Sale: approval -> sale from approval -> excel -> return; From Order")
    def line(item, rate=None):
        info = S.describe(s, item); return {**info, **S.value(info, T, s, metal_rate=rate)}
    refused("unknown barcode", lambda: S.find_item(s, "99999"))
    S.post_ready(s, "rs_approval", {"vr_date": T, "account_id": kk.id}, [line(piece)]); s.commit()
    check("on approval with KK", (piece.status, piece.holder_account_id), ("on_approval", kk.id))
    refused("sell approval piece to another party", lambda: S.post_ready(s, "rs_sale", {"vr_date": T, "account_id": mb.id}, [line(piece)]))
    s.rollback()
    ol = s.scalar(select(OrderLine).where(OrderLine.order_id == o.id))
    pend = S.pending_orders(s, kk.id)
    check("order E2E-1 pending 1", [r["bal_pcs"] for r in pend if r["ord_no"] == o.order_no], [1])
    sale = S.post_ready(s, "rs_sale", {"vr_date": T, "account_id": kk.id, "credit_days": 30},
                        [{**line(piece), "order_line_id": ol.id}]); s.commit()
    check("sold", piece.status, "sold")
    check("order shipped -> no longer pending", [r for r in S.pending_orders(s, kk.id) if r["ord_no"] == o.order_no], [])
    S.excel_invoice(s, sale, OUT + "/e2e_invoice.xlsx")
    check("approval analysis says Sold", [r["status"] for r in S.approval_analysis(s, *FY) if r["barcode"] == piece.stock_no], ["Sold"])
    S.post_ready(s, "rs_sale_return", {"vr_date": T, "account_id": kk.id}, [line(piece)]); s.commit()
    check("sale return -> in stock", piece.status, "in_stock")
    check("order pending again after return", [r["bal_pcs"] for r in S.pending_orders(s, kk.id) if r["ord_no"] == o.order_no], [1])

    print("\n== H. Repair")
    ro = Order(order_no=P.next_number(s, Order.order_no), order_date=T, account_id=mb.id, order_type="Customer", is_repair=True)
    s.add(ro); s.flush()
    S.attach_repair_pieces(s, ro, [piece.id], T); s.commit()
    rj = s.scalar(select(Job).where(Job.order_id == ro.id))
    check("repair job made, no stones carried", (rj is not None, s.scalars(select(JobBagLine).where(JobBagLine.job_id == rj.id)).all()), (True, []))
    rv = S.post_ready(s, "rs_repair_issue", {"vr_date": T, "account_id": mb.id}, [line(piece)]); s.commit()
    check("repair register: out", [r["status"] for r in S.repair_register(s, *FY)], ["Out for repair"])
    S.delete_ready(s, rv); s.commit()
    check("repair issue deleted -> in stock", piece.status, "in_stock")

    print("\n== I. Purchase ready items, return, opening")
    rp = S.post_ready(s, "rp_purchase", {"vr_date": T, "account_id": sup.id, "bill_no": "B-56", "bill_date": T},
                      [{"product_sku_id": sku.id, "location_id": prim.id, "metal_id": m590.id, "title": 590, "pcs": 1,
                        "gross_wt": "10", "net_wt": "8", "labour_rate": "1200", "metal_rate": "8680.67",
                        "metal_amount": "69445.36", "labour": "9600", "stone_amount": "0", "total": "79045.36",
                        "stones": []}]); s.commit()
    bought = s.get(StockItem, rp.lines[0].stock_item_id)
    check("bought piece in stock with barcode", (bought.status, bought.source), ("in_stock", "purchase"))
    refused("Delete History & Purchase on a bought piece", lambda: MF.delete_stock_item(s, bought))
    s.rollback()
    S.post_ready(s, "rp_return", {"vr_date": T, "account_id": sup.id}, [line(bought)]); s.commit()
    check("returned to supplier", bought.status, "returned")
    op = S.post_ready(s, "rp_opening", {"vr_date": T}, [{"product_sku_id": sku.id, "location_id": prim.id, "pcs": 1, "gross_wt": "5", "net_wt": "4", "total": "0"}]); s.commit()
    check("opening piece", s.get(StockItem, op.lines[0].stock_item_id).source, "opening")

    print("\n== J. Metal sale, stone sale / approval")
    ms = inv(s, "metal_sale", kk, [{"location_id": prim.id, "metal_id": g24.id, "colour": "Y", "weight": D("10"), "price": D("15050")}])
    check("metal sale 10 g @ 15,050", ms.lines[0].amount, D("150500.00"))
    inv(s, "stone_sale", kk, [{"location_id": prim.id, "stone_sku_id": polki.id, "size": polki.size or "", "pcs": 2, "weight": D("0.16")}])
    inv(s, "stone_approval", kk, [{"location_id": prim.id, "stone_sku_id": em.id, "size": em.size or "", "pcs": 4, "weight": D("0.4")}])
    inv(s, "stone_approval_return", kk, [{"location_id": prim.id, "stone_sku_id": em.id, "size": em.size or "", "pcs": 1, "weight": D("0.1")}])
    s.commit()
    check("stone approval balance 3", [r["bal_pcs"] for r in INV.stone_approval_analysis(s, *FY)], [3])

    print("\n== K. Stock transfer: melting + location transfer")
    before = P.stock_balance(s, prim.id, "stone", polki.id, polki.size or "")[0]
    stv = ST.post(s, {"vr_date": T, "contact_person": "Admin"}, ST.melting_lines(s, piece, T)); s.commit()
    check("melted", piece.status, "melted")
    check("8 polki back in Primary", P.stock_balance(s, prim.id, "stone", polki.id, polki.size or "")[0] - before, 8)
    tl = [{"pane": "stone", "location_id": prim.id, "stone_sku_id": polki.id, "size": polki.size or "", "out_pcs": 5, "out_wt": D("0.4"), "out_loss_pcs": 1, "out_loss_wt": D("0.08"), "price": D("8100"), "unit": "Cts"},
          {"pane": "stone", "location_id": raj.id, "stone_sku_id": polki.id, "size": polki.size or "", "in_pcs": 4, "in_wt": D("0.32"), "price": D("8100"), "unit": "Cts"}]
    check("transfer balances", ST.imbalance(tl), [])
    ST.post(s, {"vr_date": T}, tl); s.commit()
    check("transfer loss in Stone Loss Register", [r["process"] for r in RG.stone_loss_register(s, *FY) if r["process"] == "TR"], ["TR"])
    ST.delete(s, stv); s.commit()
    check("melting undone", piece.status, "in_stock")

    print("\n== L. Every register / report runs")
    for name, fn in (("metal loss", RG.metal_loss_register), ("stone loss", RG.stone_loss_register),
                     ("dust", RG.dust_register), ("wip", RG.wip_register),
                     ("wip summary", RG.wip_process_summary), ("wip stone", RG.wip_stone)):
        rows = fn(s, *FY); print(f"   {name}: {len(rows)} rows")
    check("metal analysis RAJESH 14KT 590 closing",
          {(r["location"], r["metal"]): r for r in INV.metal_analysis(s, *FY)}[("RAJESH JI", "14KT 590")]["closing"],
          D("249.175"))
    mb = {(r["worker"], r["metal"]): r for r in P.party_metal_balance(s, *FY)}
    kr = mb[(kk.name, g24.name)]
    check("Worker Balance (Metal): client owes the 10 g metal sold",
          (kr["group"], kr["in_wt"], kr["bal_wt"]), ("Client", D("10.000"), D("10.000")))
    cm = {r["client"]: r for r in P.client_metal_os(s, FY[1])}
    check("Client Metal O/S: KK fine 10 + money, supplier owed, no nominal ledgers",
          (cm[kk.name]["fine_os"], cm[kk.name]["amt_os"] > 0, cm["TEST SUPPLIER"]["amt_os"],
           "Sales A/c" in cm or "Cash in Hand" in cm),
          (D("10.000"), True, D("-448993.50"), False))
    from diagold.services import price_charts as PC
    from diagold.db.models import PriceChart
    mannu = s.scalar(select(PriceChart).where(PriceChart.name == "MANNU BHAI"))
    pc_item = s.scalars(select(StockItem).where(StockItem.status == "in_stock")).first()
    pc_info = S.describe(s, pc_item)
    check("price chart: no rule -> MANNU BHAI 1,175 / gm",
          S.value(PC.apply(s, mannu, pc_info), T, s)["labour_rate"], D("1175"))
    PC.save_rules(s, mannu, "labour", [{"family": PC.piece_keys(s, pc_info)["family"],
                                        "from_gwt": D(10), "to_gwt": D(20), "sale_price": D(900)}])
    v = S.value(PC.apply(s, mannu, pc_info), T, s)
    check("price chart: family rule in the 10-20 g slab wins", (v["labour_rate"], v["labour"]),
          (D("900"), (D("900") * D(str(pc_info["net_wt"]))).quantize(D("0.01"))))
    s.rollback()
    from diagold.services import stone_reports as SRP
    from diagold.services import admin as ADM
    ojob = s.scalar(select(Job).where(Job.status.in_(("mapped", "in_progress"))))
    refused("a correction without a reason", lambda: ADM.update_job(s, ojob, "c_ref", "X", ""))
    pcs0 = ojob.pcs
    ADM.add_pcs(s, ojob, 1, "client added one")
    check("Add Pcs in Job Card: +1, logged", (ojob.pcs, ADM.audit_rows(s, *FY)[0]["kind"]),
          (pcs0 + 1, "job_add_pcs"))
    s.rollback()
    from diagold.services import sales_reports as SRR
    sreg = SRR.sales_register(s, *FY)
    check("Sales Register: the sold piece is marked RETURN Y", [(r["vrtype"], r["ret"]) for r in sreg],
          [("RS", "Y")])
    check("Sales Dashboard: sale less its return nets to 0 by client",
          dict(SRR.cube(s, *FY, "Client", "Value")).get(kk.name), D("0.00"))
    check("Today's Daybook lists the sale with its stone lines",
          any(r["vrtype"] == "RS" for r in SRR.todays_daybook(s, T, T))
          and any(r.get("_sub") for r in SRR.todays_daybook(s, T, T)), True)
    ms = {(r["location"], r["metal"], r["where"]): r["net_wt"] for r in SRP.metal_summary(s, FY[1])}
    check("Metal Summary INV = Metal Analysis closing (RAJESH JI 14KT 590)",
          ms.get(("RAJESH JI", "14KT 590", "INV")), D("249.175"))
    lsb = {r["line"]: r for r in SRP.location_stone_balance(s, prim.id, *FY)}
    g = "pol"
    v = lambda line: lsb[line][f"{g}_wt"] or D(0)
    check("Location Stone Balance: closing = opening + inward - outward; total = inv + JC + WIP",
          (v("Closing Stock") == v("Opening Stock") + v("Inward Total") - v("Outward Total"),
           v("Total (location + in work)") == v("Balance Details: Inventory") + v("Job Card") + v("WIP")),
          (True, True))
    wsb = {(r["worker"], r["ssku"]): r for r in P.worker_stone_balance(s, FY[1])}
    check("Worker Balance (Stone): client KK holds the 3 emeralds on approval",
          wsb.get((kk.name, "EMERALD PEAR"), {}).get("pcs"), 3)
    from diagold.services import stock_tools as STK
    in_stock = [str(n) for n in s.scalars(select(StockItem.stock_no).where(StockItem.status == "in_stock"))]
    rc = STK.new_recon(s, T)
    STK.add_scans(s, rc, in_stock[1:] + ["999999"])
    res = STK.reconcile(s, rc)
    check("reconciliation: one piece not scanned -> exactly 1 missing, 1 unknown",
          (len(res["ok"]), len(res["missing"]), len(res["unknown"])), (len(in_stock) - 1, 1, 1))
    s.rollback()
    led = INV.account_ledger(s, *FY)
    test_sup = [r for r in led if r["ledger"] == "TEST SUPPLIER"]
    check("TEST SUPPLIER closing (stone 14,960 + metal 4,34,033.50 + ready 79,045.36 - return)",
          (test_sup[-1]["balance"], test_sup[-1]["drcr"]), (D("448993.50"), "Cr"))

    print("\n== M. Invariants")
    check("accounts Dr = Cr", ledger_balanced(s), True)
    check("stock balances = sum of movements", stock_consistent(s), [])

print(f"\nPASSED {passes}  FAILED {len(fails)}: {fails or 'none'}")
sys.exit(1 if fails else 0)
