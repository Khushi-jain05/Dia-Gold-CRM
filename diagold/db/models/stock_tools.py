"""Tools ▸ Stock Reconciliation (5 Oct §4.14, T-09).

A reconciliation is a counting session - a date and, optionally, one
location - with the barcodes scanned (or imported from the scanner's TXT
file). It is kept, so a count can be stopped and carried on, and looked at
again later.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from diagold.db.models.base import Base, PKMixin, TimestampMixin


class StockRecon(Base, PKMixin, TimestampMixin):
    __tablename__ = "stock_recons"

    recon_no: Mapped[int] = mapped_column(index=True)
    recon_date: Mapped[date] = mapped_column(Date, default=date.today)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    remark: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    scans: Mapped[list["StockReconScan"]] = relationship(
        cascade="all, delete-orphan", order_by="StockReconScan.id", lazy="selectin")


class StockReconScan(Base, PKMixin):
    __tablename__ = "stock_recon_scans"

    recon_id: Mapped[int] = mapped_column(ForeignKey("stock_recons.id", ondelete="CASCADE"))
    barcode: Mapped[str] = mapped_column(String(40))
