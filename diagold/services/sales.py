"""Ready-stock vouchers - Sale, Sale Return, Approval, Approval Return, Ready
Repair Issue, Ready Items purchase / return and Opening Stock (2 Oct Session 3
§4.5, §4.9-4.11; T-04, T-07, T-09, T-10).

Every line is one barcoded piece (Stock No). A piece's state is on the stock
item - in_stock, sold, on_approval (with a party), in_repair (with a party),
returned (to the supplier) - and each voucher moves it from one state to the
next; deleting the voucher moves it back, so the state is always what the
vouchers say.

A piece is valued on a sale the way the legacy line reads (Vr 1225, NS-688):

    Metal Amount = N-Wt x Metal Rate (the day's rate for its metal)  10.991 x 8,944 = 98,303.50
    Stone Amount = sum(ct or pcs x price) of its stones               32,836.50
    Labour       = labour rate x N-Wt                                 1,200 x 10.991 = 13,189.20
    Total        = Metal + Stone + Setting + Labour + Other

Stones and labour rate come from where the piece came in - its MFG transfer
line or its Ready Items purchase line - so a piece sells with the stones it
was made with. Every amount is stored on the voucher line at save time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    Account,
    DeletionLog,
    Job,
    Location,
    Metal,
    MfgTransferLine,
    Order,
    OrderLine,
    ProductSku,
    ReadyVoucher,
    ReadyVoucherLine,
    StockItem,
)
from diagold.services import costing, mfg_pricing, production
from diagold.services.production import ProductionError, next_number

ZERO = Decimal("0")
PAISA = Decimal("0.01")
D3 = Decimal("0.001")
SALES_LEDGER = "Sales A/c"
SALES_RETURN_LEDGER = "Sales Return A/c"
PURCHASE_LEDGER = "Purchase A/c"
PURCHASE_RETURN_LEDGER = "Purchase Return A/c"


def _dec(v: Any) -> Decimal:
    if v is None or v == "":
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _money(v: Decimal) -> Decimal:
    return _dec(v).quantize(PAISA, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ReadyType:
    key: str
    title: str
    code: str                    # VrType as the registers print it
    party: str                   # customer / supplier / none
    takes: tuple[str, ...]       # states a piece may be in to go on it ("" = new piece)
    leaves: str                  # state it leaves the piece in
    same_party: bool = False     # the piece must be with / sold to this account


READY_TYPES: dict[str, ReadyType] = {t.key: t for t in (
    ReadyType("rs_sale", "Ready Stock Sale", "RS", "customer", ("in_stock", "on_approval"),
              "sold"),
    ReadyType("rs_sale_return", "Ready Stock Sale Return", "RSR", "customer", ("sold",),
              "in_stock", same_party=True),
    ReadyType("rs_approval", "Ready Stock Approval", "RA", "customer", ("in_stock",),
              "on_approval"),
    ReadyType("rs_approval_return", "Ready Stock Approval Return", "RAR", "customer",
              ("on_approval",), "in_stock", same_party=True),
    ReadyType("rs_repair_issue", "Ready Repair Issue", "RRI", "customer", ("in_stock",),
              "in_repair"),
    ReadyType("rp_purchase", "Ready Items Purchase", "RP", "supplier", ("",), "in_stock"),
    ReadyType("rp_return", "Ready Item Return", "RPR", "supplier", ("in_stock",), "returned"),
    ReadyType("rp_opening", "Opening Stock — Ready Items", "OPR", "none", ("",), "in_stock"),
)}
NEW_PIECES = ("rp_purchase", "rp_opening")
STATE_LABEL = {"in_stock": "in stock", "sold": "sold", "on_approval": "out on approval",
               "in_repair": "issued to repair", "returned": "returned to the supplier"}


def next_vr_no(session: Session, vr_type: str) -> int:
    n = session.scalar(select(func.max(ReadyVoucher.vr_no)).where(
        ReadyVoucher.vr_type == vr_type))
    return (n or 0) + 1


# --------------------------------------------------------------------------
# A piece: what it is, and what it sells for
# --------------------------------------------------------------------------
def _source(session: Session, item: StockItem) -> dict[str, Any]:
    """Stones, labour rate, setting and purity from where the piece came in,
    scaled to this piece when its job was split."""
    if item.line_id:
        line = session.get(MfgTransferLine, item.line_id)
        if line is not None:
            f = Decimal(item.pcs or 1) / Decimal(line.pcs or 1)
            stones = json.loads(line.stones_json or "[]")
            if f != 1:
                for st in stones:
                    st["pcs"] = int((Decimal(st.get("pcs") or 0) * f).to_integral_value())
                    st["weight"] = str((_dec(st.get("weight")) * f).quantize(D3))
            return {"stones": stones, "labour_rate": _dec(line.labour_rate),
                    "setting": _money(_dec(line.setting_amount) * f), "title": _dec(line.title),
                    "loss_pct": _dec(line.loss_pct)}
    if item.in_line_id:
        src = session.get(ReadyVoucherLine, item.in_line_id)
        if src is not None:
            return {"stones": json.loads(src.stones_json or "[]"),
                    "labour_rate": _dec(src.labour_rate), "setting": _dec(src.setting_amount),
                    "title": _dec(src.title), "loss_pct": _dec(src.loss_pct)}
    metal = session.get(Metal, item.metal_id) if item.metal_id else None
    return {"stones": [], "labour_rate": ZERO, "setting": ZERO,
            "title": mfg_pricing.title_of(metal), "loss_pct": ZERO}


def stone_amount(st: dict) -> Decimal:
    unit = (st.get("unit") or "ct").lower()
    qty = Decimal(int(st.get("pcs") or 0)) if unit.startswith("pc") else _dec(st.get("weight"))
    return _money(qty * _dec(st.get("price")))


def describe(session: Session, item: StockItem) -> dict[str, Any]:
    """Everything a voucher line shows about a piece, before it is valued."""
    job = session.get(Job, item.job_id) if item.job_id else None
    sku = session.get(ProductSku, item.product_sku_id) if item.product_sku_id else None
    metal_id = item.metal_id or (job.metal_id if job else None)
    metal = session.get(Metal, metal_id) if metal_id else None
    loc = session.get(Location, item.location_id) if item.location_id else None
    order = session.get(Order, job.order_id) if job and job.order_id else None
    src = _source(session, item)
    holder = session.get(Account, item.holder_account_id) if item.holder_account_id else None
    return {
        "stock_item_id": item.id, "stock_no": item.stock_no, "location_id": item.location_id,
        "location": loc.name if loc else "", "job_id": item.job_id,
        "job_no": job.job_no if job else "", "product_sku_id": item.product_sku_id,
        "sku": sku.sku_code if sku else "", "c_ref": item.c_ref or (job.c_ref if job else ""),
        "metal_id": metal_id, "metal": metal.name if metal else "", "title": src["title"],
        "loss_pct": src["loss_pct"], "colour": item.colour or (job.colour if job else ""),
        "size": item.size or (production._order_line_size(session, job) if job else ""),
        "pcs": item.pcs, "gross_wt": _dec(item.gross_wt), "net_wt": _dec(item.net_wt),
        "stones": src["stones"], "labour_rate": src["labour_rate"], "setting": src["setting"],
        "cost": _dec(item.cost), "price": _dec(item.price), "tag": item.tag_text,
        "status": item.status, "holder": holder.name if holder else "",
        "holder_id": item.holder_account_id, "ord_no": order.order_no if order else "",
        "photo": (sku.image_finished or sku.image_design) if sku else "",
    }


def value(info: dict[str, Any], on_date: date, session: Session, *,
          metal_rate: Any = None, labour_rate: Any = None) -> dict[str, Any]:
    """The line's amounts: metal at the day's rate (or the one typed), stones,
    setting, labour = rate x N-Wt, total."""
    rate = _dec(metal_rate) if metal_rate not in (None, "") else production.metal_price(
        session, info["metal_id"], on_date)
    net = _dec(info["net_wt"])
    title = _dec(info["title"])
    fine = (net * title / 1000).quantize(D3) if title else ZERO
    stones = info.get("stones") or []
    st_amt = sum((stone_amount(s) for s in stones), ZERO)
    st_wt = sum((_dec(s.get("weight")) for s in stones), ZERO)
    lab_rate = _dec(labour_rate) if labour_rate not in (None, "") else _dec(info["labour_rate"])
    labour = costing.labour_amount(lab_rate, net_weight=net) if lab_rate else ZERO
    metal_amount = _money(net * rate)
    setting = _dec(info.get("setting"))
    other = _dec(info.get("other_amount"))
    return {"metal_rate": _dec(rate), "metal_amount": metal_amount, "fine_wt": fine,
            "st_wt": st_wt, "stone_amount": st_amt, "setting_amount": setting,
            "labour_rate": lab_rate, "labour": labour, "other_amount": other,
            "total": _money(metal_amount + st_amt + setting + labour + other)}


def find_item(session: Session, text: str) -> StockItem:
    """A scanned barcode (Stock No). Anything else: "Item not found" (TR4)."""
    text = (text or "").strip()
    item = session.scalar(select(StockItem).where(StockItem.stock_no == int(text))) \
        if text.isdigit() else None
    if item is None:
        raise ProductionError(f"Item not found: {text}")
    return item


def check_piece(session: Session, vr_type: str, item: StockItem,
                account_id: int | None) -> None:
    """May this piece go on this voucher? Refuses with the reason."""
    t = READY_TYPES[vr_type]
    if item.status not in t.takes:
        raise ProductionError(f"Stock No {item.stock_no} is {STATE_LABEL.get(item.status, item.status)}"
                              f" - it cannot go on a {t.title}.")
    if item.status in ("on_approval", "in_repair") and item.holder_account_id \
            and item.holder_account_id != account_id:
        holder = session.get(Account, item.holder_account_id)
        raise ProductionError(f"Stock No {item.stock_no} is out on approval with "
                              f"{holder.name if holder else 'another party'} - it can only be "
                              "returned or sold to that party.")
    if t.same_party and vr_type == "rs_sale_return":
        sold_to = last_party(session, item, "rs_sale")
        if sold_to and sold_to != account_id:
            raise ProductionError(f"Stock No {item.stock_no} was sold to another party.")
    if vr_type == "rp_return" and item.source != "purchase":
        raise ProductionError(f"Stock No {item.stock_no} was not bought in - only a "
                              "purchased piece goes back to a supplier.")


def last_party(session: Session, item: StockItem, vr_type: str) -> int | None:
    v = session.scalars(select(ReadyVoucher).join(ReadyVoucherLine)
                        .where(ReadyVoucherLine.stock_item_id == item.id,
                               ReadyVoucher.vr_type == vr_type)
                        .order_by(ReadyVoucher.vr_date.desc(), ReadyVoucher.id.desc())).first()
    return v.account_id if v else None


def available(session: Session, vr_type: str, account_id: int | None = None,
              sku_text: str = "") -> list[dict[str, Any]]:
    """Pieces that may go on this voucher - Show Stock (in stock), Show App
    (on approval with the party), sold to the party (sale return)."""
    t = READY_TYPES[vr_type]
    q = select(StockItem).where(StockItem.status.in_([s for s in t.takes if s]))
    if sku_text:
        q = q.join(ProductSku, ProductSku.id == StockItem.product_sku_id).where(
            ProductSku.sku_code.ilike(f"%{sku_text}%"))
    out = []
    for item in session.scalars(q.order_by(StockItem.stock_no)):
        try:
            check_piece(session, vr_type, item, account_id)
        except ProductionError:
            continue
        out.append(describe(session, item))
    return out


# --------------------------------------------------------------------------
# From Order: the Pending Orders picker (2 Oct §4.9)
# --------------------------------------------------------------------------
def shipped_pcs(session: Session, order_line_id: int) -> int:
    sold = session.scalar(select(func.sum(ReadyVoucherLine.pcs)).join(ReadyVoucher).where(
        ReadyVoucherLine.order_line_id == order_line_id,
        ReadyVoucher.vr_type == "rs_sale")) or 0
    back = session.scalar(select(func.sum(ReadyVoucherLine.pcs)).join(ReadyVoucher).where(
        ReadyVoucherLine.order_line_id == order_line_id,
        ReadyVoucher.vr_type == "rs_sale_return")) or 0
    return int(sold) - int(back)


def _stock_for_line(session: Session, ol: OrderLine, own_only: bool = False) -> list[StockItem]:
    """In-stock pieces for an order line: those made on its own jobs first,
    then (unless ``own_only``) any piece of the same SKU."""
    own = select(StockItem).join(Job, Job.id == StockItem.job_id).where(
        StockItem.status == "in_stock", Job.order_id == ol.order_id,
        Job.line_sno == ol.sno)
    mine = list(session.scalars(own.order_by(StockItem.stock_no)))
    seen = {i.id for i in mine}
    if ol.product_sku_id and not own_only:
        for i in session.scalars(select(StockItem).where(
                StockItem.status == "in_stock",
                StockItem.product_sku_id == ol.product_sku_id).order_by(StockItem.stock_no)):
            if i.id not in seen:
                mine.append(i)
    return mine


def pending_orders(session: Session, account_id: int | None,
                   on_invoice: dict[int, int] | None = None) -> list[dict[str, Any]]:
    """Order lines of this customer with pieces still to ship: Ord Pcs,
    Cancel Pcs, Shipped Pcs, Bal Pcs, Stock Pcs, Inv Pcs (on this invoice
    already), Price."""
    on_invoice = on_invoice or {}
    rows = []
    # A repair order's lines are the customer's own pieces, not goods to ship.
    q = select(OrderLine, Order).join(Order).where(Order.is_repair.is_(False)).order_by(
        Order.order_no, OrderLine.sno)
    if account_id:
        q = q.where(Order.account_id == account_id)
    for ol, o in session.execute(q):
        shipped = shipped_pcs(session, ol.id)
        bal = int(ol.pcs or 0) - shipped
        if bal <= 0:
            continue
        sku = session.get(ProductSku, ol.product_sku_id) if ol.product_sku_id else None
        stock = len(_stock_for_line(session, ol))
        rows.append({"order_line_id": ol.id, "ord_no": o.order_no, "ref_no": o.ref,
                     "sku": sku.sku_code if sku else ol.sku_desc, "c_ref": ol.c_ref,
                     "ord_pcs": int(ol.pcs or 0), "cancel_pcs": 0, "shipped_pcs": shipped,
                     "bal_pcs": bal, "stock_pcs": stock, "inv_pcs": on_invoice.get(ol.id, 0),
                     "price": _dec(sku.tag_price) if sku else ZERO})
    return rows


def pieces_for_orders(session: Session, takes: dict[int, int],
                      exclude: set[int] = frozenset()) -> dict[int, list[StockItem]]:
    """Pieces for several order lines at once ({order line: pcs}): first each
    line's own pieces (made on its jobs), then the same SKU from stock - so
    one line never takes the piece another line's own job made."""
    used = set(exclude)
    out: dict[int, list[StockItem]] = {k: [] for k in takes}
    for own_only in (True, False):
        for ol_id, n in takes.items():
            need = n - len(out[ol_id])
            if need <= 0:
                continue
            ol = session.get(OrderLine, ol_id)
            for i in _stock_for_line(session, ol, own_only=own_only):
                if i.id in used:
                    continue
                out[ol_id].append(i)
                used.add(i.id)
                need -= 1
                if need == 0:
                    break
    return out


