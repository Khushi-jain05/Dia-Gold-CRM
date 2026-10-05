"""Accounts core (5 Oct Session 4, T-01 / T-02 / T-04).

Everything is derived from AccountEntry postings - the ledger, the day book,
the trial balance, bill-wise outstanding and the cash flow. Nothing holds a
balance of its own.

Postings (Dr / Cr, balanced per voucher):
    Ready Stock Sale / Metal Sale / Stone Sale    Dr customer      Cr Sales A/c
    Sale Return                                   Dr Sales Return  Cr customer
    Purchase (metal / stone / ready items)        Dr Purchase A/c  Cr supplier
    Ready Item Return                             Dr supplier      Cr Purchase Return
    Receipt (Cash / Bank)                         Dr Cash / Bank   Cr party
    Receipt (Metal receive)                       Dr Metal Stock   Cr party   (fine at the day's rate)
    Payment (Cash / Bank / Metal)                 Dr party         Cr Cash / Bank / Metal Stock
    Journal / Contra                              as typed
A sale or return in CASH mode is settled at once (Dr Cash Cr customer, or the
mirror on a return), so it never shows as a bill outstanding (T-04).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    AccountEntry,
    AccountGroup,
    AccountVoucher,
    AccountVoucherLine,
    BillAllocation,
    DeletionLog,
    InvVoucher,
    InvVoucherLine,
    Location,
    Metal,
    ReadyVoucher,
    StockMovement,
)
from diagold.services.production import ProductionError

ZERO = Decimal("0")
PAISA = Decimal("0.01")


def _dec(v: Any) -> Decimal:
    if v is None or v == "":
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


# --------------------------------------------------------------------------
# Account groups (Account Group Master, 5 Oct §4.2)
# --------------------------------------------------------------------------
# (name, under, nature) - the legacy list, in its order; "under" is the parent.
GROUPS: list[tuple[str, str | None, str]] = [
    ("Current Assets", None, "Assets"), ("Fixed Assets", None, "Assets"),
    ("Investments", None, "Assets"), ("Branch/Divisions", None, "Assets"),
    ("Accounts Receivable", "Current Assets", "Assets"),
    ("Sundry Debtors", "Accounts Receivable", "Assets"),
    ("Bank Account", "Current Assets", "Assets"),
    ("Bangkok bank saving a/c", "Bank Account", "Assets"),
    ("Cash-In-Hand", "Current Assets", "Assets"),
    ("Deposits (Asset)", "Current Assets", "Assets"),
    ("Loans & Advances (A)", "Current Assets", "Assets"),
    ("Other Current Assets", "Current Assets", "Assets"),
    ("PREPAID EXPENSES GOOD", "Current Assets", "Assets"),
    ("RAW MATERIAL", "Current Assets", "Assets"),
    ("Outgoing Approvals", "Current Assets", "Assets"),
    ("Current Liabilities", None, "Liabilities"),
    ("Accounts Payable", "Current Liabilities", "Liabilities"),
    ("Sundry Creditors", "Accounts Payable", "Liabilities"),
    ("Duties & Taxes", "Current Liabilities", "Liabilities"),
    ("CGST", "Duties & Taxes", "Liabilities"), ("IGST", "Duties & Taxes", "Liabilities"),
    ("Provisions", "Current Liabilities", "Liabilities"),
    ("In-Comming Approvals", "Current Liabilities", "Liabilities"),
    ("Loans (Liability)", None, "Liabilities"), ("Share Capital", None, "Liabilities"),
    ("Suspense A/c", None, "Liabilities"),
    ("Sales Accounts", None, "Income"), ("Direct Income", None, "Income"),
    ("In-Direct Income", None, "Income"),
    ("Purchase Accounts", None, "Expenses"), ("Direct Expenses", None, "Expenses"),
    ("In-Direct Expenses", None, "Expenses"), ("COST OF GOODS SOLD", None, "Expenses"),
    ("COST OF GOODS SOLD(A)", None, "Expenses"), ("MFG Expenses", None, "Expenses"),
    ("Mics.Expenses", None, "Expenses"), ("INTERNET", "In-Direct Expenses", "Expenses"),
]

# The nominal ledgers vouchers post to: name -> (code, group).
NOMINALS: dict[str, tuple[str, str]] = {
    "Sales A/c": ("SALESAC", "Sales Accounts"),
    "Sales Return A/c": ("SALESRET", "Sales Accounts"),
    "Purchase A/c": ("PURCHASEAC", "Purchase Accounts"),
    "Purchase Return A/c": ("PURCHRET", "Purchase Accounts"),
    "Cash": ("CASH", "Cash-In-Hand"),
    "Bank": ("BANK", "Bank Account"),
    "Metal Stock A/c": ("METALSTK", "RAW MATERIAL"),
}


def seed_groups(session: Session) -> int:
    """Add the groups the master does not have yet - the legacy list plus any
    group an Account already names. Never changes an existing group."""
    have = {g.name: g for g in session.scalars(select(AccountGroup))}
    n = 0
    for i, (name, under, nature) in enumerate(GROUPS, start=1):
        if name not in have:
            g = AccountGroup(name=name, code=name[:24].upper().replace(" ", ""),
                             nature=nature, index_no=i,
                             sub_ledger_required=name in ("Accounts Receivable",
                                                          "Accounts Payable"))
            session.add(g)
            have[name] = g
            n += 1
    session.flush()
    for name, under, _nature in GROUPS:
        g = have[name]
        if under and g.parent_id is None and under in have:
            g.parent_id = have[under].id
    for (gname,) in session.execute(select(Account.group_name).distinct()):
        if gname and gname not in have:
            g = AccountGroup(name=gname, code=gname[:24].upper().replace(" ", ""),
                             index_no=len(have) + 1)
            session.add(g)
            have[gname] = g
            n += 1
    session.flush()
    return n


def nominal(session: Session, name: str) -> Account:
    """The Account a nominal ledger name posts to (made the first time)."""
    code, group = NOMINALS[name]
    a = session.scalar(select(Account).where(Account.code == code))
    if a is None:
        a = Account(code=code, name=name, account_type="Accounts", group_name=group)
        session.add(a)
        session.flush()
    return a


def backfill_nominals(session: Session) -> int:
    """Entries posted before nominal ledgers were accounts get their account."""
    n = 0
    for e in session.scalars(select(AccountEntry).where(AccountEntry.account_id.is_(None))):
        if e.ledger in NOMINALS:
            e.account_id = nominal(session, e.ledger).id
            n += 1
    session.flush()
    return n


def nominal_ids(session: Session) -> set[int]:
    """Ids of the nominal ledgers (Sales A/c, Cash …), whatever they are named."""
    codes = [c for c, _g in NOMINALS.values()]
    return set(session.scalars(select(Account.id).where(Account.code.in_(codes))))


def group_of(session: Session, account: Account) -> AccountGroup | None:
    return session.scalar(select(AccountGroup).where(AccountGroup.name == account.group_name))


# --------------------------------------------------------------------------
# Voucher type labels (the VRTYPE column everywhere)
# --------------------------------------------------------------------------
ACC_TYPES = {"receipt": ("RCPT", "Receipt"), "payment": ("PYMT", "Payment"),
             "journal": ("JV", "Journal"), "contra": ("CNTR", "Contra"),
             "opening": ("OPN", "Opening")}


def vr_code(kind: str) -> str:
    if kind in ACC_TYPES:
        return ACC_TYPES[kind][0]
    from diagold.services import inventory as INV
    return INV._vr_code(kind)


def vr_title(kind: str) -> str:
    if kind in ACC_TYPES:
        return ACC_TYPES[kind][1]
    from diagold.services import inventory as INV, sales
    if kind in INV.VOUCHER_TYPES:
        return INV.VOUCHER_TYPES[kind].title
    if kind in sales.READY_TYPES:
        return sales.READY_TYPES[kind].title
    return kind


# --------------------------------------------------------------------------
# Posting
# --------------------------------------------------------------------------
def post(session: Session, *, on: date, ref_kind: str, ref_no: int, narration: str,
         dr: int, cr: int, amount: Any, mode: str = "", fine: Any = 0) -> None:
    """One balanced Dr / Cr pair between two accounts."""
    amount = _dec(amount).quantize(PAISA)
    if not amount:
        return
    for acct_id, side in ((dr, "debit"), (cr, "credit")):
        a = session.get(Account, acct_id)
        session.add(AccountEntry(entry_date=on, account_id=acct_id, ledger=a.name if a else "",
                                 ref_kind=ref_kind, ref_no=ref_no, narration=narration,
                                 mode=mode, fine_wt=_dec(fine), **{side: amount}))
    session.flush()


def settle_cash(session: Session, *, on: date, party_id: int, amount: Any, ref_kind: str,
                ref_no: int, narration: str, incoming: bool) -> None:
    """A cash sale (incoming) or cash return (outgoing) is settled on the spot."""
    cash = nominal(session, "Cash").id
    if incoming:
        post(session, on=on, ref_kind=ref_kind, ref_no=ref_no, narration=narration + " · cash",
             dr=cash, cr=party_id, amount=amount, mode="Cash")
    else:
        post(session, on=on, ref_kind=ref_kind, ref_no=ref_no, narration=narration + " · cash",
             dr=party_id, cr=cash, amount=amount, mode="Cash")


def remove_postings(session: Session, ref_kind: str, ref_no: int) -> None:
    for e in session.scalars(select(AccountEntry).where(
            AccountEntry.ref_kind == ref_kind, AccountEntry.ref_no == ref_no)).all():
        session.delete(e)
    session.flush()


# --------------------------------------------------------------------------
# Balances, ledger, day book, trial balance (T-01)
# --------------------------------------------------------------------------
def _opening_signed(a: Account) -> Decimal:
    ob = _dec(a.opening_balance)
    return ob if (a.opening_balance_type or "Dr") == "Dr" else -ob


def balance(session: Session, account_id: int, before: date | None = None,
            upto: date | None = None, mode: str | None = None) -> Decimal:
    """Signed balance (Dr +): master opening + postings before ``before`` /
    up to ``upto``."""
    a = session.get(Account, account_id)
    q = select(func.coalesce(func.sum(AccountEntry.debit), 0),
               func.coalesce(func.sum(AccountEntry.credit), 0)).where(
        AccountEntry.account_id == account_id)
    if before is not None:
        q = q.where(AccountEntry.entry_date < before)
    if upto is not None:
        q = q.where(AccountEntry.entry_date <= upto)
    if mode:
        q = q.where(AccountEntry.mode == mode)
    dr, cr = session.execute(q).one()
    return (_opening_signed(a) if (a and not mode) else ZERO) + _dec(dr) - _dec(cr)


def drcr(v: Decimal) -> tuple[Decimal, str]:
    return abs(v).quantize(PAISA), ("Dr" if v >= 0 else "Cr")


def ledger(session: Session, account_id: int | None, date_from: date, date_to: date, *,
           monthwise: bool = True, mode: str = "") -> list[dict[str, Any]]:
    """Party / account ledger. Month-wise (Particulars = month, Opening, Debit,
    Credit, Closing) as the legacy ledger opens, or every voucher."""
    if not account_id:
        return []
    mode = "" if mode in ("", "All") else mode
    running = balance(session, account_id, before=date_from, mode=mode or None)
    q = (select(AccountEntry).where(AccountEntry.account_id == account_id,
                                    AccountEntry.entry_date >= date_from,
                                    AccountEntry.entry_date <= date_to)
         .order_by(AccountEntry.entry_date, AccountEntry.id))
    if mode:
        q = q.where(AccountEntry.mode == mode)
    entries = list(session.scalars(q))
    rows = []
    amt, side = drcr(running)
    rows.append({"particulars": "Opening Balance", "date": date_from, "opening": amt,
                 "op_drcr": side, "debit": None, "credit": None, "closing": amt, "drcr": side,
                 "_kind": "opening"})
    if monthwise:
        months: dict[tuple[int, int], list[Decimal]] = {}
        for e in entries:
            m = months.setdefault((e.entry_date.year, e.entry_date.month), [ZERO, ZERO])
            m[0] += _dec(e.debit)
            m[1] += _dec(e.credit)
        for (y, mth), (d, c) in sorted(months.items()):
            o_amt, o_side = drcr(running)
            running += d - c
            amt, side = drcr(running)
            rows.append({"particulars": date(y, mth, 1).strftime("%B %Y"),
                         "date": date(y, mth, 1), "opening": o_amt, "op_drcr": o_side,
                         "debit": d or None, "credit": c or None, "closing": amt, "drcr": side,
                         "_month": (y, mth)})
        return rows
    for e in entries:
        running += _dec(e.debit) - _dec(e.credit)
        amt, side = drcr(running)
        other = _other_side(session, e)
        rows.append({"particulars": other, "date": e.entry_date, "vrtype": vr_code(e.ref_kind),
                     "vrno": e.ref_no, "narration": e.narration, "mode": e.mode,
                     "debit": _dec(e.debit) or None, "credit": _dec(e.credit) or None,
                     "closing": amt, "drcr": side, "fine": _dec(e.fine_wt) or None,
                     "_ref_kind": e.ref_kind})
    return rows


def _other_side(session: Session, e: AccountEntry) -> str:
    """The account on the other side of an entry - what the ledger names it by.
    A party is preferred over a nominal ledger (a cash sale's cash line names
    the customer, not Sales A/c)."""
    side = AccountEntry.credit if _dec(e.debit) else AccountEntry.debit
    others = list(session.scalars(select(AccountEntry).where(
        AccountEntry.ref_kind == e.ref_kind, AccountEntry.ref_no == e.ref_no,
        AccountEntry.account_id != e.account_id, side > 0)))
    if not others:
        return ""
    noms = nominal_ids(session)
    party = next((o for o in others if o.account_id not in noms), None)
    return (party or others[0]).ledger


def day_book(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Every accounting voucher in the period, with its party, amount and mode
    (day totals come from the grid's Group by date)."""
    rows = []
    seen: set[tuple[str, int]] = set()
    q = (select(AccountEntry).where(AccountEntry.entry_date >= date_from,
                                    AccountEntry.entry_date <= date_to)
         .order_by(AccountEntry.entry_date, AccountEntry.ref_kind, AccountEntry.ref_no,
                   AccountEntry.id))
    entries = list(session.scalars(q))
    by_voucher: dict[tuple[str, int], list[AccountEntry]] = defaultdict(list)
    for e in entries:
        by_voucher[(e.ref_kind, e.ref_no)].append(e)
    for e in entries:
        key = (e.ref_kind, e.ref_no)
        if key in seen:
            continue
        seen.add(key)
        es = by_voucher[key]
        noms = nominal_ids(session)
        cash_id = nominal(session, "Cash").id
        party = next((x.ledger for x in es if x.account_id not in noms), es[0].ledger)
        # The voucher's own amount - not doubled by a cash sale's settlement.
        main = [x for x in es if not (x.narration or "").endswith(" · cash")] or es
        total = sum((_dec(x.debit) for x in main), ZERO)
        cash = sum((_dec(x.debit) - _dec(x.credit) for x in es if x.account_id == cash_id), ZERO)
        rows.append({"date": e.entry_date, "vrtype": vr_code(e.ref_kind),
                     "voucher": vr_title(e.ref_kind), "vrno": e.ref_no, "party": party,
                     "narration": es[0].narration.split(" · cash")[0],
                     "mode": next((x.mode for x in es if x.mode), ""),
                     "amount": total.quantize(PAISA), "cash": cash or None,
                     "_ref_kind": e.ref_kind})
    return rows


