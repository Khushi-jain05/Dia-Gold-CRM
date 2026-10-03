"""Inventory - metal and stone vouchers, their postings, and the ledgers read
from them (28 Sept R1 / R13 / R14, T-01, T-10).

Rules (from the 28 Sept notes):

* Every voucher line posts one stock-ledger row; location and worker balances
  are always the running sum of those rows - never typed.
* Fine weight = weight x the metal's title, stored at posting time.
* Voucher numbers run per voucher type.
* Going below zero at a location is a setting - block, warn or allow - and
  defaults to WARN, because the legacy Metal Analysis already carries
  negative closings (Primary 24KT Gold -1,030.359 g) that migration must
  accept (28 Sept Q6).
* Deleting a voucher reverses its postings and writes a DeletionLog row.

What Load Metal, Issue On Tree, Conversion, Adjustment, Worker Recovery, WIP
Rtn and Bhav Cut do was not explained (C-04); those stay placeholders.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    AccountEntry,
    DeletionLog,
    InvVoucher,
    InvVoucherLine,
    Location,
    MaterialStock,
    Metal,
    StockMovement,
    StoneSku,
)
from diagold.services import costing, production, settings
from diagold.services.production import ProductionError

ZERO = Decimal("0")
D3 = Decimal("0.001")
D4 = Decimal("0.0001")


@dataclass(frozen=True)
class VoucherType:
    key: str
    title: str
    material: str          # metal / stone
    direction: int         # +1 into the location, -1 out of it
    party: str             # what the Account is: supplier / worker
    legacy: str            # VrType as the legacy ledgers print it


VOUCHER_TYPES: dict[str, VoucherType] = {v.key: v for v in (
    VoucherType("metal_purchase", "Metal Purchase", "metal", +1, "supplier", "MP"),
    VoucherType("metal_issue", "Metal Issue Outside / Worker", "metal", -1, "worker", "MI"),
    VoucherType("metal_receipt", "Metal Receipt", "metal", +1, "worker", "MR"),
    VoucherType("stone_purchase", "Stone Purchase", "stone", +1, "supplier", "SP"),
    VoucherType("stone_issue", "Stone Issue Outside / Worker", "stone", -1, "worker", "SI"),
    VoucherType("stone_receipt", "Stone Receipt", "stone", +1, "worker", "SR"),
)}

NEGATIVE_SETTING = "inventory.negative_stock"
NEGATIVE_MODES = ("block", "warn", "allow")


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def negative_mode(session: Session) -> str:
    mode = settings.get_setting(session, NEGATIVE_SETTING, "warn")
    return mode if mode in NEGATIVE_MODES else "warn"


def next_vr_no(session: Session, vr_type: str) -> int:
    nos = session.scalars(select(InvVoucher.vr_no).where(InvVoucher.vr_type == vr_type)).all()
    return (max(nos) + 1) if nos else 1


# --------------------------------------------------------------------------
# Line arithmetic
# --------------------------------------------------------------------------
def line_fine(session: Session, metal_id: int | None, weight: Any) -> Decimal:
    metal = session.get(Metal, metal_id) if metal_id else None
    return (costing.fine_metal_weight(metal, weight) if metal else ZERO).quantize(D4)


def line_amount(material: str, pcs: Any, weight: Any, price: Any, unit: str) -> Decimal:
    """Metal: weight x price per gram. Stone: carats (or pieces) x price."""
    qty = _dec(pcs) if (unit or "").lower().startswith("pc") else _dec(weight)
    return (qty * _dec(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fill_line(session: Session, vr_type: str, row: dict[str, Any]) -> None:
    """Derived columns on one line, recomputed before every save."""
    vt = VOUCHER_TYPES[vr_type]
    if vt.material == "metal":
        row["fine_wt"] = line_fine(session, row.get("metal_id"), row.get("weight"))
        row["unit"] = row.get("unit") or "Gms"
        if vr_type == "metal_receipt":
            pct = _dec(row.get("wastage_pct"))
            if pct and not _dec(row.get("wastage_wt")):
                row["wastage_wt"] = (_dec(row.get("weight")) * pct / 100).quantize(D3)
    else:
        row["unit"] = row.get("unit") or "Cts"
        sku = session.get(StoneSku, row.get("stone_sku_id")) if row.get("stone_sku_id") else None
        if sku is not None:
            row["size"] = row.get("size") or sku.size or ""
            row["s_type"] = row.get("s_type") or sku.stone_type or ""
            if not _dec(row.get("price")):
                row["price"] = _dec(sku.cost_price) or _dec(sku.sale_price)
    row["amount"] = line_amount(vt.material, row.get("pcs"), row.get("weight"),
                                row.get("price"), row.get("unit") or "")


def check_lines(session: Session, vr_type: str, account_id: int | None,
                rows: list[dict[str, Any]]) -> str | None:
    """A sentence to refuse the save with, or None."""
    vt = VOUCHER_TYPES[vr_type]
    if not account_id:
        return f"Choose the {'supplier' if vt.party == 'supplier' else 'worker / party'}."
    real = [r for r in rows if _dec(r.get("weight")) or int(r.get("pcs") or 0)]
    if not real:
        return "Enter at least one line with a weight (or pieces)."
    for n, r in enumerate(real, start=1):
        if _dec(r.get("weight")) < 0 or int(r.get("pcs") or 0) < 0:
            return f"Line {n}: weight and pieces cannot be negative."
        if not r.get("location_id"):
            return f"Line {n}: choose the location."
        if vt.material == "metal" and not r.get("metal_id"):
            return f"Line {n}: choose the metal."
        if vt.material == "stone" and not (r.get("stone_sku_id") or r.get("particulars")):
            return f"Line {n}: choose the stone SKU (or describe the stone)."
    return None


def shortfalls(session: Session, vr_type: str, rows: list[dict[str, Any]],
               is_opening: bool = False) -> list[str]:
    """Lines that would take a location below zero."""
    vt = VOUCHER_TYPES[vr_type]
    if vt.direction > 0 or is_opening:
        return []
    need: dict[tuple, list[Any]] = {}
    for r in rows:
        if not r.get("location_id"):
            continue
        ref = r.get("metal_id") if vt.material == "metal" else r.get("stone_sku_id")
        size = "" if vt.material == "metal" else (r.get("size") or "")
        text = "" if ref else (r.get("particulars") or "")
        key = (r["location_id"], ref, size, text)
        acc = need.setdefault(key, [0, ZERO])
        acc[0] += int(r.get("pcs") or 0)
        acc[1] += _dec(r.get("weight"))
    out = []
    for (loc_id, ref, size, text), (pcs, wt) in need.items():
        have_pcs, have_wt = production.stock_balance(session, loc_id, vt.material, ref, size, text)
        if wt > have_wt or (vt.material == "stone" and pcs > have_pcs):
            loc = session.get(Location, loc_id)
            name = (session.get(Metal, ref).name if vt.material == "metal" and ref else
                    session.get(StoneSku, ref).sku_code if ref else text)
            out.append(f"{loc.name if loc else '?'} holds {have_wt} of {name}; this takes "
                       f"{wt} - it goes to {have_wt - wt}.")
    return out


# --------------------------------------------------------------------------
# Posting
# --------------------------------------------------------------------------
def post_voucher(session: Session, v: InvVoucher) -> None:
    """Post a saved voucher's lines to the stock ledger."""
    vt = VOUCHER_TYPES[v.vr_type]
    mode = negative_mode(session)
    short = shortfalls(session, v.vr_type, [
        {"location_id": l.location_id, "metal_id": l.metal_id, "stone_sku_id": l.stone_sku_id,
         "size": l.size, "particulars": l.particulars, "pcs": l.pcs, "weight": l.weight}
        for l in v.lines], v.is_opening)
    if short and mode == "block":
        raise ProductionError("Not enough stock:\n" + "\n".join(short))
    if v.is_opening and vt.direction < 0:
        # ASSUMPTION: an Opening issue records what a karigar already held when
        # the system started - no location is reduced (28 Sept C-04).
        return
    for l in v.lines:
        wt, pcs = _dec(l.weight), int(l.pcs or 0)
        if not wt and not pcs:
            continue
        ref = l.metal_id if vt.material == "metal" else l.stone_sku_id
        sku = session.get(StoneSku, l.stone_sku_id) if l.stone_sku_id else None
        size = "" if vt.material == "metal" else (l.size or (sku.size if sku else "") or "")
        production.adjust_stock(
            session, l.location_id, vt.material, ref, vt.direction * pcs, vt.direction * wt,
            size=size, ref_text="" if ref else (l.particulars or ""),
            what=l.particulars or "", kind="inward" if vt.direction > 0 else "outward",
            mv_date=v.vr_date, ref_kind=v.vr_type, ref_no=v.vr_no, remark=l.remark or "",
            allow_negative=mode != "block", account_id=v.account_id,
            fine_wt=vt.direction * _dec(l.fine_wt),
            value=(vt.direction * _dec(l.amount)) if _dec(l.amount) else None,
        )
    post_accounts(session, v)


