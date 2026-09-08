"""Setting Labour Chart and month-end karigar settlement (T-07).

The client currently works this out by hand every month: a karigar sets some
number of pieces, and the labour owed is pieces x the per-piece rate for that
stone group. This module makes it automatic.

Two rules matter:

* **The rate is never hard-coded.** It is read from the chart master every
  time. The exact per-piece figure is still being confirmed with the client -
  the recording is ambiguous between Rs 3 and Rs 30, a tenfold difference -
  so nothing in this codebase assumes either.
* **Rates are effective-dated.** Settling January again after February's rate
  changes must still produce January's original figure.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import Account, SettingLabourRate, SettingWork

STONE_GROUPS: tuple[str, ...] = SettingLabourRate.STONE_GROUPS


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def rate_for(session: Session, stone_group: str, on_date: date, *,
             setting_type_id: int | None = None,
             sku_id: int | None = None) -> tuple[Decimal, date | None]:
    """The per-piece rate in force, most specific match first.

    A SKU-level row beats a setting-type row, which beats the plain
    stone-group row - mirroring the legacy "Setting Labour Chart (SKU)".
    Returns the rate and the date it became effective, so a statement can show
    what it was based on.
    """
    base = select(SettingLabourRate).where(
        SettingLabourRate.stone_group == stone_group,
        SettingLabourRate.effective_from <= on_date,
        SettingLabourRate.is_active.is_(True),
    ).order_by(SettingLabourRate.effective_from.desc())

    for narrowing in (
        base.where(SettingLabourRate.sku_id == sku_id) if sku_id else None,
        base.where(SettingLabourRate.setting_type_id == setting_type_id)
        if setting_type_id else None,
        base.where(SettingLabourRate.sku_id.is_(None),
                   SettingLabourRate.setting_type_id.is_(None)),
    ):
        if narrowing is None:
            continue
        row = session.scalars(narrowing.limit(1)).first()
        if row is not None:
            return Decimal(str(row.rate_per_piece)), row.effective_from
    return Decimal("0"), None


@dataclass
class SettlementLine:
    stone_group: str
    pieces: int
    rate_per_piece: Decimal
    rate_effective_from: date | None
    amount: Decimal


@dataclass
class Settlement:
    """One karigar's setting labour for one month."""

    karigar_id: int | None
    karigar_name: str
    year: int
    month: int
    lines: list[SettlementLine] = field(default_factory=list)

    @property
    def total_pieces(self) -> int:
        return sum(line.pieces for line in self.lines)

    @property
    def total_amount(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal("0"))


def settle_month(session: Session, karigar_id: int | None,
                 year: int, month: int) -> Settlement:
    """Compute a karigar's setting labour for a month.

    Piece counts come from recorded setting work, never from manual entry.
    The rate used is the one in force at month end.
    """
    start, end = month_bounds(year, month)
    karigar = session.get(Account, karigar_id) if karigar_id else None

    work = session.scalars(
        select(SettingWork).where(
            SettingWork.karigar_id == karigar_id,
            SettingWork.work_date >= start,
            SettingWork.work_date <= end,
        )
    ).all()

    by_group: dict[str, int] = {}
    for row in work:
        by_group[row.stone_group] = by_group.get(row.stone_group, 0) + int(row.pieces or 0)

    lines: list[SettlementLine] = []
    for group in sorted(by_group, key=lambda g: (STONE_GROUPS.index(g)
                                                 if g in STONE_GROUPS else 99, g)):
        pieces = by_group[group]
        rate, effective = rate_for(session, group, end)
        lines.append(SettlementLine(
            stone_group=group,
            pieces=pieces,
            rate_per_piece=rate,
            rate_effective_from=effective,
            amount=(Decimal(pieces) * rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        ))

    return Settlement(
        karigar_id=karigar_id,
        karigar_name=karigar.name if karigar else "(unassigned)",
        year=year, month=month, lines=lines,
    )


def statement_text(s: Settlement) -> str:
    """A readable per-karigar monthly statement."""
    head = (f"Setting labour — {s.karigar_name} — "
            f"{calendar.month_name[s.month]} {s.year}")
    out = [head, "-" * len(head),
           f"{'Stone Group':<16}{'Pieces':>8}{'Rate/pc':>12}{'Amount':>14}   Rate from"]
    for line in s.lines:
        out.append(
            f"{line.stone_group:<16}{line.pieces:>8}{line.rate_per_piece:>12}"
            f"{line.amount:>14}   {line.rate_effective_from or '— no rate set —'}"
        )
    out.append("-" * len(head))
    out.append(f"{'TOTAL':<16}{s.total_pieces:>8}{'':>12}{s.total_amount:>14}")
    return "\n".join(out)