def trial_balance(session: Session, date_from: date, date_to: date, *,
                  detailed: bool = False) -> list[dict[str, Any]]:
    """Group-wise Opening / Debit / Credit / Closing (Detailed: account by
    account under its group). A "Difference in Opening Balances" row appears
    when the masters' openings do not tally."""
    acc: dict[int, list[Decimal]] = {}
    for a in session.scalars(select(Account)):
        acc[a.id] = [_opening_signed(a), ZERO, ZERO]
    for aid, dr, cr in session.execute(
            select(AccountEntry.account_id, func.sum(AccountEntry.debit),
                   func.sum(AccountEntry.credit))
            .where(AccountEntry.entry_date < date_from, AccountEntry.account_id.is_not(None))
            .group_by(AccountEntry.account_id)):
        acc[aid][0] += _dec(dr) - _dec(cr)
    for aid, dr, cr in session.execute(
            select(AccountEntry.account_id, func.sum(AccountEntry.debit),
                   func.sum(AccountEntry.credit))
            .where(AccountEntry.entry_date >= date_from, AccountEntry.entry_date <= date_to,
                   AccountEntry.account_id.is_not(None))
            .group_by(AccountEntry.account_id)):
        acc[aid][1] += _dec(dr)
        acc[aid][2] += _dec(cr)
    groups: dict[str, list[Decimal]] = {}
    detail: list[dict[str, Any]] = []
    for aid, (op, dr, cr) in acc.items():
        if not (op or dr or cr):
            continue
        a = session.get(Account, aid)
        g = a.group_name or "(no group)"
        t = groups.setdefault(g, [ZERO, ZERO, ZERO])
        t[0] += op
        t[1] += dr
        t[2] += cr
        cl = op + dr - cr
        detail.append({"group": g, "particulars": a.name, "opening": abs(op) or None,
                       "op_drcr": "Dr" if op >= 0 else "Cr", "debit": dr or None,
                       "credit": cr or None, "closing": abs(cl), "drcr": "Dr" if cl >= 0 else "Cr",
                       "_account_id": aid, "_level": "account"})
    rows = []
    for g, (op, dr, cr) in sorted(groups.items(), key=lambda kv: kv[0].lower()):
        cl = op + dr - cr
        rows.append({"group": g, "particulars": g, "opening": abs(op) or None,
                     "op_drcr": "Dr" if op >= 0 else "Cr", "debit": dr or None,
                     "credit": cr or None, "closing": abs(cl), "drcr": "Dr" if cl >= 0 else "Cr",
                     "_level": "group"})
        if detailed:
            rows += sorted([d for d in detail if d["group"] == g],
                           key=lambda d: d["particulars"].lower())
    diff = sum((_opening_signed(a) for a in session.scalars(select(Account))), ZERO)
    if diff:
        amt, side = drcr(-diff)
        rows.append({"group": "Diff. in Opening Balances", "particulars": "Diff. in Opening Balances",
                     "opening": amt, "op_drcr": side, "debit": None, "credit": None,
                     "closing": amt, "drcr": side, "_level": "diff", "_negative": True})
    return rows


