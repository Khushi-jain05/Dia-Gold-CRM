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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
    """One stone head in the priced catalogue.

    "Emerald Pear" is a single head; every size it comes in sits underneath it
    in :class:`StoneSkuRange` rather than becoming its own record.
    """

    __tablename__ = "stone_skus"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(160), default="")
    stone_id: Mapped[int] = mapped_column(ForeignKey("stone_info.id"))

    # Optional on purpose: most legacy records hold "-" for these, but the
    # client asked for the columns and tied them to calculation (Q15).
    shape_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_shapes.id"), nullable=True
    )
    kind_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_kinds.id"), nullable=True
    )
    quality_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_qualities.id"), nullable=True
    )
    colour: Mapped[str] = mapped_column(String(32), default="")

    is_mrp: Mapped[bool] = mapped_column(Boolean, default=False)
    shelf_no: Mapped[str] = mapped_column(String(32), default="")
    rfid: Mapped[str] = mapped_column(String(64), default="")
    add_in_netwt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    stone: Mapped[StoneInfo] = relationship()
    shape: Mapped[StoneShape | None] = relationship()
    kind: Mapped[StoneKind | None] = relationship()
    quality: Mapped[StoneQuality | None] = relationship()
    ranges: Mapped[list["StoneSkuRange"]] = relationship(
        back_populates="stone_sku", cascade="all, delete-orphan", lazy="selectin"
    )
    vendors: Mapped[list["StoneSkuVendor"]] = relationship(
        back_populates="stone_sku", cascade="all, delete-orphan", lazy="selectin"
    )

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class StoneSkuRange(Base, PKMixin):
    """One priced size band of a stone head - the costing heart of the screen.

    Cost and sale are BOTH stored as entered. In the client's real data sale is
    sometimes below cost, so neither is derived from the other and no margin
    rule is imposed over them (Q16 / C-12).
    """

    __tablename__ = "stone_sku_ranges"

    stone_sku_id: Mapped[int] = mapped_column(
        ForeignKey("stone_skus.id", ondelete="CASCADE")
    )
    range_label: Mapped[str] = mapped_column(String(16), default="")  # a..z, A, U, 23
    cost_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    sale_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    per: Mapped[str] = mapped_column(String(8), default="Cts")
    size_id: Mapped[int | None] = mapped_column(
        ForeignKey("stone_sizes.id"), nullable=True
    )
    wt_per_pcs: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    min_wt: Mapped[float] = mapped_column(Numeric(12, 4), default=0)

    PER_UNITS = ("Cts", "Pcs", "Gms")

    stone_sku: Mapped[StoneSku] = relationship(back_populates="ranges")
    size: Mapped[StoneSize | None] = relationship()


class StoneSkuVendor(Base, PKMixin):
    """A vendor that supplies this stone head."""

    __tablename__ = "stone_sku_vendors"
    __table_args__ = (
        UniqueConstraint("stone_sku_id", "account_id", name="uq_stone_sku_vendor"),
    )

    stone_sku_id: Mapped[int] = mapped_column(
        ForeignKey("stone_skus.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    stone_sku: Mapped[StoneSku] = relationship(back_populates="vendors")
    account: Mapped[Account] = relationship()


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
