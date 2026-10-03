"""Inventory ▸ Stock Transfer: location transfers and stock melting (2 Oct
Session 3 §4.6, T-06). See :mod:`diagold.db.models.transfer`.

Posting a voucher:
* Ready Stock Outward - the piece leaves ready stock ("melted").
* Metal / Stone - In adds to the line's location, Out takes from it (the
  Inventory block / warn / allow rule applies). Loss columns are recorded for
  the loss registers and do not move stock (UNCONFIRMED - 2 Oct Q6).
* Ready Stock Transfer - the piece moves to the To location.
Deleting the voucher undoes all of it.

A transfer between locations should balance - what goes out of one comes into
the other, less what was lost on the way; :func:`imbalance` says where it
does not, so the screen can ask before saving (the rule itself is UNCONFIRMED).
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (
    DeletionLog,
    Location,
    Metal,
    StockItem,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    StoneSku,
)
from diagold.services import production
from diagold.services.production import ProductionError

ZERO = Decimal("0")
D3 = Decimal("0.001")
REF = "stock_transfer"
PANES = ("ready_out", "metal", "stone", "ready_transfer")
_LINE_FIELDS = ("location_id", "to_location_id", "stock_item_id", "mt_type", "metal_id",
                "colour", "stone_sku_id", "particulars", "s_type", "size", "in_pcs", "in_wt",
                "in_loss_pcs", "in_loss_wt", "out_pcs", "out_wt", "out_loss_pcs",
                "out_loss_wt", "price", "unit", "amount", "job_no", "remark")


def _dec(v: Any) -> Decimal:
    if v is None or v == "":
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def next_vr_no(session: Session) -> int:
    return (session.scalar(select(func.max(StockTransfer.vr_no))) or 0) + 1


def line_amount(ln: dict[str, Any]) -> Decimal:
    """In (or Out) quantity x price: pieces when the price is per piece."""
    unit = (ln.get("unit") or "").lower()
    pcs = int(ln.get("in_pcs") or 0) or int(ln.get("out_pcs") or 0)
    wt = _dec(ln.get("in_wt")) or _dec(ln.get("out_wt"))
    qty = Decimal(pcs) if unit.startswith("pc") else wt
    return (qty * _dec(ln.get("price"))).quantize(Decimal("0.01"))


def imbalance(lines: list[dict[str, Any]]) -> list[str]:
    """Metal / stone items whose In does not equal Out less the losses on a
    voucher that moves no ready piece out (a melting brings stock in from a
    piece, so it is not expected to balance)."""
    if any(l.get("pane") == "ready_out" for l in lines):
        return []
    acc: dict[tuple, list[Decimal]] = {}
    for l in lines:
        if l.get("pane") not in ("metal", "stone"):
            continue
        key = (l["pane"], l.get("metal_id") or l.get("stone_sku_id") or l.get("particulars"),
               l.get("size") or "")
        a = acc.setdefault(key, [ZERO, ZERO, l.get("name") or str(key[1])])
        a[0] += _dec(l.get("in_wt")) + _dec(l.get("in_loss_wt"))
        a[1] += _dec(l.get("out_wt")) - _dec(l.get("out_loss_wt"))
    return [f"{name}: in {i} (with its loss) against out {o} (less its loss)"
            for (_p, _k, _s), (i, o, name) in acc.items() if i != o]


def _material(ln: StockTransferLine) -> tuple[str, int | None, str, str]:
    if ln.pane == "metal":
        return "metal", ln.metal_id, "", ""
    return "stone", ln.stone_sku_id, ln.size or "", "" if ln.stone_sku_id else (ln.particulars or "")


def post(session: Session, head: dict[str, Any], lines: list[dict[str, Any]], *,
         user_id: int | None = None) -> StockTransfer:
    from diagold.services import inventory as INV
    if not lines:
        raise ProductionError("Add at least one line to a pane.")
    t = StockTransfer(vr_no=next_vr_no(session), vr_date=head.get("vr_date") or date.today(),
                      contact_person=head.get("contact_person") or "",
                      ref_no=head.get("ref_no") or "", remark=head.get("remark") or "",
                      user_id=user_id)
    session.add(t)
    session.flush()
    mode = INV.negative_mode(session)
    for n, ln in enumerate(lines, start=1):
        pane = ln.get("pane")
        if pane not in PANES:
            raise ProductionError(f"Line {n}: unknown pane.")
        row = StockTransferLine(transfer_id=t.id, pane=pane,
                                **{k: ln[k] for k in _LINE_FIELDS if k in ln and ln[k] is not None})
        if pane in ("ready_out", "ready_transfer"):
            item = session.get(StockItem, ln.get("stock_item_id"))
            if item is None or item.status != "in_stock":
                raise ProductionError(f"Line {n}: Stock No "
                                      f"{item.stock_no if item else '?'} is not in stock.")
            row.prev_location_id = item.location_id
            if pane == "ready_out":
                item.status = "melted"
            else:
                if not ln.get("to_location_id"):
                    raise ProductionError(f"Line {n}: choose the location the piece goes to.")
                item.location_id = ln["to_location_id"]
        else:
            if not ln.get("location_id"):
                raise ProductionError(f"Line {n}: choose the location.")
            row.amount = row.amount or line_amount(ln)
        session.add(row)
        session.flush()
        if pane in ("metal", "stone"):
            mat, ref, size, text = _material(row)
            what = (session.get(Metal, ref).name if mat == "metal" and ref else
                    session.get(StoneSku, ref).sku_code if ref else text)
            for sign, pcs, wt in ((+1, row.in_pcs, row.in_wt), (-1, row.out_pcs, row.out_wt)):
                if not _dec(wt) and not int(pcs or 0):
                    continue
                fine = INV.line_fine(session, ref, wt) * sign if mat == "metal" else None
                production.adjust_stock(
                    session, row.location_id, mat, ref, sign * int(pcs or 0), sign * _dec(wt),
                    size=size, ref_text=text, what=what,
                    kind="transfer_in" if sign > 0 else "transfer_out", mv_date=t.vr_date,
                    ref_kind=REF, ref_no=t.vr_no, allow_negative=mode != "block",
                    fine_wt=fine, value=sign * _dec(row.amount) if _dec(row.amount) else None,
                    remark=row.remark or "")
    session.flush()
    session.refresh(t)
    return t


def delete(session: Session, t: StockTransfer, *, user_id: int | None = None) -> None:
    """Undo a stock transfer: pieces back in stock where they were, metal and
    stone movements reversed. Kept whole in the deletion log."""
    for ln in t.lines:
        if ln.pane in ("ready_out", "ready_transfer") and ln.stock_item_id:
            item = session.get(StockItem, ln.stock_item_id)
            want = "melted" if ln.pane == "ready_out" else "in_stock"
            if item is None or item.status != want or (
                    ln.pane == "ready_transfer" and item.location_id != ln.to_location_id):
                raise ProductionError(f"Stock No {item.stock_no if item else '?'} has moved on "
                                      f"since Stock Transfer Vr {t.vr_no} - undo that first.")
    image = {"transfer": {c.name: getattr(t, c.name) for c in t.__table__.columns},
             "lines": [{c.name: getattr(l, c.name) for c in l.__table__.columns} for l in t.lines]}
    for ln in t.lines:
        if ln.pane in ("ready_out", "ready_transfer") and ln.stock_item_id:
            item = session.get(StockItem, ln.stock_item_id)
            item.status = "in_stock"
            item.location_id = ln.prev_location_id
    for m in session.scalars(select(StockMovement).where(
            StockMovement.ref_kind == REF, StockMovement.ref_no == t.vr_no)).all():
        row = production.stock_row(session, m.location_id, m.material_class, m.ref_id,
                                   m.size, m.ref_text)
        if row is not None:
            row.pcs = int(row.pcs) - int(m.pcs)
            row.weight = (_dec(row.weight) - _dec(m.weight)).quantize(Decimal("0.0001"))
        session.delete(m)
    session.add(DeletionLog(user_id=user_id, kind=REF, ref=f"Stock Transfer Vr {t.vr_no}",
                            before_json=json.dumps(image, default=str)))
    session.delete(t)
    session.flush()


def melting_lines(session: Session, item: StockItem, on_date: date) -> list[dict[str, Any]]:
    """Stock Melting: a ready piece out, and its metal and stones in at the
    piece's location - metal at the day's rate, stones at their price."""
    from diagold.services import sales
    info = sales.describe(session, item)
    rate = production.metal_price(session, info["metal_id"], on_date)
    net = _dec(item.net_wt)
    out = [{"pane": "ready_out", "stock_item_id": item.id, "location_id": item.location_id,
            "name": f"Stock {item.stock_no} {info['sku']}", "stock_no": item.stock_no,
            "sku": info["sku"], "job_no": info["job_no"] or None, "metal": info["metal"],
            "colour": info["colour"], "size": info["size"], "out_pcs": item.pcs,
            "gross_wt": _dec(item.gross_wt), "out_wt": net, "price": _dec(item.cost),
            "amount": _dec(item.cost)}]
    if info["metal_id"] and net:
        out.append({"pane": "metal", "location_id": item.location_id, "mt_type": "Actual",
                    "metal_id": info["metal_id"], "name": info["metal"], "colour": info["colour"],
                    "in_pcs": 0, "in_wt": net, "price": rate, "unit": "Gms",
                    "amount": (net * rate).quantize(Decimal("0.01"))})
    for st in info["stones"]:
        label = st.get("label") or ""
        sku = session.scalar(select(StoneSku).where(StoneSku.sku_code == label))
        pcs, wt = int(st.get("pcs") or 0), _dec(st.get("weight"))
        out.append({"pane": "stone", "location_id": item.location_id,
                    "stone_sku_id": sku.id if sku else None,
                    "particulars": "" if sku else label, "name": label,
                    "s_type": st.get("s_type") or "", "size": (sku.size if sku else "") or "",
                    "in_pcs": pcs, "in_wt": wt, "price": _dec(st.get("price")),
                    "unit": "Pcs" if (st.get("unit") or "").lower().startswith("pc") else "Cts",
                    "amount": sales.stone_amount(st)})
    return out


def register(session: Session, date_from: date, date_to: date,
             panes: tuple[str, ...] = PANES) -> list[dict[str, Any]]:
    """Transfer Reg. (and the Melting List, ready_out only)."""
    rows = []
    q = (select(StockTransferLine, StockTransfer).join(StockTransfer)
         .where(StockTransfer.vr_date >= date_from, StockTransfer.vr_date <= date_to,
                StockTransferLine.pane.in_(panes))
         .order_by(StockTransfer.vr_date, StockTransfer.vr_no, StockTransferLine.id))
    for ln, t in session.execute(q):
        loc = session.get(Location, ln.location_id) if ln.location_id else None
        to = session.get(Location, ln.to_location_id) if ln.to_location_id else None
        item = session.get(StockItem, ln.stock_item_id) if ln.stock_item_id else None
        if ln.pane == "metal":
            m = session.get(Metal, ln.metal_id) if ln.metal_id else None
            name = m.name if m else ""
        elif ln.pane == "stone":
            k = session.get(StoneSku, ln.stone_sku_id) if ln.stone_sku_id else None
            name = (k.sku_code if k else ln.particulars) or ""
        else:
            from diagold.db.models import ProductSku
            sku = session.get(ProductSku, item.product_sku_id) if item and item.product_sku_id else None
            name = f"Stock {item.stock_no} {sku.sku_code if sku else ''}" if item else ""
        if ln.pane in ("ready_out", "ready_transfer") and item is not None:
            out_pcs, out_wt = item.pcs, _dec(item.net_wt)
        else:
            out_pcs, out_wt = ln.out_pcs, _dec(ln.out_wt)
        rows.append({"date": t.vr_date, "vrno": t.vr_no, "pane": {
            "ready_out": "Ready Stock Outward", "metal": "Metal", "stone": "Stone",
            "ready_transfer": "Ready Stock Transfer"}[ln.pane],
            "location": loc.name if loc else (session.get(Location, ln.prev_location_id).name
                                              if ln.prev_location_id else ""),
            "to_location": to.name if to else "", "item": name, "size": ln.size,
            "in_pcs": ln.in_pcs or None, "in_wt": _dec(ln.in_wt) or None,
            "in_loss_wt": _dec(ln.in_loss_wt) or None, "out_pcs": out_pcs or None,
            "out_wt": out_wt or None, "out_loss_wt": _dec(ln.out_loss_wt) or None,
            "price": _dec(ln.price) or None, "amount": _dec(ln.amount) or None,
            "contact": t.contact_person, "ref_no": t.ref_no})
    return rows


def stone_losses(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Stone lost on transfers - for the Stone Loss Register ("TR" rows)."""
    rows = []
    q = (select(StockTransferLine, StockTransfer).join(StockTransfer)
         .where(StockTransferLine.pane == "stone", StockTransfer.vr_date >= date_from,
                StockTransfer.vr_date <= date_to,
                (StockTransferLine.in_loss_wt > 0) | (StockTransferLine.out_loss_wt > 0)
                | (StockTransferLine.in_loss_pcs > 0) | (StockTransferLine.out_loss_pcs > 0)))
    for ln, t in session.execute(q):
        sku = session.get(StoneSku, ln.stone_sku_id) if ln.stone_sku_id else None
        loc = session.get(Location, ln.location_id) if ln.location_id else None
        pcs = int(ln.in_loss_pcs or 0) + int(ln.out_loss_pcs or 0)
        wt = _dec(ln.in_loss_wt) + _dec(ln.out_loss_wt)
        price = _dec(ln.price)
        unit = ln.unit or "Cts"
        rows.append({"date": t.vr_date, "vrno": t.vr_no, "kind": "Transfer loss",
                     "worker": t.contact_person, "process": "TR", "job_no": ln.job_no or "",
                     "location": loc.name if loc else "", "sku": "",
                     "ssku": sku.sku_code if sku else "", "stone": ln.particulars or
                     (sku.stone if sku else ""), "size": ln.size, "st_pcs": pcs, "weight": wt,
                     "price": price, "unit": unit,
                     "amount": production.stone_amount(price, unit, pcs, wt),
                     "s_type": ln.s_type, "ord_no": "", "ord_date": None, "ref_no": t.ref_no,
                     "ccode": ""})
    return rows