# --------------------------------------------------------------------------
# Bills and knock-off (T-02)
# --------------------------------------------------------------------------
RECEIVABLE = ("rs_sale", "metal_sale", "stone_sale")
PAYABLE = ("rp_purchase", "metal_purchase", "stone_purchase")
RETURN_ALLOC = {"rs_sale_return": "receivable", "rp_return": "payable"}


@dataclass
class Bill:
    kind: str
    no: int
    party_id: int
    on: date
    ref: str
    amount: Decimal
    credit_days: int
    location: str
    side: str            # receivable / payable

    @property
    def key(self) -> tuple[str, int]:
        return (self.kind, self.no)


def bills(session: Session, party_id: int | None = None, side: str | None = None,
          upto: date | None = None) -> list[Bill]:
    """Every bill-mode sale / purchase (and a party's master opening) - oldest first."""
    out: list[Bill] = []
    sides = [side] if side else ["receivable", "payable"]
    for sd in sides:
        kinds = RECEIVABLE if sd == "receivable" else PAYABLE
        q = select(ReadyVoucher).where(ReadyVoucher.vr_type.in_(kinds),
                                       ReadyVoucher.mode != "Cash")
        if party_id:
            q = q.where(ReadyVoucher.account_id == party_id)
        if upto:
            q = q.where(ReadyVoucher.vr_date <= upto)
        for v in session.scalars(q):
            acct = session.get(Account, v.account_id) if v.account_id else None
            loc = session.get(Location, v.lines[0].location_id) if v.lines and v.lines[0].location_id else None
            out.append(Bill(v.vr_type, v.vr_no, v.account_id, v.vr_date, v.ref_no,
                            _dec(v.total), int(v.credit_days or (acct.credit_days if acct else 0) or 0),
                            loc.name if loc else "", sd))
        q = select(InvVoucher).where(InvVoucher.vr_type.in_(kinds), InvVoucher.mode != "Cash")
        if party_id:
            q = q.where(InvVoucher.account_id == party_id)
        if upto:
            q = q.where(InvVoucher.vr_date <= upto)
        for v in session.scalars(q):
            acct = session.get(Account, v.account_id) if v.account_id else None
            loc = session.get(Location, v.lines[0].location_id) if v.lines and v.lines[0].location_id else None
            out.append(Bill(v.vr_type, v.vr_no, v.account_id, v.vr_date, v.ref_no,
                            sum((_dec(l.amount) for l in v.lines), ZERO).quantize(PAISA),
                            int(acct.credit_days or 0) if acct else 0,
                            loc.name if loc else "", sd))
        # A party's opening balance is its oldest bill.
        q = select(Account).where(Account.opening_balance > 0)
        if party_id:
            q = q.where(Account.id == party_id)
        for a in session.scalars(q):
            if (a.opening_balance_type or "Dr") == ("Dr" if sd == "receivable" else "Cr"):
                out.append(Bill("opening", a.id, a.id, date(2000, 1, 1), "opening",
                                _dec(a.opening_balance), int(a.credit_days or 0), "", sd))
    out.sort(key=lambda b: (b.on, b.kind, b.no))
    return out


