"""Costing primitives driven by the Metal master.

Rule from the client requirements (R5 / TR3): the purity recorded on a metal
head is the input to *every* downstream calculation. Nothing outside this
module may embed a purity constant - always read it from the master via
:func:`purity_fraction`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

# The Mining Metal Ratio rows for a head must total exactly this.
RATIO_TOTAL = Decimal("100.00")

# Nominal karat purities, expressed as a percentage of pure gold. These are
# DOCUMENTATION ONLY - used to seed a head whose name carries no explicit
# figure. A value stored on the master always wins over anything here.
NOMINAL_KARAT_PCT: dict[str, Decimal] = {
    "12KT": Decimal("50.00"),   # stated by the client: "fifty percent ... 0.5"
    "14KT": Decimal("58.50"),   # stated by the client: 58.5% / 0.585
    "18KT": Decimal("75.00"),   # 18/24 - arithmetic, not a client figure
    "22KT": Decimal("91.60"),
    "24KT": Decimal("99.90"),
}


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def purity_fraction(metal: Any) -> Decimal:
    """Return a metal head's purity as a 0-1 fraction.

    The legacy master records the same purity in three different notations and
    the client's data preserves all of them verbatim, so normalise on read:

    ==================  ==========  ============
    Stored value        Notation    Fraction
    ==================  ==========  ============
    ``590``             per mille   ``0.590``
    ``59.50``           percent     ``0.5950``
    ``0.585``           fraction    ``0.585``
    ==================  ==========  ============

    Reads ``purity_fineness`` off the master record - never a constant.
    """
    raw = _dec(getattr(metal, "purity_fineness", 0))
    if raw <= 0:
        return Decimal("0")
    if raw > 100:            # per mille, e.g. 590
        return raw / Decimal("1000")
    if raw > 1:              # percent, e.g. 59.50 or 61
        return raw / Decimal("100")
    return raw               # already a fraction, e.g. 0.585


def purity_percent(metal: Any) -> Decimal:
    """The same purity expressed as a percentage (59.00, 76.25 ...)."""
    return purity_fraction(metal) * Decimal("100")


def fine_metal_weight(metal: Any, gross_weight: Any) -> Decimal:
    """Pure-metal content of ``gross_weight`` grams of this head."""
    return _dec(gross_weight) * purity_fraction(metal)


def metal_value(metal: Any, weight: Any, rate_per_gram_pure: Any) -> Decimal:
    """Value of ``weight`` grams of this head at a rate quoted for pure metal.

    Purity is read from the Metal master, so a 14KT and an 18KT holding of the
    same weight value differently at the same gold rate.
    """
    amount = fine_metal_weight(metal, weight) * _dec(rate_per_gram_pure)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ratio_total(rows: Iterable[Any]) -> Decimal:
    """Sum the ratio percentages of a head's Mining Metal Ratio rows.

    Accepts ORM rows, plain dicts, or ``(base_metal, pct)`` pairs.
    """
    total = Decimal("0")
    for row in rows:
        if isinstance(row, dict):
            total += _dec(row.get("ratio_pct"))
        elif isinstance(row, (tuple, list)):
            total += _dec(row[1])
        else:
            total += _dec(getattr(row, "ratio_pct", 0))
    return total


def validate_metal_ratios(rows: Iterable[Any]) -> str | None:
    """Return an error message if the ratio rows do not total exactly 100.00.

    Empty is allowed (a head need not declare a ratio breakdown); anything
    else must be exact - 99.99 and 100.01 are both rejected.
    """
    rows = list(rows)
    if not rows:
        return None
    total = ratio_total(rows).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total != RATIO_TOTAL:
        return (
            f"Mining Metal Ratio must total exactly {RATIO_TOTAL}, but these "
            f"rows total {total}. Adjust the rows by {RATIO_TOTAL - total:+} "
            f"before saving."
        )
    return None


# ---------------------------------------------------------------------------
# Per-process loss
# ---------------------------------------------------------------------------
# The legend read off the client's Process screen. The letter is what the
# legacy system stores; the second item is the quantity the loss is measured
# against, so each process computes loss on its OWN basis - never a global one.
LOSS_BASES: tuple[tuple[str, str, str], ...] = (
    ("P", "PCS",      "pcs"),
    ("G", "GrossWt",  "gross_wt"),
    ("N", "NetWt",    "net_wt"),
    ("I", "ISS_NWT",  "issued_net_wt"),
    ("H", "HOURLY",   "hours"),
    ("S", "ST PCS",   "stone_pcs"),
    ("F", "Diff Wt",  "diff_wt"),
)

LOSS_BASIS_LABELS: dict[str, str] = {code: label for code, label, _ in LOSS_BASES}
_LOSS_BASIS_FIELD: dict[str, str] = {code: field for code, _, field in LOSS_BASES}


def loss_basis_label(code: str) -> str:
    """Human label for a stored loss-type letter, e.g. "N" -> "NetWt"."""
    return LOSS_BASIS_LABELS.get((code or "").strip().upper(), code or "")


def loss_basis_quantity(process: Any, **quantities: Any) -> Decimal:
    """The quantity this process measures its loss against.

    Pass whichever of pcs / gross_wt / net_wt / issued_net_wt / hours /
    stone_pcs / diff_wt are known for the job step.
    """
    code = (getattr(process, "loss_type", "") or "").strip().upper()
    field = _LOSS_BASIS_FIELD.get(code)
    if field is None:
        return Decimal("0")
    return _dec(quantities.get(field))


def process_loss(process: Any, **quantities: Any) -> Decimal:
    """Loss for one production step, on that step's own basis.

    Two processes with different loss types therefore produce different
    figures from the same job, which is exactly what the client described.
    """
    qty = loss_basis_quantity(process, **quantities)
    pct = _dec(getattr(process, "loss_percent", 0))
    return (qty * pct / Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


# ---------------------------------------------------------------------------
# Making labour (T-11)
# ---------------------------------------------------------------------------
NET_WEIGHT = "Net Weight"
GROSS_WEIGHT = "Gross Weight"


def labour_amount(rate: Any, *, net_weight: Any = 0, gross_weight: Any = 0,
                  weight_basis: str = NET_WEIGHT) -> Decimal:
    """Making labour for one item.

    The client charges labour on NET weight, not gross. The basis is an
    explicit, named argument rather than an implicit choice so every computed
    figure can be audited back to which weight it used.
    """
    weight = _dec(net_weight if weight_basis == NET_WEIGHT else gross_weight)
    return (weight * _dec(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Margin / mark-up (T-10)
# ---------------------------------------------------------------------------
MARGIN = "M"   # price = cost / (1 - rate)
MARKUP = "U"   # price = cost * (1 + rate)


def apply_margin(cost: Any, percent: Any, mode: str = MARKUP) -> Decimal:
    """Raise a cost by a percentage, as either a margin or a mark-up.

    The two are genuinely different and the legacy screen lets each component
    pick one, so both are implemented rather than conflated.
    """
    cost = _dec(cost)
    rate = _dec(percent) / Decimal("100")
    if mode == MARGIN:
        if rate >= 1:
            raise ValueError("A margin of 100% or more has no finite price.")
        price = cost / (Decimal("1") - rate)
    else:
        price = cost * (Decimal("1") + rate)
    return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_to(value: Any, step: Any) -> Decimal:
    """Round a price to the nearest step (0 or blank means no rounding)."""
    value, step = _dec(value), _dec(step)
    if step <= 0:
        return value
    return ((value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            * step).quantize(Decimal("0.01"))


@dataclass
class PriceBreakdown:
    """Tag price and customer price, with the inputs that produced them."""

    cost: Decimal
    tag_margin_percent: Decimal
    tag_mode: str
    tag_price: Decimal
    customer_discount_percent: Decimal
    customer_price: Decimal

    def as_rows(self) -> list[tuple[str, str]]:
        mode = "Margin" if self.tag_mode == MARGIN else "Markup"
        return [
            ("Cost", f"{self.cost}"),
            (f"Tag {mode} %", f"{self.tag_margin_percent}"),
            ("Tag Price", f"{self.tag_price}"),
            ("Customer Discount %", f"{self.customer_discount_percent}"),
            ("Customer Price", f"{self.customer_price}"),
        ]


def tag_and_customer_price(cost: Any, tag_margin_percent: Any,
                           customer_discount_percent: Any, *,
                           mode: str = MARKUP, round_off: Any = 0) -> PriceBreakdown:
    """The client's two-step commercial rule, both steps configurable.

    Stated as: cost + 50% margin, then the customer is given 20% less than
    that. Read literally that is ``cost * 1.50 * 0.80``. Neither percentage is
    a constant here - both come from the margin master, and the exact
    arithmetic is still being confirmed with the client (Q6).
    """
    cost = _dec(cost)
    tag = apply_margin(cost, tag_margin_percent, mode)
    discount = _dec(customer_discount_percent) / Decimal("100")
    customer = (tag * (Decimal("1") - discount)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return PriceBreakdown(
        cost=cost,
        tag_margin_percent=_dec(tag_margin_percent),
        tag_mode=mode,
        tag_price=round_to(tag, round_off),
        customer_discount_percent=_dec(customer_discount_percent),
        customer_price=round_to(customer, round_off),
    )


# ---------------------------------------------------------------------------
# SKU costing (T-23)
# ---------------------------------------------------------------------------
# These formulas were recovered from the client's live SKU ER-1337 and
# reconcile to the paisa on every figure. They were never narrated on the
# call - they come from the screen, which makes them the most reliable thing
# in the requirements.
#
#   line_amount   = weight_cts x SALE price      (not cost)
#   stone_amount  = sum(line_amount)
#   metal_rate    = pure_rate x fineness/1000
#   metal_amount  = net_wt x metal_rate          (net, never gross)
#   default_price = (stone_amount + metal_amount) x multiplier
#
# The multiplier defaults to 1.5 - the client's "cost + 50%" - and is a
# parameter, never a literal.
DEFAULT_PRICE_MULTIPLIER = Decimal("1.5")


def stone_line_amount(weight_cts: Any, sale_price: Any) -> Decimal:
    """One stone line's value. Uses the SALE price, verified on six of six rows.

    Cost price is stored too but is not what the amount is computed from - and
    in the client's real data sale is sometimes below cost, so no relationship
    between the two is assumed.
    """
    return (_dec(weight_cts) * _dec(sale_price)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def stone_amount(lines: Iterable[Any]) -> Decimal:
    """Sum of the stone lines. Accepts ORM rows, dicts or (weight, price) pairs."""
    total = Decimal("0")
    for line in lines:
        if isinstance(line, dict):
            total += stone_line_amount(line.get("weight_cts"), line.get("sale_price"))
        elif isinstance(line, (tuple, list)):
            total += stone_line_amount(line[0], line[1])
        else:
            total += stone_line_amount(
                getattr(line, "weight_cts", 0), getattr(line, "sale_price", 0)
            )
    return total


def sku_metal_rate(pure_rate_per_gram: Any, metal: Any) -> Decimal:
    """The per-gram rate for this metal head: pure rate scaled by its fineness.

    Fineness is read from the Metal master via :func:`purity_fraction`, so a
    head recorded as 600 gives 0.600 and 15,264.00 becomes 9,158.40. No purity
    constant appears here.
    """
    return (_dec(pure_rate_per_gram) * purity_fraction(metal)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def sku_metal_amount(net_weight: Any, metal_rate: Any) -> Decimal:
    """Metal value of the piece. NET weight - gross is carried but not used."""
    return (_dec(net_weight) * _dec(metal_rate)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def sku_default_price(stone_amt: Any, metal_amt: Any,
                      multiplier: Any = None) -> Decimal:
    """(stone + metal) x multiplier. The multiplier is configuration, not code."""
    mult = DEFAULT_PRICE_MULTIPLIER if multiplier is None else _dec(multiplier)
    return ((_dec(stone_amt) + _dec(metal_amt)) * mult).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


@dataclass
class SkuCosting:
    """Every derived money figure for one SKU, with its inputs."""

    stone_amount: Decimal
    metal_rate: Decimal
    metal_amount: Decimal
    labour_amount: Decimal
    finding_labour: Decimal
    setting_amount: Decimal
    total_rs: Decimal
    default_price: Decimal
    multiplier: Decimal


def cost_sku(*, stone_lines: Iterable[Any], net_weight: Any, metal: Any,
             pure_rate_per_gram: Any, labour_amount: Any = 0,
             finding_labour: Any = 0, setting_amount: Any = 0,
             multiplier: Any = None) -> SkuCosting:
    """Price one SKU from its stone lines, its weight and the day's metal rate.

    TOTAL RS is the stone amount. The client confirmed that Labour Amount,
    Finding Labour and Setting Amount are not wanted on the SKU screen, and the
    one record whose arithmetic could be verified agrees: all three were blank
    and TOTAL RS equalled Stone Amount exactly. The parameters remain so a
    caller can still supply them, but nothing in the application does.

    Setting labour is not lost - karigars are still paid per piece for setting,
    through the Setting Labour Chart and its month-end settlement.
    """
    stones = stone_amount(stone_lines)
    rate = sku_metal_rate(pure_rate_per_gram, metal)
    metal_amt = sku_metal_amount(net_weight, rate)
    labour = _dec(labour_amount) + _dec(finding_labour) + _dec(setting_amount)
    mult = DEFAULT_PRICE_MULTIPLIER if multiplier is None else _dec(multiplier)
    return SkuCosting(
        stone_amount=stones,
        metal_rate=rate,
        metal_amount=metal_amt,
        labour_amount=_dec(labour_amount),
        finding_labour=_dec(finding_labour),
        setting_amount=_dec(setting_amount),
        total_rs=(stones + labour).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        default_price=sku_default_price(stones, metal_amt, mult),
        multiplier=mult,
    )