# --------------------------------------------------------------------------
# Posting
# --------------------------------------------------------------------------
_HEAD_FIELDS = ("vr_date", "vr_time", "account_id", "ref_no", "currency_code", "credit_days",
                "salesperson", "bank_name", "margin_type", "bill_date", "bill_no",
                "bill_account_id", "bill_amount", "remark")
_LINE_FIELDS = ("location_id", "job_id", "product_sku_id", "c_ref", "metal_id", "title",
                "loss_pct", "colour", "size", "pcs", "old_wt", "gross_wt", "net_wt", "fine_wt",
                "metal_rate", "metal_amount", "st_wt", "stone_amount", "setting_amount",
                "labour_rate", "labour", "other_amount", "total", "order_line_id",
                "source_line_id", "remark")


def _accounts(session: Session, v: ReadyVoucher) -> None:
    from diagold.services import inventory as INV
    t = READY_TYPES[v.vr_type]
    text = f"{t.title} Vr {v.vr_no}" + (f" · Ref {v.ref_no}" if v.ref_no else "")
    total = _dec(v.total)
    common = dict(on=v.vr_date, amount=total, ref_kind=v.vr_type, ref_no=v.vr_no,
                  narration=text)
    if v.vr_type == "rs_sale":
        INV.post_entry(session, debit_account_id=v.account_id, credit_ledger=SALES_LEDGER,
                       **common)
    elif v.vr_type == "rs_sale_return":
        INV.post_entry(session, debit_ledger=SALES_RETURN_LEDGER, credit_account_id=v.account_id,
                       **common)
    elif v.vr_type == "rp_purchase":
        INV.post_entry(session, debit_ledger=PURCHASE_LEDGER, credit_account_id=v.account_id,
                       **common)
    elif v.vr_type == "rp_return":
        INV.post_entry(session, debit_account_id=v.account_id,
                       credit_ledger=PURCHASE_RETURN_LEDGER, **common)