def allocated(session: Session, bill: Bill) -> Decimal:
    return _dec(session.scalar(select(func.sum(BillAllocation.amount)).where(
        BillAllocation.bill_kind == bill.kind, BillAllocation.bill_no == bill.no,
        BillAllocation.party_id == bill.party_id)))


def pending_bills(session: Session, party_id: int, side: str) -> list[tuple[Bill, Decimal]]:
    out = []
    for b in bills(session, party_id, side):
        p = b.amount - allocated(session, b)
        if p > 0:
            out.append((b, p))
    return out


def allocate(session: Session, *, party_id: int, side: str, source_kind: str, source_no: int,
             amount: Any, on: date, manual: dict[tuple[str, int], Any] | None = None) -> Decimal:
    """Knock ``amount`` off the party's bills: the ones given (manual), the
    rest oldest first (FIFO). Returns what could not be placed (an advance)."""
    left = _dec(amount)
    pend = pending_bills(session, party_id, side)
    if manual:
        for (kind, no), amt in manual.items():
            amt = min(_dec(amt), left)
            match = next(((b, p) for b, p in pend if b.key == (kind, no)), None)
            if match is None or amt <= 0:
                continue
            amt = min(amt, match[1])
            session.add(BillAllocation(party_id=party_id, bill_kind=kind, bill_no=no,
                                       source_kind=source_kind, source_no=source_no,
                                       amount=amt, alloc_date=on))
            left -= amt
        session.flush()
        pend = pending_bills(session, party_id, side)
    for b, p in pend:
        if left <= 0:
            break
        amt = min(p, left)
        session.add(BillAllocation(party_id=party_id, bill_kind=b.kind, bill_no=b.no,
                                   source_kind=source_kind, source_no=source_no, amount=amt,
                                   alloc_date=on))
        left -= amt
    session.flush()
    return left


