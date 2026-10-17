"""Quotation (9 Oct Session 5 §4.27, T-12).

Legacy Quot 161: header Quot No, Date + time, Ref, Currency, Quot Type, Terms,
Account, Sales Person, Attach Doc, Tracking No, Prices From Client Chart;
lines Sno, SKU, SKU Desc, C-Ref, Line P.O., Metal, Title, Loss%, Color, Size,
Pcs, G-Wt/Pcs, N-Wt/Pcs, Tot GWt, Metal Rate, Unit, Mt Amt (= N-Wt x Metal
Rate). A quotation never posts to the ledger (the legacy shows Cr Sales A/c /
Dr party on it - treated as a defect, Q6); it can be converted to an order.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class Quotation(Base, PKMixin, TimestampMixin):
    __tablename__ = "quotations"

    quot_no: Mapped[int] = mapped_column(unique=True, index=True)
    quot_date: Mapped[date] = mapped_column(Date, default=date.today)
    quot_time: Mapped[str] = mapped_column(String(8), default="")
    ref: Mapped[str] = mapped_column(String(64), default="")
    currency_code: Mapped[str] = mapped_column(String(8), default="INR")
    quot_type: Mapped[str] = mapped_column(String(24), default="")
    terms: Mapped[str] = mapped_column(String(120), default="")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    salesperson: Mapped[str] = mapped_column(String(64), default="")
    tracking_no: Mapped[str] = mapped_column(String(60), default="")
    client_chart: Mapped[bool] = mapped_column(Boolean, default=False)
    # Open -> Sent -> Accepted / Rejected; Converted once an order is made.
    status: Mapped[str] = mapped_column(String(12), default="Open")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"),
                                                 nullable=True)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    remark: Mapped[str] = mapped_column(Text, default="")

    STATUSES = ("Open", "Sent", "Accepted", "Rejected", "Converted")

    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan",
        order_by="QuotationLine.sno", lazy="selectin")


class QuotationLine(Base, PKMixin):
    __tablename__ = "quotation_lines"

    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id", ondelete="CASCADE"))
    sno: Mapped[int] = mapped_column(default=1)
    product_sku_id: Mapped[int | None] = mapped_column(ForeignKey("product_skus.id"),
                                                       nullable=True)
    sku_desc: Mapped[str] = mapped_column(String(200), default="")
    c_ref: Mapped[str] = mapped_column(String(64), default="")
    line_po: Mapped[str] = mapped_column(String(64), default="")
    metal_id: Mapped[int | None] = mapped_column(ForeignKey("metals.id"), nullable=True)
    title: Mapped[float] = mapped_column(Numeric(9, 3), default=0)
    loss_pct: Mapped[float] = mapped_column(Numeric(9, 2), default=0)
    colour: Mapped[str] = mapped_column(String(16), default="")
    size: Mapped[str] = mapped_column(String(24), default="")
    pcs: Mapped[int] = mapped_column(default=1)
    gwt_pcs: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    nwt_pcs: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    tot_gwt: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    metal_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unit: Mapped[str] = mapped_column(String(8), default="NetWt")
    mt_amt: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    stone_amt: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    labour_rate: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    labour: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    remark: Mapped[str] = mapped_column(String(200), default="")

    quotation: Mapped[Quotation] = relationship(back_populates="lines")
