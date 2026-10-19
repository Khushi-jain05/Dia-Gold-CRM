"""Shipping Details of an order (12 Oct video, order 1680).

The legacy order has a Shipping Details dialog in five parts - Despatch,
Order, Buyer's details, Consignee details and Export - with Fetch Dept and
Fetch Last Dtls. The fields are stored as one JSON text on the order
(``Order.shipping``), so a field the client adds later needs no new column.

Fetch Last Dtls copies the details of the same customer's last order that
has any. Fetch Dept fills Buyer's / Consignee details from the account
master (name, address, city, state, GSTIN, phone) - our reading of the
button, to confirm (9 Oct question 117).
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import Account, Order

# (section, key, label, multi-line)
FIELDS: tuple[tuple[str, str, str, bool], ...] = (
    ("Despatch", "delivery_note_no", "Delivery Note No", False),
    ("Despatch", "awb_no", "AW No / Despatch Doc No", False),
    ("Despatch", "ship_via", "Ship Via / Despatch Through", False),
    ("Despatch", "destination", "Destination", False),
    ("Despatch", "edf_no", "EDF No", False),
    ("Order", "order_nos", "Order No(s) / PO#", False),
    ("Order", "sales_rep", "Sales Rep", False),
    ("Order", "payment_terms", "Mode / Terms of Payment", False),
    ("Order", "other_reference", "Other Reference", False),
    ("Order", "delivery_terms", "Terms of Delivery", False),
    ("Buyer's details", "buyer", "Buyer", True),
    ("Consignee details", "consignee", "Consignee", True),
    ("Export", "exporter_ref", "Exporter's Ref", False),
    ("Export", "pre_carriage_by", "Pre-Carriage by", False),
    ("Export", "vessel_flight", "Vessel / Flight", False),
    ("Export", "port_loading", "Port of Loading", False),
    ("Export", "port_discharge", "Port of Discharge", False),
    ("Export", "final_destination", "Final Destination", False),
    ("Export", "country_origin", "Country of origin", False),
    ("Export", "box_details", "Box No details", True),
    ("Export", "product_description", "Product Description", True),
)
KEYS = tuple(k for _s, k, _l, _m in FIELDS)


def get(order: Order) -> dict[str, str]:
    """The order's shipping details, every key present ('' when not set)."""
    try:
        data = json.loads(order.shipping or "{}")
    except ValueError:
        data = {}
    return {k: str(data.get(k) or "") for k in KEYS}


def save(session: Session, order: Order, values: dict[str, str]) -> None:
    clean = {k: (values.get(k) or "").strip() for k in KEYS}
    clean = {k: v for k, v in clean.items() if v}
    order.shipping = json.dumps(clean, ensure_ascii=False) if clean else ""
    session.flush()


def is_filled(order: Order) -> bool:
    return any(get(order).values())


def last_details(session: Session, order: Order) -> dict[str, str] | None:
    """Fetch Last Dtls: the same customer's latest earlier order with details
    (a stock order: the latest stock order). None when there is none."""
    q = select(Order).where(Order.id != order.id, Order.shipping != "")
    q = q.where(Order.account_id == order.account_id) if order.account_id \
        else q.where(Order.account_id.is_(None))
    q = q.order_by(Order.order_date.desc(), Order.order_no.desc())
    for prev in session.scalars(q):
        if is_filled(prev):
            return get(prev)
    return None


def account_details(session: Session, order: Order) -> dict[str, str]:
    """Fetch Dept: Buyer's and Consignee details from the account master."""
    a = session.get(Account, order.account_id) if order.account_id else None
    if a is None:
        return {}
    parts = [a.name, a.address, ", ".join(p for p in (a.city, a.state) if p)]
    if a.gstin:
        parts.append(f"GSTIN {a.gstin}")
    if a.phone:
        parts.append(f"Ph {a.phone}")
    text = "\n".join(p.strip() for p in parts if p and p.strip())
    return {"buyer": text, "consignee": text}


def print_html(order: Order) -> str:
    """The filled details as a block for the order print ('' when none)."""
    d = get(order)
    rows = [f"<tr><td>{label}</td><td>{d[k].replace(chr(10), '<br>')}</td></tr>"
            for _s, k, label, _m in FIELDS if d[k]]
    if order.tracking_no:
        rows.insert(0, f"<tr><td>Tracking No</td><td>{order.tracking_no}</td></tr>")
    if not rows:
        return ""
    return ("<h3>Shipping Details</h3><table border=1 cellspacing=0 cellpadding=3>"
            + "".join(rows) + "</table>")


# -- Order menu: Order List, Status, Ship Tracking Number (12 Oct video) ------

ORDER_STATUSES = ("Pending", "In Production", "Ready", "Cancelled")


def order_status(jobs: list) -> str:
    """Pending: no job moved yet; In Production: a job is in work or waiting
    for its MFG transfer; Ready: every job is in ready stock; Cancelled: every
    job cancelled. (Our reading of the legacy Order ▸ Status - question 118.)"""
    live = [j for j in jobs if j.status != "cancelled"]
    if jobs and not live:
        return "Cancelled"
    if live and all(j.status == "transferred" for j in live):
        return "Ready"
    if any(j.status in ("in_progress", "complete", "transferred") for j in live):
        return "In Production"
    return "Pending"


def order_list(session: Session, date_from, date_to, status: str | None = None,
               **_kw) -> list[dict]:
    """One row per order: customer, lines, pieces, jobs and how far they are."""
    from diagold.db.models import Job
    orders = session.scalars(select(Order).where(
        Order.order_date >= date_from, Order.order_date <= date_to)
        .order_by(Order.order_date, Order.order_no)).all()
    jobs: dict[int, list] = {}
    for j in session.scalars(select(Job).where(Job.order_id.in_([o.id for o in orders]))):
        jobs.setdefault(j.order_id, []).append(j)
    rows = []
    for o in orders:
        js = jobs.get(o.id, [])
        st = order_status(js)
        if status and st != status:
            continue
        a = session.get(Account, o.account_id) if o.account_id else None
        d = get(o)
        rows.append({
            "_order_id": o.id, "ord_no": o.order_no, "date": o.order_date,
            "type": "Repair" if o.is_repair else o.order_type,
            "client": a.name if a else "stock", "ref": o.ref,
            "lines": len(o.lines), "pcs": sum(int(l.pcs or 0) for l in o.lines),
            "jobs": len([j for j in js if j.status != "cancelled"]),
            "in_work": len([j for j in js if j.status in ("in_progress", "complete")]),
            "in_stock": len([j for j in js if j.status == "transferred"]),
            "del_dt": o.delivery_date, "status": st,
            "tracking_no": o.tracking_no, "ship_via": d["ship_via"], "awb_no": d["awb_no"],
            "destination": d["destination"], "remark": o.remark,
        })
    return rows
