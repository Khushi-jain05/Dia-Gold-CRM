"""Stone SKU = one stone with its sizes inside (5 Nov meeting, T-01).

The size rows stay the StoneSku table - stock, job bags, purchases and issues
already point at them - and each gets a StoneMaster: the stone's one name and
its shared details. ``group_stone_skus`` runs on every start-up: a size row with
no master joins the master of its stone name (made if missing). It never moves
a row that already has a master.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import StoneMaster, StoneSku

_HEAD = ("description", "mrp", "shape", "stone_type", "quality", "color", "shelf_no",
         "rfid", "add_in_netwt", "is_active")


def stone_name(sku: StoneSku) -> str:
    """The stone a size row belongs to: its Stone field, else its code less the size."""
    name = (sku.stone or "").strip()
    if name:
        return name.upper()
    code, size = (sku.sku_code or "").strip(), (sku.size or "").strip()
    if size and code.upper().endswith(size.upper()):
        code = code[: -len(size)].strip()
    return code.upper()


def size_label(sku: StoneSku) -> str:
    """What the Size list shows: the size, else what the code adds to the name
    (POLKI U, POLKI 24 have no size on the master)."""
    size = (sku.size or "").strip()
    if size:
        return size
    name = sku.master.name if sku.master else stone_name(sku)
    code = (sku.sku_code or "").strip()
    if code.upper().startswith(name.upper()):
        return code[len(name):].strip()
    return code


def group_stone_skus(session: Session) -> int:
    """Give every size row without a master the master of its stone name."""
    masters = {m.name.upper(): m for m in session.scalars(select(StoneMaster))}
    moved = 0
    for sku in session.scalars(select(StoneSku).where(StoneSku.master_id.is_(None))
                               .order_by(StoneSku.id)):
        name = stone_name(sku)
        if not name:
            continue
        m = masters.get(name)
        if m is None:
            m = StoneMaster(name=name, **{k: getattr(sku, k) for k in _HEAD})
            session.add(m)
            session.flush()
            masters[name] = m
        sku.master_id = m.id
        if not (sku.stone or "").strip():
            sku.stone = m.name
        moved += 1
    if moved:
        session.flush()
    return moved


def size_code(master_name: str, size: str, range_label: str = "") -> str:
    """The Stone SKU code of a new size row: "EMERALD PEAR 3*4"."""
    tail = (size or range_label or "").strip()
    return f"{master_name.strip()} {tail}".strip()


def sync_sizes(session: Session, master: StoneMaster) -> None:
    """After the master screen saves: each size row carries the stone's name
    and shared details, and a code (made from name + size when blank)."""
    def renamed(sku: StoneSku) -> bool:
        code = (sku.sku_code or "").strip()
        return not code or code.endswith(" (copy)") or code.startswith("__new_")

    used = {c for (c,) in session.execute(select(StoneSku.sku_code).where(
        StoneSku.master_id != master.id))}
    used |= {sku.sku_code for sku in master.sizes if not renamed(sku)}
    for sku in master.sizes:
        sku.stone = master.name
        for k in ("shape", "stone_type", "quality", "color", "shelf_no", "rfid",
                  "add_in_netwt", "mrp"):
            setattr(sku, k, getattr(master, k))
        if renamed(sku):
            code = size_code(master.name, sku.size, sku.range_label)
            base, n = code, 2
            while code in used:
                code, n = f"{base} ({n})", n + 1
            sku.sku_code = code
            used.add(code)
    session.flush()


def size_in_use(session: Session, sku: StoneSku) -> str | None:
    """Why a size row may not be deleted (it is on a voucher, a bag, a SKU's
    stones or in stock), or None."""
    from diagold.db.models import (InvVoucherLine, JobBagLine, MaterialStock,
                                   ProductSkuStone, StockMovement, StockTransferLine,
                                   StoneIssueLine)
    checks = (
        (InvVoucherLine.stone_sku_id, "an inventory voucher"),
        (StoneIssueLine.stone_sku_id, "a Stone Issue on Job-Card"),
        (JobBagLine.stone_sku_id, "a job bag"),
        (ProductSkuStone.stone_sku_id, "a Product SKU's stones"),
        (StockTransferLine.stone_sku_id, "a stock transfer"),
    )
    for col, where in checks:
        if session.scalar(select(col).where(col == sku.id).limit(1)) is not None:
            return f"Size {size_label(sku)} of {sku.stone} is used on {where} - it cannot be removed."
    for model in (MaterialStock, StockMovement):
        if session.scalar(select(model.id).where(model.material_class == "stone",
                                                 model.ref_id == sku.id).limit(1)):
            return f"Size {size_label(sku)} of {sku.stone} has stock entries - it cannot be removed."
    return None


# --------------------------------------------------------------------------
# The client's Stone SKU List (legacy export "STONE SKU List", sent 11 Nov as
# "stone list.xlsx"): one row per size - SSKU | STONE | SHAPE | C PRICE | SIZE.
# Import only ADDS: a Stone SKU not in the system (matched by name, ignoring
# case and extra spaces) is made, and a size it lacks is added under it.
# Nothing already there is changed (a blank Stone / Shape is filled). "-" means blank; C PRICE is the size's
# cost price (Per Cts).
# --------------------------------------------------------------------------
STONE_LIST_FILE = "stone_list.xlsx"
_LIST_HEAD = ("SSKU", "STONE", "SHAPE", "C PRICE", "SIZE")


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    text = " ".join(str(v).split())
    return "" if text in ("-", "—") else text


def read_stone_list(path) -> list[dict]:
    """The sheet's rows below its SSKU heading, blanks and repeats dropped."""
    from openpyxl import load_workbook
    ws = load_workbook(path, data_only=True, read_only=True).worksheets[0]
    pos: dict[str, int] | None = None
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in ws.iter_rows(values_only=True):
        if pos is None:
            head = [_cell(v).upper() for v in r]
            if "SSKU" in head:
                pos = {h: head.index(h) for h in _LIST_HEAD if h in head}
            continue
        get = lambda h: _cell(r[pos[h]]) if h in pos and pos[h] < len(r) else ""  # noqa: E731
        name = get("SSKU")
        if not name:
            continue
        size = get("SIZE")
        key = (name.upper(), size.upper())
        if key in seen:
            continue
        seen.add(key)
        try:
            price = float(get("C PRICE") or 0)
        except ValueError:
            price = 0.0
        out.append({"name": name, "stone": get("STONE"), "shape": get("SHAPE"),
                    "size": size, "cost_price": price})
    if pos is None:
        raise ValueError("No SSKU heading found - is this the Stone SKU List?")
    return out