def post_ready(session: Session, vr_type: str, head: dict[str, Any],
               lines: list[dict[str, Any]], *, user_id: int | None = None) -> ReadyVoucher:
    """Save a ready-stock voucher. For a sale / approval / return / repair
    issue each line names a piece (``stock_item_id``); for a Ready Items
    purchase or Opening Stock each line describes a new piece, which gets
    its Stock No here."""
    t = READY_TYPES[vr_type]
    if not lines:
        raise ProductionError("Add at least one piece.")
    if t.party != "none" and not head.get("account_id"):
        raise ProductionError("Choose the " + ("customer." if t.party == "customer"
                                               else "supplier."))
    v = ReadyVoucher(vr_type=vr_type, vr_no=next_vr_no(session, vr_type), user_id=user_id,
                     **{k: head[k] for k in _HEAD_FIELDS if k in head and head[k] is not None})
    v.vr_date = head.get("vr_date") or date.today()
    if v.credit_days:
        v.due_date = v.vr_date + timedelta(days=int(v.credit_days))
    session.add(v)
    session.flush()
    seen: set[int] = set()
    total = ZERO
    for sno, ln in enumerate(lines, start=1):
        row = ReadyVoucherLine(voucher_id=v.id, sno=sno,
                               stones_json=json.dumps(ln.get("stones") or [], default=str),
                               **{k: ln[k] for k in _LINE_FIELDS if k in ln
                                  and ln[k] is not None})
        if vr_type in NEW_PIECES:
            if not ln.get("product_sku_id") and not ln.get("c_ref"):
                raise ProductionError(f"Line {sno}: choose the SKU.")
            if _dec(ln.get("gross_wt")) <= 0:
                raise ProductionError(f"Line {sno}: enter the gross weight.")
            session.add(row)
            session.flush()
            item = StockItem(
                stock_no=next_number(session, StockItem.stock_no), job_id=None, line_id=None,
                product_sku_id=ln.get("product_sku_id"), location_id=ln.get("location_id"),
                pcs=int(ln.get("pcs") or 1), gross_wt=_dec(ln.get("gross_wt")),
                net_wt=_dec(ln.get("net_wt")), cost=_dec(ln.get("total")),
                price=_dec(ln.get("price") or ln.get("total")),
                tag_price=_dec(ln.get("price") or ln.get("total")),
                tag_text=mfg_pricing.tag_display(ln.get("price") or ln.get("total")),
                cert_no=(ln.get("cert_no") or "")[:40], huid=(ln.get("huid") or "")[:16],
                source="purchase" if vr_type == "rp_purchase" else "opening",
                in_line_id=row.id, metal_id=ln.get("metal_id"), colour=ln.get("colour") or "",
                size=ln.get("size") or "", c_ref=ln.get("c_ref") or "")
            session.add(item)
            session.flush()
            row.stock_item_id = item.id
        else:
            item = session.get(StockItem, ln.get("stock_item_id"))
            if item is None:
                raise ProductionError(f"Line {sno}: that piece no longer exists.")
            if item.id in seen:
                raise ProductionError(f"Stock No {item.stock_no} is on this voucher twice.")
            seen.add(item.id)
            check_piece(session, vr_type, item, v.account_id)
            row.stock_item_id = item.id
            if vr_type == "rs_sale" and item.status == "on_approval":
                # Read Barcode From Approval: the approval line it closes.
                row.source_line_id = row.source_line_id or _open_line(
                    session, item, "rs_approval")
            item.status = t.leaves
            item.holder_account_id = v.account_id if t.leaves in ("on_approval",
                                                                    "in_repair") else None
            session.add(row)
        total += _dec(ln.get("total"))
    v.total = _money(total)
    session.flush()
    _accounts(session, v)
    session.refresh(v)
    return v


