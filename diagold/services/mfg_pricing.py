"""MFG Ready Stock Transfer - the "Fill Prices" engine (28 Sept R9 / R10 / T-07).

Every finished piece is priced here from its weights, its stones and the
masters. The chain was read off the client's transfer Vr 1081 (job 28913 /
NSE-2495) and reconciles to the paisa:

    FineWt       = N-Wt x title/1000                     12.700 x 0.590 = 7.493
    Metal Rate   = fine (24K) rate x title/1000          14,713 x 0.590 = 8,680.67
    Metal Amount = N-Wt x Metal Rate                     1,10,244.51
    Stone Amount = sum(qty x price) per stone line       78,006.50
    Labour       = labour rate x net weight ("NetWt")    1,200 x 12.752 = 15,302.40
    Total        = Metal + Stone + Setting + Ex Metal + Finding + Labour + Manual
                                                         2,03,553.41
    Margin Amt   = Total x Margin % / 100                1,01,776.71
    Price/Pcs    = Total + Margin Amt                    3,05,330.12

"Margin %" on this screen is a MARK-UP (cost x 1.5), not cost / (1 - m).

No rate, percentage or purity appears as a literal: all of them come from the
Metal master, Daily Metal Rate, Labour Rate and Margin master, or are passed in.
Open points that only the client can close are marked with their 28 Sept code:
Q1 (margin 50% vs the 20% heard), Q2 (which net weight labour is on), Q5 (tag
price display), Q11 (which metal rate).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import Job, JobVoucher, LabourRate, MarginSet, Metal, StoneSku
from diagold.services import costing, production, rates

ZERO = Decimal("0")
PAISA = Decimal("0.01")
D3 = Decimal("0.001")


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(PAISA, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------
# Tag price display (28 Sept Q5)
# --------------------------------------------------------------------------
# The tag for 3,05,330.12 reads "305"; the client's rule ("if it's seven
# digits it makes it four digits") was not fully audible. The full price is
# always what is stored - only how it is printed is pluggable, and the rule in
# use is a setting, so the client's answer changes configuration, not code.
TAG_DISPLAY_SETTING = "pricing.tag_display"


def _tag_thousands(price: Decimal) -> str:
    return str(int(price.quantize(Decimal("1"), rounding=ROUND_DOWN) // 1000))


def _tag_full(price: Decimal) -> str:
    return f"{price.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}"


TAG_FORMATTERS: dict[str, tuple[str, Callable[[Decimal], str]]] = {
    # What the legacy screen showed for Vr 1081; provisional until Q5 closes.
    "thousands": ("Price in thousands, e.g. 3,05,330.12 -> 305 (provisional, Q5)",
                  _tag_thousands),
    "full": ("Full rupees, e.g. 3,05,330.12 -> 305330", _tag_full),
}


def tag_display(price: Any, rule: str = "thousands") -> str:
    """The figure printed on the tag. A zero price (repair work, R16) prints 0."""
    price = _dec(price)
    if price <= 0:
        return "0"
    _label, fn = TAG_FORMATTERS.get(rule, TAG_FORMATTERS["thousands"])
    return fn(price)


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------
@dataclass
class StoneCost:
    """One stone line of the cost break-up."""

    label: str
    pcs: int
    weight: Decimal          # carats
    unit: str                # "ct" or "pcs" - what the price is per
    price: Decimal
    s_type: str = ""

    @property
    def amount(self) -> Decimal:
        qty = Decimal(self.pcs) if self.unit == "pcs" else self.weight
        return _money(qty * self.price)


@dataclass
class TransferPrice:
    """Every figure on one MFG transfer line, with the inputs behind it.

    Stored whole on the line at save time, so history never re-prices.
    """

    net_wt: Decimal
    title: Decimal                 # parts per 1000, e.g. 590
    fine_wt: Decimal
    fine_rate: Decimal             # 24K rate per gram
    metal_rate: Decimal
    metal_amount: Decimal
    stones: list[StoneCost]
    stone_amount: Decimal
    setting_amount: Decimal
    ex_metal_amount: Decimal
    finding_labour: Decimal
    labour_rate: Decimal
    labour_weight: Decimal
    labour: Decimal
    manual_amount: Decimal
    total: Decimal
    margin_pct: Decimal
    margin_amount: Decimal
    price_per_pcs: Decimal
    pcs: int
    total_value: Decimal
    tag_price: Decimal
    tag_text: str
    notes: list[str] = field(default_factory=list)

    def as_rows(self) -> list[tuple[str, str, str]]:
        """(component, how, amount) - the cost break-up as the client reads it."""
        return [
            ("Metal", f"N-Wt {self.net_wt} x Metal Rate {self.metal_rate} "
                      f"(fine {self.fine_rate} x {self.title}/1000; FineWt {self.fine_wt})",
             f"{self.metal_amount:,.2f}"),
            ("Stones", f"{len(self.stones)} line(s)", f"{self.stone_amount:,.2f}"),
            ("Setting", "", f"{self.setting_amount:,.2f}"),
            ("Ex Metal", "", f"{self.ex_metal_amount:,.2f}"),
            ("Finding labour", "", f"{self.finding_labour:,.2f}"),
            ("Labour", f"{self.labour_rate} per g x {self.labour_weight} g (NetWt)",
             f"{self.labour:,.2f}"),
            ("Manual", "", f"{self.manual_amount:,.2f}"),
            ("Total cost", "", f"{self.total:,.2f}"),
            ("Margin", f"{self.margin_pct}% of total (mark-up)", f"{self.margin_amount:,.2f}"),
            ("Price per piece", "total + margin", f"{self.price_per_pcs:,.2f}"),
            ("Tag price", "as printed", self.tag_text),
        ]


def price_line(*, net_wt: Any, title: Any, fine_rate: Any,
               stones: Iterable[StoneCost] = (), labour_rate: Any = 0,
               labour_weight: Any = None, setting_amount: Any = 0,
               ex_metal_amount: Any = 0, finding_labour: Any = 0,
               manual_amount: Any = 0, margin_pct: Any = 0, pcs: int = 1,
               zero_tag: bool = False, tag_rule: str = "thousands") -> TransferPrice:
    """Fill Prices for one transfer line. Pure arithmetic - no database.

    ``title`` is the purity in parts per 1000 (590 for 14KT590) as the Metal
    master's Title column shows it. ``labour_weight`` defaults to ``net_wt``;
    the legacy line used 12.752 against a final 12.700, so the caller may pass
    the net weight of an earlier step until the client says which (Q2).
    ``zero_tag`` sets the tag price to 0 for repair work (R16, probable).
    """
    net = _dec(net_wt)
    title = _dec(title)
    fraction = title / Decimal("1000")
    fine_wt = (net * fraction).quantize(D3, rounding=ROUND_HALF_UP)
    fine_rate = _dec(fine_rate)
    metal_rate = _money(fine_rate * fraction)
    metal_amount = _money(net * metal_rate)
    stones = list(stones)
    stone_amount = sum((s.amount for s in stones), ZERO)
    labour_weight = net if labour_weight in (None, "") else _dec(labour_weight)
    labour = costing.labour_amount(labour_rate, net_weight=labour_weight)
    setting, ex_metal = _money(_dec(setting_amount)), _money(_dec(ex_metal_amount))
    finding, manual = _money(_dec(finding_labour)), _money(_dec(manual_amount))
    total = _money(metal_amount + stone_amount + setting + ex_metal + finding
                   + labour + manual)
    margin_pct = _dec(margin_pct)
    margin_amount = _money(total * margin_pct / Decimal("100"))
    price = total + margin_amount
    tag = ZERO if zero_tag else price
    pcs = max(int(pcs or 1), 1)
    return TransferPrice(
        net_wt=net, title=title, fine_wt=fine_wt, fine_rate=fine_rate,
        metal_rate=metal_rate, metal_amount=metal_amount, stones=stones,
        stone_amount=stone_amount, setting_amount=setting, ex_metal_amount=ex_metal,
        finding_labour=finding, labour_rate=_dec(labour_rate),
        labour_weight=labour_weight, labour=labour, manual_amount=manual, total=total,
        margin_pct=margin_pct, margin_amount=margin_amount, price_per_pcs=price,
        pcs=pcs, total_value=_money(price * pcs), tag_price=tag,
        tag_text=tag_display(tag, tag_rule),
    )


# --------------------------------------------------------------------------
# Filling a job from the masters
# --------------------------------------------------------------------------
def title_of(metal: Metal | None) -> Decimal:
    """A metal head's title in parts per 1000, whatever notation it is stored in."""
    return (costing.purity_fraction(metal) * Decimal("1000")) if metal else ZERO


