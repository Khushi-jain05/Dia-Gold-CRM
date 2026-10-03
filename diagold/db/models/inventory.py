"""Inventory vouchers - metal and stone (28 Sept R1 / R13, T-01).

One voucher shape serves every Inventory voucher the client showed: Metal
Purchase (Vr 185, SHRIKANT, 24KT 800 g), Metal Issue Outside / Worker (Vr 3969,
RAJESH JI -> CHAND KUMAR HAZRA 1.625 g), Metal Receipt (Vr 1083, TUHIN
BHANDARI, wastage), and the stone equivalents. ``vr_type`` says which; the
voucher number runs per type, as in the legacy system.

Every line posts one row to the stock ledger (:class:`StockMovement`) with its
fine weight worked out at posting time from the title in force - balances are
always the sum of movements, never typed. Which vouchers and columns the
client needs first is still to be ranked (28 Sept C-01 / Q10).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class InvVoucher(Base, PKMixin, TimestampMixin):
    __tablename__ = "inv_vouchers"
    __table_args__ = (UniqueConstraint("vr_type", "vr_no", name="uq_inv_voucher_no"),)

    vr_type: Mapped[str] = mapped_column(String(24), index=True)
    vr_no: Mapped[int] = mapped_column(index=True)
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    ref_no: Mapped[str] = mapped_column(String(64), default="")
    currency_code: Mapped[str] = mapped_column(String(8), default="INR")
    salesperson: Mapped[str] = mapped_column(String(64), default="")
    place_of_supply: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(64), default="")
    # Flags read off the legacy screens; what each does is to be explained
    # (28 Sept C-04) - they are recorded, and Opening is the only one acted on.
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    touch_xray: Mapped[bool] = mapped_column(Boolean, default=False)
    create_os: Mapped[bool] = mapped_column(Boolean, default=False)
    # Stone Issue (2 Oct §4.6): recorded, meaning UNCONFIRMED (Q7).
    worker_adjustment: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_adj: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["InvVoucherLine"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
        order_by="InvVoucherLine.sno", lazy="selectin",
    )


class InvVoucherLine(Base, PKMixin):
    __tablename__ = "inv_voucher_lines"

    voucher_id: Mapped[int] = mapped_column(ForeignKey("inv_vouchers.id", ondelete="CASCADE"))
    sno: Mapped[int] = mapped_column(default=1)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    mt_type: Mapped[str] = mapped_column(String(16), default="Actual")
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    stone_sku_id: Mapped[int | None] = mapped_column(ForeignKey("stone_skus.id"), nullable=True)
    particulars: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    colour: Mapped[str] = mapped_column(String(16), default="")
    pcs: Mapped[int] = mapped_column(default=0)
    weight: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    fine_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    unit: Mapped[str] = mapped_column(String(8), default="Gms")
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    wastage_pct: Mapped[float] = mapped_column(Numeric(9, 4), default=0)
    wastage_wt: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    job_no: Mapped[int | None] = mapped_column(nullable=True)
    s_type: Mapped[str] = mapped_column(String(24), default="")
    # Weight per piece of a stone line (legacy Wt/Pcs column, 2 Oct §4.6).
    wt_per_pcs: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    # Stone lot / certificate number (Stone Sale Register LOTNO, 2 Oct §4.10).
    lot_no: Mapped[str] = mapped_column(String(40), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")

    voucher: Mapped[InvVoucher] = relationship(back_populates="lines")


class AccountEntry(Base, PKMixin):
    """One side of the accounting a voucher posts - a purchase is "Dr
    Purchase A/c, Cr supplier" (28 Sept §4.12, T-01). A party row carries
    the Account; a nominal ledger such as Purchase A/c carries only its name."""

    __tablename__ = "account_entries"

    entry_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    ledger: Mapped[str] = mapped_column(String(80), default="")
    debit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    ref_kind: Mapped[str] = mapped_column(String(24), default="", index=True)
    ref_no: Mapped[int | None] = mapped_column(nullable=True, index=True)
    narration: Mapped[str] = mapped_column(String(200), default="")