PURCHASE_LEDGER = "Purchase A/c"


def post_accounts(session: Session, v: InvVoucher) -> None:
    """The accounting of a purchase: Dr Purchase A/c, Cr the supplier, for
    the voucher's total (28 Sept §4.12). Issues and receipts move stock
    only and post nothing here."""
    if not v.vr_type.endswith("_purchase"):
        return
    total = sum((_dec(l.amount) for l in v.lines), ZERO).quantize(Decimal("0.01"))
    if not total:
        return
    vt = VOUCHER_TYPES[v.vr_type]
    supplier = session.get(Account, v.account_id) if v.account_id else None
    text = f"{vt.title} Vr {v.vr_no}" + (f" · Ref {v.ref_no}" if v.ref_no else "")
    session.add(AccountEntry(entry_date=v.vr_date, ledger=PURCHASE_LEDGER, debit=total,
                             ref_kind=v.vr_type, ref_no=v.vr_no, narration=text))
    session.add(AccountEntry(entry_date=v.vr_date, account_id=v.account_id,
                             ledger=supplier.name if supplier else "?", credit=total,
                             ref_kind=v.vr_type, ref_no=v.vr_no, narration=text))
    session.flush()


def post_entry(session: Session, *, on: date, amount: Decimal, ref_kind: str, ref_no: int,
               narration: str, debit_ledger: str = "", debit_account_id: int | None = None,
               credit_ledger: str = "", credit_account_id: int | None = None) -> None:
    """One double entry: Dr one side, Cr the other, for ``amount``. A party
    side names its Account; a nominal side (Sales A/c) only its ledger name."""
    amount = _dec(amount).quantize(Decimal("0.01"))
    if not amount:
        return

    def name(ledger: str, acct_id: int | None) -> str:
        if acct_id:
            a = session.get(Account, acct_id)
            return a.name if a else "?"
        return ledger
    session.add(AccountEntry(entry_date=on, account_id=debit_account_id,
                             ledger=name(debit_ledger, debit_account_id), debit=amount,
                             ref_kind=ref_kind, ref_no=ref_no, narration=narration))
    session.add(AccountEntry(entry_date=on, account_id=credit_account_id,
                             ledger=name(credit_ledger, credit_account_id), credit=amount,
                             ref_kind=ref_kind, ref_no=ref_no, narration=narration))
    session.flush()