def labour_rate_for(session: Session, metal_id: int | None,
                    on_date: date) -> tuple[Decimal, str]:
    """Making-labour rate per gram for a metal on a date (Labour Rate master).
    STD on NSE-2495 was 1,200.00 per g."""
    row = session.scalars(
        select(LabourRate)
        .where(LabourRate.metal_id == metal_id, LabourRate.is_active.is_(True),
               LabourRate.effective_from <= on_date)
        .order_by(LabourRate.effective_from.desc(), LabourRate.id.desc())
    ).first()
    if row is None:
        return ZERO, "no labour rate for this metal on the Labour Rate master"
    return _dec(row.rate), f"Labour Rate from {row.effective_from}"


def margin_for(session: Session) -> tuple[Decimal, str]:
    """Tag mark-up % from the Margin master: the active set marked for tag
    price, else the first active set. Live screen: 50 (Q1: the "20%" heard
    is taken to be the customer discount, not this figure)."""
    sets = session.scalars(select(MarginSet).where(MarginSet.is_active.is_(True))
                           .order_by(MarginSet.id)).all()
    pick = next((m for m in sets if m.tagprice_margin), None) or (sets[0] if sets else None)
    if pick is None:
        return ZERO, "no margin set on the Margin master"
    return _dec(pick.tag_margin_percent), f"Margin set {pick.margin_key}"


