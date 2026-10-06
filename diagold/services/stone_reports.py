"""Stone balances by location and stage (5 Oct §4.10 / §4.13, T-07; TR6).

Stages a stone can be at:
  INV  - loose at a location (the stock ledger, StockMovement);
  JC   - in a job's bag (Job Card), not with a karigar;
  WIP  - out with a karigar on a job step, or set in a piece still being made;
  RDY  - set in a finished piece in ready stock;
  LOS  - broken or lost (bag breakage / transfer loss).

JC and WIP belong to the location the stones were issued from (the bag
line's source location). Groups are the client's three heads - DIAMOND,
POLKI, COLOR STONE - plus OTHER for text no stone master matches.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import (Job, JobBagLine, Location, MfgTransferLine, StockItem,
                               StockMovement, StoneSku)
from diagold.services import production

ZERO = Decimal("0")
D3 = Decimal("0.001")
GROUP_COLS = (("DIAMOND", "dia"), ("COLOR STONE", "cs"), ("POLKI", "pol"), ("OTHER", "oth"))
_GKEY = dict(GROUP_COLS)
OPEN_JOBS = ("pending", "mapped", "in_progress", "complete")


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _gkey(group: str) -> str:
    return _GKEY.get((group or "").upper(), "oth")


# Location Wise Stone Balance: which line each ledger movement lands on.
def _line_of(m: StockMovement) -> str:
    rk, kind = m.ref_kind or "", m.kind or ""
    if kind == "opening" or rk == "opening":
        return "opening"
    if rk == "stone_purchase":
        return "purchase"
    if rk in ("bag", "inv_return") and kind == "return":
        return "job_return"
    if kind == "breakage":
        return "breakage"
    if rk == "stone_issue":
        return "issue_job"
    if rk == "stone_sale":
        return "sale"
    if rk in ("stone_approval",):
        return "approval"
    if rk == "stock_transfer":
        return "transfer_in" if _dec(m.weight) > 0 or m.pcs > 0 else "transfer_out"
    return "receipt" if (_dec(m.weight) > 0 or m.pcs > 0) else "other_out"


INWARD_LINES = (("purchase", "Purchase"), ("receipt", "Receipt (stone receipt / approval "
                                                      "return)"),
                ("job_return", "Return From Job"), ("transfer_in", "Transfer In"))
OUTWARD_LINES = (("issue_job", "Issued To Job (used in ready stock / in work)"),
                 ("sale", "Sale"), ("approval", "Approval"), ("transfer_out", "Transfer Out"),
                 ("breakage", "Breakage / Loss"), ("other_out", "Other Out"))


def _hold(line: JobBagLine) -> tuple[tuple[int, Decimal], tuple[int, Decimal]]:
    """(JC, WIP) of one bag line: JC = the bag's balance; WIP = issued to
    karigars less back (with them, or set in the piece being made)."""
    row = production.bag_row(line)
    jc = row["bal"]
    iss, back = row["iss"], row["back"]
    return jc, (iss[0] - back[0], iss[1] - back[1])


def location_stone_balance(session: Session, location_id: int | None, date_from: date,
                           date_to: date) -> list[dict[str, Any]]:
    """Rows Opening, Purchase, Receipt …, Inward Total, Issued To Job …,
    Outward Total, Closing Stock, then Balance Details (Inventory, Job Card,
    WIP, Total) - each with ct and pcs per DIA / CS / POL / OTHER.
    Closing = Opening + Inward - Outward (the loose stones at the location);
    Total = Inventory + Job Card + WIP (the location's stones incl. in work).
    Negative figures are flagged."""
    if not location_id:
        return []
    acc: dict[str, dict[str, list]] = {}

    def add(line: str, g: str, pcs: int, wt: Decimal) -> None:
        a = acc.setdefault(line, {}).setdefault(g, [0, ZERO])
        a[0] += pcs
        a[1] += wt

    for m in session.scalars(select(StockMovement).where(
            StockMovement.material_class == "stone", StockMovement.location_id == location_id,
            StockMovement.mv_date <= date_to)):
        g = _gkey(m.stone_group)
        pcs, wt = int(m.pcs or 0), _dec(m.weight)
        if m.mv_date < date_from or _line_of(m) == "opening":
            add("opening", g, pcs, wt)
            continue
        line = _line_of(m)
        add(line, g, abs(pcs), abs(wt))
    # Balance details: stones issued from here still in work (as on To).
    for bl, job in session.execute(select(JobBagLine, Job).join(Job, JobBagLine.job_id == Job.id)
                                   .where(JobBagLine.source_location_id == location_id,
                                          Job.status.in_(OPEN_JOBS))):
        g = _gkey(production.stone_group_label(session, bl.stone_sku_id, bl.particulars))
        (jp, jw), (wp, ww) = _hold(bl)
        add("d_jc", g, jp, jw)
        add("d_wip", g, wp, ww)

    def tot(lines) -> dict[str, list]:
        out: dict[str, list] = {}
        for ln in lines:
            for g, (p, w) in acc.get(ln, {}).items():
                o = out.setdefault(g, [0, ZERO])
                o[0] += p
                o[1] += w
        return out

    acc["inward"] = tot([k for k, _l in INWARD_LINES])
    acc["outward"] = tot([k for k, _l in OUTWARD_LINES])
    closing: dict[str, list] = {}
    for g in _GKEY.values():
        o = acc.get("opening", {}).get(g, [0, ZERO])
        i = acc["inward"].get(g, [0, ZERO])
        x = acc["outward"].get(g, [0, ZERO])
        closing[g] = [o[0] + i[0] - x[0], o[1] + i[1] - x[1]]
    acc["closing"] = closing
    acc["d_inv"] = closing
    acc["d_total"] = tot(["d_inv", "d_jc", "d_wip"])

    plan = ([("opening", "Opening Stock", "")]
            + [(k, l, "INWARD") for k, l in INWARD_LINES]
            + [("inward", "Inward Total", "total")]
            + [(k, l, "OUTWARD") for k, l in OUTWARD_LINES]
            + [("outward", "Outward Total", "total"), ("closing", "Closing Stock", "total"),
               ("d_inv", "Balance Details: Inventory", "BALANCE DETAILS"),
               ("d_jc", "Job Card", "BALANCE DETAILS"), ("d_wip", "WIP", "BALANCE DETAILS"),
               ("d_total", "Total (location + in work)", "total")])
    rows = []
    for key, label, section in plan:
        vals = acc.get(key, {})
        r: dict[str, Any] = {"line": label, "section": section, "_bold": section == "total"}
        neg = False
        for g in _GKEY.values():
            p, w = vals.get(g, [0, ZERO])
            r[f"{g}_wt"] = w.quantize(D3) if w else None
            r[f"{g}_pcs"] = p or None
            neg = neg or p < 0 or w < 0
        r["_negative"] = neg and key in ("closing", "d_inv", "d_total")
        rows.append(r)
    return rows


# --------------------------------------------------------------------------
# Stone Summary
# --------------------------------------------------------------------------
def stone_summary(session: Session, date_to: date, *, groups_only: bool = False
                  ) -> list[dict[str, Any]]:
    """LOCATION, GROUP, STONE, WHERE (INV / JC / WIP / RDY / LOS), PCS,
    WEIGHT, VALUE - every stone the business owns, by where it is.
    "Groups only" rolls the stones up to DIAMOND / POLKI / COLOR STONE."""
    acc: dict[tuple, list] = {}
    locs: dict[int | None, str] = {}

    def loc(lid):
        if lid not in locs:
            l = session.get(Location, lid) if lid else None
            locs[lid] = l.name if l else "(no location)"
        return locs[lid]

    skus: dict[int | None, StoneSku | None] = {}

    def stone_name(sku_id, text) -> str:
        if sku_id not in skus:
            skus[sku_id] = session.get(StoneSku, sku_id) if sku_id else None
        k = skus[sku_id]
        return ((k.stone or k.sku_code) if k else (text or "")).strip() or "?"

    def add(lid, group, stone, where, pcs, wt, val) -> None:
        a = acc.setdefault((loc(lid), group or production.OTHER_GROUP,
                            "" if groups_only else stone, where), [0, ZERO, ZERO])
        a[0] += pcs
        a[1] += wt
        a[2] += val

    for m in session.scalars(select(StockMovement).where(
            StockMovement.material_class == "stone", StockMovement.mv_date <= date_to)):
        add(m.location_id, m.stone_group, stone_name(m.ref_id, m.ref_text), "INV",
            int(m.pcs or 0), _dec(m.weight), _dec(m.value))
        if m.kind == "breakage":
            add(m.location_id, m.stone_group, stone_name(m.ref_id, m.ref_text), "LOS",
                -int(m.pcs or 0), -_dec(m.weight), -_dec(m.value))
    for bl, job in session.execute(select(JobBagLine, Job).join(Job, JobBagLine.job_id == Job.id)
                                   .where(Job.status.in_(OPEN_JOBS))):
        group = production.stone_group_label(session, bl.stone_sku_id, bl.particulars)
        price, unit = production.stone_price(session, bl.stone_sku_id)
        (jp, jw), (wp, ww) = _hold(bl)
        name = stone_name(bl.stone_sku_id, bl.particulars)
        for where, p, w in (("JC", jp, jw), ("WIP", wp, ww)):
            if p or w:
                add(bl.source_location_id, group, name, where, p, w,
                    production.stone_amount(price, unit, p, w))
    for item in session.scalars(select(StockItem).where(StockItem.status == "in_stock")):
        line = session.get(MfgTransferLine, item.line_id) if item.line_id else None
        stones = json.loads(line.stones_json or "[]") if line else []
        for st in stones:
            label = st.get("label") or ""
            group = (st.get("s_type") or "").upper()
            group = {"DIA": "DIAMOND", "CS": "COLOR STONE", "COLOUR STONE": "COLOR STONE"}.get(
                group, group)
            if group not in _GKEY:
                group = production.stone_group_label(session, None, label.rsplit(" ", 1)[0])
            add(item.location_id, group, label.rsplit(" ", 1)[0] if " " in label else label,
                "RDY", int(st.get("pcs") or 0), _dec(st.get("weight")), _dec(st.get("amount")))
    order = {"RDY": 0, "INV": 1, "JC": 2, "WIP": 3, "LOS": 4}
    rows = []
    for (l, g, stone, where), (p, w, v) in sorted(
            acc.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], order.get(kv[0][3], 9))):
        if not p and not w:
            continue
        rows.append({"location": l, "group": g, "stone": stone, "where": where, "pcs": p,
                     "weight": w.quantize(D3), "value": v.quantize(Decimal("0.01")),
                     "_negative": p < 0 or w < 0})
    return rows
