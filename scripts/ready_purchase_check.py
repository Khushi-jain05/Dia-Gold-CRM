"""Purchase ▸ Ready Items, driven through the screen itself (as a user does it),
on the app's own data; the piece stays in stock so it can be compared.

    python scripts/ready_purchase_check.py

Supplier FULL FLOW SUPPLIER (made by scripts/full_flow_check.py) -> Add Piece:
BANG-32, 14KT 590 (title and metal rate fill from the masters), G-Wt 25.000,
labour 1,200 / g -> Stones: POLKI 12-14 20 pcs 3.500 ct @8,100 and DIA RD MIX
200 pcs 3.000 ct @13,500 -> N-Wt follows (25.000 - 6.5 x 0.2 = 23.700) ->
Save. Then the voucher, the stock item, the accounts and Ready Closing Stock
are checked. The database is backed up first; the result is appended to
full_flow_report.md next to it.
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402
from sqlalchemy import select  # noqa: E402

from diagold.config import DATA_DIR, DB_PATH  # noqa: E402

TODAY = date.today()
TAG = f"FF-{TODAY:%d%b}".upper()
fails: list[str] = []
passes = 0


def check(label, got, want):
    global passes
    if got == want:
        passes += 1
        print("  PASS", label, got)
    else:
        fails.append(label)
        print("  FAIL", label, got, f"(want {want})")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    bk = DB_PATH.with_name(f"{DB_PATH.name}.backup-{datetime.now():%Y%m%d-%H%M%S}-pre-ready-purchase")
    shutil.copy2(DB_PATH, bk)
    from diagold.db.session import SessionLocal, init_db
    init_db()
    from diagold.db.models import (Account, AccountEntry, Metal, ProductSku, ReadyVoucher,
                                   StockItem, StoneSku)
    from diagold.services import stock_tools as STK
    import diagold.ui.ready_vouchers as RV
    # Answer the screen's own questions as a user would (Save? Yes).
    RV.confirm_save = lambda *a, **k: True
    shown: list[str] = []
    QMessageBox.information = staticmethod(lambda *a, **k: shown.append(a[2]))
    QMessageBox.warning = staticmethod(lambda *a, **k: shown.append("WARN " + a[2]))

    with SessionLocal() as s:
        sup = s.scalar(select(Account).where(Account.code == "FFSUP"))
        polki = s.scalar(select(StoneSku).where(StoneSku.sku_code == "POLKI 12-14"))
        dia = s.scalar(select(StoneSku).where(StoneSku.sku_code == "DIA RD MIX"))
        bang = s.scalar(select(ProductSku).where(ProductSku.sku_code == "BANG-32"))
        m590 = s.scalar(select(Metal).where(Metal.name == "14KT 590"))
        if not all([sup, polki, dia, bang, m590]):
            print("Run scripts/full_flow_check.py first (supplier FFSUP, DIA RD MIX).")
            return 1
        sup_name, sup_id = sup.name, sup.id
        stones = [
            {"label": polki.sku_code, "stone_sku_id": polki.id, "s_type": "POL",
             "size": polki.size or "", "pcs": 20, "weight": "3.500", "price": "8100",
             "unit": "Cts"},
            {"label": dia.sku_code, "stone_sku_id": dia.id, "s_type": "DIA", "size": "",
             "pcs": 200, "weight": "3.000", "price": "13500", "unit": "Cts"}]

    print(f"Database: {DB_PATH}\nBackup:   {bk}")
    print("\n== Purchase ▸ Ready Items (the screen)")
    w = RV.ReadyVoucherWidget("rp_purchase")
    w.account.setCurrentText(sup_name)
    check("supplier picked", w._account_id(), sup_id)
    w.ref.setText(TAG)
    w.bill_no.setText(TAG + "-RP")

    # Add Piece: drive the dialog exactly as typed on screen.
    captured = {}

    def fill(dlg) -> QDialog.DialogCode:
        dlg.sku.setCurrentIndex(dlg.sku.findData(bang.id))
        dlg.metal.setCurrentIndex(dlg.metal.findData(m590.id))   # title + rate follow
        dlg.colour.setText("Y")
        dlg.size.setText("2.4")
        dlg.gross.setValue(25.0)
        captured["net_no_stones"] = round(dlg.net.value(), 3)
        dlg.stones = [dict(x) for x in stones]                   # what Stones… returns
        dlg._net_from_stones()
        dlg._recalc()
        dlg.lab_rate.setValue(1200)
        captured["values"] = dlg.values()
        return QDialog.DialogCode.Accepted
    RV.NewPieceDialog.exec = fill
    w.add_piece()
    v = captured["values"]
    check("before the stones N-Wt = G-Wt", captured["net_no_stones"], 25.0)
    check("N-Wt after the stones = 25.000 − 6.5 ct × 0.2", v["net_wt"], D("23.700"))
    check("title / metal rate from the masters", (v["title"], v["metal_rate"]),
          (D("590.000"), D("8680.67")))
    check("FineWt = 23.700 × 590 / 1000", v["fine_wt"], D("13.983"))
    check("St Wt 6.500 ct, stone amount 28,350 + 40,500", (v["st_wt"], v["stone_amount"]),
          (D("6.500"), D("68850.00")))
    metal_amt = (D("23.700") * D("8680.67")).quantize(D("0.01"))
    labour = (D("23.700") * 1200).quantize(D("0.01"))
    check("metal amount = 23.700 × 8,680.67", v["metal_amount"], metal_amt)
    check("labour = 1,200 × 23.700", D(str(v["labour"])).quantize(D("0.01")), labour)
    total = metal_amt + D("68850.00") + labour
    check("total", D(str(v["total"])).quantize(D("0.01")), total)
    check("one line on the grid", w.grid.rowCount(), 1)
    w.save()
    print("   screen says:", w.totals.text())

    with SessionLocal() as s:
        rv = s.scalars(select(ReadyVoucher).where(ReadyVoucher.vr_type == "rp_purchase")
                       .order_by(ReadyVoucher.id.desc())).first()
        ln = rv.lines[0]
        item = s.get(StockItem, ln.stock_item_id)
        check("voucher saved with the bill no", rv.bill_no, TAG + "-RP")
        check("piece in stock, source purchase", (item.status, item.source), ("in_stock", "purchase"))
        check("stock item G / N", (D(str(item.gross_wt)), D(str(item.net_wt))),
              (D("25.000"), D("23.700")))
        ents = s.scalars(select(AccountEntry).where(AccountEntry.ref_kind == "rp_purchase",
                                                    AccountEntry.ref_no == rv.vr_no)).all()
        check("accounts: Dr Purchase = Cr supplier = total",
              (sum(D(str(e.debit or 0)) for e in ents), sum(D(str(e.credit or 0)) for e in ents)),
              (total, total))
        row = next((r for r in STK.ready_closing_stock(s, TODAY) if r["stock_no"] == item.stock_no), {})
        check("Ready Closing Stock: DIA WT 3.000 · POL WT 3.500",
              (row.get("dia_wt"), row.get("polki_wt")), (D("3.000"), D("3.500")))
        check("... N-WT 23.700, OTH-WT 0", (row.get("n_wt"), row.get("oth_wt")), (D("23.700"), None))
        vr_no, stock_no = rv.vr_no, item.stock_no

    print(f"\nPASSED {passes}  FAILED {len(fails)}: {fails or 'none'}")
    rep = DATA_DIR / "full_flow_report.md"
    with rep.open("a", encoding="utf-8") as f:
        f.write(f"\n## M. Purchase ▸ Ready Items — through the screen ({passes} passed, "
                f"{len(fails)} failed)\n\n"
                f"- Ready Items Purchase Vr **{vr_no}** from {sup_name}, bill {TAG}-RP: BANG-32 "
                "14KT 590 Y size 2.4, G 25.000; stones POLKI 12-14 20 / 3.500 ct @8,100, DIA RD MIX "
                "200 / 3.000 ct @13,500 → **N-Wt 23.700**, FineWt 13.983\n"
                f"- Metal {metal_amt:,.2f} + Stones 68,850.00 + Labour {labour:,.2f} = **{total:,.2f}**; "
                "Dr Purchase A/c, Cr FULL FLOW SUPPLIER\n"
                f"- Stock **{stock_no}** stays in stock — Ready Closing Stock shows DIA WT 3.000, "
                "POL WT 3.500\n")
    print(f"Report: {rep}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
