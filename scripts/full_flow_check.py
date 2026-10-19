"""One full business flow on the app's own database, every step checked, and
the data LEFT IN PLACE so it can be opened in the app and compared.

    python scripts/full_flow_check.py              # the app's data (backed up first)
    DIAGOLD_DATA_DIR=/some/copy python scripts/full_flow_check.py

Masters -> inventory (purchase, issue + EDIT, receipt) -> order with shipping
details -> Job Card -> Job Mapping -> stones on the job -> every process
(CASTING received without weight, a loss, the next issue taking the last
weight, setting with returns / breakage, an EDIT) -> job costing -> MFG
transfer -> ready stock -> approval + return -> sale against the order ->
dispatch + WhatsApp (sandbox) -> receipt -> Ready Items purchase (net from the
stones) -> stock melting -> reports and invariants.

Everything it makes carries ref / remark "FF-<date>" so it is easy to find.
A report of every record number and figure is written next to the database
(full_flow_report.md) and printed.
"""
from __future__ import annotations

import os
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from diagold.config import DB_PATH, DATA_DIR  # noqa: E402

TODAY = date.today()
TAG = f"FF-{TODAY:%d%b}".upper()
fails: list[str] = []
passes = 0
report: list[str] = []


def check(label, got, want):
    global passes
    if got == want:
        passes += 1
        print("  PASS", label, got)
    else:
        fails.append(label)
        print("  FAIL", label, got, f"(want {want})")


def note(section: str, *rows: str) -> None:
    report.append(f"\n## {section}\n")
    report.extend(f"- {r}" for r in rows)


def backup() -> Path | None:
    if not DB_PATH.exists():
        return None
    dst = DB_PATH.with_name(f"{DB_PATH.name}.backup-{datetime.now():%Y%m%d-%H%M%S}-pre-full-flow")
    shutil.copy2(DB_PATH, dst)
    return dst


