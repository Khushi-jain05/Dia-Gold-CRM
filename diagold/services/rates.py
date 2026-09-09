"""Daily metal / labour rates and date-effective stock valuation.

The client updates the gold rate every day and expects the whole stock to
re-price against that day's rate with no manual re-entry. Two rules follow:

* **History is never overwritten.** A valuation for a past date reproduces
  exactly, because it reads the rate that applied on that date.
* **Valuation scales with purity.** A gram of 18KT and a gram of 14KT are
  worth different amounts at the same gold rate, so the purity always comes
  from the Metal master (see :mod:`diagold.services.costing`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import DailyLabourRate, DailyMetalRate, Metal
from diagold.services import costing


@dataclass
class RateInfo:
    """A rate together with the date it actually came from."""

    rate: Decimal
    effective_date: date | None

    @property
    def found(self) -> bool:
        return self.effective_date is not None


def rate_for(session: Session, metal_id: int, on_date: date) -> RateInfo:
    """The rate in force for a metal on a date - the latest on or before it.

    Returns the effective date too, so a screen can show what a valuation is
    based on rather than just a number.
    """
    row = session.scalars(
        select(DailyMetalRate)
        .where(DailyMetalRate.metal_id == metal_id,
               DailyMetalRate.rate_date <= on_date)
        .order_by(DailyMetalRate.rate_date.desc())
        .limit(1)
    ).first()
    if row is None:
        return RateInfo(Decimal("0"), None)
    rate = row.pure_rate_per_gram or row.rate_per_gram
    return RateInfo(Decimal(str(rate)), row.rate_date)


def labour_rate_for(session: Session, metal_id: int | None,
                    on_date: date) -> RateInfo:
    """Same lookup for the parallel Daily Labour Rates master (pending Q9)."""
    row = session.scalars(
        select(DailyLabourRate)
        .where(DailyLabourRate.metal_id == metal_id,
               DailyLabourRate.rate_date <= on_date)
        .order_by(DailyLabourRate.rate_date.desc())
        .limit(1)
    ).first()
    if row is None:
        return RateInfo(Decimal("0"), None)
    return RateInfo(Decimal(str(row.rate)), row.rate_date)


def set_rate(session: Session, metal_id: int, on_date: date,
             rate_per_gram: Decimal | float | str, *,
             pure_rate_per_gram: Decimal | float | str = 0,
             remark: str = "") -> DailyMetalRate:
    """Record (or correct) one metal's rate for one day.

    One rate per metal per day. Correcting today's figure updates today's row
    only - earlier days are left untouched so history stays reproducible.
    """
    row = session.scalar(
        select(DailyMetalRate).where(DailyMetalRate.metal_id == metal_id,
                                     DailyMetalRate.rate_date == on_date)
    )
    if row is None:
        row = DailyMetalRate(metal_id=metal_id, rate_date=on_date)
        session.add(row)
    row.rate_per_gram = Decimal(str(rate_per_gram))
    row.pure_rate_per_gram = Decimal(str(pure_rate_per_gram or 0))
    row.remark = remark
    session.flush()
    return row


@dataclass
class HoldingValue:
    metal_id: int
    metal_name: str
    weight: Decimal
    purity_fraction: Decimal
    rate: Decimal
    effective_date: date | None
    value: Decimal


def value_holdings(session: Session,
                   holdings: Iterable[tuple[int, Decimal | float | str]],
                   on_date: date) -> list[HoldingValue]:
    """Value ``(metal_id, weight_in_grams)`` pairs at a given date's rates.

    Purity is read from the Metal master for every line, so identical weights
    of different karats value differently.
    """
    out: list[HoldingValue] = []
    for metal_id, weight in holdings:
        metal = session.get(Metal, metal_id)
        if metal is None:
            continue
        info = rate_for(session, metal_id, on_date)
        out.append(HoldingValue(
            metal_id=metal_id,
            metal_name=metal.name,
            weight=Decimal(str(weight)),
            purity_fraction=costing.purity_fraction(metal),
            rate=info.rate,
            effective_date=info.effective_date,
            value=costing.metal_value(metal, weight, info.rate),
        ))
    return out


def total_value(lines: Iterable[HoldingValue]) -> Decimal:
    return sum((line.value for line in lines), Decimal("0"))
