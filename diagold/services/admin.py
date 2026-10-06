"""Admin utilities (5 Oct §4.13 / §4.14, T-11).

* Correction utilities - Update Job Card Metal / C-Ref, Update Job Card /
  Order Pcs, Update Job Card SKU, Add Pcs in Job Card, Update SSKU Price in
  Ready Stock (preview, then apply), Delete item history (with "delete SKU
  also"). Each writes an AuditLog row: who, when, before / after, reason.
* Declarations - up to six lines per document type, printed at its foot.
* Print layouts - Packing List / Sale Invoice (client vs default) and MFG
  Transfer; each client picks its layouts in the Account master.
* Masters Excel - every master list in one workbook.
* Backup - a dated copy of the database file.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from diagold.db.models import (Account, AuditLog, Colour, FamilyCategory, Job, Metal,
                               MfgTransferLine, OrderLine, ProductSku, ReadyVoucherLine,
                               StockItem, StoneGroup, StoneInfo, StoneKind, StoneQuality,
                               StoneShape, StoneSku)
from diagold.db.models.sku import Item
from diagold.services import settings
from diagold.services.production import ProductionError

ZERO = Decimal("0")


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _need_reason(reason: str) -> None:
    if not (reason or "").strip():
        raise ProductionError("Give the reason for the correction - it is kept in the audit "
                              "log.")


def audit(session: Session, kind: str, ref: str, before: dict, after: dict, reason: str,
          user: Any = None) -> AuditLog:
    _need_reason(reason)
    row = AuditLog(kind=kind, ref=ref[:80], reason=reason.strip()[:200],
                   user_id=getattr(user, "id", None),
                   user_name=getattr(user, "full_name", "") or getattr(user, "username", "")
                   or "",
                   before_json=json.dumps(before, default=str),
                   after_json=json.dumps(after, default=str))
    session.add(row)
    session.flush()
    return row


def audit_rows(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    q = select(AuditLog).where(func.date(AuditLog.at) >= date_from.isoformat(),
                               func.date(AuditLog.at) <= date_to.isoformat()
                               ).order_by(AuditLog.at.desc())
    return [{"at": a.at.strftime("%d-%m-%Y %H:%M"), "user": a.user_name, "kind": a.kind,
             "ref": a.ref, "reason": a.reason,
             "before": ", ".join(f"{k}: {v}" for k, v in json.loads(a.before_json).items()),
             "after": ", ".join(f"{k}: {v}" for k, v in json.loads(a.after_json).items())}
            for a in session.scalars(q)]


# --------------------------------------------------------------------------
# Job card corrections
# --------------------------------------------------------------------------
def find_job(session: Session, job_no: Any) -> Job:
    text = str(job_no or "").strip()
    job = session.scalar(select(Job).where(Job.job_no == int(text))) if text.isdigit() else None
    if job is None:
        raise ProductionError(f"Job {text} not found.")
    return job


def _order_line(session: Session, job: Job) -> OrderLine | None:
    if not job.order_id:
        return None
    return session.scalar(select(OrderLine).where(OrderLine.order_id == job.order_id,
                                                  OrderLine.sno == job.line_sno))


def _editable(job: Job) -> None:
    if job.status == "transferred":
        raise ProductionError(f"Job {job.job_no} is already in ready stock - correct the "
                              "piece (or delete it from stock) instead.")
    if job.status == "cancelled":
        raise ProductionError(f"Job {job.job_no} is cancelled.")


def update_job(session: Session, job: Job, field: str, value: Any, reason: str,
               user: Any = None, kind: str = "") -> None:
    """field = metal_id / c_ref / pcs / product_sku_id - on the job and its
    order line (so a re-saved order keeps the correction)."""
    _need_reason(reason)
    _editable(job)
    if field not in ("metal_id", "c_ref", "pcs", "product_sku_id"):
        raise ProductionError(f"Cannot update {field}.")
    if field == "pcs":
        value = int(value or 0)
        if value <= 0:
            raise ProductionError("Pieces must be more than 0.")
    if field in ("metal_id", "product_sku_id") and not value:
        raise ProductionError("Choose the new value.")
    if field == "c_ref":
        value = (value or "").strip()
    line = _order_line(session, job)
    before = {"job": getattr(job, field)}
    if line is not None:
        before["order line"] = getattr(line, field)
    setattr(job, field, value)
    if line is not None:
        setattr(line, field, value)
        if field == "product_sku_id":
            sku = session.get(ProductSku, value)
            line.sku_desc = sku.description if sku else line.sku_desc
    audit(session, kind or f"job_{field}", f"Job {job.job_no}", before,
          {"job": value, **({"order line": value} if line is not None else {})}, reason, user)


def add_pcs(session: Session, job: Job, extra: int, reason: str, user: Any = None) -> None:
    """Add Pcs in Job Card: more pieces on an existing job (and its order line)."""
    _need_reason(reason)
    extra = int(extra or 0)
    if extra <= 0:
        raise ProductionError("Enter how many pieces to add.")
    update_job(session, job, "pcs", int(job.pcs or 0) + extra, reason, user,
               kind="job_add_pcs")


# --------------------------------------------------------------------------
# Update SSKU Price in Ready Stock
# --------------------------------------------------------------------------
def _stone_matches(st: dict, ssku: str, size: str | None) -> bool:
    label = (st.get("label") or "").strip()
    if not (label == ssku or label.startswith(ssku + " ")):
        return False
    if size:
        rest = label[len(ssku):].strip()
        return (st.get("size") or rest) == size
    return True


def _piece_stones(session: Session, item: StockItem) -> tuple[Any, list[dict], Decimal]:
    """(the line holding the stones, its stones, this piece's share of them)."""
    if item.line_id:
        line = session.get(MfgTransferLine, item.line_id)
        if line is not None:
            return line, json.loads(line.stones_json or "[]"), \
                Decimal(item.pcs or 1) / Decimal(line.pcs or 1)
    if item.in_line_id:
        line = session.get(ReadyVoucherLine, item.in_line_id)
        if line is not None:
            return line, json.loads(line.stones_json or "[]"), Decimal(1)
    return None, [], Decimal(1)


def ssku_price_preview(session: Session, ssku: str, size: str | None,
                       new_price: Any) -> list[dict[str, Any]]:
    """Every piece in ready stock carrying the stone: its stone amount and
    piece price before and after."""
    from diagold.services import sales
    new_price = _dec(new_price)
    rows = []
    for item in session.scalars(select(StockItem).where(StockItem.status == "in_stock")
                                .order_by(StockItem.stock_no)):
        _line, stones, share = _piece_stones(session, item)
        for st in stones:
            if not _stone_matches(st, ssku, size):
                continue
            old_amt = sales.stone_amount(st)
            new_amt = sales.stone_amount({**st, "price": str(new_price)})
            delta = ((new_amt - old_amt) * share).quantize(Decimal("0.01"))
            sku = session.get(ProductSku, item.product_sku_id) if item.product_sku_id else None
            rows.append({"_id": item.id, "stock_no": item.stock_no,
                         "sku": sku.sku_code if sku else "", "stone": st.get("label"),
                         "pcs": st.get("pcs"), "weight": _dec(st.get("weight")),
                         "old_price": _dec(st.get("price")), "new_price": new_price,
                         "old_amount": old_amt, "new_amount": new_amt,
                         "piece_old": _dec(item.price),
                         "piece_new": _dec(item.price) + delta, "_delta": delta})
    return rows


def ssku_price_apply(session: Session, ssku: str, size: str | None, new_price: Any,
                     reason: str, user: Any = None) -> int:
    """Re-price the stone on every piece in ready stock: the stone line and
    the piece's price move by the difference. Returns pieces changed."""
    _need_reason(reason)
    rows = ssku_price_preview(session, ssku, size, new_price)
    if not rows:
        return 0
    lines_done: set[tuple[str, int]] = set()
    for r in rows:
        item = session.get(StockItem, r["_id"])
        line, stones, _share = _piece_stones(session, item)
        key = (type(line).__name__, line.id)
        if key not in lines_done:
            lines_done.add(key)
            for st in stones:
                if _stone_matches(st, ssku, size):
                    st["price"] = str(_dec(new_price))
                    from diagold.services import sales
                    st["amount"] = str(sales.stone_amount(st))
            line.stones_json = json.dumps(stones, default=str)
        item.price = _dec(item.price) + r["_delta"]
    audit(session, "ssku_price", f"{ssku} {size or 'all sizes'}",
          {"pieces": {r["stock_no"]: str(r["piece_old"]) for r in rows},
           "stone price": str(rows[0]["old_price"])},
          {"pieces": {r["stock_no"]: str(r["piece_new"]) for r in rows},
           "stone price": str(_dec(new_price))}, reason, user)
    return len({r["_id"] for r in rows})


def delete_item_history(session: Session, stock_no: Any, *, delete_sku: bool, reason: str,
                        user: Any = None) -> str:
    """Delete a piece from ready stock (its job goes back to Pending for MFG
    Transfer); with "Delete SKU also", the SKU too when nothing else uses it."""
    _need_reason(reason)
    from diagold.services import manufacturing as MF
    text = str(stock_no or "").strip()
    item = session.scalar(select(StockItem).where(StockItem.stock_no == int(text))) \
        if text.isdigit() else None
    if item is None:
        raise ProductionError(f"Stock No {text} not found.")
    sku_id = item.product_sku_id
    before = {"stock no": item.stock_no, "sku_id": sku_id, "job_id": item.job_id}
    audit(session, "delete_item", f"Stock No {item.stock_no}", before,
          {"deleted": True, "sku deleted": delete_sku}, reason, user)
    MF.delete_stock_item(session, item, user_id=getattr(user, "id", None), reason=reason)
    msg = f"Stock No {text} deleted; its job is back in Pending for MFG Transfer."
    if delete_sku and sku_id:
        used = (session.scalar(select(func.count(StockItem.id)).where(
            StockItem.product_sku_id == sku_id))
            or session.scalar(select(func.count(Job.id)).where(Job.product_sku_id == sku_id))
            or session.scalar(select(func.count(OrderLine.id)).where(
                OrderLine.product_sku_id == sku_id)))
        if used:
            msg += " The SKU is still used by other pieces / jobs / orders, so it stays."
        else:
            session.delete(session.get(ProductSku, sku_id))
            msg += " The SKU is deleted too."
    session.flush()
    return msg


# --------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------
DECLARATION_DOCS: dict[str, int] = {
    "Purchase Metal": 4, "Purchase Stone": 4, "Purchase Ready Stock": 4, "Quotation": 4,
    "Sale As Approval": 4, "Sale Stone": 4, "Sale Ready Stock": 6, "Order": 4,
}
# Which voucher prints which declaration.
DOC_OF_VOUCHER = {"metal_purchase": "Purchase Metal", "stone_purchase": "Purchase Stone",
                  "rp_purchase": "Purchase Ready Stock", "rs_approval": "Sale As Approval",
                  "stone_sale": "Sale Stone", "stone_approval": "Sale Stone",
                  "rs_sale": "Sale Ready Stock", "order": "Order"}


def declarations(session: Session, doc: str) -> list[str]:
    raw = settings.get_setting(session, f"decl.{doc}", "[]")
    try:
        lines = json.loads(raw)
    except ValueError:
        lines = []
    n = DECLARATION_DOCS.get(doc, 4)
    return (list(lines) + [""] * n)[:n]


def set_declarations(session: Session, doc: str, lines: list[str], user: str = "") -> None:
    settings.set_setting(session, f"decl.{doc}",
                         json.dumps([l.strip() for l in lines][:DECLARATION_DOCS[doc]]), user)


def declaration_html(session: Session, voucher_type: str) -> str:
    doc = DOC_OF_VOUCHER.get(voucher_type)
    lines = [l for l in declarations(session, doc) if l] if doc else []
    if not lines:
        return ""
    return ("<hr><p style='font-size:9pt'><b>Declaration</b><br>"
            + "<br>".join(l.replace("<", "&lt;") for l in lines) + "</p>")


# --------------------------------------------------------------------------
# Print layouts (Advance Options)
# --------------------------------------------------------------------------
LAYOUTS = ("PACKING LIST (CLIENT)", "SALE INVOICE (CLIENT)", "SALE INVOICE (DEFAULT)",
           "PACKING LIST (DEFAULT)", "MFG TRANSFER")
LAYOUT_DEFAULT = {"title": "", "header": "", "show_prices": True, "show_stones": True,
                  "footer": ""}


def layout(session: Session, name: str) -> dict[str, Any]:
    try:
        return {**LAYOUT_DEFAULT, **json.loads(settings.get_setting(session, f"layout.{name}",
                                                                    "{}"))}
    except ValueError:
        return dict(LAYOUT_DEFAULT)


def set_layout(session: Session, name: str, values: dict[str, Any], user: str = "") -> None:
    settings.set_setting(session, f"layout.{name}",
                         json.dumps({k: values.get(k, v) for k, v in LAYOUT_DEFAULT.items()}),
                         user)


def layout_for(session: Session, doc: str, account_id: int | None) -> tuple[str, dict]:
    """doc = "SALE INVOICE" / "PACKING LIST": the client's own layout when the
    Account master says CLIENT, else the default."""
    a = session.get(Account, account_id) if account_id else None
    field = "invoice_layout" if doc == "SALE INVOICE" else "packing_layout"
    which = (getattr(a, field, "") or "DEFAULT") if a else "DEFAULT"
    name = f"{doc} ({'CLIENT' if which.upper() == 'CLIENT' else 'DEFAULT'})"
    return name, layout(session, name)


# --------------------------------------------------------------------------
# Masters Excel
# --------------------------------------------------------------------------
def masters_lists(session: Session) -> dict[str, list[str]]:
    names = lambda model: [n for n in session.scalars(  # noqa: E731
        select(model.name).order_by(model.name)) if n]
    party = list(session.scalars(select(Account).where(Account.is_active.is_(True))
                                 .order_by(Account.name)))
    vendor_groups = ("Sundry Creditors", "Accounts Payable")
    return {
        "Item": names(Item), "Family": names(FamilyCategory),
        "Style": sorted({s for s in session.scalars(select(ProductSku.style)) if s}),
        "Metal": names(Metal), "Color": names(Colour),
        "Stone": sorted(set(names(StoneInfo)) | {s for s in session.scalars(
            select(StoneSku.stone)) if s}),
        "Shape": names(StoneShape), "Type": names(StoneKind), "Quality": names(StoneQuality),
        "Group": names(StoneGroup),
        # No Origin / Treatment / Creation Type masters yet (asked) - empty columns.
        "Origin": [], "Treatment": [], "CreationType": [],
        "Vendors": [a.name for a in party if a.group_name in vendor_groups],
        "Clients": [a.name for a in party if a.account_type == "Client"
                    and a.group_name not in vendor_groups],
    }


def masters_excel(session: Session, path: str | Path) -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    lists = masters_lists(session)
    wb = Workbook()
    ws = wb.active
    ws.title = "Masters"
    ws.append(list(lists))
    for c in ws[1]:
        c.font = Font(bold=True)
    for i in range(max((len(v) for v in lists.values()), default=0)):
        ws.append([v[i] if i < len(v) else None for v in lists.values()])
    wb.save(path)
    return sum(len(v) for v in lists.values())


# --------------------------------------------------------------------------
# Backup
# --------------------------------------------------------------------------
def backup_dir(session: Session | None = None) -> Path:
    p = settings.opt("opt.backup_path", session).strip()
    return Path(p).expanduser() if p else Path.home() / "DiaGoldBackups"


def backup_now(session: Session | None = None) -> Path:
    """A consistent copy of the database (SQLite online backup) named by date."""
    import sqlite3

    from diagold.config import DB_PATH
    out = backup_dir(session)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"diagold_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
    src = sqlite3.connect(str(DB_PATH))
    try:
        dst = sqlite3.connect(str(dest))
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()
    return dest


def backups(session: Session | None = None) -> list[dict[str, Any]]:
    d = backup_dir(session)
    if not d.is_dir():
        return []
    return [{"file": p.name, "path": str(p), "size_kb": round(p.stat().st_size / 1024),
             "at": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d-%m-%Y %H:%M")}
            for p in sorted(d.glob("diagold_*.sqlite3"), reverse=True)]


def copy_backup(path: str | Path, to: str | Path) -> Path:
    return Path(shutil.copy2(path, to))
