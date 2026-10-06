"""Tools ▸ Register a Complaint and Gatepass (5 Oct §4.14, T-10). Built as
seen on the call; whether the client uses them is still to confirm (Q5)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class Complaint(Base, PKMixin, TimestampMixin):
    __tablename__ = "complaints"

    comp_no: Mapped[int] = mapped_column(unique=True, index=True)
    comp_date: Mapped[date] = mapped_column(Date, default=date.today)
    comp_from: Mapped[str] = mapped_column(String(16), default="Customer")  # Customer/Floor/Other
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    job_no: Mapped[int | None] = mapped_column(nullable=True)
    stock_no: Mapped[int | None] = mapped_column(nullable=True)
    sku: Mapped[str] = mapped_column(String(40), default="")
    complaint: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(8), default="Open")          # Open / Closed
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolution: Mapped[str] = mapped_column(String(200), default="")

    lines: Mapped[list["ComplaintLine"]] = relationship(
        cascade="all, delete-orphan", order_by="ComplaintLine.id", lazy="selectin")

    FROM = ("Customer", "Floor", "Other")


class ComplaintLine(Base, PKMixin):
    __tablename__ = "complaint_lines"

    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"))
    comp_type: Mapped[str] = mapped_column(String(40), default="")
    complaint: Mapped[str] = mapped_column(String(200), default="")
    related_person: Mapped[str] = mapped_column(String(80), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")


class GatePass(Base, PKMixin, TimestampMixin):
    __tablename__ = "gate_passes"

    gp_no: Mapped[int] = mapped_column(unique=True, index=True)
    gp_date: Mapped[date] = mapped_column(Date, default=date.today)
    box_weight: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    box_pcs: Mapped[int] = mapped_column(default=0)
    box_description: Mapped[str] = mapped_column(String(200), default="")
    destination: Mapped[str] = mapped_column(String(120), default="")
    delivery_remark: Mapped[str] = mapped_column(String(200), default="")
    packed_by: Mapped[str] = mapped_column(String(80), default="")
    delivered_by: Mapped[str] = mapped_column(String(80), default="")
    sealed_no: Mapped[str] = mapped_column(String(60), default="")
    # Receipt block
    received_by: Mapped[str] = mapped_column(String(80), default="")
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    receipt_remark: Mapped[str] = mapped_column(String(200), default="")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
