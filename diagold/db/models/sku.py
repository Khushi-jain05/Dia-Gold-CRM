"""S.K.U. module models.

Two screens the client uses constantly:

* **Stone SKU** - the priced catalogue of every stone in every size. Prices are
  held per (stone, size) per carat in a child grid, and that grid is the input
  to all stone costing.
* **Product SKU Master** - the register of every finished piece, with its
  images, its stone bill of material and the money panel.

Also the Item master, which classifies a Product SKU and supplies the code
prefixes used elsewhere.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import (Boolean, Date, ForeignKey, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin
from diagold.db.models.master import (Account, FamilyCategory, Metal, SettingType,
                                      SkuInfo, StoneInfo, StoneKind, StoneQuality,
                                      StoneShape, StoneSize)


# ---------------------------------------------------------------------------
# Item master (T-24)
# ---------------------------------------------------------------------------
class Item(Base, PKMixin, TimestampMixin):
    """The product category a SKU belongs to - Bangle, Jhumki, Choker...

    The three code fields are prefixes for auto-generated codes elsewhere. The
    legacy screen captions them as such, but every SKU seen was hand-typed, so
    generation stays off until the client confirms (Q24).
    """

    __tablename__ = "items"

    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(32), unique=True)  # sku prefix
    virtual_design_code: Mapped[str] = mapped_column(String(32), default="")
    mould_code: Mapped[str] = mapped_column(String(32), default="")
    unit: Mapped[str] = mapped_column(String(16), default="Pcs")
    number: Mapped[int] = mapped_column(default=0)
    pcs: Mapped[int] = mapped_column(default=1)
    # Stored, never acted on - a previous vendor's marketplace app is the only
    # known reason it exists (Q19 / C-10).
    shopify_code: Mapped[str] = mapped_column(String(64), default="")
    # The jewellery family this item belongs to. A Product SKU picks this up
    # automatically when its Item is chosen - the karat stays hand-typed.
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("family_categories.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    family: Mapped[FamilyCategory | None] = relationship()
    price_ranges: Mapped[list["ItemPriceRange"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class ItemPriceRange(Base, PKMixin):
    """One band of the "Set Sales Price Range For M.I.S. Report" grid."""

    __tablename__ = "item_price_ranges"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    srno: Mapped[int] = mapped_column(default=1)
    price_from: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    price_to: Mapped[float] = mapped_column(Numeric(18, 2), default=0)

    item: Mapped[Item] = relationship(back_populates="price_ranges")


# ---------------------------------------------------------------------------
# Stone SKU (T-20)
# ---------------------------------------------------------------------------
class StoneSku(Base, PKMixin, TimestampMixin):
    """A catalogue Stone SKU - the client's legacy "Stone SKU" master screen.

    Stone / Shape / Type / Quality / Colour are free-typed text here (no
    dropdown lookups), matching how the client's original screen works. The
    Range/Size Info fields are a single rate-card row per SKU, not a repeating
    grid - the client's screen has one range per SKU.
    """

    __tablename__ = "stone_skus"

    sku_code: Mapped[str] = mapped_column(String(64), unique=True)
    mrp: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    stone: Mapped[str] = mapped_column(String(80), default="")
    shape: Mapped[str] = mapped_column(String(32), default="")
    stone_type: Mapped[str] = mapped_column(String(32), default="")
    quality: Mapped[str] = mapped_column(String(32), default="")
    color: Mapped[str] = mapped_column(String(32), default="")
    shelf_no: Mapped[str] = mapped_column(String(24), default="")
    rfid: Mapped[str] = mapped_column(String(40), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    range_label: Mapped[str] = mapped_column(String(16), default="")
    cost_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    sale_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    per: Mapped[str] = mapped_column(String(16), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    wt_per_pcs: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    min_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)

    def __str__(self) -> str:  # pragma: no cover
        return self.sku_code


# ---------------------------------------------------------------------------
# Stone packets (unchanged from v0.1)
# ---------------------------------------------------------------------------
class StonePacket(Base, PKMixin, TimestampMixin):
    """A received lot / packet of loose stones, tracked by packet number."""

    __tablename__ = "stone_packets"

    packet_no: Mapped[str] = mapped_column(String(32), unique=True)
    stone_id: Mapped[int | None] = mapped_column(ForeignKey("stone_info.id"), nullable=True)
    lot_no: Mapped[str] = mapped_column(String(32), default="")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pieces: Mapped[int] = mapped_column(default=0)
    weight_ct: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    rate_per_ct: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    location: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="In Stock")
    remarks: Mapped[str] = mapped_column(Text, default="")

    stone: Mapped[StoneInfo | None] = relationship()
    supplier: Mapped[Account | None] = relationship()


# ---------------------------------------------------------------------------
# Product SKU Master (T-22)
# ---------------------------------------------------------------------------
class ProductSku(Base, PKMixin, TimestampMixin):
    """One finished piece - the densest screen in the application.

    The money fields are split deliberately: Stone Amount, Metal Amount,
    TOTAL RS and Default Price are DERIVED (see
    :mod:`diagold.services.costing`), while Manual Price % is typed. Both are
    stored; neither overwrites the other.
    """

    __tablename__ = "product_skus"

    sku_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    # The figure the legacy screen prints under the SKU (6200 on ER-1337). It is
    # not derivable from any other figure on the record and was never explained,
    # so it is stored and shown, never computed (see C-14).
    tag_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    description: Mapped[str] = mapped_column(String(200), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    category2: Mapped[str] = mapped_column(String(64), default="")
    pattern: Mapped[str] = mapped_column(String(64), default="")
    pattern2: Mapped[str] = mapped_column(String(64), default="")

    # -- classification -------------------------------------------------
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    s_item: Mapped[str] = mapped_column(String(64), default="")
    # Auto-filled from the Item master; the karat below is typed by hand.
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("family_categories.id"), nullable=True
    )
    style: Mapped[str] = mapped_column(String(64), default="")
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    # Copied from the chosen metal head so the screen shows it beside the metal,
    # exactly as the legacy form does. The costing always reads the master, not
    # this copy.
    metal_fineness: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    item_pcs: Mapped[int] = mapped_column(default=1)

    # -- physical --------------------------------------------------------
    mt_plt_col: Mapped[str] = mapped_column(String(32), default="")
    enamal_col: Mapped[str] = mapped_column(String(32), default="")
    jewelry_size: Mapped[str] = mapped_column(String(32), default="")
    chain_type: Mapped[str] = mapped_column(String(32), default="")
    length: Mapped[str] = mapped_column(String(32), default="")
    design_no: Mapped[str] = mapped_column(String(64), default="")
    mt_loss_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    tolerance_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    tolerance_g: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_loss_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    gross_weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    net_weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    stamp: Mapped[str] = mapped_column(String(32), default="")
    snap: Mapped[str] = mapped_column(String(32), default="")
    inscription: Mapped[str] = mapped_column(String(64), default="")
    jwl_type: Mapped[str] = mapped_column(String(32), default="")

    # -- flags -----------------------------------------------------------
    is_rubber: Mapped[bool] = mapped_column(Boolean, default=False)
    is_master: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cad: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cpx: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sizable: Mapped[bool] = mapped_column(Boolean, default=False)
    upc: Mapped[str] = mapped_column(String(48), default="")
    link_cert: Mapped[str] = mapped_column(String(48), default="")
    # The "MC%= 0.00 LC%= 0.00" readout. Zero on every record seen and never
    # explained, so both are carried but nothing is derived from them (C-14).
    mc_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    lc_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)

    # -- references (purpose not yet explained - Q22) ---------------------
    master_sku: Mapped[str] = mapped_column(String(40), default="")
    sku_ref: Mapped[str] = mapped_column(String(40), default="")
    hu_id: Mapped[str] = mapped_column(String(40), default="")

    min_pcs: Mapped[int] = mapped_column(default=0)
    box_qty: Mapped[int] = mapped_column(default=0)

    # -- images (T-25) ----------------------------------------------------
    image_finished: Mapped[str] = mapped_column(String(255), default="")
    image_design: Mapped[str] = mapped_column(String(255), default="")
    image_cad: Mapped[str] = mapped_column(String(255), default="")
    image_cert: Mapped[str] = mapped_column(String(255), default="")
    cad_stl_file: Mapped[str] = mapped_column(String(255), default="")

    # -- money -------------------------------------------------------------
    # Typed inputs
    labour_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    finding_labour: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    setting_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    extra_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    manual_price_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    # Derived and stored, so a saved SKU keeps the figures it was priced at
    stone_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    metal_rate: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    metal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_rs: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    default_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    item: Mapped[Item | None] = relationship()
    family: Mapped[FamilyCategory | None] = relationship()
    metal: Mapped[Metal | None] = relationship()
    stones: Mapped[list["ProductSkuStone"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )

    DERIVED_MONEY_FIELDS = (
        "stone_amount", "metal_rate", "metal_amount", "total_rs", "default_price",
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.sku_code} - {self.description}".strip(" -")


class ProductSkuStone(Base, PKMixin):
    """One stone line on a Product SKU.

    ``amount`` is computed from the SALE price, verified against six of six
    rows on the client's SKU ER-1337.
    """

    __tablename__ = "product_sku_stones"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("product_skus.id", ondelete="CASCADE")
    )
    stone_sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_skus.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(160), default="")
    size_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_sizes.id"), nullable=True
    )
    wt_per_pcs: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    min_wt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    pieces: Mapped[int] = mapped_column(default=0)
    weight_cts: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    # Zero on every row observed; meaning not yet explained (Q28).
    brk_wt_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    cost_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    sale_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    per: Mapped[str] = mapped_column(String(8), default="Cts")
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    setting_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("setting_types.id"), nullable=True
    )

    product: Mapped[ProductSku] = relationship(back_populates="stones")
    stone_sku: Mapped[StoneSku | None] = relationship()
    size: Mapped[StoneSize | None] = relationship()