def _open_line(session: Session, item: StockItem, vr_type: str) -> int | None:
    line = session.scalars(select(ReadyVoucherLine).join(ReadyVoucher).where(
        ReadyVoucherLine.stock_item_id == item.id, ReadyVoucher.vr_type == vr_type)
        .order_by(ReadyVoucherLine.id.desc())).first()
    return line.id if line else None


def _state_before(session: Session, v: ReadyVoucher, line: ReadyVoucherLine) -> tuple[str, int | None]:
    """What a piece was before this voucher moved it."""
    t = v.vr_type
    if t in ("rs_sale",):
        if line.source_line_id:
            src = session.get(ReadyVoucherLine, line.source_line_id)
            sv = src.voucher if src else None
            return "on_approval", sv.account_id if sv else v.account_id
        return "in_stock", None
    if t == "rs_sale_return":
        return "sold", None
    if t == "rs_approval_return":
        return "on_approval", v.account_id
    return "in_stock", None


def delete_ready(session: Session, v: ReadyVoucher, *, user_id: int | None = None,
                 reason: str = "") -> None:
    """Undo a voucher: every piece goes back to the state it was in (a new
    piece from a purchase / opening is removed), and its accounting goes.
    Refused if a piece has moved on since."""
    from diagold.services import inventory as INV
    t = READY_TYPES[v.vr_type]
    for line in v.lines:
        item = session.get(StockItem, line.stock_item_id) if line.stock_item_id else None
        if item is None:
            continue
        if item.status != t.leaves or (t.leaves in ("on_approval", "in_repair")
                                       and item.holder_account_id != v.account_id):
            raise ProductionError(
                f"Stock No {item.stock_no} has moved on since {t.title} Vr {v.vr_no} "
                f"(now {STATE_LABEL.get(item.status, item.status)}) - undo that first.")
        later = session.scalar(select(ReadyVoucherLine.id).join(ReadyVoucher).where(
            ReadyVoucherLine.stock_item_id == item.id, ReadyVoucherLine.id > line.id))
        if later:
            raise ProductionError(f"Stock No {item.stock_no} is on a later voucher - "
                                  "delete that first.")
    image = {"voucher": {c.name: getattr(v, c.name) for c in v.__table__.columns},
             "lines": [{c.name: getattr(l, c.name) for c in l.__table__.columns}
                       for l in v.lines]}
    for line in list(v.lines):
        item = session.get(StockItem, line.stock_item_id) if line.stock_item_id else None
        if item is None:
            continue
        if v.vr_type in NEW_PIECES:
            line.stock_item_id = None
            session.flush()
            session.delete(item)
        else:
            item.status, item.holder_account_id = _state_before(session, v, line)
    INV.remove_entries(session, v.vr_type, v.vr_no)
    session.add(DeletionLog(user_id=user_id, kind=v.vr_type,
                            ref=f"{t.title} Vr {v.vr_no}"[:64], reason=reason,
                            before_json=json.dumps(image, default=str)))
    session.delete(v)
    session.flush()


