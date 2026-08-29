"""Master-data models - the Master menu.

These are the reference tables the rest of the ERP builds on: company profile,
currencies, party/ledger accounts, metals, findings, parts & moulds, and the
stone / SKU / manufacturing attribute masters.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
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
    account_type: Mapped[str] = mapped_column(String(32), default="Customer")
    group_name: Mapped[str] = mapped_column(String(64), default="Sundry Debtors")
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

    ACCOUNT_TYPES = (
        "Customer", "Supplier", "Karigar", "Bank", "Cash", "Expense", "Income", "Other",
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name}"


class Metal(Base, PKMixin, TimestampMixin):
    __tablename__ = "metals"

    name: Mapped[str] = mapped_column(String(48))
    purity_label: Mapped[str] = mapped_column(String(24), default="")  # 22K, 18K, 925...
    fineness: Mapped[float] = mapped_column(Numeric(6, 4), default=0)  # 0.916, 0.750...
    color: Mapped[str] = mapped_column(String(24), default="")  # Yellow / White / Rose
    rate_per_gram: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    hsn_code: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} {self.purity_label}".strip()


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
    __tablename__ = "parts_moulds"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="Part")  # Part / Mould
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    cavity_count: Mapped[int] = mapped_column(default=1)
    location: Mapped[str] = mapped_column(String(64), default="")
    rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    metal: Mapped[Metal | None] = relationship()


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
    __tablename__ = "stone_info"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(80))  # Diamond, Ruby, CZ...
    stone_type: Mapped[str] = mapped_column(String(24), default="Natural")  # Natural/Lab/Imitation
    shape: Mapped[str] = mapped_column(String(32), default="Round")
    quality: Mapped[str] = mapped_column(String(32), default="")  # VS-GH, SI, etc.
    color: Mapped[str] = mapped_column(String(32), default="")
    size_mm: Mapped[str] = mapped_column(String(24), default="")
    sieve: Mapped[str] = mapped_column(String(24), default="")
    weight_unit: Mapped[str] = mapped_column(String(8), default="ct")  # ct / pcs
    rate_per_unit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    hsn_code: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.code} - {self.name} {self.shape}".strip()


class ManufacturingProcess(Base, PKMixin, TimestampMixin):
    """Process / department master for job-work routing and costing."""

    __tablename__ = "manufacturing_processes"

    code: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(80))  # Casting, Filing, Setting, Polish...
    department: Mapped[str] = mapped_column(String(64), default="")
    sequence: Mapped[int] = mapped_column(default=1)
    rate_type: Mapped[str] = mapped_column(String(16), default="Per Gram")
    rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_inhouse: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class OtherSetting(Base, PKMixin, TimestampMixin):
    """Catch-all 'Other' master - miscellaneous configurable lists / settings."""

    __tablename__ = "other_settings"

    group_name: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