def remove_allocations(session: Session, source_kind: str, source_no: int) -> None:
    for a in session.scalars(select(BillAllocation).where(
            BillAllocation.source_kind == source_kind,
            BillAllocation.source_no == source_no)).all():
        session.delete(a)
    session.flush()


def bill_has_allocations(session: Session, kind: str, no: int) -> bool:
    return bool(session.scalar(select(BillAllocation.id).where(
        BillAllocation.bill_kind == kind, BillAllocation.bill_no == no)))


def outstanding(session: Session, date_from: date, date_to: date, *,
                side: str) -> list[dict[str, Any]]:
    """Outstanding Receivables / Payables, bill-wise: DATE, REF NO, VR NO,
    PARTICULARS, OP AMT, PND AMT, C-Day (days since the bill), Location; plus
    any unplaced receipt / payment as "On account" (an advance)."""
    rows = []
    sign = "Dr" if side == "receivable" else "Cr"
    for b in bills(session, side=side, upto=date_to):
        p = b.amount - _dec(session.scalar(select(func.sum(BillAllocation.amount)).where(
            BillAllocation.bill_kind == b.kind, BillAllocation.bill_no == b.no,
            BillAllocation.party_id == b.party_id, BillAllocation.alloc_date <= date_to)))
        if p <= 0:
            continue
        a = session.get(Account, b.party_id)
        days = (date_to - b.on).days if b.kind != "opening" else None
        rows.append({"date": b.on if b.kind != "opening" else None, "ref_no": b.ref,
                     "vrtype": vr_code(b.kind) if b.kind != "opening" else "OPN",
                     "vrno": b.no if b.kind != "opening" else "", "party": a.name if a else "",
                     "op_amt": b.amount, "pnd_amt": p.quantize(PAISA), "drcr": sign,
                     "c_day": days, "credit_days": b.credit_days or None,
                     "overdue": (days - b.credit_days) if days is not None and b.credit_days
                     and days > b.credit_days else None,
                     "location": b.location, "_party_id": b.party_id,
                     "_negative": bool(days is not None and b.credit_days and days > b.credit_days)})
    # Money received / paid that no bill took (advances).
    kinds = ("receipt",) if side == "receivable" else ("payment",)
    for v in session.scalars(select(AccountVoucher).where(AccountVoucher.vr_type.in_(kinds),
                                                          AccountVoucher.vr_date <= date_to)):
        used = _dec(session.scalar(select(func.sum(BillAllocation.amount)).where(
            BillAllocation.source_kind == v.vr_type, BillAllocation.source_no == v.vr_no)))
        left = _dec(v.amount) - used
        if left > 0 and v.account_id:
            a = session.get(Account, v.account_id)
            rows.append({"date": v.vr_date, "ref_no": "On account", "vrtype": vr_code(v.vr_type),
                         "vrno": v.vr_no, "party": a.name if a else "", "op_amt": _dec(v.amount),
                         "pnd_amt": -left, "drcr": "Cr" if side == "receivable" else "Dr",
                         "c_day": (date_to - v.vr_date).days, "credit_days": None,
                         "overdue": None, "location": "", "_party_id": v.account_id})
    rows.sort(key=lambda r: (r["party"].lower(), r["date"] or date(2000, 1, 1)))
    return rows


