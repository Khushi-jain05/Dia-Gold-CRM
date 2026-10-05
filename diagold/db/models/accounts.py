"""Accounts (5 Oct Session 4 §4.2-4.5, T-01 / T-02 / T-04).

* AccountGroup - the chart of accounts as a tree (Account Group Master:
  Name, Code, Under, Sub Ledger Required, Index). Every Account sits in one
  group, by name (Account.group_name).
* AccountVoucher - Voucher Entry: Receipt, Payment, Journal, Contra. A
  receipt / payment is in a mode - Cash, Bank or Metal ("metal receive":
  settled in fine gold, valued at the day's rate).
* BillAllocation - which receipt / payment / return knocked off how much of
  which bill (bill-wise outstanding, FIFO by default).

Balances are never stored: the ledger, day book, trial balance, outstanding
and cash flow are all worked out from AccountEntry postings.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class AccountGroup(Base, PKMixin, TimestampMixin):
    __tablename__ = "account_groups"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    code: Mapped[str] = mapped_column(String(24), default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"),
                                                  nullable=True)
    sub_ledger_required: Mapped[bool] = mapped_column(Boolean, default=False)
    index_no: Mapped[int] = mapped_column(default=0)
    # Assets / Liabilities / Income / Expenses - where the group lands.
    nature: Mapped[str] = mapped_column(String(16), default="")


class AccountVoucher(Base, PKMixin, TimestampMixin):
    __tablename__ = "account_vouchers"

    vr_type: Mapped[str] = mapped_column(String(12), index=True)   # receipt/payment/journal/contra
    vr_no: Mapped[int] = mapped_column(index=True)
    vr_date: Mapped[date] = mapped_column(Date, default=date.today)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="Cash")      # Cash / Bank / Metal
    # The cash or bank ledger the money moves through (receipt / payment / contra).
    cash_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"),
                                                        nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    # Metal receive / pay: the metal, weight, fine and the day's rate.
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    fine_wt: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    metal_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    ref_no: Mapped[str] = mapped_column(String(64), default="")
    narration: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["AccountVoucherLine"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
        order_by="AccountVoucherLine.id", lazy="selectin")


class AccountVoucherLine(Base, PKMixin):
    """A Journal / Contra line: one account, debit or credit."""

    __tablename__ = "account_voucher_lines"

    voucher_id: Mapped[int] = mapped_column(ForeignKey("account_vouchers.id",
                                                       ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    debit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    narration: Mapped[str] = mapped_column(String(200), default="")

    voucher: Mapped[AccountVoucher] = relationship(back_populates="lines")


class BillAllocation(Base, PKMixin, TimestampMixin):
    """``amount`` of bill (bill_kind, bill_no) knocked off by the voucher
    (source_kind, source_no) - a receipt, payment or return."""

    __tablename__ = "bill_allocations"

    party_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    bill_kind: Mapped[str] = mapped_column(String(24))
    bill_no: Mapped[int] = mapped_column()
    source_kind: Mapped[str] = mapped_column(String(24))
    source_no: Mapped[int] = mapped_column()
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    alloc_date: Mapped[date] = mapped_column(Date, default=date.today)