def update_ready(session: Session, v: ReadyVoucher, head: dict[str, Any],
                 lines: dict[int, dict[str, Any]], *, user_id: int | None = None) -> ReadyVoucher:
    """Edit a saved voucher: header fields and each line's rates / amounts
    (which pieces are on it changes only by delete and redo). The accounting
    is posted again for the new total."""
    from diagold.services import inventory as INV
    before = {"voucher": {c.name: getattr(v, c.name) for c in v.__table__.columns},
              "lines": [{c.name: getattr(l, c.name) for c in l.__table__.columns}
                        for l in v.lines]}
    for k in _HEAD_FIELDS:
        if k in head and k != "account_id":
            setattr(v, k, head[k])
    v.due_date = v.vr_date + timedelta(days=int(v.credit_days)) if v.credit_days else None
    total = ZERO
    for line in v.lines:
        ch = lines.get(line.id) or {}
        for k in ("metal_rate", "metal_amount", "stone_amount", "setting_amount", "labour_rate",
                  "labour", "other_amount", "total", "old_wt", "remark"):
            if k in ch:
                setattr(line, k, ch[k])
        if "stones" in ch:
            line.stones_json = json.dumps(ch["stones"], default=str)
        total += _dec(line.total)
    v.total = _money(total)
    INV.remove_entries(session, v.vr_type, v.vr_no)
    _accounts(session, v)
    session.add(DeletionLog(user_id=user_id, kind=v.vr_type + "_edit",
                            ref=f"{READY_TYPES[v.vr_type].title} Vr {v.vr_no}"[:64],
                            reason="edited", before_json=json.dumps(before, default=str)))
    session.flush()
    return v