AGE_BUCKETS = [(0, 30, "0-30"), (31, 60, "31-60"), (61, 90, "61-90"), (91, 180, "91-180"),
               (181, 100000, "180+")]


def ageing(session: Session, date_from: date, date_to: date, *, side: str,
           monthly: bool = False) -> list[dict[str, Any]]:
    """O/S Day Wise (ageing buckets per party) or O/S Monthly (pending by the
    bill's month, per party)."""
    by_party: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for r in outstanding(session, date_from, date_to, side=side):
        if r["c_day"] is None and r["ref_no"] == "opening":
            col = "opening"
        elif monthly:
            col = r["date"].strftime("%Y-%m") if r["date"] else "opening"
        else:
            d = r["c_day"] or 0
            col = next(lbl for lo, hi, lbl in AGE_BUCKETS if lo <= d <= hi)
        by_party[r["party"]][col] += r["pnd_amt"]
        by_party[r["party"]]["total"] += r["pnd_amt"]
    return [{"party": p, **{k: v for k, v in cols.items()}} for p, cols in
            sorted(by_party.items(), key=lambda kv: kv[0].lower())]


def party_closing(session: Session, party_id: int | None) -> tuple[Decimal, str]:
    if not party_id:
        return ZERO, ""
    return drcr(balance(session, party_id))