def main() -> int:
    bk = backup()
    from diagold.db.session import SessionLocal, init_db
    init_db()
    from diagold.db.models import (Account, AccountEntry, InvVoucherLine, Job, JobBagLine,
                                   JobVoucher, Location, MaterialStock, Metal, Order,
                                   OrderLine, ProductSku, StockItem, StockMovement, StoneIssue,
                                   StoneIssueLine, StoneSku)
    from diagold.db.models import InvVoucher
    from diagold.services import (accounts as ACC, inventory as INV, job_costing as JC,
                                  manufacturing as MF, order_shipping as OSH, production as P,
                                  sales as S, settings as SET, stock_tools as STK,
                                  stock_transfer as ST, whatsapp as WA)

    print(f"Database: {DB_PATH}\nBackup:   {bk}\nTag:      {TAG}")
    from diagold.services import rates as RT
    from diagold.services.demo_data import FINE_RATE, load_demo
    with SessionLocal() as s:
        # The demo data, as `python main.py --demo` loads it (once only).
        print(load_demo(s))
        s.commit()
    with SessionLocal() as s:
        g = lambda m, **w: s.scalar(select(m).filter_by(**w))  # noqa: E731
        # Masters ▸ Daily Metal Rate for today (24K fine 14,713 / g, the demo's rate).
        for name in ("14KT 590", "24KT Gold"):
            mt = g(Metal, name=name)
            RT.set_rate(s, mt.id, TODAY, FINE_RATE, pure_rate_per_gram=FINE_RATE, remark=TAG)
        s.commit()

        # -- A. Masters ------------------------------------------------------
        print("\n== A. Masters")
        kk = g(Account, code="KK")
        chand = g(Account, code="CHANDKUMARHAZRA")
        W = {c: g(Account, code=c) for c in ("OFFICE", "FACTORY", "BUDDHAPOL", "RAKESHS",
                                             "AKSHAYJ", "JAGDISHPRA")}
        prim = g(Location, name="Primary")
        m590 = g(Metal, name="14KT 590")
        polki = g(StoneSku, sku_code="POLKI 12-14")
        em = g(StoneSku, sku_code="EMERALD PEAR 3*4")
        ns, bang = g(ProductSku, sku_code="NS-1430"), g(ProductSku, sku_code="BANG-32")
        check("masters present", all([kk, chand, prim, m590, polki, em, ns, bang, *W.values()]), True)
        sup = g(Account, code="FFSUP") or Account(code="FFSUP", name="FULL FLOW SUPPLIER",
                                                  account_type="Accounts",
                                                  group_name="Accounts Payable")
        dia = g(StoneSku, sku_code="DIA RD MIX") or StoneSku(
            sku_code="DIA RD MIX", stone="DIA", stone_type="DIA", per="Cts",
            cost_price=D("13500"), sale_price=D("13500"))
        s.add_all([sup, dia])
        kk.whatsapp_no, kk.whatsapp_opt_in = kk.whatsapp_no or "98765 43210", True
        SET.set_setting(s, "whatsapp.enabled", "1")
        s.commit()
        rate = P.metal_price(s, m590.id, TODAY)
        print("   14KT 590 rate today", rate)
        note("A. Masters", f"Daily Metal Rate {TODAY:%d-%m-%Y}: 24K fine 14,713 / g on 14KT 590 and "
             "24KT Gold", f"Supplier **{sup.name}** (code FFSUP)",
             f"Stone SKU **DIA RD MIX** (diamond, 13,500 / ct)",
             f"KK JEWELS WhatsApp {kk.whatsapp_no}, opted in; Tools ▸ Option WhatsApp on (sandbox)",
             f"14KT 590 metal rate used: **{rate:,.2f} / g**")

        # -- B. Inventory ------------------------------------------------------
        print("\n== B. Inventory")

        def inv(vt, acct, lines, **h):
            v = InvVoucher(vr_type=vt, vr_no=INV.next_vr_no(s, vt), vr_date=TODAY,
                           account_id=acct.id if acct else None, ref_no=TAG, **h)
            s.add(v)
            s.flush()
            for n, r in enumerate(lines, 1):
                INV.fill_line(s, vt, r)
                s.add(InvVoucherLine(voucher_id=v.id, sno=n, **r))
            s.flush()
            s.refresh(v)
            INV.repost_voucher(s, v)
            s.commit()
            return v

        def bal(material, ref, size=""):
            return P.stock_balance(s, prim.id, material, ref, size)

        sp = inv("stone_purchase", sup, [
            {"location_id": prim.id, "stone_sku_id": polki.id, "size": polki.size or "", "pcs": 40,
             "weight": D("3.200"), "price": D("8100")},
            {"location_id": prim.id, "stone_sku_id": dia.id, "size": "", "pcs": 500,
             "weight": D("7.000"), "price": D("13500")},
            {"location_id": prim.id, "stone_sku_id": em.id, "size": em.size or "", "pcs": 20,
             "weight": D("2.000"), "price": D("2000")}])
        check("stone purchase amounts", [D(str(l.amount)) for l in sp.lines],
              [D("25920.00"), D("94500.00"), D("4000.00")])
        mp = inv("metal_purchase", sup, [{"location_id": prim.id, "metal_id": m590.id,
                                          "colour": "Y", "weight": D("100"), "price": rate}])
        before = bal("metal", m590.id)[1]
        mi = inv("metal_issue", chand, [{"location_id": prim.id, "metal_id": m590.id,
                                         "weight": D("5.000")}])
        after5 = bal("metal", m590.id)[1]
        check("metal issue 5 g takes 5 g from Primary", D(str(before - after5)).quantize(D("0.001")),
              D("5.000"))
        # 19 Oct item 5: EDIT the issue to 4 g
        mi.lines[0].weight = D("4.000")
        INV.fill_line(s, "metal_issue", {"metal_id": m590.id, "weight": D("4")})
        mi.lines[0].fine_wt = INV.line_fine(s, m590.id, D("4"))
        s.flush()
        INV.repost_voucher(s, mi)
        s.commit()
        after4 = bal("metal", m590.id)[1]
        check("EDIT issue 5 -> 4 g: Primary gets 1 g back", D(str(after4 - after5)).quantize(D("0.001")),
              D("1.000"))
        mr = inv("metal_receipt", chand, [{"location_id": prim.id, "metal_id": m590.id,
                                           "weight": D("3.800"), "wastage_pct": D("2.5")}])
        check("receipt wastage 2.5 % of 3.800", D(str(mr.lines[0].wastage_wt)), D("0.095"))
        note("B. Inventory (Inventory ▸ Metal / Stone)",
             f"Stone Purchase Vr **{sp.vr_no}** from FULL FLOW SUPPLIER: POLKI 12-14 40 pcs 3.200 ct "
             "@8,100 = 25,920 · DIA RD MIX 500 pcs 7.000 ct @13,500 = 94,500 · EMERALD PEAR 3*4 "
             "20 pcs 2.000 ct @2,000 = 4,000",
             f"Metal Purchase Vr **{mp.vr_no}**: 14KT 590 100 g into Primary",
             f"Metal Issue Outside / Worker Vr **{mi.vr_no}** to CHAND KUMAR HAZRA: saved at 5 g, then "
             "**edited to 4.000 g** — Primary went back up by 1 g (19 Oct item 5)",
             f"Metal Receipt Vr **{mr.vr_no}** from CHAND: 3.800 g, wastage 2.5 % = 0.095")

        # -- C. Order ------------------------------------------------------------
        print("\n== C. Order with shipping details")
        o = Order(order_no=P.next_number(s, Order.order_no), order_date=TODAY, account_id=kk.id,
                  order_type="Customer", ref=TAG, terms="30 days", priority="High",
                  delivery_date=TODAY, tracking_no="TRK-" + TAG)
        s.add(o)
        s.flush()
        s.add_all([OrderLine(order_id=o.id, sno=1, product_sku_id=ns.id, c_ref="FF-NS",
                             metal_id=m590.id, colour="Y", size="7", pcs=1),
                   OrderLine(order_id=o.id, sno=2, product_sku_id=bang.id, c_ref="FF-BANG",
                             metal_id=m590.id, colour="Y", size="2.4", pcs=2)])
        s.flush()
        s.refresh(o)
        P.order_saved(s, o)
        OSH.save(s, o, {"ship_via": "BlueDart", "destination": "Jaipur",
                        "payment_terms": "30 days", **OSH.account_details(s, o)})
        s.commit()
        check("order save makes no job yet (Job Card makes them)",
              s.scalars(select(Job).where(Job.order_id == o.id)).all(), [])
        pend = [r for r in P.pending_for_explode(s) if r["_order_id"] == o.id]
        check("Pending Orders For Explode: 2 lines (1 + 2 pcs)", [r["pending"] for r in pend], [1, 2])

        # -- D. Job Card -----------------------------------------------------------
        print("\n== D. Job Card")
        jc_vr, made = P.explode_orders(s, [
            {"order_id": o.id, "sno": 1, "prod_pcs": 1, "job_pcs": 1, "due": TODAY},
            {"order_id": o.id, "sno": 2, "prod_pcs": 2, "job_pcs": 1, "due": TODAY}], vr_date=TODAY)
        s.commit()
        check("Job Card makes 3 jobs (BANG-32 2 pcs at 1 per job)", len(made), 3)
        j1, j2, j3 = [s.scalar(select(Job).where(Job.job_no == n)) for n in made]
        note("C. Order ▸ Order", f"Order **{o.order_no}** KK JEWELS, Ref {TAG}, Terms 30 days, "
             f"Tracking No TRK-{TAG}; Shipping Details: BlueDart → Jaipur, buyer/consignee from KK JEWELS",
             "Line 1 NS-1430 14KT 590 Y size 7 × 1 · Line 2 BANG-32 size 2.4 × 2",
             "On save: **no job** — the lines wait in Job Card ▸ Show Orders")
        note("D. Production - Planning ▸ Job Card",
             f"Job Card Vr **{jc_vr}** → jobs **{made[0]}** (NS-1430), **{made[1]}** and **{made[2]}** "
             "(BANG-32, 1 pc each)", "Edit Job# with any of them shows this voucher")

        # -- E. Job Mapping + stones -------------------------------------------------
        print("\n== E. Job Mapping and stones on the job")
        for j in (j1, j2, j3):
            P.map_job(s, j, "Default", TODAY)
        s.commit()
        check("route", P.route_string(s, j1), "CAD CAM CS HM COL PP ST FP fs Meena Puwai")
        si = StoneIssue(vr_no=P.next_number(s, StoneIssue.vr_no), job_id=j1.id, vr_date=TODAY)
        s.add(si)
        s.flush()
        for n, (sku, size, pcs, wt, typ) in enumerate([
                (dia, "", 120, "1.800", "DIA"), (polki, polki.size or "", 12, "0.960", "POL"),
                (em, em.size or "", 6, "0.600", "CS")], 1):
            s.add(StoneIssueLine(issue_id=si.id, sno=n, location_id=prim.id, stone_sku_id=sku.id,
                                 size=size, pcs=pcs, weight=D(wt), s_type=typ))
        s.flush()
        s.refresh(si)
        P.apply_stone_issue(s, si)
        s.commit()
        bag = {l.stone_sku_id: l for l in s.scalars(select(JobBagLine).where(
            JobBagLine.job_id == j1.id, JobBagLine.rcvd_pcs > 0))} if hasattr(JobBagLine, "rcvd_pcs") \
            else {l.stone_sku_id: l for l in s.scalars(select(JobBagLine).where(JobBagLine.job_id == j1.id))}
        rows = P.bag_ledger(s, j1)
        check("Job Card Bag received 138 pcs / 3.360 ct",
              (sum(r["rcvd"][0] for r in rows), sum(r["rcvd"][1] for r in rows)), (138, D("3.360")))
        note("E. Job Mapping + Inventory ▸ Stone ▸ Issue On Job Card",
             "All three jobs mapped to **Default**: CAD CAM CS HM COL PP ST FP fs Meena Puwai",
             f"Stone Issue on Job-Card Vr **{si.vr_no}** for job {j1.job_no}: DIA RD MIX 120 / 1.800 ct, "
             "POLKI 12-14 12 / 0.960, EMERALD PEAR 3*4 6 / 0.600 — Job Card Bag 138 pcs / 3.360 ct")

        # -- F. Manufacturing, job 1 ----------------------------------------------------
        print("\n== F. Manufacturing — job", j1.job_no)
        log: list[str] = []

        def st(job, kind, w, gross=None, net=None, stones=None, **x):
            r = [r for r in P.pending_steps(s, kind) if r["_job_id"] == job.id][0]
            ln = {"job_id": job.id, "step_id": r["_step_id"], "pcs": 1,
                  "gross": D(gross) if gross else None, "net": D(net) if net else None,
                  "stones": stones or {}, "metal": [], **x}
            vr = P.post_multi_voucher(s, kind, w.id, [ln], vr_date=TODAY,
                                      vr_time=datetime.now().strftime("%H:%M"), user_id=None)
            s.commit()
            v = s.scalar(select(JobVoucher).where(JobVoucher.vr_no == vr,
                                                  JobVoucher.job_id == job.id))
            log.append(f"{r['process']} {kind} Vr {vr} {w.name}"
                       + (f" G {v.gross_wt} N {v.net_wt}" if v.net_wt is not None
                          else " (no weight)"))
            return vr

        for _ in range(2):                       # CAD, CAMMING: no weights
            st(j1, "issue", W["OFFICE"])
            st(j1, "receive", W["OFFICE"])
        st(j1, "issue", W["OFFICE"], "22.000", "22.000")      # CASTING weighed out
        st(j1, "receive", W["OFFICE"])                         # ... back with NO weight (item 1)
        check("CASTING received without a weight", P.current_step(s, j1)[1], None)
        check("HandMade goes out at the casting weight", P.last_weights(s, j1),
              (D("22.000"), D("22.000")))
        st(j1, "issue", chand, "22.000", "22.000")
        st(j1, "receive", chand, "21.500", "21.500")           # ghat 0.500
        check("after the loss, COLOUR goes out at 21.500 (item 2)", P.last_weights(s, j1),
              (D("21.500"), D("21.500")))
        st(j1, "issue", W["FACTORY"], "21.500", "21.500")
        st(j1, "receive", W["FACTORY"], "21.500", "21.500")
        st(j1, "issue", W["BUDDHAPOL"], "21.500", "21.500")
        st(j1, "receive", W["BUDDHAPOL"], "21.200", "21.200")
        out = {bag[dia.id].id: {"pcs": 120, "wt": D("1.800")},
               bag[polki.id].id: {"pcs": 12, "wt": D("0.960")},
               bag[em.id].id: {"pcs": 6, "wt": D("0.600")}}
        st(j1, "issue", W["RAKESHS"], "21.200", "21.200", stones=out)
        back = {bag[polki.id].id: {"pcs": 2, "wt": D("0.160"), "break_pcs": 0, "break_wt": D(0)},
                bag[dia.id].id: {"pcs": 0, "wt": D(0), "break_pcs": 1, "break_wt": D("0.015")}}
        vr_set = st(j1, "receive", W["RAKESHS"], "21.800", stones=back)
        set_rcv = s.scalar(select(JobVoucher).where(JobVoucher.vr_no == vr_set, JobVoucher.job_id == j1.id))
        in_piece = D("3.360") - D("0.160") - D("0.015")
        check("Setting N-Wt = 21.800 − stones in piece × 0.2",
              D(str(set_rcv.net_wt)), (D("21.800") - in_piece * D("0.2")).quantize(D("0.001")))
        # 19 Oct item 1: EDIT that entry (gross typed wrong: 21.850)
        P.update_voucher(s, vr_set, {set_rcv.id: {"gross_wt": "21.850",
                                                  "net_wt": str(D("21.850") - in_piece * D("0.2"))}})
        s.commit()
        s.refresh(set_rcv)
        check("EDIT setting receipt gross 21.800 -> 21.850", D(str(set_rcv.gross_wt)), D("21.850"))
        g1, n1 = P.last_weights(s, j1)
        for w in (W["BUDDHAPOL"], W["AKSHAYJ"], W["JAGDISHPRA"], W["JAGDISHPRA"]):
            st(j1, "issue", w, str(g1), str(n1))
            g1, n1 = g1 - D("0.010"), n1 - D("0.010")
            st(j1, "receive", w, str(g1), str(n1))
        s.refresh(j1)
        check("job 1 complete (pending MFG transfer)", j1.status, "complete")
        note(f"F. Job History — job {j1.job_no} (F11)", *log,
             "**Check:** CASTING row has an issue weight 22.000 and a blank receipt (item 1); "
             "HandMade 22.000 → 21.500 (loss 0.500 = 2.27 %); COLOUR issue 21.500 (item 2); "
             f"Setting receipt Vr {vr_set} edited to G 21.850 (item 1 'edit')")

        # -- G. Jobs 2 + 3 together, merged ------------------------------------------
        print("\n== G. Jobs 2 + 3 on one voucher per step, merged")
        merged = None
        for i, w in enumerate((W["OFFICE"], W["OFFICE"], W["OFFICE"], chand, W["FACTORY"],
                               W["BUDDHAPOL"], W["RAKESHS"], W["BUDDHAPOL"], W["AKSHAYJ"],
                               W["JAGDISHPRA"], W["JAGDISHPRA"])):
            weigh = i >= 3
            lines = []
            for j in (j2, j3):
                r = [r for r in P.pending_steps(s, "issue") if r["_job_id"] == j.id][0]
                gw = P.last_weights(s, j)[0] or D("12.000")
                lines.append({"job_id": j.id, "step_id": r["_step_id"], "pcs": 1,
                              "gross": gw if weigh else None, "net": gw if weigh else None})
            vr = P.post_multi_voucher(s, "issue", w.id, lines, vr_date=TODAY)
            if i == 0:
                merged = P.merge_jobs(s, [j2.id, j3.id], vr)
            back = []
            for ln in lines:
                r = [r for r in P.pending_steps(s, "receive") if r["_job_id"] == ln["job_id"]][0]
                gw = (ln["gross"] - D("0.050")) if weigh else None
                back.append({**ln, "step_id": r["_step_id"], "gross": gw, "net": gw})
            P.post_multi_voucher(s, "receive", w.id, back, vr_date=TODAY)
            s.commit()
        s.refresh(j2)
        s.refresh(j3)
        check("jobs 2 + 3 complete", (j2.status, j3.status), ("complete", "complete"))
        check("merged as one group", (j2.merge_group, j3.merge_group), (merged, merged))
        note("G. Jobs 2 + 3 (BANG-32)",
             f"Every step on ONE voucher for both jobs; merged as **{merged}** on the CAD issue",
             "HandMade 12.000 each, 0.050 loss per step after it")

        # -- H. Job costing + MFG transfer ----------------------------------------------
        print("\n== H. Job costing and MFG transfer")
        sheet = JC.costing_sheet(s, j1, TODAY)
        t = MF.post_transfer(s, [{"job_id": j.id, "margin_pct": D("50")} for j in (j1, j2, j3)],
                             vr_date=TODAY, location_id=prim.id, ref_no=TAG)
        s.commit()
        items = MF.stock_for_transfer(s, t)
        check("3 pieces into ready stock", len(items), 3)
        p1 = next(i for i in items if i.job_id == j1.id)
        p2, p3 = [i for i in items if i.job_id in (j2.id, j3.id)]
        ln1 = next(l for l in t.lines if l.job_id == j1.id)
        check("job 1 tag = price ÷ 1,000", ln1.tag_text,
              str(int(D(str(ln1.price_per_pcs)) / 1000)))
        note("H. Job Costing + Manufacturing ▸ MFG Transfer",
             f"Job Costing job {j1.job_no}: metal {sheet.price.metal_amount:,.2f} + stones "
             f"{sheet.price.stone_amount:,.2f} + labour {sheet.price.labour:,.2f} = total "
             f"{sheet.price.total:,.2f}",
             f"MFG Transfer Vr **{t.vr_no}** (margin 50 %): stock **{p1.stock_no}** (NS-1430, job "
             f"{j1.job_no}) G {ln1.gross_wt} N {ln1.net_wt} total {D(str(ln1.total)):,.2f} price "
             f"{D(str(ln1.price_per_pcs)):,.2f} TAG **{ln1.tag_text}**; stock **{p2.stock_no}**, "
             f"**{p3.stock_no}** (BANG-32)")

        # -- I. Ready Closing Stock ------------------------------------------------------
        print("\n== I. Ready Closing Stock — DIA / POL / CS WT")
        rows = {r["stock_no"]: r for r in STK.ready_closing_stock(s, TODAY)}
        r1 = rows.get(p1.stock_no, {})
        check("DIA WT of the NS-1430 piece = 1.800 − 0.015 broken", r1.get("dia_wt"), D("1.785"))
        check("POL WT = 0.960 − 0.160 returned", r1.get("polki_wt"), D("0.800"))
        check("CS WT = 0.600", r1.get("cs_wt"), D("0.600"))
        note("I. Reports ▸ Ready Closing Stock", f"Stock {p1.stock_no}: **DIA WT 1.785 · POL WT 0.800 · "
             "CS WT 0.600** (item 2); amounts on Ctrl+F1")

        # -- J. Approval, sale, dispatch, receipt -------------------------------------
        print("\n== J. Approval, sale against the order, dispatch, receipt")

        def line(item):
            info = S.describe(s, item)
            return {**info, **S.value(info, TODAY, s)}
        ap = S.post_ready(s, "rs_approval", {"vr_date": TODAY, "account_id": kk.id, "ref_no": TAG},
                          [line(p2)])
        s.commit()
        check("BANG-32 on approval with KK", p2.status, "on_approval")
        ar = S.post_ready(s, "rs_approval_return", {"vr_date": TODAY, "account_id": kk.id},
                          [line(p2)])
        s.commit()
        s.refresh(p2)
        check("approval returned", p2.status, "in_stock")
        ol1 = s.scalar(select(OrderLine).where(OrderLine.order_id == o.id, OrderLine.sno == 1))
        sale = S.post_ready(s, "rs_sale", {"vr_date": TODAY, "account_id": kk.id, "credit_days": 30,
                                           "salesperson": "Admin", "ref_no": TAG},
                            [{**line(p1), "order_line_id": ol1.id}, line(p3)])
        s.commit()
        check("sold", (p1.status, p3.status), ("sold", "sold"))
        msg = S.dispatch(s, sale, ship_by="Courier", ship_no="BD-" + TAG, ship_date=TODAY,
                         expected_date=TODAY)
        s.commit()
        check("WhatsApp to KK logged (sandbox)", getattr(msg, "status", None) in ("sandbox", "sent", "logged"),
              True)
        total = D(str(sale.total)) if hasattr(sale, "total") else sum(
            (D(str(l.total)) for l in sale.lines), D(0))
        rc = ACC.post_voucher(s, "receipt", {"vr_date": TODAY, "account_id": kk.id, "mode": "Cash",
                                              "amount": D("100000"), "narration": TAG})
        s.commit()
        note("J. Sale ▸ Ready Stock",
             f"Approval Vr **{ap.vr_no}** BANG-32 stock {p2.stock_no} to KK → Approval Return Vr "
             f"**{ar.vr_no}** (back in stock)",
             f"Sale Vr **{sale.vr_no}** to KK JEWELS: stock {p1.stock_no} (against order {o.order_no} "
             f"line 1) + stock {p3.stock_no}; total {total:,.2f}",
             f"Dispatched by Courier, tracking BD-{TAG}; WhatsApp to KK in Tools ▸ WhatsApp Log "
             f"(status {getattr(msg, 'status', '?')})",
             f"Receipt Vr **{rc.vr_no}** from KK: cash 1,00,000")

        # -- K. Ready Items purchase (net from stones) + stock melting ----------------
        print("\n== K. Ready Items purchase, then melt it")
        stones = [{"label": polki.sku_code, "s_type": "POL", "weight": "3.5", "pcs": 20,
                   "price": "8100", "unit": "Cts"},
                  {"label": dia.sku_code, "s_type": "DIA", "weight": "3.0", "pcs": 200,
                   "price": "13500", "unit": "Cts"}]
        net = S.net_from_gross(D("25"), stones)
        check("N-Wt = 25.000 − 6.5 ct × 0.2 (item 3)", net, D("23.700"))
        rp = S.post_ready(s, "rp_purchase", {"vr_date": TODAY, "account_id": sup.id,
                                             "bill_no": TAG, "bill_date": TODAY},
                          [{"product_sku_id": bang.id, "location_id": prim.id, "metal_id": m590.id,
                            "title": 590, "pcs": 1, "gross_wt": "25", "net_wt": str(net),
                            "fine_wt": str((net * 590 / 1000).quantize(D("0.001"))),
                            "metal_rate": str(rate), "metal_amount": str((net * rate).quantize(D("0.01"))),
                            "stone_amount": "68850", "labour": "0",
                            "total": str((net * rate).quantize(D("0.01")) + D("68850")),
                            "stones": stones}])
        s.commit()
        bought = s.get(StockItem, rp.lines[0].stock_item_id)
        check("bought piece in stock, N-Wt 23.700", (bought.status, D(str(bought.net_wt))),
              ("in_stock", D("23.700")))
        pol_before = P.stock_balance(s, prim.id, "stone", polki.id, polki.size or "")
        mlines = ST.melting_lines(s, bought, TODAY)
        check("melting gives piece + metal + 2 stones", sorted(l["pane"] for l in mlines),
              ["metal", "ready_out", "stone", "stone"])
        tv = ST.post(s, {"vr_date": TODAY, "contact_person": "Admin", "ref_no": TAG}, mlines)
        s.commit()
        s.refresh(bought)
        pol_after = P.stock_balance(s, prim.id, "stone", polki.id, polki.size or "")
        check("melted piece out of stock", bought.status != "in_stock", True)
        check("its polki back in Primary (+20 / 3.5 ct)",
              (pol_after[0] - pol_before[0], D(str(pol_after[1] - pol_before[1])).quantize(D("0.001"))),
              (20, D("3.500")))
        note("K. Purchase ▸ Ready Items + Inventory ▸ Stock Transfer",
             f"Ready Items Purchase Vr **{rp.vr_no}** from FULL FLOW SUPPLIER: BANG-32 G 25.000, stones "
             f"6.5 ct → **N-Wt 23.700** (item 3); stock {bought.stock_no}",
             f"Stock Transfer Vr **{tv.vr_no}** — Stock Melting of {bought.stock_no}: piece out, 23.700 g "
             "14KT 590 and the stones back into Primary (item 4: on screen, removing the piece removes "
             "all three panes' lines)")

        # -- L. Reports and invariants ------------------------------------------------------
        print("\n== L. Reports and invariants")
        st_rows = {r["ord_no"]: r for r in OSH.order_list(s, TODAY, TODAY)}
        check("Order List: the order is Ready (all jobs in stock)", st_rows[o.order_no]["status"], "Ready")
        dr = sum((D(str(e.debit or 0)) for e in s.scalars(select(AccountEntry))), D(0))
        cr = sum((D(str(e.credit or 0)) for e in s.scalars(select(AccountEntry))), D(0))
        check("accounts Dr = Cr", dr == cr, True)
        acc = defaultdict(lambda: [0, D(0)])
        for m in s.scalars(select(StockMovement).where(StockMovement.kind != "breakage")):
            k = (m.location_id, m.material_class, m.ref_id, m.size or "", m.ref_text or "")
            acc[k][0] += int(m.pcs)
            acc[k][1] += D(str(m.weight))
        bad = [r for r in s.scalars(select(MaterialStock))
               if (int(r.pcs), D(str(r.weight)).quantize(D("0.0001"))) !=
               (acc[(r.location_id, r.material_class, r.ref_id, r.size or "", r.ref_text or "")][0],
                acc[(r.location_id, r.material_class, r.ref_id, r.size or "", r.ref_text or "")][1]
                .quantize(D("0.0001")))]
        check("stock = sum of movements (every location)", len(bad), 0)
        note("L. Where to compare",
             f"Order ▸ Order List / Status ▸ Ready: order {o.order_no} = Ready",
             f"Reports ▸ Ready Closing Stock: stock {p2.stock_no} (BANG-32) is the only one of this "
             "flow still in stock", "Account ▸ Ledger KK JEWELS: sale debit, receipt 1,00,000 credit",
             "Reports ▸ Karigar ▸ Worker Metal Ledger: CHAND — issue 4.000 (edited), receipt 3.800",
             "Accounts Dr = Cr and stock = movements were checked after the flow")

    print(f"\nPASSED {passes}  FAILED {len(fails)}: {fails or 'none'}")
    out = DATA_DIR / "full_flow_report.md"
    out.write_text(f"# Full flow check — {TODAY:%d-%m-%Y}  ({TAG})\n\nDatabase `{DB_PATH}`  \n"
                   f"Backup before the run `{bk}`  \nResult: **{passes} passed, {len(fails)} failed**"
                   + (f" — {', '.join(fails)}" if fails else "") + "\n" + "\n".join(report) + "\n",
                   encoding="utf-8")
    print(f"Report: {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