# --------------------------------------------------------------------------
# Excel invoice - the client's breakup layout (2 Oct §4.9, TR6)
# --------------------------------------------------------------------------
def stone_block(st: dict) -> str:
    g = (st.get("s_type") or st.get("group") or "").upper()
    label = (st.get("label") or "").upper()
    if "DIA" in g or (not g and "DIA" in label):
        return "DIAMOND"
    if "POL" in g or (not g and "POLKI" in label):
        return "POLKI"
    return "COLOR STONE"


def excel_invoice(session: Session, v: ReadyVoucher, path: str) -> None:
    """Invoice in the client's Excel breakup format: per piece the metal,
    then Diamond / Polki / Colour Stone blocks side by side, labour and the
    piece total - every amount a live formula; the note on the metal rate at
    the foot."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    acct = session.get(Account, v.account_id) if v.account_id else None
    wb = Workbook()
    ws = wb.active
    ws.title = f"Invoice {v.vr_no}"
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="E4E7EC")
    thin = Side(style="thin", color="B0B7C3")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.append(["Invoice No", v.vr_no, "Date", v.vr_date.strftime("%d-%m-%Y"), "Client",
               acct.name if acct else "", "CURR", v.currency_code or "RS", "Exc Rate", 1])
    for c in ws[1]:
        c.font = bold
    # columns
    piece = ["Sno", "Image", "SKU", "GrossWt", "Metal", "NetWt", "FineWt", "Mt Price",
             "Mt Amount"]
    blocks = [("DIAMOND", ["Type", "Pcs", "Cts", "Price", "Amount"]),
              ("POLKI", ["Size", "Pcs", "Cts", "Price", "Amount"]),
              ("COLOR STONE", ["Name", "Pcs", "Cts", "Price", "Amount"])]
    tail = ["Labour Price", "Labour", "Setting / Other", "TOTAL"]
    heads = piece + [h for _b, hs in blocks for h in hs] + tail
    start = {}
    col = len(piece) + 1
    for name, hs in blocks:
        start[name] = col
        col += len(hs)
    t0 = col
    # group header row (merged) + column header row
    ws.append([])
    ws.append(heads)
    gr, hr = 2, 3
    ws.cell(gr, 1, "PIECE")
    ws.merge_cells(start_row=gr, start_column=1, end_row=gr, end_column=len(piece))
    for name, hs in blocks:
        ws.cell(gr, start[name], name)
        ws.merge_cells(start_row=gr, start_column=start[name], end_row=gr,
                       end_column=start[name] + len(hs) - 1)
    ws.cell(gr, t0, "LABOUR / TOTAL")
    ws.merge_cells(start_row=gr, start_column=t0, end_row=gr, end_column=t0 + len(tail) - 1)
    for r in (gr, hr):
        for c in ws[r]:
            c.font = bold
            c.fill = fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = box
    total_cells = []
    row = hr + 1
    for line in v.lines:
        item = session.get(StockItem, line.stock_item_id) if line.stock_item_id else None
        sku = session.get(ProductSku, line.product_sku_id) if line.product_sku_id else None
        metal = session.get(Metal, line.metal_id) if line.metal_id else None
        stones = json.loads(line.stones_json or "[]")
        by = {name: [s for s in stones if stone_block(s) == name] for name, _h in blocks}
        n = max([1] + [len(x) for x in by.values()])
        r0, r1 = row, row + n - 1
        ws.cell(r0, 1, line.sno)
        ws.cell(r0, 3, f"{sku.sku_code if sku else ''}\nStock {item.stock_no if item else ''}")
        ws.cell(r0, 3).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r0, 4, float(_dec(line.gross_wt)))
        ws.cell(r0, 5, metal.name if metal else "")
        ws.cell(r0, 6, float(_dec(line.net_wt)))
        ws.cell(r0, 7, float(_dec(line.fine_wt)))
        ws.cell(r0, 8, float(_dec(line.metal_rate)))
        ws.cell(r0, 9, f"=ROUND({L(6)}{r0}*{L(8)}{r0},2)")
        amount_refs = [f"{L(9)}{r0}"]
        for name, _hs in blocks:
            c0 = start[name]
            for i, st in enumerate(by[name]):
                rr = r0 + i
                label = st.get("size") if name == "POLKI" and st.get("size") else st.get("label")
                ws.cell(rr, c0, label or "")
                ws.cell(rr, c0 + 1, int(st.get("pcs") or 0))
                ws.cell(rr, c0 + 2, float(_dec(st.get("weight"))))
                ws.cell(rr, c0 + 3, float(_dec(st.get("price"))))
                qty = L(c0 + 1) if (st.get("unit") or "ct").lower().startswith("pc") else L(c0 + 2)
                ws.cell(rr, c0 + 4, f"=ROUND({qty}{rr}*{L(c0 + 3)}{rr},2)")
            if by[name]:
                amount_refs.append(f"SUM({L(c0 + 4)}{r0}:{L(c0 + 4)}{r1})")
        ws.cell(r0, t0, float(_dec(line.labour_rate)))
        ws.cell(r0, t0 + 1, f"=ROUND({L(t0)}{r0}*{L(6)}{r0},2)")
        ws.cell(r0, t0 + 2, float(_dec(line.setting_amount) + _dec(line.other_amount)))
        amount_refs += [f"{L(t0 + 1)}{r0}", f"{L(t0 + 2)}{r0}"]
        ws.cell(r0, t0 + 3, "=" + "+".join(amount_refs))
        ws.cell(r0, t0 + 3).font = bold
        total_cells.append(f"{L(t0 + 3)}{r0}")
        # product image, when the file is there and Pillow can read it
        photo = (sku.image_finished or sku.image_design) if sku else ""
        if photo:
            try:
                from openpyxl.drawing.image import Image as XLImage
                img = XLImage(photo)
                img.width, img.height = 70, 70
                ws.add_image(img, f"{L(2)}{r0}")
                ws.row_dimensions[r0].height = max(ws.row_dimensions[r0].height or 15, 56)
            except Exception:  # noqa: BLE001 - no Pillow / unreadable image: no picture
                pass
        for rr in range(r0, r1 + 1):
            for c in range(1, t0 + len(tail)):
                ws.cell(rr, c).border = box
        row = r1 + 1
    ws.cell(row, t0 + 2, "Grand Total").font = bold
    ws.cell(row, t0 + 3, "=" + "+".join(total_cells) if total_cells else 0).font = bold
    ws.cell(row + 2, 1, "NOTE: Metal Rate Will Be Charged as on Date of Payment").font = bold
    for c in range(1, t0 + len(tail)):
        ws.column_dimensions[L(c)].width = 11
    ws.column_dimensions[L(3)].width = 16
    ws.column_dimensions[L(2)].width = 11
    for name, _hs in blocks:
        ws.column_dimensions[L(start[name])].width = 18
    for r in ws.iter_rows(min_row=hr + 1, max_row=row):
        for c in r:
            if isinstance(c.value, float) or (isinstance(c.value, str) and c.value.startswith("=")):
                c.number_format = "#,##0.00" if c.column not in (4, 6, 7) else "#,##0.000"
    ws.freeze_panes = ws.cell(hr + 1, 4)
    wb.save(path)


# --------------------------------------------------------------------------
# Sale reports (2 Oct §4.10 R15, T-09)
# --------------------------------------------------------------------------
def _groups(line: ReadyVoucherLine) -> dict[str, Decimal]:
    out = {"DIAMOND": ZERO, "POLKI": ZERO, "COLOR STONE": ZERO}
    for st in json.loads(line.stones_json or "[]"):
        out[stone_block(st)] += stone_amount(st)
    return out


def _line_row(session: Session, v: ReadyVoucher, l: ReadyVoucherLine) -> dict[str, Any]:
    acct = session.get(Account, v.account_id) if v.account_id else None
    item = session.get(StockItem, l.stock_item_id) if l.stock_item_id else None
    sku = session.get(ProductSku, l.product_sku_id) if l.product_sku_id else None
    metal = session.get(Metal, l.metal_id) if l.metal_id else None
    loc = session.get(Location, l.location_id) if l.location_id else None
    g = _groups(l)
    return {"date": v.vr_date, "vrno": v.vr_no, "vrtype": READY_TYPES[v.vr_type].code,
            "particulars": acct.name if acct else "", "ref_no": v.ref_no,
            "location": loc.name if loc else "", "barcode": item.stock_no if item else "",
            "sku": sku.sku_code if sku else "", "metal": metal.name if metal else "",
            "col": l.colour, "pcs": l.pcs, "g_wt": _dec(l.gross_wt), "n_wt": _dec(l.net_wt),
            "fine_wt": _dec(l.fine_wt), "metal_amount": _dec(l.metal_amount),
            "dia": g["DIAMOND"], "polki": g["POLKI"], "cs": g["COLOR STONE"],
            "stone_amount": _dec(l.stone_amount), "labour": _dec(l.labour),
            "price": _dec(l.total), "_job_id": l.job_id}


def ready_register(session: Session, date_from: date, date_to: date,
                   types: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = []
    q = (select(ReadyVoucher).where(ReadyVoucher.vr_type.in_(types),
                                    ReadyVoucher.vr_date >= date_from,
                                    ReadyVoucher.vr_date <= date_to)
         .order_by(ReadyVoucher.vr_date, ReadyVoucher.vr_no))
    for v in session.scalars(q):
        for l in v.lines:
            rows.append(_line_row(session, v, l))
    return rows


def approval_balance(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Ready Stock Approval Balance: pieces out on approval now - with whom,
    since when, for how many days."""
    rows = []
    for item in session.scalars(select(StockItem).where(StockItem.status == "on_approval")
                                .order_by(StockItem.stock_no)):
        line = session.scalars(select(ReadyVoucherLine).join(ReadyVoucher).where(
            ReadyVoucherLine.stock_item_id == item.id, ReadyVoucher.vr_type == "rs_approval")
            .order_by(ReadyVoucherLine.id.desc())).first()
        if line is None or line.voucher.vr_date > date_to:
            continue
        r = _line_row(session, line.voucher, line)
        r["days"] = (date_to - line.voucher.vr_date).days
        rows.append(r)
    return rows