# --------------------------------------------------------------------------
# Voucher Entry: Receipt / Payment / Journal / Contra (T-01, T-04)
# --------------------------------------------------------------------------
def next_vr_no(session: Session, vr_type: str) -> int:
    return (session.scalar(select(func.max(AccountVoucher.vr_no)).where(
        AccountVoucher.vr_type == vr_type)) or 0) + 1


def post_voucher(session: Session, vr_type: str, head: dict[str, Any],
                 lines: list[dict[str, Any]] | None = None,
                 allocations: dict[tuple[str, int], Any] | None = None, *,
                 user_id: int | None = None) -> AccountVoucher:
    """Save a Receipt / Payment (Cash, Bank or Metal) or a Journal / Contra."""
    from diagold.services import inventory as INV, production
    if vr_type not in ACC_TYPES or vr_type == "opening":
        raise ProductionError(f"Unknown voucher type {vr_type}.")
    on = head.get("vr_date") or date.today()
    v = AccountVoucher(vr_type=vr_type, vr_no=next_vr_no(session, vr_type), vr_date=on,
                       account_id=head.get("account_id"), mode=head.get("mode") or "Cash",
                       cash_account_id=head.get("cash_account_id"),
                       amount=_dec(head.get("amount")), metal_id=head.get("metal_id"),
                       location_id=head.get("location_id"), weight=_dec(head.get("weight")),
                       ref_no=head.get("ref_no") or "", narration=head.get("narration") or "",
                       user_id=user_id)
    session.add(v)
    session.flush()
    text = f"{ACC_TYPES[vr_type][1]} Vr {v.vr_no}" + (f" · {v.narration}" if v.narration else "")
    if vr_type in ("receipt", "payment"):
        if not v.account_id:
            raise ProductionError("Choose the party.")
        if v.mode == "Metal":
            if not (v.metal_id and v.location_id and _dec(v.weight) > 0):
                raise ProductionError("Metal receive / pay: choose the metal, the location and "
                                      "enter the weight.")
            v.fine_wt = INV.line_fine(session, v.metal_id, v.weight)
            v.metal_rate = production.metal_price(session, v.metal_id, on)
            if not _dec(v.amount):
                v.amount = (_dec(v.weight) * _dec(v.metal_rate)).quantize(PAISA)
            sign = 1 if vr_type == "receipt" else -1
            production.adjust_stock(
                session, v.location_id, "metal", v.metal_id, 0, sign * _dec(v.weight),
                kind="inward" if sign > 0 else "outward", mv_date=on, ref_kind=vr_type,
                ref_no=v.vr_no, account_id=v.account_id, fine_wt=sign * _dec(v.fine_wt),
                allow_negative=INV.negative_mode(session) != "block",
                value=sign * _dec(v.amount), remark="metal " + ("receive" if sign > 0 else "pay"))
            book = nominal(session, "Metal Stock A/c").id
        else:
            book = v.cash_account_id or nominal(session, "Cash" if v.mode == "Cash" else "Bank").id
            v.cash_account_id = book
        if _dec(v.amount) <= 0:
            raise ProductionError("Enter the amount.")
        if vr_type == "receipt":
            post(session, on=on, ref_kind=vr_type, ref_no=v.vr_no, narration=text, dr=book,
                 cr=v.account_id, amount=v.amount, mode=v.mode, fine=v.fine_wt)
            allocate(session, party_id=v.account_id, side="receivable", source_kind=vr_type,
                     source_no=v.vr_no, amount=v.amount, on=on, manual=allocations)
        else:
            post(session, on=on, ref_kind=vr_type, ref_no=v.vr_no, narration=text,
                 dr=v.account_id, cr=book, amount=v.amount, mode=v.mode, fine=v.fine_wt)
            allocate(session, party_id=v.account_id, side="payable", source_kind=vr_type,
                     source_no=v.vr_no, amount=v.amount, on=on, manual=allocations)
    else:
        lines = [l for l in (lines or []) if l.get("account_id") and (
            _dec(l.get("debit")) or _dec(l.get("credit")))]
        if len(lines) < 2:
            raise ProductionError("A journal needs at least two lines.")
        dr = sum((_dec(l.get("debit")) for l in lines), ZERO)
        cr = sum((_dec(l.get("credit")) for l in lines), ZERO)
        if dr != cr:
            raise ProductionError(f"Debit {dr:,.2f} and credit {cr:,.2f} must be equal.")
        if vr_type == "contra":
            cash_like = {"Cash-In-Hand", "Bank Account", "Bangkok bank saving a/c"}
            for l in lines:
                a = session.get(Account, l["account_id"])
                if a.group_name not in cash_like:
                    raise ProductionError(f"Contra is between cash and bank only - {a.name} is "
                                          f"in {a.group_name}.")
        for l in lines:
            a = session.get(Account, l["account_id"])
            session.add(AccountVoucherLine(voucher_id=v.id, account_id=a.id,
                                           debit=_dec(l.get("debit")), credit=_dec(l.get("credit")),
                                           narration=l.get("narration") or ""))
            side = "debit" if _dec(l.get("debit")) else "credit"
            session.add(AccountEntry(entry_date=on, account_id=a.id, ledger=a.name,
                                     ref_kind=vr_type, ref_no=v.vr_no,
                                     narration=l.get("narration") or text, mode="",
                                     **{side: _dec(l.get(side))}))
        v.amount = dr
    session.flush()
    session.refresh(v)
    return v