def import_stone_list(session: Session, path) -> dict[str, int]:
    """Add the Stone SKUs and sizes not in the system. Returns
    {"Stone SKU": masters added, "Size": size rows added}."""
    masters = {" ".join(m.name.split()).upper(): m
               for m in session.scalars(select(StoneMaster))}
    added = {"Stone SKU": 0, "Size": 0}
    touched: list[StoneMaster] = []
    for row in read_stone_list(path):
        m = masters.get(row["name"].upper())
        if m is None:
            m = StoneMaster(name=row["name"], stone=row["stone"], shape=row["shape"])
            session.add(m)
            session.flush()
            masters[row["name"].upper()] = m
            added["Stone SKU"] += 1
        for k in ("stone", "shape"):            # a blank detail is filled, never changed
            if not (getattr(m, k) or "").strip() and row[k]:
                setattr(m, k, row[k])
        if m not in touched:
            touched.append(m)
        have = {(s.size or "").strip().upper() for s in m.sizes}
        if row["size"].upper() in have:
            continue
        m.sizes.append(StoneSku(stone=m.name, size=row["size"], per="Cts",
                                cost_price=row["cost_price"]))
        added["Size"] += 1
    session.flush()
    for m in touched:
        sync_sizes(session, m)
    return added


def seed_stone_list(session: Session) -> dict[str, int]:
    """Once only, on first start: the client's Stone SKU List."""
    from diagold.services import settings
    from diagold.services.master_import import DATA
    key = "seed.stone_list"
    if settings.get_setting(session, key, "") == "1" or not (DATA / STONE_LIST_FILE).is_file():
        return {}
    settings.set_setting(session, key, "1")
    return import_stone_list(session, DATA / STONE_LIST_FILE)