def approval_analysis(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Ready Stock Approval Analysis: every piece sent on approval in the
    period, and what became of it - returned (weights back), sold, or still
    out (balance = out - returned - sold)."""
    rows = []
    q = (select(ReadyVoucher).where(ReadyVoucher.vr_type == "rs_approval",
                                    ReadyVoucher.vr_date >= date_from,
                                    ReadyVoucher.vr_date <= date_to)
         .order_by(ReadyVoucher.vr_date, ReadyVoucher.vr_no))
    for v in session.scalars(q):
        for l in v.lines:
            r = _line_row(session, v, l)
            ret = session.scalars(select(ReadyVoucherLine).join(ReadyVoucher).where(
                ReadyVoucherLine.stock_item_id == l.stock_item_id,
                ReadyVoucher.vr_type == "rs_approval_return",
                ReadyVoucherLine.id > l.id).order_by(ReadyVoucherLine.id)).first()
            sold = session.scalars(select(ReadyVoucherLine).join(ReadyVoucher).where(
                ReadyVoucherLine.stock_item_id == l.stock_item_id,
                ReadyVoucher.vr_type == "rs_sale", ReadyVoucherLine.id > l.id)
                .order_by(ReadyVoucherLine.id)).first()
            first = min([x for x in (ret, sold) if x], key=lambda x: x.id, default=None)
            if first is ret and ret is not None:
                r.update(status="Returned", ret_g=_dec(ret.gross_wt), ret_n=_dec(ret.net_wt),
                         ret_fine=_dec(ret.fine_wt), on=ret.voucher.vr_date)
            elif first is sold and sold is not None:
                r.update(status="Sold", on=sold.voucher.vr_date)
            else:
                r.update(status="Out")
            rows.append(r)
    return rows


def repair_register(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Repair Register (2 Oct §4.11, T-10): every Ready Repair Issue - the
    piece, the party, and whether it is still out for repair."""
    rows = []
    for r in ready_register(session, date_from, date_to, ("rs_repair_issue",)):
        item = session.scalar(select(StockItem).where(StockItem.stock_no == r["barcode"])) \
            if r["barcode"] != "" else None
        r["status"] = ("Out for repair" if item is not None and item.status == "in_repair"
                       else STATE_LABEL.get(item.status, item.status).capitalize()
                       if item is not None else "")
        r["days"] = (date_to - r["date"]).days if r["status"] == "Out for repair" else None
        rows.append(r)
    return rows



# --------------------------------------------------------------------------
# Repair order: Repair List (2 Oct §4.11, T-10)
# --------------------------------------------------------------------------
def repair_stock(session: Session) -> list[dict[str, Any]]:
    """The Repair Stock picker: pieces in stock or already out for repair."""
    q = select(StockItem).where(StockItem.status.in_(("in_stock", "in_repair"))).order_by(
        StockItem.stock_no)
    return [describe(session, i) for i in session.scalars(q)]


def attach_repair_pieces(session: Session, order: Order, item_ids: list[int],
                         on_date: date | None = None) -> int:
    """Add the picked pieces to a repair order as its lines - SKU, C-Ref,
    metal, colour, size, pcs, weights and the metal amount at the day's rate
    - and allot their jobs. Returns how many were added."""
    if not order.is_repair:
        raise ProductionError(f"Order {order.order_no} is not ticked Repair.")
    have = {l.stock_item_id for l in order.lines if l.stock_item_id}
    sno = max([l.sno for l in order.lines], default=0)
    n = 0
    for iid in item_ids:
        if iid in have:
            continue
        item = session.get(StockItem, iid)
        info = describe(session, item)
        rate = production.metal_price(session, info["metal_id"], on_date or date.today())
        pcs = max(int(item.pcs or 1), 1)
        sno += 1
        session.add(OrderLine(
            order_id=order.id, sno=sno, product_sku_id=item.product_sku_id,
            sku_desc=info["sku"], c_ref=info["c_ref"], metal_id=info["metal_id"],
            colour=info["colour"], size=info["size"], pcs=pcs,
            net_wt_per_pcs=(_dec(item.net_wt) / pcs).quantize(D3),
            tot_gross_wt=_dec(item.gross_wt), metal_rate_unit=f"{rate}",
            metal_amount=_money(_dec(item.net_wt) * rate), stock_item_id=item.id,
            remark=f"Repair of Stock No {item.stock_no}"))
        n += 1
    session.flush()
    session.refresh(order)
    production.sync_jobs_for_order(session, order)
    return n