def delete_voucher(session: Session, v: AccountVoucher, *, user_id: int | None = None) -> None:
    from diagold.services import production
    image = {c.name: getattr(v, c.name) for c in v.__table__.columns}
    remove_postings(session, v.vr_type, v.vr_no)
    remove_allocations(session, v.vr_type, v.vr_no)
    for m in session.scalars(select(StockMovement).where(
            StockMovement.ref_kind == v.vr_type, StockMovement.ref_no == v.vr_no)).all():
        row = production.stock_row(session, m.location_id, m.material_class, m.ref_id,
                                   m.size, m.ref_text)
        if row is not None:
            row.pcs = int(row.pcs) - int(m.pcs)
            row.weight = (_dec(row.weight) - _dec(m.weight)).quantize(Decimal("0.0001"))
        session.delete(m)
    session.add(DeletionLog(user_id=user_id, kind=v.vr_type,
                            ref=f"{ACC_TYPES[v.vr_type][1]} Vr {v.vr_no}",
                            before_json=json.dumps(image, default=str)))
    session.delete(v)
    session.flush()


# --------------------------------------------------------------------------
# Cash flow (T-04)
# --------------------------------------------------------------------------
def cash_flow(session: Session, date_from: date, date_to: date, *,
              by_day: bool = False) -> list[dict[str, Any]]:
    """Every movement through Cash: cash sale, cash return, cash received,
    cash paid, contra - per party and day; or one summary row per day."""
    cash = nominal(session, "Cash")
    q = (select(AccountEntry).where(AccountEntry.account_id == cash.id,
                                    AccountEntry.entry_date >= date_from,
                                    AccountEntry.entry_date <= date_to)
         .order_by(AccountEntry.entry_date, AccountEntry.id))
    rows = []
    days: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for e in session.scalars(q):
        inflow, outflow = _dec(e.debit), _dec(e.credit)
        if e.ref_kind in ("rs_sale", "metal_sale", "stone_sale"):
            what = "Cash sale"
        elif e.ref_kind in ("rs_sale_return",):
            what = "Cash return"
        elif e.ref_kind == "receipt":
            what = "Cash received"
        elif e.ref_kind == "payment":
            what = "Cash paid"
        else:
            what = vr_title(e.ref_kind)
        party = _other_side(session, e)
        rows.append({"date": e.entry_date, "kind": what, "vrtype": vr_code(e.ref_kind),
                     "vrno": e.ref_no, "party": party, "cash_in": inflow or None,
                     "cash_out": outflow or None, "net": inflow - outflow})
        d = days[e.entry_date]
        d[what] += inflow - outflow
        d["net"] += inflow - outflow
    if not by_day:
        return rows
    return [{"date": d, "cash_sale": v.get("Cash sale"), "cash_return": v.get("Cash return"),
             "cash_received": v.get("Cash received"), "cash_paid": v.get("Cash paid"),
             "net": v.get("net")} for d, v in sorted(days.items())]