def remove_entries(session: Session, ref_kind: str, ref_no: int) -> None:
    for e in session.scalars(select(AccountEntry).where(
            AccountEntry.ref_kind == ref_kind, AccountEntry.ref_no == ref_no)).all():
        session.delete(e)
    session.flush()


def _vr_code(ref_kind: str) -> str:
    if ref_kind in VOUCHER_TYPES:
        return VOUCHER_TYPES[ref_kind].legacy
    from diagold.services import sales
    if ref_kind in sales.READY_TYPES:
        return sales.READY_TYPES[ref_kind].code
    return ref_kind


def backfill_accounts(session: Session) -> int:
    """Post the accounting of purchases saved before it was posted. Safe to
    run every start: a voucher that already has its entries is skipped."""
    done = {(k, n) for k, n in session.execute(
        select(AccountEntry.ref_kind, AccountEntry.ref_no))}
    n = 0
    for v in session.scalars(select(InvVoucher).where(
            InvVoucher.vr_type.in_(("metal_purchase", "stone_purchase")))):
        if (v.vr_type, v.vr_no) not in done:
            post_accounts(session, v)
            n += 1
    return n


def account_ledger(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Account Ledger: every accounting entry with a running balance per
    ledger (Dr positive, Cr negative); entries before the From date make up
    each ledger's opening."""
    rows, bal = [], {}
    q = select(AccountEntry).where(AccountEntry.entry_date <= date_to).order_by(
        AccountEntry.entry_date, AccountEntry.id)
    for e in session.scalars(q):
        name = e.ledger
        if e.account_id:
            acct = session.get(Account, e.account_id)
            name = acct.name if acct else name
        b = bal.get(name, ZERO) + _dec(e.debit) - _dec(e.credit)
        bal[name] = b
        if e.entry_date < date_from:
            continue
        rows.append({"ledger": name, "date": e.entry_date,
                     "vrtype": _vr_code(e.ref_kind),
                     "vrno": e.ref_no, "narration": e.narration,
                     "debit": _dec(e.debit) or None, "credit": _dec(e.credit) or None,
                     "balance": abs(b), "drcr": "Dr" if b >= 0 else "Cr"})
    rows.sort(key=lambda r: (r["ledger"].lower(), r["date"]))
    return rows


def metal_to_job_step(session: Session, voucher: Any, location_id: int, metal_id: int,
                      weight: Any, pcs: int = 0) -> None:
    """F5 on an issue voucher (28 Sept §4.4 / T-03): metal handed out with a
    job step, taken from a location's stock and booked to the karigar."""
    wt = _dec(weight)
    if wt <= 0:
        return
    if not location_id or not metal_id:
        raise ProductionError("F5 Metal: choose the location and the metal.")
    short = shortfalls(session, "metal_issue", [{"location_id": location_id,
                                                 "metal_id": metal_id, "weight": wt}])
    if short and negative_mode(session) == "block":
        raise ProductionError("Not enough stock:\n" + "\n".join(short))
    production.adjust_stock(
        session, location_id, "metal", metal_id, -int(pcs or 0), -wt, kind="outward",
        mv_date=voucher.vr_date, job_id=voucher.job_id, ref_kind="job_voucher",
        ref_no=voucher.vr_no, allow_negative=negative_mode(session) != "block",
        account_id=voucher.worker_id, fine_wt=-line_fine(session, metal_id, wt),
        remark="metal with a job step (F5)")


def delete_voucher(session: Session, v: InvVoucher, *, user_id: int | None = None) -> None:
    """Reverse a voucher's postings and keep the whole voucher in the log."""
    vt = VOUCHER_TYPES[v.vr_type]
    moves = session.scalars(select(StockMovement).where(
        StockMovement.ref_kind == v.vr_type, StockMovement.ref_no == v.vr_no)).all()
    for m in moves:
        row = production.stock_row(session, m.location_id, m.material_class, m.ref_id,
                                   m.size, m.ref_text)
        if row is not None:
            row.pcs = int(row.pcs) - int(m.pcs)
            row.weight = (_dec(row.weight) - _dec(m.weight)).quantize(D4)
            if vt.direction > 0 and (row.pcs < 0 or _dec(row.weight) < 0) \
                    and negative_mode(session) == "block":
                raise ProductionError(
                    f"{vt.title} {v.vr_no} cannot be deleted - what it brought in has "
                    "already gone out again.")
        session.delete(m)
    for e in session.scalars(select(AccountEntry).where(
            AccountEntry.ref_kind == v.vr_type, AccountEntry.ref_no == v.vr_no)).all():
        session.delete(e)

    def image(obj) -> dict[str, Any]:
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

    session.add(DeletionLog(
        user_id=user_id, kind=v.vr_type, ref=f"{vt.title} {v.vr_no}",
        before_json=json.dumps({"voucher": image(v), "lines": [image(l) for l in v.lines]},
                               default=str)))
    session.flush()


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def metal_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Location x metal: opening / inward / outward / closing weight, fine and
    base (GOLD / ALLOY), as the legacy Metal Analysis (28 Sept §4.14)."""
    acc: dict[tuple[int, int | None], dict[str, Decimal]] = {}
    for m in session.scalars(select(StockMovement).where(
            StockMovement.material_class == "metal", StockMovement.mv_date <= date_to)):
        a = acc.setdefault((m.location_id, m.ref_id), {k: ZERO for k in (
            "opening", "inward", "outward", "fine")})
        w = _dec(m.weight)
        if m.mv_date < date_from or m.kind == "opening":
            a["opening"] += w
        elif w >= 0:
            a["inward"] += w
        else:
            a["outward"] += -w
        a["fine"] += _dec(m.fine_wt)
    rows = []
    for (loc_id, metal_id), a in acc.items():
        loc = session.get(Location, loc_id)
        metal = session.get(Metal, metal_id) if metal_id else None
        closing = a["opening"] + a["inward"] - a["outward"]
        rows.append({
            "location": loc.name if loc else "?", "_location_id": loc_id,
            "_metal_id": metal_id, "type": "Actual", "metal": metal.name if metal else "?",
            "title": (costing.purity_fraction(metal) * 1000).quantize(Decimal("0.1"))
            if metal else ZERO,
            "opening": a["opening"].quantize(D3), "inward": a["inward"].quantize(D3),
            "outward": a["outward"].quantize(D3), "closing": closing.quantize(D3),
            "fine": a["fine"].quantize(D3), "base": (metal.base_metal if metal else "") or "",
            "_negative": closing < 0,
        })
    rows.sort(key=lambda r: (r["location"].lower(), r["metal"].lower()))
    return rows


def location_ledger(session: Session, location_id: int, material: str, ref_id: int | None,
                    date_from: date, date_to: date) -> list[dict[str, Any]]:
    """One location's movements of one metal (or stone), with running closing."""
    q = (select(StockMovement)
         .where(StockMovement.location_id == location_id,
                StockMovement.material_class == material,
                StockMovement.mv_date <= date_to)
         .order_by(StockMovement.mv_date, StockMovement.id))
    if ref_id:
        q = q.where(StockMovement.ref_id == ref_id)
    bal, rows, opened = ZERO, [], False
    for m in session.scalars(q):
        w = _dec(m.weight)
        if m.mv_date < date_from:
            bal += w
            continue
        if not opened:
            rows.append({"date": None, "vrno": "", "vrtype": "OPENING", "particulars": "",
                         "job_no": "", "inward": None, "outward": None, "closing": bal})
            opened = True
        bal += w
        acct = session.get(Account, m.account_id) if m.account_id else None
        vt = VOUCHER_TYPES.get(m.ref_kind)
        rows.append({
            "date": m.mv_date, "vrno": m.ref_no or "",
            "vrtype": vt.legacy if vt else (m.ref_kind or m.kind).upper(),
            "particulars": acct.name if acct else (m.remark or ""),
            "job_no": "", "inward": w if w > 0 else None, "outward": -w if w < 0 else None,
            "closing": bal.quantize(D3),
        })
    return rows


def worker_balances(session: Session, date_to: date) -> list[dict[str, Any]]:
    """Worker Balance (Metal) from Inventory: issued to each karigar less
    received back and wastage allowed, in weight and fine, per metal."""
    acc: dict[tuple[int, int], dict[str, Decimal]] = {}
    q = (select(InvVoucherLine, InvVoucher).join(InvVoucher)
         .where(InvVoucher.vr_type.in_(("metal_issue", "metal_receipt")),
                InvVoucher.vr_date <= date_to))
    for line, v in session.execute(q):
        if not v.account_id or not line.metal_id:
            continue
        a = acc.setdefault((v.account_id, line.metal_id), {k: ZERO for k in (
            "issued", "received", "wastage", "fine")})
        w = _dec(line.weight)
        if v.vr_type == "metal_issue":
            a["issued"] += w
            a["fine"] += _dec(line.fine_wt)
        else:
            a["received"] += w
            a["wastage"] += _dec(line.wastage_wt)
            metal = session.get(Metal, line.metal_id)
            a["fine"] -= _dec(line.fine_wt) + costing.fine_metal_weight(metal, line.wastage_wt)
    rows = []
    for (acct_id, metal_id), a in acc.items():
        acct = session.get(Account, acct_id)
        metal = session.get(Metal, metal_id)
        bal = a["issued"] - a["received"] - a["wastage"]
        rows.append({"worker": acct.name if acct else "?", "metal": metal.name if metal else "?",
                     "issued": a["issued"].quantize(D3), "received": a["received"].quantize(D3),
                     "wastage": a["wastage"].quantize(D3), "balance": bal.quantize(D3),
                     "fine": a["fine"].quantize(D3), "_negative": bal < 0})
    rows.sort(key=lambda r: (r["worker"].lower(), r["metal"].lower()))
    return rows


def check_balance(session: Session, account_id: int | None,
                  on_date: date | None = None) -> dict[str, Any]:
    """Check Bal on Metal Issue (28 Sept §4.12): before issuing, what the
    karigar already holds - the Worker Metal Ledger closing and, per metal,
    the Inventory issue / receipt balance - and what each location has in
    stock to issue from."""
    on_date = on_date or date.today()
    acct = session.get(Account, account_id) if account_id else None
    wt = fine = ZERO
    per_metal = []
    if acct is not None:
        wt, fine = production.worker_metal_balance(session, acct.id, on_date)
        per_metal = [r for r in worker_balances(session, on_date) if r["worker"] == acct.name]
    stock = []
    for row in session.scalars(select(MaterialStock).where(
            MaterialStock.material_class == "metal", MaterialStock.weight != 0)):
        loc = session.get(Location, row.location_id)
        metal = session.get(Metal, row.ref_id) if row.ref_id else None
        stock.append({"location": loc.name if loc else "?",
                      "metal": metal.name if metal else row.ref_text,
                      "weight": _dec(row.weight).quantize(D3),
                      "fine": line_fine(session, row.ref_id, row.weight).quantize(D3),
                      "_negative": _dec(row.weight) < 0})
    stock.sort(key=lambda r: (r["location"].lower(), r["metal"].lower()))
    return {"worker": acct.name if acct else "", "bal_wt": wt, "bal_fine": fine,
            "per_metal": per_metal, "stock": stock}


def stone_outstanding(session: Session, account_id: int | None = None) -> list[dict[str, Any]]:
    """Show O/S on Stone Receipt (28 Sept §4.11): stones issued outside / to a
    worker and not yet received back, per account, location, stone and size -
    what the receipt can bring in."""
    acc: dict[tuple, dict[str, Any]] = {}
    q = (select(InvVoucherLine, InvVoucher).join(InvVoucher)
         .where(InvVoucher.vr_type.in_(("stone_issue", "stone_receipt"))))
    if account_id:
        q = q.where(InvVoucher.account_id == account_id)
    for line, v in session.execute(q):
        if not v.account_id:
            continue
        key = (v.account_id, line.location_id, line.stone_sku_id, line.particulars or "",
               line.size or "")
        a = acc.setdefault(key, {"pcs": 0, "weight": ZERO, "price": ZERO, "unit": "Cts",
                                 "s_type": ""})
        sign = 1 if v.vr_type == "stone_issue" else -1
        a["pcs"] += sign * int(line.pcs or 0)
        a["weight"] += sign * _dec(line.weight)
        if sign > 0:
            a["price"], a["unit"] = _dec(line.price), line.unit or "Cts"
            a["s_type"] = line.s_type or a["s_type"]
    rows = []
    for (acct_id, loc_id, sku_id, part, size), a in acc.items():
        if a["pcs"] <= 0 and a["weight"] <= 0:
            continue
        acct = session.get(Account, acct_id)
        loc = session.get(Location, loc_id) if loc_id else None
        sku = session.get(StoneSku, sku_id) if sku_id else None
        rows.append({"account_id": acct_id, "account": acct.name if acct else "?",
                     "location_id": loc_id, "location": loc.name if loc else "",
                     "stone_sku_id": sku_id, "stone": sku.sku_code if sku else part,
                     "particulars": part, "size": size, "pcs": a["pcs"],
                     "weight": a["weight"].quantize(D3), "price": a["price"],
                     "unit": a["unit"], "s_type": a["s_type"]})
    rows.sort(key=lambda r: (r["account"].lower(), r["stone"].lower(), r["size"]))
    return rows


def day_book(session: Session, date_from: date, date_to: date,
             material: str | None = None) -> list[dict[str, Any]]:
    """Every Inventory voucher line in the period."""
    rows = []
    q = (select(InvVoucherLine, InvVoucher).join(InvVoucher)
         .where(InvVoucher.vr_date >= date_from, InvVoucher.vr_date <= date_to)
         .order_by(InvVoucher.vr_date, InvVoucher.vr_type, InvVoucher.vr_no,
                   InvVoucherLine.sno))
    for line, v in session.execute(q):
        vt = VOUCHER_TYPES.get(v.vr_type)
        if vt is None or (material and vt.material != material):
            continue
        acct = session.get(Account, v.account_id) if v.account_id else None
        loc = session.get(Location, line.location_id) if line.location_id else None
        if vt.material == "metal":
            metal = session.get(Metal, line.metal_id) if line.metal_id else None
            item = metal.name if metal else ""
        else:
            sku = session.get(StoneSku, line.stone_sku_id) if line.stone_sku_id else None
            item = (sku.sku_code if sku else line.particulars) or ""
        rows.append({
            "date": v.vr_date, "vrtype": vt.legacy, "voucher": vt.title, "vrno": v.vr_no,
            "account": acct.name if acct else "", "location": loc.name if loc else "",
            "item": item, "size": line.size, "pcs": line.pcs, "weight": _dec(line.weight),
            "fine": _dec(line.fine_wt), "price": _dec(line.price), "amount": _dec(line.amount),
            "wastage": _dec(line.wastage_wt) or None,
        })
    return rows
