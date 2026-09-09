"""SKU module models - Stone SKU catalog and Product SKU master."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin
from diagold.db.models.master import Metal, SkuInfo, StoneInfo


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


class ProductSku(Base, PKMixin, TimestampMixin):
    """The design / product master - one row per catalogue style."""

    __tablename__ = "product_skus"

    sku_code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("sku_info.id"), nullable=True)
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    collection: Mapped[str] = mapped_column(String(80), default="")
    gender: Mapped[str] = mapped_column(String(16), default="Unisex")
    size: Mapped[str] = mapped_column(String(24), default="")

    gross_weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    net_weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    metal_weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    stone_weight_ct: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    stone_pieces: Mapped[int] = mapped_column(default=0)

    making_charge_type: Mapped[str] = mapped_column(String(16), default="Per Gram")
    making_charge: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    wastage_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)

    hsn_code: Mapped[str] = mapped_column(String(16), default="")
    image_path: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="Active")

    category: Mapped[SkuInfo | None] = relationship()
    metal: Mapped[Metal | None] = relationship()
    stones: Mapped[list["ProductSkuStone"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.sku_code} - {self.name}"


class ProductSkuStone(Base, PKMixin):
    """Stone bill-of-material line for a Product SKU."""

    __tablename__ = "product_sku_stones"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("product_skus.id", ondelete="CASCADE")
    )
    stone_id: Mapped[int | None] = mapped_column(ForeignKey("stone_info.id"), nullable=True)
    pieces: Mapped[int] = mapped_column(default=0)
    weight_ct: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    setting_type: Mapped[str] = mapped_column(String(32), default="")
    rate_per_ct: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)

    product: Mapped[ProductSku] = relationship(back_populates="stones")
    stone: Mapped[StoneInfo | None] = relationship()