"""Master-data models - the Master menu.

These are the reference tables the rest of the ERP builds on: company profile,
currencies, party/ledger accounts, metals, findings, parts & moulds, and the
stone / SKU / manufacturing attribute masters.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class Company(Base, PKMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(128), default="Dia Gold")
    legal_name: Mapped[str] = mapped_column(String(160), default="")
    address_line1: Mapped[str] = mapped_column(String(160), default="")
    address_line2: Mapped[str] = mapped_column(String(160), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    country: Mapped[str] = mapped_column(String(80), default="India")
    pincode: Mapped[str] = mapped_column(String(20), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    gstin: Mapped[str] = mapped_column(String(30), default="")
    pan: Mapped[str] = mapped_column(String(20), default="")
    base_currency: Mapped[str] = mapped_column(String(8), default="INR")
    financial_year_start: Mapped[str] = mapped_column(String(10), default="04-01")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Currency(Base, PKMixin, TimestampMixin):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(8), default="")
    exchange_rate: Mapped[float] = mapped_column(Numeric(18, 6), default=1)
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Account(Base, PKMixin, TimestampMixin):
    """Party / ledger master - customers, suppliers, karigars, banks, expenses."""

    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    account_type: Mapped[str] = mapped_column(String(32), default="Client")
    group_name: Mapped[str] = mapped_column(String(64), default="Accounts Receivable")
    contact_person: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(80), default="")
    gstin: Mapped[str] = mapped_column(String(30), default="")
    pan: Mapped[str] = mapped_column(String(20), default="")
    currency_code: Mapped[str] = mapped_column(String(8), default="INR")
    opening_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    opening_balance_type: Mapped[str] = mapped_column(String(4), default="Dr")
    credit_days: Mapped[int] = mapped_column(default=0)
    credit_limit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # One master creates every party. Type is mainly a filter.
    ACCOUNT_TYPES = ("Client", "Worker", "Designer", "Accounts")

    # Read off the client's live system. NOTE: the source list was captured
    # alphabetically and stops at "IGST", so it is A-I only - the rest arrives
    # with the legacy export (C-01). "Sundry Debtors" is included because the
    # client's own seed rows use it.
    ACCOUNT_GROUPS = (
        "Accounts Payable", "Accounts Receivable", "Bangkok bank saving a/c",
        "Bank Account", "Branch/Divisions", "Cash-In-Hand", "CGST",
        "COST OF GOODS SOLD", "Current Assets", "Current Liabilities",
        "Deposits (Asset)", "Direct Expenses", "Direct Income",
        "Duties & Taxes", "Fixed Assets", "IGST", "Sundry Debtors",
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class Metal(Base, PKMixin, TimestampMixin):
    """A metal *head* - one purity/fineness of one base metal.

    Multiple heads exist per karat because casting batches differ in fineness
    (14KT CASTING 59.50 and 14KT CASTING 60.40 are distinct heads, not
    duplicates). The ``purity_fineness`` recorded here is the single source of
    truth for every downstream costing calculation - see
    :mod:`diagold.services.costing`. Never hard-code a purity elsewhere.
    """

    __tablename__ = "metals"

    name: Mapped[str] = mapped_column(String(80))  # "14KT CASTING 590"
    code: Mapped[str] = mapped_column(String(24), unique=True)
    print_on_tag: Mapped[str] = mapped_column(String(24), default="")  # "590"
    description: Mapped[str] = mapped_column(Text, default="")
    base_metal: Mapped[str] = mapped_column(String(32), default="GOLD")
    work_adjust_metal: Mapped[str] = mapped_column(String(32), default="")

    # The critical field. Recorded as the client declares it - 590 (per mille),
    # 59.50 (percent) and 0.585 (fraction) all occur in the legacy master and
    # are preserved verbatim. Use costing.purity_fraction() to normalise.
    purity_fineness: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    purity_for_custom: Mapped[float] = mapped_column(Numeric(12, 4), default=0)

    colour: Mapped[str] = mapped_column(String(24), default="")  # "Y" / "W" / "R"
    specific_gravity: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    purity_weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    hsn_code: Mapped[str] = mapped_column(String(16), default="")
    box_no: Mapped[str] = mapped_column(String(24), default="")
    is_mrp: Mapped[bool] = mapped_column(Boolean, default=False)
    is_effects_net_wt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    ratios: Mapped[list["MetalRatio"]] = relationship(
        back_populates="metal", cascade="all, delete-orphan", lazy="selectin"
    )
    vendors: Mapped[list["MetalVendor"]] = relationship(
        back_populates="metal", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}".strip(" -")


class MetalRatio(Base, PKMixin):
    """One row of a metal head's Mining Metal Ratio (base metal vs alloy).

    The rows for a head must total exactly 100.00 - enforced on save by
    :func:`diagold.services.costing.validate_metal_ratios`.
    """

    __tablename__ = "metal_ratios"

    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id", ondelete="CASCADE"))
    base_metal: Mapped[str] = mapped_column(String(32), default="GOLD")
    ratio_pct: Mapped[float] = mapped_column(Numeric(9, 3), default=0)

    metal: Mapped[Metal] = relationship(back_populates="ratios")


class MetalVendor(Base, PKMixin):
    """Link row - a vendor (an Account) that supplies this metal head."""

    __tablename__ = "metal_vendors"
    __table_args__ = (UniqueConstraint("metal_id", "account_id", name="uq_metal_vendor"),)

    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    metal: Mapped[Metal] = relationship(back_populates="vendors")
    account: Mapped["Account"] = relationship()


class Finding(Base, PKMixin, TimestampMixin):
    __tablename__ = "findings"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(64), default="")  # Clasp, Post, Jump ring
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    unit: Mapped[str] = mapped_column(String(8), default="gm")
    rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    metal: Mapped[Metal | None] = relationship()


class PartMould(Base, PKMixin, TimestampMixin):
    """The mould register - one row per mould, with its wax weight and history.

    Mould numbers follow prefix-number patterns (SLR-0139, SCR-013, SLR-485)
    but the format is deliberately not enforced: both 3- and 4-digit suffixes
    occur in the client's data.
    """

    __tablename__ = "parts_moulds"

    code: Mapped[str] = mapped_column(String(24), unique=True)   # Mould #
    name: Mapped[str] = mapped_column(String(120))               # Item
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="Mould")  # Part / Mould
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("family_categories.id"), nullable=True
    )
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    vendor_code: Mapped[str] = mapped_column(String(32), default="")

    wax_weight_per_pcs: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    no_of_pcs: Mapped[int] = mapped_column(default=1)
    l_price_gms: Mapped[float] = mapped_column(Numeric(12, 4), default=0)

    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    cad_file_desc: Mapped[str] = mapped_column(String(200), default="")
    part_no: Mapped[str] = mapped_column(String(48), default="")

    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    cavity_count: Mapped[int] = mapped_column(default=1)
    rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    metal: Mapped[Metal | None] = relationship()
    location: Mapped["Location | None"] = relationship()
    vendor: Mapped["Account | None"] = relationship()
    family: Mapped["FamilyCategory | None"] = relationship()
    modifications: Mapped[list["MouldModification"]] = relationship(
        back_populates="mould", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class MouldModification(Base, PKMixin, TimestampMixin):
    """An append-only entry in a mould's modification history.

    Past entries are never edited or deleted - the log is the record of how
    the mould changed over its life.
    """

    __tablename__ = "mould_modifications"

    mould_id: Mapped[int] = mapped_column(
        ForeignKey("parts_moulds.id", ondelete="CASCADE")
    )
    modified_on: Mapped[date] = mapped_column(Date, default=date.today)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    remark: Mapped[str] = mapped_column(String(200), default="")

    mould: Mapped[PartMould] = relationship(back_populates="modifications")


class SkuInfo(Base, PKMixin, TimestampMixin):
    """Product-category master used when creating Product SKUs."""

    __tablename__ = "sku_info"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    category: Mapped[str] = mapped_column(String(64))  # Ring, Necklace, Earring...
    sub_category: Mapped[str] = mapped_column(String(64), default="")
    hsn_code: Mapped[str] = mapped_column(String(16), default="")
    gender: Mapped[str] = mapped_column(String(16), default="Unisex")
    making_charge_type: Mapped[str] = mapped_column(String(16), default="Per Gram")
    making_charge: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.category}"


class StoneInfo(Base, PKMixin, TimestampMixin):
    """One stone, classified against the granular reference masters.

    A stone belongs to a Stone Group; its shape, kind, quality and size are
    their own lookup masters rather than free text, so the client can extend
    each list independently.
    """

    __tablename__ = "stone_info"

    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))  # Diamond, Ruby, CZ...

    stone_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_groups.id"), nullable=True
    )
    stone_kind_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_kinds.id"), nullable=True
    )
    shape_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_shapes.id"), nullable=True
    )
    quality_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_qualities.id"), nullable=True
    )
    size_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_sizes.id"), nullable=True
    )

    color: Mapped[str] = mapped_column(String(32), default="")
    sieve: Mapped[str] = mapped_column(String(24), default="")
    # The unit travels with the stone into costing: carats for diamond and
    # emerald, pieces for CZ.
    weight_unit: Mapped[str] = mapped_column(String(8), default="ct")
    rate_per_unit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    hsn_code: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    WEIGHT_UNITS = ("ct", "pcs", "gm")

    stone_group: Mapped["StoneGroup | None"] = relationship()
    stone_kind: Mapped["StoneKind | None"] = relationship()
    shape: Mapped["StoneShape | None"] = relationship()
    quality: Mapped["StoneQuality | None"] = relationship()
    size: Mapped["StoneSize | None"] = relationship()

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class ManufacturingProcess(Base, PKMixin, TimestampMixin):
    """A production step, carrying its OWN loss-calculation basis.

    Loss is computed per process step, never globally - CAD, casting and
    setting each lose material differently, so each row picks its own basis
    from :data:`LOSS_BASES`.
    """

    __tablename__ = "manufacturing_processes"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(80))  # CASTING, KHUDAI, Puwai...
    base_process: Mapped[str] = mapped_column(String(48), default="Job Work")
    labour_type: Mapped[str] = mapped_column(String(24), default="STD")

    # The letter is the legacy code: P/G/N/I/H/S/F - see costing.LOSS_BASES.
    loss_type: Mapped[str] = mapped_column(String(2), default="N")
    # Percentage applied to whichever quantity the loss basis selects.
    # NOTE: the meeting never stated where the loss rate itself is held; it may
    # belong on the job rather than the process. Confirm with the client.
    loss_percent: Mapped[float] = mapped_column(Numeric(9, 4), default=0)

    labour_accounting: Mapped[bool] = mapped_column(Boolean, default=False)
    module: Mapped[str] = mapped_column(String(48), default="")   # e.g. Factory-1
    is_print_vr: Mapped[bool] = mapped_column(Boolean, default=False)
    order_srno: Mapped[int] = mapped_column(default=0)
    labour_gn: Mapped[str] = mapped_column(String(48), default="")
    process_type: Mapped[str] = mapped_column(String(16), default="None")  # Wax / None

    # Per-process switches read off the legacy screen.
    check_weight_tolerance: Mapped[bool] = mapped_column(Boolean, default=False)
    fill_auto_stone: Mapped[bool] = mapped_column(Boolean, default=False)   # F3
    fill_auto_mould: Mapped[bool] = mapped_column(Boolean, default=False)   # F7
    use_diff_wt_as_metal: Mapped[bool] = mapped_column(Boolean, default=False)

    department: Mapped[str] = mapped_column(String(64), default="")
    sequence: Mapped[int] = mapped_column(default=1)
    rate_type: Mapped[str] = mapped_column(String(16), default="Per Gram")
    rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_inhouse: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    checkpoints: Mapped[list["ProcessCheckpoint"]] = relationship(
        back_populates="process", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class ProcessCheckpoint(Base, PKMixin):
    """One QC check point belonging to a manufacturing process."""

    __tablename__ = "process_checkpoints"

    process_id: Mapped[int] = mapped_column(
        ForeignKey("manufacturing_processes.id", ondelete="CASCADE")
    )
    srno: Mapped[int] = mapped_column(default=1)
    checkpoint: Mapped[str] = mapped_column(String(200), default="")

    process: Mapped[ManufacturingProcess] = relationship(back_populates="checkpoints")


class DefaultProcessStep(Base, PKMixin, TimestampMixin):
    """One step of the default process sequence (legacy "Set Default Process").

    The client never explained what the default sequence should be (open
    question Q13), so nothing is seeded here - the screen is ready for them
    to fill in.
    """

    __tablename__ = "default_process_steps"

    step_no: Mapped[int] = mapped_column(default=1)
    process_id: Mapped[int | None] = mapped_column(
        ForeignKey("manufacturing_processes.id"), nullable=True
    )
    remark: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    process: Mapped[ManufacturingProcess | None] = relationship()


class DailyMetalRate(Base, PKMixin, TimestampMixin):
    """The gold rate for one metal head on one date.

    History is never overwritten: a valuation for a past date reproduces
    exactly by reading the rate that applied on that date.
    """

    __tablename__ = "daily_metal_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "metal_id", name="uq_metal_rate_day"),
    )

    rate_date: Mapped[date] = mapped_column(Date)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"))
    rate_per_gram: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    # Optional override for the pure-metal rate this head is priced from.
    pure_rate_per_gram: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    remark: Mapped[str] = mapped_column(String(160), default="")

    metal: Mapped[Metal] = relationship()


class DailyLabourRate(Base, PKMixin, TimestampMixin):
    """Date-effective labour rate.

    Present in the legacy rights list but never discussed on the call, so this
    mirrors Daily Metal Rate and is flagged for confirmation (open question Q9).
    """

    __tablename__ = "daily_labour_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "metal_id", name="uq_labour_rate_day"),
    )

    rate_date: Mapped[date] = mapped_column(Date)
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    rate: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    remark: Mapped[str] = mapped_column(String(160), default="")

    metal: Mapped[Metal | None] = relationship()


class OtherSetting(Base, PKMixin, TimestampMixin):
    """Catch-all 'Other' master - miscellaneous configurable lists / settings."""

    __tablename__ = "other_settings"

    group_name: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Location(Base, PKMixin, TimestampMixin):
    """Where the firm's material physically sits.

    NOT a customer list (the client corrected this explicitly): a Location is a
    named karigar holding gold, a process area, a branch office, or a logical
    bucket. Stock and work-in-progress reference it, so it is a foreign key
    from the start. Retire entries with ``is_active`` - never delete, or
    historic stock movements stop resolving.
    """

    __tablename__ = "locations"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    location_type: Mapped[str] = mapped_column(String(24), default="Karigar")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    LOCATION_TYPES = ("Karigar", "Department", "Branch", "Logical")

    account: Mapped["Account | None"] = relationship()
    materials: Mapped[list["LocationMaterial"]] = relationship(
        back_populates="location", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class LocationMaterial(Base, PKMixin):
    """A material type held at a location.

    Different karigars hold different things - one handles gold, one handles
    setting, one holds loose stones - so a location carries however many tags
    it needs.
    """

    __tablename__ = "location_materials"
    __table_args__ = (
        UniqueConstraint("location_id", "material_type", name="uq_location_material"),
    )

    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE")
    )
    material_type: Mapped[str] = mapped_column(String(32), default="Gold")

    MATERIAL_TYPES = ("Gold", "Loose Stone", "Setting", "WIP", "Ready Stock", "Findings", "Mould")

    location: Mapped[Location] = relationship(back_populates="materials")


class SettingType(Base, PKMixin, TimestampMixin):
    """How a stone is set - Bezel, Channel, Prong, Pave..."""

    __tablename__ = "setting_types"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class FamilyCategory(Base, PKMixin, TimestampMixin):
    """The jewellery family an item belongs to."""

    __tablename__ = "family_categories"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Colour(Base, PKMixin, TimestampMixin):
    """Gold colour a design is made in - Yellow (default), Rose, White."""

    __tablename__ = "colours"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class LabourRate(Base, PKMixin, TimestampMixin):
    """Making-labour rate held PER KARAT, applied against NET weight.

    Distinct from setting labour (:class:`SettingLabourRate`), which is paid
    per piece to karigars for stone setting. Rates are effective-dated so a
    historic job keeps the rate that applied on its own date.
    """

    __tablename__ = "labour_rates"

    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    karat: Mapped[str] = mapped_column(String(24), default="")   # e.g. "18KT"
    rate: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    unit: Mapped[str] = mapped_column(String(16), default="Per Gram")
    # The client charges labour on net weight, not gross. Kept as a stored,
    # named basis so every computed figure is auditable (open question Q5).
    weight_basis: Mapped[str] = mapped_column(String(16), default="Net Weight")
    effective_from: Mapped[date] = mapped_column(Date, default=date.today)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    WEIGHT_BASES = ("Net Weight", "Gross Weight")

    metal: Mapped[Metal | None] = relationship()

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.karat} @ {self.rate}"


class MarginSet(Base, PKMixin, TimestampMixin):
    """A margin / mark-up configuration driving tag price and customer price.

    Margin is applied COMPONENT-WISE (labour, stone, setting, finding, metal),
    not as one number on the total. Every percentage is data, never a constant
    in the code - the exact arithmetic is still being confirmed (Q6).
    """

    __tablename__ = "margin_sets"

    margin_key: Mapped[str] = mapped_column(String(48), unique=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    advance_defination: Mapped[bool] = mapped_column(Boolean, default=False)
    loss_percent: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    tagprice_margin: Mapped[bool] = mapped_column(Boolean, default=False)
    overall_percent: Mapped[float] = mapped_column(Numeric(9, 4), default=0)

    # The client's stated rule: cost + 50% margin, then 20% less to the
    # customer. Both steps are separate, editable parameters.
    tag_margin_percent: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    customer_discount_percent: Mapped[float] = mapped_column(Numeric(9, 4), default=0)

    stone_group_wise: Mapped[bool] = mapped_column(Boolean, default=False)
    round_off: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    components: Mapped[list["MarginComponent"]] = relationship(
        back_populates="margin_set", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return self.margin_key


class MarginComponent(Base, PKMixin):
    """One priced component of a margin set, in Margin or Markup mode."""

    __tablename__ = "margin_components"
    __table_args__ = (
        UniqueConstraint("margin_set_id", "component", name="uq_margin_component"),
    )

    margin_set_id: Mapped[int] = mapped_column(
        ForeignKey("margin_sets.id", ondelete="CASCADE")
    )
    component: Mapped[str] = mapped_column(String(32), default="Labour")
    percent: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    mode: Mapped[str] = mapped_column(String(2), default="M")   # M: Margin, U: Markup

    COMPONENTS = ("Labour", "Stone", "Setting", "Finding", "Metal")
    MODES = ("M", "U")

    margin_set: Mapped[MarginSet] = relationship(back_populates="components")


class SettingLabourRate(Base, PKMixin, TimestampMixin):
    """Per-piece setting rate paid to karigars, keyed by stone group.

    Optionally narrowed by setting type or SKU - a SKU-level row overrides the
    group-level rate, mirroring the legacy "Setting Labour Chart (SKU)".
    Effective-dated so settling a past month never changes.
    """

    __tablename__ = "setting_labour_rates"

    stone_group: Mapped[str] = mapped_column(String(32), default="Diamond")
    setting_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("setting_types.id"), nullable=True
    )
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku_info.id"), nullable=True)
    rate_per_piece: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    effective_from: Mapped[date] = mapped_column(Date, default=date.today)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Decided by the client on the call.
    STONE_GROUPS = ("Diamond", "Polki", "Colour Stone")

    setting_type: Mapped["SettingType | None"] = relationship()
    sku: Mapped["SkuInfo | None"] = relationship()


class SettingWork(Base, PKMixin, TimestampMixin):
    """Setting work recorded against a karigar - the input to settlement.

    Piece counts must come from recorded work, never hand-entered at
    settlement time. The Manufacturing module will write these rows; the
    table exists now so the month-end calculation is real and testable.
    """

    __tablename__ = "setting_work"

    work_date: Mapped[date] = mapped_column(Date, default=date.today)
    karigar_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    stone_group: Mapped[str] = mapped_column(String(32), default="Diamond")
    setting_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("setting_types.id"), nullable=True
    )
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku_info.id"), nullable=True)
    pieces: Mapped[int] = mapped_column(default=0)
    remark: Mapped[str] = mapped_column(String(160), default="")

    karigar: Mapped["Account | None"] = relationship()


# ---------------------------------------------------------------------------
# Stone reference data (T-06)
# ---------------------------------------------------------------------------
# The legacy system splits this across nine masters and the client walked
# through them one by one, so the granular model is reproduced here rather
# than flattened. Setting Type and the Setting Labour Chart (with its SKU
# override) are the remaining two, defined above.
#
# NOTE: still awaiting the client's formal sign-off on this structure (Q1 /
# C-03). The design follows what they demonstrated on the call.
class StoneGroup(Base, PKMixin, TimestampMixin):
    """Diamond, Polki, Colour Stone - decided by the client, not proposed."""

    __tablename__ = "stone_groups"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class StoneShape(Base, PKMixin, TimestampMixin):
    """Round, Oval, Emerald cut..."""

    __tablename__ = "stone_shapes"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class StoneKind(Base, PKMixin, TimestampMixin):
    """The legacy "Type" master - Natural, Lab Grown, Imitation."""

    __tablename__ = "stone_kinds"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class StoneQuality(Base, PKMixin, TimestampMixin):
    """Clarity / quality grades - VS-GH, VS-FG..."""

    __tablename__ = "stone_qualities"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class StoneSize(Base, PKMixin, TimestampMixin):
    """Sizes are open-ended - users add them as new ones come into use."""

    __tablename__ = "stone_sizes"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    size_mm: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name