def latest_net(session: Session, job: Job) -> Decimal:
    """The job's net weight as last weighed - the finished piece's N-Wt."""
    v = session.scalars(
        select(JobVoucher).where(JobVoucher.job_id == job.id, JobVoucher.kind == "receive",
                                 JobVoucher.net_wt.is_not(None))
        .order_by(JobVoucher.vr_date.desc(), JobVoucher.vr_time.desc(), JobVoucher.id.desc())
    ).first()
    return _dec(v.net_wt) if v is not None else ZERO


def job_stones(session: Session, job: Job) -> list[StoneCost]:
    """Stones in the finished piece: per bag line, what went to a karigar and
    did not come back. Price is the Stone SKU's sale price per its unit; a
    line with no SKU is priced 0 and must be typed on the transfer."""
    out: list[StoneCost] = []
    for row in production.bag_ledger(session, job):
        iss_pcs, iss_wt = row["iss"]
        back_pcs, back_wt = row["back"]
        pcs, wt = iss_pcs - back_pcs, iss_wt - back_wt
        if pcs <= 0 and wt <= 0:
            continue
        sku = session.get(StoneSku, row.line.stone_sku_id) if row.line.stone_sku_id else None
        # Selling price, as the SKU costing verified on ER-1337 (sale, not cost).
        price = (_dec(sku.sale_price) or _dec(sku.cost_price)) if sku else ZERO
        unit = (sku.per if sku else "") or "Cts"
        out.append(StoneCost(
            label=f"{row.line.particulars} {row.line.size}".strip(), pcs=pcs,
            weight=wt, unit="pcs" if unit.lower().startswith("pc") else "ct",
            price=price, s_type=row.line.s_type or "",
        ))
    return out


def fill_prices(session: Session, job: Job, on_date: date | None = None, *,
                labour_weight: Any = None, margin_pct: Any = None,
                manual_amount: Any = 0, zero_tag: bool = False) -> TransferPrice:
    """"Fill Prices" for one job from the masters, as of ``on_date``.

    Reads: title from the Metal master, fine rate from Daily Metal Rate (Q11:
    taken to be the day's 24K rate), labour rate from the Labour Rate master,
    mark-up from the Margin master, stones from the job bag. Setting Amount is
    left 0 - it read 0.00 on the one transfer seen, and whether the setting
    labour paid to the karigar belongs there is asked as 28 Sept Q12.
    """
    from diagold.services import settings

    on_date = on_date or date.today()
    metal = session.get(Metal, job.metal_id) if job.metal_id else None
    notes: list[str] = []
    if metal is None:
        notes.append("The job has no metal, so the metal amount is 0.")
    info = rates.rate_for(session, metal.id, on_date) if metal else rates.RateInfo(ZERO, None)
    if metal is not None and not info.found:
        notes.append(f"No Daily Metal Rate for {metal.name} on or before {on_date}.")
    lab_rate, lab_src = labour_rate_for(session, job.metal_id, on_date)
    notes.append(lab_src)
    if margin_pct in (None, ""):
        margin_pct, m_src = margin_for(session)
        notes.append(m_src)
    net = latest_net(session, job)
    if labour_weight in (None, ""):
        notes.append("Labour is on the final net weight - which net weight the client "
                     "uses is to be confirmed (28 Sept Q2).")
    rule = settings.get_setting(session, TAG_DISPLAY_SETTING, "thousands")
    result = price_line(
        net_wt=net, title=title_of(metal), fine_rate=info.rate,
        stones=job_stones(session, job), labour_rate=lab_rate,
        labour_weight=labour_weight, manual_amount=manual_amount,
        margin_pct=margin_pct, pcs=job.pcs, zero_tag=zero_tag, tag_rule=rule,
    )
    result.notes = notes
    return result
